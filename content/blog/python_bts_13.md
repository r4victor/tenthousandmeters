Title: Python behind the scenes #13: the GIL and its effects on Python multithreading
Date: 2021-09-22 8:55
Tags: Python behind the scenes, Python, CPython
Summary: As you probably know, the GIL stands for the Global Interpreter Lock, and its job is to make the CPython interpreter thread-safe. The GIL allows only one OS thread to execute Python bytecode at any given time, and the consequence of this is that it's not possible to speed up CPU-intensive Python code by distributing the work among multiple threads. This is, however, not the only negative effect of the GIL. The GIL introduces overhead that makes multi-threaded programs slower, and what is more surprising, it can even have an impact I/O-bound threads.<br><br>In this post I'd like to tell you more about non-obvious effects of the GIL. Along the way, we'll discuss what the GIL really is, why it exists, how it works, and how it's going to affect Python concurrency in the future.

As you probably know, the GIL stands for the Global Interpreter Lock, and its job is to make the CPython interpreter thread-safe. The GIL allows only one OS thread to execute Python bytecode at any given time, and the consequence of this is that it's not possible to speed up CPU-intensive Python code by distributing the work among multiple threads. This is, however, not the only negative effect of the GIL. The GIL introduces overhead that makes multi-threaded programs slower, and what is more surprising, it can even have an impact I/O-bound threads.

In this post I'd like to tell you more about non-obvious effects of the GIL. Along the way, we'll discuss what the GIL really is, why it exists, how it works, and how it's going to affect Python concurrency in the future.

**Note**: In this post I'm referring to CPython 3.9. Some implementation details will certainly change as CPython evolves. I'll try to keep track of important changes and add update notes.

## OS threads, Python threads and the GIL

Let me first remind you what Python threads are and how multithreading works in Python. When you run the `python` executable, the OS starts a new process with one thread of execution called the main thread. As in the case of any other C program, the main thread begins executing `python` by entering its `main()` function. All the main thread does next can be summarized by three steps:

1. [initialize the interpreter]({filename}/blog/python_bts_03.md);
2. [compile Python code to bytecode]({filename}/blog/python_bts_02.md);
3. [enter the evaluation loop to execute the bytecode]({filename}/blog/python_bts_04.md).

