Title: Python behind the scenes #7: how Python attributes work
Date: 2020-12-15 6:25
Tags: Python behind the scenes, Python, CPython

What happens when we get or set an attribute of a Python object? This question is not as simple as it may seem at first. It's true that any experienced Python programmer has a good intuitive understanding of how attributes work, and the documentation helps a lot to strengthen the understanding. Yet, when a really non-trivial question regarding attributes comes up, the intuition fails and the documentation can no longer help. Even a question as basic as "What is an attribute?" fits into that category. To gain a deep understanding and be able to answer such questions, one has to study how attributes are implemented. That's what we're going to do today.

## A brief recall

Last time we studied how the Python object system works. Some of the things we've learned in that part are crucial for our current disscussion, so let's recall them briefly.

A Python object is an instance of a C struct that has at least two members:

* a reference count; and
* a pointer to the object's type.

Every object must have a type because the type determines how the object behaves. A type is also a Python object, an instance of the `PyTypeObject` struct:

```C
// PyTypeObject is a typedef for "struct _typeobject"

struct _typeobject {
    PyVarObject ob_base; // expansion of PyObject_VAR_HEAD macro
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

The members of a type are called slots. Each slot is responsible for a particular aspect of the object's behavior. For example, the ` tp_call` slot of a type specifies what happens when we call the object of that type. Some slots are grouped together in suites. An example of a suite is the "number" suite `tp_as_number`. Last time we studied its `nb_add` slot that specifies how to add objects. This and all other slots are very well [described](https://docs.python.org/3/c-api/typeobj.html) in the docs.

How slots of a type are set depends on how the type is defined. There are two ways to define a type in CPython:

* statically; or
* dynamically.

A statically defined type is just a statically initialized instance of `PyTypeObject`. All built-in types are defined statically. Here's, for example, the definition of the `float` type:

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

To dynamically allocate a new type, we call a metatype. A metatype is a type whose instances are types. It determines how types behave. In particular, it creates new type instances. Python has one built-in metatype known as `type`. It's the metatype of all built-in types. It's also used as the default metatype to create classes. When CPython executes the `class` statement, it typically calls `type()` to create the class. We can create a class by calling `type()` directly:

```python
MyClass = type(name, bases, namespace)
```

Slots of a statically defined type are specified explicitly. Slots of a class are set automatically by the metatype. Some slots are mapped to special methods. Last time we studied how a slot is set when the corresponding special method is defined. Both statically and dynamically defined types can inherit some slots from its bases.

Let's turn our attention to attrubutes.

## Attributes and the VM

What is an attribute? We might say that an attribute is a variable associated with an object, but it's more than that. It's hard to give a definition that captures all important aspects of attributes. So, instead of starting with a definition, let's start with something we know for sure.

We know for sure that in Python we can do three things with attributes:

* get the value of an attribute: `value = obj.attr`
* set an attribute to some value: `obj.attr = value`
* delete an attribute: `del obj.attr`

What these operations do depends, like any other aspect of the object's behavior, on the object's type. A type has certain slots responsible for getting, setting and deleting attributes. The VM calls these slots to execute the statements we listed above. To see what these slots are and how the VM calls them, let's apply the familiar method:

1. Write a piece of code that gets/sets/deletes an attribute.
2. Disassemble it to bytecode using the [`dis`](https://docs.python.org/3/library/dis.html) module.
3. Take a look at the implementation of the produced bytecode instructions in [`ceval.c`](https://github.com/python/cpython/blob/3.9/Python/ceval.c).

### Getting an attribute

Let's first see what the VM does when we get the value of an attribute. The compiler produces the `LOAD_ATTR` opcode to load the value:

```text
$ echo 'obj.attr' | python -m dis
  1           0 LOAD_NAME                0 (obj)
              2 LOAD_ATTR                1 (attr)
