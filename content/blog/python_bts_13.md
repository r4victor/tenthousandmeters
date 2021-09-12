Title: Python behind the scenes #13: the GIL and its effects on Python multithreading
Date: 2021-09-06 12:50
Tags: Python behind the scenes, Python, CPython

As you probably know, the GIL stands for the Global Interpreter Lock, and its job is to make the CPython interpreter thread-safe. The GIL allows only one OS thread to execute Python bytecode at any given time, and the consequence of this is that you cannot speed up CPU-intensive Python code by distributing the work among multiple threads. This is, however, not the only negative effect of the GIL. The GIL often makes multi-threaded programs slower compared to their single-threaded equivalents and, what is more surprising, can even affect the performance of I/O-bound threads.

In this post I'd like to tell you more about those non-obvious effects of the GIL. As we study them, we'll discuss what the GIL really is, why it exists, how it works, how it evolved, and how it's going to affect Python concurrency in the future.

**Note**: In this post I'm referring to CPython 3.9. Some implementation details will certainly change as CPython evolves. I'll try to keep track of important changes and add update notes.

## Python threads

How `python` starts; how the main thread enters the eval loop; what happens when a new Python thread starts

## The effects of the GIL

Experiments

## How the GIL works

The GIL state, mutexes, conditional variables

the ready queue, the queue of threads waiting on a CV

