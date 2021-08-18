Title: Python behind the scenes #12: how async/await works in Python
Date: 2021-07-29 7:00
Tags: Python behind the scenes, Python, CPython

Mark functions as `async`. Call them with `await`. All of a sudden, your program becomes asynchronous – it can do useful things while it waits for other things, such as I/O operations, to complete.

Code written in the `async`/`await` style looks like regular synchronous code but works very differently. To understand how it works, one should be familiar with many non-trivial concepts including concurrency, parallelism, event loops, I/O multiplexing, asynchrony, cooperative multitasking and coroutines. Python's implementation of `async`/`await` adds even more concepts to this list: generators, generator-based coroutines, native coroutines, `yield` and `yield from`. Because of this complexity, some Python programmers prefer not to use `async`/`await` at all, while many others use it but do not realize how it actually works. I believe that neither should be the case. The `async`/`await` pattern can be explained in a simple manner if you start from the ground up. And that's what we're going to do today.

## It's all about concurrency 

Computers execute programs sequentially – one instruction after another. But a typical program performs multiple tasks, and it doesn't always make sense to wait for some task to complete before starting the next one. For example, a chess program that waits for a player to make a move should be able to update the clock in the meantime. Such an ability of a program to deal with multiple things simultaneously is what we call **concurrency**. Concurrency doesn't mean that multiple tasks must run at the same physical time. They can run in an interleaved manner: a task runs for some time, then suspends and lets other tasks run, hoping it will get more time in the future. For this reason, a modern OS can run thousands of processes on a machine that has only a few cores. If multiple tasks do run at the same physical time, as in the case of a multi-core machine or a cluster, then we have **parallelism**, a special case of concurrency.

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

If the tasks are independent, then you can make the program concurrent by decomposing each function into several functions and call the decomposed functions in an interleaved manner, like so:

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

Of course, this is an oversimplified example. The point here is that the language doesn't determine whether you can write concurrent programs or not but may provide features that make concurrent programming more convenient. As we'll learn today, `async`/`await` is just such a feature.

To see how one goes from concurrency to  `async`/`await`, we'll write a real-world concurrent program – a TCP echo server that supposed to handle multiple clients simultaneously. We'll start with the simplest, sequential version of the server that is not concurrent. Then, we'll make it concurrent using OS threads. After that, we'll see how we can write the concurrent version that runs in a single thread using I/O multiplexing. From this point onwards, we'll develop the single-threaded approach by introducing event loops, callbacks, generators, coroutines and, finally, `async`/`await`.

## A sequential server

Writing a TCP echo server that handles only one client at a time is straightforward. The server listens for incoming connections on some port, and when a client connects, the server talks to the client until the connection is closed. Then it continues to listen for new connections. This logic can be implemented using basic socket programming:

```python
# echo_01_seq.py

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

Take time to study this code. We'll be using it as a framework for subsequent, concurrent versions of the server. If you need a reminder on sockets, check out [Beej's Guide to Network Programming](https://beej.us/guide/bgnet/) and the [docs on the `socket` module](https://docs.python.org/3/library/socket.html). What we do here in a nutshell is:

1. create a new TCP/IP socket with `socket.socket()`
2. bind the socket to an address and a port with `sock.bind()`
3. mark the socket as a "listeting" socket with `sock.listen()`
4. accept new connections with `sock.accept()`
5. read data from the client with `sock.recv()` and send the data back to the client with `sock.sendall()`.

This version of server is not concurrent by design. When multiple clients try to connect to the server at about the same time, one client connects and occupies the server, while other clients wait until the current client disconnects. I wrote a simple simulation program to demonstrate this:

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

The clients connect, send the same two messages and disconnect. It takes half a second for a client to type a message, and thus, it takes about three seconds for the server to serve all the clients. A single slow client, however, could make the server unavailable for an arbitrary long time. We should really make the server concurrent!

## OS threads

The easiest way to make the server concurrent is by using OS threads. We just run the `handle_client()` function in a separate thread instead of calling it in the main thread and leave the rest of the code  unchanged:

```python
# echo_02_threads.py

import socket
import threading


