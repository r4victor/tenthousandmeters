Title: Python behind the scenes #10: how Python dictionaries work
Date: 2021-03-02 5:49
Tags: Python behind the scenes, Python, CPython

Python dictionaries are an extremely important part of Python. Of course they are imporant because programmers use them a lot, but that's not the only reason. Another reason is that CPython uses them internally to run Python code. We've seen that in previous parts. CPython does a dictionary lookup every time we access an object's attribute or a class variable, and accessing a global or built-in variable also involves a dictionary lookup if the result is not cached. What makes a dictionary appealing is that the lookup and insert operations are fast and that they remain fast even as we add more and more elements to the dictionary. You probably know why this is the case: Python dictionaries are hash tables. A hash table is a fundamental data structure. Its idea is simple and has been around for more that 50 years. Nevertheless, implementing a hash table that works well in practice is still a challenging task. We need to dive deep into the world of hash tables to understand how Python dictionaries really work. And that's what we're going to do today. We'll begin by designing a simple fully-functional hash table. Then we'll discuss what it takes to implement a hash table that works well in practice and see how CPython does that. As a bonus, we'll learn a few facts about Python dictionaries that will help us use them more efficiently.

## What is a dictionary

Let us first clarify that a dictionary and a hash table are not the same thing. A **dictionary** (also known as a map or associative array) is an interface that maintains a collection of (key, value) pairs and supports at least three operations:

* Insert a (key, value) pair: `d[key] = value`.
* Lookup the value for a given key: `d[key]`.
* Delete the key and the associated value: `del d[key]`.

A hash table is a data structure that is commonly used to implement dictionaries. We may, however, use other data structures to implement dictionaries as well. For example, we may store the (key, value) pairs in a [linked list](https://en.wikipedia.org/wiki/Linked_list) and do a linear search to lookup the value for a given key. A dictionary can also be implemented as a sorted array or as a [search tree](https://en.wikipedia.org/wiki/Search_tree). All these data structures can be used to implement the same interface. The difference between them is that they have different perfomace characteristics. Hash tables are a popular choice because they exhibit excellent average-case performance. We'll see what it means in theory and in practice, but before we do that, let's discuss how hash tables work.

## Designing a simple hash table

In its essence, a hash table is an array. A nice fact about arrays is that we can access the i-th element of an array in constant time. The main idea behind a hash table is to map each possible key to an array index, so that the index can be used to quickly locate the value of the key. We'll now show how to build such a mapping.

Let's restrict for a moment the set of possible keys to a relatively small range of non-negative integers, say [0, 999]. We can then implement the dictionary using an array of size 1000. We just use keys as indices to the array, so that the i-th element of the array holds the value of the key i. Obviously, the insert, lookup and delete operations take constant time.

The shortcoming of this implementation is that it supports very limited set of keys. Arbitrary-precision integers, strings, tuples and other data types that we may need to use as keys are not supported. How can we fix it? Suppose we could devise a function that would map every possible key, be it an integer, a string or a something else, to an index of the array. Then we could store the value of a key under the corresponding index.

## Designing a real-world hash table

