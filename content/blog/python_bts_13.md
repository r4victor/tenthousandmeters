Title: Python behind the scenes #13: the GIL and its effects on Python multithreading
Date: 2021-09-06 12:50
Tags: Python behind the scenes, Python, CPython

As you probably know, the GIL stands for the Global Interpreter Lock, and its job is to make the CPython interpreter thread-safe. The GIL allows only one OS thread to execute Python bytecode at any given time, and the consequence of this is that it is not possible to speed up CPU-intensive Python code by distributing the work among multiple threads. This is, however, not the only negative effect of the GIL. The GIL can make multi-threaded programs slower compared to their single-threaded equivalents and, what is more surprising, can even affect the performance of I/O-bound threads.

In this post I'd like to tell you more about non-obvious effects of the GIL. As we study them, we'll discuss what the GIL really is, why it exists, how it works, how it evolved, and how it's going to affect Python concurrency in the future.

**Note**: In this post I'm referring to CPython 3.9. Some implementation details will certainly change as CPython evolves. I'll try to keep track of important changes and add update notes.

## OS threads, Python threads and the GIL

Let me first remind you what Python threads are and how multithreading works in Python. When you run the `python` executable, the OS starts a new process with one thread of execution called the main thread. As in the case of any other C program, the main thread begins the execution of `python` by entering its `main()` function. If we follow the source code, we'll see that all the main thread does next can be summarised by three steps:

1. [initialize the interpreter]({filename}/blog/python_bts_03.md);
2. [compile Python code to bytecode]({filename}/blog/python_bts_02.md);
3. [enter the evaluation loop to execute the bytecode]({filename}/blog/python_bts_04.md).

