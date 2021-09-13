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

Now suppose we want to perform 100,000,000 decrements. We may run `countdown(100_000_000)` in a single thread, or `countdown(50_000_000)` in two threads, or `countdown(25_000_000)` in four threads, and so forth. In the language without the GIL like C, we would see a speedup as the number of threads increases. Running Python on my MacBook Pro with 4 cores, I see the following:

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
2. perform the operation, e.g. [`recv()`](https://man7.org/linux/man-pages/man2/recv.2.html) or [`select()`](https://man7.org/linux/man-pages/man2/select.2.html);
3. acquire the GIL.

Thus, threads sometimes release the GIL voluntarily before another thread sets `gil_drop_request`. 

In general, 



## How the GIL works

The GIL state, mutexes, conditional variables

the ready queue, the queue of threads waiting on a CV

