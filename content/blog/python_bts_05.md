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
$ python -m dis global_fast_deref.py
...
  7          12 LOAD_GLOBAL              0 (x)
             14 LOAD_FAST                0 (y)
             16 BINARY_ADD
             18 LOAD_DEREF               0 (z)
             20 BINARY_ADD
             22 RETURN_VALUE
...
```

None of the opcodes are `LOAD_NAME`. The compiler produces the `LOAD_GLOBAL` opcode to load the value of `x`, the `LOAD_FAST` opcode to load the value of `y` and the `LOAD_DEREF` opcode to load the value of `z`.  In general, which opcode the compiler produces for a variable depends on the scope of that variable. This is done so that the VM can store and load values of variables with different scopes differently. CPython uses four pairs of load/store opcodes in total and one more load opcode for the very special case:

* It uses the `LOAD_FAST` and `STORE_FAST` opcodes for the variables local to a function. They are called `*_FAST`, because the VM uses an array to implement name-value mapping for such variables, which works faster than a dictionary.
* It uses the `LOAD_GLOBAL` and `STORE_GLOBAL` opcodes for the variables global to a function.
* It uses the `LOAD_DEREF` and `STORE_DEREF` opcodes for the variables bound in a function and used by the nested function. These opcodes are used to implement [closures](https://en.wikipedia.org/wiki/Closure_(computer_programming)).
* It uses the `LOAD_NAME` and `STORE_NAME` opcodes for other variables. These effectively are the variables of a module or a class definition.
* It uses the `LOAD_CLASSDEREF` opcode for variables of a class definition nested in a function and not bound in the class definition but bound in the function.

Whoa! What does it mean for a variable to be local to a function? Global to a function? What do we mean by the scope of a variable at all? We need to answer these questions before we can understand why CPython works with variables in multiple ways.

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
$ python -m dis example6.py
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

The VM doesn't need to get the names of local variables to load and store their values. Nevertheless, it stores the names of local variables in the `co_varnames` tuple in a code object. Names are necessary for debugging and error messages. They are also used by the tools such as `dis` that reads  `co_varnames` to display names in parentheses:

```text
              2 STORE_FAST               1 (y)
```

CPython provides the `local()` built-in function that returns the name-value mapping of the current namepace in the form of a dictionary. The VM doesn't keep such a dictionary for functions but it can built one on the fly by mapping keys from `co_varnames` to values from `f_localsplus`.

The `LOAD_FAST` opcode simply pushes `f_localsplus[oparg]` on the stack:

```C
case TARGET(LOAD_FAST): {
    PyObject *value = GETLOCAL(oparg);
    if (value == NULL) {
        format_exc_check_arg(tstate, PyExc_UnboundLocalError,
                             UNBOUNDLOCAL_ERROR_MSG,
                             PyTuple_GetItem(co->co_varnames, oparg));
        goto error;
    }
    Py_INCREF(value);
    PUSH(value);
    FAST_DISPATCH();
}
```

The `LOAD_FAST` and  `STORE_FAST` opcodes exist for performance reasons only. What's the speed gain? Let's measure the difference between `STORE_FAST` and `STORE_NAME`. The following piece of code stores the value of variable `i` 100 million times:

```python
for i in range(10**8):
		pass
```

If we place it in a module, the compiler produces the `STORE_NAME` opcode. If we place it in a function, the compiler produces the `STORE_FAST` opcode. Let's do both and compare the running times:

```python
import time


times = []
for _ in range(5):
    start = time.time()
    for i in range(10**8):
        pass
    times.append(time.time() - start)

print('STORE_NAME: ' + ' '.join(f'{elapsed:.3f}s' for elapsed in sorted(times)))


def f():
    times = []
    for _ in range(5):
        start = time.time()
        for i in range(10**8):
            pass
        times.append(time.time() - start)

    print('STORE_FAST: ' + ' '.join(f'{elapsed:.3f}s' for elapsed in sorted(times)))


f()
```

```text
$ python fast_vs_name.py
STORE_NAME: 4.536s 4.572s 4.650s 4.742s 4.855s
STORE_FAST: 2.597s 2.608s 2.625s 2.628s 2.645s
```

Another difference in implementation of `STORE_NAME` and `STORE_FAST` could affect the results. The case block for the `STORE_FAST` opcode ends with the `FAST_DISPATCH()` macro, which means that the VM goes to the next instruction straight away after it executes the `STORE_FAST` instruction. The case block for the `STORE_NAME` opcode ends with the `DISPATCH()` macro, which means that the VM may possible go to the start of the evaluation loop. At the start of the evaluation loop the VM checks whether it has to suspend the bytecode execution, for example, to release the GIL or to handle signals. I've replaced the `DISPATCH()` macro with `FAST_DISPATCH()` in the case block for `STORE_NAME`, recompiled CPyhon and got similar results. So, the difference in times should indeed be explained by:

* the extra step to get a name; and
* the fact that a dictionary is slower than an array.

## LOAD_DEREF and STORE_DEREF

There is one case when the compiler doesn't produce the `LOAD_FAST` and `STORE_FAST` opcodes for variables local to a function. This happens when a variable is used within a nested function. 

```python
def f():
    b = 1
    def g():
        return b
