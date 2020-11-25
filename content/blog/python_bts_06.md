Title: Python behind the scenes #6: how Python object system works
Date: 2020-11-21 5:18
Tags: Python behind the scenes, Python, CPython

As we know from the previous parts of this series, the execution of a Python program consists of two major steps:

1. The CPython compiler translates Python code to bytecode.
2. The CPython VM executes the bytecode.

We've been focusing on the second step for quite a while. In part 4 we've looked at the evaluation loop, a place where the bytecode gets executed. And in part 5 we've studied how the VM executes the instructions that are used to implement variables. What we haven't covered yet is how the VM actually computes something. We postponed this question because to answer it, we first need to understand how the most fundamental part of the language works. Today we'll study the Python object model.

## Motivation

Let's write a piece of code that computes something.

```python
def f(x):
    return x + 7
```

The compiler translates the body of the function `f` to the following bytecode:

```text
$ python -m dis f.py
...
  2           0 LOAD_FAST                0 (x)
              2 LOAD_CONST               1 (7)
              4 BINARY_ADD
              6 RETURN_VALUE
```

And the VM executes this bytecode as follows:

1. It loads the value of the parameter `x` onto the stack.
2. It loads the constant `7` onto the stack.
3. It pops the right operand from the stack, peeks the left operand, adds them and replaces the left operand on top of the stack with the result.
4. It pops the value from the stack and returns it.

Note that the compiler doesn't know whether `x` is an integer, a float, a list or something else, so it always produces the same `BINARY_ADD` opcode to perform the addition. The VM, therefore, must be able to figure out the right way to add `x` to `7` depending on what `x` is.

CPython solves this problem by representing everything in the language as a Python object (hence the phrase "Everything in Python is an object"). So, the VM needs to work only with Python objects. All values the VM stores on the value stack are pointers to Python objects. The VM doesn't know how to add integers or floats but it knows that any Python object has a type. A type, in turn, knows everything about objects of that type. The `int` type knows how to add integers, and the `float` type knows how to add floats. So, the VM asks the type to perform the operation.

This simplified explanation captures the essence of the solution, but it also omits a lot of important details. For example, you might think that to add `x` to `7`, the VM simply calls something like `x.__add__(7)`, `type(x).__add__(x, 7)` or `(7).__radd__(x)`, but the reality is a bit more complicated. To get a more realistic picture, we need to understand what Python objects and types really are and how they work.

## Python objects and types

We've discussed Python objects a little in [part 3]({filename}/blog/python_bts_03.md). This discussion is worth repeating here.    A Python object is:

* an instance of the `PyObject` struct; or
* an instance of any other struct that extends the `PyObject` struct.

The `PyObject` struct is defined as follows:

```C
typedef struct _object {
    _PyObject_HEAD_EXTRA // for debugging purposes only
    Py_ssize_t ob_refcnt;
    PyTypeObject *ob_type;
} PyObject;
```

It has two members:

* a reference count ` ob_refcnt` that CPython uses for garbage collection; and
* a pointer to the object's type `ob_type`.

Instances of the `PyObject` struct are useless because they don't store any value. All other Python objects that actually store something are defined by extending `PyObject`. A struct extends `PyObject` if:

* its first member is `PyObject`; or
* its first member is another struct that extends `PyObject`.

The C standard states that a pointer to any struct can be converted to a pointer to its first member and vice versa. Since any Python object extends `PyObject`, CPython can treat any Python object as `PyObject`. It's easy to understand with an example. Here's how CPython defines the `float` object:

```C
typedef struct {
    PyObject_HEAD // macro that expands to "PyObject ob_base;"
    double ob_fval;
} PyFloatObject;
```

The C standard simply states that we can convert a pointer to `PyFloatObject` to a pointer to `PyObject` and vice versa:

```C
PyFloatObject float_object;
// ...
PyObject *obj_ptr = (PyObject *)&float_object;
PyFloatObject *float_obj_ptr = (PyFloatObject *)obj_ptr;
```

The VM treats every Python object as `PyObject` because the only thing it needs to access is the object's type. A type is also a Python object, an instance of the `PyTypeObject` struct:

