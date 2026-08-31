from __future__ import annotations

import io
import zipfile

import pytest

from pubparser import UnsafeArchiveError, open_epub
from pubparser.archive import EpubArchive, normalize_archive_path


def make_custom_epub(opf: str, resources: dict[str, str | bytes]) -> io.BytesIO:
    bio = io.BytesIO()
    container_xml = '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf"/></rootfiles></container>'
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("EPUB/package.opf", opf)
        for path, content in resources.items():
            zf.writestr(f"EPUB/{path}", content)
    bio.seek(0)
    return bio


def test_resource_collection_supports_lazy_bytes_text_and_filters():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Resources</dc:title></metadata>
 <manifest>
  <item id="chap" href="chapter.xhtml" media-type="application/xhtml+xml" properties="scripted"/>
  <item id="css" href="style.css" media-type="text/css"/>
 </manifest><spine><itemref idref="chap"/></spine></package>'''
    xhtml = '<?xml version="1.0" encoding="iso-8859-1"?><html xmlns="http://www.w3.org/1999/xhtml"><body>caf\xe9</body></html>'.encode("latin-1")
    bio = io.BytesIO()
    container_xml = '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf"/></rootfiles></container>'
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("EPUB/package.opf", opf)
        zf.writestr("EPUB/chapter.xhtml", xhtml)
        zf.writestr("EPUB/style.css", 'body { font-family: serif; }')
    bio.seek(0)
    with open_epub(bio) as book:
        assert len(book.resources) == 2
        assert book.resources["chap"].read_text().endswith('</html>')
        assert "café" in book.resources["chap"].read_text()
        assert book.resources.by_path("EPUB/style.css").id == "css"
        assert [r.id for r in book.resources.by_media_type("text/css")] == ["css"]
        assert [r.id for r in book.resources.with_property("scripted")] == ["chap"]
        with book.resources["css"].open() as stream:
            assert b"font-family" in stream.read()


def test_remote_resource_is_visible_but_never_fetched():
    from pubparser.errors import ResourceError

    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Remote</dc:title></metadata>
 <manifest><item id="remote" href="https://example.invalid/a.css" media-type="text/css"/><item id="chap" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
 <spine><itemref idref="chap"/></spine></package>'''
    with open_epub(make_custom_epub(opf, {"chapter.xhtml": "<html/>"})) as book:
        resource = book.resources["remote"]
        assert resource.is_remote
        assert not resource.exists
        with pytest.raises(ResourceError):
            resource.read_bytes()


def test_metadata_requires_actual_dublin_core_namespace():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="2.0" xmlns:fake="urn:fake" xmlns:dc="http://purl.org/dc/elements/1.1/">
 <metadata><fake:title>Wrong</fake:title><dc:title>Right</dc:title></metadata>
 <manifest><item id="chap" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
 <spine><itemref idref="chap"/></spine></package>'''
    with open_epub(make_custom_epub(opf, {"chapter.xhtml": "<html/>"})) as book:
        assert book.metadata.all("title") == ("Right",)


def test_archive_rejects_drive_qualified_and_unsafe_directory_paths():
    with pytest.raises(UnsafeArchiveError):
        normalize_archive_path("C:/outside.txt")

    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        info = zipfile.ZipInfo("../unsafe/")
        info.external_attr = 0o40775 << 16
        zf.writestr(info, b"")
    bio.seek(0)
    with pytest.raises(UnsafeArchiveError):
        EpubArchive(bio).open()
