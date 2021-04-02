Title: Python behind the scenes #10: how Python dictionaries work
Date: 2021-03-02 5:49
Tags: Python behind the scenes, Python, CPython

Python dictionaries are an extremely important part of Python. Of course they are imporant because programmers use them a lot, but that's not the only reason. Another reason is that the interpreter uses them internally to run Python code. CPython does a dictionary lookup every time we access an object's attribute or a class variable, and accessing a global or built-in variable also involves a dictionary lookup if the result is not cached. What makes a dictionary appealing is that lookups and other dictionary operations are fast and that they remain fast even as we add more and more elements to the dictionary. You probably know why this is the case: Python dictionaries are implemented as hash tables. A hash table is a fundamental data structure. The idea behind it is very simple and widely known. Yet, implementing a practical hash table is not a trivial task. There are different hash table designs that vary in complexity and performance. And new, better designs are constantly being developed.

The goal of this post is to learn how hash tables are implemented in CPython. But understanding all the aspects of hash table design can be hard, and CPython's implementation is especially sophisticated, so we should approach this topic gradually. In the first part of the post, we'll design a simple fully-functional hash table, discuss its strengths and limitations and outline a general approach to design a hash table that works well in practice. In the second part, we'll focus on the specifics of CPython's implementation and finally see how Python dictionaries work behind the scenes.

## What is a dictionary

Let us first clarify that a dictionary and a hash table are not the same thing. A dictionary (also known as a map or associative array) is an interface that maintains a collection of (key, value) pairs and supports at least three operations:

* Insert a (key, value) pair: `d[key] = value`.
* Lookup the value for a given key: `d[key]`.
* Delete the key and the associated value: `del d[key]`.

