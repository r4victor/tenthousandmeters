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

The other requirement says that the probability of a key being mapped to a bucket must be the same for all buckets and equal to `1/number_of_buckets`. So, we would like to have a hash function that distributes the keys uniformly among buckets. The problem with this is that the probability distribution of hashes is affected by the probability distribution of keys. For example, if the keys are uniformly distributed, then the hash function `h(key) = key % number_of_buckets` will give uniform distribution of hashes. But suppose that the keys are limited to even integers. Then, if the number of buckets is even, the same hash function will never map a key to an odd bucket. At least half of buckets won't be used. So, what hash function should we choose? This is the topic of the next section.

## Hash functions

If we cannot predict what the keys in every possible application will be, then we need to choose a hash function that is expected to uniformly distribute any set of keys. The way to do this is to generate the hash function randomly. That is, with equal probability, we assign a random hash to each possible key. Note that the hash function itself must be deterministic. Only the generation step is random.

A randomly generated hash function is the best hash function. Unfortunately, it's impractical. The only way to represent such a function in a program is to store it explicitly as a table of (key, hash) pairs, like so:

| key    | 0    | 1    | 2    | 3    | 4    | 5    | 6    | 7    | ...  |
| ------ | ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| h(key) | 43   | 521  | 883  | 118  | 302  | 91   | 339  | 16   | ...  |

And this requires too much memory.

The best thing we can do in practice is to choose a hash function that in some sense approximates a randomly generated hash function. Fortunately, there exists a number of approaches to do that. Before we delve into them, note that there is no need to choose a separate hash function for each possible hash table size. What real-world hash table implementations do instead is introduce an auxiliary hash function that maps keys to fixed-size integers, such as 32-bit or 64-bit ints, and another function that maps these integers to hash table buckets. Only the latter function changes when the size of the hash table changes. Typically, it's just the modulo operation, so that the bucket for a given key is calculated as follows:

```text
hash(key) % number_of_buckets
```

Most implementations use powers of 2 as the hash table size because in this case the modulo operation can be computed very efficiently. To compute `hash(key) % (2 ** m)`, we just take `m` lower bits of `hash(key)`: 

```text
hash(key) & (2 ** m - 1)
```

This approach requires that the `hash()` function produces uniformly distributed hashes. When the `hash()` function is not designed with this requirement in mind, hash table designers resort to certain tricks. A common advice is to use prime number as the hash table size, so that the bucket for a given key is calculated as follows:

```text
hash(key) % prime_number
```

Composite numbers are considered to be a bad choice because of the following identity:

$$ka\;\%\;kn = k (a \;\% \;n)$$

It means that if a key shares a common factor with the number of buckets, then the key will be mapped to a bucket that is a multiple of this factor. So, the buckets will be filled disproportionately if such keys dominate. Prime numbers are recommended because they are more likely to break patterns in the input data.

