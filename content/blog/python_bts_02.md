Title: Python behind the scenes #2: how the CPython compiler works
Date: 2020-09-06 10:50
Tags: Python behind the scenes, Python, CPython
Summary:

### Today's subject

In [the first post]({filename}/blog/python_bts_01.md) of the series we've looked at the CPython VM. We've learned that it works by executing a given series of instructions called bytecode. We've also seen that Python bytecode is not sufficient to fully describe what a piece of code does. That's why there exists a notion of a code object. To execute a code block such as a module or a function means to execute a corresponding code object, which contains block's bytecode along with the lists of names of variables used in the block and block's various properties such as a number of arguments and a coroutine flag.

Typically, a Python programmer doesn't write bytecode and doesn't create the code objects but writes a normal Python code. So CPython must be able to create a code object from a source code. This job is done by the CPython compiler. In this part we'll explore how it works.

### What CPython compiler is

We understood what the responsibilities of the CPython compiler are, but before looking at how it is implemented, let's figure out why we call it a compiler in the first place?

A compiler, in its general sense, is a program that translates a program in one language into an equivalent program in another language. There are many types of compilers, but most of the times by a compiler we mean a static compiler, which translates a program in a high-level language to a machine code. Does CPython have something in common with this type of a compiler? To answer this question, let's take a look at the traditional three-stage design of a static compiler.

<img src="{static}/blog/python_bts_02/diagram1.png" alt="diagram1" style="zoom:50%; display: block; margin: 0 auto;" />

The frontend of a compiler transforms a source code into some intermediate representation (IR). The optimizer then takes an IR, optimizes it and passes an optimized IR to the backend that generates machine code. If we choose an IR that is not specific to any source language and any target machine, then we get a key benefit of the three-stage design – for a compiler to support a new source language only an additional frontend is needed and to support a new target machine only an additional backend is needed.

The LLVM toolchain is a great example of a success of this model. There are frontends for C, Rust, Swift and many other programming languages that rely on LLVM to provide more complicated parts of the compiler. LLVM's creator, Chris Lattner, gives a good [overview of its architecture](http://aosabook.org/en/llvm.html).

CPython, however, doesn't need to support multiple source languages and target machines but only a Python code and the CPython VM. Nevertheless, CPython compiler is an implementation of the three-stage design. To see why, we should examine the stages of a three-stage compiler in more detail. 

<img src="{static}/blog/python_bts_02/diagram2.png" alt="diagram1" style="zoom:50%; display: block; margin: 0 auto;" />

The picture above represent a classic model of a compiler. Now compare it to the architecture of the CPython compiler in the picture below.

<img src="{static}/blog/python_bts_02/diagram3.png" alt="diagram1" style="zoom:50%; display: block; margin: 0 auto;" />