```C
// PyTypeObject is a typedef for "struct _typeobject"
struct _typeobject {
    PyObject_VAR_HEAD // macro that expands to "PyVarObject ob_base;"
                      //
                      // definition of PyVarObject:
                      // typedef struct {
                      //     PyObject ob_base;
                      //     Py_ssize_t ob_size; /* Number of items in variable part */          
                      // } PyVarObject;
    
    const char *tp_name; /* For printing, in format "<module>.<name>" */
    Py_ssize_t tp_basicsize, tp_itemsize; /* For allocation */

    /* Methods to implement standard operations */

    destructor tp_dealloc;
    Py_ssize_t tp_vectorcall_offset;
    getattrfunc tp_getattr;
    setattrfunc tp_setattr;
    PyAsyncMethods *tp_as_async; /* formerly known as tp_compare (Python 2)
                                    or tp_reserved (Python 3) */
    reprfunc tp_repr;

    /* Method suites for standard classes */

    PyNumberMethods *tp_as_number;
    PySequenceMethods *tp_as_sequence;
    PyMappingMethods *tp_as_mapping;

    /* More standard operations (here for binary compatibility) */

    hashfunc tp_hash;
    ternaryfunc tp_call;
    reprfunc tp_str;
    getattrofunc tp_getattro;
    setattrofunc tp_setattro;

    /* Functions to access object as input/output buffer */
    PyBufferProcs *tp_as_buffer;

    /* Flags to define presence of optional/expanded features */
    unsigned long tp_flags;

    const char *tp_doc; /* Documentation string */

    /* Assigned meaning in release 2.0 */
    /* call function for all accessible objects */
    traverseproc tp_traverse;

    /* delete references to contained objects */
    inquiry tp_clear;

    /* Assigned meaning in release 2.1 */
    /* rich comparisons */
    richcmpfunc tp_richcompare;

    /* weak reference enabler */
    Py_ssize_t tp_weaklistoffset;

    /* Iterators */
    getiterfunc tp_iter;
    iternextfunc tp_iternext;

    /* Attribute descriptor and subclassing stuff */
    struct PyMethodDef *tp_methods;
    struct PyMemberDef *tp_members;
    struct PyGetSetDef *tp_getset;
    struct _typeobject *tp_base;
    PyObject *tp_dict;
    descrgetfunc tp_descr_get;
    descrsetfunc tp_descr_set;
    Py_ssize_t tp_dictoffset;
    initproc tp_init;
    allocfunc tp_alloc;
    newfunc tp_new;
    freefunc tp_free; /* Low-level free-memory routine */
    inquiry tp_is_gc; /* For PyObject_IS_GC */
    PyObject *tp_bases;
    PyObject *tp_mro; /* method resolution order */
    PyObject *tp_cache;
    PyObject *tp_subclasses;
    PyObject *tp_weaklist;
    destructor tp_del;

    /* Type attribute cache version tag. Added in version 2.6 */
    unsigned int tp_version_tag;

    destructor tp_finalize;
    vectorcallfunc tp_vectorcall;
};
```

A type determines how the objects of that type behave. Each `tp_*` member of a type, called slot, is responsible for a particular aspect of the object's behavior. Here's some examples:

* `tp_new` is a pointer to a function that creates new objects of the type.
* `tp_str` is a pointer to a function that implements  `str()` for objects of the type.
* `tp_hash` is a pointer to a function that implements  `hash()` for objects of the type.

Some slots are grouped together in structs. For example, the `PySequenceMethods` struct contains the slots that implement the sequence protocol:

```C
typedef struct {
    lenfunc sq_length;
    binaryfunc sq_concat;
    ssizeargfunc sq_repeat;
    ssizeargfunc sq_item;
    void *was_sq_slice;
    ssizeobjargproc sq_ass_item;
    void *was_sq_ass_slice;
    objobjproc sq_contains;

    binaryfunc sq_inplace_concat;
    ssizeargfunc sq_inplace_repeat;
} PySequenceMethods;
```



