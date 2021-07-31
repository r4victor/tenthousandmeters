Title: Python behind the scenes #12: how async/await works in Python
Date: 2021-07-29 7:00
Tags: Python behind the scenes, Python, CPython

Mark functions as `async`. Call them with `await`. All of a sudden, your program becomes asynchronous – it can do useful things while it waits for other things, such as I/O operations, to complete.

Code written in the `async`/`await` style looks like regular synchronous code but works very differently. To understand how it works, one should be familiar with many non-trivial concepts including concurrency, parallelism, event loops, I/O multiplexing, asynchrony, cooperative multitasking and coroutines. Python's implementation of `async`/`await` adds even more concepts to this list: generators, generator-based coroutines, native coroutines, `yield` and `yield from`. Because of this complexity, some Python programmers prefer not to use `async`/`await` at all, while many others use it but do not realize how it actually works. I believe that neither should be the case. The `async`/`await` pattern can be explained in a simple manner if you start from the ground up, and that's what this post aims to do.

## It's all about concurrency 

Computers execute programs sequentially – one instruction after another. But a typical program performs multiple tasks, and it doesn't always make sense to wait for some task to complete before starting the next one. For example, a chess program that waits for a player to make a move should be able to update the clock in the meantime. Such an ability of a program to deal with multiple things simultaneously is what we call **concurrency**. Concurrency doesn't mean that multiple tasks must run at the same physical time. They can run in an interleaving manner: a task runs for some time, then suspends and lets other tasks to run, hoping it will get more time in the future. For this reason, a modern OS can run thousands of processes on a machine that has only a few cores. If multiple tasks do run at the same physical time, as in the case of a multi-core machine or a cluster, then we have **parallelism**, a special case of concurrency.

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

If the tasks are independent, then you can decompose each function into several functions and call the decomposed functions in an interleaving manner to get concurrency:

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

Of course, this is an oversimplified example. The point here is that the language doesn't determine whether you can write concurrent programs or not but may provide features that make concurrent programming more convenient, and `async`/`await` is just such a feature.

To see how one goes from concurrency to  `async`/`await`, we'll write a real-world concurrent program – a TCP echo server that supposed to handle multiple clients simultaneously. We'll start with the simplest, sequential version of the server that is not concurrent. Then, we'll make it concurrent using OS threads. After that, we'll see how we can write the concurrent version that runs in a single thread using I/O multiplexing. From this point onwards, we'll develop this approach by introducing event loops, callbacks, generators, coroutines and, finally, `async`/`await`.

## A sequential server

