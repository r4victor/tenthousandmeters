Title: Python behind the scenes #9: how Python strings work
Date: 2021-02-09 9:30
Tags: Python behind the scenes, Python, CPython

In 1991 Guido van Rossum released the first version of the Python programming language to the world. About that time the world began to witness a major change in how computer systems represent written language. The internalization of the Internet increased the demand to support different writing systems, and the Unicode standard was developed to meet this demand. Unicode defined a single character set able to represent any written language, various non-alphanumeric symbols and, eventually, emoji 😀. Python wasn't designed with Unicode in mind, but it evolved towards Unicode support during the years. In 2000, PEP 100 added built-in support for Unicode strings – the `unicode` type that later became the `str` type in Python 3. Python strings have been proven to be a handy way to work with text in the Unicode age. Today we'll see how they work behind the scenes.

## The scope of this post

This post doesn't try to cover all aspects of text encoding in relation to Python. You see, programming language designers have to make several text encoding decisions because they have to answer the following questions:

* How to talk to the external world (the encodings of command-line parameters, environment variables, standard streams and the file system).
* How to read the source code (the encoding of source files).
* How to represent text internally (the encoding of strings).

This post focuses on the last problem.

## The essence of text encoding

## Unicode basics

## Python's road to Unicode support

## Meet Python strings