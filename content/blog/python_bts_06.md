Title: Python behind the scenes #6: how Python object system works
Date: 2020-11-21 5:18
Tags: Python behind the scenes, Python, CPython

As we know from the previous parts of this series, the execution of a Python program consists of two major steps:

1. The CPython compiler translates Python code to bytecode.
2. The CPython VM executes the bytecode.

We've been focusing on the second step for quite a while. In part 4 we've looked at the evaluation loop, a place where the bytecode gets executed. And in part 5 we've studied how the VM executes the instructions that are used to implement variables. What we haven't covered yet is how the VM actually computes something. We postponed this question because to answer it, we first need to understand how the most fundamental part of the language works. Today, we'll study the Python object system.

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

CPython solves this problem by representing everything in the language as a Python object (hence the phrase "Everything in Python is an object"). So, the VM needs to work only with Python objects, and all values the VM stores on the value stack are pointers to Python objects. The VM doesn't know how to add integers or floats but it knows that any Python object has a type. A type, in turn, knows everything about objects of that type. The `int` type knows how to add integers, and the `float` type knows how to add floats. So, the VM asks the type to perform the operation.

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

Some slots, called sub-slots, are grouped together in structs. For example, the `PySequenceMethods` struct contains the sub-slots that implement the sequence protocol:

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

