Title: Python behind the scenes #3: stepping through the CPython source code
Date: 2020-09-28 5:59
Tags: Python behind the scenes, Python, CPython

In the first and the second parts of this series we've explored the ideas behind the execution and the compilation of a Python program. We'll continue to focus on ideas in the next parts but this time we'll make an exception and look at the actual code that brings those ideas to life. 

### Plan for today

The CPython codebase is around 350,000 lines of C code (excluding header files) and almost 600,000 lines of Python code. Undoubtedly, it would be a daunting task to comprehend all of that at once. So, today we'll confine our study to that part of the source code that executes on every run. We'll start with the `main` function of the `python` executable and step through the source code until we reach the evaluation loop, a place where the Python bytecode gets executed.

Our goal is not to understand every piece of code we'll encounter but to highlight the most interesting parts, study them, and, eventually, get an approximate idea of what happens at the very start of the execution of a Python program.

There are few more notices I should make. First, we won't step into every function. We'll make only a high-level overview of some parts and dive deep into others. Nevertheless, I promise to present functions in the order of execution. Second, to save our time and attention, we'll omit large chunks of code that deal with such things as error handling and memory managment. Third, I allow myself to rephrase some comments if it makes code clearer. With that said, let's begin our journey through the CPython source code.

### Getting CPython

Before we can explore the source code, we need to get it. Let's clone the CPython repository:

```text
$ git clone https://github.com/python/cpython/ && cd cpython
```

The current `master` branch is the future CPython 3.10. We're interested in the latest stable release, which is CPython 3.9, so let's switch to the `3.9` branch:

```text
$ git checkout 3.9
```

Inside the root directory we find the following contents:

```text
$ ls -p
CODE_OF_CONDUCT.md      Objects/                config.sub
Doc/                    PC/                     configure
Grammar/                PCbuild/                configure.ac
Include/                Parser/                 install-sh
LICENSE                 Programs/               m4/
Lib/                    Python/                 netlify.toml
Mac/                    README.rst              pyconfig.h.in
Makefile.pre.in         Tools/                  setup.py
Misc/                   aclocal.m4
Modules/                config.guess
```

Some of the listed subdirectories are of particular importance to us in the course of this series:

* `Grammar/` contains the grammar files we discussed last time.
* `Include/` contains header files. These header files are used both by CPython and by the users of the [Python/C API](Python/C API).
* `Lib/` contains standard library modules written in Python. While some modules, such as ` argparse` and `wave`, are written in Python entirely, many wrap C code. For example, the Python `io` module  wraps the C `_io` module .
* `Modules/` contains standard library modules written in C. While some modules, such as `itertools`, are intended to be imported directly, others are wrapped by the Python modules.
* `Objects/` contains the implementations of the built-in types. If you want to understand how `string` or `list` are implemented, this is the ultimate place to go to.
* `Parser/` contains the old parser, the old parser generator, the new parser and the tokenizer.
* `Programs/` contains source files that are compiled as executables. 
* `Python/` contains source files for the interpreter itself. This includes the compiler, the evaluation loop, the `builtin` module and many other interesting things.
* `Tools/` contains tools useful for building and managing CPython. For example, the new parser generator lives here.

In the ideal world, all we need to do to compile CPython is to run `./configure` and `make`:

```text
$ ./configure
```