def run_sever(host='127.0.0.1', port=55555):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen()
    while True:
        client_sock, addr = sock.accept()
        print('Connection from', addr)
        thread = threading.Thread(target=handle_client, args=[client_sock])
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

Thread pools solve the problem of uncontrolled thread creation. Instead of submiting each task to a separate thread, we submit tasks to a queue and let a group of threads, called a **thread pool**, take and process the tasks  from the queue. We predefine the maximum number of threads in a thread pool, so the server cannot start too many threads. Here's how we can implement the server based on a thread pool using the Python standard [`concurrent.futures`](https://docs.python.org/3/library/concurrent.futures.html#threadpoolexecutor) module:

```python
# echo_03_thread_pool.py

import socket
from concurrent.futures import ThreadPoolExecutor


pool = ThreadPoolExecutor(max_workers=20)


def run_sever(host='127.0.0.1', port=55555):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen()
    while True:
        client_sock, addr = sock.accept()
        print('Connection from', addr)
        pool.submit(handle_client, client_sock)


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

Think about the sequential server again. Such a server always waits for some specific event to happen. When it has no connected clients, it waits for a new client to connect. When it has a connected client, it waits for this client to send some data. To work concurrently, however, the server should instead be able to handle any event that happens next. If the current client doesn't send anything, but a new client connects, the server should accept the new connection. Then it should maintain multiple active connections and reply to the client that sends data next.

But how can the server know what event it should handle next? By default, socket methods such as `accept()`, `recv()` and `sendall()` are all blocking. So if the server decides to call `accept()`, it will block until a new client connects and won't be not able to call `recv()` on the client sockets in the meantime. We could solve this problem by setting a timeout on blocking socket operations with `sock.settimeout(timeout)` or by turning a socket into a completely non-blocking mode with `sock.setblocking(False)`. We could then maintain a set of active sockets and, for each socket, call the correspoding socket method in an infinite loop. So, we would call `accept()` on the socket that listens for new connections and `recv()` on the sockets that wait for clients to send data.

The problem with the described approach is that it's not clear how to do the polling right. If we make all the sockets non-blocking or set timeouts too short, the server will be making calls all the time and consume a lot of CPU. Conversely, if we set timeouts too long, the server will be slow to reply.

The better approach is to ask the OS which sockets are ready for reading and writing. Clearly, the OS has this information. When a new packet arrives on a network interface, the OS gets notified, decodes the packet, determines the socket to which the packet belongs and wakes up the processes that do a blocking read on that socket. But a process doesn't need to read from the socket to get notified. It can use an **I/O multiplexing** mechanism such as [`select()`](https://man7.org/linux/man-pages/man2/select.2.html), [`poll()`](https://man7.org/linux/man-pages/man2/poll.2.html) or [`epoll()`](https://man7.org/linux/man-pages/man7/epoll.7.html) to tell the OS that it's interested in reading from or writing to some socket. When the socket becomes ready, the OS will wake up such processes as well.

The Python standard [`selectors`](https://docs.python.org/3/library/selectors.html) module wraps different I/O multiplexing mechanisms available on the system and provides the same high-level API, called a selector, to each of them. So it provides `select()` as `SelectSelector` and `epoll()` as `EpollSelector`. It also provides the most efficient mechanism available on the system as `DefaultSelector`.

Let me quickly show you how you're supposed to use the `selectors` module. You first create a selector object:

```python
sel = selectors.DefaultSelector()
```

Then you register a socket that you want to monitor. You pass the socket, the types of events you're interested in (the socket becomes ready for reading or writing) and any auxiliary data to the selector's [`register()`](https://docs.python.org/3/library/selectors.html#selectors.BaseSelector.register) method:

```python
sel.register(sock, selectors.EVENT_READ, my_data)
```

Finally, you call the selector's [`select()`](https://docs.python.org/3/library/selectors.html#selectors.BaseSelector.select) method:

```python
keys_events = sel.select()
```

This call returns a list of `(key, events)` tuples. Each tuple describes a ready socket:

* `key` is an object that stores the socket (`key.fileobj`) and the auxiliary data associated with the socket (`key.data`).
* `events` is a bitmask of events ready on the socket (`selectors.EVENT_READ` or `selectors.EVENT_WRITE` or both).

If there are ready sockets when you call `select()`, then `select()` returns immideatly. Otherwise, it blocks until some of the registered sockets become ready. The OS will notify `select()` as it notifies blocking socket methods like `recv()`.

What should we do with a ready socket? We certainly had some idea of what do to with the socket when we registered it, so let's register every socket with a callback that should be called when the socket becomes ready. That's, by the way, what the auxially data parameter of the selector's `register()` method is for. 

When we no longer need to monitor some socket, we just pass it to the selector's [`unregister()`](https://docs.python.org/3/library/selectors.html#selectors.BaseSelector.unregister) method.

We're now ready to implement a single-threaded concurrent version of the server using I/O multiplexing:

```python
# echo_04_io_multiplexing.py

