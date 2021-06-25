Title: Python behind the scenes #11: how the Python import system works
Date: 2021-06-22 6:06
Tags: Python behind the scenes, Python, CPython

If you ask me to name the most misunderstood feature of Python, I will answer without a second thought: the Python import system. Just remember how many times you used relative imports and got something like `ImportError: attempted relative import with no known parent package`; or tried to figure out how to structure a project so that all the imports work correctly; or hack `sys.path` when you couldn't find a better solution. Many Python programmers had such experiences. A number of popular questions on StackOverflow, like [Importing files from different folder](https://stackoverflow.com/questions/4383571/importing-files-from-different-folder) (1822 votes), [Relative imports in Python 3](https://stackoverflow.com/questions/16981921/relative-imports-in-python-3) (1064 votes) and [Relative imports for the billionth time](https://stackoverflow.com/questions/14132789/relative-imports-for-the-billionth-time) (993 votes), is a good inidcator of that.

The goal of this post is to get the full picture of the Python import system and understand the reasoning behind its design. We'll see what exactly happens when Python executes an import statement, and this, I hope, will help you solve the import problems much more effectively or avoid them altogether. Let's go!

## Modules and module objects

The job of the import system is to import modules, but what is a module? We apply the term "module" to a number of different things including Python files, directories and built-in modules written in C. So the best we can do is to say that a **module** is anything that Python considers a module. We'll see what the full list includes in the course of this post.

When Python imports a module, it creates a **module object**. Consider the simplest form of the import statement:

```python
import m
```

It tells Python to find the module named `"m"`, create and initialize the module object for the module, and assign the module object to the variable `m`. The term "module" is often applied to a module object as well.

