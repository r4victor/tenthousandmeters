Title: Python behind the scenes #4: how Python bytecode is executed
Date: 2020-10-15 14:15
Tags: Python behind the scenes, Python, CPython

We started this series with an overview of the CPython VM. We learned that to run a Python program, CPython first compiles it to bytecode, and we studied how the compiler works in part two. Last time we stepped through the CPython source code starting with the `main()` function until we reached the evaluation loop, a place where Python bytecode gets executed. While all this may be very interesting in itself, the main reason why we spent time on it was to prepare for the discussion that we start today. The goal of this discussion is to understand how CPython executes the bytecode.

### Starting point

Let's briefly recall what we learned in the previous parts. We tell CPython what to do by writing Python code. The CPython VM, hovewer, understands only Python bytecode. This is the job of the compiler to translate Python code to bytecode. The compiler stores bytecode in a code object, which is a structure that fully describes what a code block, like a module or a function body, does. To execute a code object, CPython first creates a state of execution for it called a frame object. Then it passes a frame object to a frame evaluation function to perform the actual computation. The default frame evaluation function is `_PyEval_EvalFrameDefault()`. This function implements the core of the CPython VM. Namely, it implements the logic for the execution of Python bytecode. So, this function is what we're going to study today.

To understand how `_PyEval_EvalFrameDefault()` works it is crucial to have an idea of what its input, a frame object, is. A frame object is a Python object defined by the following C struct:

```C
// typedef struct _frame PyFrameObject; in other place
struct _frame {
    PyObject_VAR_HEAD
    struct _frame *f_back;      /* previous frame, or NULL */
    PyCodeObject *f_code;       /* code segment */
    PyObject *f_builtins;       /* builtin symbol table (PyDictObject) */
    PyObject *f_globals;        /* global symbol table (PyDictObject) */
    PyObject *f_locals;         /* local symbol table (any mapping) */
    PyObject **f_valuestack;    /* points after the last local */
    /* Next free slot in f_valuestack.  Frame creation sets to f_valuestack.
       Frame evaluation usually NULLs it, but a frame that yields sets it
       to the current stack top. */
    PyObject **f_stacktop;
    PyObject *f_trace;          /* Trace function */
    char f_trace_lines;         /* Emit per-line trace events? */
    char f_trace_opcodes;       /* Emit per-opcode trace events? */

    /* Borrowed reference to a generator, or NULL */
    PyObject *f_gen;

    int f_lasti;                /* Last instruction if called */
    int f_lineno;               /* Current line number */
    int f_iblock;               /* index in f_blockstack */
    char f_executing;           /* whether the frame is still executing */
    PyTryBlock f_blockstack[CO_MAXBLOCKS]; /* for try and loop blocks */
    PyObject *f_localsplus[1];  /* locals+stack, dynamically sized */
};
```

The `f_code` field of a frame object points to a code object. A code object is also a Python object. Here's its definition:

```C
struct PyCodeObject {
    PyObject_HEAD
    int co_argcount;            /* #arguments, except *args */
    int co_posonlyargcount;     /* #positional only arguments */
    int co_kwonlyargcount;      /* #keyword only arguments */
    int co_nlocals;             /* #local variables */
    int co_stacksize;           /* #entries needed for evaluation stack */
    int co_flags;               /* CO_..., see below */
    int co_firstlineno;         /* first source line number */
    PyObject *co_code;          /* instruction opcodes */
    PyObject *co_consts;        /* list (constants used) */
    PyObject *co_names;         /* list of strings (names used) */
    PyObject *co_varnames;      /* tuple of strings (local variable names) */
    PyObject *co_freevars;      /* tuple of strings (free variable names) */
    PyObject *co_cellvars;      /* tuple of strings (cell variable names) */
    /* The rest aren't used in either hash or comparisons, except for co_name,
       used in both. This is done to preserve the name and line number
       for tracebacks and debuggers; otherwise, constant de-duplication
       would collapse identical functions/lambdas defined on different lines.
    */
    Py_ssize_t *co_cell2arg;    /* Maps cell vars which are arguments. */
    PyObject *co_filename;      /* unicode (where it was loaded from) */
    PyObject *co_name;          /* unicode (name, for reference) */
    PyObject *co_lnotab;        /* string (encoding addr<->lineno mapping) See
                                   Objects/lnotab_notes.txt for details. */
    void *co_zombieframe;       /* for optimization only (see frameobject.c) */
    PyObject *co_weakreflist;   /* to support weakrefs to code objects */
    /* Scratch space for extra data relating to the code object.
       Type is a void* to keep the format private in codeobject.c to force
       people to go through the proper APIs. */
    void *co_extra;

    /* Per opcodes just-in-time cache
     *
     * To reduce cache size, we use indirect mapping from opcode index to
     * cache object:
     *   cache = co_opcache[co_opcache_map[next_instr - first_instr] - 1]
     */

    // co_opcache_map is indexed by (next_instr - first_instr).
    //  * 0 means there is no cache for this opcode.
    //  * n > 0 means there is cache in co_opcache[n-1].
    unsigned char *co_opcache_map;
    _PyOpcache *co_opcache;
    int co_opcache_flag;  // used to determine when create a cache.
    unsigned char co_opcache_size;  // length of co_opcache.
};
```

The most important field of a code object is `co_code`. It's a pointer to a Python bytes object representing the bytecode. The bytecode is a sequence of two-byte instructions: one byte for an opcode and one byte for an argument.

Don't worry if some members of the above structures are still a mystery to you. We'll see what they are used for as we move forward in our attempt to understand how CPython executes bytecode. 

### Evaluation loop

The problem of executing bytecode may seem a no-brainer to you. Indeed, all CPython has to do is to iterate over the instructions and to act according to them. And this is what essentially `_PyEval_EvalFrameDefault()` does. It contains an infinite `for (;;)` loop that we refer to as the evaluation loop. Inside that loop there is a giant switch statement over all possible opcodes. The bytecode is represented by an array of 16-bit unsigned integers, one element per instruction. CPython keeps track of the next instruction to execute using the `next_instr` variable, which is a pointer to the array of instructions. At the start of each iteration of the evaluation loop, CPython calculates the next opcode and its argument by taking the least significant and the most significant byte of the next instruction respectively and increments `next_instr`.

