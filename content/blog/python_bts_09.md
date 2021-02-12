Title: Python behind the scenes #9: how Python strings work
Date: 2021-02-09 9:30
Tags: Python behind the scenes, Python, CPython

In 1991 Guido van Rossum released the first version of the Python programming language to the world. About that time the world began to witness a major change in how computer systems represent written language. The internalization of the Internet increased the demand to support different writing systems, and the Unicode standard was developed to meet this demand. Unicode defined a single character set able to represent any written language, various non-alphanumeric symbols and, eventually, emoji 😀. Python wasn't designed with Unicode in mind, but it evolved towards Unicode support during the years. In 2000, PEP 100 added built-in support for Unicode strings – the `unicode` type that later became the `str` type in Python 3. Python strings have been proven to be a handy way to work with text in the Unicode age. Today we'll see how they work behind the scenes.

## The scope of this post

This post doesn't try to cover all aspects of text encoding in relation to Python. You see, programming language designers have to make several text encoding decisions because they have to answer the following questions:

* How to talk to the external world (the encodings of command-line parameters, environment variables, standard streams and the file system).
* How to read the source code (the encoding of source files).
* How to represent text internally (the encoding of strings).

This post focuses on the last problem. But before we dive into the internals of Python strings, let's discuss the problem of text encoding as a whole and clarify what Unicode really is.

## The essence of text encoding

You see this text as a sequence of characters rendered by your browser and displayed on your screen. I see this text as the same sequence of characters as I type it into my editor. In order for us to see the same thing, your browser and my editor must be able to represent the same set of characters, that is, they must agree on a **character set**. They also need to choose some, possibly different, ways to represent the text internally to be able to work with it. For example, they may choose to associate each character with a unit of one or more bytes and represent the text as a sequence of those units. To make our communication possible, your browser and my webserver must agree on how to **encode** text into bytes and **decode** text from bytes, since bytes is what they transmit to talk to each other.

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

This may seem absurd to you. How can a browser decode the HTML to read the encoding if it doesn't know the encoding yet? This is usually not a problem in practice because the beginning of an HTML page contains only ASCII characters and most encodings used on the web encode ASCII characters in the same way. Browsers use a [clever algorithms](https://html.spec.whatwg.org/multipage/parsing.html#determining-the-character-encoding) to detect the encoding...

## Unicode basics

## Python's road to Unicode support

## Meet Python strings