import socket
import selectors


sel = selectors.DefaultSelector()


def setup_listening_socket(host='127.0.0.1', port=55555):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen()
    sel.register(sock, selectors.EVENT_READ, accept)


def accept(sock):
    client_sock, addr = sock.accept()
    print('Connection from', addr)
    sel.register(client_sock, selectors.EVENT_READ, recv_and_send)


def recv_and_send(sock):
    recieved_data = sock.recv(4096)
    if recieved_data:
        # assume sendall won't block
        sock.sendall(recieved_data)
    else:
        print('Client disconnected:', sock.getpeername())
        sel.unregister(sock)
        sock.close()


def run_event_loop():
    while True:
        for key, _ in sel.select():
            callback = key.data
            sock = key.fileobj
            callback(sock)


if __name__ == '__main__':
    setup_listening_socket()
    run_event_loop()
```

Here we first register an `accept()` callback on the listening socket. This callback accepts new clients and registers a `recv_and_send()` callback on every client socket. The core of the program is the **event loop** – an infinite loop that, on every iteration, selects ready sockets and calls the corresponding callbacks.

The event loop version of the server handles multiple clients perfectly fine. Its main disadvantage compared to the multi-threaded versions is that the code is structured in a weird, callback-centered way. The code in our example doesn't look so bad, but this is in part because we do not handle all the things properly. For example, writing to a socket may block if the write queue is full, so we should also check whether the socket is ready for writing before calling `sock.sendall()`. This means that the `recv_and_send()` function must be decomposed into two functions, and one of these functions must be registered as a callback at any given time depending on the server's state. The problem would be even more apparent if implemented something more complex than the primitive echo protocol.

OS threads do not impose callback style programming on us, yet they provide concurrency. How is that possible? The key here is the ability of the OS to suspend and resume thread execution. If we had functions that can be suspended and resumed like OS threads, we could write concurrent single-threaded code. Guess what? Pyhon allows us to write such functions. 

## Generator functions and generators

A **generator function** is a function that has one or more [`yield`](https://docs.python.org/3/reference/expressions.html#yield-expressions) expressions in its body, like this one:

```pycon
$ python -q
>>> def gen():
...     yield 1
...     yield 2
...     return 3
... 
>>> 
```

When you call a generator function, Python doesn't run the function's code as it does for ordinary functions but returns a **generator object**, or simply a **generator**:

```pycon
>>> g = gen()
>>> g
<generator object gen at 0x105655660>
```

To actually run the code, you pass the generator to the built-in [`next()`](https://docs.python.org/3/library/functions.html#next) function. This function calls the generator's [`__next__()`](https://docs.python.org/3/reference/expressions.html#generator.__next__) method that runs the generator to the first `yield` expression, at which point it suspends the execution and returns the argument of `yield`. Calling `next()` second time resumes the generator from the point where it was suspended, runs it to the next `yield` expression and returns its argument:

```pycon
>>> next(g)
1
>>> next(g)
2
```

When no more `yield` expressions are left, calling `next()` raises a `StopIteration` exception:

```pycon
>>> next(g)
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
StopIteration: 3
```

If the generator returns something, the exception holds the returned value:

```pycon
>>> g = gen()
>>> next(g)
1
>>> next(g)
2
>>> try:
...     next(g)
... except StopIteration as e:
...     e.value
... 
3
```

Initially generators were introduced to Python as an alternative way to write iterators. Recall that in Python, an object that can be iterated over (as with a `for` loop) is called an **iterable**. An iterable implements the [`__iter__()`](https://docs.python.org/3/reference/datamodel.html#object.__iter__) special method that returns an **iterator**. An iterator, in turn, implements the [`__next__()`](https://docs.python.org/3/library/stdtypes.html#iterator.__next__) special method that returns the next value every time you call it. Every iterator is also an iterable. It implements [`__iter__()`](https://docs.python.org/3/reference/datamodel.html#object.__iter__) that returns the iterator itself. Generators allowed us to write iterators as functions that `yield` values instead of defining classes with special methods. Python fills the special methods for us so that generators become iterators automatically.

We can get the generated values by calling `next()` but we typically iterate over them with a `for` loop:

```pycon
>>> for i in gen():
...     i
... 
1
2
```

Generators produce values in a lazy, on-demand manner, so they are memory-efficient and can even be used to generate infinite sequences. [PEP 255](https://www.python.org/dev/peps/pep-0255/) describes how generators can be used to generate values. We, however, want to use generators for a completely different reason. What's important for us is not the values that a generator produces but the mere fact that it can be suspended and resumed.

## Generators as coroutines

Take any program that performs multiple tasks. Turn functions that represent these tasks into generators by inserting few `yield` statements here and there. Then run the generators in a round-robin fashion: call `next()` on every generator in some fixed order and repeat this step until all the generators are exhausted. You'll get a concurrent program that runs like this:

picture??

Let's apply this strategy to the sequential server to make it concurrent. First, we insert some `yield` statements. I suggest to insert them before every blocking operation. Then, we need to run generators. I suggest to write a class that maintains a queue of scheduled generators (or simply tasks) and provides the `run()` method that runs the tasks in a loop in a round-robin fashion. We'll call this class `EventLoopNoIO` since it functions like an event loop except that it doesn't do I/O multiplexing. Here's the server code:

```python
# echo_05_yield_no_io.py