...
```

And the VM executes this opcode as follows:

```C
case TARGET(LOAD_ATTR): {
    PyObject *name = GETITEM(names, oparg);
    PyObject *owner = TOP();
    PyObject *res = PyObject_GetAttr(owner, name);
    Py_DECREF(owner);
    SET_TOP(res);
    if (res == NULL)
        goto error;
    DISPATCH();
}
```

We can see that the VM calls the `PyObject_GetAttr()` function to do the job. Here's what it does:

```C
PyObject *
PyObject_GetAttr(PyObject *v, PyObject *name)
{
    PyTypeObject *tp = Py_TYPE(v);

    if (!PyUnicode_Check(name)) {
        PyErr_Format(PyExc_TypeError,
                     "attribute name must be string, not '%.200s'",
                     Py_TYPE(name)->tp_name);
        return NULL;
    }
    if (tp->tp_getattro != NULL)
        return (*tp->tp_getattro)(v, name);
    if (tp->tp_getattr != NULL) {
        const char *name_str = PyUnicode_AsUTF8(name);
        if (name_str == NULL)
            return NULL;
        return (*tp->tp_getattr)(v, (char *)name_str);
    }
    PyErr_Format(PyExc_AttributeError,
                 "'%.50s' object has no attribute '%U'",
                 tp->tp_name, name);
    return NULL;
}
```

This function first tries to call the `tp_getattro` slot of the object's type. If this slot is not defined, it tries to call the `tp_getattr` slot. If `tp_getattr` is not defined either, it raises `AttributeError`.

A type defines `tp_getattro` or `tp_getattr` or both to support attribute access. [According to the documentation](https://docs.python.org/3/c-api/typeobj.html#c.PyTypeObject.tp_getattr), the only difference between them is that `tp_getattro` takes a Python string as the name of an attribute and `tp_getattr` takes a C string. Though the choice exists, you won't find types in CPython that implement `tp_getattr`. This slot has been deprecated in favor of `tp_getattro`.

### Setting an attribute

From the VM's perspective, setting an attribute is not much different from getting it. The compiler produces the `STORE_ATTR` opcode to set an attribute to some value:

```text
$ echo 'obj.attr = value' | python -m dis
  1           0 LOAD_NAME                0 (value)
              2 LOAD_NAME                1 (obj)
              4 STORE_ATTR               2 (attr)
...
```

The VM executes `STORE_ATTR` as follows:

```C
case TARGET(STORE_ATTR): {
    PyObject *name = GETITEM(names, oparg);
    PyObject *owner = TOP();
    PyObject *v = SECOND();
    int err;
    STACK_SHRINK(2);
    err = PyObject_SetAttr(owner, name, v);
    Py_DECREF(v);
    Py_DECREF(owner);
    if (err != 0)
        goto error;
    DISPATCH();
}
```

We find that `PyObject_SetAttr()` is the function that does the job:

```C
int
PyObject_SetAttr(PyObject *v, PyObject *name, PyObject *value)
{
    PyTypeObject *tp = Py_TYPE(v);
    int err;

    if (!PyUnicode_Check(name)) {
        PyErr_Format(PyExc_TypeError,
                     "attribute name must be string, not '%.200s'",
                     Py_TYPE(name)->tp_name);
        return -1;
    }
    Py_INCREF(name);

    PyUnicode_InternInPlace(&name);
    if (tp->tp_setattro != NULL) {
        err = (*tp->tp_setattro)(v, name, value);
        Py_DECREF(name);
        return err;
    }
    if (tp->tp_setattr != NULL) {
        const char *name_str = PyUnicode_AsUTF8(name);
        if (name_str == NULL) {
            Py_DECREF(name);
            return -1;
        }
        err = (*tp->tp_setattr)(v, (char *)name_str, value);
        Py_DECREF(name);
        return err;
    }
    Py_DECREF(name);
    _PyObject_ASSERT(name, Py_REFCNT(name) >= 1);
    if (tp->tp_getattr == NULL && tp->tp_getattro == NULL)
        PyErr_Format(PyExc_TypeError,
                     "'%.100s' object has no attributes "
                     "(%s .%U)",
                     tp->tp_name,
                     value==NULL ? "del" : "assign to",
                     name);
    else
        PyErr_Format(PyExc_TypeError,
                     "'%.100s' object has only read-only attributes "
                     "(%s .%U)",
                     tp->tp_name,
                     value==NULL ? "del" : "assign to",
                     name);
    return -1;
}
```

This function calls the `tp_setattro` and `tp_setattr` slots the same way as `PyObject_GetAttr()` calls `tp_getattro` and `tp_getattr`. The `tp_setattro` slot comes in pair with `tp_getattro`, and `tp_setattr` comes in pair with `tp_getattr`. Just like `tp_getattr`, `tp_setattr` is deprecated.

Note that `PyObject_SetAttr()` checks whether a type defines `tp_getattro` or `tp_getattr`. A type must implement attribute access to support attribute assignment.

### Deleting an attribute

Interestingly, a type has no special slot for deleting an attribute. What then specifies how to delete an attribute? Let's see. The compiler produces the `DELETE_ATTR` opcode to delete the attribute:

```text
$ echo 'del obj.attr' | python -m dis
  1           0 LOAD_NAME                0 (obj)
              2 DELETE_ATTR              1 (attr)
