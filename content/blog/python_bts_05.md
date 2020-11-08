Title: Python behind the scenes #5: how variables are implemented in CPython
Date: 2020-11-07 5:34
Tags: Python behind the scenes, Python, CPython

Consider a simple assignment statement in Python:

```python
a = b
```

The meaning of this statement may seem trivial. What we do here is take the value of the name `b` and assign it to the name `a`, but do we really? This is an ambiguous exmplanation that gives rise to a lot of questions:

* What does it mean for a name to be associated with a value? What is a value?
* What does CPython do to assign a value to a name? To retrieve a value?
* Do all the variables are implemented in the same way?

Today we'll answer these questions and understand how variables, so crucial aspect of a programming language, are implemented in CPython.

## Start of the investigation

Where should we start our investigation? We know from the previous parts that to run Python code, CPython compiles it to bytecode, so let's start by looking at the bytecode to which `a = b` compiles:

```
$ echo 'a = b' | python -m dis

  1           0 LOAD_NAME                0 (b)
              2 STORE_NAME               1 (a)
...
```

Last time we learned that the CPython VM operates using the value stack. This should give us an idea of what `LOAD_NAME` and `STORE_NAME` instructions do:

* `LOAD_NAME` gets the value of the name `b` and pushes it on the stack.
* `STORE_NAME` pops the value from the stack and binds the name `a` to that value.

We can get more details by looking at the CPython source code. Let's start with the `STORE_NAME` opcode since we need to bind a name to a value before we can get a value from a name. Here's the piece of code responsible for the execution of `STORE_NAME` opcode: 

```C
case TARGET(STORE_NAME): {
    PyObject *name = GETITEM(names, oparg);
    PyObject *v = POP();
    PyObject *ns = f->f_locals;
    int err;
    if (ns == NULL) {
        _PyErr_Format(tstate, PyExc_SystemError,
                      "no locals found when storing %R", name);
        Py_DECREF(v);
        goto error;
    }
    if (PyDict_CheckExact(ns))
      	err = PyDict_SetItem(ns, name, v);
    else
      	err = PyObject_SetItem(ns, name, v);
    Py_DECREF(v);
    if (err != 0)
      	goto error;
    DISPATCH();
}
```

Let's analyze what it means:

1. The names of variables are strings. They are stored in a tuple in a code object called `co_names`. The `names` variable is just a shorthand for `co_names`. The argument of the `STORE_NAME` instruction is not a name but an index used to look up the name in `co_names`.  The first thing the VM does is get the name, which it's going to assign a value to, from `co_names`.
2. The VM pops the value from the stack.
3. Values of variables are stored in a frame object. The `f_locals` field of a frame object is a mapping from the names of local variables to their values. The VM assigns a value `v` to a name `name` by setting `f_locals[name] = v`.

We can learn from this that:

* Python variables are names mapped to values.
* Values are references to Python objects.

The logic for executing the `LOAD_NAME` opcode is a bit more complicated because the VM looks up the value of a variable in several places:

```C
case TARGET(LOAD_NAME): {
    PyObject *name = GETITEM(names, oparg);
    PyObject *locals = f->f_locals;
    PyObject *v;
  
    if (locals == NULL) {
        _PyErr_Format(tstate, PyExc_SystemError,
                        "no locals when loading %R", name);
        goto error;
    }
  
  	// look up the value in `f->f_locals`
    if (PyDict_CheckExact(locals)) {
        v = PyDict_GetItemWithError(locals, name);
        if (v != NULL) {
            Py_INCREF(v);
        }
        else if (_PyErr_Occurred(tstate)) {
            goto error;
        }
    }
    else {
        v = PyObject_GetItem(locals, name);
        if (v == NULL) {
            if (!_PyErr_ExceptionMatches(tstate, PyExc_KeyError))
                goto error;
            _PyErr_Clear(tstate);
        }
    }
  
  	// look up the value in `f->f_globals` and `f->f_builtins`
    if (v == NULL) {
        v = PyDict_GetItemWithError(f->f_globals, name);
        if (v != NULL) {
            Py_INCREF(v);
        }
        else if (_PyErr_Occurred(tstate)) {
            goto error;
        }
        else {
            if (PyDict_CheckExact(f->f_builtins)) {
                v = PyDict_GetItemWithError(f->f_builtins, name);
                if (v == NULL) {
                    if (!_PyErr_Occurred(tstate)) {
                        format_exc_check_arg(
                                tstate, PyExc_NameError,
                                NAME_ERROR_MSG, name);
                    }
                    goto error;
                }
                Py_INCREF(v);
            }
            else {
                v = PyObject_GetItem(f->f_builtins, name);
                if (v == NULL) {
                    if (_PyErr_ExceptionMatches(tstate, PyExc_KeyError)) {
                        format_exc_check_arg(
                                    tstate, PyExc_NameError,
                                    NAME_ERROR_MSG, name);
                    }
                    goto error;
                }
            }
        }
    }
    PUSH(v);
    DISPATCH();
}
```

This code translates to Engish as follows:

1. As for the `STORE_NAME` opcode, the VM first gets the name of a variable.
2. The VM looks up the value of the name in the mapping of local variables: `v = f_locals[name]`.
3. If the name is not in `f_locals`, the VM looks up the value in the mapping of global variables `f_globals`. And if the name is not in `f_globals` either, the VM looks up the value in `f_builtins`. The `f_builtins` field of a frame object points  to the dictionary of the `builtins` module, which contains bult-in types, functions, exceptions and constants. If the name is not there, the VM gives up and sets the `NameError` exception. 
4. If the VM finds the value, it pushes the value on the stack.

The way the VM searches for a name has the following effects:

* We always have the names from the `builtin`'s dictionary, such as `int`, `next`, `ValueError` and `None`, at our disposal.
* If we use a built-in name for a local variable or a global variable, the new variable will shadow the built-in one.

* A local variable shadows the global variable with the same name.
  

Since all we need to be able to do with variables is to assign values to them and to get their values, you might think that the `STORE_NAME` and `LOAD_NAME` opcodes are sufficient to implement Python variables. This is not the case. Consider the example:

```python
x = 1

def f(y, z):
    def _():
        return z

    return x + y + z
```

The `f` function has to load the values of variables `x`, `y` and `z` to add them and return the result. Note which opcodes the compiler produces to do that:

```
$ python3 -m dis global_fast_deref.py
...
  7          12 LOAD_GLOBAL              0 (x)
             14 LOAD_FAST                0 (y)
             16 BINARY_ADD
             18 LOAD_DEREF               0 (z)
             20 BINARY_ADD
             22 RETURN_VALUE
...
```

None of the opcodes are `LOAD_NAME`. The compiler produces the `LOAD_GLOBAL` opcode to load the value of `x`, the `LOAD_FAST` opcode to load the value of `y` and the `LOAD_DEREF` opcode to load the value of `z`.  In general, which opcode the compiler produces for a variable depends on the scope of that variable. This is done so that the VM can store and load values of variables with different scopes differently. CPython uses four pairs of load/store opcodes in total:

* It uses the `LOAD_FAST` and `STORE_FAST` opcodes for the variables local to a function. They are called `*_FAST`, because the VM uses an array to implement name-value mapping for such variables, which works faster than a dictionary.
* It uses the `LOAD_GLOBAL` and `STORE_GLOBAL` opcodes for the variables global to a function.
* It uses the `LOAD_DEREF` and `STORE_DEREF` opcodes for the variables bound in a function and used by the nested function. These opcodes are used to implement closures.
* It uses the `LOAD_NAME` and `STORE_NAME` opcodes for the variables local to a namespace other than a function namespace. These effectively are the variables local to a module or a class.