import socket

from event_loop_01_no_io import EventLoopNoIO


loop = EventLoopNoIO()


def run_sever(host='127.0.0.1', port=55555):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen()
    while True:
        yield
        client_sock, addr = sock.accept()
        print('Connection from', addr)
        loop.create_task(handle_client(client_sock))


def handle_client(sock):
    while True:
        yield
        recieved_data = sock.recv(4096)
        if not recieved_data:
            break
        yield
        sock.sendall(recieved_data)

    print('Client disconnected:', sock.getpeername())
    sock.close()


if __name__ == '__main__':
    loop.create_task(run_sever())
    loop.run()
```

and here's the event loop code:

```python
# event_loop_01_no_io.py

from collections import deque


class EventLoopNoIO:
    def __init__(self):
        self.tasks_to_run = deque([])

    def create_task(self, coro):
        self.tasks_to_run.append(coro)

    def run(self):
        while self.tasks_to_run:
            task = self.tasks_to_run.popleft()
            try:
                next(task)
            except StopIteration:
                continue
            self.create_task(task)
```

The problem with this solution is that it provides very limited concurrency. The tasks run in an interleaved manner, but their order is fixed. So if the next scheduled task is the task that accepts new connections, tasks that handle connected clients will have to wait until a new client connects.

Another way to phrase this problem is to say that the event loop doesn't check whether socket operations will block, so we can fix it by adding I/O multiplexing. Instead of rescheduling a task immediately after running it, the event loop should reschedule the task only when the socket that the task is waiting on becomes available for reading (or writing). A task can register its intention to read from or write to a socket by calling some event loop method. Alternatively, it can just `yield` this information to the event loop. Here's a version of the server that takes the latter approach:

```python
# echo_06_yield_io.py

import socket

from event_loop_02_io import EventLoopIo


loop = EventLoopIo()


def run_sever(host='127.0.0.1', port=55555):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen()
    while True:
        yield 'wait_read', sock
        client_sock, addr = sock.accept()
        print('Connection from', addr)
        loop.create_task(handle_client(client_sock))


