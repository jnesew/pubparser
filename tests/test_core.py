from __future__ import annotations

import io
import zipfile

import pytest

from pubparser import ContainerError, UnsafeArchiveError, open_epub
from pubparser.archive import EpubArchive, normalize_archive_path
from pubparser.security import SecurityLimits


def make_epub(*, container_xml: str | None = None, opf: str | None = None) -> io.BytesIO:
    container_xml = container_xml or '''<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>'''
    opf = opf or '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:identifier id="pub-id">urn:test</dc:identifier>
  <dc:title>Test Book</dc:title>
  <dc:creator>Example Author</dc:creator>
  <dc:language>en</dc:language>
 </metadata>
 <manifest><item id="chap" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
 <spine><itemref idref="chap"/></spine>
</package>'''
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("EPUB/package.opf", opf)
        zf.writestr("EPUB/chapter.xhtml", "<html xmlns='http://www.w3.org/1999/xhtml'><body><p>Hello</p></body></html>")
    bio.seek(0)
    return bio


def test_open_epub_parses_package_and_lazy_resource():
    with open_epub(make_epub()) as book:
        assert book.metadata.primary_title == "Test Book"
        assert book.metadata.primary_author == "Example Author"
        assert book.package.version == "3.0"
        assert book.spine[0].resource.resolved_path == "EPUB/chapter.xhtml"
        assert b"Hello" in book.read_resource("chap")


def test_normalize_archive_path_rejects_escape():
    with pytest.raises(UnsafeArchiveError):
        normalize_archive_path("../outside")


def test_duplicate_normalized_paths_rejected():
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("a/../b", "one")
        zf.writestr("b", "two")
    bio.seek(0)
    with pytest.raises(UnsafeArchiveError):
        EpubArchive(bio).open()


def test_doctype_is_rejected():
    xml = '''<!DOCTYPE container [<!ENTITY x "boom">]><container><rootfiles><rootfile full-path="EPUB/package.opf"/></rootfiles></container>'''
    with pytest.raises(ContainerError):
        open_epub(make_epub(container_xml=xml))


def test_entry_count_limit():
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("a", "1")
        zf.writestr("b", "2")
    bio.seek(0)
    limits = SecurityLimits(max_entries=1)
    with pytest.raises(UnsafeArchiveError):
        EpubArchive(bio, limits=limits).open()


def test_unknown_spine_reference_is_diagnostic():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>X</dc:title></metadata>
 <manifest><item id="chap" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
 <spine><itemref idref="missing"/></spine>
</package>'''
    with open_epub(make_epub(opf=opf)) as book:
        assert any(d.code == "EPUB_MISSING_MANIFEST_ITEM" for d in book.diagnostics)