```

The way the VM executes this opcode reveals the answer:

```C
case TARGET(DELETE_ATTR): {
    PyObject *name = GETITEM(names, oparg);
    PyObject *owner = POP();
    int err;
    err = PyObject_SetAttr(owner, name, (PyObject *)NULL);
    Py_DECREF(owner);
    if (err != 0)
        goto error;
    DISPATCH();
}
```

To delete an attribute, the VM calls the same `PyObject_SetAttr()` function that it calls to set an attribute. The `NULL` value indicates that the attribute should be deleted.

In this section we've learned that the `tp_getattro` and `tp_setattro` slots determine how attributes of an object work. The next question that comes to mind is: How are these slots implemented?

## Slots implementations

Any function of the appropriate signature can be an implementation of  `tp_getattro` and `tp_setattro`. A type can implement these slots in an absolutely arbitrary way. Fortunately, we need to study only a few implementations to understand how Python attributes work. This is because most types use the same generic implementation.

The generic functions for getting and setting attributes are  `PyObject_GenericGetAttr()` and `PyObject_GenericSetAttr()`. All classes use them by default. Most built-in types specify them as slots implementations exlicitly or inherit them from `object` that also uses the generic implementation.

In this post, we'll focus on the generic implementation, since it's basically what we mean when we think about Python attributes. And while we'll be talking about a single concrete implementation, keep in mind that theoretically `tp_getattro` and `tp_setattro` can be anything.

We'll also discuss two important cases when the generic implementation is not used. The first case is any class that customizes attribute access and assignment by implementing the `__getattribute__()`,  `__getattr__()`, `__setattr__()` and `__delattr__()` special methods. CPython sets the `tp_getattro` and `tp_setattro` slots of such a class to the functions that call those methods. The second case is `type`. It implements the `tp_getattro` and `tp_setattro` slots in its own way, though its implementation is quite similiar to the generic one. Attributes of types and attributes of ordinary objects work differently but not by much.

## Generic attribute management

The `PyObject_GenericGetAttr()` and `PyObject_GenericSetAttr()` functions implement the behavior of attributes that we're all accustomed to. When we set an attribute of an object to some value, CPython puts the value in the object's dictionary:

```pycon
$ python -q
>>> class A:
...     pass
... 
>>> a = A()
>>> a.__dict__
{}
>>> a.x = 'instance attribute'
>>> a.__dict__
{'x': 'instance attribute'}
```

When we try to get the value of the attribute, CPython loads it from the object's dictionary:

```pycon
>>> a.x
'instance attribute'
```

If the object's dictionary doesn't contain the attribute, CPython loads the value from the type's dictionary:

```pycon
>>> A.y = 'class attribute'
>>> a.y
'class attribute'
```

If the type's dictionary doesn't contain the attribute either, CPython searches for the value in the dictionaries of the parent types:

```pycon
>>> class B(A): # note the inheritance
...     pass
... 
>>> b = B()
>>> b.y
'class attribute'
```

As we can see, an attribute of an object is one of two things: 

* an instance variable; or
* a type variable.

Instance variables are stored in the object's dictionary, and type variables are stored in the type's dictionary and in the dictionaries of the parent types. To set an attribute to some value, CPython simply updates the object's dictionary. To get the value of an attribute, CPython searches for it first in the object's dictionary and then in the type's dictionary and in the dictionaries of the parent types. The order in which CPython iterates over the types when it searches for the value is [the Method Resolution Order](https://www.python.org/download/releases/2.3/mro/) (MRO).

### Descriptors

Python attributes would be as simple as that if there were no descriptors. Techically, a descriptor is a Python object whose type implements certain slots: `tp_descr_get` or `tp_descr_set` or both. Essentially, a descriptor is a Python object that, when used as an attribute, controls what happens we get, set or delete it. If `PyObject_GenericGetAttr()` finds that the value is a descriptor whose type implements the `tp_descr_get` slot, it doesn't just return the value as it normally does but calls `tp_descr_get` and returns the result of this call. The `tp_descr_get` slot recieves three parameters: the descriptor itself, the object whose attribute is being looked up and the object's type. It's up to `tp_descr_get` to decide what to do with the parameters and what to return. Similarly, `PyObject_GenericSetAttr()` looks up the current attribute value. If it finds that the value is a descriptor whose type implements `tp_descr_set`, it calls `tp_descr_set` instead of just updating the object's dictionary. The arguments passed to `tp_descr_set` are the descriptor, the object, and the new value to be assigned. When we delete an attribute, `PyObject_GenericSetAttr()` calls `tp_descr_set` with the new value set to `NULL`.

On one side, descriptors make Python attributes a bit complex. On the other side, descriptors make Python attributes powerful. As Python's glossary [says](https://docs.python.org/3/glossary.html#term-descriptor),

> Understanding descriptors is a key to a deep understanding of Python because they are the basis for many features including functions, methods, properties, class methods, static methods, and reference to super classes.

Indeed, we use descriptors all the time. Let's revise one important use case of descriptors that we discussed in the previous part: methods.

A function put in the type's dictionary works not like an ordinary function but like a method. That is, we don't need to explicitly pass the first argument when we call it:

```pycon
>>> A.f = lambda self: self
>>> a.f()
<__main__.A object at 0x108a20d60>
```

The `a.f` attribute not only works like a method, it is a method:

```pycon
>>> a.f
<bound method <lambda> of <__main__.A object at 0x108a20d60>>
```

However, if we look up the value of `'f'` in the type's dictionary, we'll get the original function:

```pycon
>>> A.__dict__['f']
<function <lambda> at 0x108a4ca60> 
```

CPython returns not the value stored in the dictionary but something else. This is because functions are descriptors. The `function` type implements the `tp_descr_get` slot, so `PyObject_GenericGetAttr()` calls this slot and returns the result. The result of the call is a method object that stores both the function and the instance. When we call a method object, the instance is prepended to the list of arguments and the function gets called.

Descriptors have their special behavior only when they are used as type variables. When they are used as instance variables, they behave like ordinary objects. For example, a function put in the object's dictionary does not become a method:

```pycon
>>> a.g = lambda self: self
>>> a.g
<function <lambda> at 0x108a4cc10>
```

Apparently, the language designers haven't found a case when using a descriptor as an instance variable would be a good idea. The consequence of this is that instance variables are very straightforward. They are just data.

The `function` type is an example of a built-in descriptor type. We can also define our own descriptors. To do that, we create a class that implements the descriptor protocol: the `__get__()`, `__set__()` and `__delete__()` special methods:

```pycon
>>> class DescrClass:
...     def __get__(self, obj, type=None):
...             print('I can do anything')
...             return self
...
>>> A.descr_attr = DescrClass()
>>> a.descr_attr 
I can do anything
<__main__.DescrClass object at 0x108b458e0>
```

If a class defines `__get__()`, CPython sets its `tp_descr_get` slot to the function that calls that method. If a class defines `__set__()` or `__delete__()`, CPython sets its `tp_descr_set` slot to the function that calls `__delete__()` when the value is `NULL` and calls `__set__()` otherwise.

If you wonder why anyone would want to define their our descriptors in the first place, check out the excellent [Descriptor HowTo Guide](https://docs.python.org/3/howto/descriptor.html#id1) by Raymond Hettinger.

Now, when we know what descriptors are, we're ready to study the algorithms for getting and setting attributes. However, since we're going to look at the actual code, we first need to understand where attributes are stored. That is, we need to understand what the object's and type's dictionaries really are.

### Object's and type's dictionaries

An object's dictionary is a dictionary in which instance variables are stored. A pointer to the object's dictionary is a member of the object. For example, a function object has the `func_dict` member that points to the function's dictionary:

```C
typedef struct {
    // ...
    PyObject *func_dict;        /* The __dict__ attribute, a dict or NULL */
    // ...
} PyFunctionObject;
```

To tell CPython which member of an object is the pointer to the object's dictionary, the object's type specifies an offset of this member using the `tp_dictoffset` slot. Here's how the `function` type does this:

```C
PyTypeObject PyFunction_Type = {
    // ...
    offsetof(PyFunctionObject, func_dict),      /* tp_dictoffset */
    // ... 
};
```

A positive value of `tp_dictoffset` specifies an offset from the start of the struct. A negative value specifies an offset from the end of the struct. The zero offset means that the object doesn't have the dictionary. For example, integers don't have dictionaries because `tp_dictoffset` of the `int` type is set to `0`:

```pycon
>>> (12).__dict__
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
AttributeError: 'int' object has no attribute '__dict__'
>>> int.__dictoffset__
0
```

Typically, classes have a non-zero `tp_dictoffset`. The only exception is classes that define the `__slots__` attribute. This attribute is an optimization. We'll cover the essentials first and disccus `__slots__` later.

A type's dictionary is a dictionary of a type object. Just like the `func_dict` member of a function points to the function's dictionary, the `tp_dict` slot of a type points to the type's dictionary. The crucial difference between the dictionary of an ordinary object and the dictionary of a type is that CPython knows about `tp_dict`, so it doesn't need to locate the dictionary of a type via `tp_dictoffset`. Since `tp_dictoffset` of `type` is unnecessary, it's set to `0`. Handling the type's dictionary in a general way would indroduce an additional level of indirection and, as we'll see, wouldn't bring much benefit.

Now, when we know what descriptors are and where attributes are stored, we're ready to see what the `PyObject_GenericGetAttr()` and `PyObject_GenericSetAttr()` functions do.

### PyObject_GenericSetAttr()

We begin with `PyObject_GenericSetAttr()`, a function whose job is set an attribute to a given value. This function turns out to be a thin wrapper around another function:

```C
int
PyObject_GenericSetAttr(PyObject *obj, PyObject *name, PyObject *value)
{
    return _PyObject_GenericSetAttrWithDict(obj, name, value, NULL);
}
```

And that function actually does the work:

```C
int
_PyObject_GenericSetAttrWithDict(PyObject *obj, PyObject *name,
                                 PyObject *value, PyObject *dict)
{
    PyTypeObject *tp = Py_TYPE(obj);
    PyObject *descr;
    descrsetfunc f;
    PyObject **dictptr;
    int res = -1;

    if (!PyUnicode_Check(name)){
        PyErr_Format(PyExc_TypeError,
                     "attribute name must be string, not '%.200s'",
                     Py_TYPE(name)->tp_name);
        return -1;
    }

    if (tp->tp_dict == NULL && PyType_Ready(tp) < 0)
        return -1;

    Py_INCREF(name);
		
    // Look up the current attribute value
  	// in the type's dict and its parents' dicts using the MRO.
    descr = _PyType_Lookup(tp, name);

  	// If found a descriptor that implements `tp_descr_set`, call this slot.
    if (descr != NULL) {
        Py_INCREF(descr);
        f = Py_TYPE(descr)->tp_descr_set;
        if (f != NULL) {
            res = f(descr, obj, value);
            goto done;
        }
    }

  	// `PyObject_GenericSetAttr()` calls us with `dict` set to `NULL`.
  	// So, `if` will be executed.
    if (dict == NULL) {
      	// Get the object's dict.
        dictptr = _PyObject_GetDictPtr(obj);
        if (dictptr == NULL) {
            if (descr == NULL) {
                PyErr_Format(PyExc_AttributeError,
                             "'%.100s' object has no attribute '%U'",
                             tp->tp_name, name);
            }
            else {
                PyErr_Format(PyExc_AttributeError,
                             "'%.50s' object attribute '%U' is read-only",
                             tp->tp_name, name);
            }
            goto done;
        }
      	// Update the object's dict with the new value.
      	// If `value` is `NULL`, delete the attribute from the dict.
        res = _PyObjectDict_SetItem(tp, dictptr, name, value);
    }
    else {
        Py_INCREF(dict);
        if (value == NULL)
            res = PyDict_DelItem(dict, name);
        else
            res = PyDict_SetItem(dict, name, value);
        Py_DECREF(dict);
    }
    if (res < 0 && PyErr_ExceptionMatches(PyExc_KeyError))
        PyErr_SetObject(PyExc_AttributeError, name);

  done:
    Py_XDECREF(descr);
    Py_DECREF(name);
    return res;
}
```

Despite its length, it implements a simple algorithm:

1. Search for the attribute value among type variables. The order of search is the MRO.
2. If the value is a descriptor whose type implements the `tp_descr_set` slot, call the slot.
3. Otherwise, update the object's dictionary with the new value.

We haven't discussed the descriptors that implement the `tp_descr_set` slot, so you may wonder why we need them at all. Consider Python's `property()`. The following example from the docs demostrates its canonical usage to create a managed attribute:

```python
class C:
    def __init__(self):
        self._x = None
    def getx(self):
        return self._x
    def setx(self, value):
        self._x = value
    def delx(self):
        del self._x
    x = property(getx, setx, delx, "I'm the 'x' property.")