def handle_client(sock):
    while True:
        yield 'wait_read', sock
        recieved_data = sock.recv(4096)
        if not recieved_data:
            break
        yield 'wait_write', sock
        sock.sendall(recieved_data)

    print('Client disconnected:', sock.getpeername())
    sock.close()


if __name__ == '__main__':
    loop.create_task(run_sever())
    loop.run()
```

And here's the new event loop that does I/O multiplexing:

```python
# event_loop_02_io.py

from collections import deque
import selectors


class EventLoopIo:
    def __init__(self):
        self.tasks_to_run = deque([])
        self.sel = selectors.DefaultSelector()

    def create_task(self, coro):
        self.tasks_to_run.append(coro)

    def run(self):
        while True:
            if self.tasks_to_run:
                task = self.tasks_to_run.popleft()
                try:
                    op, arg = next(task)
                except StopIteration:
                    continue

                if op == 'wait_read':
                    self.sel.register(arg, selectors.EVENT_READ, task)
                elif op == 'wait_write':
                    self.sel.register(arg, selectors.EVENT_WRITE, task)
                else:
                    raise ValueError('Unknown event loop operation:', op)
            else:
                for key, _ in self.sel.select():
                    task = key.data
                    sock = key.fileobj
                    self.sel.unregister(sock)
                    self.create_task(task)

```

What do we get out of it? First, we get the server that handles multiple clients perfectly fine:

```text
$ python clients.py 
[00.185755] Client 0 tries to connect.
        [00.186700] Client 1 tries to connect.
                [00.186975] Client 2 tries to connect.
[00.188485] Client 0 connects.
        [00.188753] Client 1 connects.
                [00.188820] Client 2 connects.
[00.691060] Client 0 sends "Hello".
        [00.691454] Client 1 sends "Hello".
                [00.691605] Client 2 sends "Hello".
[00.692412] Client 0 recieves "Hello".
        [00.692527] Client 1 recieves "Hello".
                [00.692680] Client 2 recieves "Hello".
[01.196732] Client 0 sends "world!".
        [01.196933] Client 1 sends "world!".
                [01.197188] Client 2 sends "world!".
[01.197494] Client 0 recieves "world!".
[01.197624] Client 0 disconnects.
        [01.197687] Client 1 recieves "world!".
        [01.197766] Client 1 disconnects.
                [01.198063] Client 2 recieves "world!".
                [01.198195] Client 2 disconnects.
```

Second, we get the code that looks like regular sequential code. Of course, we had to write the event loop, but this is not something you typically do yourself. Event loops come with libraries, and in Python, you're most likely to use an event loop that comes with [`asyncio`](https://docs.python.org/3/library/asyncio.html).

When you use generators for multitasking, as we did in this section, you typically refer to them as coroutines. **Coroutines** are functions that can be supsended by explicitly yielding the control. So, according to this definition, simple generators with `yield` expressions are enough to implement coroutines. A true coroutine, however, should also be able to yield the control to other coroutines by calling them. But generators can yield the control only to the caller.

We'll see why we need true coroutines if try to factor out some generator's code into a subgenerator. Consider these two lines of code of the `handle_client()` generator:

```python
yield 'wait_read', sock
recieved_data = sock.recv(4096)
```

It would be very handy to factor them out into a separate function:

```python
def async_recv(sock, n):
    yield 'wait_read', sock
    return sock.recv(n)
