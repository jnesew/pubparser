from __future__ import annotations

import io
import zipfile

import pytest

from pubparser import ContainerError, ParsingMode, ValidationError, open_epub


def make_multi_rootfile_epub() -> io.BytesIO:
    bio = io.BytesIO()
    container = '''<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>
      <rootfile full-path="A/package.opf" media-type="application/oebps-package+xml"/>
      <rootfile full-path="B/package.opf" media-type="application/oebps-package+xml"/>
    </rootfiles></container>'''
    def opf(title: str, chapter: str) -> str:
        return f'''<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
          <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{title}</dc:title></metadata>
          <manifest><item id="c" href="{chapter}" media-type="application/xhtml+xml"/></manifest>
          <spine><itemref idref="c"/></spine></package>'''
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("A/package.opf", opf("First", "one.xhtml"))
        zf.writestr("A/one.xhtml", "<html/>")
        zf.writestr("B/package.opf", opf("Second", "two.xhtml"))
        zf.writestr("B/two.xhtml", "<html/>")
    bio.seek(0)
    return bio


def test_rootfile_can_be_selected_by_index_or_declared_path():
    epub = make_multi_rootfile_epub()
    with open_epub(epub) as book:
        assert len(book.container.rootfiles) == 2
        assert book.metadata.primary_title == "First"
    epub.seek(0)
    with open_epub(epub, rootfile=1) as book:
        assert book.metadata.primary_title == "Second"
        assert book.resources["c"].resolved_path == "B/two.xhtml"
    epub.seek(0)
    with open_epub(epub, rootfile="B/package.opf") as book:
        assert book.metadata.primary_title == "Second"
    epub.seek(0)
    with pytest.raises(ContainerError):
        open_epub(epub, rootfile="not-declared.opf")


def make_nonconforming_metadata_epub() -> io.BytesIO:
    bio = io.BytesIO()
    container = '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf"/></rootfiles></container>'
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="2.0" xmlns:fake="urn:fake">
      <metadata><fake:title>Recovered title</fake:title></metadata>
      <manifest><item id="c" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
      <spine><itemref idref="c"/></spine></package>'''
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("EPUB/package.opf", opf)
        zf.writestr("EPUB/chapter.xhtml", "<html/>")
    bio.seek(0)
    return bio


def test_compatibility_mode_recovers_non_dc_metadata_without_changing_security():
    epub = make_nonconforming_metadata_epub()
    with open_epub(epub, mode=ParsingMode.NORMAL) as book:
        assert book.metadata.primary_title is None
    epub.seek(0)
    with open_epub(epub, mode="compatibility") as book:
        assert book.mode is ParsingMode.COMPATIBILITY
        assert book.metadata.primary_title == "Recovered title"
        assert any(issue.code == "EPUB_COMPAT_DC_NAMESPACE" for issue in book.diagnostics)


def test_strict_mode_rejects_validation_errors_and_exposes_issues():
    epub = make_nonconforming_metadata_epub()
    with pytest.raises(ValidationError) as excinfo:
        open_epub(epub, mode="strict")
    assert excinfo.value.issues
    assert any(issue.code == "EPUB_METADATA_TITLE_MISSING" for issue in excinfo.value.issues)


def test_unknown_mode_is_rejected_before_interpretation():
    with pytest.raises(ValueError):
        open_epub(make_multi_rootfile_epub(), mode="anything-goes")