```

> If c is an instance of C, `c.x` will invoke the getter, `c.x = value` will invoke the setter and `del c.x` the deleter.

How does `property()` work? The answer is simple. It's a descriptor type. It implements both the `tp_descr_get` and `tp_descr_set` slots that call the specified functions. Though the example from the docs doesn't show this, we can use a custom setter to do something useful. For example, we can use it to perform some validation of the new value.

### PyObject_GenericGetAttr()

Getting the value of an attribute is a bit more complicated than setting it. Let's see by how much. The `PyObject_GenericGetAttr()` function also delegates the work to another function: 

```C
PyObject *
PyObject_GenericGetAttr(PyObject *obj, PyObject *name)
{
    return _PyObject_GenericGetAttrWithDict(obj, name, NULL, 0);
}
```

And here's what that function does:

```C
PyObject *
_PyObject_GenericGetAttrWithDict(PyObject *obj, PyObject *name,
                                 PyObject *dict, int suppress)
{
    /* Make sure the logic of _PyObject_GetMethod is in sync with
       this method.

       When suppress=1, this function suppress AttributeError.
    */

    PyTypeObject *tp = Py_TYPE(obj);
    PyObject *descr = NULL;
    PyObject *res = NULL;
    descrgetfunc f;
    Py_ssize_t dictoffset;
    PyObject **dictptr;

    if (!PyUnicode_Check(name)){
        PyErr_Format(PyExc_TypeError,
                     "attribute name must be string, not '%.200s'",
                     Py_TYPE(name)->tp_name);
        return NULL;
    }
    Py_INCREF(name);

    if (tp->tp_dict == NULL) {
        if (PyType_Ready(tp) < 0)
            goto done;
    }

    descr = _PyType_Lookup(tp, name);

    f = NULL;
    if (descr != NULL) {
        Py_INCREF(descr);
        f = Py_TYPE(descr)->tp_descr_get;
        if (f != NULL && PyDescr_IsData(descr)) {
            res = f(descr, obj, (PyObject *)Py_TYPE(obj));
            if (res == NULL && suppress &&
                    PyErr_ExceptionMatches(PyExc_AttributeError)) {
                PyErr_Clear();
            }
            goto done;
        }
    }

    if (dict == NULL) {
        /* Inline _PyObject_GetDictPtr */
        dictoffset = tp->tp_dictoffset;
        if (dictoffset != 0) {
            if (dictoffset < 0) {
                Py_ssize_t tsize = Py_SIZE(obj);
                if (tsize < 0) {
                    tsize = -tsize;
                }
                size_t size = _PyObject_VAR_SIZE(tp, tsize);
                _PyObject_ASSERT(obj, size <= PY_SSIZE_T_MAX);

                dictoffset += (Py_ssize_t)size;
                _PyObject_ASSERT(obj, dictoffset > 0);
                _PyObject_ASSERT(obj, dictoffset % SIZEOF_VOID_P == 0);
            }
            dictptr = (PyObject **) ((char *)obj + dictoffset);
            dict = *dictptr;
        }
    }
    if (dict != NULL) {
        Py_INCREF(dict);
        res = PyDict_GetItemWithError(dict, name);
        if (res != NULL) {
            Py_INCREF(res);
            Py_DECREF(dict);
            goto done;
        }
        else {
            Py_DECREF(dict);
            if (PyErr_Occurred()) {
                if (suppress && PyErr_ExceptionMatches(PyExc_AttributeError)) {
                    PyErr_Clear();
                }
                else {
                    goto done;
                }
            }
        }
    }

    if (f != NULL) {
        res = f(descr, obj, (PyObject *)Py_TYPE(obj));
        if (res == NULL && suppress &&
                PyErr_ExceptionMatches(PyExc_AttributeError)) {
            PyErr_Clear();
        }
        goto done;
    }

    if (descr != NULL) {
        res = descr;
        descr = NULL;
        goto done;
    }

    if (!suppress) {
        PyErr_Format(PyExc_AttributeError,
                     "'%.50s' object has no attribute '%U'",
                     tp->tp_name, name);
    }
  done:
    Py_XDECREF(descr);
    Py_DECREF(name);
    return res;
}
```

The major steps of this algorithm are:

1. Search for the attribute value among type variables. The order of search is the MRO.
2. If the value is a data descriptor whose type implements the `tp_descr_get` slot, call this slot and return the result. Otherwise, remember the value and continue. A data descriptor is a descriptor whose type implements the `tp_descr_set` slot.
3. Locate the object's dictionary using `tp_dictoffset`. If the dictionary contains the value, return it.
4. If the value from step 2 is a descriptor whose type implements the `tp_descr_get` slot, call this slot and return the result.
5. Return the value from step 2. The value can be `NULL`.

Since an attribute can be both an instance variable and a type variable, CPython must decide which one takes precedence over the other. What the algorithm does is essentially implement a certain order of precedence. This order is:

1. type data descriptors
2. instance variables
3. type non-data descriptors and other type variables

The natural question to ask is: Why does it implement this particular order? More specifically, **why do data descriptors take precedence over instance variables but non-data descriptros don't? **First of all, note that some descriptors must take precedence over instance variables in order for Python to work as expected. An example of such a descriptor is the `__dict__` attribute of an object. You won't find the `'__dict__'` key in the object's dictionary because `__dict__` is a data descriptor stored in the type's dictionary:

```pycon
>>> a.__dict__
{'x': 'instance attribute', 'g': <function <lambda> at 0x108a4cc10>}
>>> A.__dict__['__dict__']
<attribute '__dict__' of 'A' objects>
>>> a.__dict__ is A.__dict__['__dict__'].__get__(a)
True
```

The `tp_descr_get` slot of this descriptor returns the object's dictionary located at `tp_dictoffset`. Now suppose that data descriptors don't take precedence over instance variables. What would happend then if we put `'__dict__'` in the object's dictionary and assigned it some other dictionary:

```pycon
>>> a.__dict__['__dict__'] = {}
```

The `a.__dict__` attribute would return not the object's dictionary but the dictionary we assigned! That would be totally unexpected for someone who relies on `__dict__`. Fortunately, data descriptors do take precedence over instance variables, so we get the object's dictionary:

```pycon
>>> a.__dict__
{'x': 'instance attribute', 'g': <function <lambda> at 0x108a4cc10>, '__dict__': {}}
```

Non-data descriptors don't take precedence over instance variables, so that most of the time instance variables have a priority over type variables. Of course, the existing order of precedence is one of many design choices. Guido van Rossum explains the reasoning behind it in [PEP 252](https://www.python.org/dev/peps/pep-0252/):

> In the more complicated case, there's a conflict between names stored in the instance dict and names stored in the type dict. If both dicts have an entry with the same key, which one should we return? Looking at classic Python for guidance, I find conflicting rules: for class instances, the instance dict overrides the class dict, **except** for the special attributes (like `__dict__` and `__class__`), which have priority over the instance dict.
>
> I resolved this with the following set of rules, implemented in `PyObject_GenericGetAttr()`: ...

**Why is the `__dict__` attribute implemented as a descriptor in the first place?** Making it an instance variable would lead to the same problem. It would be possible to override the `__dict__` attribute and hardly anyone wants to have this possibility.

We've learned how attributes of an ordinary object work. Let's see now how attributes of a type work.

## Type attributes

Basically, attributes of a type work just like attributes of an ordinary object. When we set an attribute of a type to some value, CPython puts the value in the type's dictionary:

```pycon
>>> B.x = 'class attribute'
>>> B.__dict__
mappingproxy({'__module__': '__main__', '__doc__': None, 'x': 'class attribute'})
```

When we get the value of the attribute, CPython loads it from the type's dictionary:

```pycon
>>> B.x
'class attribute'
```

If the type's dictionary doesn't contain the attribute, CPython loads the value from the metatype's dictionary:

```pycon
>>> B.__class__
<class 'type'>
>>> B.__class__ is object.__class__
True
```

Finally, if the metatype's dictionary doesn't contain the attribute either, CPython searches for the value in the dictionaries of metatype's parents... The analogy with the generic implementation is clear. We just change the words "object" with "type" and "type" with "metatype". However, we said before that `type` implements the `tp_getattro` and `tp_setattro` slots in its own way. Why? Let's take a look at the code.

### type_setattro()

We begin with the `type_setattro()` function, an implementation of the `tp_setattro` slot:

```C
static int
type_setattro(PyTypeObject *type, PyObject *name, PyObject *value)
{
    int res;
    if (!(type->tp_flags & Py_TPFLAGS_HEAPTYPE)) {
        PyErr_Format(
            PyExc_TypeError,
            "can't set attributes of built-in/extension type '%s'",
            type->tp_name);
        return -1;
    }
    if (PyUnicode_Check(name)) {
        if (PyUnicode_CheckExact(name)) {
            if (PyUnicode_READY(name) == -1)
                return -1;
            Py_INCREF(name);
        }
        else {
            name = _PyUnicode_Copy(name);
            if (name == NULL)
                return -1;
        }
        // ...
    }
    else {
        /* Will fail in _PyObject_GenericSetAttrWithDict. */
        Py_INCREF(name);
    }
  	
  	// Call the generic set function.
    res = _PyObject_GenericSetAttrWithDict((PyObject *)type, name, value, NULL);
    if (res == 0) {
        PyType_Modified(type);

      	// If attribute is a special method,
      	// add update the corresponding slots.
        if (is_dunder_name(name)) {
            res = update_slot(type, name);
        }
        assert(_PyType_CheckConsistency(type));
    }
    Py_DECREF(name);
    return res;
}
```

We can see that this function calls generic `_PyObject_GenericSetAttrWithDict()`, but it does something else too. It checks whether the attribute to be set is a special method. If the attribute is a special method, it updates the slots corresponding to that special method. For example, if we define the `__add__()` special method on an existing class, CPython will set the `nb_add` slot of the class to the default implementation that calls the method. Due to this mechanism, special methods and slots of a class are kept in sync.

### type_getattro()

The `type_getattro()` function, an implemenation of the `tp_getattro` slot, resembles the generic function:

```C
/* This is similar to PyObject_GenericGetAttr(),
   but uses _PyType_Lookup() instead of just looking in type->tp_dict. */
