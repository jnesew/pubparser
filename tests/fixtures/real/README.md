# Real-world EPUB fixtures

## Project Gutenberg 35 — *The Time Machine*

This directory tracks a real Project Gutenberg EPUB supplied for parser regression testing. The binary EPUB itself is intentionally not required in Git history; `pg35/fetch_fixture.py` retrieves the exact sample and refuses to accept changed bytes unless its recorded SHA-256 is reviewed and updated.

Fixture facts recorded from the supplied EPUB itself:

- Title: *The Time Machine*
- Creator: H. G. Wells
- EPUB identifier: `http://www.gutenberg.org/35`
- EPUB version: 3.0
- Source recorded in package metadata: `https://www.gutenberg.org/files/35/35-h/35-h.htm`
- Rights recorded in package metadata: `Public domain in the USA.`
- SHA-256: `5bb9169caeca3866d7e62eac8ea24ba8be98cc6cf7d004acd227ddd12a110126`

The fixture is especially useful because it includes an EPUB 3 Navigation Document (`toc.xhtml`), an EPUB 2 NCX (`toc.ncx`), a cover image, multiple XHTML spine documents, stylesheets, and explicit Project Gutenberg header/footer spine entries.

To install the fixture locally:

```bash
python tests/fixtures/real/pg35/fetch_fixture.py
```

`tests/test_real_fixture.py` skips when the optional real-world fixture is absent, so ordinary offline unit tests remain deterministic and network-free. When the fixture is present, its SHA-256 and expected package structure are checked before parser assertions run.

This fixture is test data, not part of the pubparser library runtime.