Another trick is to use powers of 2 as the hash table size but scramble the bits of a hash before taking the modulus. You may find such a trick in the [Java HashMap](https://github.com/openjdk/jdk/blob/742d35e08a212d2980bc3e4eec6bc526e65f125e/src/java.base/share/classes/java/util/HashMap.java):

```Java
/**
* Computes key.hashCode() and spreads (XORs) higher bits of hash
* to lower.  Because the table uses power-of-two masking, sets of
* hashes that vary only in bits above the current mask will
* always collide. (Among known examples are sets of Float keys
* holding consecutive whole numbers in small tables.)  So we
* apply a transform that spreads the impact of higher bits
* downward. There is a tradeoff between speed, utility, and
* quality of bit-spreading. Because many common sets of hashes
* are already reasonably distributed (so don't benefit from
* spreading), and because we use trees to handle large sets of
* collisions in bins, we just XOR some shifted bits in the
* cheapest possible way to reduce systematic lossage, as well as
* to incorporate impact of the highest bits that would otherwise
* never be used in index calculations because of table bounds.
*/
static final int hash(Object key) {
    int h;
    return (key == null) ? 0 : (h = key.hashCode()) ^ (h >>> 16);
}
```

No tricks are needed if we choose a proper hash function in the first place. As we've already said, there exists a number of approaches to do that. Let us now see what they are.

### Non-cryptographic hash functions

The first approach is to choose a well-known non-cryptographic hash function that was designed to work well in practice. The list of such functions includes [Jenkins hash](https://en.wikipedia.org/wiki/Jenkins_hash_function), [FNV hash](https://en.wikipedia.org/wiki/Jenkins_hash_function), [MurmurHash](https://en.wikipedia.org/wiki/MurmurHash), [CityHash](https://github.com/google/cityhash), [xxHash](https://github.com/Cyan4973/xxHash) and [many others](https://en.wikipedia.org/wiki/List_of_hash_functions#Non-cryptographic_hash_functions). These functions take byte sequences as their inputs, so they can be used to hash all kinds of data. To get a rough idea of how they work, let's take a look at the [FNV-1a hash](https://en.wikipedia.org/wiki/Fowler%E2%80%93Noll%E2%80%93Vo_hash_function). Here's what its Python implementation may look like:

```python
OFFSET_BASIS = 2166136261
FNV_PRIME = 16777619
HASH_SIZE = 2 ** 32


def fvn1a(data: bytes) -> int:
    h = OFFSET_BASIS
    for byte in data:
        h = h ^ byte
        h = (h * FNV_PRIME) % HASH_SIZE
    return h
```

For each byte in the input, the function performs two steps:

* combines the byte with the current hash value (xor); and
* mixes the current hash value (multiply).

All hash functions have this structure. To get an idea of why they work that way and why they use particular operations and constants, check out Bret Mulveyʼs [excellent article on hash functions](https://papa.bretmulvey.com/post/124027987928/hash-functions). Bret also explains how to evaluate the quality of a hash function, so we won't discuss it here. Some very interesting results can be found in [this answer](https://softwareengineering.stackexchange.com/questions/49550/which-hashing-algorithm-is-best-for-uniqueness-and-speed) on StackExchange. Check them out too!

A fixed non-cryptographic hash function performs well in practice under normal circumstances. It performs very poorly when someone intentionally tries to supply bad inputs to the hash table. The reason is that a non-cryptographic hash function is not collision-resistant, so it's fairly easy to come up with a sequence of distinct keys that all have the same hash and thus map to the same bucket. If a malicious user inserts a sequence of $n$ such keys, then the hash table will handle the input in $O(n^2)$. This may take a long time and freeze the program. The attack we're talking about is known as a Hash DoS attack or hash flooding. A potential target of hash flooding is a web application that automatically parses incoming query parameters or POST data into a dictionary. Since most web frameworks offer this functionality, the problem is real. Next we'll look at two approaches to choose a hash function that solve it.

### Universal hashing

Note that attackers won't be able to come up with the sequence of colliding keys if they know nothing about the hash function used. So, a randomly generated hash function is again the best solution. We said that we cannot use such a function in practice, but what if we randomly choose a hash function from a family of "good" functions that can be computed efficiently, won't it do the job? It will, though we need to find a family of functions suitable for this purpose. A family won't be suitable, for example, if we can come up with the sequence of keys that collide for every function in the family. Ideally, we would like to have a family such that, for any set of keys, a function randomly chosen from the family is expected to distribute the keys uniformly among buckets. Such families exist, and they are called universal families. We say that a family of functions is **d-universal** if, for two fixed distinct keys, the propability to choose a function that maps these keys to the same bucket is less than `d/number_of_buckets`. In mathematical notation this definiton looks like this:

$$ \forall x \ne y \in Keys\;\; \underset{h\in F}\Pr[h(x) = h(y)] \le \frac{d}{number\_of\_buckets}$$