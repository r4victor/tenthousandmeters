Title: Python behind the scenes #13: the GIL and its effects on Python multithreading
Date: 2021-09-06 12:50
Tags: Python behind the scenes, Python, CPython

As you probably know, the GIL stands for the Global Interpreter Lock, and its job is to make the CPython interpreter thread-safe. The GIL allows only one OS thread to execute Python bytecode at any given time, and the consequence of this is that you cannot speed up CPU-intensive Python code by distributing the work among multiple threads. This is, however, not the only negative effect of the GIL. The GIL can make a multi-threaded program slower compared to its single-threaded equivalent and, what is more surprising, can even affect the performance of I/O-bound threads.

In this post I'd like to tell you more about non-obvious effects of the GIL. As we study them, we'll discuss what the GIL really is, why it exists, how it works, how it evolved, and how it's going to affect Python concurrency in the future.

**Note**: In this post I'm referring to CPython 3.9. Some implementation details will certainly change as CPython evolves. I'll try to keep track of important changes and add update notes.

## OS threads, Python threads and the GIL

Let me first remind you what Python threads are and how multithreading works in Python. When you run the `python` executable, the OS starts a new process with one thread of execution called the main thread. As in the case of any other C program, the main thread begins the execution of `python` by entering its `main()` function. If we follow the source code, we'll see that all the main thread does next can be summarised by three steps:

1. [initialize the interpreter]({filename}/blog/python_bts_03.md);
2. [compile Python code to bytecode]({filename}/blog/python_bts_02.md);
3. [enter the evaluation loop to execute the bytecode]({filename}/blog/python_bts_04.md).

