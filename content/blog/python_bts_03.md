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

If you don't see a directory for tests, and your heart starts beating faster, relax. It's `Lib/test/`. Tests are useful not only for CPython development but also for getting an understanding of how CPython works. For example, to understand what kinds of optimization the peephole optimizer must do, you can go to `Lib/test/test_peepholer.py` and look. And to understand what some piece of code of the peephole optimizer does, you can delete it, recompile CPython, run 

```text
$ ./python.exe -m test test_peepholer
```

and see which tests fail.

In the ideal world, all we need to do to compile CPython is to run `./configure` and `make`:

```text
$ ./configure
```

```
$ make -j -s
```

 `make` will produce an executable named `python`, but don't be suprised to see `python.exe` on Mac OS. The `.exe` extension is used to distinguish the executable from the `Python/` directory on the case-insensitive filesystem. Check out the Python Developer's Guide for [more information on compiling](https://devguide.python.org/setup/#compiling).

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

We should stop on `pymain_main` for a little bit longer, though, at the first sight, it doesn't seem to do much either:

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

What's the benefit of having distinct initialization phases? In a nutshell, it allows to tune CPython more easily. For example, one may set a custom memory allocator in the `preinitialized` state or override the path configuration in the `core_initialized` state. Of course, CPython itself doesn't need to tune anything. Such capabilities are important to the users of the Python/C API who extend and embed Python. [PEP 432](https://www.python.org/dev/peps/pep-0432/) and [PEP 587](https://www.python.org/dev/peps/pep-0587/) explain in greater detail why having multi-phase initialization is a good idea.

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

`_PyRuntime_Initialize` initializes the runtime state. The runtime state is stored in the global variable called `_PyRuntime` of type `_PyRuntimeState`, which is defined as follows:

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

    // ... less interesting stuff for now
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

After the call to `_PyRuntime_Initialize`, the `_PyRuntime` global variable is initialized to the defaults. Next, `pymain_init` initializes `preconfig`  by calling `PyPreConfig_InitPythonConfig(&preconfig)`  and then calls `_Py_PreInitializeFromPyArgv(&preconfig, args)` to perfrom the actual preinitialization. What's the reason to initialize another `preconfig` if there is already one in `_PyRuntime`? Remember that many functions that CPython calls are also exposed via the Python/C API. So, CPython just uses this API in the way it's designed to be used. Another consequence of this is that, when stepping thought the CPython source code, as we do today, you often encounter a function that seems to do more than you expect it to do. For example, `_PyRuntime_Initialize` is called several times during the initialization process. Of course, it does nothing on the subsequent calls.

`_Py_PreInitializeFromPyArgv` reads the command line arguments, the enviroment variables and the global configuration variables to set  `_PyRuntime.preconfig`, the current locale and the memory allocator. It doesn't read all the configuration, but only those parameters that are relevant to the preinitialization phase. For example, it parses only the `-E -I -X` arguments. 

At this point, the runtime is preinitialized. The rest `pymain_init` does is prepares `config` for the next initialization phase. You should not confuse `config` with `preconfig`. `config` is a structure that holds most of the Python configuration. It's heavily used during the initialization phase and then also during the execution of a Python program. To understand how, I recommend you to look over its definition, even despite its length:

```C
/* --- PyConfig ---------------------------------------------- */

typedef struct {
    int _config_init;     /* _PyConfigInitEnum value */

    int isolated;         /* Isolated mode? see PyPreConfig.isolated */
    int use_environment;  /* Use environment variables? see PyPreConfig.use_environment */
    int dev_mode;         /* Python Development Mode? See PyPreConfig.dev_mode */

    /* Install signal handlers? Yes by default. */
    int install_signal_handlers;

    int use_hash_seed;      /* PYTHONHASHSEED=x */
    unsigned long hash_seed;

    /* Enable faulthandler?
       Set to 1 by -X faulthandler and PYTHONFAULTHANDLER. -1 means unset. */
    int faulthandler;

    /* Enable PEG parser?
       1 by default, set to 0 by -X oldparser and PYTHONOLDPARSER */
    int _use_peg_parser;

    /* Enable tracemalloc?
       Set by -X tracemalloc=N and PYTHONTRACEMALLOC. -1 means unset */
    int tracemalloc;

    int import_time;        /* PYTHONPROFILEIMPORTTIME, -X importtime */
    int show_ref_count;     /* -X showrefcount */
    int dump_refs;          /* PYTHONDUMPREFS */
    int malloc_stats;       /* PYTHONMALLOCSTATS */

    /* Python filesystem encoding and error handler:
       sys.getfilesystemencoding() and sys.getfilesystemencodeerrors().

       Default encoding and error handler:

       * if Py_SetStandardStreamEncoding() has been called: they have the
         highest priority;
       * PYTHONIOENCODING environment variable;
       * The UTF-8 Mode uses UTF-8/surrogateescape;
       * If Python forces the usage of the ASCII encoding (ex: C locale
         or POSIX locale on FreeBSD or HP-UX), use ASCII/surrogateescape;
       * locale encoding: ANSI code page on Windows, UTF-8 on Android and
         VxWorks, LC_CTYPE locale encoding on other platforms;
       * On Windows, "surrogateescape" error handler;
       * "surrogateescape" error handler if the LC_CTYPE locale is "C" or "POSIX";
       * "surrogateescape" error handler if the LC_CTYPE locale has been coerced
         (PEP 538);
       * "strict" error handler.

       Supported error handlers: "strict", "surrogateescape" and
       "surrogatepass". The surrogatepass error handler is only supported
       if Py_DecodeLocale() and Py_EncodeLocale() use directly the UTF-8 codec;
       it's only used on Windows.

       initfsencoding() updates the encoding to the Python codec name.
       For example, "ANSI_X3.4-1968" is replaced with "ascii".

       On Windows, sys._enablelegacywindowsfsencoding() sets the
       encoding/errors to mbcs/replace at runtime.


       See Py_FileSystemDefaultEncoding and Py_FileSystemDefaultEncodeErrors.
       */
    wchar_t *filesystem_encoding;
    wchar_t *filesystem_errors;

    wchar_t *pycache_prefix;  /* PYTHONPYCACHEPREFIX, -X pycache_prefix=PATH */
    int parse_argv;           /* Parse argv command line arguments? */

    /* Command line arguments (sys.argv).

       Set parse_argv to 1 to parse argv as Python command line arguments
       and then strip Python arguments from argv.

       If argv is empty, an empty string is added to ensure that sys.argv
       always exists and is never empty. */
    PyWideStringList argv;

    /* Program name:

       - If Py_SetProgramName() was called, use its value.
       - On macOS, use PYTHONEXECUTABLE environment variable if set.
       - If WITH_NEXT_FRAMEWORK macro is defined, use __PYVENV_LAUNCHER__
         environment variable is set.
       - Use argv[0] if available and non-empty.
       - Use "python" on Windows, or "python3 on other platforms. */
    wchar_t *program_name;

    PyWideStringList xoptions;     /* Command line -X options */

    /* Warnings options: lowest to highest priority. warnings.filters
       is built in the reverse order (highest to lowest priority). */
    PyWideStringList warnoptions;

    /* If equal to zero, disable the import of the module site and the
       site-dependent manipulations of sys.path that it entails. Also disable
       these manipulations if site is explicitly imported later (call
       site.main() if you want them to be triggered).

       Set to 0 by the -S command line option. If set to -1 (default), it is
       set to !Py_NoSiteFlag. */
    int site_import;

    /* Bytes warnings:

       * If equal to 1, issue a warning when comparing bytes or bytearray with
         str or bytes with int.
       * If equal or greater to 2, issue an error.

       Incremented by the -b command line option. If set to -1 (default), inherit
       Py_BytesWarningFlag value. */
    int bytes_warning;

    /* If greater than 0, enable inspect: when a script is passed as first
       argument or the -c option is used, enter interactive mode after
       executing the script or the command, even when sys.stdin does not appear
       to be a terminal.

       Incremented by the -i command line option. Set to 1 if the PYTHONINSPECT
       environment variable is non-empty. If set to -1 (default), inherit
       Py_InspectFlag value. */
    int inspect;

    /* If greater than 0: enable the interactive mode (REPL).

       Incremented by the -i command line option. If set to -1 (default),
       inherit Py_InteractiveFlag value. */
    int interactive;

    /* Optimization level.

       Incremented by the -O command line option. Set by the PYTHONOPTIMIZE
       environment variable. If set to -1 (default), inherit Py_OptimizeFlag
       value. */
    int optimization_level;

    /* If greater than 0, enable the debug mode: turn on parser debugging
       output (for expert only, depending on compilation options).

       Incremented by the -d command line option. Set by the PYTHONDEBUG
       environment variable. If set to -1 (default), inherit Py_DebugFlag
       value. */
    int parser_debug;

    /* If equal to 0, Python won't try to write ``.pyc`` files on the
       import of source modules.

       Set to 0 by the -B command line option and the PYTHONDONTWRITEBYTECODE
       environment variable. If set to -1 (default), it is set to
       !Py_DontWriteBytecodeFlag. */
    int write_bytecode;

    /* If greater than 0, enable the verbose mode: print a message each time a
       module is initialized, showing the place (filename or built-in module)
       from which it is loaded.

       If greater or equal to 2, print a message for each file that is checked
       for when searching for a module. Also provides information on module
       cleanup at exit.

       Incremented by the -v option. Set by the PYTHONVERBOSE environment
       variable. If set to -1 (default), inherit Py_VerboseFlag value. */
    int verbose;

    /* If greater than 0, enable the quiet mode: Don't display the copyright
       and version messages even in interactive mode.

       Incremented by the -q option. If set to -1 (default), inherit
       Py_QuietFlag value. */
    int quiet;

   /* If greater than 0, don't add the user site-packages directory to
      sys.path.

      Set to 0 by the -s and -I command line options , and the PYTHONNOUSERSITE
      environment variable. If set to -1 (default), it is set to
      !Py_NoUserSiteDirectory. */
    int user_site_directory;

    /* If non-zero, configure C standard steams (stdio, stdout,
       stderr):

       - Set O_BINARY mode on Windows.
       - If buffered_stdio is equal to zero, make streams unbuffered.
         Otherwise, enable streams buffering if interactive is non-zero. */
    int configure_c_stdio;

    /* If equal to 0, enable unbuffered mode: force the stdout and stderr
       streams to be unbuffered.

       Set to 0 by the -u option. Set by the PYTHONUNBUFFERED environment
       variable.
       If set to -1 (default), it is set to !Py_UnbufferedStdioFlag. */
    int buffered_stdio;

    /* Encoding of sys.stdin, sys.stdout and sys.stderr.
       Value set from PYTHONIOENCODING environment variable and
       Py_SetStandardStreamEncoding() function.
       See also 'stdio_errors' attribute. */
    wchar_t *stdio_encoding;

    /* Error handler of sys.stdin and sys.stdout.
       Value set from PYTHONIOENCODING environment variable and
       Py_SetStandardStreamEncoding() function.
       See also 'stdio_encoding' attribute. */
    wchar_t *stdio_errors;

#ifdef MS_WINDOWS
    /* If greater than zero, use io.FileIO instead of WindowsConsoleIO for sys
       standard streams.

       Set to 1 if the PYTHONLEGACYWINDOWSSTDIO environment variable is set to
       a non-empty string. If set to -1 (default), inherit
       Py_LegacyWindowsStdioFlag value.

       See PEP 528 for more details. */
    int legacy_windows_stdio;
#endif

    /* Value of the --check-hash-based-pycs command line option:

       - "default" means the 'check_source' flag in hash-based pycs
         determines invalidation
       - "always" causes the interpreter to hash the source file for
         invalidation regardless of value of 'check_source' bit
       - "never" causes the interpreter to always assume hash-based pycs are
         valid

       The default value is "default".

       See PEP 552 "Deterministic pycs" for more details. */
    wchar_t *check_hash_pycs_mode;

    /* --- Path configuration inputs ------------ */

    /* If greater than 0, suppress _PyPathConfig_Calculate() warnings on Unix.
       The parameter has no effect on Windows.

       If set to -1 (default), inherit !Py_FrozenFlag value. */
    int pathconfig_warnings;

    wchar_t *pythonpath_env; /* PYTHONPATH environment variable */
    wchar_t *home;          /* PYTHONHOME environment variable,
                               see also Py_SetPythonHome(). */

    /* --- Path configuration outputs ----------- */

    int module_search_paths_set;  /* If non-zero, use module_search_paths */
    PyWideStringList module_search_paths;  /* sys.path paths. Computed if
                                       module_search_paths_set is equal
                                       to zero. */

    wchar_t *executable;        /* sys.executable */
    wchar_t *base_executable;   /* sys._base_executable */
    wchar_t *prefix;            /* sys.prefix */
    wchar_t *base_prefix;       /* sys.base_prefix */
    wchar_t *exec_prefix;       /* sys.exec_prefix */
    wchar_t *base_exec_prefix;  /* sys.base_exec_prefix */
    wchar_t *platlibdir;        /* sys.platlibdir */

    /* --- Parameter only used by Py_Main() ---------- */

    /* Skip the first line of the source ('run_filename' parameter), allowing use of non-Unix forms of
       "#!cmd".  This is intended for a DOS specific hack only.

       Set by the -x command line option. */
    int skip_source_first_line;

    wchar_t *run_command;   /* -c command line argument */
    wchar_t *run_module;    /* -m command line argument */
    wchar_t *run_filename;  /* Trailing command line argument without -c or -m */

    /* --- Private fields ---------------------------- */

    /* Install importlib? If set to 0, importlib is not initialized at all.
       Needed by freeze_importlib. */
    int _install_importlib;

    /* If equal to 0, stop Python initialization before the "main" phase */
    int _init_main;

    /* If non-zero, disallow threads, subprocesses, and fork.
       Default: 0. */
    int _isolated_interpreter;

    /* Original command line arguments. If _orig_argv is empty and _argv is
       not equal to [''], PyConfig_Read() copies the configuration 'argv' list
       into '_orig_argv' list before modifying 'argv' list (if parse_argv
       is non-zero).

       _PyConfig_Write() initializes Py_GetArgcArgv() to this list. */
    PyWideStringList _orig_argv;
} PyConfig;
```

`pymain_init` initializes `config` to the defaults by calling `PyConfig_InitPythonConfig(&config)`, stores the command line arguments in `config.argv` by calling `PyConfig_SetBytesArgv(&config, args->argc, args->bytes_argv)` and, eventually, calls `Py_InitializeFromConfig(&config)` to perform the core and the main initialization phases. Here's slightly simplified `Py_InitializeFromConfig`:

```C
PyStatus
Py_InitializeFromConfig(const PyConfig *config)
{
    // ... handle errors
  
    PyStatus status;

  	// yeah, call once again
    status = _PyRuntime_Initialize();
    // ...
    _PyRuntimeState *runtime = &_PyRuntime;

    PyThreadState *tstate = NULL;
    status = pyinit_core(runtime, config, &tstate);
    // ...
    config = _PyInterpreterState_GetConfig(tstate->interp);

    if (config->_init_main) {
        status = pyinit_main(tstate);
        // ...
    }

    return _PyStatus_OK();
}

```

Here we can clearly see the separation between the initialization phases. The core phase is done by `pyinit_core`, and the main phase is done by `pyinit_main`. The `pyinit_core` function initializes the "core" of Python. More specifically,

1. It prepares the configuration: parses the command line arguments, reads the environment variables, calculates `config.module_search_paths `, chooses the encodings for the standard streams and the file system and writes all of this to the appropriate place in `config`.
2. It applies the configuration: initializes the standard streams, generates the secret key for hashing, creates the main interpreter state and the main thread state, initializes the GIL and takes it, enables the GC, initializes built-in types and exceptions, initializes the `sys` module and the `builtins` module and sets up the import mechanism for built-in and frozen modules.

The first step is not very interesting, so let's look at the `pyinit_config` function, which performs the second step:

```C
static PyStatus
pyinit_config(_PyRuntimeState *runtime,
              PyThreadState **tstate_p,
              const PyConfig *config)
{
  	// initialize C standard streams (stdin, stdout, stderr)
  	// set secret key for hashing
    PyStatus status = pycore_init_runtime(runtime, config);
    // ... handle errors

    PyThreadState *tstate;
  	// create the main interpreter state and the main thread state
    // take GIL
    status = pycore_create_interpreter(runtime, config, &tstate);
    // ...
    *tstate_p = tstate;

    // types, exception, sys, builtins, import, etc.
    status = pycore_interp_init(tstate);
    // ...

    /* Only when we get here is the runtime core fully initialized */
    runtime->core_initialized = 1;
    return _PyStatus_OK();
}
```

CPython uses [SipHash24](https://en.wikipedia.org/wiki/SipHash) hash function to compute hashes. It takes an input along with the secret key, which is stored in the `_Py_HashSecret` global variable.  `pycore_init_runtime` calls `_Py_HashRandomization_Init` to randomly generate the key. The purpose of randomization is to protect a Python application from hash collision DoS attacks. Python and many other languages including PHP, Ruby, JavaScript and C# were once vulnerable to such attacks. An attacker could send a set of strings with the same hash to an application and increase dramatically the CPU time required to put these strings in the dictionary because they all happen to be in the same bucket. The solution is to supply a hash function with the randomly generated key uknown to the attacker. Python also allows to generate a key deterministically by setting the `PYTHONHASHSEED` environment variable to some fixed value. To learn more about the attack, check [this presentation](https://fahrplan.events.ccc.de/congress/2011/Fahrplan/attachments/2007_28C3_Effective_DoS_on_web_application_platforms.pdf). To learn more about the CPython's hash algorithm, check [PEP 456](https://www.python.org/dev/peps/pep-0456/).

In the first part we learned that CPython uses a thread state to store thread-specific data, such as a call stack and an exception state, and an interpreter state to store interpreter-specific data, such as loaded modules and import settings.  The `pycore_create_interpreter`  function creates an interpreter state and a thread state for the main thread that is currently executing. An interpreter state is represented by the following struct:

```C
// The PyInterpreterState typedef is in Include/pystate.h.
struct _is {
		
  	// _PyRuntime.interpreters.head stores the most recently created interpreter
  	// next allows to access all interpreters
    struct _is *next;
  	// holds the most recently created thread state
  	// thread states of the same interpreter are linked together
    struct _ts *tstate_head;

    /* Reference to the _PyRuntime global variable. This field exists
       to not have to pass runtime in addition to tstate to a function.
       Get runtime from tstate: tstate->interp->runtime. */
    struct pyruntimestate *runtime;

    int64_t id;
  	// track references to the interpreter
    int64_t id_refcount;
    int requires_idref;
    PyThread_type_lock id_mutex;

    int finalizing;

    struct _ceval_state ceval;
    struct _gc_runtime_state gc;

    PyObject *modules; 	// sys.modules
    PyObject *modules_by_index;
    PyObject *sysdict; 	// sys.__dict__
    PyObject *builtins; // builtins.__dict__
    PyObject *importlib;
		
  	// a list of codec search functions
    PyObject *codec_search_path;
    PyObject *codec_search_cache;
    PyObject *codec_error_registry;
    int codecs_initialized;

    struct _Py_unicode_state unicode;

    PyConfig config;

    PyObject *dict;  /* Stores per-interpreter state */

    PyObject *builtins_copy;
    PyObject *import_func;
    /* Initialized to PyEval_EvalFrameDefault(). */
    _PyFrameEvalFunction eval_frame;

    // see `atexit` module
    void (*pyexitfunc)(PyObject *);
    PyObject *pyexitmodule;

    uint64_t tstate_next_unique_id;

  	// see `warnings` module
    struct _warnings_runtime_state warnings;

  	// a list of audit hooks, see sys.addaudithook
    PyObject *audit_hooks;
  
#if _PY_NSMALLNEGINTS + _PY_NSMALLPOSINTS > 0
    // small integers are preallocated in this array so that they can be shared
  	// the default range is [-5, 256]
    PyLongObject* small_ints[_PY_NSMALLNEGINTS + _PY_NSMALLPOSINTS];
#endif
  
  // ... less interesting stuff for now
};
```

The important thing to note here is that `config` belongs to the interpreter state. The configuration that was read before is stored in `config` of the newly created interpreted state. Then, `pycore_create_interpreter` creates the first thread state, which is defined as follows:

```C
// The PyThreadState typedef is in Include/pystate.h.
struct _ts {
  
  	// double-linked list is used to access all thread states
  	// belonging to the same interpreter
    struct _ts *prev;
    struct _ts *next;
    PyInterpreterState *interp;

    // reference to the current frame (it can be NULL)
  	// the call stack is accesible via frame->f_back
    PyFrameObject *frame;
  
  	// ... checking if recursion level is too deep

    // ... tracing/profiling

    /* The exception currently being raised */
    PyObject *curexc_type;
    PyObject *curexc_value;
    PyObject *curexc_traceback;

    /* The exception currently being handled, if no coroutines/generators
     * are present. Always last element on the stack referred to be exc_info.
     */
    _PyErr_StackItem exc_state;

    /* Pointer to the top of the stack of the exceptions currently
     * being handled */
    _PyErr_StackItem *exc_info;

    PyObject *dict;  /* Stores per-thread state */

    int gilstate_counter;

    PyObject *async_exc; /* Asynchronous exception to raise */
    unsigned long thread_id; /* Thread id where this tstate was created */

    /* Unique thread state id. */
    uint64_t id;

    // ... less interesting stuff for now
};
```

