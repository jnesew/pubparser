# pubparser extraction API

## Overview

`pubparser` separates EPUB parsing from downstream consumers. The parser exposes structural information and extracted document text without attempting to render pages or behave like a browser.

The primary extraction API is spine ordered and lazy:

```python
from pubparser import open_epub

with open_epub("book.epub") as book:
    for document in book.iter_documents():
        print(document.title)
        print(document.text)
```

## Document extraction

`iter_documents()` yields `ExtractedDocument` objects in publication spine order.

Each document contains:

- `resource` — the originating EPUB manifest resource;
- `text` — normalized visible text extraction;
- `blocks` — optional structured content blocks;
- `title` — derived display title;
- `title_source` — rule used to derive the title.

Title derivation is deterministic:

1. first meaningful `h1` in the document body;
2. first meaningful `h2` if no `h1` exists;
3. document `title` element;
4. manifest resource id fallback.

The eager equivalent is:

```python
with open_epub("book.epub") as book:
    documents = book.extract_documents()
```

## Compatibility mode

Normal parsing uses XML-safe XHTML parsing. Some real-world EPUB files contain HTML-like XHTML that browsers accept but XML parsers reject.

For these files:

```python
from pubparser import ParsingMode, open_epub

with open_epub("book.epub", mode=ParsingMode.COMPATIBILITY) as book:
    for document in book.iter_documents():
        print(document.text)
```

Compatibility recovery handles selected benign malformed markup while preserving the security model.

It does **not** enable:

- external resource loading;
- JavaScript execution;
- DTD processing;
- entity expansion;
- unsafe markup declarations.

## Backward compatibility

Older callers can continue using:

```python
book.iter_text()
book.extract_text()
```

These remain aliases for the document extraction API.

## Project Gutenberg cleanup

Project Gutenberg normalization is explicit and does not modify the source EPUB:

```python
from pubparser import normalize_project_gutenberg

with open_epub("book.epub") as book:
    cleanup = normalize_project_gutenberg(book)
    for document in book.iter_documents(normalization=cleanup):
        print(document.text)
```

This keeps source parsing, cleanup, and application-specific processing as separate layers.