Like everything in Python, a module object is a [Python object]({filename}/blog/python_bts_06.md). Its definition can be found in [`Objects/moduleobject.c`](https://github.com/python/cpython/blob/3.9/Objects/moduleobject.c):

```C
typedef struct {
    PyObject ob_base;
    PyObject *md_dict;
    struct PyModuleDef *md_def;
    void *md_state;
    PyObject *md_weaklist;
    PyObject *md_name;
} PyModuleObject;
```

The only field of a module object that we should care about is `md_dict`. It's the dictionary of a module object (available as `m.__dict__`), and it's where the attributes of a module object are stored. Typical attributes of a module object are functions, classes, constants and other modules. They are the reason to import a module in the first place, and a module object is just a namespace for them.

To see that there is nothing magical about module objects, let's create one. We create Python objects by calling their types like `MyClass()` or `set()`. The type of module objects is called `PyModule_Type` in the C code but it's not available in Python as a built-in. Fortunately, such "unavailable" types can be found in the [`types`](https://docs.python.org/3/library/types.html) standard module:

```pycon
$ python -q
>>> from types import ModuleType
>>> m = ModuleType('m')
>>> m
<module 'm'>
```

Another way to get `ModuleType` in Python is to import some module and then call `type()` on the module object returned:

```pycon
>>> import sys
>>> ModuleType = type(sys)
>>> ModuleType
<class 'module'>
```

And this is exactly how the `types` module defines `ModuleType`.

A newly created module object is not very interesting but has some special attributes preinitialized:

```pycon
>>> m.__dict__
{'__name__': 'm', '__doc__': None, '__package__': None, '__loader__': None, '__spec__': None}
```

Most of these special attributes are mainly used by the import system itself, and we'll later see  how. For now, let's take a look at the `__name__` attribute that is often used to get the name of the current module:

```pycon
>>> __name__
'__main__'
```

Notice that `__name__` is available as a global variable. This is because the dictionary of global variables is always set to the dictionary of the current module. Here's a proof:

```pycon
>>> import sys
>>> current_module = sys.modules[__name__] # sys.modules stores loaded modules
>>> current_module.__dict__ is globals()
True
```

When Python imports a Python file, it creates a new module object and then executes the contents of the file using the dictionary of the module object as the dictionary of global variables. Similarly, when Python executes a Python file as a script, it first creates a special module called `'__main__'` and then uses its dictionary as the dictionary of global variables. Thus, global variables are always attributes of some module, and this module is considered to be the current module.

Okay. We can always access attributes defined in the current module and we can import other modules to access their attributes. Let's see now see what Python does when it imports modules.

## Desugaring the import statement

Recall that a piece of Python code is executed in two steps:

1. The [compiler]({filename}/blog/python_bts_02.md) compiles the code to bytecode.
2. The [VM]({filename}/blog/python_bts_01.md) executes the bytecode.

To see how an import statement gets executed, we can look at the bytecode produced for it. As always, the [dis](https://docs.python.org/3/library/dis.html) standard module can help us with this:

```text
$ echo "import m" | python3 -m dis
  1           0 LOAD_CONST               0 (0)
              2 LOAD_CONST               1 (None)
              4 IMPORT_NAME              0 (m)
              6 STORE_NAME               0 (m)
...
```

The first [`LOAD_CONST`](https://docs.python.org/3/library/dis.html#opcode-LOAD_CONST) instruction pushes `0` onto the value stack. The second `LOAD_CONST` pushes `None`. Then the `IMPORT_NAME` opcode does something that we'll look into in a moment. Finally, [`STORE_NAME`](https://docs.python.org/3/library/dis.html#opcode-STORE_NAME) assigns the value on top of the value stack to the variable `m`.

The logic of opcode execution is implemented in the [evaluation loop]({filename}/blog/python_bts_04.md) in [`Python/ceval.c`](https://github.com/python/cpython/blob/3.9/Python/ceval.c). Here's the code that executes `IMPORT_NAME`:

```C
case TARGET(IMPORT_NAME): {
    PyObject *name = GETITEM(names, oparg);
    PyObject *fromlist = POP();
    PyObject *level = TOP();
    PyObject *res;
    res = import_name(tstate, f, name, fromlist, level);
    Py_DECREF(level);
    Py_DECREF(fromlist);
    SET_TOP(res);
    if (res == NULL)
        goto error;
    DISPATCH();
}
```

So, what `IMPORT_NAME` does is call the `import_name()` function and leaves the result of the call on top of the value stack. The constants `0` and `None` that were pushed onto the stack are used as the `level` and `fromlist` arguments. And the argument to `IMPORT_NAME` specifies the name of the module.

The `import_name()` function is implemented as follows:

```C
static PyObject *
import_name(PyThreadState *tstate, PyFrameObject *f,
            PyObject *name, PyObject *fromlist, PyObject *level)
{
    _Py_IDENTIFIER(__import__);
    PyObject *import_func, *res;
    PyObject* stack[5];

    import_func = _PyDict_GetItemIdWithError(f->f_builtins, &PyId___import__);
    if (import_func == NULL) {
        if (!_PyErr_Occurred(tstate)) {
            _PyErr_SetString(tstate, PyExc_ImportError, "__import__ not found");
        }
        return NULL;
    }

    /* Fast path for not overloaded __import__. */
    if (import_func == tstate->interp->import_func) {
        int ilevel = _PyLong_AsInt(level);
        if (ilevel == -1 && _PyErr_Occurred(tstate)) {
            return NULL;
        }
        res = PyImport_ImportModuleLevelObject(
                        name,
                        f->f_globals,
                        f->f_locals == NULL ? Py_None : f->f_locals,
                        fromlist,
                        ilevel);
        return res;
    }

    Py_INCREF(import_func);

    stack[0] = name;
    stack[1] = f->f_globals;
    stack[2] = f->f_locals == NULL ? Py_None : f->f_locals;
    stack[3] = fromlist;
    stack[4] = level;
    res = _PyObject_FastCall(import_func, stack, 5);
    Py_DECREF(import_func);
    return res;
}
```

In English, it reads like this:

1. Look up the `__import__()` function in the `builtins` module.
2. If the `__import__()` function is the same thing as `tstate->interp->import_func`, then call `PyImport_ImportModuleLevelObject()`. 
3. Otherwise, call `__import__()`.

The [`builtins.__import__()`](https://docs.python.org/3/library/functions.html#__import__) function is the function that implements the logic of the import machinery. Its default implementation calls `PyImport_ImportModuleLevelObject()`, and the algorithm above also calls this function in step 2. It takes a shortcut. Why doesn't it always take a shortuct? It's because Python allows us to set `builtins.__import__()` to a custom function. To know whether `builtins.__import__()` was overridden, Python saves the default implementation in `tstate->interp->import_func`.



