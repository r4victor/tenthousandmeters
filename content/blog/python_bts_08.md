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

We'll also discuss how CPython's implementation compares to others and highlight some important details of Python integers.

## Bignum representation

Think for a moment how you would represent big integers in your program if you were to implement them yourself. Probably the most obvious way to do that is to store an integer as a sequence of digits, just like we usually write down numbers. For example, the integer `51090942171709440000` could be represented as `['5', '1', '0', '9', '0', '9', '4', '2', '1', '7', '1', '7', '0', '9', '4', '4', '0', '0', '0', '0']`. This is essentially how bignums are represented in practice. The only important difference is that instead of base 10, much larger bases are used. For example, CPython uses base 2^15 or base 2^30 depending on the platform. What's wrong with base 10? If we represent each digit in a sequence with a single byte but use only 10 out of 256 possible values, it would be very memory-inefficient. We could solve this memory-efficiency problem if we use base 256, so that each digit takes a value between 0 and 255. But still much larger bases are used in practice. The reason for that is because larger base means that numbers have less digits, and the less digits numbers have, the faster arithmetic operations are performed. The base cannot be arbitrary large. It's typically limited by the size of the integers that the CPU can work with. We'll see why this is the case when we discuss bignum arithmetic in the next section. Now let's take a look at how CPython represents bignums.

Everything related to the representation of Python integers can be found in `Include/longintrepr.h`. Technically, Python integers are instances of `PyLongObject` defined in `Include/longobject.h`, but `PyLongObject` is a typedef for `struct _longobject` that is defined in `Include/longintrepr.h`:

```C
struct _longobject {
  	PyVarObject ob_base; // expansion of PyObject_VAR_HEAD macro
    digit ob_digit[1];
};
```

This struct extends [`PyVarObject`](https://docs.python.org/3/c-api/structures.html#c.PyVarObject), which in turn extends [`PyObject`](https://docs.python.org/3/c-api/structures.html#c.PyObject):

```C
typedef struct {
    PyObject ob_base;
    Py_ssize_t ob_size; /* Number of items in variable part */
} PyVarObject;
```

So, besides a reference count and a type that all Python objects have, an integer has two other members: 

* `ob_size` that comes from `PyVarObject`; and 
* `ob_digit` that is defined in `struct _longobject`.

The `ob_digit` member is a pointer to an array of digits. On 64-bit platforms, each digit is a 30-bit integer that takes values between 0 and 2^30-1 and is stored as an unsigned 32-bit int (`digit` is a typedef for `uint32_t`). On 32-bit platforms, each digit is a 15-bit integer that takes values between 0 and 2^15-1 and is stored as an unsigned 16-bit int (`digit` is a typedef for `unsigned short`). To make things concrete, we'll use 30-bit digits throughout this post.

The `ob_size` member is a signed int, whose absolute value tells us the number of digits in the `ob_digit` array. The sign of `ob_size` indicates the sign of the integer. Negative `ob_size` means that the integer is negative.

Digits are stored in a little-endian order. The first digit (`ob_digit[0]`) is the least significant, and the last digit (`ob_digit[abs(ob_size)-1]`) is the most significant.

Finally, the absolute value of an integer is calculated as follows: 

$$val = ob\_digit[0] \times (2 ^{30})^0 + ob\_digit[1] \times (2 ^{30})^1 + \cdots + ob\_digit[abs(ob\_size) - 1] \times (2 ^{30})^{abs(ob\_size) - 1}$$

Let's see what all of this means with an example. Suppose we have an integer object that has `ob_digit = [3, 5, 1]` and `ob_size = -3`. To compute its value, we can do the following:

```pycon
$ python -q
>>> base = 2**30
>>> -(3 * base**0 + 5 * base**1 + 1 * base**2)
-1152921509975556099
```

Now let's do the reverse. Suppose we want to get the bignum representation of the number `51090942171709440000`. Here's how we can do that:

```pycon
>>> x = 51090942171709440000
>>> x % base
952369152
>>> (x // base) % base
337507546
>>> (x // base // base) % base
44
>>> (x // base // base // base) % base
0
```

So, `ob_digit = [952369152, 337507546, 44]` and `ob_size = 3`. Actually, we don't even have to compute the digits, we can get them by inspecting the integer object using the [`ctypes`](https://docs.python.org/3/library/ctypes.html#module-ctypes) standard library:

```python
import ctypes


MAX_DIGITS = 1000

# This is a class to map a C `PyLongObject` struct to a Python object
class PyLongObject(ctypes.Structure):
    _fields_ = [
        ("ob_refcnt", ctypes.c_ssize_t),
        ("ob_type", ctypes.c_void_p),
        ("ob_size", ctypes.c_ssize_t),
        ("ob_digit", MAX_DIGITS * ctypes.c_uint32)
    ]


def get_digits(num):
    obj = PyLongObject.from_address(id(num))
    digits_len = abs(obj.ob_size)
    return obj.ob_digit[:digits_len]
```

```pycon
>>> from num_digits import get_digits
>>> x = 51090942171709440000
>>> get_digits(x)
[952369152, 337507546, 44]
```



## Bignum arithmetic

## Memory usage considerations





