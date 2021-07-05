Title: Python behind the scenes #11: how the Python import system works
Date: 2021-06-22 6:06
Tags: Python behind the scenes, Python, CPython

If you ask me to name the most misunderstood feature of Python, I will answer without a second thought: the Python import system. Just remember how many times you used relative imports and got something like `ImportError: attempted relative import with no known parent package`; or tried to figure out how to structure a project so that all the imports work correctly; or hack `sys.path` when you couldn't find a better solution. Many Python programmers had such experiences. A number of popular questions on StackOverflow, like [Importing files from different folder](https://stackoverflow.com/questions/4383571/importing-files-from-different-folder) (1822 votes), [Relative imports in Python 3](https://stackoverflow.com/questions/16981921/relative-imports-in-python-3) (1064 votes) and [Relative imports for the billionth time](https://stackoverflow.com/questions/14132789/relative-imports-for-the-billionth-time) (993 votes), is a good inidcator of that.

The goal of this post is to get the full picture of the Python import system and understand the reasoning behind its design. We'll see what exactly happens when Python executes an import statement, and this, I hope, will help you solve the import problems much more effectively or avoid them altogether. Let's go!

## Modules and module objects

Consider a simple import statement:

```python
import m
```

What do you think it does? Intuitively, it tells Python to import a module named `"m"` and assign the module to the variable `m`. But this explanation leaves unclear what a module is and what the variable `m` is set to exactly. What the statement `import m` actually does is tell Python to find a module named `"m"`, create a module object for that module, and assign the module object to the variable `m`. 

A **module** is anything that Python considers a module and knows how to create a module object for. This includes things like Python files, directories and built-in modules written in C. We'll discuss the full list a bit later.

The primary reason to import any module is to get an access to the functions, classes, constants and other names that the module defines. These names must be stored somewhere, and this is what module objects are for. A **module object** is a Python object that acts as a namespace for the module's names. The names are stored in the module object's dictionary (available as `m.__dict__`), so we can access them as attributes. 

Beware that the term "module" is often applied to module objects as well.

If you wonder how module objects are implemented, here's the definition from [`Objects/moduleobject.c`](https://github.com/python/cpython/blob/3.9/Objects/moduleobject.c):

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

The `md_dict` field stores the module's dictionary. Other fields are not really important for our discussion.

