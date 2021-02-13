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

Note that the HTTP header and the HTML metatag specify "charset", i.e. a character set. This may seem confusing since UTF-8 is not a character set. What they really specify is a character encoding. The two terms are often used interchangeably because character encodings used to define a character set of the same name. For example, the ASCII character encoding defines the ASCII character set. The Unicode Standard fixes the terminology by giving precise definitions to all important terms. We'll study them, but before, let's discuss why and how the Unicode project began.

## The road to Unicode

Before the adoption of Unicode, most computer systems used the [ASCII](https://en.wikipedia.org/wiki/ASCII) character encoding that encodes a set of 128 characters using a 7-bit pattern to encode each character. ASCII was sufficient to deal with English texts but that's about it. Other character encodings were developed to support more languages. Most of them [extended ASCII](https://en.wikipedia.org/wiki/Extended_ASCII) to 256 characters and used 8 bits per character. For example, the [ISO 8859](https://en.wikipedia.org/wiki/ISO/IEC_8859) standard defined a family of 15 such character encodings. Among them were:

* Latin Western European ISO 8859-1 (German, French, Portuguese, Italian, ...)
* Central European ISO 8859-2 (Polish, Croatian, Czech, Slovak, ...)
* Latin/Cyrillic ISO 8859-5 (Russian, Serbian, Ukrainian, ...)
* Latin/Arabic ISO 8859-6
* Latin/Greek ISO 8859-7

Multi-lingual software had to handle many different character encodings. This complicated things a lot. Another problem was to choose the right encoding to decode text. Failing to do so resulted in a garbled text known as [mojibake](https://en.wikipedia.org/wiki/Mojibake). For example, if you encode the Russian word for mojibake "кракозябры" using the [KOI-8](https://en.wikipedia.org/wiki/KOI8-R) encoding and decode it using ISO 8859-1, you'll get "ËÒÁËÏÚÑÂÒÙ".

These problems with different character encodings are not gone completely. Nevertheless, it became much more easier to write multi-lingual software nowadays. This is due to two independent initiatives that began in the late 1980s. One was [the ISO 10646 project](https://en.wikipedia.org/wiki/Universal_Coded_Character_Set) led by the the International Organization for Standardization (ISO). The other was [the Unicode project](https://home.unicode.org/) led by an association of software companies. Both projects had the same goal: to replace hundreds of conflicting character encodings with a single universal one that covers all languages in widespread use. They quickly realized that it doesn't make sense to have two different universal character encodings, so 

## Unicode basics



## Python's road to Unicode support

## Meet Python strings