A type has a lot of slots (and each slots is very well [documented](https://docs.python.org/3/c-api/typeobj.html) in the docs). Among these slots, there should be a slot that performs the addition. After careful inspection of the `PyTypeObject` struct, we find that its `tp_as_number` field points to a group of number-related slots. One of these slots is a binary function called `nb_add`:

```C
typedef struct {
    binaryfunc nb_add; // definition of "binaryfunc":
                       // typedef PyObject * (*binaryfunc)(PyObject *, PyObject *);
    binaryfunc nb_subtract;
    binaryfunc nb_multiply;
    binaryfunc nb_remainder;
    binaryfunc nb_divmod;
    // ... more sub-slots
} PyNumberMethods;
```

It seems that `nb_add` is what we're looking for. Let's see now how the `BINARY_ADD` opcode is implemented and find out if the VM indeed calls `nb_add` to add objects.

## BINARY_ADD

Like any other opcode, `BINARY_ADD` is implemented in the evaluation loop in [`Python/ceval.c`](https://github.com/python/cpython/blob/3.9/Python/ceval.c#L1684):

```C
case TARGET(BINARY_ADD): {
    PyObject *right = POP();
    PyObject *left = TOP();
    PyObject *sum;
    /* NOTE(haypo): Please don't try to micro-optimize int+int on
        CPython using bytecode, it is simply worthless.
        See http://bugs.python.org/issue21955 and
        http://bugs.python.org/issue10044 for the discussion. In short,
        no patch shown any impact on a realistic benchmark, only a minor
        speedup on microbenchmarks. */
    if (PyUnicode_CheckExact(left) &&
                PyUnicode_CheckExact(right)) {
        sum = unicode_concatenate(tstate, left, right, f, next_instr);
        /* unicode_concatenate consumed the ref to left */
    }
    else {
        sum = PyNumber_Add(left, right);
        Py_DECREF(left);
    }
    Py_DECREF(right);
    SET_TOP(sum);
    if (sum == NULL)
        goto error;
    DISPATCH();
}
```

That's an interesting peice of code. We can see that it calls `PyNumber_Add()` to add two objects, but if the objects are strings, it calls `unicode_concatenate()` instead. Why so? This is an optimization. Python strings seem immutable, but sometimes CPython mutates a string and thus avoids creating a new string. Consider appending one string to another:

```python
output += some_string
```

If the `output ` variable points to a string that has no other references, it's safe to mutate that string. This what `unicode_concatenate()` does.

It might be tempting to handle other special cases in the evaluation loop as well and optimize, for example, integers and floats. The comment explicitly warns against it. The problem is that a new special case comes with an additional check, and this check is only usefull when it succeeds. Otherwise, it may have a negative effect on performance. 

After this little digression, let's look at `PyNumber_Add()`. We find this function in [`Objects/abstract.c`](https://github.com/python/cpython/blob/3.9/Objects/abstract.c#L1016):

```C
PyObject *
PyNumber_Add(PyObject *v, PyObject *w)
{
  	// NB_SLOT(nb_add) expands to "offsetof(PyNumberMethods, nb_add)"
    PyObject *result = binary_op1(v, w, NB_SLOT(nb_add));
    if (result == Py_NotImplemented) {
        PySequenceMethods *m = Py_TYPE(v)->tp_as_sequence;
        Py_DECREF(result);
        if (m && m->sq_concat) {
            return (*m->sq_concat)(v, w);
        }
        result = binop_type_error(v, w, "+");
    }
    return result;
}
```

Let's first step into `binary_op1()` and figure out what `PyNumber_Add()` does later:

```C
static PyObject *
binary_op1(PyObject *v, PyObject *w, const int op_slot)
{
    PyObject *x;
    binaryfunc slotv = NULL;
    binaryfunc slotw = NULL;

    if (Py_TYPE(v)->tp_as_number != NULL)
        slotv = NB_BINOP(Py_TYPE(v)->tp_as_number, op_slot);
    if (!Py_IS_TYPE(w, Py_TYPE(v)) &&
        Py_TYPE(w)->tp_as_number != NULL) {
        slotw = NB_BINOP(Py_TYPE(w)->tp_as_number, op_slot);
        if (slotw == slotv)
            slotw = NULL;
    }
    if (slotv) {
        if (slotw && PyType_IsSubtype(Py_TYPE(w), Py_TYPE(v))) {
            x = slotw(v, w);
            if (x != Py_NotImplemented)
                return x;
            Py_DECREF(x); /* can't do it */
            slotw = NULL;
        }
        x = slotv(v, w);
        if (x != Py_NotImplemented)
            return x;
        Py_DECREF(x); /* can't do it */
    }
    if (slotw) {
        x = slotw(v, w);
        if (x != Py_NotImplemented)
            return x;
        Py_DECREF(x); /* can't do it */
    }
    Py_RETURN_NOTIMPLEMENTED;
}
```

The `binary_op1()` function takes an offset of a number slot as a parameter (in our case, the slot is `nb_add`). Then it gets the corresponding slots of both operands and implements essentialy the following logic:

1. If the type of one operand is a subtype of another, call the slot of the subtype.

2. If the left operand doesn't have the slot, call the slot of the right operand.

3. Otherwise, call the slot of the left operand.

The reason to always call the slot of a subtype is to allow the subtypes to override the behaviour of their ancestors:

```pycon
$ python -q
>>> class HungryInt(int):
...     def __add__(self, o):
...         return self
...
>>> x = HungryInt(5)
>>> x + 2
5
>>> 2 + x
7
>>> HungryInt.__radd__ = lambda self, o: self
>>> 2 + x
5
```

Let's turn back to `PyNumber_Add()`. If `binary_op1()` succeeds, `PyNumber_Add()` simply returns the result of `binary_op1()`. If `binary_op1()` returns the [`NotImplemented`](https://docs.python.org/3/library/constants.html#NotImplemented) constant, which means that the operation cannot be performed for a given combination of types, `PyNumber_Add()` tries to call the `sq_concat` sequence slot of the first operand and returns the result of this call:

```C
PySequenceMethods *m = Py_TYPE(v)->tp_as_sequence;
if (m && m->sq_concat) {
    return (*m->sq_concat)(v, w);
}
```

A type can support the `+` operator either by defining `nb_add` or by defining `sq_concat`. These slots have  different semantics:

* `nb_add` means algebraic addition with properties like `a + b = b + a`.
* `sq_concat` means the concatenation of sequences.

Built-in types such as `int` and `float` implement `nb_add`, and built-in types such as `str` and `list` implement `sq_concat`. Technically, there's no much difference. The main reason to choose one slot over another is to indicate the appropriate meaning. In fact, the `sq_concat` slot is so unnecessary that it's set to `NULL` for all user-defined types (i.e. classes).

We assured ourselves that the VM calls the `nb_add` slot to perfrom the addition. Let's see now how different types implement this slot.

## How slots are set

The way the slots of a type are set depends on how that type is created. There are two ways to create a type object:

* by statically defining it; or
* by dynamically allocating it.

### Statically defined types

An example of a statically defined type is any built-in type. Here's, for instance, how CPython defines the `float` type:

```C
PyTypeObject PyFloat_Type = {
    PyVarObject_HEAD_INIT(&PyType_Type, 0)
    "float",
    sizeof(PyFloatObject),
    0,
    (destructor)float_dealloc,                  /* tp_dealloc */
    0,                                          /* tp_vectorcall_offset */
    0,                                          /* tp_getattr */
    0,                                          /* tp_setattr */
    0,                                          /* tp_as_async */
    (reprfunc)float_repr,                       /* tp_repr */
    &float_as_number,                           /* tp_as_number */
    0,                                          /* tp_as_sequence */
    0,                                          /* tp_as_mapping */
    (hashfunc)float_hash,                       /* tp_hash */
    0,                                          /* tp_call */
    0,                                          /* tp_str */
    PyObject_GenericGetAttr,                    /* tp_getattro */
    0,                                          /* tp_setattro */
    0,                                          /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,   /* tp_flags */
    float_new__doc__,                           /* tp_doc */
    0,                                          /* tp_traverse */
    0,                                          /* tp_clear */
    float_richcompare,                          /* tp_richcompare */
    0,                                          /* tp_weaklistoffset */
    0,                                          /* tp_iter */
    0,                                          /* tp_iternext */
    float_methods,                              /* tp_methods */
    0,                                          /* tp_members */
    float_getset,                               /* tp_getset */
    0,                                          /* tp_base */
    0,                                          /* tp_dict */
    0,                                          /* tp_descr_get */
    0,                                          /* tp_descr_set */
    0,                                          /* tp_dictoffset */
    0,                                          /* tp_init */
    0,                                          /* tp_alloc */
    float_new,                                  /* tp_new */
};
```

The slots of a statically defined type are specified explicitly. We can easily see how the `float` type implements `nb_add` by looking at the number slots:

```C
static PyNumberMethods float_as_number = {
    float_add,          /* nb_add */
    float_sub,          /* nb_subtract */
    float_mul,          /* nb_multiply */
    // ... more number slots
};
```

where we find `float_add`, a straightforward implementation:

```C
static PyObject *
float_add(PyObject *v, PyObject *w)
{
    double a,b;
    CONVERT_TO_DOUBLE(v, a);
    CONVERT_TO_DOUBLE(w, b);
    a = a + b;
    return PyFloat_FromDouble(a);
}
```

The floating-point arithmetic is not that important for our discussion. What's important is that we learned how the VM evaluates the expression `x + 7` when the type of `x` is a built-in type and, furthermore, we learned how the behaviour of a built-in type is specified.

### Dynamically allocated types

Python allows programmers to define their own types using the `class` statement. A Python class is just a dynamically allocated instance of `PyTypeObject`. To see this, let's define a simple class:

```python
class A:
    pass
```

The compiler translates this class definition to the following bytecode:

```text
$ python -m dis class.py      
  1           0 LOAD_BUILD_CLASS
              2 LOAD_CONST               0 (<code object A at 0x108d82240, file "class.py", line 1>)
              4 LOAD_CONST               1 ('A')
              6 MAKE_FUNCTION            0
              8 LOAD_CONST               1 ('A')
             10 CALL_FUNCTION            2
             12 STORE_NAME               0 (A)
...
```

And here's what this bytecode does:

1. `LOAD_BUILD_CLASS` pushes the  `__build_class__()` function from the `builtins` module onto the stack.
2. `MAKE_FUNCTION` takes the code object of the class, turns it into a function and pushes this function onto the stack.
3. `CALL_FUNCTION` calls `__build_class__()` with two arguments: the function from the previous step and the name of the class. The result of this call is a class that is pushed onto the stack.
4. `STORE_NAME` pops the class from the stack and stores it under the name `A`.

The job of the `__build_class__()` is to find the right metatype and then call this metatype with appropriate arguments to create a class. A metatype is a type whose instances are types. An example of a metatype is `PyType_Type`, known in Python as `type`. This metatype is the type of all built-in types and the default type for classes. The type of `type` is `type` itself. The following example demonstrates the point:

```pycon
$ python -q
>>> type(1)
<class 'int'>
>>> type(int)
<class 'type'>
>>> type(type)
<class 'type'>
>>> 
>>> class A: pass
... 
>>> type(A)
<class 'type'>
```

A metatype determines the behavior of types. In particular, it's responsible for the creation of classes. To create a new class, we call a metatype with three arguments:

1. the name of a class
2. a tuple of its bases
3. its namespace.

Bases are types from which a class inherits. If bases are not specified, `PyBaseObject_Type`, known in Python as `object`, is used as a base. Every Python type directly or indirectly inherits from `object`. The `object` type implements the behavior that every Python type is expected to have. For example, it implements `tp_alloc`, `tp_init` and `tp_repr` slots.

A namespace is a dictionary that serves as a prototype for the dictionary of a class. To populate the namespace, `__build_class__()` executes the class body, which it got as the first parameter, in the namespace. The names defined in the class body later become attributes of the class. Typically, a namespace starts as an empty dictionary, but if the metatype implements the [`__prepare__`](https://docs.python.org/3/reference/datamodel.html#preparing-the-class-namespace) method, this method is called to prepare the namespace.

Let's summarize what `__build_class__()` does:

1. It determines the metatype that will be used to create a class.
2. It initializes the empty namespace or calls metatype's `__prepare__`.
3. It executes the body of the class in the namespaces.
4. It calls the metatype to create the class.

Python allows to specifiy which metatype should be used to create a class with the `metaclass` keyword:

```python
class A(metaclass=MyMetatype):
  pass
```

How exactly `__build_class__()` determines the metatype is nicely [described](https://docs.python.org/3/reference/datamodel.html#determining-the-appropriate-metaclass) in the docs:

> The appropriate metaclass for a class definition is determined as follows:
>
> - if no bases and no explicit metaclass are given, then [`type()`](https://docs.python.org/3/library/functions.html#type) is used;
> - if an explicit metaclass is given and it is *not* an instance of [`type()`](https://docs.python.org/3/library/functions.html#type), then it is used directly as the metaclass;
> - if an instance of [`type()`](https://docs.python.org/3/library/functions.html#type) is given as the explicit metaclass, or bases are defined, then the most derived metaclass is used.
>
> The most derived metaclass is selected from the explicitly specified metaclass (if any) and the metaclasses (i.e. `type(cls)`) of all specified base classes. The most derived metaclass is one which is a subtype of *all* of these candidate metaclasses. If none of the candidate metaclasses meets that criterion, then the class definition will fail with `TypeError`.

As we can see the metatype defaults to `type`. So, typically, `__build_class__()` calls `type` to create a class. A Python object is callable when its type implements the `tp_call` slot. The type of `type` is `type` itself, and its `tp_call` slot points to the `type_call()` function. This function is invoked when we call any type whose metatype is `type`, not just `type` itself, that is, when we call `type()`, `str()`, `list()` or `MyClass()`. The result of such a call is a new object of the called type.

What `type_call` does is essentialy two things:

1. It calls `tp_new` of a type to create an object.
2. It calls `tp_init` of a type to initialize the created object.

The `tp_new` slot of `type` points to the `type_new()` function. This is the function that creates classes. The `tp_init` slot of `type` points to the function that does nothing, so all the work is done by `type_new()`. The `type_new()` function is nearly 500 lines long and probably deserves a separate post. Recall that we started our disscussion about classes because we wanted to understand how their slots are set, in particular, the `nb_add` slot. So, for now, let's concentrate on this issue.

What `type_new()` does can roughly be summarized as follows:

1. Allocate `PyHeapTypeObject`.
2. Set type's slots.

`PyHeapTypeObject` is a struct that extends `PyTypeObject`. It contains `PyTypeObject` as well as structs with sub-slots:

```C
/* The *real* layout of a type object when allocated on the heap */
typedef struct _heaptypeobject {
    PyTypeObject ht_type;
    PyAsyncMethods as_async;
    PyNumberMethods as_number;
    PyMappingMethods as_mapping;
    PySequenceMethods as_sequence;
    PyBufferProcs as_buffer;
    PyObject *ht_name, *ht_slots, *ht_qualname;
    struct _dictkeysobject *ht_cached_keys;
    PyObject *ht_module;
    /* here are optional user slots, followed by the members. */
} PyHeapTypeObject;
```

`PyTypeObject` doesn't contain structs with sub-slots, only pointers to them, so it makes sense to have `PyHeapTypeObject` to allocate everything at once.

The next step is to set the slots of the allocated type. What would you expect `nb_add` of a class to be? We know that we can define special methods such as `__add__()` and `__radd__()` to specify how to add objects of a class. But what's the connection between special methods and slots? That's the ultimate question of our investigation.

## Special methods and slots

It turns out that CPython keeps a mapping between special methods and slots. This mapping is represented by an array of `slotdef` structs. Each `slotdef` struct contains the name of a special method, the offset of the corresponding slot in the `PyHeapTypeObject` struct, a poiner to the slot's default function and some other things:

```C
// typedef struct wrapperbase slotdef;

struct wrapperbase {
    const char *name;
    int offset;
    void *function;
    wrapperfunc wrapper;
    const char *doc;
    int flags;
    PyObject *name_strobj;
};
```

And here's how the mapping is defined:

```C
#define TPSLOT(NAME, SLOT, FUNCTION, WRAPPER, DOC) \
    {NAME, offsetof(PyTypeObject, SLOT), (void *)(FUNCTION), WRAPPER, \
     PyDoc_STR(DOC)}

static slotdef slotdefs[] = {
  TPSLOT("__getattribute__", tp_getattr, NULL, NULL, ""),
  TPSLOT("__getattr__", tp_getattr, NULL, NULL, ""),
  TPSLOT("__setattr__", tp_setattr, NULL, NULL, ""),
  TPSLOT("__delattr__", tp_setattr, NULL, NULL, ""),
  TPSLOT("__repr__", tp_repr, slot_tp_repr, wrap_unaryfunc,
         "__repr__($self, /)\n--\n\nReturn repr(self)."),
  TPSLOT("__hash__", tp_hash, slot_tp_hash, wrap_hashfunc,
         "__hash__($self, /)\n--\n\nReturn hash(self)."),
  // ... more slotdefs
}

```

This is not a one-to-one mapping. For example, both `__add__()` and `__radd__()` special methods map to the same `nb_add` slot. Conversely, both the `mp_subscript` mapping slot and the `sq_item` sequence slot map to the same `__getitem__()` special method.

CPython uses the `slotdefs` array to set the slots of a class. The `type_new()` function calls `fixup_slot_dispatchers()` to do that. The latter calls `update_one_slot()` for each struct in `slotdefs`. This function looks up the special method corresponding to struct's `name` in the class. For example, if struct's `name` is `"__add__"`, it looks up `A.__add__`. If it finds such a method, it sets the slot specified by struct's `offset` to the function specified by struct's `function`.

Let's see how the `nb_add` slot is set. It corresponds to the following `slotdefs` entries:

```C
static slotdef slotdefs[] = {
    // ...
    BINSLOT("__add__", nb_add, slot_nb_add, "+"),
    RBINSLOT("__radd__", nb_add, slot_nb_add,"+"),
    // ...
}
```

that expand to:

```C
static slotdef slotdefs[] = {
    // ...
    // {name, offset, function,
  	//     wrapper, doc}
  	// 
    {"__add__", offsetof(PyHeapTypeObject, as_number.nb_add), (void *)(slot_nb_add),
        wrap_binaryfunc_l, PyDoc_STR("__add__" "($self, value, /)\n--\n\nReturn self" "+" "value.")},

    {"__radd__", offsetof(PyHeapTypeObject, as_number.nb_add), (void *)(slot_nb_add),
        wrap_binaryfunc_r, PyDoc_STR("__radd__" "($self, value, /)\n--\n\nReturn value" "+" "self.")},
    // ...
}
```

What's important here is that `function` of both entries is `slot_nb_add()`. When we define the `__add__()` method on a class, `update_one_slot()` finds it and sets the `nb_add` slot of the class to the `slot_nb_add()` function. Similarly, when we define the `__radd__()` method, `update_one_slot()` sets `nb_add` to `slot_nb_add()` as well. Note that when several special methods map to the same slot, they must agree an `function`.

Now, what is `slot_nb_add()`, you ask? This function is defined with a macro that expands as follows:

```C
static PyObject *
slot_nb_add(PyObject *self, PyObject *other) {
    PyObject* stack[2];
    PyThreadState *tstate = _PyThreadState_GET();
    _Py_static_string(op_id, "__add__");
    _Py_static_string(rop_id, "__radd__");
    int do_other = !Py_IS_TYPE(self, Py_TYPE(other)) && \
        Py_TYPE(other)->tp_as_number != NULL && \
        Py_TYPE(other)->tp_as_number->nb_add == slot_nb_add;
    if (Py_TYPE(self)->tp_as_number != NULL && \
        Py_TYPE(self)->tp_as_number->nb_add == slot_nb_add) {
        PyObject *r;
        if (do_other && PyType_IsSubtype(Py_TYPE(other), Py_TYPE(self))) {
            int ok = method_is_overloaded(self, other, &rop_id);
            if (ok < 0) {
                return NULL;
            }
            if (ok) {
                stack[0] = other;
                stack[1] = self;
                r = vectorcall_maybe(tstate, &rop_id, stack, 2);
                if (r != Py_NotImplemented)
                    return r;
                Py_DECREF(r); do_other = 0;
            }
        }
        stack[0] = self;
        stack[1] = other;
        r = vectorcall_maybe(tstate, &op_id, stack, 2);
        if (r != Py_NotImplemented || Py_IS_TYPE(other, Py_TYPE(self)))
            return r;
        Py_DECREF(r);
    }
    if (do_other) {
        stack[0] = other;
        stack[1] = self;
        return vectorcall_maybe(tstate, &rop_id, stack, 2);
    }
    Py_RETURN_NOTIMPLEMENTED;
}
```

You don't need to study this code carefully. It basicaly repeats the logic of its caller, `binary_op1()`. The main difference is that `slot_nb_add()` eventually calls `__add__()` or `__radd__()  ` special method.

Now we know how the VM evaluates the expression `x + 7` when `x` is an instance of a class that defines `__add__()`:

1. The VM calls `binary_op1()`.
2. `binary_op1()` calls `slot_nb_add()`.
3. `slot_nb_add()` calls `__add__()`.

We've answered the question we started with. But, as it often happens, the answer gives rise to even more questions. Our goal for the rest of this post is to tackle those.

## Setting special method on existing class

Suppose that we create a class without `__add__()` and `__radd__()` methods. In this case, the `nb_add` slot of the class is set to `NULL`. As expected, we cannot add instances of that class. If we, however, update the class by setting `__add__()` or `__radd__()`, the addition works as if the method was a part of the class definition. Here's what I mean:

```pycon
$ python -q
>>> class A:
...     pass
... 
>>> x = A()
>>> x + 2
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
TypeError: unsupported operand type(s) for +: 'A' and 'int'
>>> A.__add__ = lambda self, o: 5
>>> x + 2
5
>>> 
```

How does that work? To set an attribute on an object, the VM calls the `tp_setattro` slot of the object's type. The `tp_setattro` slot of `type` points to the `type_setattro()` function, so, when we set an attribute on a class, this function gets called. To set an attribute, it stores the value of the attribute in the class's dictionary and, if the attribute is a special method, it sets the corresponding slots. It basically calls the same `update_one_slot()` function.

## Inheritance

When we define a class that inherits from other type, we expect the class to inherit some behavior of that type. For example, when we define a class  that inherits from `int`, we expect it to support the addition:

```pycon
$ python -q
>>> class MyInt(int):
...     pass
... 
>>> x = MyInt(2)
>>> y = MyInt(4)
>>> x + y
6
```

Does `MyInt` inherit `nb_add` of `int`? How is that implemented? The `type_new()` function recieves a tuple of bases that we specified. Since bases, in turn, may inherit from other types, all these ancestor types combined form an hierarchy. An hierarchy, hovewer, doesn't specify the order of inheritance, so `type_new()` converts this hierarchy into a list. [The Method Resolution Order](https://www.python.org/download/releases/2.3/mro/) (MRO) determines how to perform this conversion. Once the MRO is calculated, it's trivial to implement the inheritance. The `type_new()` function iterates over ancestors according to the MRO. From each ancestor, it copies those slots that haven't been set on the type before. Some slots support the inheritence and some don't. You can check in [the docs](https://docs.python.org/3/c-api/typeobj.html#type-objects) whether a particular slot is inherited or not.

If no bases were specified, `type_new()` assumes that `object` is the only base. This is why all Python types directly or indirectly inherit from `object`.

## Attributes



