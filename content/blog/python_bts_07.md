Title: Python behind the scenes #7: how Python attributes work
Date: 2020-12-15 6:25
Tags: Python behind the scenes, Python, CPython

What happens when you get or set an attribute of a Python object? This question is not as simple as it may seem at first. It's true that any experienced Python programmer has a good intuitive understanding of how attributes work, and the documentation helps a lot to strengthen the understanding. Yet, once a really non-trivial question regarding attributes comes up, the intuition fails and the documentation can no longer help. To gain a deep understanding and be able to answer such questions, one has to study how attributes are implemented. That's what we're going to do today.

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

The members of a type are called slots. Each slot is responsible for a particular aspect of the object's behavior. For example, the ` tp_call` slot of a type specifies what happens when we call the object of that type. Some slots are grouped together in suites. An example of a suite is the "number" suite `tp_as_number`. Last time we studied in great detail its `nb_add` slot that specifies how to add objects. This and all other slots are very well [described](https://docs.python.org/3/c-api/typeobj.html) in the docs.

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

Like any other aspect of the object's behavior, how attributes of an object work depends on the object's type. The certain slots of a type specify what happens when we get and set attributes of an object of that type. Let's find out what those slots are and how they are used.

To learn how the CPython VM gets and sets attributes, we'll apply the familiar method:

1. Write a piece of code that gets (sets) an attribute.
2. Disassemble it to bytecode using the [`dis`](https://docs.python.org/3/library/dis.html) module.
3. Take a look at the implementation of the produced bytecode instructions in [`ceval.c`](https://github.com/python/cpython/blob/3.9/Python/ceval.c).

### Getting an attribute

Let's first see what the VM does when we get an attribute of an object. The compiler produces the `LOAD_ATTR` opcode to load the attribute:

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

We can see that the VM calls the `PyObject_GetAttr()` function to do the job. Let's see what it does:

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

## Setting an attribute

From the VM's perspective, setting an attribute is not much different from getting it. The compiler produces the `STORE_ATTR` opcode to set the attribute:

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

`PyObject_SetAttr()` is the function that does the job:

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