static PyObject *
type_getattro(PyTypeObject *type, PyObject *name)
{
    PyTypeObject *metatype = Py_TYPE(type);
    PyObject *meta_attribute, *attribute;
    descrgetfunc meta_get;
    PyObject* res;

    if (!PyUnicode_Check(name)) {
        PyErr_Format(PyExc_TypeError,
                     "attribute name must be string, not '%.200s'",
                     Py_TYPE(name)->tp_name);
        return NULL;
    }

    /* Initialize this type (we'll assume the metatype is initialized) */
    if (type->tp_dict == NULL) {
        if (PyType_Ready(type) < 0)
            return NULL;
    }

    /* No readable descriptor found yet */
    meta_get = NULL;

    /* Look for the attribute in the metatype */
    meta_attribute = _PyType_Lookup(metatype, name);

    if (meta_attribute != NULL) {
        Py_INCREF(meta_attribute);
        meta_get = Py_TYPE(meta_attribute)->tp_descr_get;

        if (meta_get != NULL && PyDescr_IsData(meta_attribute)) {
            /* Data descriptors implement tp_descr_set to intercept
             * writes. Assume the attribute is not overridden in
             * type's tp_dict (and bases): call the descriptor now.
             */
            res = meta_get(meta_attribute, (PyObject *)type,
                           (PyObject *)metatype);
            Py_DECREF(meta_attribute);
            return res;
        }
    }

    /* No data descriptor found on metatype. Look in tp_dict of this
     * type and its bases */
    attribute = _PyType_Lookup(type, name);
    if (attribute != NULL) {
        /* Implement descriptor functionality, if any */
        Py_INCREF(attribute);
        descrgetfunc local_get = Py_TYPE(attribute)->tp_descr_get;

        Py_XDECREF(meta_attribute);

        if (local_get != NULL) {
            /* NULL 2nd argument indicates the descriptor was
             * found on the target object itself (or a base)  */
            res = local_get(attribute, (PyObject *)NULL,
                            (PyObject *)type);
            Py_DECREF(attribute);
            return res;
        }

        return attribute;
    }

    /* No attribute found in local __dict__ (or bases): use the
     * descriptor from the metatype, if any */
    if (meta_get != NULL) {
        PyObject *res;
        res = meta_get(meta_attribute, (PyObject *)type,
                       (PyObject *)metatype);
        Py_DECREF(meta_attribute);
        return res;
    }

    /* If an ordinary attribute was found on the metatype, return it now */
    if (meta_attribute != NULL) {
        return meta_attribute;
    }

    /* Give up */
    PyErr_Format(PyExc_AttributeError,
                 "type object '%.50s' has no attribute '%U'",
                 type->tp_name, name);
    return NULL;
}
```

This algorithm indeed repeats the logic of the generic implementation, but with three important differences:

* It gets the type's dictionary via `tp_dict`. The generic implementation would try to locate it using metatype's `tp_dictoffset`.
* It searches for the type variable not only in type's dictionary but also in the dictionaries of type's parents. The generic implementation would handle a type like an ordinary object that has no notions of inheritance.
* It supports type descriptors. The generic implementation would support only metatype descriptors.

As a result, we have the following order of precedence:

1. metatype data descriptors
2. type descriptors and other type variables
3. metatype non-data descriptors and other metatype variables.

That's how `type` implements the `tp_getattro` and `tp_setattro` slots. Attributes of most types work according to this implementation, since `type` is the metatype of all built-in types and the metatype of all classes by default. Classes themselves, as we've already said, use the generic implementation by default. If we want to change the behavior of attribues of a class instance or the behavior of attributes of a class, we need to define a new class or a new metaclass that uses a custom implementation. Python provides an easy way to do this.

## Custom attribute management

The `tp_getattro` and `tp_setattro` slots of a class are initially set by the `type_new()` function that creates new classes. The generic implementationd is its default choice. A class can customize attribute access, assignment and deletion by defining the `__getattribute__()`, `__getattr__()`, `__setattr__()` and `__delattr__()` special methods. When a class defines `__setattr__()` or `__delattr__()`, its `tp_setattro` slot is set to the `slot_tp_setattro()` function. When a class defines  `__getattribute__()` or `__getattr__()`, its `tp_getattro` slot is set to the `slot_tp_getattr_hook()` function.



--

Sometimes, though, the generic implementation is not that straightforward. For example, some attributes of an object seem to belong to the object, but they are not in the object's dictionary. An example of such attribute is `__dict__` itself:

```pycon
>>> a.__dict__
{'x': 'instance attribute'} # __dict__ isn't here
```

Where does object's `__dict__ ` come from? Let's take a look at the type's dictionary:

```pycon
>>> A.__dict__
mappingproxy({'__module__': '__main__', '__dict__': <attribute '__dict__' of 'A' objects>, '__weakref__': <attribute '__weakref__' of 'A' objects>, '__doc__': None, 'y': 'class attribute'})
```

It contains the `'__dict__'` key. The value of this key is what we are looking for. If we call its `__get__()` method with the object as the argument, we'll get the object's dictionary:

```pycon
>>> A.__dict__['__dict__'].__get__(a)
{'x': 'instance attribute'}
```

You may recognize that `A.__dict__['__dict__']` is a descriptor. Descriptors are what makes the generic implementation a bit complex. But they also make it powerfull. As Python's glossary [says](https://docs.python.org/3/glossary.html#term-descriptor),

> Understanding descriptors is a key to a deep understanding of Python because they are the basis for many features including functions, methods, properties, class methods, static methods, and reference to super classes.

We've already mentioned descriptors in the previous part. This time, let's study them more thoroughly.