```
$ make -j -s
```

 `make` will produce an executable called `python`. Don't be suprised to see `python.exe` on Mac OS. The `.exe` extension is used to distinguish the executable from the `Python/` directory on the case-insensitive filesystem. Check out the Python Developer's Guide for [more information on compiling](https://devguide.python.org/setup/#compiling).

At this point we can proudly say that we've built our own copy of CPython:

```text
$ ./python.exe
Python 3.9.0rc2+ (heads/3.9-dirty:bdf46bc7e1, Sep 29 2020, 12:44:38) 
[Clang 10.0.0 (clang-1000.10.44.4)] on darwin
Type "help", "copyright", "credits" or "license" for more information.
>>> 2 ** 16
65536
```

### Source code

The execution of CPython, like execution of any other C program, starts with the `main` function in `Python/python.c`:

```C
/* Minimal main program -- everything is loaded from the library */

#include "Python.h"

#ifdef MS_WINDOWS
int
wmain(int argc, wchar_t **argv)
{
    return Py_Main(argc, argv);
}
#else
int
main(int argc, char **argv)
{
    return Py_BytesMain(argc, argv);
}
#endif
```

There isn't much going on there. The only thing worth mentioning is that on Windows CPython uses [`wmain`](https://docs.microsoft.com/en-us/cpp/c-language/using-wmain?view=vs-2019) instead of `main` as an entrypoint to receive `argv` as `UTF-16` encoded strings. The affect of this is that on other platforms CPython performs an additional step of converting a `char` string to a `wchar_t` string. The input encoding depends on the locale settings, and the output encoding depends on the size of `w_char`. For example, if `sizeof(wchar_t) == 4`, the `UCS-4` encoding is used.

We find `Py_Main` and `Py_BytesMain` in `Modules/main.c`. What they do is essentially call `pymain_main` with slightly different arguments:

```C
int
Py_Main(int argc, wchar_t **argv)
{
    _PyArgv args = {
        .argc = argc,
        .use_bytes_argv = 0,
        .bytes_argv = NULL,
        .wchar_argv = argv};
    return pymain_main(&args);
}


int
Py_BytesMain(int argc, char **argv)
{
    _PyArgv args = {
        .argc = argc,
        .use_bytes_argv = 1,
        .bytes_argv = argv,
        .wchar_argv = NULL};
    return pymain_main(&args);
}
```

We should discuss `pymain_main` in more detail, though, at the first sight, it doesn't seem to do much either:

```C
static int
pymain_main(_PyArgv *args)
{
    PyStatus status = pymain_init(args);
    if (_PyStatus_IS_EXIT(status)) {
        pymain_free();
        return status.exitcode;
    }
    if (_PyStatus_EXCEPTION(status)) {
        pymain_exit_error(status);
    }

    return Py_RunMain();
}
```

Last time we learned that before a Python program starts executing, CPython does a lot of things to compile it. It turns out that CPython does a lot of things even before it starts compiling a program. Those things constitute the initialization of CPython. We've already mentioned in the first part that CPython works in three stages:

1. initialization
2. compilation; and
3. interpretation.

So, what `pymain_main` does is call `pymain_init(args)` to perform the initialization and then call `Py_RunMain()` to proceed with the next stages. The question remains: what does CPython do during the initialization? It's not that hard to answer. At the very least CPython has to:

* find a common language with the OS to handle properly the encodings of arguments, environment variables, standard streams and the file system
* parse the command line arguments and read the environment variables to determine the options to run with
* configure the standard streams
* initialize the runtime state, the main interpreter state and the main thread state
* initialize built-in types and the `builtins` module
* initialize the `sys` module
* set up the import system
* create the `__main__` module.

Before we step into `pymain_init` to see how all of that is done, let's discuss the initialization process in more detail.

#### initialization

Starting with CPython 3.8, the initialization is done in three distinct phases:

1. preinitialization
2. core initialization; and
3. main initialization.

The phases gradually intoduce new capabilities. The preinitialization phase initializes the runtime state, sets up the default memory allocator and performs very basic configuration. There is no sign of Python yet. The core initialization phase initializes the main interpreter state and the main thread state, built-in types and exceptions, the `builtins` module, the `sys` module and the import system. At this point, you can use the "core" of Python. Tough, some things are not available yet. For example, the `sys` module is only partially initialized, and only the import of built-in and frozen modules is supported. After the main initialization phase the CPython is fully initialized and ready to compile and execute a Python program.

What's the benefit of having distinct initialization phases? In a nutshell, they allow to tune CPython more easily. For example, one may set a custom memory allocator in the `preinitialized` state or override the path configuration in the `core_initialized` state. Of course, CPython itself doesn't need to tune anything. Such capabilities are important to the users of the Python/C API who extend and embed Python.

The `pymain_init` function mostly deals with the preinitialization and calls `Py_InitializeFromConfig(&config)` in the end to perform the core and the main phases of the initialization:

```C
static PyStatus
pymain_init(const _PyArgv *args)
{
    PyStatus status;

    status = _PyRuntime_Initialize();
  	// ... handle errors

    PyPreConfig preconfig;
    PyPreConfig_InitPythonConfig(&preconfig);

    status = _Py_PreInitializeFromPyArgv(&preconfig, args);
  	// ... 

    PyConfig config;
    PyConfig_InitPythonConfig(&config);

    // read config from command line arguments, environment variables, configuration files
    if (args->use_bytes_argv) {
        status = PyConfig_SetBytesArgv(&config, args->argc, args->bytes_argv);
    }
    else {
        status = PyConfig_SetArgv(&config, args->argc, args->wchar_argv);
    }
    // ... 

  	// preinitialized, perform core and main initialization
    status = Py_InitializeFromConfig(&config);
	// ... 

    return status;
}
```

`_PyRuntime_Initialize` initializes the runtime. The runtime is represented partly by the runtime state and partly by other global variables such as those that hold the memory allocators. The runtime state is stored in the global variable called `_PyRuntime` of type `_PyRuntimeState`, which is defined as follows:

```C
/* Full Python runtime state */

typedef struct pyruntimestate {
    /* Is running Py_PreInitialize()? */
    int preinitializing;

    /* Is Python preinitialized? Set to 1 by Py_PreInitialize() */
    int preinitialized;

    /* Is Python core initialized? Set to 1 by _Py_InitializeCore() */
    int core_initialized;

    /* Is Python fully initialized? Set to 1 by Py_Initialize() */
    int initialized;

    /* Set by Py_FinalizeEx(). Only reset to NULL if Py_Initialize() is called again. */
    _Py_atomic_address _finalizing;

    struct pyinterpreters {
        PyThread_type_lock mutex;
        PyInterpreterState *head;
        PyInterpreterState *main;
        int64_t next_id;
    } interpreters;

    unsigned long main_thread;

    struct _ceval_runtime_state ceval;
    struct _gilstate_runtime_state gilstate;

    PyPreConfig preconfig;

    // less interesting stuff for now...
} _PyRuntimeState;
```

The last field `preconfig` holds the configuration that is used to preinitialize CPython. It's also used by the next phase to complete the configuration. Here's the extensively commented definition of `PyPreConfig`:

```C
typedef struct {
    int _config_init;     /* _PyConfigInitEnum value */

    /* Parse Py_PreInitializeFromBytesArgs() arguments?
       See PyConfig.parse_argv */
    int parse_argv;

    /* If greater than 0, enable isolated mode: sys.path contains
       neither the script's directory nor the user's site-packages directory.

       Set to 1 by the -I command line option. If set to -1 (default), inherit
       Py_IsolatedFlag value. */
    int isolated;

    /* If greater than 0: use environment variables.
       Set to 0 by -E command line option. If set to -1 (default), it is
       set to !Py_IgnoreEnvironmentFlag. */
    int use_environment;

    /* Set the LC_CTYPE locale to the user preferred locale? If equals to 0,
       set coerce_c_locale and coerce_c_locale_warn to 0. */
    int configure_locale;

    /* Coerce the LC_CTYPE locale if it's equal to "C"? (PEP 538)

       Set to 0 by PYTHONCOERCECLOCALE=0. Set to 1 by PYTHONCOERCECLOCALE=1.
       Set to 2 if the user preferred LC_CTYPE locale is "C".

       If it is equal to 1, LC_CTYPE locale is read to decide if it should be
       coerced or not (ex: PYTHONCOERCECLOCALE=1). Internally, it is set to 2
       if the LC_CTYPE locale must be coerced.

       Disable by default (set to 0). Set it to -1 to let Python decide if it
       should be enabled or not. */
    int coerce_c_locale;

    /* Emit a warning if the LC_CTYPE locale is coerced?

       Set to 1 by PYTHONCOERCECLOCALE=warn.

       Disable by default (set to 0). Set it to -1 to let Python decide if it
       should be enabled or not. */
    int coerce_c_locale_warn;

#ifdef MS_WINDOWS
    /* If greater than 1, use the "mbcs" encoding instead of the UTF-8
       encoding for the filesystem encoding.

       Set to 1 if the PYTHONLEGACYWINDOWSFSENCODING environment variable is
       set to a non-empty string. If set to -1 (default), inherit
       Py_LegacyWindowsFSEncodingFlag value.

       See PEP 529 for more details. */
    int legacy_windows_fs_encoding;
#endif

    /* Enable UTF-8 mode? (PEP 540)

       Disabled by default (equals to 0).

       Set to 1 by "-X utf8" and "-X utf8=1" command line options.
       Set to 1 by PYTHONUTF8=1 environment variable.

       Set to 0 by "-X utf8=0" and PYTHONUTF8=0.

       If equals to -1, it is set to 1 if the LC_CTYPE locale is "C" or
       "POSIX", otherwise it is set to 0. Inherit Py_UTF8Mode value value. */
    int utf8_mode;

    /* If non-zero, enable the Python Development Mode.

       Set to 1 by the -X dev command line option. Set by the PYTHONDEVMODE
       environment variable. */
    int dev_mode;

    /* Memory allocator: PYTHONMALLOC env var.
       See PyMemAllocatorName for valid values. */
    int allocator;
} PyPreConfig;
```