```

and then call the function like this:

```python
recieved_data = async_recv(sock, 4096)
```

But it won't work. The `async_recv()` function returns a generator, not the data. So the `handle_client()` generator has to run the `async_recv()` subgenerator with `next()`. However, it can't just call `next()` until the subgenerator is exhausted. The subgenerator yields values to the event loop, so `handle_client()` has to reyield them. It also has to handle the `StopIteration` exception and extract the result. Obviously, the amount of work that it has to do exceeds all the benefits of factoring out two lines of code.

Python made several attempts at solving this issue. First, [PEP 342](https://www.python.org/dev/peps/pep-0342/) introduced enhanced generators in Python 2.5. Generators got the [`send()`](https://docs.python.org/3/reference/expressions.html#generator.send) method that works like `__next__()` but also sends a value to the generator. The value becomes the value of the `yield` expression that the generator is suspended on:

```pycon
>>> def consumer():
...     val = yield 1
...     print('Got', val)
...     val = yield
...     print('Got', val)
... 
>>> c = consumer()
>>> next(c)
1
>>> c.send(2)
Got 2
>>> c.send(3)
Got 3
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
StopIteration
```

In fact, the generator's `__next__()` method became simply a shorthand for `send(None)`.

Generators also got the [`throw()`](https://docs.python.org/3/reference/expressions.html#generator.throw) method that runs the generator like `send()` or `__next__()` but also raises a specified exception at the suspension point and the [`close()`](https://docs.python.org/3/reference/expressions.html#generator.close) method that raises a [`GeneratorExit`](https://docs.python.org/3/library/exceptions.html#GeneratorExit) exception.

The introduction of `send()` allowed us to write "reverse" generators that get input values with `yield` and send output values to some other generator by calling `send()`. We're, however, interested in this enhancement because it allowed us to implement true coroutines. Instead of running a subgenerator inplace, we could now `yield` it to the event loop, run it in the event loop and then `send()` its result to the generator (or throw an exception into the generator if the subgenerator raises one). The generator would call the subgenerator like this:

```python
recieved_data = yield async_recv(sock)
```

and this call would work just as if one coroutine calls another.

This solution requires some non-trivial logic in the event loop, and you may find it hard to understand. Don't worry. You don't need to. [PEP 380](https://www.python.org/dev/peps/pep-0380/) introduced a much more intuitive solution for implementing coroutines in Python 3.3.

## yield from

You've probably used `yield from` to yield values from an iterable. So you should know that this statement:

```python
yield from iterable
```

works as a shorthand for this piece of code:

```python
for i in iterable:
    yield i
```

But `yield from` does a bit more when you use it with generators. It does exactly what a generator is supposed to do to run a subgenerator inplace. It calls `next()` on the subgenerator and reyields the yielded value, gets the value sended to the generator and repasses it to the subgenerator with `send()`, reyields the next yielded value and continues this process until the subgenerator raises an exception. It catches the `StopIteration` exception and extracts the result from it. It also propagates any exception raised by calling the generator's [`throw()`](https://docs.python.org/3/reference/expressions.html#generator.throw) method into the subgenerator and closes the subgenerator if the generator's [`close()`](https://docs.python.org/3/reference/expressions.html#generator.close) method was called. All in all, the PEP [says](https://www.python.org/dev/peps/pep-0380/#id13) that this statement:

```python
RESULT = yield from EXPR
```

is semantically equivalent to this code:

```python
_i = iter(EXPR)
try:
    _y = next(_i)
except StopIteration as _e:
    _r = _e.value
else:
    while 1:
        try:
            _s = yield _y
        except GeneratorExit as _e:
            try:
                _m = _i.close
            except AttributeError:
                pass
            else:
                _m()
            raise _e
        except BaseException as _e:
            _x = sys.exc_info()
            try:
                _m = _i.throw
            except AttributeError:
                raise _e
            else:
                try:
                    _y = _m(*_x)
                except StopIteration as _e:
                    _r = _e.value
                    break
        else:
            try:
                if _s is None:
                    _y = next(_i)
                else:
                    _y = _i.send(_s)
            except StopIteration as _e:
                _r = _e.value
                break
RESULT = _r
```

The code may seem complicated but what it essentially does is make the subgenerator work as if its code were a part of the generator. So this `yield from` call:

```python
recieved_data = yield from async_recv(sock)
```

works as if the call were replaced with the code of `async_recv()`. That's also counts as a coroutine call. And in contrast to the previous `yield`-based solution, the event loop logic stays the same.

Let's take advantage of `yield from` to make the server's code more concise. First, we factor out every boilerplate `yield` statement and the following socket operation to a separate generator function. We put these functions in the event loop:

```python
# event_loop_03_yield_from.py

from collections import deque
import selectors