The main thread is a regular OS thread that executes compiled C code. Its state is represented by CPU registers and the call stack of C functions. A Python thread, however, must capture such things as the call stack of Python functions and the exception state. So what CPython does is put those things in a [thread state structure](https://github.com/python/cpython/blob/5d28bb699a305135a220a97ac52e90d9344a3004/Include/cpython/pystate.h#L51) and associate the thread state with the OS thread. In other words, `Python thread = OS thread + Python thread state `.

The evaluation loop is an infinite loop that contains a giant switch over all possible bytecode instructions. To enter the loop, a thread must hold the GIL. The main thread takes the GIL during the initialization, so it's free to enter. When it enters the loop, it just starts executing bytecode instructions one by one according to the switch.

From time to time, the thread has to suspend the bytecode execution. We're interested in one reason to do that: another thread has requested the GIL. To react to such requests, each iteration of the evaluation loop starts with the corresponding check. Here's the evaluation loop summarized:

```C
PyObject*
_PyEval_EvalFrameDefault(PyThreadState *tstate, PyFrameObject *f, int throwflag)
{
    // ... declaration of local variables and other boring stuff

  	// the evaluation loop
    for (;;) {

        // `eval_breaker` tells whether we should suspend the bytecode execution
        // e.g. other thread requested the GIL
        if (_Py_atomic_load_relaxed(eval_breaker)) {

            // `eval_frame_handle_pending()` suspends the bytecode execution
            // e.g. drops the GIL and lets other threads execute the bytecode
            if (eval_frame_handle_pending(tstate) != 0) {
                goto error;
            }
        }

        // get next bytecode instruction
        NEXTOPARG();
        
        switch (opcode) {
            case TARGET(NOP) {
                FAST_DISPATCH(); // next iteration
            }

            case TARGET(LOAD_FAST) {
                // ... code for loading local variable
                FAST_DISPATCH(); // next iteration
            }

            // ... 117 more cases for every possible opcode
        }

        // ... error handling
    }

    // ... termination
}
```

In a single-threaded Python program, the main thread is the only thread, and it never releases the GIL. Let's now see what happens when we have multiple Python threads. To start a new Python thread, we use the standard [`threading`](https://docs.python.org/3/library/threading.html) module, like so:

```python
import threading

def f(a, b, c):
    # do something
    pass

t = threading.Thread(target=f, args=(1, 2), kwargs={'c': 3})
t.start()
```

The `start()` method of a `Thread` instance creates a new OS thread. On Unix-like system including Linux and macOS, it calls the [pthread_create()](https://man7.org/linux/man-pages/man3/pthread_create.3.html) function for that purpose. The newly created thread starts executing the `t_bootstrap()` function with the `boot` argument. The `boot` argument is a struct that contains the target function, the passed arguments and a thread state for the new OS thread:

```C
struct bootstate {
    PyInterpreterState *interp;
    PyObject *func;
    PyObject *args;
    PyObject *keyw;
    PyThreadState *tstate;
    _PyRuntimeState *runtime;
};
```

The `t_bootstrap()` function does a number of things, but most importantly, it acquires the GIL and then enters the evaluation loop to execute the bytecode of the target function.

To acquire the GIL, a thread first checks whether some other thread holds the GIL. If this is not the case, the thread acquires the GIL immediately. Otherwise, it waits until the GIL is released. It waits for a fixed time interval (5 ms by default), and if the GIL is not released during that period, it sets the `gil_drop_request` flag. The GIL-holding thread sees this flag when it starts the next iteration of the evaluation loop and releases the GIL. One of the GIL-waiting threads acquires the GIL. It may or may not be the thread that set `gil_drop_request`.

That's the bare minimum of what we need to know about the GIL. Let me now demonstrate its effects that I was talking about earlier. If you find them interesting, proceed with the next sections in which we study the GIL in more detail.

## The effects of the GIL

The first effect of the GIL is well-known: multiple Python threads cannot run in parallel on a multi-core machine. Thus, a multi-threaded program is not faster than its single-threaded equivalent. Consider the following CPU-bound function that performs the decrement operation a given number of times:

```python
def countdown(n):
    while n > 0:
        n -= 1
```

Now suppose we want to perform 100,000,000 decrements. We may run `countdown(100_000_000)` in a single thread, or `countdown(50_000_000)` in two threads, or `countdown(25_000_000)` in four threads, and so forth. In the language without the GIL like C, we would see a speedup as the number of threads increases. Running Python on my MacBook Pro with 2 cores and [hyper-threading](https://en.wikipedia.org/wiki/Hyper-threading), I see the following:

| Number of threads | Operations per thread (n) | Time in seconds (best of 3) |
| ----------------- | ------------------------- | --------------------------- |
| 1                 | 100,000,000               | 6.52                        |
| 2                 | 50,000,000                | 6.57                        |
| 4                 | 25,000,000                | 6.59                        |
| 8                 | 12,500,000                | 6.58                        |

The times don't change. In fact, multi-threaded programs may run slower because of the overhead associated with context switching. We'll see this effect later.

Although Python threads cannot help us speed up CPU-intensive code, they are useful when we want to perform multiple I/O-bound tasks simultaneously. Consider a server that listens for incoming connections and, when it receives a connection, runs a handler function in a separate thread. The handler function talks to the client by reading from and writing to the client's socket. When reading from the socket, the thread just hangs until the client sends something. This is where multithreading helps us: another thread can run in the meantime.

To allow other threads run while the currently running thread is waiting for I/O, CPython implements all I/O operations using the following pattern:

1. release the GIL;
2. perform the operation, e.g. [`write()`](https://man7.org/linux/man-pages/man2/write.2.html), [`recv()`](https://man7.org/linux/man-pages/man2/recv.2.html) or [`select()`](https://man7.org/linux/man-pages/man2/select.2.html);
3. acquire the GIL.

Thus, threads sometimes release the GIL voluntarily before another thread sets `gil_drop_request`.

In general, a thread needs to hold the GIL only while it works with Python objects. So CPython releases the GIL when performing any significant computations in pure C or when calling into the OS, not just when doing I/O. For example, hash functions in the [`hashlib`](https://docs.python.org/3/library/hashlib.html) module release the GIL when computing hashes. This allows us to actually speed up Python code that calls such functions using multithreading.

Suppose we need to compute SHA-256 hashes of eight 128 MB messages. We may compute `hashlib.sha256(message).digest()` for each message in a single thread, but we may also distribute the work among multiple threads. If I do that on my machine, I get the following results:

| Number of threads | Message size per thread | Time in seconds (best of 3) |
| ----------------- | ----------------------- | --------------------------- |
| 1                 | 1 GB                    | 3.30                        |
| 2                 | 512 MB                  | 1.68                        |
| 4                 | 256 MB                  | 1.50                        |
| 8                 | 128 MB                  | 1.60                        |

Going from one thread to two threads is almost 2x speed-up because the threads run in parallel. Adding more threads doesn't help much because my machine has only 2 physical cores. The conclusion here is that it is possible to speed up CPU-intensive Python code using multithreading if that code calls C functions that release the GIL. And such functions can be found not only in the standard library but also in computational-heavy third-party modules like [NumPy](https://github.com/numpy/numpy). You can even write a C extension that releases the GIL yourself.

We've mentioned CPU-bound threads – threads that compute something most of the time, and I/O-bound threads – threads that wait for I/O most of the time. The most interesting effect of the GIL takes place when we mix the two. Consider a simple TCP echo server that listens for incoming connections and, when a client connects, spawns a new thread to handle the client:

```python
from threading import Thread
import socket


def run_server(host='127.0.0.1', port=33333):
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen()
    while True:
        client_sock, addr = sock.accept()
        print('Connection from', addr)
        Thread(target=handle_client, args=(client_sock,)).start()


def handle_client(sock):
    while True:
        received_data = sock.recv(4096)
        if not received_data:
            break
        sock.sendall(received_data)

    print('Client disconnected:', sock.getpeername())
    sock.close()


if __name__ == '__main__':
    run_server()
```

How many requests per second can this sever handle? I wrote a simple client program that just sends and receives 1-byte message to the server as fast as it can and got something about 30k RPS. This is most probably not an accurate measure since the client and the server run on the same machine, but that's not the point. The point is to see how the RPS drops if the server performs some CPU-bound task in a separate thread.

Consider the exact same server but with an additional dummy thread that increments and decrements the same variable in an infinite loop (any CPU-bound task will do just the same):

```python
# ... the same server code

def compute():
    n = 0
    while True:
        n += 1
        n -= 1

if __name__ == '__main__':
    Thread(target=compute).start()
    run_server()
```

How do you expect the RPS to change? Slightly? 2x less? 10x less? No. The RPS drops to 100, which is 300x less! And this is very surprising if you are used to the way operating systems schedule threads. To see what I mean, let's run the server and the CPU-bound thread as separate processes so that they are not affected by the GIL. We can move the code to different files or just use the [`multiprocessing`](https://docs.python.org/3/library/multiprocessing.html) standard module to spawn a new process like so:

```python
from multiprocessing import Process

# ... the same server code

if __name__ == '__main__':
    Process(target=compute).start()
    run_server()
```

And this yields about 20k RPS. Moreover, if we start two, three, or four CPU-bound processes, the RPS stays about the same. The OS scheduler prioritizes the I/O thread, which is the right thing to do.

In the server example the I/O thread waits for the socket to become ready for reading and writing, but the performance of any other I/O thread would degrade just the same. Consider a UI thread that waits for user input. It would freeze regularly if you run it alongside a CPU-bound thread. Clearly, this is not how normal OS threads work, and the cause is the GIL. It somehow interferes with the OS scheduler.

This problem is actually well-known among CPython developers. David Beazley gave a [talk](https://www.youtube.com/watch?v=Obt-vMVdM8s) about it in 2010 and also opened a [related issue on bugs.python.org](https://bugs.python.org/issue7946). The issue was closed this year, but it was never fixed. In the rest of this post we'll try to figure out why. Let's begin with a high-level explanation of the problem.

The problem takes place because each time the I/O-bound thread performs an I/O operation, it releases the GIL, and when it tries to require the GIL after the operation, the CPU-bound thread already holds it. So the I/O-bound thread must wait for at least 5 ms before it can set `gil_drop_request` and force the CPU-bound thread to release the GIL. On single-core machines, the problem doesn't exist because it is the OS that decides whether to schedule the I/O-bound or the CPU-bound thread. And the OS does the scheduling well. On a multi-core machine, the OS doesn't have to decide which thread to schedule. It can schedule both on different cores. The result is that the CPU-bound thread happens to acquire the GIL first most of the time, and each I/O operation in the I/O-bound thread costs at least 5 ms more.

## Deconstructing the GIL

The GIL state, mutexes, conditional variables

the ready queue, the queue of threads waiting on a CV

