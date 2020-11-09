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
* It uses the `LOAD_NAME` and `STORE_NAME` opcodes for the variables local to a namespace other than a function namespace. These effectively are the variables local to a module or a class definition.

What does it mean for a variable to be local to a function? Global? What do we mean by the scope of a variable? We need to answer these questions before we can understand why CPython works with variables in four different ways.

## Namespaces and scopes

CPython keeps track of all variables used within each namepspace. A namespace in Python is just a synonym for a code object in the context of variables. A module, a function and a class define namespaces. The scope of a variable is relative to a namespace. This is why I use phrases such as "local to a function". The following example illustrates the point:

```python
a = 1

def f():
    b = 3
    return a + b
```

Here, `a` is a global variable to the `f` function, but it's local to the module. The `b` variable is local to the `f` function, but it doesn't exist in the module's namespace at all.

The variable is considered to be local to a namespace if it's bound in that namespace. The assignment statement like `a = 1` binds the name `a` to `1`. The assignment statement, though, is not the only way to bind a name. [The Python Language Reference](https://docs.python.org/3/reference/executionmodel.html#naming-and-binding) lists a few more:

> The following constructs bind names: formal parameters to functions, `import` statements, class and function definitions (these bind the class or function name in the defining block), and targets that are identifiers if occurring in an assignment, `for` loop header, or after as in a `with` statement or `except` clause. The `import` statement of the form `from ... import *` binds all names defined in the imported module, except those beginning with an underscore. This form may only be used at the module level.

Because any binding of a name makes the compiler think that the name is local, the following code raises an exception:

```python
a = 1

def f():
    a += 1
    return a

print(f())
```

```text
$ python example3.py
...
    a += 1
UnboundLocalError: local variable 'a' referenced before assignment
```

The `a += 1` statement is a form of assignment, so the compiler thinks that `a` is local. To perfrom the operation, the VM tries to load the value of `a`, fails and sets the exception. To tell the compiler that `a` is global despite the assignment we can use the `global` statement:

```python
a = 1

def f():
    global a
    a += 1
    return a

print(f())
```

```text
$ python example4.py 
2
```

Similarly, we use the `nonlocal` statement to tell the compiler that a name assigned in an enclosed (nested) function corresponds to the namespace of the enclosing function:

```python
a = 1 # this is not used

def f():
    a = 2
    def g():
        nonlocal a
        a += 1
        return a

    return g()

print(f())
```

```text
$ python example5.py 
3
```

This is the work of the compiler to analyze the usage of names within the namespace, take statements like `global` and `nonlocal` into account and produce the right opcodes to load and store values. Let's see why CPython uses four pairs of load/store opcodes and how the VM executes them.

## LOAD_FAST and STORE_FAST

The compiler produces `LOAD_FAST` and `STORE_FAST` opcodes for variables local to a function. Here's an example:

```python
def f(x):
    y = x
    return y
```

```
$ python3 -m dis example6.py
...
  2           0 LOAD_FAST                0 (x)
              2 STORE_FAST               1 (y)

  3           4 LOAD_FAST                1 (y)
              6 RETURN_VALUE
```

The `y` variable is local to `f` because it's bound in `f` by the assignment. The `x` variable is local to `f` because it's bound in `f` as its parameter.

Let's look at the code for executing the `STORE_FAST` opcode:

```C
case TARGET(STORE_FAST): {
    PREDICTED(STORE_FAST);
    PyObject *value = POP();
    SETLOCAL(oparg, value);
    FAST_DISPATCH();
}
```

`SETLOCAL()` is a macro that essentially expands to `fastlocals[oparg] = value`. The `fastlocals` variable is just a shorthand for the `f_localsplus` field of a frame object. The `f_localsplus` field is an array of pointers to Python objects. It stores values of local variables, cell variables, free variables and the value stack. Last time we learned that the `f_localsplus` array is used to store the value stack. In the next sections of this post we'll see how it's used to store values of cell and free variables. For now we're interested in the first part of the array that's used for local variables.

We've seen that in the case of the `STORE_NAME` opcode, the VM first gets the name from `co_names` and then maps that name to the value on top of the stack. It uses `f_locals` as a name-value mapping, which is usually a dictionary. In the case of the `STORE_FAST` opcode, the VM doesn't need to get the name. The number of local variables can be calculated statically by the compiler, so the VM can use an array to store their values. Each local variable corresponds to an index of the array. To map a name to a value, the VM simply stores the value in the corresponding index.



The `STORE_FAST` opcode exists for performance reasons. Nevertheless, the difference with `STORE_NAME` is significant. 

