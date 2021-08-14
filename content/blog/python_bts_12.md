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

Think about the sequential server again. Such a server always waits for some specific event to happen. When it has no connected clients, it waits for a new client to connect. When it has a connected client, it waits for this client to send some data. To work concurrently, however, the server should instead be able to handle any event that happens next. If the current client doesn't send anything, but a new client connects, the server should accept the new connection. Then it should maintain multiple active connections and reply to the client that sends data next.

But how can we know what event the server should handle next? By default, socket methods such as `accept()`, `recv()` and `sendall()` are all blocking. So if we decide to call `accept()`, the program will block until a new client connects, and we won't be able to call `recv()` on client sockets in the meantime. We could solve this problem by setting a timeout on the blocking socket methods with `sock.settimeout(timeout)` or by turning a socket into a non-blocking mode with `sock.setblocking(False)`. We could then maintain a set of active sockets and, for each socket, call the correspoding socket method in an infinite loop. So, we would call `accept()` on the socket that listens for new connections and `recv()` on the sockets that wait for clients to send data.

The problem with the described approach is that it's not clear how to do the polling right. If we make all the sockets non-blocking or set timeouts too short, then the server will be making calls all the time and consume a lot of CPU. Conversely, if we set timeouts too long, the server will be slow to reply.

The better approach is to ask the OS which sockets are ready for reading and writing. Clearly, the OS has this information. When a new packet arrives on a network interface, the OS gets notified, decodes the packet, determines the socket to which the packet belongs and wakes up the processes that do blocking `recv()` on that socket. But a process doesn't need to call `recv()` to get notified. It can use an **I/O multiplexing** mechanism such as [`select()`](https://man7.org/linux/man-pages/man2/select.2.html), [`poll()`](https://man7.org/linux/man-pages/man2/poll.2.html) or [`epoll()`](https://man7.org/linux/man-pages/man7/epoll.7.html) to tell the OS that it's interested in reading from or writing to some socket. When the socket becomes ready, the OS will wake up such a process as well.

