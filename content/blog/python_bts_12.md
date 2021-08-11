Title: Python behind the scenes #12: how async/await works in Python
Date: 2021-07-29 7:00
Tags: Python behind the scenes, Python, CPython

Mark functions as `async`. Call them with `await`. All of a sudden, your program becomes asynchronous – it can do useful things while it waits for other things, such as I/O operations, to complete.

Code written in the `async`/`await` style looks like regular synchronous code but works very differently. To understand how it works, one should be familiar with many non-trivial concepts including concurrency, parallelism, event loops, I/O multiplexing, asynchrony, cooperative multitasking and coroutines. Python's implementation of `async`/`await` adds even more concepts to this list: generators, generator-based coroutines, native coroutines, `yield` and `yield from`. Because of this complexity, some Python programmers prefer not to use `async`/`await` at all, while many others use it but do not realize how it actually works. I believe that neither should be the case. The `async`/`await` pattern can be explained in a simple manner if you start from the ground up, and that's what this post aims to do.

## It's all about concurrency 

Computers execute programs sequentially – one instruction after another. But a typical program performs multiple tasks, and it doesn't always make sense to wait for some task to complete before starting the next one. For example, a chess program that waits for a player to make a move should be able to update the clock in the meantime. Such an ability of a program to deal with multiple things simultaneously is what we call **concurrency**. Concurrency doesn't mean that multiple tasks must run at the same physical time. They can run in an interleaved manner: a task runs for some time, then suspends and lets other tasks to run, hoping it will get more time in the future. For this reason, a modern OS can run thousands of processes on a machine that has only a few cores. If multiple tasks do run at the same physical time, as in the case of a multi-core machine or a cluster, then we have **parallelism**, a special case of concurrency.

A picture??

It's crucial to understand that you can write concurrent programs without any special support from the language. Suppose you write a program that performs two tasks, each task being represented by a separate function:

```python
def do_task1():
	# ...

def do_task2():
	# ...

def main():
    do_task1()
    do_task2()
```

If the tasks are independent, then you can decompose each function into several functions and call the decomposed functions in an interleaved manner to get concurrency:

```python
def do_task1_part1():
	# ...
	
def do_task1_part2():
	# ...

def do_task2_part1():
	# ...
	
def do_task2_part2():
	# ...

def main():
    do_task1_part1()
    do_task2_part1()
    do_task1_part2()
    do_task2_part2()
```

Of course, this is an oversimplified example. The point here is that the language doesn't determine whether you can write concurrent programs or not but may provide features that make concurrent programming more convenient. The `async`/`await` pattern is just such a feature.

To see how one goes from concurrency to  `async`/`await`, we'll write a real-world concurrent program – a TCP echo server that supposed to handle multiple clients simultaneously. We'll start with the simplest, sequential version of the server that is not concurrent. Then, we'll make it concurrent using OS threads. After that, we'll see how we can write the concurrent version that runs in a single thread using I/O multiplexing. From this point onwards, we'll develop the single-threaded approach by introducing event loops, callbacks, generators, coroutines and, finally, `async`/`await`.

## A sequential server

Writing a TCP echo server that handles only one client at a time is straightforward. The server listens for incoming connections on some port, and when a client connects, the server talks to the client until the connection is closed. Here's how this logic can be implemented using basic socket programming:

```python
# echo_seq.py

import socket


def run_sever(host='127.0.0.1', port=55555):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen()
    while True:
        client_sock, addr = sock.accept()
        print('Connection from', addr)
        handle_client(client_sock)


def handle_client(sock: socket.socket):
    while True:
        recieved_data = sock.recv(4096)
        if not recieved_data:
            break
        sock.sendall(recieved_data)

    print('Client disconnected:', sock.getpeername())
    sock.close()


if __name__ == '__main__':
    run_sever()
```

