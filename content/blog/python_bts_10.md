Title: Python behind the scenes #10: how Python dictionaries work
Date: 2021-03-02 5:49
Tags: Python behind the scenes, Python, CPython

Python dictionaries are an extremely important part of Python. Not only they are used in Python code, but they are also used to run Python code. CPython does a dictionary lookup every time you access an object's attribute or a class variable. And accessing a global or built-in variable also involves a dictionary lookup if the result is not cached. What makes a dictionary appealing is that the lookup and insert operations are fast and that they remain fast even as we add more and more elements to the dictionary. You probably know why this is the case – Python dictionaries are hash tables. There is a number of different ways to implement a hash table, however, and if you haven't taken a time to study the CPython implementation on its own, you'd be surprised to learn how it works. Today we'll discuss what it takes to implement a real-world hash table, see how CPython does that and learn a few facts that will help us use Python dictionaries more efficiently.

## What is a dictionary

Let us first clarify that a dictionary and a hash table are not the same thing. A dictionary (also known as a map or associative array) is an interface that somehow maintains a collection of (key, value) pairs and supports at least three operations:

* Insert a (key, value) pair: `d[key] = value`.
* Lookup the value for a given key: `d[key]`.
* Delete the key and the associated value: `del d[key]`.

A hash table is a data structure that is commonly used to implement dictionaries. We may, however, use other data structures to implement dictionaries as well. For example, we may store the (key, value) pairs in a [linked list](https://en.wikipedia.org/wiki/Linked_list) and do a linear search to lookup the value for a given key. A dictionary can also be implemented as a sorted array or as a [search tree](https://en.wikipedia.org/wiki/Search_tree). The choice of the data structure matters a lot because it determines the dictionary performance. This is where hash tables shine. Under certain assumptions, they provide inserts, lookups and deletes that take constant time on average.

## Designing a simple hash table



## Designing a real-world hash table

