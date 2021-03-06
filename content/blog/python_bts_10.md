Title: Python behind the scenes #10: how Python dictionaries work
Date: 2021-03-02 5:49
Tags: Python behind the scenes, Python, CPython

Python dictionaries are an extremely important part of Python. Of course they are imporant because programmers use them a lot, but that's not the only reason. Another reason is that CPython uses them internally to run Python code. We've seen that in previous parts. CPython does a dictionary lookup every time we access an object's attribute or a class variable, and accessing a global or built-in variable also involves a dictionary lookup if the result is not cached. What makes a dictionary appealing is that the lookup and insert operations are fast and that they remain fast even as we add more and more elements to the dictionary. You probably know why this is the case: Python dictionaries are hash tables. A hash table is a fundamental data structure. Its idea is simple and has been around for more that 50 years. Nevertheless, implementing a hash table that works well in practice is still a challenging task. We need to dive deep into the world of hash tables to understand how Python dictionaries really work. And that's what we're going to do today. We'll begin by designing a simple fully-functional hash table. Then we'll discuss what it takes to implement a hash table that works well in practice and see how CPython does that. As a bonus, we'll learn a few facts about Python dictionaries that will help us use them more efficiently.

## What is a dictionary

Let us first clarify that a dictionary and a hash table are not the same thing. A dictionary (also known as a map or associative array) is an interface that maintains a collection of (key, value) pairs and supports at least three operations:

* Insert a (key, value) pair: `d[key] = value`.
* Lookup the value for a given key: `d[key]`.
* Delete the key and the associated value: `del d[key]`.

A hash table is a data structure that is commonly used to implement dictionaries. We may, however, use other data structures to implement dictionaries as well. For example, we may store the (key, value) pairs in a [linked list](https://en.wikipedia.org/wiki/Linked_list) and do a linear search to lookup the value for a given key. A dictionary can also be implemented as a sorted array or as a [search tree](https://en.wikipedia.org/wiki/Search_tree). All these data structures can be used to implement the same interface. The difference between them is that they have different perfomace characteristics. Hash tables are a popular choice because they exhibit excellent average-case performance. We'll see what it means in theory and in practice, but before we do that, let's discuss how hash tables work.

## Designing a simple hash table

In its essence, a hash table is an array. A nice fact about arrays is that we can access the i-th element of an array in constant time. The main idea behind a hash table is to map each possible key to an array index, so that the index can be used to quickly locate the value of the key. 

An array index specifies a position in the array. In the hash table terminology an individual array position is called a **bucket**. The function that maps keys to buckets is called a **hash function**. We now show one simple way to construct it.

To hash integer keys, we use a hash function of the form `h(key) = key % number_of_buckets`. It gives the values in the range `[0, number_of_buckets - 1]`. And this is exactly what we need! To hash other data types we first convert them to integers. For example, we can convert a string to an integer if we interpret the characters of the string as digits in a certain base. Then the integer value of the string of length $n$ can be calculated as follows:

$$str\_to\_int(s) = s[0] \times base ^{n-1} + s[1] \times base ^{n-2} + \cdots + s[n-1]$$

where $base$ is the size of the alphabet.

With this approach, different keys may map to the same bucket. In fact, if the number of possible keys is larger than the number of buckets, then some key will always map to the same bucket no matter what hash function we choose. So, we have to find a way to handle hash collisions. One popular method to do that is called **chaining**. The idea of chaining is to associate an additional data structure with each bucket and to store all the items that hash to the same bucket in that data structure. The following picture shows a hash table that uses linked lists for chaining:

<br>

<img src="{static}/blog/python_bts_10/hash_table_with_chaining.png" alt="hash_table_with_chaining" style="width:700px; display: block; margin: 0 auto;" />

<br>

To insert a (key, value) pair into such a table, we hash the key and search for it in the corresponding linked list. If we find the key, we update the value. If we don't find the key, we add a new entry to the list. The lookup and delete operations are done in a similar manner.

We now have a working hash table. How well does it perform? The worst-case analysis is quite simple. If the set of possible keys is sufficiently large, then there is a non-zero chance that all the items we add to the hash table will happen to be in the same bucket. The average-case performance is more promising. It largely depends on two factors. First, it depends on how evenly the hash function distributes the keys among buckets. Second, it depends on the average number of items per bucket. This latter characteristic of a hash table is called a **load factor**:

$$load\_factor = \frac{number\_of\_items}{number\_of\_buckets}$$

Theory says that if a key is equally likely to hash to any bucket and if the load factor is bounded by a constant, then the expected time of a single insert, lookup and delete operation is constant.

The load factor requirement is easy to satisfy. We just double the size of the hash table when the load factor exceeds some predefined limit. Let this limit be 2. Then if, upon insertion, the load factor becomes more than 2, we allocate a new hash table that has twice as many buckets as the current one and reinsert all the items into the new hash table. This way, no matter how many items we insert into the hash table, the load factor is always kept between 1 and 2. The cost of resizing the hash table is proportional to the number of items in it, so inserts that trigger resizing are expensive. Nevertheless, such inserts are rare, because the size of the hash table grows in the geometric progression. The expected time of a single insert remains constant.

The other requirement says that the probability of a key being mapped to a bucket must be the same for all buckets and equal to `1/number_of_buckets`. So, we would like to have a hash function that distributes the keys uniformly among buckets. The problem with this is that the probability distribution of hashes is affected by the probability distribution of keys. For example, if the keys are uniformly distributed, then the hash function `h(key) = key % number_of_buckets` will give uniform distribution of hashes. But suppose that the keys are limited to even integers. Then, if the number of buckets is even, the same hash function will never map a key to an odd bucket. At least half of buckets won't be used.

## Designing a real-world hash table

