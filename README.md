# pubparser

`pubparser` is a small, safe, permissively licensed EPUB parsing toolkit. It focuses on structural parsing, inspection, extraction, validation, and conservative source normalization without becoming a browser or rendering engine.

Current development target: **0.1**.

## Principles

- MIT-licensed project code.
- Python standard-library-only runtime core.
- EPUB input is treated as untrusted.
- Parsing, rendering, validation, and source cleanup remain separate layers.
- Resources are read lazily instead of expanding the whole archive on open.
- Remote resources are never fetched automatically.
- DRM bypass is out of scope; encryption metadata is only inspected and classified.

## Current capabilities

- security-checked ZIP/OCF container access;
- `META-INF/container.xml` and multiple rootfiles;
- EPUB 2 and EPUB 3 OPF parsing;
- Dublin Core metadata plus EPUB `meta` properties/refinements;
- manifest, spine, reading direction, and rendition metadata;
- EPUB 3 Navigation Documents and EPUB 2 NCX normalized to one model;
- TOC, landmarks, page lists, and NCX nav lists;
- EPUB 2/3 cover discovery;
- lazy `ResourceCollection` access with bytes, streams, text decoding, and manifest filters;
- plain and structured XHTML text extraction;
- conservative Project Gutenberg header/footer normalization;
- `encryption.xml` inspection and font-obfuscation recognition;
- structural validation and typed diagnostics;
- CLI inspection, TOC, text extraction, and validation commands.

## Quick start

```python
from pubparser import open_epub

with open_epub("book.epub") as book:
    print(book.metadata.primary_title)
    print(book.metadata.primary_author)

    if book.navigation:
        for entry in book.navigation.toc:
            print(entry.label, entry.href)
```

Manifest resources are exposed through lazy handles and never trigger network access:

```python
with open_epub("book.epub") as book:
    cover_candidates = book.resources.with_property("cover-image")
    css_files = book.resources.by_media_type("text/css")
    chapter = book.resources["chapter-1"]
    data = chapter.read_bytes()
```

Remote manifest resources remain inspectable as metadata, but `read_bytes()`, `open()`, and `read_text()` refuse to fetch them.

Text extraction is spine-ordered and lazy when using `iter_text()`:

```python
with open_epub("book.epub") as book:
    for document in book.iter_text():
        print(document.resource.href)
        print(document.text)
```

Project Gutenberg cleanup is explicit and auditable:

```python
from pubparser import normalize_project_gutenberg, open_epub

with open_epub("book.epub") as book:
    result = normalize_project_gutenberg(book)
    for document in book.iter_text(normalization=result):
        print(document.text)
```

The source EPUB is never modified by normalization.

## CLI

```text
epubtool info BOOK.epub
epubtool metadata BOOK.epub
epubtool spine BOOK.epub
epubtool files BOOK.epub
epubtool toc BOOK.epub
epubtool text BOOK.epub
epubtool text --clean-gutenberg BOOK.epub
epubtool validate BOOK.epub
```

`info`, `metadata`, `spine`, `files`, `toc`, `text`, and `validate` support JSON output where applicable.

## Security model

The core enforces archive entry, resource-size, total-expanded-size, expansion-ratio, XML-size, and XML-depth limits. Archive traversal, absolute paths, drive-qualified paths, backslash paths, NUL paths, duplicate normalized paths, unsafe XML entities/DTDs, malformed URI escapes, and EPUB-local references that escape the container root are rejected. A simple inert HTML5 doctype is permitted for XHTML content; DTD subsets and entity declarations remain rejected.

Scripts are never executed and external resources are never fetched as part of parsing.

## Real-world test fixture

A Project Gutenberg EPUB of H. G. Wells's *The Time Machine* is used as an optional real-world regression fixture. Its exact SHA-256 is recorded under `tests/fixtures/real/`; the binary is downloaded locally rather than committed to Git history.

## Scope

Not currently in scope:

- browser/rendering engine behavior;
- JavaScript execution;
- full CSS layout;
- DRM circumvention;
- EPUB writing/repacking;
- EPUBCheck-equivalent conformance coverage.

These boundaries are intentional. The project should remain useful as a focused parser/toolkit rather than becoming an all-format ebook framework.

## License

MIT. See `LICENSE` and `THIRD_PARTY_DEPENDENCIES.md`.
