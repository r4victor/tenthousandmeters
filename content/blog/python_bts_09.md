Title: Python behind the scenes #9: how Python strings work
Date: 2021-02-09 9:30
Tags: Python behind the scenes, Python, CPython

In 1991 Guido van Rossum released the first version of the Python programming language to the world. About that time the world began to witness a major change in how computer systems represent written language. The internalization of the Internet increased the demand to support different writing systems, and the Unicode standard was developed to meet this demand. Unicode defined a universal character set able to represent any written language, various non-alphanumeric symbols and, eventually, emoji 😀. Python wasn't designed with Unicode in mind, but it evolved towards Unicode support during the years. The major change happened when Python got a built-in support for Unicode strings – the `unicode` type that later became the `str` type in Python 3. Python strings have been proven to be a handy way to work with text in the Unicode age. Today we'll see how they work behind the scenes.

## The scope of this post

This post doesn't try to cover all aspects of text encoding in relation to Python. You see, programming language designers have to make several text encoding decisions because they have to answer the following questions:

* How to talk to the external world (the encodings of command-line parameters, environment variables, standard streams and the file system).
* How to read the source code (the encoding of source files).
* How to represent text internally (the encoding of strings).

This post focuses on the last problem. But before we dive into the internals of Python strings, let's briefly discuss the problem of text encoding on a real life example and clarify what Unicode really is.

## The essence of text encoding

You see this text as a sequence of characters rendered by your browser and displayed on your screen. I see this text as the same sequence of characters as I type it into my editor. In order for us to see the same thing, your browser and my editor must be able to represent the same set of characters, that is, they must agree on a **character set**. They also need to choose some, possibly different, ways to represent the text internally to be able to work with it. For example, they may choose to associate each character with a unit consisting of one or more bytes and represent the text as a sequence of those units. Such a mapping is usually referred to as a **character encoding**. A character encoding is also crucial for our communication. Your browser and my webserver must must agree on how to **encode** text into bytes and **decode** text from bytes, since bytes is what they transmit to talk to each other.

The character set that your browser and my editor use is Unicode. Unicode is able to represent English as well as any other written language you can think of (文言, Čeština, Ελληνικά, עברית, हिन्दी), 日本語, Português, Русский) and thousands of miscellaneous symbols (₤, ⅐, ↳, ∭, ⌘, , ♫, 👨🏼‍💻, 🍺) . My webserver returns this text as a part of the HTML page in the UTF-8 encoding. You browser knows which encoding was used to encode the text because the `Content-Type` HTTP header declares the encoding in the response:

```text
Content-Type: text/html; charset=utf-8
```

Even if you save this HTML page locally, your browser will still be able to detect its encoding because the encoding is specified in the HTML itself:

```html
<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="utf-8" />
 	<!-- ... -->
</html>
```

This may seem absurd to you. How can a browser decode the HTML to read the encoding if it doesn't know the encoding yet? This is usually not a problem in practice because the beginning of an HTML page contains only ASCII characters and most encodings used on the web encode ASCII characters in the same way. Check out the [HTML standard](https://html.spec.whatwg.org/multipage/parsing.html#concept-encoding-confidence) to learn more about the algorithm that browsers use to determine the encoding.

Note that the HTTP header and the HTML metatag specify "charset", i.e. a character set. This may seem confusing since UTF-8 is not a character set. What they really specify is a character encoding. The two terms are often used interchangeably because character encodings typically imply a character set of the same name. For example, the ASCII character encoding implies the ASCII character set. The Unicode Standard fixes the terminology by giving precise definitions to all important terms. We'll study them, but before, let's discuss why and how the Unicode project began.

## The road to Unicode

