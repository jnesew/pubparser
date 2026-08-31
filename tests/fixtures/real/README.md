# Real-world EPUB fixtures

## Project Gutenberg 35 — *The Time Machine*

The `pg35/pg35-images-3.epub.b64.part*` files are the Base64-encoded bytes of a real Project Gutenberg EPUB supplied for parser regression testing. Tests concatenate and decode the parts in memory; the split representation is repository-transport plumbing only and does not modify the EPUB bytes.

Fixture facts recorded from the EPUB itself:

- Title: *The Time Machine*
- Creator: H. G. Wells
- EPUB identifier: `http://www.gutenberg.org/35`
- EPUB version: 3.0
- Source recorded in package metadata: `https://www.gutenberg.org/files/35/35-h/35-h.htm`
- Rights recorded in package metadata: `Public domain in the USA.`
- SHA-256 of decoded EPUB: `5bb9169caeca3866d7e62eac8ea24ba8be98cc6cf7d004acd227ddd12a110126`

The fixture is useful because it includes an EPUB 3 Navigation Document (`toc.xhtml`), an EPUB 2 NCX (`toc.ncx`), a cover image, multiple XHTML spine documents, stylesheets, and explicit Project Gutenberg header/footer spine entries.

This fixture is test data, not part of the pubparser library runtime.