```

```
$ python -m dis nested.py
...
Disassembly of <code object f at 0x1027c72f0, file "nested.py", line 1>:
  2           0 LOAD_CONST               1 (1)
              2 STORE_DEREF              0 (b)

  3           4 LOAD_CLOSURE             0 (b)
              6 BUILD_TUPLE              1
              8 LOAD_CONST               2 (<code object g at 0x1027c7240, file "nested.py", line 3>)
             10 LOAD_CONST               3 ('f.<locals>.g')
             12 MAKE_FUNCTION            8 (closure)
             14 STORE_FAST               0 (g)
             16 LOAD_CONST               0 (None)
             18 RETURN_VALUE

Disassembly of <code object g at 0x1027c7240, file "nested.py", line 3>:
  4           0 LOAD_DEREF               0 (b)
              2 RETURN_VALUE
```

The compiler produces the `LOAD_DEREF` and `STORE_DEREF` opcodes for cell and free variables. A cell variable is a local variable used in a nested function. In our example, `b` is a cell variable of the `f` function, because it's used in `g`. A free variable is a cell variable from the perspective of a nested function. It's a variable not bound in a function but bound in the enclosing function or a variable marked `nonlocal`. In our example, `b` is a free variable of the `g` function, because it's not bound in `g` but bound in `f`.

The values of cell and free variables are stored in the `f_localsplus ` array after the values of normal local variables. The only difference is that `f_localsplus[index_of_cell_or_free_var]` points not to the value directly but to a cell object containing the value:

```C
typedef struct {
    PyObject_HEAD
    PyObject *ob_ref;       /* Content of the cell or NULL when empty */
} PyCellObject;
```

The `STORE_DEREF` opcode pops the value from the stack, gets the cell of the variable specified by `oparg` and assigns `ob_ref` of that cell to the value:

```C
case TARGET(STORE_DEREF): {
    PyObject *v = POP();
    PyObject *cell = freevars[oparg]; // freevars = f->f_localsplus + co->co_nlocals
    PyObject *oldobj = PyCell_GET(cell);
    PyCell_SET(cell, v); // expands to ((PyCellObject *)(cell))->ob_ref = v
    Py_XDECREF(oldobj);
    DISPATCH();
}
```

Similarly, `LOAD_DEREF` pushes on the stack content of a cell:

```C
case TARGET(LOAD_DEREF): {
    PyObject *cell = freevars[oparg];
    PyObject *value = PyCell_GET(cell);
    if (value == NULL) {
      format_exc_unbound(tstate, co, oparg);
      goto error;
    }
    Py_INCREF(value);
    PUSH(value);
    DISPATCH();
}
```

The value of a cell variable and the corresponding free variable is stored in the same cell. The VM passes the cells of the enclosing function to the enclosed function when it creates the enclosed function. The `LOAD_CLOSURE` opcode pushes a cell on the stack and the `MAKE_FUNCTION` opcode creates a function that uses that cell for the corresponding free variable. Due to the cell mechanism, when the enclosing function reassigns a cell variable, the enclosed function sees the reassignment:

```python
def f():
    def g():
        print(a)
    a = 'assigned'
    g()
    a = 'reassigned'
    g()

f()
```

```text
$ python cell_reassign.py 
assigned
reassigned
```

and vice versa:

```python
def f():
    def g():
        nonlocal a
        a = 'reassigned'
    a = 'assigned'
    print(a)
    g()
    print(a)

f()
```

```text
$ python free_reassign.py 
assigned
reassigned
```

Do we really need the cell mechanism to implement such behavior? Couldn't we just use the enclosing namespace to load and store the values of free variables? Yes, we could, but consider the following example:

```python
def get_counter(start=0):
    def count():
        nonlocal c
        c += 1
        return c

    c = start - 1
    return count

count = get_counter()
print(count())
print(count())
```

```text
$ python counter.py 
0
1
```

Recall that when we call a function, CPython creates a frame object to execute it. A frame object captures the state of the code object's execution including the name-value mapping. This example shows that an enclosed function can outlive the frame object of the enclosing function. The benefit of the cell mechasim is that it allows to avoid keeping the frame object of an enclosing function in memory.

## LOAD_GLOBAL and STORE_GLOBAL

The compiler produces the `LOAD_GLOBAL` and `STORE_GLOBAL` opcodes for variables global to a function. The variable is considered be global to a function if it's marked `global` or if it's not bound within the function and any enclosing function (i.e. it's neither local nor free). Here's an example:

```python
a = 1
d = 1

