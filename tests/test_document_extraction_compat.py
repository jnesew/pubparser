from __future__ import annotations

import io
import zipfile

import pytest

from pubparser import ResourceError, open_epub


def make_epub(chapter_markup: str, *, item_id: str = "chapter") -> io.BytesIO:
    bio = io.BytesIO()
    container = (
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="EPUB/package.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = f'''<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">
      <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:identifier id="book-id">urn:test:document-extraction</dc:identifier>
        <dc:title>Fixture</dc:title>
        <dc:language>en</dc:language>
        <meta property="dcterms:modified">2026-08-31T00:00:00Z</meta>
      </metadata>
      <manifest><item id="{item_id}" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
      <spine><itemref idref="{item_id}"/></spine>
    </package>'''
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("EPUB/package.opf", opf)
        zf.writestr("EPUB/chapter.xhtml", chapter_markup)
    bio.seek(0)
    return bio


def first_document(epub: io.BytesIO, *, mode: str = "normal"):
    with open_epub(epub, mode=mode) as book:
        return next(book.iter_documents())


def test_iter_documents_uses_h1_h2_title_resource_id_precedence():
    document = first_document(
        make_epub(
            '''<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Document title</title></head>
            <body><h2>Secondary heading</h2><h1>Primary heading</h1><p>Body text.</p></body></html>'''
        )
    )
    assert document.title == "Primary heading"
    assert document.title_source == "h1"
    assert "Body text." in document.text

    document = first_document(
        make_epub(
            '''<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Document title</title></head>
            <body><h2>Secondary heading</h2><p>Body text.</p></body></html>'''
        )
    )
    assert document.title == "Secondary heading"
    assert document.title_source == "h2"

    document = first_document(
        make_epub(
            '''<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Document title</title></head>
            <body><p>Body text.</p></body></html>'''
        )
    )
    assert document.title == "Document title"
    assert document.title_source == "title"

    document = first_document(
        make_epub(
            '''<html xmlns="http://www.w3.org/1999/xhtml"><head></head><body><p>Body text.</p></body></html>''',
            item_id="fallback-id",
        )
    )
    assert document.title == "fallback-id"
    assert document.title_source == "resource-id"


def test_iter_text_remains_compatible_and_exposes_titles():
    epub = make_epub(
        '''<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Chapter One</h1><p>Hello world.</p></body></html>'''
    )
    with open_epub(epub) as book:
        documents = tuple(book.iter_text())
        assert documents == book.extract_documents()
        assert documents == book.extract_text()
        assert documents[0].title == "Chapter One"


def test_compatibility_mode_recovers_common_malformed_html():
    malformed = '''<!DOCTYPE html><html><head><title>Fallback title</title></head>
    <body><h1>Chapter One<p>Hello <b>world</body></html>'''

    with open_epub(make_epub(malformed), mode="normal") as book:
        with pytest.raises(ResourceError):
            next(book.iter_documents())

    document = first_document(make_epub(malformed), mode="compatibility")
    assert document.title == "Chapter One"
    assert document.title_source == "h1"
    assert "Hello world" in document.text
    assert any(block.kind == "heading" and block.text == "Chapter One" for block in document.blocks)


def test_compatibility_mode_does_not_relax_unsafe_declaration_checks():
    unsafe = '''<!DOCTYPE html [<!ENTITY boom "expanded">]>
    <html><body><h1>Unsafe</h1><p>&boom;</p></body></html>'''
    with open_epub(make_epub(unsafe), mode="compatibility") as book:
        with pytest.raises(ResourceError, match="unsafe|cannot extract"):
            next(book.iter_documents())


def test_compatibility_mode_handles_omitted_paragraph_end_tags_without_duplicate_text():
    malformed = '''<html><body><h2>Section</h2><p>First paragraph<p>Second paragraph</body></html>'''
    document = first_document(make_epub(malformed), mode="compatibility")
    assert document.title == "Section"
    assert document.text.count("First paragraph") == 1
    assert document.text.count("Second paragraph") == 1
    paragraphs = [block.text for block in document.blocks if block.kind == "paragraph"]
    assert paragraphs == ["First paragraph", "Second paragraph"]