class EventLoopYieldFrom:
    def __init__(self):
        self.tasks_to_run = deque([])
        self.sel = selectors.DefaultSelector()

    def create_task(self, coro):
        self.tasks_to_run.append(coro)

    def sock_recv(self, sock, n):
        yield 'wait_read', sock
        return sock.recv(n)

    def sock_sendall(self, sock, data):
        yield 'wait_write', sock
        sock.sendall(data)
    
    def sock_accept(self, sock):
        yield 'wait_read', sock
        return sock.accept()

    def run(self):
        while True:
            if self.tasks_to_run:
                task = self.tasks_to_run.popleft()
                try:
                    op, arg = next(task)
                except StopIteration:
                    continue

                if op == 'wait_read':
                    self.sel.register(arg, selectors.EVENT_READ, task)
                elif op == 'wait_write':
                    self.sel.register(arg, selectors.EVENT_WRITE, task)
                else:
                    raise ValueError('Unknown event loop operation:', op)
            else:
                for key, _ in self.sel.select():
                    task = key.data
                    sock = key.fileobj
                    self.sel.unregister(sock)
                    self.create_task(task)

```

Then, we `yield from` the generators in the server's code:

```python
from collections import deque
import socket

from event_loop import EventLoop


loop = EventLoop()


def run_sever(host='127.0.0.1', port=55555):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen()
    while True:
        client_sock, addr = yield from loop.sock_accept(sock)
        print('Connection from', addr)
        loop.create_task(handle_client(client_sock))


def handle_client(sock: socket.socket):
    while True:
        recieved_data = yield from loop.sock_recv(sock, 4096)
        if not recieved_data:
            break
        yield from loop.sock_sendall(sock, recieved_data)

    print('Client disconnected:', sock.getpeername())
    sock.close()


if __name__ == '__main__':
    loop.create_task(run_sever())
    loop.run()
```

And that's it! Generators, `yield` and `yield from` are all we need to implement coroutines, and coroutines allow us to write asynchronous, concurrent code. What about `async`/`await`? Well, it's just a synactic feature on top of generators that was introduced to fix the generators' ambiguity.

## async/await

When you see a generator function, you cannot always say immediately whether it's intended to be used as a regular generator or as a coroutine. In both cases, the function looks like any other function defined with `def` and contains a bunch of `yield` and `yield from` expressions. [PEP 492](https://www.python.org/dev/peps/pep-0492/) introduced the `async` and `await` keywords in Python 3.5 to make coroutines a distinct concept. 

You define a **native coroutine** **function** using the `async def` syntax:

```pycon
>>> async def coro():
...     return 1
... 
```

When you call such a function, it returns a **native coroutine object**, or simply a **native coroutine**. A native coroutine is pretty much the same thing as a generator except that it has a different type and doesn't implement `__next__()`. Event loops call `send(None)` to run native coroutines:

```pycon
>>> coro().send(None)
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
StopIteration: 1
```

Native coroutines can call each other with the `await` keyword:

```pycon
>>> async def coro2():
...     r = await coro()
...     return 1 + r
... 
>>> coro2().send(None)
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
StopIteration: 2
```

The `await` keyword does exactly the same thing with coroutines that `yield from` does with generators. In fact, `await` implemented as `yield from` with some additional checks to ensure that the object being awaited is not a regular generator or some other iterable.

When you use generators as coroutines, you must end every chain of `yield from` calls with a generator that does `yield`. Similarly, you must end every chain of `await` calls with a `yield` expression. However, if you try to use a `yield` expression in an `async def` function, what you'll get is not a native coroutine but something called an asynchronous generator:

```pycon
>>> async def g():
...     yield 2
... 
>>> g()
<async_generator object g at 0x1046c6790>
```

We're not going spend time on asynchronous generators here, but in a nutshell, they implement the asynchronous version of the iterator protocol: the [`__aiter__()`](https://docs.python.org/3/reference/datamodel.html#object.__aiter__) and [`__anext__()`](https://docs.python.org/3/reference/datamodel.html#object.__anext__) special methods. See [PEP 525 ](https://www.python.org/dev/peps/pep-0525/) to learn more. What's important for us at now is that `__anext__()` is awaitable while asynchronous generators themeselves are not. Thus, we cannot end a chain of `await` calls with an `async def` function containing `yield`. What should we end the chain with? There are two options.

First, we can write a regular generator function and decorate it with `@types.coroutine`. This decorator sets a special flag on the function behind the generator so that the generator can be used in an `await` expression just like a native coroutine:

```pycon
>>> import types
>>> @types.coroutine
... def gen_coro():
...     yield 3
... 
>>> async def coro3():
...     await gen_coro()
... 
>>> coro3().send(None)
3
```

A generator decorated with `@types.coroutine` is called a **generator-based coroutine**. Why do we need such coroutines? Well, if Python allowed us to `await` on regular generators, we would again mix the concepts of generators and coroutines and come back to the same ambiguity problem. The `@types.coroutine` decorator explicitly says that the generator is a coroutine.

As a second option, we can make any object awaitable by defining the [`__await__()`](https://docs.python.org/3/reference/datamodel.html#object.__await__) special method. When we `await` on some object, `await` first checks whether the object is a native coroutine or a generator-based coroutine, in which case it "yields from" the coroutine. Otherwise, it "yields from" the iterator returned by the object's `__await__()` method. This iterator may be a regular generator:

```pycon
>>> class A:
...     def __await__(self):
...             yield 4
... 
>>> async def coro4():
...     await A()
... 
>>> coro4().send(None)
4
```

Let's now write the final version of the server using `async`/`await`. First, we mark the server's functions with `async` and change `yield from` calls to `await` calls:

```python
# echo_08_async_await.py