The Python standard [`selectors`](https://docs.python.org/3/library/selectors.html) module wraps different I/O multiplexing mechanisms available on the system and provides the same high-level API to each of them. For example, it wraps `select()` with `SelectSelector` and `epoll()` with `EpollSelector`. It provides the most efficient mechanism available on the system as `DefaultSelector`. Here's how you are supposed to use it. You first create a selector object:

```python
sel = selectors.DefaultSelector()
```

Then you register a socket that you want to monitor. You pass the socket, the types of events (read or write) and any auxiliary data to the selector's `register()` method:

```python
sel.register(sock, selectors.EVENT_READ, my_data)
```

Finally, you call the selector's `select()` method:

```python
keys_events = sel.select()
```

This call returns a list of `(key, events)` tuples. Each tuple describes a ready socket:

* `key` is an object that stores the socket (`key.fileobj`) and the auxiliary data associated with the socket (`key.data`).
* `events` is a bitmask of events ready on the socket (`selectors.EVENT_READ` or `selectors.EVENT_WRITE` or both).

If there are ready sockets when you call `select()`, then `select()` returns immideatly. Otherwise, it blocks until some of the registered sockets become ready. The OS will notify `select()` as it notifies blocking socket methods like `recv()`.

What should we do with a ready socket? We certainly had some idea of what do to with the socket when we registered it, so let's register every socket with a callback that should be called when the socket becomes ready. After all, that's what the auxially data parameter of the selector's `register()` method is for.

Now we're ready to implement a single-threaded concurrent server using I/O multiplexing:

```python
# echo_io_multiplexing.py

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

The event loop solution works fine. Its main disadvantage compared to the multi-threaded solutions is that you have to structure the code in a weird, callback-centered way. The code in our example doesn't look so bad, but this is in part because we do not handle all the things properly. For example, writing to a socket may block if the write queue is full, so we should also check whether the socket is ready for writing before calling `sendall()`. This means that the `recv_and_send()` function must be decomposed into two functions. The problem would be even more apparent if we were to implement something beyond the  primitive "echo" protocol.

OS threads do not impose callback style programming on us, yet they provide concurrency. How is that possible? The key here is the ability of the OS to suspend and resume thread execution. If we'd have functions that can be suspended and resumed like OS threads, we could write concurrent single-threaded code. And you know what? Pyhon allows us to write such functions. 

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

When you call a generator function, Python doesn't run the function's code as it does for ordinary functions but returns a **generator**:

```pycon
>>> g = gen()
>>> g
<generator object gen at 0x105655660>
```

To actually run the code, you pass the generator to the built-in [`next()`](https://docs.python.org/3/library/functions.html#next) function. It runs the generator to the first `yield` expression, at which point it suspends the execution and returns the argument of `yield`. Calling `next()` second time resumes the generator from the point where it was suspended and runs it to the next `yield`:

```pycon
>>> next(g)
1
>>> next(g)
2
```

When no more `yield` expressions are left, calling `next()` raises the `StopIteration` exception:

```pycon
>>> next(g)
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
StopIteration: 3
```

If the generator returns something, the exception will hold the returned value:

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



Initially generators were introduced to Python as an alternative way to write iterators. Instead of defining a class with the [`__iter__()`](https://docs.python.org/3/reference/datamodel.html#object.__iter__) and [`__next__()`](https://docs.python.org/3/library/stdtypes.html#iterator.__next__) special methods, you can now use the `yield` keyword to write a function that generates values. Python fills the special methods for you, so the function becomes the iterator automatically. You can get the generatated values by calling `next()` but you typically iterate over them in a `for` loop:

```pycon
>>> for i in gen():
...     i
... 
1
2
```

Generators produce values in a lazy, on-demand manner, so they are memory-efficient and can even be used to generate infinite sequences. [PEP 255](https://www.python.org/dev/peps/pep-0255/) describes this use case of generators in great detail. We, however, want to use generators for a completely different reason. What's important for us is not the values that a generator produces but the mere fact that it can be suspended and resumed.

## Generators as a means to concurrency

Take any program that performs multiple tasks. Turn functions that represent these tasks into generators by inserting few `yield` statements here and there. Then run the generators in a round-robin fashion: call `next()` on every generator in some fixed order and repeat this step until all generators are exhausted. You'll get a concurrent program that runs like this:

picture??

Let's apply this strategy to the sequential server to make it concurrent. First, we insert some `yield` statements. I suggest to insert them before every blocking operation. Then, we need to run generators. I suggest to write a class that maintains a queue of scheduled tasks (generators) and provides the `run()` method that runs the scheduled tasks in a loop in a round-robin fashion. We'll call this class `EventLoopNoIO` since it functions like an event loop except that it doesn't do I/O multiplexing. Here's the server code:

```python
from collections import deque
import socket

from event_loop_no_io import EventLoopNoIO


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


def handle_client(sock: socket.socket):
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

Another way to phrase this problem is to say that the event loop doesn't check whether socket methods will block, so we can fix it by adding I/O multiplexing. Instead of rescheduling a task immediately after running it, the event loop should reschedule the task only when the socket that the task is waiting on becomes available for reading (or writing). The task can register its intention to read from or write to a socket by calling some event loop method. Alternatively, it can just `yield` this information to the event loop. Here's a version of the server that takes the latter approach:

```python
from collections import deque
import socket

from event_loop_io import EventLoopIo


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


def handle_client(sock: socket.socket):
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

What do we get out of it? First, we get the server that works with multiple clients perfectly fine:

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

We'll find that using generators in this way has an issue if try to factor out some generator's code into a subgenerator. For example, it would be very handy to move these two lines:

```python
yield 'wait_read', sock
recieved_data = sock.recv(4096)
```

into a separate function:

```python
def async_recv(sock, bufsize=4096):
    yield 'wait_read', sock
    return sock.recv(bufsize)
```

and then call the function like this:

```python
recieved_data = async_recv(sock)
```

But it won't work. The `async_recv()` function returns a generator, not the data, so we have to run the generator by calling `next()`. We also have to reyield yielded values, handle the `StopIteration` exception and extract the result from it. Obviously, the amount of code that we have to write exceeds all the benefits of factoring out the code.

--

[PEP 255](https://www.python.org/dev/peps/pep-0255/) describes this initial use case of generators. [PEP 342](https://www.python.org/dev/peps/pep-0342/) introduced enhanced generators in Python 2.5, which enabled other uses cases as well. Generators got the `send()` method that works like `__next__()` but also sends a value to a generator that becomes the value of the suspended `yield` expression:

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