A hash table is a data structure that is commonly used to implement dictionaries. We may, however, use other data structures to implement dictionaries as well. For example, we may store the (key, value) pairs in a [linked list](https://en.wikipedia.org/wiki/Linked_list) and do a linear search to lookup the value for a given key. A dictionary can also be implemented as a sorted array or as a [search tree](https://en.wikipedia.org/wiki/Search_tree). All these data structures can be used to implement the same interface. The difference between them is that they have different perfomace characteristics. Hash tables are a popular choice because they exhibit excellent average-case performance. To see what it means in theory and in practice, let's discuss how hash tables work.

## Designing a simple hash table

In its essence, a hash table is an array. A nice fact about arrays is that we can access the i-th element of an array in constant time. The main idea behind a hash table is to map each key to an array index, so that the index can be used to quickly locate the value of the key. 

An array index specifies a position in the array. In the hash table terminology an individual array position is called a **bucket**. The function that maps keys to buckets is called a **hash function**. We now show one simple way to construct it.

To hash integer keys, we use a hash function of the form `h(key) = key % number_of_buckets`. It gives the values in the range `[0, number_of_buckets - 1]`. And this is exactly what we need! To hash other data types we first convert them to integers. For example, we can convert a string to an integer if we interpret the characters of the string as digits in a certain base. Then the integer value of the string of length $n$ can be calculated as follows:

$$str\_to\_int(s) = s[0] \times base ^{n-1} + s[1] \times base ^{n-2} + \cdots + s[n-1]$$

where $base$ is the size of the alphabet.

With this approach, different keys may map to the same bucket. In fact, if the number of possible keys is larger than the number of buckets, then some key will always map to the same bucket no matter what hash function we choose. So, we have to find a way to handle hash collisions. One popular method to do that is called **chaining**. The idea of chaining is to associate an additional data structure with each bucket and to store all the items that hash to the same bucket in that data structure. The following picture shows a hash table that uses linked lists for chaining:

<br>

<img src="{static}/blog/python_bts_10/hash_table_with_chaining.png" alt="hash_table_with_chaining" style="width:700px; display: block; margin: 0 auto;" />

<br>

To insert a (key, value) pair into such a table, we first hash the key to get its bucket and then search for the key in the corresponding linked list. If we find the key, we update the value. If we don't find the key, we add a new entry to the list. The lookup and delete operations are done in a similar manner.

Since the comparison of keys may take a long time (e.g. the keys are lengthy strings), the hashes are typically compared first. If the hashes are not equal, then the keys are not equal either. It's a common practice to store the hash along with the key and the value to avoid recomputing it each time.

We now have a working hash table. How well does it perform? The worst-case analysis is quite simple. If the set of possible keys is sufficiently large, then there is a non-zero chance that all the items we insert into the hash table will happen to be in the same bucket. The average-case performance is more promising. It largely depends on two factors. First, it depends on how evenly the hash function distributes the keys among buckets. Second, it depends on the average number of items per bucket. This latter characteristic of a hash table is called a **load factor**:

$$load\_factor = \frac{number\_of\_items}{number\_of\_buckets}$$

Theory says that if every key is equally likely to hash to any bucket, independently of other keys, and if the load factor is bounded by a constant, then the expected time of a single insert, lookup and delete operation is $O(1)$.

To see why this statement is true, insert $n$ different keys into the hash table with $m$ buckets and calculate the [expected](https://en.wikipedia.org/wiki/Expected_value) length of any chain. It will be equal to the load factor:

$$E[len(chain_j)] = \sum_{i=1}^{n} \Pr[key_i \;maps \;to \;bucket\; j ] = n \times  \Pr[a\; key \;maps \;to \;bucket\; j ] = n \times \frac{1}{m} = load\_factor$$

For more elaborate proofs, consult a textbook. [Introduction to Algorithms](https://en.wikipedia.org/wiki/Introduction_to_Algorithms) (a.k.a. CLRS) is a good choice.


How reasonable are the assumptions of the statement? The load factor assumption is easy to satisfy. We just double the size of the hash table when the load factor exceeds some predefined limit. Let this limit be 2. Then if, upon insertion, the load factor becomes more than 2, we allocate a new hash table that has twice as many buckets as the current one and reinsert all the items into the new hash table. This way, no matter how many items we insert into the hash table, the load factor is always kept between 1 and 2. The cost of resizing the hash table is proportional to the number of items in it, so inserts that trigger resizing are expensive. Nevertheless, such inserts are rare because the size of the hash table grows in the geometric progression. The expected time of a single insert remains $O(1)$.

The other assumption means that the probability of a key being mapped to a bucket must be the same for all buckets and equal to `1/number_of_buckets`. In other words, the hash function must produce uniformly distributed hashes. It's not that easy to construct such a hash function because the distribution of hashes may depend on the distribution of keys. For example, if the keys are integers, and each integer is equally likely to be the next key, then the modulo hash function `h(key) = key % number_of_buckets` will give uniform distribution of hashes. But suppose that the keys are limited to even integers. Then, if the number of buckets is even, the modulo hash function will never map a key to an odd bucket. At least half of buckets won't be used. 

It's quite easy to choose a bad hash function. How do we choose a good one? This is the topic of the next section.

## Hash functions

If we cannot predict what the keys in every possible application will be, then we need to choose a hash function that is expected to uniformly distribute any set of keys. The way to do this is to generate the hash function randomly. That is, with equal probability, we assign a random hash to each possible key. Note that the hash function itself must be deterministic. Only the generation step is random.

In theory, a randomly generated hash function is the best hash function. Unfortunately, it's impractical. The only way to represent such a function in a program is to store it explicitly as a table of (key, hash) pairs, like so:

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

This approach may lead to many hash collisions if the hashes differ mainly in higher bits. To make this situation unlikely, the `hash()` function is designed to give a close-to-uniform distribution of hashes.

Some hash table designers do not construct the `hash()` function properly and resort to certain tricks instead. A common advice is to use prime number as the hash table size, so that the bucket for a given key is calculated as follows:

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

The first approach is to choose a well-known non-cryptographic hash function designed for hash tables. The list of such functions includes [Jenkins hash](https://en.wikipedia.org/wiki/Jenkins_hash_function), [FNV hash](https://en.wikipedia.org/wiki/Jenkins_hash_function), [MurmurHash](https://en.wikipedia.org/wiki/MurmurHash), [CityHash](https://github.com/google/cityhash), [xxHash](https://github.com/Cyan4973/xxHash) and [many others](https://en.wikipedia.org/wiki/List_of_hash_functions#Non-cryptographic_hash_functions). These functions take byte sequences as their inputs, so they can be used to hash all kinds of data. To get a rough idea of how they work, let's take a look at the [FNV-1a hash](https://en.wikipedia.org/wiki/Fowler%E2%80%93Noll%E2%80%93Vo_hash_function). Here's what its Python implementation may look like:

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

1. combines the byte with the current hash value (xor); and
2. mixes the current hash value (multiplication).

All hash functions have this structure. To get an idea of why they work that way and why they use particular operations and constants, check out Bret Mulveyʼs [excellent article on hash functions](https://papa.bretmulvey.com/post/124027987928/hash-functions). Bret also explains how to evaluate the quality of a hash function, so we won't discuss it here. Some very interesting results can be found in [this answer](https://softwareengineering.stackexchange.com/questions/49550/which-hashing-algorithm-is-best-for-uniqueness-and-speed) on StackExchange. Check them out too!

A fixed non-cryptographic hash function performs well in practice under normal circumstances. It performs very poorly when someone intentionally tries to supply bad inputs to the hash table. The reason is that a non-cryptographic hash function is not collision-resistant, so it's fairly easy to come up with a sequence of distinct keys that all have the same hash and thus map to the same bucket. If a malicious user inserts a sequence of $n$ such keys, then the hash table will handle the input in $O(n^2)$. This may take a long time and freeze the program. The attack we're talking about is known as a Hash DoS attack or **hash flooding**. A potential target of hash flooding is a web application that automatically parses incoming query parameters or POST data into a dictionary. Since most web frameworks offer this functionality, the problem is real. Next we'll look at two approaches to choose a hash function that solve it.

### Universal hashing

Note that attackers won't be able to come up with the sequence of colliding keys if they know nothing about the hash function used. So, a randomly generated hash function is again the best solution. We said that we cannot use such a hash function in practice because it cannot be computed efficiently. But what if we randomly choose a hash function from a family of "good" functions that can be computed efficiently, won't it do the job? It will, though we need to find a suitable family of functions. A family won't be suitable, for example, if we can come up with a sequence of keys that collide for every function in the family. Ideally, we would like to have a family such that, for any set of keys, a function randomly chosen from the family is expected to distribute the keys uniformly among buckets. Such families exist, and they are called **universal families**. We say that a family of functions is universal if, for two fixed distinct keys, the propability to choose a function that maps these keys to the same bucket is less than `1/number_of_buckets`. In mathematical notation the same definition looks like this:

$$ \forall x \ne y \in Keys\;\; \underset{h\in F}\Pr[h(x) = h(y)] \le \frac{1}{number\_of\_buckets}$$

It means that an average function from a universal family is unlikely to produce colliding hashes for two distinct keys.

Just to get an idea of what a universal family may look like, here's a classic example of a universal family that can be used to hash integer keys:

$$h_{a, b}(x) = ((ax + b)\;\%\;p)\;\%\;number\_of\_buckets$$

where $p$ is any fixed prime number at least as large as the number of possible keys, and $a \in \{1, ...p-1\}$ and $b \in \{0, ...p-1\}$ are parameters chosen at random that specify a concrete hash function from the family.

What does universality give us? Suppose that we randomly choose a hash function from a universal family and use this hash function to insert a sequence of keys into a hash table with chaining and table resizing as described in the previous section. Then theory says that the expected length of each chain in the hash table is bounded by a constant. This implies that the expected time of a single insert, lookup and delete operation is $O(1)$. And it does not matter what keys we insert!

Note that we've made a similiar statement before:

> Theory says that if every key is equally likely to hash to any bucket, independently of other keys, and if the load factor is bounded by a constant, then the expected time of a single insert, lookup and delete operation is $O(1)$.

The important difference is that in the case of universal hashing the word "expected"  means averaging over hash functions, while the statement from the previous section refers to averaging over the keys.

To learn more about the theory behind universal hashing, read [the paper](https://www.cs.princeton.edu/courses/archive/fall09/cos521/Handouts/universalclasses.pdf) by Lawrence Carter and Mark Wegman that indroduced this concept. For examples of most efficient universal families known today, see [Mikkel Thorup's survey](https://arxiv.org/abs/1504.06804).

Universal hashing looks good in theory because it guarantees excellent average-case performance and protects against hash flooding. Nevertheless, you won't find many hash table implementations that actually use it. The reason is a combination of two facts:

* Universal hash functions are not as fast as the fastest non-cryptographic hash functions.
* Universal hash functions do not protect against advanced types of hash flooding.

What does the latter point mean? It is true that if a universal hash function is used, attackers cannot come up with a sequence of colliding keys beforehand. But if the attackers can observe how the hash function maps keys, they might be able to deduce how it works and come up with such a sequence. This situation is possible when users can work with the hash table interactively: insert a key, then lookup a key, then insert a key again and so on. To learn how the hash function maps keys, the attackers may perform a timing attack. First, they insert a single key into the hash table. Then, they try to lookup some other key that maps to the same bucket. When some key maps to the same bucket, the lookup takes more time because the hash table must compare the keys, so such a key is possible to detect. This is one way in which the information about the hash function may leak. Once it leaks, universal hashing doesn't give us any guarantees.

The described attack is known as **advanced hash flooding**. It was identified by Jean-Philippe Aumasson and Daniel J. Bernstein in 2012. At that time, most hash table implementations used non-cryptographic hash functions. Some of those hash functions employed an idea of universal hashing and took a randomly generated seed. Still, they [were vulnerable](http://emboss.github.io/blog/2012/12/14/breaking-murmur-hash-flooding-dos-reloaded/) to hash flooding. Aumasson and Bernstein pointed out this problem and argued that because of advanced hash flooding, even true universal hashing couldn't be a solution. They developed a keyed hash function called [SipHash](https://en.wikipedia.org/wiki/SipHash) that became the solution and is now widely used.

### SipHash

SipHash takes a 128-bit secret key and a variable-length input and produces 64-bit hash. Unlike non-cryptographic hash functions, SipHash is designed to have certain cryptographic properties. Specifically, it's designed to work as a [message authentication code](https://en.wikipedia.org/wiki/Message_authentication_code) (MAC). MACs guarantee that it is not feasible to compute the hash of a given input without knowing the secret key even when the hash of any other input is at hand. Thus, if the secret key is randomly generated and unknown to attackers, SipHash protects against advanced hash flooding.

Note that no hash function including SipHash can prevent the attackers from finding the colliding keys by bruteforce as we've seen in the example of a timing attack. This approach, however, requires $O(n^2)$ requests to find $n$ colliding keys, so the potential damage caused by the attack is significantly reduced.

Note also that there is no formal proof of SipHash's security. Such proofs are beyond the state of the art of the modern cryptography. Moreover, it is conceivable that somone will break SipHash in the future. Nevertheless, some cryptanalysis and much evidence show that SipHash should work as a MAC today.

SipHash is not as fast as some non-cryptographic hash functions, but its speed is comparable. The combination of speed and security made SipHash a safe bet for a general-purpose hash table. It's now used as a hash function in Python, Perl, Ruby, Rust, Swift and other languages. To learn more about SipHash, check out [the paper](http://cr.yp.to/siphash/siphash-20120918.pdf) by Aumasson and Bernstein.

The choice of the hash function plays a huge role in the performance of a hash table. It is, however, not the only choice hash table designers have to make. They also have to decide how to handle hash collisions. Chaining is one option, but there are other methods that often perform better in practice. In fact, most state-of-the-art hash table implementations use methods other than chaining. Let us now see what those methods are.

## Collision resolution methods

We saw that chaining can be used to implement a hash table whose average-case performance is constant. Asymptotically, we cannot do better. But asymptotic behavior is not what's important in practice. What's important in practice is the actual time it takes to process real-world data and the amount of memory required to do that. From this perspective, other collision resolution methods often perform better than chaining. Most of them are based on the same idea called **open addressing**.

In open addressing, all items are stored directly in the hash table. Hash collisions are resolved by using a hash function of a special form. Instead of mapping each key to a single bucket, a hash function of this form maps each key to a sequence of buckets. Such a sequence is called a **probe sequence**. Buckets in a probe sequence are often referred to as **probes**.

To insert a new (key, value) pair in a hash table with open addressing, we iterate over the buckets in the probe sequence until we find an empty bucket and store the pair there. We will always find an empty bucket eventually if the hash table is not full and if the probe sequence covers all the buckets in the hash table. In addition to that, the probe sequence should be a permutation of buckets since visiting the same bucket more than once is a waste of time. The following picture illustrates the insertion process into a hash table with open addressing:

<img src="{static}/blog/python_bts_10/hash_table_with_open_addressing.png" alt="hash_table_with_open_addressing" style="width:700px; display: block; margin: 20px auto 0 auto;" />

To lookup the value of a key, we iterate over the buckets in the probe sequence until we either find the key or find an empty bucket. If we find an empty bucket, then the key is not in the hash table because otherwise it would be inserted into the empty bucket that we found.

Deleting a key from a hash table with open addressing is not that straightforward. If we just clear the bucket it occupies, then some lookups will break because lookups assume that there are no gaps in a probe sequence. The following picture illustrates the problem:

<img src="{static}/blog/python_bts_10/hash_table_deletion.png" alt="hash_table_deletion" style="width:400px; display: block; margin: 20px auto 30px auto;" />

The problem is typically solved by marking the key deleted instead of actually deleting it. This way, it continues to occupy the bucket, so lookups do not break. The bucket can be reused later. The opportinity to reuse the bucket may not arise, but the dummy item will be removed eventually anyway when the hash table resizes.

One advantage of open addressing over chaining is that the hash table doesn't store a linked list pointer for every item in the hash table. This saves space. On the other hand, empty buckets take more space because each bucket stores an item instead of a pointer. Whether a hash table with open addressing is more memory-efficient depends on the size of items. If the items are much larger than pointers, than chaining is better. But if the items take little space (e.g. the keys and the values are pointers themselves), then open addressing wins. The saved space can then be used to increase the number of buckets. More buckets means less hash collisions, and less hash collisions means the hash table is faster.

So, how do we construct a hash function that returns probe sequences? Typically, it's built of ordinary hash functions that we've studied before. In **linear probing**, for example, an ordinary hash function is used to compute the first probe. Every next probe is just the next bucket in the hash table:

```text
probes[i] = hash(key) + i % number_of_buckets
```

So, if the first probe is bucket `b`, then the probe sequence is:

````text
[b, b + 1, b + 2, ..., number_of_buckets - 1, 0, 1, ..., b - 1]
````

Despite its simplicity, linear probing guarantees constant average-case performance under two conditions. The first conditions is that the load factor must be strictly less than 1. The second condition is that the `hash()` function must map every key with equal probability to any bucket and independently of other keys.

As we've already discussed, the second condition is hard-to-impossible to satisfy. In practice, we choose a hash function that works well enough, but linear probing is very sensitive to the quality of the hash function, so it's harder to do. Another issue is that the load factor must be low if we want a decent performance. Consider the following estimate of the expected number of scanned buckets to insert a new key that Donald Knuth derives in [his proof](https://jeffe.cs.illinois.edu/teaching/datastructures/2011/notes/knuth-OALP.pdf) of the statement:

$$E[\#scanned\_buckets(load\_factor)] \approx \frac{1}{2}(1 + \frac{1}{(1-load\_factor)^2})$$

If we take a load factor of 90%, then we'll have about 50 buckets scanned on average assuming that the number of items in the hash table is sufficiently large. Thus, the load factor should be much lower. And that means more empty buckets and higher memory usage.

When we insert a new key or lookup a key that is not in the hash table, we want to find an empty bucket as soon as possible. With linear probing, it can be a problem because of contiguous clusters of occupied buckets. Such clusters tend to grow because the larger the cluster is, the more likely the next key will hash to the bucket in that cluster and will be inserted at its end. This problem is known as **primary clustering**.

**Quadratic probing** solves the primary clustering problem and is less sensitive to the quality of the hash function. It's similiar to linear probing. The difference is that the value of the i-th probe depends quadratically on i:

```text
probes[i] = hash(key) + a * i + b * (i ** 2) % number_of_buckets
```

The constants `a` and `b` must be chosen carefully for the probe sequence to cover all the buckets. When the size of the hash table is a power of 2, setting `a = b = 1/2` guarantees that the probe sequence will cover all the buckets before it starts repeating them. What does the probe sequence look like? If the first probe is bucket `b`, then the sequence goes like `b`, `b + 1`, `b + 3`, `b + 6`, `b + 10`, `b + 15`, `b + 21` and so on (modulo `number_of_buckets`). Note that the interval between two consecutive probes increases by 1 at each step. The intervals form a sequence of numbers known as [triangular numbers](https://en.wikipedia.org/wiki/Triangular_number). To learn why triangular numbers produce complete probe sequences, check out [this paper](http://www.chilton-computing.org.uk/acl/literature/reports/p012.htm).

An alternative to quadratic probing is **pseudo-random probing**. Like other probing schemes, it computes the first probe by calling the hash function:

```text
probes[0] = hash(key) % number_of_buckets
```

Then it passes the first probe as a seed to a pseudo-random number generator (PRNG) to compute the subsequent probes. Typically, the PRNG is implemented as a [linear congruential generator](https://en.wikipedia.org/wiki/Linear_congruential_generator), so the probes are computed as follows: 

```text
probes[i] = a * probes[i-1] + c % number_of_buckets
```

[Hull–Dobell Theorem](https://en.wikipedia.org/wiki/Linear_congruential_generator#c_%E2%89%A0_0) tells us how to choose the constants `a` and `c` so that the probe sequence convers all the buckets before it starts repeating them. Setting `a = 5` and `c = 1` when the size of the hash table is a power of 2 will do the job.

Quadratic probing and pseudo-random probing are still quite sensitive to the quality of the hash function because the probe sequences of two different keys will be identical whenever the keys map to the same bucket initially. This situation is also a form of clustering known as **secondary clustering**. There is a probing scheme that mitigates it. It's called **double hashing**.

In double hashing, the interval between two consecutive probes depends on the key itself. More specifically, a second, independent hash function determines the interval, so the probe sequence is calculated as follows:

```text
probes[i] = hash1(key) + hash2(key) * i % number_of_buckets
```

To ensure that the probe sequence covers all the buckets, the `hash2()` function must produce hashes that are relatively prime to the number of buckets, that is, `hash2(key)` and `number_of_buckets` must have no common factors except 1. This can be achieved by constructing the `hash2()` function in such a way so that it always returns a odd number and by setting the size of the hash table to a power of 2.

The more "random" probe sequences are, the less likely clustering is to occur and the less probes are needed. Thus, in theory, such sequences are better. But theory and practice do not always agree. Up until now we've been measuring the time complexity of algorithms in the number of elementary steps, such as the number of probes or the number of traversed linked list nodes. This metric works fine for asymptotic analysis, but it does not agree with the actual time measurements because it assumes that the cost of each elementary step is roughly the same, and that's not true in reality. In reality, the steps that access main memory are the most expensive. A single access to RAM takes about 100 ns. Compare it to the cost of accessing the fastest [CPU cache](https://en.wikipedia.org/wiki/CPU_cache) – it's about 1 ns. Therefore, one of the most important aspects of hash table design is the effective use of the cache.

Linear probing may perform quite well because it's very cache-friendly. To see why, recall that data is moved from the main memory to the cache in cache lines, which are contiguous blocks of memory, typically 64 bytes long. When the contents of the first bucket in a probe sequence have been read, the contents of the next several buckets are already in the cache.

As a general rule, a data structure will be more cache-effective if the items that are often used together are placed close to each other in memory. Linear probing follows this rule much better than other probing schemes. And open addressing in general works better than chaining in this respect because in chaining each item sits in a separately allocated node.

To better comprehend how much the cache affects hash table performance, consider the following graph:

<img src="{static}/blog/python_bts_10/dict_performance.png" alt="dict_performance" style="width:758px; display: block; margin: 0 auto;" />

This graph shows how the time of a single lookup in a Python dictionary changes as the number of items in the dictionary increases. It is clear that the time is not constant but increases as well. Why? Hash collisions are not the reason because the keys were chosen at random from a uniform distribution. You might also think that it's a peculiarity of a Python dictionary, but it's not. Any other hash table would behave similarly. The real reason is that when the hash table is small, it fits completely into the cache, so the CPU doesn't need to access the main memory. As the hash table grows larger, the portion of the hash table that is not in the cache grows as well, and the CPU has to access the main memory more frequently.

By the way, have you noticed those zigzags in the graph? They indicate the moments when the hash table resizes.

So, we've discussed a number of methods to resolve hash collisions: chaining and open addressing with various probing schemes. You probably think: why do we need all of them? The reason is that different methods suit different use cases. Chaining makes sense when the items are large and when deletes are frequent. Linear probing works best when the items are small and when the hash function distributes the keys uniformly. And quadratic probing, pseudo-random probing and double hashing are a safe bet in most cases.

State-of-the-art hash tables are typically variations of open addressing with some improvements. Google's [Swiss Table](https://abseil.io/about/design/swisstables), for example, uses [SIMD](https://en.wikipedia.org/wiki/SIMD) instructions to probe several buckets in parallel. [This talk](https://www.youtube.com/watch?v=ncHmEUmJZf4) explains how it works in detail. [Robin Hood hashing](https://en.wikipedia.org/wiki/Hash_table#Robin_Hood_hashing) is perhaps the most popular advanced method to resolve hash collisions. To understand the idea behind it, observe that the number of probes to lookup a key equals the number of probes that was required to insert it. Naturally, we would like to keep those numbers low. And that's what Robin Hood hashing tries to do. When a new key gets inserted, it doesn't just wait for an empty bucket but can also displace other keys. It displaces any key whose final probe number is less than the number of the current probe. The displaced key then continues on its probe sequence, possibly displacing other keys. As a result, large probe numbers do not emerge, and lookups become faster. To learn more about the benefits of Robin Hood hashing, check out [this post](https://www.sebastiansylvan.com/post/robin-hood-hashing-should-be-your-default-hash-table-implementation/). See also [Malte Skarupke's talk](https://www.youtube.com/watch?v=M2fKMP47slQ) to learn more about advanced methods to resolve hash collisions.

Well done! We've covered the essentials of hash table design. There is much more to say on this topic, but we now know enough to understand how Python dictionaries work. Without further ado, let's apply our knowledge.

## Python dictionaries

### Overview

A Python dictionary is a hash table with open addressing. Its size is always a power of 2, and its load factor varies between 1/3 and 2/3.

The hash of a Python object is a 32-bit or 64-bit singed integer (on 32-bit and 64-bit platforms respectively). We call the built-in `hash()` function to compute it, and this function works by calling the `tp_hash` slot of the object's type. Built-in types implement the `tp_hash` slot directly, and classes can implement it by defining the `__hash__()` special method. Thus, the hash function is different for different types. Strings and `bytes` objects are hashed with SipHash, while other types implement custom, simpler hashing algorithms.

The hash of an integer, for example, is usually the integer itself:

```pycon
$ python -q
>>> hash(1)
1
>>> hash(2343)
2343
>>> hash(-54)
-54
```

This is not always the case because Python integers can be arbitrary large. So, CPython implements a hashing algorithm that works like this:

```python
MODULUS = 2 ** 61 - 1 # Mersenne prime; taking the modulus is efficient

def hash_unoptimized(integer):
    """Unoptimized version of hash() for integers"""
    hash_value = abs(integer) % MODULUS
    if integer < 0:
        hash_value = -hash_value

    if hash_value == -1: # -1 indicates an error; do not use it
        return -2
    
    return hash_value
```

Because the algorithm is so simple, it's very easy to come up with a sequence of integers that all have the same hash:

```pycon
$ python -q
>>> modulus = 2 ** 61 - 1
>>> hash(0)
0
>>> hash(modulus)
0
>>> hash(modulus * 2)
0
>>> hash(modulus * 3)
0
>>> hash(modulus * 1000)
0
```

Isn't this a security issue? Apparently, CPython developers thougth that nobody in a sane mind would cast keys to integers automatically when parsing untrusted user input, so they decided not to use SipHash in this case.

But even non-malicious inputs exhibit regularities that such a primitive hash function won't break. To mitigate the effects of poorly distributed hashes, CPython implements a clever probing scheme.

The probing scheme is pseudo-random probing with a modification. To see the reasoning behind this modification, recall that pseudo-random probing suffers from secondary clustering: the whole probe sequence is determined by the first probe, and the first probe depends only on lower bits of the hash (`m` lower bits when the size of the hash table is `2**m`). CPython solves this problem by perturbing the first few probes with values that depend on higher bits of the hash. Here's what the algorithm that computes probes looks like:

```python
def get_probes(hash_value, hash_table_size):
    mask = hash_table_size - 1 # used to take modulus fast
    perturb = hash_value # used to perturb the probe sequence
    probe = hash_value & mask

    while True:
        yield probe

        perturb >>= 5
        probe = (probe * 5 + perturb + 1) & mask
```

Initially, `perturb` is set to the hash value. Then, at each iteration, it is shifted 5 bits to the right and the result is added to the linear congruential generator to perturb the next probe. This way, every next probe depends on 5 extra bits of the hash until `perturb` becomes 0. When `perturb` becomes 0, the linear congruential generator is guaranteed to cover all the buckets by the Hull–Dobell Theorem.

Despite the clever probing scheme, CPython hash tables seem very inefficient. First, their maximum load factor is 2/3, which is about 66.6%, and this is when state-of-the-art hash tables work well with load factors of 90% and more. So, there is a huge room for improvement here. Second, pseudo-random probing is not cache-friendly. And we saw how important the cache is.

Are CPython hash tables really as inefficient as they seem? Well, they certainly perform worse than Google's Swiss Table with hundreds of millions of items. But they are not optimized for such huge loads. They are optimized to be compact and to be fast when the hash table is small enough to fit into the cache. This is because the most important uses of Python dictionaries are the storage and retrieval of object attributes, class methods and global variables. And in this cases, the dictionaries are typically small and many.

CPython also employs some interesting optimizations to better fit the use cases above. Let's now take a look at them.

### Compact dictionaries

Before version 3.6, CPython hash tables looked like that:

Since version 3.6, CPython hash tables look like this:

### Shared keys

### String interning

--

Initially, it's set to 8. Then it doubles every time the load factor exceeds 2/3. CPython does not calculate the load factor explicitly but keeps track of the number of available buckets that is initially set to 2/3 of the total number of buckets:

```C
#define USABLE_FRACTION(n) (((n) << 1)/3)
```





 It starts with 8 buckets, and then the number of buckets doubles every time 

--

Like chaining, open addressing guarantees constant average-case performance under two conditions. The first condition is the same: the load factor must be bounded by a constant. The second condition is that the hash function is equally likely to map a key to any permutation of buckets.

Unfortunately, there is no practical way to construct such a hash function. Practical hash functions that produce probe sequences are typically built of ordinary hash functions. In **linear probing**, for example, an ordinary hash function is used to compute the first bucket in a probe sequence, and every next bucket in the probe sequence is just the next bucket in the hash table. In other words, the i-th bucket in the probe seqeunce is computed as follows:


Linear probing is not even close to meet the second condition of the statement. It can produce $number\_of\_buckets$ different probe sequences while there are $number\_of\_buckets!$ possible permutations of buckets. Therefore, most permutations are not used.

Another issue with linear probing is clustering. When we insert a new key or lookup a key that is not in the hash table, we want to find an empty bucket as soon as possible. With linear probing



---

There are two main directions of improvement:

* making the hash table more memory-efficient; and
* making the hash table more cache-friendly.

The first direction of improvement comes from the fact that a hash table with chaining stores a linked list pointer for every item in the hash table, and these pointers take space. We can save memory if we manage to get rid of the pointers. Sometimes it's worth doing and sometimes not. If the size of a pointer is significantly less than the size of a (key, value) pair, then we save only a small portion of the total memory occupied by the hash table. But if the keys and values take little space (e.g. there are pointers themselves), then a significant portion of the memory can be saved.

A more memory-efficient hash table not only takes less space for the same number of buckets but also has more buckets for the same amount of space. More buckets means less hash collisions, so memory and speed are closely related. One way to make a hash table faster is to make it more memory-efficient. 

Another way to improve upon chaining is to design a more cache-friendly hash table. Up until now we've been measuring the time complexity of algorithms in the number of elementary operations such as the number of linked list entries we need to traverse to lookup a key. This metric works fine for asymptotic analysis, but it does not agree with actual time measurements because it assumes that the cost of each elementary operation is roughly the same, and that's not true in reality. In reality, the operations that access main memory are the most expensive. A single access to RAM takes about 100 ns. Compare it to the cost of accessing the fastest [CPU cache](https://en.wikipedia.org/wiki/CPU_cache) – it's about 1 ns. Therefore, a faster hash table should access main memory less frequently. When it needs to read some data, the data should better be in the CPU cache. 

To see how the CPU cache affects hash table performance, consider the following graph:

<img src="{static}/blog/python_bts_10/dict_performance.png" alt="dict_performance" style="width:758px; display: block; margin: 0 auto;" />

This graph shows how the time of a single lookup in a Python dictionary changes as the number of items in the dictionary increases. It is clear that the time is not constant but increases as well. Why? Hash collisions cannot explain this behavior because the keys to insert and the keys to lookup were picked at random. You might also think that  it's a peculiarity of CPython's implementation, but it's not. Any other implementation would behave similarly. The real reason is that when the hash table is small, it fits completely into the CPU cache, so the CPU doesn't need to access the main memory. As the hash table grows larger, the CPU starts to access the main memory more frequently.

A lot can be said about the effective use of the cache. Ulrich Drepper's paper [What Every Programmer Should Know About Memory](https://people.freebsd.org/~lstewart/articles/cpumemory.pdf) is a comprehensive source on this topic.

```

```