import socket

from event_loop_04_async_await import EventLoopAsyncAwait


loop = EventLoopAsyncAwait()


async def run_sever(host='127.0.0.1', port=55555):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen()
    while True:
        client_sock, addr = await loop.sock_accept(sock)
        print('Connection from', addr)
        loop.create_task(handle_client(client_sock))


async def handle_client(sock):
    while True:
        recieved_data = await loop.sock_recv(sock, 4096)
        if not recieved_data:
            break
        await loop.sock_sendall(sock, recieved_data)

    print('Client disconnected:', sock.getpeername())
    sock.close()


if __name__ == '__main__':
    loop.create_task(run_sever())
    loop.run()
```

Then, we modify the event loop. We decorate generator functions with `@types.coroutine` so that they can be used with `await` and run the tasks by calling `send(None)` instead of `next()`:

```python
# event_loop_04_async_await.py

from collections import deque
import selectors
import types


class EventLoopAsyncAwait:
    def __init__(self):
        self.tasks_to_run = deque([])
        self.sel = selectors.DefaultSelector()

    def create_task(self, coro):
        self.tasks_to_run.append(coro)

    @types.coroutine
    def sock_recv(self, sock, n):
        yield 'wait_read', sock
        return sock.recv(n)

    @types.coroutine
    def sock_sendall(self, sock, data):
        yield 'wait_write', sock
        sock.sendall(data)
    
    @types.coroutine
    def sock_accept(self, sock):
        yield 'wait_read', sock
        return sock.accept()

    def run(self):
        while True:
            if self.tasks_to_run:
                task = self.tasks_to_run.popleft()
                try:
                    op, arg = task.send(None)
                except StopIteration:
                    continue

                if op == 'wait_read':
                    self.sel.register(arg, selectors.EVENT_READ, task)
                elif op == 'wait_write':
                    self.sel.register(arg, selectors.EVENT_WRITE, task)
                else:
                    raise ValueError('Unknown event loop operation:', op)
            else:
                for key, _ in self.sel.select():
                    task = key.data
                    sock = key.fileobj
                    self.sel.unregister(sock)
                    self.create_task(task)

```

And we're done! We've implemented an `async`/`await`-based concurrent server from scratch. It works exactly like the previous version of the server based on `yield from` and only has a slightly different syntax. 

By now, you should understand what `async`/`await` is all about. But you also should have questions about implementation details of generators, coroutines, `yield`, `yield from` and `await`. We're going to cover that  in the next section.

## How generators and coroutines are implemented