To see that there is nothing magical about module objects, let's create one. We usually create objects by calling their types, like `MyClass()` or `set()`. The type of module objects is `PyModule_Type` in the C code but it's not available in Python as a built-in. Fortunately, such "unavailable" types can be found in the [`types`](https://docs.python.org/3/library/types.html) standard module:

```pycon
$ python -q
>>> from types import ModuleType
>>> ModuleType
<class 'module'>
```

Another way to get `ModuleType` in Python is to import some module and then call `type()` on the module object returned:

```pycon
>>> import sys
>>> ModuleType = type(sys)
>>> ModuleType
<class 'module'>
```

This is, by the way, how the `types` module defines `ModuleType`.

Finally, we create a module object:

```pycon
>>> m = ModuleType('m')
>>> m
<module 'm'>
```

A newly created module object is not very interesting but has some special attributes preinitialized:

```pycon
>>> m.__dict__
{'__name__': 'm', '__doc__': None, '__package__': None, '__loader__': None, '__spec__': None}
```

Most of these special attributes are mainly used by the import system itself. Programmers are most likely to be familiar with the `__name__` attribute. It's often used to get the name of the current module:

```pycon
>>> __name__
'__main__'
```

Notice that `__name__` is available as a global variable. This is because the dictionary of global variables is always set to the dictionary of the current module:

```pycon
>>> import sys
>>> current_module = sys.modules[__name__] # sys.modules stores loaded modules
>>> current_module.__dict__ is globals()
True
```

The current module acts as a namespace for the execution of Python code. When Python imports a Python file, it creates a new module object and then executes the contents of the file using the dictionary of the module object as the dictionary of global variables. Similarly, when Python executes a Python file as a script, it first creates a special module called `"__main__"` and then uses its dictionary as the dictionary of global variables. Thus, global variables are always attributes of some module, and this module is considered to be the **current module**. 

## Different kinds of modules

By default, Python recognizes the following things as modules:

1. Built-in modules.
2. Frozen modules.
3. C extensions.
4. Python files.
5. Directories.

Built-in modules are a part of the `python` executable. They are written in C and typically located in the [`Modules/`](https://github.com/python/cpython/tree/3.9/Modules) directory. The `array`, `itertools`, `math` and `sys` modules are all examples of built-in modules. 

Frozen modules are too a part of the `python` executable, but they are written in Python. Python code is compiled to a code object and then the binary representation of the code object is incorporated into the executable. The `_frozen_importlib` and `_frozen_importlib_external` modules are rare examples of frozen modules. They are the modules that implement the core of the import system. Python freezes them because it cannot import them as other Python files.

C extensions allow us to write our own modules in C or C++ via the [Python/C API](https://docs.python.org/3/c-api/index.html). They are [shared libraries](https://stackoverflow.com/questions/9688200/difference-between-shared-objects-so-static-libraries-a-and-dlls-so) (.so) that expose a so called [initialization function](https://docs.python.org/3/extending/building.html#c.PyInit_modulename). The primary reason to write C extensions is performance. Computational intensive libraries, such as `numpy`, hide a bunch of C extensions under the hood.

## Submodules and packages

We tell Python what modules to import by specifying module names. If module names were limited to simple identifiers like `"mymodule"` or `"utils"`, then all names must have been unique, and we would have to think very hard every time we give a new file a name. For this reason, Python allows modules to have submodules and module names to contain dots.

When Python executes this statements:

```python
import a.b
```

it first imports the module `"a"` and then the submodule `"a.b"`. It adds the submodule to the module's dictionary and assigns the module to the variable `a`, so we can access the submodule as a module's attribute (`a.b`).

A module that can have submodules is called a **package**. Technically, a package is a module that has a `__path__` attribute. This attribute tells Python where to look for submodules. When Python imports a top-level module, it looks up the appropriately named Python file, directory and C extension in the directories listed in `sys.path`. But when it imports a submodule, it uses the `__path__` attribute of the parent module instead of `sys.path`.

### Regular packages

Directories are the most common way to organize modules into packages. If a directory contains a `__init__.py` file, it's considered to be a **regular package**. When Python imports such a directory, it executes the `__init__.py` file, so the names defined there become the attributes of the module.

The `__init__.py` file is typically left empty or contains package-related attributes such as `__doc__` and `__version__`. It can also be used to decouple the public API of a package from its internal implementation. Suppose you develop a library with the following structure:

```text
mylibrary/
	__init__.py
	module1.py
	module2.py
```

And you want to provide the users of your library with two functions: `func1()` defined in `module1.py` and `func2()` defined in `module2.py`. If you left `__init__.py` empty, then the users must specify the submodules to import the functions:

```python
from mylibrary.module1 import func1
from mylibrary.module2 import func2
```

It may be something you want, but you may also want to allow the users to import the functions like this:

```
from mylibrary import func1, func2
```

So you import `func1()` and `func2()` in `__init__.py`:

```python
# mylibrary/__init__.py
from mylibrary.module1 import func1
from mylibrary.module2 import func2
```

And the users are happy.

### Namespace packages

Before version 3.3, Python had only regular packages. Directories without `__init__.py` were not considered packages at all. And this was a problem because [people didn't like](https://mail.python.org/pipermail/python-dev/2006-April/064400.html) to create empty `__init__.py` files.

The problem was solved with the introduction of **namespace packages** in [PEP 420](https://www.python.org/dev/peps/pep-0420/). But namespace packages solved another problem as well. They allowed developers to place contents of a package across multiple locations.

If you have the following directory structure:

```text
mylibs/
	company_name/
		package1/...
morelibs/
	company_name/
		package2/...
```

And both `mylibs` and `morelibs` are in `sys.path`, then you can import both `package1` and `package2` like this:

```pycon
>>> import company_name.package1
>>> import company_name.package2
```

This is because `company_name` is a namespace package that contains two locations:

```pycon
>>> company_name.__path__
_NamespacePath(['/morelibs/company_name', '/mylibs/company_name'])
```

How does it work? When Python traverses path entries on the path during the module search, it remebers the directories without `__init__.py` that match the module's name. If after traversing all the entries, it couldn't find a regular package, a Python file or a C extension, it creates a module object whose `__path__` contains the memorized directories.

The initial idea of requiring `__init__.py` was to prevent directories on the path (`sys.path` or `__path__`) named like `string` or `site` from shadowing standard modules. Namespace package do not shadow other modules because they have lower precedence during the module search.

## Importing from modules

Besides importing modules, we can also import module attributes using a `from <> import <>` statement like this:

```python
from module import func, Class, submodule
```

It tells Python to import a module named `"module"` and assign the specified attributes to the corresponding variables:

```python
func = module.func
Class = module.Class
submodule = module.submodule
```

Note that the `module` variable is not available after the import as if it was deleted:

```python
del module
```

When Python sees that a module doesn't have a specified attribute, it considers the attribute to be a submodule and tries to import it. If, in our example, the module defines `func` and `Class` but not `submodule`, then Python will try to import `"module.submodule"`.

## Relative imports

Up until now we've been telling Python what modules to import by specifying absolute module names. The `from <> import <>` statement allows us to specify relative module names. Here are a few examples:

```python
from . import a
from .. import a
from .a import b
from ..a.b import c
```

The constructions like `.` and `..a.b` are relative module names, but what are they relative to? As we said, a Python file is executed in the context of the current module whose dictionary acts as a dictionary of global variables. The current module, as any other module, can belong to a package. This package is considered to be the **current package**, and this is what relative module names are relative to.

The `__package__` attribute of a module stores the name of the package to which the module belongs. If a module is a package, then the module belongs to itself, and  `__package__` is just the module's name (`__name__`). If the module is a submodule, then it belongs to the parent module, and `__package__` is set to the parent module's name. Finally, if the module is not a package nor a submodule, then its package is undefined. In this case, `__package__` can be set to an empty string or `None`.

A relative module name is a module name preceeded by some number of dots. One leading dot represents the current package. So, when `__package__` is defined, the following statement:

```python
from . import a
```

works as if the dot was replaced with the value of `__package__`.

Each extra dot tells Python to move one level up from `__package__` . If `__package__` is set to `"a.b"`, then this statement: 

```
from .. import d
```

works as if the dots were replaced with `a`.

You cannot move outside the top-level package. If you try this:

```
from ... import e
```

Python will throw an error:

````text
ImportError: attempted relative import beyond top-level package
````

This is because Python does not move through the file system to resolve relative imports. It just takes the value of `__package__`, strips some suffix and appends the new one to get the absolute module name.

Obviously, relative imports break when `__package__` is not defined at all. In this case, you get the following error:

```text
ImportError: attempted relative import with no known parent package
```

You most commonly see it when you run a Python file with relative imports as a script. This is because the code is executed in the `"__main__"` module whose `__package__` attribute is set to `None`.

Note that "parent package" is the term that Python uses to denote the current package.

## Desugaring the import statement

If we desugar any import statement, we'll see that it eventually calls the built-in [`__import__()`](https://docs.python.org/3/library/functions.html#__import__) function to import modules. This function takes the module's name and a bunch of other parameters, finds the module and returns a module object for it. At least, this is what it's supposed to do.

Python allows us to set `__import__()` to a custom function, so we can change the import process completely. Here's a change that just breaks everything:

```
>>> import builtins
>>> builtins.__import__ = None
>>> import math
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
TypeError: 'NoneType' object is not callable
```

However, you don't really see people overriding `__import__()` for reasons other than logging or debugging. This is because the default implementation already provides powerfull mechanisms for customization.

The default implementation of `__import__()` is the `importlib.__import__()` function. Well, not quite. You see, `importlib` is a standard module that implements the core of the import system. It's written in Python because the import process involves path handling and other things that you would prefer to do in Python rather than in C. But some functions of `importlib` are ported to C for performance reasons. And default `__import__()` actually calls a C port of `importlib.__import__()`.

Let's now see how various import statements are expressed via `__import__()` so that afterwards we can focus solely on this function.

### Simple imports

How can we find out what a Python statement does? Recall that a piece of Python code is executed in two steps:

1. The [compiler]({filename}/blog/python_bts_02.md) compiles the code to bytecode.
2. The [VM]({filename}/blog/python_bts_01.md) executes the bytecode.

So to see what a statement does, we can look at the bytecode produced for it and then find out what each bytecode instruction does by looking at the [evaluation loop]({filename}/blog/python_bts_04.md) in [`Python/ceval.c`](https://github.com/python/cpython/blob/3.9/Python/ceval.c).

To get the bytecode, we use the [`dis`](https://docs.python.org/3/library/dis.html) standard module:

```text
$ echo "import m" | python -m dis
  1           0 LOAD_CONST               0 (0)
              2 LOAD_CONST               1 (None)
              4 IMPORT_NAME              0 (m)
              6 STORE_NAME               0 (m)
...
```

The first [`LOAD_CONST`](https://docs.python.org/3/library/dis.html#opcode-LOAD_CONST) instruction pushes `0` onto the value stack. The second `LOAD_CONST` pushes `None`. Then the `IMPORT_NAME` instruction does something we'll look into in a moment. Finally, [`STORE_NAME`](https://docs.python.org/3/library/dis.html#opcode-STORE_NAME) assigns the value on top of the value stack to the variable `m`.

The code that executes the `IMPORT_NAME` instruction looks as follows:

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

The `import_name()` function calls `__import__()` to do the work. But if `__import__()` wasn't overriden, it takes a shortcut and calls the C port of `importlib.__import__()` called `PyImport_ImportModuleLevelObject()`. Here's `import_name()` for the sake of completeness:

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

If you analyze how the arguments are prepared and passed, you'll be able to conclude that this statement:

```
import m
```

is actually equivalent to this code:

```python
m = __import__("m", globals(), locals(), None, 0)
```

The meaning of the arguments is explained in the docsting of `importlib.__import__()`:

```python
def __import__(name, globals=None, locals=None, fromlist=(), level=0):
    """Import a module.

    The 'globals' argument is used to infer where the import is occurring from
    to handle relative imports. The 'locals' argument is ignored. The
    'fromlist' argument specifies what should exist as attributes on the module
    being imported (e.g. ``from module import <fromlist>``).  The 'level'
    argument represents the package location to import from in a relative
    import (e.g. ``from ..pkg import mod`` would have a 'level' of 2).

    """
```

As we've said, all import statements eventually call `__import__()` to import modules. They only differ in what they do before and after the call and how they make the call. The `from <> import <>` statements, for example, pass non-empty `fromlist`, and relative imports pass non-zero `level`.

Let's now express other import statements via `__import__()` as we did for a simple `import m` statement. We'll do it much faster this time, though.

### Importing submodules

This statement:

```python
import a.b.c
```

compiles to the following bytecode:

```text
$ echo "import a.b.c" | python -m dis  
  1           0 LOAD_CONST               0 (0)
              2 LOAD_CONST               1 (None)
              4 IMPORT_NAME              0 (a.b.c)
              6 STORE_NAME               1 (a)
...
```

and is equivalent to the following code:

```python
a = __import__('a.b.c', globals(), locals(), None, 0)
```

Note that the arguments to ` __import__()` are passed in the same way as in the case of `import m`. The only difference is that the VM assigns the result of `__import__()` not to the name of the module (`a.b.c` is not a valid variable name) but to the first identifier before the dot, i.e. `a`. As we would expect, `__import__()` returns the top-level module in this case.

### from <> import <>

This statement:

```python
from a.b import f, g
```

compiles to the following bytecode:

```text
$ echo "from a.b import f, g" | python -m dis  
  1           0 LOAD_CONST               0 (0)
              2 LOAD_CONST               1 (('f', 'g'))
              4 IMPORT_NAME              0 (a.b)
              6 IMPORT_FROM              1 (f)
              8 STORE_NAME               1 (f)
             10 IMPORT_FROM              2 (g)
             12 STORE_NAME               2 (g)
             14 POP_TOP
...
```

and is equivalent to the following code:

```python
a_b = __import__('a.b', globals(), locals(), ('f', 'g'), 0)
f = a_b.f
g = a_b.g
del a_b
```

Note that the names to import are passed as `fromlist`. When `fromlist` is not empty, `__import__()` returns not the top-level module as in the case of a simple import but the specifed module like `a.b`.

### Relative imports

This statement:

```python
from .. import f
```

compiles to the following bytecode

```text
$ echo "from .. import f" | python -m dis
  1           0 LOAD_CONST               0 (2)
              2 LOAD_CONST               1 (('f',))
              4 IMPORT_NAME              0
              6 IMPORT_FROM              1 (f)
              8 STORE_NAME               1 (f)
             10 POP_TOP
```

and is equivalent to the following code:

```python
m = __import__('', globals(), locals(), ('f'), 2)
f = m.f
del m
```

The `level` argument tells `__import__()` how many leading dots the relative import has. Since it's set to `2`, `__import__()` calculates the absolute name of the module by (1) taking the value of `__package__` and (2) stripping its last portion. The `__package__` attribute is available to `__import__()` because it's passed with `globals()`.

Now let's see how `__import__()` works. 

## Inside \__import__()

The algorithm that `__import__()` implements can be summarized as follows:

1. If `level > 0`, resolve a relative module name to an absolute one. 
2. Import the module.
3. If `fromlist` is empty, slice the module name up to the first dot to get the top-level module name. Import and return the top-level module.
4. If `fromlist` contains names that are not in the module's dictionary, import them as submodules. If `"*"`  is in `fromlist`, use module's `__all__` as new `fromlist` and repeat this step.
5. Return the module.

Step 2 is where all the action happens. We'll focus on it in the remaining sections, but let us first elaborate on step 1.

### Resolving relative names

To resolve a relative module name, `__import__()` needs to know the current package of the module from which the import statement was executed. So it looks up `__package__` in `globals`. If `__package__` is `None`, `__import__()` tries to deduce the current package from `__name__`. Since Python always sets `__package__` correctly, this fallback is typically unnecessary. It can only be useful for modules originated by other means. All we should remember is that relative imports break when `__package__` is set to an empty string, as in the case of a top-level module, or to `None`, as in the case of a script, and have a chance of succeeding otherwise. You can look at the [`_calc___package__()`](https://github.com/python/cpython/blob/57c6cb5100d19a0e0218c77d887c3c239c9ce435/Lib/importlib/_bootstrap.py#L1090) function to see how the current package is calculated exactly.

Once the current package is calculated, `__import__()` checks whether it got well-formed arguments:

```python
# Lib/importlib/_bootstrap.py

def _sanity_check(name, package, level):
    """Verify arguments are "sane"."""
    if not isinstance(name, str):
        raise TypeError('module name must be str, not {}'.format(type(name)))
    if level < 0:
        raise ValueError('level must be >= 0')
    if level > 0:
        if not isinstance(package, str):
            raise TypeError('__package__ not set to a string')
        elif not package:
            raise ImportError('attempted relative import with no known parent '
                              'package')
    if not name and level == 0:
        raise ValueError('Empty module name')
```

and, finally, resolves the relative name:

```python
# Lib/importlib/_bootstrap.py

def _resolve_name(name, package, level):
    """Resolve a relative module name to an absolute one."""
    # strip last `level - 1` portions of `package`
    bits = package.rsplit('.', level - 1)
    if len(bits) < level:
        # stripped less than `level - 1` portions
        raise ImportError('attempted relative import beyond top-level package')
    base = bits[0]
    return '{}.{}'.format(base, name) if name else base
```

Now let's discuss how modules are imported.

### The import process

The function that imports modules is called [`_find_and_load()`](https://github.com/python/cpython/blob/57c6cb5100d19a0e0218c77d887c3c239c9ce435/Lib/importlib/_bootstrap.py#L1022). It takes an absolute module name and performs the following steps:

1. If the module is in `sys.modules`, return it.
2. Initialize the path to search for the module to `None`.
3. If the module has a parent module (the name contains at least one dot), import the parent module if it's not in `sys.modules` yet. Set the path to parent's `__path__`.
4. Find the module's spec using the module's name and the path. If the spec is not found, raise `ModuleNotFoundError`.
5. Load the module from the spec.
6. Add the module to the dictionary of the parent module.
7. Return the module.

All imported modules are stored in the `sys.modules` dictionary. This dictionary maps module names to module objects and acts as a cache. Before searching for a module, `_find_and_load() ` checks `sys.modules` and returns the module immideatly if it's there. Modules are added to `sys.module` at the end of step 5.

If the module wasn't found in `sys.modules`, `_find_and_load() `  proceeds with importing the module. The import process consists of finding the module and loading the module. Finders and loaders are objects that perform these tasks.

### Finders and loaders

The job of a **finder** is to make sure that the module exists, determine which loader should be used for loading the module and provide the information needed for loading, such as module's location. The job of a **loader** is to load the module, that is, to create a module object for the module and execute the module. The same object can function both as a finder and as a loader. Such an object is called an **importer**.

Finders implement the `find_spec()` method that takes a module name and a path to search for the module and returns a module spec. A **module spec** is an object that encapsulates the loader and all the information needed for loading. This includes module's special attributes, such as `__name__`,  `__path__` and `__package__`. They are simply copied from the spec after the module object is created. The full list of spec attributes can be found in [the docs](https://docs.python.org/3/library/importlib.html#importlib.machinery.ModuleSpec).

To find a module spec, `_find_and_load()` iterates over the finders listed in `sys.meta_path` and calls `find_spec()` on each one until the spec is found. If the spec is not found, it raises `ModuleNotFoundError`.

By default, `sys.meta_path` stores three finders:

1. `BuiltinImporter` that works with built-in modules
2. `FrozenImporter` that works with frozen modules; and
3. `PathFinder` that works with Python files, directories and C extensions.

These are called **meta path finders**. Python differentiates them from **path entry finders** that are a part of `PathFinder`. We'll see how different finders work in the next sections.

To create a module object, `_find_and_load()`  calls the loader's `create_module()` method that takes a module spec and returns a module object. If this method is not implemented or returns `None`, then `__import__()` creates the new module object itself. If the module object does not define some special attributes, which is usually the case, the attributes are copied from the spec. Here's how this logic is implemented in the code:

```python
def module_from_spec(spec):
    """Create a module based on the provided spec."""
    # Typically loaders will not implement create_module().
    module = None
    if hasattr(spec.loader, 'create_module'):
        # If create_module() returns `None` then it means default
        # module creation should be used.
        module = spec.loader.create_module(spec)
    elif hasattr(spec.loader, 'exec_module'):
        raise ImportError('loaders that define exec_module() '
                          'must also define create_module()')
    if module is None:
        # _new_module(name) returns type(sys)(name)
        module = _new_module(spec.name)
    
    # copy undefined module attributes (__loader__, __package__, etc.)
    # from the spec
    _init_module_attrs(spec, module)
    return module
```

After creating the module object, `_find_and_load()`  executes the module by calling the loader's `exec_module()` method. What this method does depends on the loader, but typically it populates the module's dictionary with functions, classes, constants and other things that the module defines. The loader for Python files, for example, executes the contents of the file when `exec_module()` is called.

The full loading process is implemented as follows:

```python
def _load_unlocked(spec):
    # ... compatibility stuff

    module = module_from_spec(spec)

    # needed for parallel imports
    spec._initializing = True
    try:
        sys.modules[spec.name] = module
        try:
            if spec.loader is None:
                if spec.submodule_search_locations is None:
                    raise ImportError('missing loader', name=spec.name)
                # A namespace package so do nothing.
            else:
                spec.loader.exec_module(module)
        except:
            try:
                del sys.modules[spec.name]
            except KeyError:
                pass
            raise
        # Move the module to the end of sys.modules.
        # this is to maintain the import order;
        # remember that Python dicts are ordered?
        module = sys.modules.pop(spec.name)
        sys.modules[spec.name] = module
        _verbose_message('import {!r} # {!r}', spec.name, spec.loader)
    finally:
        spec._initializing = False

    return module
```

This piece of code is interesting for several reasons. First, a module is added to `sys.modules` before it is executed. Due to this logic, Python supports circular imports. If we have two modules that import each other like this:

```python
# a.py
import b

X = "some constant"
```

```python
# b.py
import a
```

We can import them without any issues:

```pycon
$ python -q
>>> import a
>>> 
```

The catch is that the module `a` is only partially initialized when the module `b` is executed. So if we use `X` in `b`: 

```python
# b.py
import a

print(X)
```

we get an error:

```pycon
$ python -q
>>> import a
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
  File "/a.py", line 1, in <module>
    import b
  File "/b.py", line 3, in <module>
    print(X)
NameError: name 'X' is not defined
```

Second, a module is removed from `sys.modules` if the execution fails for any reason, but modules that were successfully imported as a side-effect remain in `sys.modules`.

Finally, the module in `sys.modules` can be replaced during the module execution. Thus, the module is looked up in `sys.modules` before it's returned.

We're now done with `_find_and_load()` and `__import__()` and ready to see how different finders and loaders work. We begin with `PathFinder` since it's a meta path finder that application developers should care about the most.

## PathFinder

`PathFinder` searches for Python files, directories and C extensions on the path. The path is passed as an argument to `find_spec() ` and set to parent's `__path__`. If it's `None`, as in the case of a top-level module, `sys.path` is used for the path instead.

`PathFinder` doesn't do the search itself but delegates this work to path entry finders. For each entry on the path, it 

## C modules

