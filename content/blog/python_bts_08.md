Title: Python behind the scenes #8: how Python integers work
Date: 2021-02-04 5:33
Tags: Python behind the scenes, Python, CPython

In the previous parts of this series we studied the core of the CPython interpreter and saw how the most fundamental aspects of Python are implemented. We made an overview of the CPython VM, took a look at the CPython compiler, stepped through the CPython source code, studied how the VM executes the bytecode and learned how variables work. In the two most recent posts we focused on the Python object system. We learned what Python objects and Python types are, how they are defined and what determines their behavior. This discussion gave us a good understanding of how Python objects work in general. What we haven't discussed is how particular objects, such as strings, integers and lists, are implemented. In this and several upcoming posts we'll cover the implementations of the most important and most interesting built-in types. The subject of today's post is `int`.

## Why Python integers are interesting

Integers require no introduction. They are so ubiquitous and seem so basic that you may doubt whether it's worth discussing how they are implemented at all. Yet, Python integers are interesting because they are not just 32-bit or 64-bit integers that the CPUs work with natively. Python integers are [arbitrary-precision integers](https://en.wikipedia.org/wiki/Arbitrary-precision_arithmetic), also known as bignums, which effectively means that they can be as large as you want, and their sizes are only limited by the amount of available memory.

Bignums are handy to work with because you don't need to worry about such things as integer overflows. They are extensively used in fields like cryptography and computer algebra where big numbers arise all the time and must be represented precisely. So, [many](https://en.wikipedia.org/wiki/List_of_arbitrary-precision_arithmetic_software) programming languages have bignums built-in. This includes Python, JavaScript, Ruby, Haskell, Erlang, Julia, Racket. Other provide bignums as a part of the standard library. This includes Go, Java, C#, D, PHP. Numerous third-party libraries implement bignums. The most popular one is [the GNU Multiple Precision Arithmetic Library](https://en.wikipedia.org/wiki/GNU_Multiple_Precision_Arithmetic_Library) (GMP), which provides a C API but has bingings for all major languages.

There are a lot of bignum implementations. They are different in detail, but the general approach to implement bignums is the same. Today we'll see what this approach looks like and use CPython's implementation as an example. The two main questions we'll have to answer are:

* how to represent bignums; and
* how to performs arithmetic operations, such as addition and multiplication, on bignums.

We'll also discuss how CPython's implementation compares to others and highlight other important details of Python integers.

## Bignum representation

## Bignum arithmetic

## Memory usage considerations





