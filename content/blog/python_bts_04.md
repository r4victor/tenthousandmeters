Title: Python behind the scenes #4: how Python bytecode is executed
Date: 2020-10-15 14:15
Tags: Python behind the scenes, Python, CPython

We started this series with an overview of the CPython VM. We learned that to run a Python program, CPython first compiles it to bytecode, and we studied how the compiler works in part two. Last time we stepped through the CPython source code starting with the `main()` function until we reached the evaluation loop, a place where Python bytecode gets executed. While all this may be very interesting in itself, the main reason why we spent time on it was to prepare for the discussion that we start today. The goal of this discussion is to understand how CPython executes the bytecode.

### Starting point

Let's briefly recall what we learned in the previous parts. We tell CPython what to do by writing Python code. The CPython VM, hovewer, understands only Python bytecode. This is the job of the compiler to translate Python code to bytecode. The compiler stores bytecode in a code object, which is a structure that fully describes what a code block, like a module or a function body, does. To execute a code object, CPython first creates a state of execution for it called a frame object. Then it passes a frame object to a frame evaluation function to perform the actual computation. The default frame evaluation function is `_PyEval_EvalFrameDefault()`. This function implements the core of the CPython VM. Namely, it implements the logic for the execution of Python bytecode. So, this function is what we're going to study today.

To understand how `_PyEval_EvalFrameDefault()` works, it is crucial to have an idea of what its input, a frame object, is. A frame object is a Python object defined by the following C struct:

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

### Overview of the evaluation loop

The problem of executing Python bytecode may seem a no-brainer to you. Indeed, all CPython has to do is to iterate over the instructions and to act according to them. And this is what essentially `_PyEval_EvalFrameDefault()` does. It contains an infinite `for (;;)` loop that we refer to as the evaluation loop. Inside that loop there is a giant switch statement over all possible opcodes. The bytecode is represented by an array of 16-bit unsigned integers, one element per instruction. CPython keeps track of the next instruction to be executed using the `next_instr` variable, which is a pointer to the array of instructions. At the start of each iteration of the evaluation loop, CPython calculates the next opcode and its argument by taking the least significant and the most significant byte of the next instruction respectively and increments `next_instr`. The `_PyEval_EvalFrameDefault()` function is nearly 3000 lines long, but its essence can be captured by the following simplified version:

```C
PyObject*
_PyEval_EvalFrameDefault(PyThreadState *tstate, PyFrameObject *f, int throwflag)
{
    // ... declarations and initialization of local variables
    // ... macros definitions
    // ... call depth handling
    // ... code for tracing and profiling

    for (;;) {
      	// ... check if the bytecode execution must be suspended,
      	// e.g. other thread requested the GIL
      
      	// NEXTOPARG() macro
      	_Py_CODEUNIT word = *next_instr; // _Py_CODEUNIT is a typedef for uint16_t
        opcode = _Py_OPCODE(word);
        oparg = _Py_OPARG(word);
        next_instr++;

        switch (opcode) {
            case TARGET(NOP) {
                FAST_DISPATCH(); // more on this later
            }

            case TARGET(LOAD_FAST) {
                // ... code for loading local variable
            }

            // ... 117 more cases for every possible opcode
        }
      
      	// ... error handling
    }
  	
  	// ... termination
}
```

To get a more realistic picture, let's disscuss some of the omitted pieces in more detail.

#### reasons to suspend the loop

From time to time, the currently running thread stops executing the bytecode to do something else or to do nothing. This can happen due to one of the four reasons:

* There are signals to handle. When you register a function as a signal handler using [`signal.signal()`](https://docs.python.org/3/library/signal.html#signal.signal), CPython stores this function in the array of handlers. The function that is actually will be called when a thread receives a signal is `signal_handler()` (it's passed to the [`sigaction()`](https://www.man7.org/linux/man-pages/man2/sigaction.2.html) library function on Unix-like systems). When called, `signal_handler()` sets a boolean variable telling that the function in the array of handlers corresponding to the received signal has to be called. Periodically, the main thread of the main interpreter calls the tripped handlers.
* There are pending calls to call. Pending calls is a mechanism that allows to shedule a function to be executed from the main thread. This mechanism is exposed by the Python/C API via the [`Py_AddPendingCall()`](https://docs.python.org/3/c-api/init.html#c.Py_AddPendingCall) function.
* The asynchronous exception is raised. The asynchronous exception is an exception set in one thread from another. This can be done using the [`PyThreadState_SetAsyncExc()`](https://docs.python.org/3/c-api/init.html#c.PyThreadState_SetAsyncExc) function provided by the Python/C API.
* The currently running thread is requested to drop the GIL. When it sees such a request, it drops the GIL and waits until it acquires the GIL again.

CPython has indicators for each of these events. The variable indicating that there are handlers to call is a member of `runtime->ceval`, which is a `_ceval_runtime_state` struct:

```C
struct _ceval_runtime_state {
    /* Request for checking signals. It is shared by all interpreters (see
       bpo-40513). Any thread of any interpreter can receive a signal, but only
       the main thread of the main interpreter can handle signals: see
       _Py_ThreadCanHandleSignals(). */
    _Py_atomic_int signals_pending;
    struct _gil_runtime_state gil;
};
```

Other indicators are members of `interp->ceval,` which is a `_ceval_state` struct:

```C
struct _ceval_state {
    int recursion_limit;
    /* Records whether tracing is on for any thread.  Counts the number
       of threads for which tstate->c_tracefunc is non-NULL, so if the
       value is 0, we know we don't have to check this thread's
       c_tracefunc.  This speeds up the if statement in
       _PyEval_EvalFrameDefault() after fast_next_opcode. */
    int tracing_possible;
    /* This single variable consolidates all requests to break out of
       the fast path in the eval loop. */
    _Py_atomic_int eval_breaker;
    /* Request for dropping the GIL */
    _Py_atomic_int gil_drop_request;
    struct _pending_calls pending;
};
```

The result of ORing all indicators together is stored in the `eval_breaker` variable. It tells whether there is any reason for the currently running thread to stop its normal bytecode execution. Each iteration of the evaluation loop starts with the check whether `eval_breaker` is true. If it is true, the thread checks the indicators to determine what exactly it is asked to do, does that and continues executing the bytecode.

#### computed GOTOs

The code for the evaluation loop is full of macros such as `TARGET()` and `DISPATCH()`. These are not the means to make the code more compact. They expand to different code depending on whether the certain optimization, referred to as "computed GOTOs", is used. They goal of this optimization is to speed up the bytecode execution by writing code in such a way, so that a CPU can use its [branch prediction mechanism](https://en.wikipedia.org/wiki/Branch_predictor) to predict the next opcode.

After executing any given instruction, CPython does one of three things:

* It returns from the evaluation function. This happens when CPython executes `RETURN_VALUE`, `YIELD_VALUE` or `YIELD_FROM` instruction.
* It handles the error and either continues the execution or returns from the evaluation function with the exception set. The error can occur when, for example, CPython executes the `BINARY_ADD` instruction and the objects to be added do not implement `__add__` and `__radd__` methods.
* It continues the execution. How does it do that? You might expect that the cases just end with the `continue` statement. The reality, though, is a little bit more complicated.

To understand what's the problem with the simple  `continue  ` statement, we need to understand what `switch` compiles to. An opcode is an integer between 0 and 255. Because the range is dense, the compiler can create a jump table that stores addresses of the case blocks and use opcodes as indices into that table. The modern compilers indeed do that, so the switch control flow is effectively implemented as a single indirect jump. It's fast, but the problem is that a CPU has a little chance of predicting the next opcode. The best it can do is to choose the last opcode or, possibly, the most frequent one. The idea of the optimization is to have a separate jump in the end of each non-returning case block. A CPU can then predict the next opcode as the most probable opcode following the current one.

The optimization can be enabled or disabled. It depends on whether the compiler supports the GCC C extension called ["Labels as Values"](https://gcc.gnu.org/onlinedocs/gcc/Labels-as-Values.html) or not. The effect of enabling the optimization is that the certain macros, such as `TARGET()`, `DISPATCH()` and `FAST_DISPATCH()`, expand in different way. These macros are used extensively throughout the code of the evaluation loop. Every case expression has a form `TARGET(op)`, where  `op` is a macro for the integer literal representing an opcode. And every non-returning case block ends with `DISPATCH()` or `FAST_DISPATCH()` macro. Let's first look at what these macros expand to when the optimization is disabled:

```C

for (;;) {
  	// ... check if the bytecode execution must be suspended

fast_next_opcode:
  	// NEXTOPARG() macro
    _Py_CODEUNIT word = *next_instr;
    opcode = _Py_OPCODE(word);
    oparg = _Py_OPARG(word);
    next_instr++;

    switch (opcode) {
        // TARGET(NOP) expands to NOP
      	case NOP: {
          	goto fast_next_opcode; // FAST_DISPATCH() macro
        }
        
        // ...

        case BINARY_MULTIPLY: {
            // ... code for binary multiplication
            continue; // DISPATCH() macro
        }
        
        // ...
    }
  	
  	// ... error handling
}
  	
```

The `FAST_DISPATCH()` is used for some opcode when it's undesirable to suspend the evaluation loop after executing that opcode. Otherwise, the implementation is very straightforward.

If the compiler supports "Labels as Values" extension, we can use the unary `&&` operator on a label to get its address. It has a value of type `void *`, which we can store in a pointer:

```C
void *ptr;
// ...
ptr = &&my_label;
```

We can then go to the label by dereferencing the pointer:

```C
goto *ptr;
```

This extension allows to implement a jump table in C as an array of label pointers. And that's what CPython does:

```C
static void *opcode_targets[256] = {
    &&_unknown_opcode,
    &&TARGET_POP_TOP,
    &&TARGET_ROT_TWO,
    &&TARGET_ROT_THREE,
    &&TARGET_DUP_TOP,
    &&TARGET_DUP_TOP_TWO,
    &&TARGET_ROT_FOUR,
    &&_unknown_opcode,
    &&_unknown_opcode,
    &&TARGET_NOP,
    &&TARGET_UNARY_POSITIVE,
    &&TARGET_UNARY_NEGATIVE,
    &&TARGET_UNARY_NOT,
  	// ... quite a few more
};

```

Here's how the optimized version of the evaluation loop looks like:

```C
for (;;) {
  	// ... check if the bytecode execution must be suspended

fast_next_opcode:
  	// NEXTOPARG() macro
    _Py_CODEUNIT word = *next_instr;
    opcode = _Py_OPCODE(word);
    oparg = _Py_OPARG(word);
    next_instr++;

    switch (opcode) {
        // TARGET(NOP) expands to NOP: TARGET_NOP:
        // TARGET_NOP is a label
      	case NOP: TARGET_NOP: {
          	// FAST_DISPATCH() macro
            // when tracing is disabled
            f->f_lasti = INSTR_OFFSET();
            NEXTOPARG();
            goto *opcode_targets[opcode];
        }
        
        // ...

      	case BINARY_MULTIPLY: TARGET_BINARY_MULTIPLY: {
            // ... code for binary multiplication
          	// DISPATCH() macro
            if (!_Py_atomic_load_relaxed(eval_breaker)) {
              FAST_DISPATCH();
            }
            continue;
        }
        
        // ...
    }
  	
  	// ... error handling
}
```

The extension is supported by the GCC and Clang compilers. So, when you run `python`, you probably have the optimization enabled. The question is how it affects the performance. Here, I'll rely on the comment from the source code:

> At the time of this writing, the "threaded code" version is up to 15-20% faster than the normal "switch" version, depending on the compiler and the CPU architecture.