Before the adoption of Unicode, most computer systems used the [ASCII](https://en.wikipedia.org/wiki/ASCII) character encoding that encodes a set of 128 characters using a 7-bit pattern to encode each character. ASCII was sufficient to deal with English texts but that's about it. Other character encodings were developed to support more languages. Most of them [extended ASCII](https://en.wikipedia.org/wiki/Extended_ASCII) to 256 characters encoding each character with 8 bits. For example, the [ISO 8859](https://en.wikipedia.org/wiki/ISO/IEC_8859) standard defined a family of 15 such character encodings. Among them were:

* Latin Western European ISO 8859-1 (German, French, Portuguese, Italian, ...)
* Central European ISO 8859-2 (Polish, Croatian, Czech, Slovak, ...)
* Latin/Cyrillic ISO 8859-5 (Russian, Serbian, Ukrainian, ...)
* Latin/Arabic ISO 8859-6
* Latin/Greek ISO 8859-7.

Multi-lingual software had to handle many different character encodings. This complicated things a lot. Another problem was to choose the right encoding to decode text. Failing to do so resulted in a garbled text known as [mojibake](https://en.wikipedia.org/wiki/Mojibake). For example, if you encode the Russian word for mojibake "кракозябры" using the [KOI-8](https://en.wikipedia.org/wiki/KOI8-R) encoding and decode it using ISO 8859-1, you'll get "ËÒÁËÏÚÑÂÒÙ".

The problems with different character encodings are not gone completely. Nevertheless, it became much more easier to write multi-lingual software nowadays. This is due to two independent initiatives that began in the late 1980s. One was [ISO 10646](https://en.wikipedia.org/wiki/Universal_Coded_Character_Set), an international standard, and the other was Unicode, a project orginized by a consortium of software companies. Both projects had the same goal: to replace hundreds of conflicting character encodings with a single universal one that covers all languages in widespread use. They quickly realized that having two different universal character sets wouldn't help achieve the goal, so in 1991 the Universal Coded Character Set (UCS) defined by ISO and Unicode's character set were unified. And though today two projects define the same character encoding model, both continue to exist. The difference between them is that the Unicode Standard has a greater scope:

> The assignment of characters is only a small fraction of what the Unicode Standard and its associated specifications provide. The specifications give programmers extensive descriptions and a vast amount of data about the handling of text, including how to:
>
> * divide words and break lines 
> * sort text in different languages 
> * format numbers, dates, times, and other elements appropriate to different locales 
> * display text for languages whose written form flows from right to left, such as Arabic or Hebrew 
> * display text in which the written form splits, combines, and reorders, such as for the languages of South Asia 
> * deal with security concerns regarding the many look-alike characters from writing systems around the world

The most important thing we need to understand about Unicode is how it encodes characters.

## Unicode basics

Unicode defines **characters** as smallest components of written language that have semantic value. This means that such units as diacritical marks are considered to be characters on their own. Multiple Unicode characters can be combined to produce what visually looks like a single character. Such combinations of characters are called **grapheme clusters** in Unicode. For example, the string "á" is a grapheme cluster that consists of two characters: the Latin letter "a" and the accute accent "´". Unicode encodes some grapheme clusters as separate characters as well, but does that solely for compatibility with legacy encodings. Due to combining characters, Unicode can represent all sorts of grapheme clusters such as "ä́" and, at the same time, keep the character set relatively simple.

Unicode characters are abstract. The standard doesn't care about the exact shape a character takes when it's rendered. The shape, called a **glyph**, is considered to be a concern of a font designer. The connection between characters and glyps can be quite compilcated. Multiple characters can merge into a single glyph. A single character can be rendered as multiple glyphs. And how characters map to glyphs can depend on the context. Check out the [Unicode Technical Report #17](https://www.unicode.org/reports/tr17/#CharactersVsGlyphs) for examples.

Unicode doesn't map characters to bytes directly. It does the mapping in two steps:

1. The **coded character set** maps characters to code points.
2. A **character encoding form**, such as UTF-8, maps code points to sequences of code units, where each code unit is a sequence of one or more bytes.

The Unicode coded character set is what we usually mean when we say Unicode. It's the same thing as the UCS defined by ISO 10646. The word "coded" means that it's not actually a set but a mapping. This mapping assigns a code point to each character in the character set. A **code point** is just an integer in the range [0, 1114111], which is written as U+0000..U+10FFFF in the Unicode hexadecimal notation and is called a **code space**. The current Unicode 13.0 assigns code points to 143,859 characters.

Techically, the coded character set is a [collection of entries](https://www.unicode.org/charts/). Each entry defines a character and assigns a code point to it by specifying three pieces of information:

* the code point value
* the name of the character; and
* a representative glyph.

For example, the entry for the letter "b" looks like this: (U+0062, LATIN SMALL LETTER B, b).

The standard also specifies various character properties such as whether the character is a letter, a numeral or some other symbol, whether it's written from left-to-right or from right-to-left and whether it's an uppercase letter, lowercase letter or doesn't have a case at all. All this information is contained in the [Unicode Character Database](https://unicode.org/ucd/).

If we encode some text with the coded character set, what we get is a sequence of code points called a **Unicode string**. This is the right level of abstraction to do text processing. Computers, however, know nothing about code points, so code points must be encoded to bytes. Unicode defines three character encoding forms to do that: UTF-8, UTF-16 and UTF-32. Each is capable of encoding the whole code space but has its own strengths and weaknesses.

UTF-32 is the most straightforward encoding form. Each code point is represented by a code unit of 32 bits. For example, the code point U+01F193 is encoded as `0x0001F193`. The main advantage of UTF-32, besides simplicity, is that it's a fixed-width encoding form, i.e. each code point corresponds to a fixed number of code units. This allows fast code point indexing: we can access the nth code point of a UTF-32-encoded string in constant time.

Originally, Unicode defined only one encoding form that represented each code point by a code unit of 16 bits. It was possible to encode the whole code space using this encoding form because the code space was smaller and consisted of 2^16 = 65,536 code points. Over time, the Unicode Consortium realized that 65,536 code points were not enough and extended the code space to 1,114,112 code points. The problem was that the new code points, which constituted the range U+10000..U+10FFFF, could not be represented by a single 16-bit code unit. Unicode solved this problem by encoding the new code points with a pair of 16-bit code units, called a **surrogate pair**. Two unassigned ranges of code points were reserved to be used only in surrogate pairs: U+D800..U+DBFF for higher parts of surrogate pairs and U+DC00..U+DFFF for lower parts of surrogate pairs. Each of these ranges consists of 1024 code points, so they can be used to encode 1024 × 1024 = 1,048,576 code points. This encoding form that uses one 16-bit code unit to encode code points in the range U+0000..U+FFFF and two 16-bit code units to encode code points in the range U+10000..U+10FFFF became known as UTF-16. Its original version is a part of the ISO 10646 standard and is called UCS-2. The only difference between UTF-16 and UCS-2 is that UCS-2 is only capable of encoding code points in the range U+0000..U+FFFF known as the Basic Multilingual Plane (BMP). The ISO 10646 standard also defines the UCS-4 encoding form, which is the same thing as UTF-32.

UTF-32 and UTF-16 are widely used for representing Unicode strings in programs. They are, however, not very suitable for text storage and transmission. The first problem is that they are space-inefficient. This is especially true when a text that consists mostly of ASCII characters is encoded using the UTF-32 encoding form. The second problem is that bytes in a code unit can be arranged in a little-endian or big-endian order, so UTF-32 and UTF-16 come in two flavors each. The special code point called the byte order mark (BOM) is often added to the beginning of a text to specify the endianness. And the proper handling of BOMs adds complexity. The UTF-8 encoding form doesn't have these issues. It represents each code point by a sequence of one, two, three or four bytes. The leading bits of the first byte indicate the length of the sequence. Other bytes always have the form `0b10xxxxxx` to distinguish them from the first byte. The following table shows what sequences of each length look like and what ranges of code points they encode:

| Range             | Byte 1       | Byte 2       | Byte 3       | Byte 4       |
| ----------------- | ------------ | ------------ | ------------ | ------------ |
| U+0000..U+007F    | `0b0xxxxxxx` |              |              |              |
| U+0080..U+07FF    | `0b110xxxxx` | `0b10xxxxxx` |              |              |
| U+0800..U+FFFF    | `0b1110xxxx` | `0b10xxxxxx` | `0b10xxxxxx` |              |
| U+10000..U+10FFFF | `0b11110xxx` | `0b10xxxxxx` | `0b10xxxxxx` | `0b10xxxxxx` |

To encode a code point, we choose an appropriate template from the table above and replace xs in it with the binary representation of a code point. An appropriate template is the shortest template that is capable of encoding the code point. The binary representation of a code point is aligned to the right, and the leading xs are replaced with 0s.

Note that UTF-8 represents all ASCII characters using just one byte, so that any ASCII-encoded text is also a UTF-8-encoded text. This feature is one of the reasons why UTF-8 gained adoption and [became](https://googleblog.blogspot.com/2008/05/moving-to-unicode-51.html) the most dominant encoding on the web.

This section should give us a basic idea of how Unicode works. If you want to learn more about Unicode, I really recommend reading the first few chapters of the [Unicode Standard](https://www.unicode.org/versions/Unicode13.0.0/).

## A brief history of Python strings

The way Python strings work today is very different from the way Python strings worked when Python was first released. This aspect of the language changed significantly multiple times. To better understand why modern Python strings work the way they do, let's take a quick look into the past.

Initially, Python had one built-in type to represent strings – the `str` type. It was not the `str` type we know today. Python strings were byte strings, that is, sequences of bytes, and worked similar to how `bytes` objects work in Python 3. This is in constrast to Python 3 strings that are Unicode strings.

Since byte strings were sequences of bytes, they were used to represent all kinds of data: sequences of ASCII characters, UTF-8-encoded texts and arbitrary arrays of bytes. Byte strings themselves didn't hold any information about the encoding. It was up to a program to interpret the values. For example, we could put a UTF-8-encoded text into a byte string, print it to the stdout and see the actual Unicode characters if the terminal encoding was UTF-8:

```pycon
$ python2.7
>>> s = '\xe2\x9c\x85'
>>> print(s)
✅
```

Though byte strings were sequences of bytes, they were called strings for a reason. The reason is that Python provided string methods for byte strings, such as `str.split()` and `str.upper()`. Think about what the `str.upper()` method should do on a sequence of bytes. It doesn't make sense to take a byte and convert it to an uppercase variant because bytes don't have case. It starts make sense if we assume that the sequence of bytes is a text in some encoding. That's exactly what Python did. The assumed encoding depended on a [locale](https://en.wikipedia.org/wiki/Locale_(computer_software)). Typically, it was ASCII. We could change the locale, so that string methods started to work on non-ASCII encoded text:

```pycon
$ python2.7
>>> s = '\xef\xe8\xf2\xee\xed' # Russian 'питон' in the encoding windows-1251
>>> '\xef\xe8\xf2\xee\xed'.upper() # does nothing since characters are non-ascii
'\xef\xe8\xf2\xee\xed'
>>> import locale
>>> locale.setlocale(locale.LC_ALL , 'ru_RU.CP1251')
'ru_RU.CP1251'
>>> '\xef\xe8\xf2\xee\xed'.upper() # converts to uppercase
'\xcf\xc8\xd2\xce\xcd'
>>> print('\xef\xe8\xf2\xee\xed'.upper().decode('windows-1251')) # let's print it
ПИТОН
```

The implementation of this logic relied on the C standard library. It worked for 8-bit fixed-width encodings but didn't work for UTF-8 or any other Unicode encoding. In short, Python had no Unicode strings back then.

Then the `unicode` type was introduced. This happened before Python 2 when PEPs hadn't existed yet. The change was only later described in [PEP 100](https://www.python.org/dev/peps/pep-0100/). The instances of `unicode` were true Unicode strings, that is, sequences of code points (or, if you prefer, sequences of Unicode characters). They worked much like strings we have today:

```pycon
$ python2.7
>>> s = u'питон' # note unicode literal
>>> s # each element is a code point
u'\u043f\u0438\u0442\u043e\u043d'
>>> s[1] # can index code points
u'\u0438'
>>> print(s.upper()) # string methods work
ПИТОН
```

Python used the UCS-2 encoding to represent Unicode strings internally. UCS-2 was capable of encoding all the code points that were assigned at that moment. But then Unicode assigned first code points outside the Basic Multilingual Plane, and UCS-2 could no longer encode all the code points. Python switched from UCS-2 to UTF-16. Now any code point outside the Basic Multilingual Plane could be represented by a surrogate pair. This caused another problem. Since UTF-16 is a variable-width encoding, getting the nth code point of a string requires scanning the string until that code point is found. Python had string indexing in constant time and didn't want to lose that. So, what happend is that Unicode objects siezed to be true Unicode strings and became sequence of code units. This had the following consequences:

```pycon
$ python2.7
>>> u'hello'[4] # indexing is still supported and works fast
u'o'
>>> len(u'😀') # but length of a character outside BMP is 2
2
>>> u'😀'[1] # and indexing returns code units, not code points
u'\ude00'
```

[PEP 261](https://www.python.org/dev/peps/pep-0261/) tried to revive true Unicode strings. It introduced a compile-time option that enabled the UCS-4 encoding. Now Python had two distinct builds: a "narrow" build and a "wide" build. The choice of the build affected the way Unicode objects worked. UCS-4 could not replace UTF-16 altogether because of its space-inefficiency, so both had to coexist. Internally, Unicode object was represented as an array of `Py_UNICODE` elements. The `Py_UNICODE` type was set to `wchar_t` if the size of `wchar_t` was compatible with the build. Otherwise, it was set to either `unsigned short` (UTF-16) or  `unsigned long` (UCS-4).

In the meantime, Python developers focused their attention on another source of confusion: the coexistence of byte strings and Unicode strings. There were several problems with this. For example, it was possible to mix two types:

```pycon
>>> "I'm str" + u" and I'm unicode"
u"I'm str and I'm unicode"
```

Unless it wasn't:

```pycon
>>> "I'm str \x80" + u" and I'm unicode"
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
UnicodeDecodeError: 'ascii' codec can't decode byte 0x80 in position 8: ordinal not in range(128)
```

The famous Python 3.0 release renamed the `unicode` type to the `str` type and replaced the `str` type with the `bytes` type. The essence of this change summarized in the [release notes](https://docs.python.org/3/whatsnew/3.0.html#text-vs-data-instead-of-unicode-vs-8-bit):

> The biggest difference with the 2.x situation is that any attempt to mix text and data in Python 3.0 raises `TypeError`, whereas if you were to mix Unicode and 8-bit strings in Python 2.x, it would work if the 8-bit string happened to contain only 7-bit (ASCII) bytes, but you would get `UnicodeDecodeError` if it contained non-ASCII values. This value-specific behavior has caused numerous sad faces over the years.

Python strings became the Python strings we know today with the release of Python 3.3. [PEP 393](https://www.python.org/dev/peps/pep-0393/) got rid of "narrow" and "wide" builds and introduced the flexible string representation. This representation made Python strings true Unicode strings without exceptions. Its essence can be summarized as follows. Three different fixed-width encodings are used to represent strings: UCS-1, UCS-2 and UCS-4. Which encoding is used for a given string depends on the largest code point of that string:

* If all code points are in the range U+0000..U+00FF, then UCS-1 is used. UCS-1 encodes code points in that range with one byte and does not encode other code points at all. It's equivalent to the Latin-1 (ISO 8859-1) encoding.
* If all code points are in the range U+0000..U+FFFF and at least one code point is in the range U+0100..U+FFFF, then UCS-2 is used.
* Finally, if at least one code point is in the range U+10000..U+10FFFF, then UCS-4 is used.

In addition to this, CPython distinguishes the case when a string contains only ASCII characters. Such strings are encoded using UCS-1 but stored in a special way. Let's take a look at the actual code to understand the details.

## Meet modern Python strings

CPython uses three structs to represent string objects: `PyASCIIObject`, `PyCompactUnicodeObject` and `PyUnicodeObject`. The second one extends the first one, and the third one extends the second one:

```C
typedef struct {
  PyObject_HEAD
  Py_ssize_t length;
  Py_hash_t hash;
  struct {
      unsigned int interned:2;
      unsigned int kind:2;
      unsigned int compact:1;
      unsigned int ascii:1;
      unsigned int ready:1;
  } state;
  wchar_t *wstr;
} PyASCIIObject;

typedef struct {
  PyASCIIObject _base;
  Py_ssize_t utf8_length;
  char *utf8;
  Py_ssize_t wstr_length;
} PyCompactUnicodeObject;

typedef struct {
  PyCompactUnicodeObject _base;
  union {
      void *any;
      Py_UCS1 *latin1;
      Py_UCS2 *ucs2;
      Py_UCS4 *ucs4;
  } data;
} PyUnicodeObject;
```

Why do we need all these structs? Recall that CPython provides the [Python/C API](https://docs.python.org/3/c-api/index.html) that allows writing C extensions. In particular, it provides a [set of functions to work with strings](https://docs.python.org/3/c-api/unicode.html#unicode-objects-and-codecs). Many of these functions expose the internal representation of strings, so PEP 393 could not get rid of the old representation without breaking C extensions. One of the reasons why the current representation of strings is more compilcated than it should be is because CPython continues to provide the old API. For example, it provides the `PyUnicode_AsUnicode()` function that returns the `Py_UNICODE*` representation of a string.

Let's first see how CPython represents strings created using the new API. These are called "canonical" strings. They include all the strings that we create when we write Python code. The `PyASCIIObject` struct is used to represent ASCII-only strings. The buffer that holds a string is not a part of the struct but immediately follows it. The allocation is done at once like this:

```C
obj = (PyObject *) PyObject_MALLOC(struct_size + (size + 1) * char_size);
```

The `PyCompactUnicodeObject` struct is used to represent all other Unicode strings. The buffer is allocated in the same way right after the struct. Only `struct_size` is different and `char_size` can be `1`,  `2` or `4`.

The reason why both `PyASCIIObject` and `PyCompactUnicodeObject` exist is because of an optimization. It's often neccessary to get a UTF-8 representation of a string. If a string is an ASCII-only string, then CPython can simply return the data stored in the buffer. But otherwise, CPython has to perform a conversion from the current encoding to UTF-8. The `utf8` field of `PyCompactUnicodeObject` is used to store the cached UTF-8 representation. A UTF-8 representation is not always cached. The special API function [`PyUnicode_AsUTF8AndSize()`](https://docs.python.org/3/c-api/unicode.html#c.PyUnicode_AsUTF8AndSize)  should be called when the cache is needed.

If someone requests the old `Py_UNICODE*` representation of a "compact" string, then CPython may need to perform a conversion. Similiarly to `utf8`, the `wstr` field of `PyASCIIObject` is used to store the cached `Py_UNICODE*` representation. 

The old API allowed creating strings with a `NULL` buffer and filling the buffer afterwards. Today the strings created in this way are called "legacy" strings. They are represented by the `PyUnicodeObject` struct. Initially, they have only the `Py_UNICODE*` representation. The `wstr` field is used to hold it. The users of the API must call the [`PyUnicode_READY()`](https://docs.python.org/3/c-api/unicode.html#c.PyUnicode_READY) function on "legacy" strings to make them work with the new API. This function stores the canonical (USC-1, UCS-2 or UCS-4) representation of a string in the `data` field of `PyUnicodeObject`.

The old API is still supported but deprecated. [PEP 623](https://www.python.org/dev/peps/pep-0623/) lays down a plan to remove it in Python 3.12.

