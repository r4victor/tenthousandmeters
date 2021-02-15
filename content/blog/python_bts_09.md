Title: Python behind the scenes #9: how Python strings work
Date: 2021-02-09 9:30
Tags: Python behind the scenes, Python, CPython

In 1991 Guido van Rossum released the first version of the Python programming language to the world. About that time the world began to witness a major change in how computer systems represent written language. The internalization of the Internet increased the demand to support different writing systems, and the Unicode standard was developed to meet this demand. Unicode defined a single character set able to represent any written language, various non-alphanumeric symbols and, eventually, emoji 😀. Python wasn't designed with Unicode in mind, but it evolved towards Unicode support during the years. In 2000, PEP 100 added built-in support for Unicode strings – the `unicode` type that later became the `str` type in Python 3. Python strings have been proven to be a handy way to work with text in the Unicode age. Today we'll see how they work behind the scenes.

## The scope of this post

This post doesn't try to cover all aspects of text encoding in relation to Python. You see, programming language designers have to make several text encoding decisions because they have to answer the following questions:

* How to talk to the external world (the encodings of command-line parameters, environment variables, standard streams and the file system).
* How to read the source code (the encoding of source files).
* How to represent text internally (the encoding of strings).

This post focuses on the last problem. But before we dive into the internals of Python strings, let's briefly discuss the problem of text encoding on a real life example and clarify what Unicode really is.

## Text encoding is everywhere

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

This may seem absurd to you. How can a browser decode the HTML to read the encoding if it doesn't know the encoding yet? This is usually not a problem in practice because the beginning of an HTML page contains only ASCII characters and most encodings used on the web encode ASCII characters in the same way. Check out [the HTML standard](https://html.spec.whatwg.org/multipage/parsing.html#concept-encoding-confidence) to learn more about the algorithm that browsers use to determine the encoding.

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

The Unicode coded character set is what we usually mean when we say Unicode. It's the same thing as the UCS defined by ISO 10646. The word "coded" means that it's not actually a set but a mapping. This mapping assigns a code point to each character in the character set. A **code point** is just an integer in the range [0, 1114111], which is written as U+0000..U+10FFFF in the Unicode hexadecimal notation. The range of code points is called a **code space.** As of Unicode 13.0, out of 1,114,112 code points in the code space 143,859 are assigned.

Techically, the coded character set is a [collection of entries](https://www.unicode.org/charts/). Each entry defines a character and assigns a code point to it by specifying three pieces of information:

* the code point value
* the name of the character; and
* a representative glyph.

For example, the entry for the letter "b" looks like this: (U+0062, LATIN SMALL LETTER B, b).

The standard also specifies various character properties such as whether the character is a letter, a numeral or some other symbol, whether it's written from left-to-right or from right-to-left and whether it's an uppercase letter, lowercase letter or doesn't have a case at all. All this information is contained in the [Unicode Character Database](https://unicode.org/ucd/).

If we encode some text with the coded character set, what we get is a sequence of code points. This is the right level of abstraction to do text processing. Computers, however, know nothing about code points, so code points must be encoded to bytes. Unicode defines three character encoding forms to do that: UTF-8, UTF-16 and UTF-32. Each is capable of encoding the whole code space but has its own strengths and weaknesses.

UTF-32 is the most straightforward encoding form. Each code point is represented by a code unit of 32 bits. For example, the code point U+01F193 is encoded as `0x0001F193`. The main advantage of UTF-32, besides simplicity, is that it's a fixed-width encoding form, i.e. each code point corresponds to a fixed number of code units. This allows fast code point indexing: we can access the nth code point of a UTF-32-encoded string for $O(1)$.



## Python's road to Unicode support

## Meet Python strings