Looks similar, isnt't it? The point here is that the structure of the CPython compiler should be familiar to anyone who studied compilers before. If you didn't, a famous [Dragon Book](https://en.wikipedia.org/wiki/Compilers:_Principles,_Techniques,_and_Tools) is an excellent introduction to the theory of compiler construction. It's long, but you'll benefit even by reading only the first few chapters.

The comparison we've made requires several comments. First, since version 3.9, CPython uses a new parser by default that outputs an AST (Abstract Syntax Tree) straight away without an intermediate step of building a parse tree. Thus, the model of the CPython compiler is simplified even further. Second, some of the presented phases of the CPython compiler do so little compared to their counterparts of the static compilers that some may say that the CPython compiler is no more than a frontend. We won't take this view of the hardcore compiler writers.

### Overview of the compiler's architecture

The diagrams are nice, but they hide many details and can be misleanding, so let's spend some time discussing the overall design of the CPython compiler.

The two major components of the CPython compiler are:

1. the frontend; and
2. the backend.

The frontend takes a Python code and produces an AST. The backend takes an AST and produces a code object. Throughout CPython's source code the terms parser and compiler are used for the frontend and the backend respectively. This is yet another meaning of the word compiler. It was probably better to call it something like a code object generator, but we'll stick with the compiler since it doesn't seem to cause much trouble.

The job of the parser is to check whether an input is a syntactically correct Python code. If it's not, then the parser reports an error like the following:

```python
x = y = = 12
        ^
SyntaxError: invalid syntax
```

If an input is correct, then the parser organizes it according to the rules of the grammar. A grammar defines the syntax of a language. The notion of a formal grammar is so crucial for our discussion that, I think, we should digress a little to remember its formal definition.

According to the classic definition, a grammar is a tuple of four items:

* $N$ – a finite set of terminal symbols (usually denoted by the lowercase letters).
* $\Sigma$ – a finite set of nonterminal symbols (usually denoted by the uppercase letters).
* $P$ – a set of production rules. In the case of context-free grammars, which include the Python's grammar, a production rule is just a mapping from a nonterminal symbol to any sequence of terminal and nonterminal symbols like $A \to aB$.
* $S$ – one distinguished nonterminal symbol.

A grammar is then said to define a language that consists of all sequences of terminal symbols that can be generated by applying the rules of a grammar. To generate some sequence one starts with the symbol $S$ and then recursively replaces each nonterminal symbol with a sequence according to production rules until the whole sequence consists only of terminal symbols. Using established convention for the notation, it's sufficient to list the rules of a grammar. Let's end this digression with an example of a simple grammar that generates sequences of alternating ones and zeros:

$S \to 10S \;| \;10$

We'll continue to discuss grammars when we look at the parser in more detail.

### Abstract syntax tree

The ultimate goal of the parser is to produce an AST. An AST is a tree data structure that serves as a high-level representation of a source code. Here's an example of a piece of code and a dump of the corresponding AST produced by the standard [`ast`](https://docs.python.org/3/library/ast.html) module:

```python
x = 123
f(x)
```

```text
$ python -m ast example1.py
Module(
   body=[
      Assign(
         targets=[
            Name(id='x', ctx=Store())],
         value=Constant(value=123)),
      Expr(
         value=Call(
            func=Name(id='f', ctx=Load()),
            args=[
               Name(id='x', ctx=Load())],
            keywords=[]))],
   type_ignores=[])
```

The types of the AST nodes are formally defined using [the Zephyr Abstract Syntax Definition Language](https://www.cs.princeton.edu/research/techreps/TR-554-97) (ASDL). The ASDL is a simple declarative language that was created to describe tree-like IRs, which is what the AST is. Here is the definitions of the `Assign` and `Expr` nodes from [Parser/Python.asdl](https://github.com/python/cpython/blob/master/Parser/Python.asdl):

```text
stmt = ... | Assign(expr* targets, expr value, string? type_comment) | ...
expr = ... | Call(expr func, expr* args, keyword* keywords) | ...
```

The ASDL specification should give us an idea of what the Python AST looks like. The parser, however, needs to represent an AST in the C code. Fortunately, it's easy to generate the C structs for the AST nodes from their ASDL descriptions. That's what CPython does, and the result looks like the following:

```C
struct _stmt {
    enum _stmt_kind kind;
    union {
      	// ... other kinds of statements
      	struct {
            asdl_seq *targets;
            expr_ty value;
            string type_comment;
      	} Assign;
      	// ... other kinds of expression
    } v;
  	int lineno;
    int col_offset;
    int end_lineno;
    int end_col_offset;
};

struct _expr {
    enum _expr_kind kind;
    union {
      	// ... other kinds of expression
      	struct {
            expr_ty func;
            asdl_seq *args;
            asdl_seq *keywords;
        } Call;
      	// ... other kinds of expression
    } v;
    // ... same as in _stmt
};
```

An AST is a handy representation to work with. It tells what a program does hiding all non-essential information such as indentation, punctuation and other Python's syntactic features.

One of the main beneficiaries of an AST is the compiler, which can walk an AST and emit bytecode in a straightforward manner. Many Python tools, besides the compiler, use an AST to work with a Python code. For example, pytest makes changes to an AST to provide a usefull information when the `assert` statement fails, which by itself does nothing but raises an `AssertionError` if the expression evaluates to `False`. Another example is Bandit that finds common security issues in Python code by analyzing an AST.

Now, when we've studied the Python AST a little bit, we can look at how the parser builds it from a source code.

### From source code to AST

In fact, as I mentioned earlier, starting with version 3.9, CPython has not one but two parsers. The new parser is used by default. It's also possible to use the old parser by passing `-X oldparser` option. In CPython 3.10, however, the old parser will be completely removed.

The two parser are very different. We'll focus on the new one but before discuss the old parser as well.

#### old parser

For a long time the Python's syntax was formally defined by the generative grammar. It's a kind of a grammar we've talked about earlier. It tells how to generate correct sequences in a language it defines. The problem is that a generative grammar doesn't directly corresponds to a parsing algorithm that would be able to parse sequences from the defined language. Fortunately, smart people distinguished the classes of generative grammars for which the corresponding parser can be built in a straightforward way. These include [context free](https://en.wikipedia.org/wiki/Context-free_grammar), [LL(k),](https://en.wikipedia.org/wiki/LL_grammar) [LR(k)](https://en.wikipedia.org/wiki/LR_parser), [LALR](https://en.wikipedia.org/wiki/LALR_parser) and many others types of grammars. The Python's grammar is LL(1). It's specified using a kind of [Extended Backus–Naur Form](https://en.wikipedia.org/wiki/Extended_Backus%E2%80%93Naur_form) (EBNF). To get an idea on how it can be used to describe Python's syntax, take a look at the rules for the while statement.

```text
file_input: (NEWLINE | stmt)* ENDMARKER
stmt: simple_stmt | compound_stmt
compound_stmt: ... | while_stmt | ...
while_stmt: 'while' namedexpr_test ':' suite ['else' ':' suite]
suite: simple_stmt | NEWLINE INDENT stmt+ DEDENT
...
```

CPython extends the traditional notation with features like:

* grouping of alternatives: (a | b)
* optional parts: [a]
* zero or more and one or more repetitions: a* and a+.

We can see [why Guido van Rossum chose to use regular expressions](https://www.blogger.com/profile/12821714508588242516). They allow to express the syntax of a programming language in a more natural (for a programmer) way. Instead of writing $A \to aA | a$ , we can just write $A \to a+$. This choice came with a cost.

The parsing of an LL(1) grammar is a solved problem. The solution is a Pushdown Automaton (PDA), which acts as a top-down parser. A PDA operates by simulating a generation of an input string using a stack. To parse some input it starts with the start symbol on the stack. Then it looks at the first symbol in the input, guesses which rule should be applied to the start symbol and replaces the start symbol with a right-hand side of that rule. If a top symbol on the stack matches the next symbol, a PDA pops it and skips the matched symbol. If a top symbol is a nonterminal, a PDA tries to guess the rule to replace it with based on the next input symbol. The process repeats until the whole input is scanned or if a PDA can't match a terminal symbol on the stack with the next symbol in the input resulting in an error.

CPython couldn't use this method directly because of how the rules look, so the new method had to be developed. To support extended notation, the old parser represents each rule of a grammar with a [Deterministic Finite Automaton](https://en.wikipedia.org/wiki/Deterministic_finite_automaton) (DFA), which is famous for being equivalent to a regular expression. The parser itself is a stack-based automaton like PDA, but instead of pushing symbols on the stack, it pushes states of the DFAs. Here's the key data structures used by the old parser:

```C
typedef struct {
    int              s_state;       /* State in current DFA */
    const dfa       *s_dfa;         /* Current DFA */
    struct _node    *s_parent;      /* Where to add next node */
} stackentry;

typedef struct {
    stackentry      *s_top;         /* Top entry */
    stackentry       s_base[MAXSTACK];/* Array of stack entries */
                                    /* NB The stack grows down */
} stack;

typedef struct {
    stack           p_stack;        /* Stack of parser states */
    grammar         *p_grammar;     /* Grammar to use */
  																	// basically, a collection of DFAs
    node            *p_tree;        /* Top of parse tree */
    // ...
} parser_state;
```

And the comment from [Parser/parser.c](https://github.com/python/cpython/blob/3.9/Parser/parser.c) that summarizes this approach:

> A parsing rule is represented as a Deterministic Finite-state Automaton
> (DFA).  A node in a DFA represents a state of the parser; an arc represents
> a transition.  Transitions are either labeled with terminal symbols or
> with nonterminals.  When the parser decides to follow an arc labeled
> with a nonterminal, it is invoked recursively with the DFA representing
> the parsing rule for that as its initial state; when that DFA accepts,
> the parser that invoked it continues.  The parse tree constructed by the
> recursively called parser is inserted as a child in the current parse tree.

The parser builds a parse tree, also known as Concrete Syntax Tree (CST), while parsing an input. In constrast to an AST, a parse tree directly corresponds to the rules applied when deriving an input. All nodes in a parse tree are represented using the same `node` struct:

```C
typedef struct _node {
    short               n_type;
    char                *n_str;
    int                 n_lineno;
    int                 n_col_offset;
    int                 n_nchildren;
    struct _node        *n_child;
    int                 n_end_lineno;
    int                 n_end_col_offset;
} node;
```

A parse tree, however, is not what the compiler waits for. It has to be converted to an AST. This work is done in [Python/ast.c](https://github.com/python/cpython/blob/3.9/Python/ast.c). The algorithm is to walk a parse tree recursively and translate its nodes to the AST nodes. Hardly anyone finds these nearly 6,000 lines of code exciting. 

#### tokenizer

Python is not a simple language from the syntactic point of view. The Python's grammar, tough, looks simple and fits in about 200 lines including comments. This is because the symbols of the grammar are tokens and not individual characters. A token is represented by its type such as `NUMBER`, `NAME`, `NEWLINE`, its value and its position in a source code. CPython distinguishes 63 types of tokens, all of which are listed in [Grammar/Tokens](https://github.com/python/cpython/blob/3.9/Grammar/Tokens). We can see what a tokenized program looks like using the standard `tokenize` module:

```Python
def x_plus(x):
    if x >= 0:
        return x
    return 0
```

```text
$ python -m tokenize example2.py 
0,0-0,0:            ENCODING       'utf-8'        
1,0-1,3:            NAME           'def'          
1,4-1,10:           NAME           'x_plus'       
1,10-1,11:          OP             '('            
1,11-1,12:          NAME           'x'            
1,12-1,13:          OP             ')'            
1,13-1,14:          OP             ':'            
1,14-1,15:          NEWLINE        '\n'           
2,0-2,4:            INDENT         '    '         
2,4-2,6:            NAME           'if'           
2,7-2,8:            NAME           'x'            
2,9-2,11:           OP             '>='           
2,12-2,13:          NUMBER         '0'            
2,13-2,14:          OP             ':'            
2,14-2,15:          NEWLINE        '\n'           
3,0-3,8:            INDENT         '        '     
3,8-3,14:           NAME           'return'       
3,15-3,16:          NAME           'x'            
3,16-3,17:          NEWLINE        '\n'           
4,4-4,4:            DEDENT         ''             
4,4-4,10:           NAME           'return'       
4,11-4,12:          NUMBER         '0'            
4,12-4,13:          NEWLINE        '\n'           
5,0-5,0:            DEDENT         ''             
5,0-5,0:            ENDMARKER      ''     
```

This is how the program looks to the parser. When the parser needs a token, it requests one from the tokenizer. The tokenizer reads one character at a time from the buffer and tries to match the seen prefix with some type of token. How does the tokenizer work with different encodings? It relies on the `io` module. First, the tokenizer detects the encoding. If no encoding is specified, it defaults to UTF-8. Then, the tokenizer opens a file with a C call, which is equivalent to Python's `open(fd, mode='r', encoding=enc)`, and reads its contents by calling the `readline` function. This function returns a unicode string. The characters the tokenizer reads are just bytes in the UTF-8 representation of that string (or EOF).

We could define what a number or a name is directly in the grammar, tough it would become more compex. What we couldn't do is to express the significance of identation in the grammar without making it [context-sensitive](https://en.wikipedia.org/wiki/Context-sensitive_grammar) and, therefore, not suitable for parsing. The tokenizer makes work of the parser much easier by providing `INDENT` and `DEDENT` tokens. They mean what the curly braces mean in a language like C. The tokenizer is powerfull because it has state. The current identation level is kept on the top of the stack. When the level is increased, it's pushed on the stack. If the level is decreased, all higher levels are popped from the stack.

The old parser is a non-trivial piece of the CPython's codebase. The DFAs for the rules of the grammar are generated automatically, but other parts of the parser are written by hand. This is in contrast with the new parser, which seems to be a much more elegant solution to the problem of parsing Python code.

#### new parser

The new parser comes with the new grammar. This grammar is a [Parsing Expression Grammar](https://en.wikipedia.org/wiki/Parsing_expression_grammar) (PEG). The important thing to understand is that PEG is not just a class of formal grammars. It's another way to define a formal grammar. PEGs were [introduced by Bryan Ford in 2004](https://pdos.csail.mit.edu/~baford/packrat/popl04/) as a tool to describe a programming language and to generate a parser based on the description. A PEG is different from the traditional formal grammar in that its rules map nonterminals to the parsing expressions instead of just sequences of symbols. This is in the spirit of the CPython's way to describe a grammar. A parsing expression is defined inductively. If $e$, $e_1$, and $e_2$ are parsing expressions, then so is:

1. the empty string
2. any terminal
3. any nonterminal
4. $e_1e_2$, a sequence
5. $e_1/e_2$, prioritized choice
6. $e*$, zero-or-more repetitions
7. $!e$, a not-predicate.

PEGs are analytic grammars, which means that they are designed not only to generate languages but to analyze them as well. Ford formalized how a parsing expression $e$ recognizes an input $x$. Basically, any attempt to recognize an input with some parsing expression can either succeed or fail and consume some input or not. For example, applying a parsing expression $a$ to an input $ab$ results in success and consumes $a$. This formalization allows to convert any PEG to a [recursive descent parser](https://en.wikipedia.org/wiki/Recursive_descent_parser). 