The main thread is a regular OS thread that executes compiled C code. Its state is represented by CPU registers and the call stack of C functions. A Python thread, however, must capture such things as the call stack of Python functions and the exception state. So what CPython does is put those things in a [thread state structure](https://github.com/python/cpython/blob/5d28bb699a305135a220a97ac52e90d9344a3004/Include/cpython/pystate.h#L51) and associate the thread state with the OS thread. In other words, `Python thread = OS thread + Python thread state `.

The evaluation loop is an infinite loop that contains a giant switch over all possible bytecode instructions. To enter the loop, a thread must hold the GIL. The main thread takes the GIL during the initialization, so it's free to enter. When it enters the loop, it just starts executing bytecode instructions one by one according to the switch.

From time to time, the thread has to suspend the bytecode execution. We're interested in one reason to do that: another thread has requested the GIL. To react to such requests, each iteration of the evaluation loop starts with the corresponding check. Here's how this implemented in the code:

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

In a single-threaded Python program, the main thread is the only thread, and it never releases the GIL. Let's now see what happens in a multi-threaded program. To start a new Python thread, we use the [`threading`](https://docs.python.org/3/library/threading.html) standard module:

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

To acquire the GIL, a thread first checks whether some other thread holds the GIL. If this is not the case, the thread acquires the GIL immediately. Otherwise, it waits until the GIL is released. It waits for a fixed time interval called the **switch interval** (5 ms by default), and if the GIL is not released during that interval, it sets the `eval_breaker` and `gil_drop_request` flags. The `eval_breaker` flag tells the GIL-holding thread to suspend bytecode execution, and `gil_drop_request` tells why. The GIL-holding thread sees the flags when it starts the next iteration of the evaluation loop and releases the GIL. It notifies the GIL-awaiting threads, and one of them acquires the GIL. It may or may not be the thread that set the flags.

That's the bare minimum of what we need to know about the GIL. Let me now demonstrate its effects that I was talking about earlier. If you find them interesting, proceed with the next sections in which we study the GIL in more detail.

## The effects of the GIL

The first effect of the GIL is well-known: multiple Python threads cannot run in parallel on a multi-core machine. Thus, a multi-threaded program is not faster than its single-threaded equivalent. Consider the following CPU-bound function that performs the decrement operation a given number of times:

```python
def countdown(n):
    while n > 0:
        n -= 1
```

Now suppose we want to perform 100,000,000 decrements. We may run `countdown(100_000_000)` in a single thread, or `countdown(50_000_000)` in two threads, or `countdown(25_000_000)` in four threads, and so forth. In the language without the GIL like C, we would see a speedup as the number of threads increases. Running Python on my MacBook Pro with 2 cores and [hyper-threading](http://www.lighterra.com/papers/modernmicroprocessors/), I see the following:

| Number of threads | Operations per thread (n) | Time in seconds (best of 3) |
| ----------------- | ------------------------- | --------------------------- |
| 1                 | 100,000,000               | 6.52                        |
| 2                 | 50,000,000                | 6.57                        |
| 4                 | 25,000,000                | 6.59                        |
| 8                 | 12,500,000                | 6.58                        |

The times don't change. In fact, multi-threaded programs may run slower because of the overhead associated with [context switching](https://en.wikipedia.org/wiki/Context_switch). The default switch interval is 5 ms, so context switches do not happens that often. We'll see a substantial slowdown if we decrease the switch interval with [`sys.setswitchinterval()`](https://docs.python.org/3/library/sys.html#sys.setswitchinterval). More on this later.

Although Python threads cannot help us speed up CPU-intensive code, they are useful when we want to perform multiple I/O-bound tasks simultaneously. Consider a server that listens for incoming connections and, when it receives a connection, runs a handler function in a separate thread. The handler function talks to the client by reading from and writing to the client's socket. When reading from the socket, the thread just hangs until the client sends something. This is where multithreading helps: another thread can run in the meantime.

To allow other threads run while the currently running thread is waiting for I/O, CPython implements all I/O operations using the following pattern:

1. release the GIL;
2. perform the operation, e.g. [`write()`](https://man7.org/linux/man-pages/man2/write.2.html), [`recv()`](https://man7.org/linux/man-pages/man2/recv.2.html) or [`select()`](https://man7.org/linux/man-pages/man2/select.2.html);
3. acquire the GIL.

Thus, threads sometimes release the GIL voluntarily before another thread sets `eval_breaker` and `gil_drop_request`.

In general, a thread needs to hold the GIL only while it works with Python objects. So CPython releases the GIL when performing any significant computations in pure C or when calling into the OS, not just when doing I/O. For example, hash functions in the [`hashlib`](https://docs.python.org/3/library/hashlib.html) standard module release the GIL when computing hashes. This allows us to actually speed up Python code that calls such functions using multithreading.

Suppose we want to compute SHA-256 hashes of eight 128 MB messages. We may compute `hashlib.sha256(message).digest()` for each message in a single thread, but we may also distribute the work among multiple threads. If I do the comparison on my machine, I get the following results:

| Number of threads | Message size per thread | Time in seconds (best of 3) |
| ----------------- | ----------------------- | --------------------------- |
| 1                 | 1 GB                    | 3.30                        |
| 2                 | 512 MB                  | 1.68                        |
| 4                 | 256 MB                  | 1.50                        |
| 8                 | 128 MB                  | 1.60                        |

Going from one thread to two threads is almost 2x speed-up because the threads run in parallel. Adding more threads doesn't help much because my machine has only 2 physical cores. The conclusion here is that it is possible to speed up CPU-intensive Python code using multithreading if that code calls C functions that release the GIL. And such functions can be found not only in the standard library but also in computational-heavy third-party modules like [NumPy](https://github.com/numpy/numpy). You can even write a [C extension that releases the GIL](https://docs.python.org/3/c-api/init.html?highlight=gil#releasing-the-gil-from-extension-code) yourself.

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

How many requests per second can this sever handle? I wrote a simple client program that just sends and receives 1-byte message to the server as fast as it can and got something about 30k RPS. This is most probably not an accurate measure since the client and the server run on the same machine, but that's not the point. The point is to see how the RPS drops when the server performs some CPU-bound task in a separate thread.

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

And this yields about 20k RPS. Moreover, if we start two, three, or four CPU-bound processes, the RPS stays about the same. The OS scheduler prioritizes the I/O thread, which is the right thing to do.

In the server example the I/O thread waits for the socket to become ready for reading and writing, but the performance of any other I/O thread would degrade just the same. Consider a UI thread that waits for user input. It would freeze regularly if you run it alongside a CPU-bound thread. Clearly, this is not how normal OS threads work, and the cause is the GIL. It interferes with the OS scheduler.

This problem is actually well-known among CPython developers. They refer to it as the **convoy effect.** David Beazley gave a [talk](https://www.youtube.com/watch?v=Obt-vMVdM8s) about it in 2010 and also opened a [related issue on bugs.python.org](https://bugs.python.org/issue7946). In 2021, 11 years laters, the issue was closed. However, it hasn't been fixed. In the rest of this post we'll try to figure out why.

## The convoy effect

The convoy effect takes place because each time the I/O-bound thread performs an I/O operation, it releases the GIL, and when it tries to reacquire the GIL after the operation, the GIL is likely to be already taken by the CPU-bound thread. So the I/O-bound thread must wait for at least 5 ms before it can set `eval_breaker` and `gil_drop_request` to force the CPU-bound thread to release the GIL.

The OS can schedule the CPU-bound thread as soon as the I/O-bound thread releases the GIL. The I/O-bound thread can be scheduled only when the I/O operation completes, so it has less chances to take the GIL first. If the operation is really fast such as a non-blocking `send()`, the chances are actually quite good but only on a single-core machine where the OS has to decide which thread to schedule. Because the OS prioritizes I/O-bound threads, the fact of choice mitigates the convoy effect.

On a multi-core machine, the OS doesn't have to decide which thread to schedule. It can schedule both on different cores. The result is that the CPU-bound thread is almost guaranteed to acquire the GIL first, and each I/O operation in the I/O-bound thread costs extra 5 ms.

Note that a thread that is forced to release the GIL waits until another thread takes it, so the I/O-bound acquires the GIL after one switch interval. Without this logic, the convoy effect would be even more severe.

Now, how much is 5 ms? It depends on how much the I/O operations take. If the thread waits for seconds until the data on the socket becomes available for reading, extra 5 ms do not matter much. But some I/O operations are really fast. For example, [`send()`](https://man7.org/linux/man-pages/man2/send.2.html) blocks only when the send buffer is full and returns immediately otherwise. So if the I/O operations take microseconds, then milliseconds of waiting for the GIL may have a huge effect.

In our example, the server without the CPU-bound thread handles 30k RPS, which means that a single request takes about 1/30k ≈ 30 µs. With the CPU-bound thread, `recv()` and `send()` add extra 5 ms = 5,000 µs to every request each, and a single request now takes 10,030 µs. This is about 300x more. Thus, the performance is 300x less. The numbers match.

You may ask: Is the convoy effect a problem in real-world applications? I don't know. It never was a problem for me, nor could I find evidence that anyone else ran into it. People do not complain, and this is part of the reason why the issue hasn't been fixed.

But what if the convoy effect does cause performance problems in your application? There are two ways you can fix it.

## Fixing the convoy effect

Since the problem is that the I/O-bound thread waits for the switch interval until it requests the GIL, we may try to set the switch interval to a smaller value. Python provides the [`sys.setswitchinterval(interval)`](https://docs.python.org/3/library/sys.html#sys.setswitchinterval) function for that purpose. The `interval` argument is a floating-point value representing seconds. The switch interval is measured in microseconds, so the smallest value is `0.000001`. Here's the RPS I get if I vary the switch interval and the number of CPU threads:

| Switch interval in seconds | RPS with no CPU threads | RPS with one CPU threads | RPS with two CPU threads | RPS with four CPU threads |
| -------------------------- | ----------------------- | ------------------------ | ------------------------ | ------------------------- |
| 0.1                        | 30,000                  | 5                        | 2                        | 0                         |
| 0.01                       | 30,000                  | 50                       | 30                       | 15                        |
| **0.005**                  | **30,000**              | **100**                  | **50**                   | **30**                    |
| 0.001                      | 30,000                  | 500                      | 280                      | 200                       |
| 0.0001                     | 30,000                  | 3,200                    | 1,700                    | 1000                      |
| 0.00001                    | 30,000                  | 11,000                   | 5,500                    | 2,800                     |
| 0.000001                   | 30,000                  | 10,000                   | 4,500                    | 2,500                     |

The results show several things: 

* The switch interval is irrelevant if the I/O-bound thread is the only thread.
* As we add one CPU-bound thread, the RPS drops significantly.
* As we double the number of CPU-bound threads, the RPS halves.
* As we decrease the switch interval, the RPS increases almost proportionally until the switch interval becomes too small. This is because the cost of context switching becomes significant.

Smaller switch intervals make I/O-bound threads more responsive. But too small switch intervals introduce a lot of overhead caused by a high number of context switches. Recall the `countdown()` function. We saw that we cannot speed it up with multiple threads. If we set the switch interval too small, then we'll also see a slowdown:

| Switch interval in seconds | Elapsed time (one thread) | Elapsed time (two threads) | Elapsed time (four threads) | Elapsed time (eight threads) |
| -------------------------- | ------------------------- | -------------------------- | --------------------------- | ---------------------------- |
| 0.1                        | 7.29                      | 6.80                       | 6.50                        | 6.61                         |
| 0.01                       | 6.62                      | 6.61                       | 7.15                        | 6.71                         |
| **0.005**                  | **6.53**                  | **6.58**                   | **7.20**                    | **7.19**                     |
| 0.001                      | 7.02                      | 7.36                       | 7.56                        | 7.12                         |
| 0.0001                     | 6.77                      | 9.20                       | 9.36                        | 9.84                         |
| 0.00001                    | 6.68                      | 12.29                      | 19.15                       | 30.53                        |
| 0.000001                   | 6.89                      | 17.16                      | 31.68                       | 86.44                        |

Again, the switch interval doesn't matter if there is only one thread. Also, the number of threads doesn't matter if the switch interval is large enough. A small switch interval and several threads is when you get poor performance.

The conclusion is that changing the switch interval is an option, but you should be careful to measure how it affects your application.

There is another way to fix the convoy effect that I came up with. Since the problem is much less severe on single-core machines, we could try to restrict all Python threads to a single-core. This would force the OS to choose which thread to schedule, and the I/O-bound thread would have the priority.

Not every OS provides a way to restrict a group of threads to certain cores. As far as I understand, macOS provides only a [mechanism](https://developer.apple.com/library/archive/releasenotes/Performance/RN-AffinityAPI/) to give hints to the OS scheduler. The mechanism that we need is available on Linux. It's the [`pthread_setaffinity_np()`](https://man7.org/linux/man-pages/man3/pthread_setaffinity_np.3.html) function. You pass a thread and a mask of CPU cores to `pthread_setaffinity_np()`, and the OS schedules the thread only on the cores specified by the mask.

`pthread_setaffinity_np()` is a C function. To call it from Python, you may use something like [`ctypes`](https://docs.python.org/3/library/ctypes.html). I didn't want to mess with `ctypes`, so I just modified the CPython source code. Then I compiled the executable, ran the echo server on a dual core Ubuntu machine and got the following results:

| Number of CPU-bound threads | 0    | 1    | 2    | 4    | 8    |
| :-------------------------- | ---- | ---- | ---- | ---- | ---- |
| RPS                         | 24k  | 12k  | 3k   | 30   | 10   |

The server can tolerate one CPU-bound thread quite well. But since the I/O-bound thread needs to compete with other threads for the GIL, as we add more threads, the performance drops massively. The fix is more of a hack. Why don't CPython developers just implement a proper GIL?

## A proper GIL

The fundamental problem with the GIL is that it interferes with the OS scheduler. Ideally, you would like to run an I/O-bound thread as soon the I/O operation it waits for completes. And that's what the OS scheduler does. But then the thread gets stuck immediately waiting for the GIL, so the OS scheduler's decision doesn't really mean anything. You may try to get rid of the switch interval so that a thread that wants the GIL gets it immediately. But then you have a problem with CPU-bound threads because they want the GIL all the time.

The proper solution is to differentiate between the threads. An I/O-bound thread should be able to take away the GIL from a CPU-bound thread without waiting, but threads with the same priority should wait for each other. The OS scheduler already differentiates between the threads, but you cannot rely on it because it knows nothing about the GIL. It seems that the only option is to implement the scheduling logic in the interpreter.

After David Beazley opened the [issue](https://bugs.python.org/issue7946), CPython developers made several attempts to solve it. Beazley himself proposed a [simple patch](http://dabeaz.blogspot.com/2010/02/revisiting-thread-priorities-and-new.html). In short, this patch allows an I/O-bound thread to preempt a CPU-bound thread. By default, all threads are considered I/O-bound. Once a thread is forced to release the GIL, it's flagged as CPU-bound. When a thread releases the GIL voluntarily, the flag is reset, and the thread is considered I/O-bound again.

Beazley's patch solved all the GIL problems that we've discussed today. Why hasn't it been merged? The consensus seems to be that any simple implementation of the GIL would fail in some pathological cases. At most, you might need to try a bit harder to find them. A proper solution has to do scheduling like an OS, or as Nir Aides put it:

> ... Python really needs a scheduler, not a lock.

So Aides implemented a full-fledged scheduler in [his patch](https://bugs.python.org/issue7946#msg101612). The patch worked, but a scheduler is never a trivial thing, so merging it to CPython required a lot of effort. Finally, the work was abandoned because at the time there wasn't enough evidence that the issue caused problems in production code. See [the discussion](https://bugs.python.org/issue7946) for more details.

The GIL never had a huge fanbase. The effects we saw today only make it worse and raise the all time question again.

## Can't we remove the GIL?

The first step to remove the GIL is to understand why it exists. Think why you would typically use locks in a multi-threaded program, and you'll get the answer. It's to prevent race conditions and make certain operations atomic from the perspective of other threads. Say you have a sequence of statements that modifies some data structure. If you don't surround it with a lock, then another thread can access the data structure somewhere in the middle of the modification and get a broken incomplete view.

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
    for _ in range(100):
        sum += 1
```

Similarly, in C incrementing an integer like `x++` or `++x` is not atomic because the compiler translates such operations to a sequence of machine instructions. Threads can interleave in between.



## How operating systems schedule threads

the ready queue, the queue of threads waiting on a CV

## Deconstructing the GIL

Steps to take the GIL:

1. Lock the GIL mutex: `pthread_mutex_lock(&gil->mutex)`.
2. See if `gil->locked`. If it's not, go to step 4.
3. Wait for the GIL. While `gil->locked`:
    1. Remember `gil->switch_number`.
    2. Wait for the GIL-holding thread to drop the GIL: `pthread_cond_timedwait(&gil->cond, &gil->mutex, switch_interval)`.
    3. If timed out, and `gil->locked`, and `gil->switch_number` didn't change, tell the GIL-holding thread to drop the GIL: set `ceval->gil_drop_request` and `ceval->eval_breaker`.
4. Take the GIL and notify the GIL-holding thread that we took it:
    1. Lock the switch mutex: `pthread_mutex_lock(&gil->switch_mutex)`.
    2. Set `gil->locked`.
    3. If the thread is not `gil->last_holder`, update `gil->last_holder` and increment `gil->switch_number`.
    4. Notify the GIL-holding thread that we took the GIL: `pthread_cond_signal(&gil->switch_cond)`.
    5. Unlock the switch mutex: `pthread_mutex_unlock(&gil->switch_mutex)`.
5. Reset `ceval->gil_drop_request`.
6. Recompute `ceval->eval_breaker`.
7. Unlock the GIL mutex: `pthread_mutex_unlock(&gil->mutex)`.

Steps to drop the GIL:

1. Lock the GIL mutex: `pthread_mutex_lock(&gil->mutex)`.
2. Reset `gil->locked`.
3. Notify the GIL-awaiting threads that we drop the GIL: `pthread_cond_signal(&gil->cond)`.
4. Unlock the GIL mutex: `pthread_mutex_unlock(&gil->mutex)`.
5. If `ceval->gil_drop_request`, wait for the other thread to take the GIL:
    1. Lock the switch mutex: `pthread_mutex_lock(&gil->switch_mutex)`.
    2. If the thread is still `gil->last_holder`, wait: `pthread_cond_wait(&gil->switch_cond, &gil->switch_mutex)`.
    3. Unlock the switch mutex: `pthread_mutex_unlock(&gil->switch_mutex)`.

