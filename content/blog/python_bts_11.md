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

Okay. We can always access attributes defined in the current module and we can import other modules to access their attributes. Let's now see how Python executes the import statement.

## Desugaring the import statement