If you need a reminder on sockets, check out [Beej's Guide to Network Programming](https://beej.us/guide/bgnet/) and the [docs on the `socket` module](https://docs.python.org/3/library/socket.html). What we do here in a nutshell is:

1. create a new TCP/IP socket with `socket.socket()`
2. bind the socket to an address and a port with `sock.bind()`
3. mark the socket as a "listeting" socket with `sock.listen()`
4. accept new connections with `sock.accept()`
5. read data from the client with `sock.recv()` and send the data back to the client with `sock.sendall()`.

By design, the server is not concurrent. When multiple clients try to connect to the server at about the same time, one client connects and occupies the server, while other clients wait until the current client disconnects. To demonstrate this behavior, I wrote a simple simulation program:

```text
$ python clients.py 
[00.089920] Client 0 tries to connect.
        [00.090327] Client 1 tries to connect.
                [00.090591] Client 2 tries to connect.
[00.091846] Client 0 connects.
[00.594164] Client 0 sends "Hello".
[00.594418] Client 0 recieves "Hello".
[01.098472] Client 0 sends "world!".
[01.098699] Client 0 recieves "world!".
[01.098834] Client 0 disconnects.
        [01.100122] Client 1 connects.
        [01.602280] Client 1 sends "Hello".
        [01.602492] Client 1 recieves "Hello".
        [02.106502] Client 1 sends "world!".
        [02.106746] Client 1 recieves "world!".
        [02.106880] Client 1 disconnects.
                [02.107984] Client 2 connects.
                [02.613505] Client 2 sends "Hello".
                [02.613746] Client 2 recieves "Hello".
                [03.115106] Client 2 sends "world!".
                [03.115378] Client 2 recieves "world!".
                [03.115628] Client 2 disconnects.
```

Clients connect, send the same two messages and disconnect. It takes half a second for a client to type a message, and thus, it takes about three seconds for the server to serve all the clients. A single slow client, however, could make the server unavailable for an arbitrary long time.

## OS threads

The easiest way to make the server concurrent is by using OS threads. We just run the `handle_client()` function in a separate thread instead of calling it in the main thread and leave the rest of the code  unchanged:

```python
import socket
import threading # first change


def run_sever(host='127.0.0.1', port=55555):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen()
    while True:
        client_sock, addr = sock.accept()
        print('Connection from', addr)
        thread = threading.Thread(target=handle_client, args=[client_sock]) # second change
        thread.start()


def handle_client(sock: socket.socket):
    while True:
        recieved_data = sock.recv(4096)
        if not recieved_data:
            break
        sock.sendall(recieved_data)

    print('Client disconnected:', sock.getpeername())
    sock.close()


if __name__ == '__main__':
    run_sever()
```

Now multiple clients can talk to the server simultaneously:

```text
$ python clients.py 
[00.160676] Client 0 tries to connect.
        [00.161220] Client 1 tries to connect.
                [00.161499] Client 2 tries to connect.
[00.163616] Client 0 connects.
        [00.165548] Client 1 connects.
                [00.166799] Client 2 connects.
[00.667159] Client 0 sends "Hello".
        [00.667496] Client 1 sends "Hello".
                [00.667868] Client 2 sends "Hello".
[00.668173] Client 0 recieves "Hello".
        [00.668275] Client 1 recieves "Hello".
                [00.668426] Client 2 recieves "Hello".
[01.172414] Client 0 sends "world!".
        [01.172645] Client 1 sends "world!".
                [01.172778] Client 2 sends "world!".
[01.172963] Client 0 recieves "world!".
[01.173096] Client 0 disconnects.
        [01.173159] Client 1 recieves "world!".
        [01.173234] Client 1 disconnects.
                [01.173835] Client 2 recieves "world!".
                [01.174323] Client 2 disconnects.
```

The one-thread-per-client approach is easy to implement but doesn't scale well. OS threads are an expensive resource in terms of memory, so you can't have too many of them. For example, the Linux machine that serves this website is capable of running about 8k threads at most. And that's the hard limit. Even fewer threads may be enough to swamp the server. The server doesn't just work poorly under heavy workloads; it also becomes an easy target for a DoS attack.

**Thread pools** solve the problem of uncontrolled thread creation. Instead of submiting each task to a separate thread, we submit tasks to a queue and let a group of threads, called a thread pool, take and process the tasks  from the queue. We predefine the maximum number of threads in a thread pool, so the server cannot start too many threads. To implement the concurrent server based on a thread pool, we can  use the Python standard [`concurrent.futures`](https://docs.python.org/3/library/concurrent.futures.html#threadpoolexecutor) module:

```python
import socket
from concurrent.futures import ThreadPoolExecutor # first change


def run_sever(host='127.0.0.1', port=55555):
    pool = ThreadPoolExecutor(max_workers=20) # second change
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen()
    while True:
        client_sock, addr = sock.accept()
        print('Connection from', addr)
        pool.submit(handle_client, client_sock) # third change


def handle_client(sock: socket.socket):
    while True:
        recieved_data = sock.recv(4096)
        if not recieved_data:
            break
        sock.sendall(recieved_data)

    print('Client disconnected:', sock.getpeername())
    sock.close()


if __name__ == '__main__':
    run_sever()
```

The thread pool approach is both simple and practical. Note, however, that you still need to do something to prevent slow clients from occupying the thread pool. You may drop long-living connections, require the clients to maintain some minimum throughput rate, let the threads return the tasks to the queue or combine any of the suggested methods. The conclusion here is that making the server concurrent using OS threads is not as straightforward as it may seem at first, and it's worthwhile to explore other approaches to concurrency. 

## I/O multiplexing