def f():
    b = 1
    def g():
        global d
        c = 1
        d = 1
        return a + b + c + d

```

The `c` variable is not global to `g` because it's local to `g`. The `b` variable is not global to `g` because it's free. The `a` variables is global to `g` because it's not local nor free. And the `d` variable is global to `g` because it's explicitly marked `global`.

Here's the implementation of the `STORE_GLOBAL` opcode:

```C
case TARGET(STORE_GLOBAL): {
    PyObject *name = GETITEM(names, oparg);
    PyObject *v = POP();
    int err;
    err = PyDict_SetItem(f->f_globals, name, v);
    Py_DECREF(v);
    if (err != 0)
      	goto error;
    DISPATCH();
}
```

The `f_globals` field of a frame object is a dictionary that maps global names to their values. When CPython creates a frame object for a module, it assigns `f_globals` to the dictionary of the module. We can easily check this:

```text
$ python -q
>>> import sys
>>> globals() is sys.modules['__main__'].__dict__
True
```

When the VM executes the `MAKE_FUNCTION` opcode to create a new function object, it assigns the `func_globals` field of that object to the `f_globals` field of the current frame. When the function is called, the VM creates a frame object with `f_globals` set to `func_globals`.

The implementation of `LOAD_GLOBAL` is similiar to that of `LOAD_NAME` with two exceptions:

* It doesn't look up values in `f_locals`.
* It uses cache to decrease the lookup time.

CPython caches the results in the `co_opcache` field of a code object. This is an array of pointers to the `_PyOpcache` objects:

```C
typedef struct {
    PyObject *ptr;  /* Cached pointer (borrowed reference) */
    uint64_t globals_ver;  /* ma_version of global dict */
    uint64_t builtins_ver; /* ma_version of builtin dict */
} _PyOpcache_LoadGlobal;

struct _PyOpcache {
    union {
        _PyOpcache_LoadGlobal lg;
    } u;
    char optimized;
};
```

The `ptr` field of the `_PyOpcache_LoadGlobal` struct points to the actual result of `LOAD_GLOBAL`. The cache is maintained per instruction number. Another array in a code object called `co_opcache_map` maps each intruction in the bytecode to its index minus one in `co_opcache`. If the instruction is not `LOAD_GLOBAL`, it maps the instruction to `0`. The size of the cache doesn't exceed 254. If bytecode contains more than 254 `LOAD_GLOBAL` instructions, `co_opcache_map` maps extra instructions to `0`.

If the VM finds a value in a cache when it executes `LOAD_GLOBAL`, it makes sure that the `f_global` and `f_builtins` dictionaries haven't been modified since the last time the value was looked up. This is done by comparing `globals_ver` and `builtins_ver` with `ma_version_tag` of the dictionaries. The `ma_version_tag` field of a dictionary changes each time the dictionary is modified. See [PEP 509](https://www.python.org/dev/peps/pep-0509/) for more details.

If the VM doesn't find a value in a cache, it does a normal look up first in `f_globals` and then in `f_builtins`. If it finds the value, it remembers the current values of `ma_version_tag` of both dictionaries and pushes the value on the stack.

## LOAD_NAME and STORE_NAME (and LOAD_CLASSDEREF)

At this point you might wonder why CPython uses the `LOAD_NAME` and `STORE_NAME` opcodes at all. The compiler indeed doesn't produce these opcodes when it compiles functions, but a function is only one kind of code block. CPython distinguishes three kinds of code blocks in total:

* modules
* functions (comprehensions and lambdas are also functions)
* class definitions.

We haven't talked about class definitions, so let's fix it. The compiler creates a code object for each code block in a program. The VM executes the module's code object when we run or import the module. It executes the function's code object when we call the function. And it executes the code object of a class definition when we create the class. Here's what I mean:

```python
class A:
    print('This code is executed')
```

```text
$ python create_class.py 
This code is executed
```

The compiler produces the `LOAD_NAME` and `STORE_NAME` opcodes for all variables within a class definition (with one exception). Because of this, the variables within a class definition work differently than the variables within a function:

```python
x = 'global'

class C:
    print(x)
    x = 'local'
    print(x)
```

```text
$ python class_local.py
global
local
```

On the first load, the VM gets the value of the `x` variable from `f_globals`. Then, it stores the new value in `f_locals` and, on the second load, gets it from there. If `C` was a function,  we would get `UnboundLocalError: local variable 'x' referenced before assignment ` when we call it, because the compiler would think that the `x` variable is local to `C`.

When we place a function inside a class, which is a common practice to implement methods, the function doesn't see the names bound in the class' namespace:

```python
class D:
    x = 1
    def method(self):
        print(x)

D().method()
```

```text
$ python func_in_class.py
...
NameError: name 'x' is not defined
```

This is because the VM stores the value of `x`  with `STORE_NAME` when it executes the class definition and tries to load it with `LOAD_GLOBAL` when it executes the function.