The main thread is a regular OS thread that executes compiled C code. Its state includes values of CPU registers and the call stack of C functions. A Python thread, however, must capture the call stack of Python functions, the exception state, and other Python-related things. So what CPython does is put those things in a [thread state struct](https://github.com/python/cpython/blob/5d28bb699a305135a220a97ac52e90d9344a3004/Include/cpython/pystate.h#L51) and associate the thread state with the OS thread. In other words, `Python thread = OS thread + Python thread state `.

The evaluation loop is an infinite loop that contains a giant switch over all possible bytecode instructions. To enter the loop, a thread must hold the GIL. The main thread takes the GIL during the initialization, so it's free to enter. When it enters the loop, it just starts executing bytecode instructions one by one according to the switch.

From time to time, a thread has to suspend bytecode execution. It checks if there are any reasons to do that at the beginning of each iteration of the evaluation loop. We're interested in one such reason: another thread has requested the GIL. Here's how this logic is implemented in the code:

```C
PyObject*
_PyEval_EvalFrameDefault(PyThreadState *tstate, PyFrameObject *f, int throwflag)
{
    // ... declaration of local variables and other boring stuff

  	// the evaluation loop
    for (;;) {

        // `eval_breaker` tells whether we should suspend bytecode execution
        // e.g. other thread requested the GIL
        if (_Py_atomic_load_relaxed(eval_breaker)) {

            // `eval_frame_handle_pending()` suspends bytecode execution
            // e.g. when another thread requests the GIL,
            // this function drops the GIL and waits for the GIL again
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

In a single-threaded Python program, the main thread is the only thread, and it never releases the GIL. Let's now see what happens in a multi-threaded program. We use the [`threading`](https://docs.python.org/3/library/threading.html) standard module to start a new Python thread:

```python
import threading

def f(a, b, c):
    # do something
    pass

t = threading.Thread(target=f, args=(1, 2), kwargs={'c': 3})
t.start()
```

The `start()` method of a `Thread` instance creates a new OS thread. On Unix-like systems including Linux and macOS, it calls the [pthread_create()](https://man7.org/linux/man-pages/man3/pthread_create.3.html) function for that purpose. The newly created thread starts executing the `t_bootstrap()` function with the `boot` argument. The [`boot`](https://github.com/python/cpython/blob/5d28bb699a305135a220a97ac52e90d9344a3004/Modules/_threadmodule.c#L1019) argument is a struct that contains the target function, the passed arguments, and a thread state for the new OS thread. The [`t_bootstrap()`](https://github.com/python/cpython/blob/5d28bb699a305135a220a97ac52e90d9344a3004/Modules/_threadmodule.c#L1029) function does a number of things, but most importantly, it acquires the GIL and then enters the evaluation loop to execute the bytecode of the target function.

To acquire the GIL, a thread first checks whether some other thread holds the GIL. If this is not the case, the thread acquires the GIL immediately. Otherwise, it waits until the GIL is released. It waits for a fixed time interval called the **switch interval** (5 ms by default), and if the GIL is not released during that time, it sets the `eval_breaker` and `gil_drop_request` flags. The `eval_breaker` flag tells the GIL-holding thread to suspend bytecode execution, and `gil_drop_request` explains why. The GIL-holding thread sees the flags when it starts the next iteration of the evaluation loop and releases the GIL. It notifies the GIL-awaiting threads, and one of them acquires the GIL. It's up to the OS to decide which thread to wake up, so it may or may not be the thread that set the flags.

That's the bare minimum of what we need to know about the GIL. Let me now demonstrate its effects that I was talking about earlier. If you find them interesting, proceed with the next sections in which we study the GIL in more detail.

## The effects of the GIL

The first effect of the GIL is well-known: multiple Python threads cannot run in parallel. Thus, a multi-threaded program is not faster than its single-threaded equivalent even on a multi-core machine. As an naive attempt to parallelize Python code, consider the following CPU-bound function that performs the decrement operation a given number of times:

```python
def countdown(n):
    while n > 0:
        n -= 1
```

Now suppose we want to perform 100,000,000 decrements. We may run `countdown(100_000_000)` in a single thread, or `countdown(50_000_000)` in two threads, or `countdown(25_000_000)` in four threads, and so forth. In the language without the GIL like C, we would see a speedup as we increase the number of threads. Running Python on my MacBook Pro with two cores and [hyper-threading](http://www.lighterra.com/papers/modernmicroprocessors/), I see the following:

| Number of threads | Decrements per thread (n) | Time in seconds (best of 3) |
| ----------------- | ------------------------- | --------------------------- |
| 1                 | 100,000,000               | 6.52                        |
| 2                 | 50,000,000                | 6.57                        |
| 4                 | 25,000,000                | 6.59                        |
| 8                 | 12,500,000                | 6.58                        |

The times don't change. In fact, multi-threaded programs may run slower because of the overhead associated with [context switching](https://en.wikipedia.org/wiki/Context_switch). The default switch interval is 5 ms, so context switches do not happens that often. But if we decrease the switch interval, we will see a slowdown. More on why we might need to do that later.

Although Python threads cannot help us speed up CPU-intensive code, they are useful when we want to perform multiple I/O-bound tasks simultaneously. Consider a server that listens for incoming connections and, when it receives a connection, runs a handler function in a separate thread. The handler function talks to the client by reading from and writing to the client's socket. When reading from the socket, the thread just hangs until the client sends something. This is where multithreading helps: another thread can run in the meantime.

To allow other threads run while the GIL-holding thread is waiting for I/O, CPython implements all I/O operations using the following pattern:

1. release the GIL;
2. perform the operation, e.g. [`write()`](https://man7.org/linux/man-pages/man2/write.2.html), [`recv()`](https://man7.org/linux/man-pages/man2/recv.2.html), [`accept()`](https://man7.org/linux/man-pages/man2/accept.2.html);
3. acquire the GIL.

Thus, a thread may release the GIL voluntarily before another thread sets `eval_breaker` and `gil_drop_request`. In general, a thread needs to hold the GIL only while it works with Python objects. So CPython applies the release-perform-acquire pattern not just to I/O operations but also to other blocking calls into the OS like [select()](https://man7.org/linux/man-pages/man2/select.2.html) and [pthread_mutex_lock()](https://linux.die.net/man/3/pthread_mutex_lock), and to heavy computations in pure C. For example, hash functions in the [`hashlib`](https://docs.python.org/3/library/hashlib.html) standard module release the GIL. This allows us to actually speed up Python code that calls such functions using multithreading.

Suppose we want to compute SHA-256 hashes of eight 128 MB messages. We may compute `hashlib.sha256(message)` for each message in a single thread, but we may also distribute the work among multiple threads. If I do the comparison on my machine, I get the following results:

| Number of threads | Total size of messages per thread | Time in seconds (best of 3) |
| ----------------- | --------------------------------- | --------------------------- |
| 1                 | 1 GB                              | 3.30                        |
| 2                 | 512 MB                            | 1.68                        |
| 4                 | 256 MB                            | 1.50                        |
| 8                 | 128 MB                            | 1.60                        |

Going from one thread to two threads is almost a 2x speedup because the threads run in parallel. Adding more threads doesn't help much because my machine has only two physical cores. The conclusion here is that it's possible to speed up CPU-intensive Python code using multithreading if the code calls C functions that release the GIL. Note that such functions can be found not only in the standard library but also in computational-heavy third-party modules like [NumPy](https://github.com/numpy/numpy). You can even write a [C extension that releases the GIL](https://docs.python.org/3/c-api/init.html?highlight=gil#releasing-the-gil-from-extension-code) yourself.

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

How many requests per second can this sever handle? I wrote a [simple client program](https://github.com/r4victor/pbts13_gil/blob/master/effect2_client.py) that just sends and receives 1-byte messages to the server as fast as it can and got something about 30k RPS. This is most probably not an accurate measure since the client and the server run on the same machine, but that's not the point. The point is to see how the RPS drops when the server performs some CPU-bound task in a separate thread.

Consider the exact same server but with an additional dummy thread that increments and decrements a variable in an infinite loop (any CPU-bound task will do just the same):

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

How do you expect the RPS to change? Slightly? 2x less? 10x less? No. The RPS drops to 100, which is 300x less! And this is very surprising if you are used to the way operating systems schedule threads. To see what I mean, let's run the server and the CPU-bound thread as separate processes so that they are not affected by the GIL. We can split the code into two different files or just use the [`multiprocessing`](https://docs.python.org/3/library/multiprocessing.html) standard module to spawn a new process like so:

```python
from multiprocessing import Process

# ... the same server code

if __name__ == '__main__':
    Process(target=compute).start()
    run_server()
```

And this yields about 20k RPS. Moreover, if we start two, three, or four CPU-bound processes, the RPS stays about the same. The OS scheduler prioritizes the I/O-bound thread, which is the right thing to do.

In the server example the I/O-bound thread waits for the socket to become ready for reading and writing, but the performance of any other I/O-bound thread would degrade just the same. Consider a UI thread that waits for user input. It would freeze regularly if you run it alongside a CPU-bound thread. Clearly, this is not how normal OS threads work, and the cause is the GIL. It interferes with the OS scheduler.

This problem is actually well-known among CPython developers. They refer to it as the **convoy effect.** David Beazley gave a [talk](https://www.youtube.com/watch?v=Obt-vMVdM8s) about it in 2010 and also opened a [related issue on bugs.python.org](https://bugs.python.org/issue7946). In 2021, 11 years laters, the issue was closed. However, it hasn't been fixed. In the rest of this post we'll try to figure out why.

## The convoy effect

The convoy effect takes place because each time the I/O-bound thread performs an I/O operation, it releases the GIL, and when it tries to reacquire the GIL after the operation, the GIL is likely to be already taken by the CPU-bound thread. So the I/O-bound thread must wait for at least 5 ms before it can set `eval_breaker` and `gil_drop_request` to force the CPU-bound thread release the GIL.

The OS can schedule the CPU-bound thread as soon as the I/O-bound thread releases the GIL. The I/O-bound thread can be scheduled only when the I/O operation completes, so it has less chances to take the GIL first. If the operation is really fast such as a non-blocking [`send()`](https://man7.org/linux/man-pages/man2/send.2.html), the chances are actually quite good but only on a single-core machine where the OS has to decide which thread to schedule.

On a multi-core machine, the OS doesn't have to decide which of the two threads to schedule. It can schedule both on different cores. The result is that the CPU-bound thread is almost guaranteed to acquire the GIL first, and each I/O operation in the I/O-bound thread costs extra 5 ms.

Note that a thread that is forced to release the GIL waits until another thread takes it, so the I/O-bound thread acquires the GIL after one switch interval. Without this logic, the convoy effect would be even more severe.

Now, how much is 5 ms? It depends on how much time the I/O operations take. If a thread waits for seconds until the data on a socket becomes available for reading, extra 5 ms do not matter much. But some I/O operations are really fast. For example, [`send()`](https://man7.org/linux/man-pages/man2/send.2.html) blocks only when the send buffer is full and returns immediately otherwise. So if the I/O operations take microseconds, then milliseconds of waiting for the GIL may have a huge impact.

The echo server without the CPU-bound thread handles 30k RPS, which means that a single request takes about 1/30k ≈ 30 µs. With the CPU-bound thread, `recv()` and `send()` add extra 5 ms = 5,000 µs to every request each, and a single request now takes 10,030 µs. This is about 300x more. Thus, the throughput is 300x less. The numbers match.

You may ask: Is the convoy effect a problem in real-world applications? I don't know. I never ran into it, nor could I find evidence that anyone else did. People do not complain, and this is part of the reason why the issue hasn't been fixed.

But what if the convoy effect does cause performance problems in your application? Here are two ways to fix it.

## Fixing the convoy effect

Since the problem is that the I/O-bound thread waits for the switch interval until it requests the GIL, we may try to set the switch interval to a smaller value. Python provides the [`sys.setswitchinterval(interval)`](https://docs.python.org/3/library/sys.html#sys.setswitchinterval) function for that purpose. The `interval` argument is a floating-point value representing seconds. The switch interval is measured in microseconds, so the smallest value is `0.000001`. Here's the RPS I get if I vary the switch interval and the number of CPU threads:

| Switch interval in seconds | RPS with no CPU threads | RPS with one CPU thread | RPS with two CPU threads | RPS with four CPU threads |
| -------------------------- | ----------------------- | ----------------------- | ------------------------ | ------------------------- |
| 0.1                        | 30,000                  | 5                       | 2                        | 0                         |
| 0.01                       | 30,000                  | 50                      | 30                       | 15                        |
| **0.005**                  | **30,000**              | **100**                 | **50**                   | **30**                    |
| 0.001                      | 30,000                  | 500                     | 280                      | 200                       |
| 0.0001                     | 30,000                  | 3,200                   | 1,700                    | 1000                      |
| 0.00001                    | 30,000                  | 11,000                  | 5,500                    | 2,800                     |
| 0.000001                   | 30,000                  | 10,000                  | 4,500                    | 2,500                     |

The results show several things: 

* The switch interval is irrelevant if the I/O-bound thread is the only thread.
* As we add one CPU-bound thread, the RPS drops significantly.
* As we double the number of CPU-bound threads, the RPS halves.
* As we decrease the switch interval, the RPS increases almost proportionally until the switch interval becomes too small. This is because the cost of context switching becomes significant.

Smaller switch intervals make I/O-bound threads more responsive. But too small switch intervals introduce a lot of overhead caused by a high number of context switches. Recall the `countdown()` function. We saw that we cannot speed it up with multiple threads. If we set the switch interval too small, then we'll also see a slowdown:

| Switch interval in seconds | **Time in seconds** (threads: 1) | **Time in seconds** (threads: 2) | **Time in seconds** (threads: 4) | **Time in seconds** (threads: 8) |
| -------------------------- | -------------------------------- | -------------------------------- | -------------------------------- | -------------------------------- |
| 0.1                        | 7.29                             | 6.80                             | 6.50                             | 6.61                             |
| 0.01                       | 6.62                             | 6.61                             | 7.15                             | 6.71                             |
| **0.005**                  | **6.53**                         | **6.58**                         | **7.20**                         | **7.19**                         |
| 0.001                      | 7.02                             | 7.36                             | 7.56                             | 7.12                             |
| 0.0001                     | 6.77                             | 9.20                             | 9.36                             | 9.84                             |
| 0.00001                    | 6.68                             | 12.29                            | 19.15                            | 30.53                            |
| 0.000001                   | 6.89                             | 17.16                            | 31.68                            | 86.44                            |

Again, the switch interval doesn't matter if there is only one thread. Also, the number of threads doesn't matter if the switch interval is large enough. A small switch interval and several threads is when you get poor performance.

The conclusion is that changing the switch interval is an option for fixing the convoy effect, but you should be careful to measure how the change affects your application.

The second way to fix the convoy effect is even more hacky. Since the problem is much less severe on single-core machines, we could try to restrict all Python threads to a single-core. This would force the OS to choose which thread to schedule, and the I/O-bound thread would have the priority.

Not every OS provides a way to restrict a group of threads to certain cores. As far as I understand, macOS provides only a [mechanism to give hints](https://developer.apple.com/library/archive/releasenotes/Performance/RN-AffinityAPI/) to the OS scheduler. The mechanism that we need is available on Linux. It's the [`pthread_setaffinity_np()`](https://man7.org/linux/man-pages/man3/pthread_setaffinity_np.3.html) function. It takes a thread and a mask of CPU cores and tells the OS to schedule the thread only on the cores specified by the mask.

`pthread_setaffinity_np()` is a C function. To call it from Python, you may use something like [`ctypes`](https://docs.python.org/3/library/ctypes.html). I didn't want to mess with `ctypes`, so I just modified the CPython source code. Then I compiled the executable, ran the echo server on a dual core Ubuntu machine and got the following results:

| Number of CPU-bound threads | 0    | 1    | 2    | 4    | 8    |
| :-------------------------- | ---- | ---- | ---- | ---- | ---- |
| RPS                         | 24k  | 12k  | 3k   | 30   | 10   |

The server can tolerate one CPU-bound thread quite well. But since the I/O-bound thread needs to compete with all CPU-bound threads for the GIL, as we add more threads, the performance drops massively. The fix is more of a hack. Why don't CPython developers just implement a proper GIL?

## A proper GIL

The fundamental problem with the GIL is that it interferes with the OS scheduler. Ideally, you would like to run an I/O-bound thread as soon the I/O operation it waits for completes. And that's what the OS scheduler usually does. In CPython, however, the thread then immediately gets stuck waiting for the GIL, so the OS scheduler's decision doesn't really mean anything. You may try to get rid of the switch interval so that a thread that wants the GIL gets it without delay, but then you have a problem with CPU-bound threads because they want the GIL all the time.

The proper solution is to differentiate between the threads. An I/O-bound thread should be able to take away the GIL from a CPU-bound thread without waiting, but threads with the same priority should wait for each other. The OS scheduler already differentiates between the threads, but you cannot rely on it because it knows nothing about the GIL. It seems that the only option is to implement the scheduling logic in the interpreter.

After David Beazley opened the [issue](https://bugs.python.org/issue7946), CPython developers made several attempts to solve it. Beazley himself proposed a [simple patch](http://dabeaz.blogspot.com/2010/02/revisiting-thread-priorities-and-new.html). In short, this patch allows an I/O-bound thread to preempt a CPU-bound thread. By default, all threads are considered I/O-bound. Once a thread is forced to release the GIL, it's flagged as CPU-bound. When a thread releases the GIL voluntarily, the flag is reset, and the thread is considered I/O-bound again.

Beazley's patch solved all the GIL problems that we've discussed today. Why hasn't it been merged? The consensus seems to be that any simple implementation of the GIL would fail in some pathological cases. At most, you might need to try a bit harder to find them. A proper solution has to do scheduling like an OS, or as Nir Aides put it:

> ... Python really needs a scheduler, not a lock.

So Aides implemented a full-fledged scheduler in [his patch](https://bugs.python.org/issue7946#msg101612). The patch worked, but a scheduler is never a trivial thing, so merging it to CPython required a lot of effort. Finally, the work was abandoned because at the time there wasn't enough evidence that the issue caused problems in production code. See [the discussion](https://bugs.python.org/issue7946) for more details.

The GIL never had a huge fanbase. What we've seen today only makes it worse. We come back to the all time question.

## Can't we remove the GIL?

The first step to remove the GIL is to understand why it exists. Think why you would typically use locks in a multi-threaded program, and you'll get the answer. It's to prevent race conditions and make certain operations atomic from the perspective of other threads. Say you have a sequence of statements that modifies some data structure. If you don't surround the sequence with a lock, then another thread can access the data structure somewhere in the middle of the modification and get a broken incomplete view.

Or say you increment the same variable from multiple threads. If the increment operation is not atomic and not protected by a lock, then the final value of the variable can be less than the the total number of increments. This is a typical data race:

1. Thread 1 reads the value `x`.
2. Thread 2 reads the value `x`.
3. Thread 1 writes back the value `x + 1`.
4. Thread 2 writes back the value `x + 1`, thus discarding the changes made by Thread 1.

In Python the `+=` operation is not atomic because it consists of multiple bytecode instructions. To see how it can lead to data races, set the switch interval to `0.000001` and run the following function in multiple threads:

```python
sum = 0

def f():
    global sum
    for _ in range(1000):
        sum += 1
```

Similarly, in C incrementing an integer like `x++` or `++x` is not atomic because the compiler translates such operations to a sequence of machine instructions. Threads can interleave in between.

The GIL is so helpful because CPython increments and decrements integers that can be shared between threads all over the place. This is CPython's way to do garbage collection. Every Python object has a reference count field. This field counts the number of places that reference the object: other Python objects, local and global C variables. One place more increments the reference count. One place less decrements it. When the reference count reaches zero, the object is deallocated. If not the GIL, some decrements could overwrite each other and the object would stay in memory forever. Worse still, overwritten increments could result in a deallocated object that has active references.

The GIL also simplifies the implementation of built-in mutable data structures. Lists, dicts and sets do not use locking internally, yet because of the GIL, they can be safely used in multi-threaded programs. Similarly, the GIL allows threads to safely access global and interpreter-wide data: loaded modules, preallocated objects, interned strings as so on.

Finally, the GIL simplifies the writing of C extensions. Developers can assume that only one thread runs their C extension at any given time. Thus, they don't need to use additional locking to make the code thread-safe. When they do want to run the code in parallel, they can release the GIL.

To sum up, what the GIL does is make the following thread-safe:

1. reference counting;

2. mutable data structures;

3. global and interpreter-wide data;

4. C extensions.

To remove the GIL and still have a working interpreter, you need to find alternative mechanisms for thread-safety. People tried to do that in the past. The most notable attempt was Larry Hastings' Gilectomy project started in 2016. Hastings [forked](https://github.com/larryhastings/gilectomy) CPython, [removed](https://github.com/larryhastings/gilectomy/commit/4a1a4ff49e34b9705608cad968f467af161dcf02) the GIL, modified reference counting to use [atomic](https://gcc.gnu.org/onlinedocs/gcc-4.1.1/gcc/Atomic-Builtins.html) increments and decrements, and put a lot of fine-grained locks to protect mutable data structures and interpreter-wide data.

Gilectomy could run some Python code and run it in parallel. However, the single-threaded performance of CPython was compromised. Atomic increments and decrements alone added about 30% overhead. Hastings tried to address this by implementing buffered reference counting. In short, this technique confines all reference count updates to one special thread. Other threads only commit the increments and decrements to the log, and the special thread reads the log. This worked, but the overhead was [still significant](https://mail.python.org/archives/list/python-dev@python.org/message/YJDRVOUSRVGCZTKIL7ZUJ6ITVWZTC246/).

In the end, it [became evident](https://lwn.net/Articles/754577/) that Gilectomy is not going to be merged into CPython. Hastings stopped working on the project. It wasn't a complete failure, though. It taught us why removing the GIL from CPython is hard. There are two main reasons:

1. Garbage collection based on reference counting is not suited for multithreading. The only solution is to implement a [tracing garbage collector](https://en.wikipedia.org/wiki/Tracing_garbage_collection) that JVM, CLR, Go, and other runtimes without a GIL implement.
2. Removing the GIL breaks existing C extensions. There is no way around it.

Nowadays nobody thinks seriously about removing the GIL. Does it mean that we are to live with the GIL forever?

## The future of the GIL and Python concurrency

This sounds scary, but it's much more probable that CPython will have many GILs than no GIL at all. Literally, there is an initiative to introduce multiple GILs to CPython. It's called subinterpreters. The idea is to have multiple interpreters within the same process. Threads within one interpreter still share the GIL, but multiple interpreters can run parallel. No GIL is needed to synchronize interpreters because they have no common global state and do not share Python objects. All global state is made per-interpreter, and interpreters communicate via message passing only. The ultimate goal is to introduce to Python a concurrency model based on communicating sequential processes found in languages like Go and Clojure.

Interpreters have been a part of CPython since version 1.5 but only as an isolation mechanism. They store data specific to a group of threads: loaded modules, builtins, import settings and so forth. They are not exposed in Python, but C extensions can use them via the Python/C API. A few actually do that, though, [`mod_wsgi`](https://modwsgi.readthedocs.io/en/develop/index.html) being a notable example.

Today's interpreters are limited by the fact that they have to share the GIL. This can change only when all the global state is made per-interpreter. The work is [being done](https://pythondev.readthedocs.io/subinterpreters.html) in that direction, but few things remain global: some built-in types, singletons like `None`, `True` and `False`, and parts of the memory allocator. C extensions also need to [get rid of the global state](https://www.python.org/dev/peps/pep-0630/) before they can work with subinterpreters.

Eric Snow wrote [PEP 554](https://www.python.org/dev/peps/pep-0554/) that adds the `interpreters` module to the standard library. The idea is to expose the existing interpreters C API to Python and provide mechanisms of communication between interpreters. The proposal targeted Python 3.9 but was postponed until the GIL is made per-interpreter. Even then it's not guaranteed to succeed. The matter of [debate](https://mail.python.org/archives/list/python-dev@python.org/thread/3HVRFWHDMWPNR367GXBILZ4JJAUQ2STZ/) is whether Python really needs another concurrency model.

Another exciting project that's going on nowadays is [Faster CPython](https://github.com/faster-cpython). In October 2020, Mark Shannon proposed a [plan](https://github.com/markshannon/faster-cpython) to make CPython ≈5x faster over several years. And it's actually much more realistic than it may sound because CPython has a lot of potential for optimization. The addition of JIT alone can result in an enormous performance boost.

There were similar projects before, but they failed because they lacked proper funding or expertise. This time, Microsoft [volunteered](https://lwn.net/Articles/857754/) to sponsor Faster CPython and let Mark Shannon, Guido van Rossum, and Eric Snow work on the project. The incremental changes already go to CPython – they do not stale in a fork.

Faster CPython focuses on single-threaded performance. The team has no plans to change or remove the GIL. Nevertheless, if the project succeeds, one of the Python's major pain points will be fixed, and the GIL question may become more relevant than ever.

## P.S.

The benchmarks used in this post are [available on GitHub](https://github.com/r4victor/pbts13_gil). Special thanks to David Beazley for [his amazing talks](https://dabeaz.com/talks.html). Larry Hastings' talks on the GIL and Gilectomy ([one](https://www.youtube.com/watch?v=KVKufdTphKs), [two](https://www.youtube.com/watch?v=P3AyI_u66Bw), [three](https://www.youtube.com/watch?v=pLqv11ScGsQ)) were also very interesting to watch. To understand how modern OS schedulers work, I've read Robert Love's book [*Linux Kernel Development*](https://www.amazon.com/Linux-Kernel-Development-Robert-Love/dp/0672329468). Highly recommend it!

If you want to study the GIL in more detail, you should read the source code. The [`Python/ceval_gil.h`](https://github.com/python/cpython/blob/3.9/Python/ceval_gil.h) file is a perfect place to start. To help you with this venture, I wrote the following bonus section.

## The implementation details of the GIL *

Technically, the GIL is a flag indicating whether the GIL is locked or not, a set of mutexes and conditional variables that control how this flag is set, and some other utility variables like the switch interval. All these things are stored in the `_gil_runtime_state` struct:

```C
struct _gil_runtime_state {
    /* microseconds (the Python API uses seconds, though) */
    unsigned long interval;
    /* Last PyThreadState holding / having held the GIL. This helps us
       know whether anyone else was scheduled after we dropped the GIL. */
    _Py_atomic_address last_holder;
    /* Whether the GIL is already taken (-1 if uninitialized). This is
       atomic because it can be read without any lock taken in ceval.c. */
    _Py_atomic_int locked;
    /* Number of GIL switches since the beginning. */
    unsigned long switch_number;
    /* This condition variable allows one or several threads to wait
       until the GIL is released. In addition, the mutex also protects
       the above variables. */
    PyCOND_T cond;
    PyMUTEX_T mutex;
#ifdef FORCE_SWITCHING
    /* This condition variable helps the GIL-releasing thread wait for
       a GIL-awaiting thread to be scheduled and take the GIL. */
    PyCOND_T switch_cond;
    PyMUTEX_T switch_mutex;
#endif
};
```

The `_gil_runtime_state` stuct is a part of the global state. It's stored in the `_ceval_runtime_state` struct, which in turn is a part of `_PyRuntimeState` that all Python threads have an access to:

```C
struct _ceval_runtime_state {
    _Py_atomic_int signals_pending;
    struct _gil_runtime_state gil;
};
```

```C
typedef struct pyruntimestate {
    // ...
    struct _ceval_runtime_state ceval;
    struct _gilstate_runtime_state gilstate;

    // ...
} _PyRuntimeState;
```

Note that `_gilstate_runtime_state` is a struct different from `_gil_runtime_state`. It stores information about the GIL-holding thread:

```C
struct _gilstate_runtime_state {
    /* bpo-26558: Flag to disable PyGILState_Check().
       If set to non-zero, PyGILState_Check() always return 1. */
    int check_enabled;
    /* Assuming the current thread holds the GIL, this is the
       PyThreadState for the current thread. */
    _Py_atomic_address tstate_current;
    /* The single PyInterpreterState used by this process'
       GILState implementation
    */
    /* TODO: Given interp_main, it may be possible to kill this ref */
    PyInterpreterState *autoInterpreterState;
    Py_tss_t autoTSSkey;
};
```

Finally, there is a `_ceval_state` struct, which is a part of `PyInterpreterState`. It stores the `eval_breaker` and `gil_drop_request` flags:

```C
struct _ceval_state {
    int recursion_limit;
    int tracing_possible;
    /* This single variable consolidates all requests to break out of
       the fast path in the eval loop. */
    _Py_atomic_int eval_breaker;
    /* Request for dropping the GIL */
    _Py_atomic_int gil_drop_request;
    struct _pending_calls pending;
};
```

The Python/C API provides the [`PyEval_RestoreThread()`](https://docs.python.org/3/c-api/init.html#c.PyEval_RestoreThread) and [`PyEval_SaveThread()`](https://docs.python.org/3/c-api/init.html#c.PyEval_SaveThread) functions to acquire and release the GIL. These function also take care of setting `gilstate->tstate_current`. Under the hood, all the job is done by the [`take_gil()`](https://github.com/python/cpython/blob/5d28bb699a305135a220a97ac52e90d9344a3004/Python/ceval_gil.h#L211) and [`drop_gil()`](https://github.com/python/cpython/blob/5d28bb699a305135a220a97ac52e90d9344a3004/Python/ceval_gil.h#L144) functions. They are called by the GIL-holding thread when it suspends bytecode execution:

```C
/* Handle signals, pending calls, GIL drop request
   and asynchronous exception */
static int
eval_frame_handle_pending(PyThreadState *tstate)
{
    _PyRuntimeState * const runtime = &_PyRuntime;
    struct _ceval_runtime_state *ceval = &runtime->ceval;

    /* Pending signals */
    // ...

    /* Pending calls */
    struct _ceval_state *ceval2 = &tstate->interp->ceval;
    // ...

    /* GIL drop request */
    if (_Py_atomic_load_relaxed(&ceval2->gil_drop_request)) {
        /* Give another thread a chance */
        if (_PyThreadState_Swap(&runtime->gilstate, NULL) != tstate) {
            Py_FatalError("tstate mix-up");
        }
        drop_gil(ceval, ceval2, tstate);

        /* Other threads may run now */

        take_gil(tstate);

        if (_PyThreadState_Swap(&runtime->gilstate, tstate) != NULL) {
            Py_FatalError("orphan tstate");
        }
    }

    /* Check for asynchronous exception. */
    // ...
}
```

On Unix-like systems the implementation of the GIL relies on primitives provided by the [pthreads](https://man7.org/linux/man-pages/man7/pthreads.7.html) library. These include mutexes and conditional variables. In short, they work as follows. A thread calls [`pthread_mutex_lock(mutex)`](https://linux.die.net/man/3/pthread_mutex_lock) to lock the mutex. When another thread does the same, it blocks. The OS puts it on the queue of threads that wait for the mutex and wakes it up when the first thread calls [`pthread_mutex_unlock(mutex)`](https://linux.die.net/man/3/pthread_mutex_unlock). Only one thread can run the protected code at a time.

Conditional variables allow one thread to wait until another thread makes some condition true. To wait on a conditional variable a thread locks a mutex and calls [`pthread_cond_wait(cond, mutex)`](https://linux.die.net/man/3/pthread_cond_wait) or [`pthread_cond_timedwait(cond, mutex, time)`](https://linux.die.net/man/3/pthread_cond_wait). These calls atomically unlock the mutex and make the thread block. The OS puts the thread on a waiting queue and wakes it up when another thread calls [`pthread_cond_signal()`](https://linux.die.net/man/3/pthread_cond_signal). The awakened thread locks the mutex again and proceeds. Here's how conditional variables are typically used:

```python
# awaiting thread

mutex.lock()
while not condition:
	cond_wait(cond_variable, mutex)
# ... condition is True, do something
mutex.unlock()
```

```python
# signaling thread

mutex.lock()
# ... do something and make condition True
cond_signal(cond_variable)
mutex.unlock()
```

Note that the awaiting thread should check the condition in a loop because it's [not guaranteed](https://stackoverflow.com/questions/7766057/why-do-you-need-a-while-loop-while-waiting-for-a-condition-variable) to be true after the notification. The mutex ensures that the awaiting thread doesn't miss the condition going from false to true.

The `take_gil()` and `drop_gil()` functions use the `gil->cond` conditional variable to notify GIL-awaiting threads that the GIL has been released and `gil->switch_cond` to notify the GIL-holding thread that other thread took the GIL. These conditional variables are protected by two mutexes: `gil->mutex` and `gil->switch_mutex`.

Here's the steps of [`take_gil()`](https://github.com/python/cpython/blob/5d28bb699a305135a220a97ac52e90d9344a3004/Python/ceval_gil.h#L211) :

1. Lock the GIL mutex: `pthread_mutex_lock(&gil->mutex)`.
2. See if `gil->locked`. If it's not, go to step 4.
3. Wait for the GIL. While `gil->locked`:
    1. Remember `gil->switch_number`.
    2. Wait for the GIL-holding thread to drop the GIL: `pthread_cond_timedwait(&gil->cond, &gil->mutex, switch_interval)`.
    3. If timed out, and `gil->locked`, and `gil->switch_number` didn't change, tell the GIL-holding thread to drop the GIL: set `ceval->gil_drop_request` and `ceval->eval_breaker`.
4. Take the GIL and notify the GIL-holding thread that we took it:
    1. Lock the switch mutex: `pthread_mutex_lock(&gil->switch_mutex)`.
    2. Set `gil->locked`.
    3. If we're not the `gil->last_holder` thread, update `gil->last_holder` and increment `gil->switch_number`.
    4. Notify the GIL-releasing thread that we took the GIL: `pthread_cond_signal(&gil->switch_cond)`.
    5. Unlock the switch mutex: `pthread_mutex_unlock(&gil->switch_mutex)`.
5. Reset `ceval->gil_drop_request`.
6. Recompute `ceval->eval_breaker`.
7. Unlock the GIL mutex: `pthread_mutex_unlock(&gil->mutex)`.

Note that while a thread waits for the GIL, another thread can took it, so it's necessary to check `gil->switch_number` to ensure that a thread that just took the GIL won't be forced to drop it.

Finally, here's the steps of [`drop_gil()`](https://github.com/python/cpython/blob/5d28bb699a305135a220a97ac52e90d9344a3004/Python/ceval_gil.h#L144) :

1. Lock the GIL mutex: `pthread_mutex_lock(&gil->mutex)`.
2. Reset `gil->locked`.
3. Notify the GIL-awaiting threads that we drop the GIL: `pthread_cond_signal(&gil->cond)`.
4. Unlock the GIL mutex: `pthread_mutex_unlock(&gil->mutex)`.
5. If `ceval->gil_drop_request`, wait for another thread to take the GIL:
    1. Lock the switch mutex: `pthread_mutex_lock(&gil->switch_mutex)`.
    2. If we're still `gil->last_holder`, wait: `pthread_cond_wait(&gil->switch_cond, &gil->switch_mutex)`.
    3. Unlock the switch mutex: `pthread_mutex_unlock(&gil->switch_mutex)`.

Note that the GIL-releasing thread doesn't need to wait for a condition in a loop. It calls `pthread_cond_wait(&gil->switch_cond, &gil->switch_mutex)` only to ensure that it doesn't reacquire the GIL immediately. If the switch occurred, this means that another thread took the GIL, and it's fine to compete for the GIL again.

<br>

*If you have any questions, comments or suggestions, feel free to contact me at victor@tenthousandmeters.com*
