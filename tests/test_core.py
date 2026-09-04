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


def make_custom_epub(opf: str, resources: dict[str, str]) -> io.BytesIO:
    bio = io.BytesIO()
    container_xml = '''<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>'''
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("EPUB/package.opf", opf)
        for path, text in resources.items():
            zf.writestr(f"EPUB/{path}", text)
    bio.seek(0)
    return bio


def test_epub3_navigation_normalizes_toc_landmarks_page_list_and_nesting():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Nav</dc:title></metadata>
 <manifest>
  <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  <item id="one" href="one.xhtml" media-type="application/xhtml+xml"/>
  <item id="two" href="two.xhtml" media-type="application/xhtml+xml"/>
 </manifest>
 <spine page-progression-direction="rtl"><itemref idref="one"/><itemref idref="two"/></spine>
</package>'''
    nav = '''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
 <nav epub:type="toc"><ol>
  <li><a href="one.xhtml#start">One</a><ol><li><a href="one.xhtml#sub">Sub section</a></li></ol></li>
  <li><a href="two.xhtml">Two</a></li>
 </ol></nav>
 <nav epub:type="landmarks"><ol><li><a epub:type="bodymatter" href="one.xhtml">Start</a></li></ol></nav>
 <nav epub:type="page-list"><ol><li><a href="two.xhtml#p2">2</a></li></ol></nav>
 </body></html>'''
    with open_epub(make_custom_epub(opf, {"nav.xhtml": nav, "one.xhtml": "<html/>", "two.xhtml": "<html/>"})) as book:
        assert book.navigation is not None
        assert book.navigation.source == "epub3-nav"
        assert [e.label for e in book.navigation.toc] == ["One", "Two"]
        assert book.navigation.toc[0].path == "EPUB/one.xhtml"
        assert book.navigation.toc[0].fragment == "start"
        assert book.navigation.toc[0].children[0].label == "Sub section"
        assert book.navigation.landmarks[0].label == "Start"
        assert book.navigation.page_list[0].fragment == "p2"
        assert book.package.page_progression_direction == "rtl"


def test_epub2_ncx_is_navigation_fallback_and_navlist_is_retained():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>NCX</dc:title></metadata>
 <manifest>
  <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  <item id="chap" href="chapter.xhtml" media-type="application/xhtml+xml"/>
 </manifest>
 <spine toc="ncx"><itemref idref="chap"/></spine>
</package>'''
    ncx = '''<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">
 <navMap><navPoint id="a"><navLabel><text>Chapter</text></navLabel><content src="chapter.xhtml#c"/>
   <navPoint id="b"><navLabel><text>Nested</text></navLabel><content src="chapter.xhtml#n"/></navPoint>
 </navPoint></navMap>
 <pageList><pageTarget><navLabel><text>1</text></navLabel><content src="chapter.xhtml#p1"/></pageTarget></pageList>
 <navList><navLabel><text>Figures</text></navLabel><navTarget><navLabel><text>Fig 1</text></navLabel><content src="chapter.xhtml#f1"/></navTarget></navList>
</ncx>'''
    with open_epub(make_custom_epub(opf, {"toc.ncx": ncx, "chapter.xhtml": "<html/>"})) as book:
        assert book.navigation is not None
        assert book.navigation.source == "epub2-ncx"
        assert book.navigation.toc[0].label == "Chapter"
        assert book.navigation.toc[0].children[0].label == "Nested"
        assert book.navigation.page_list[0].label == "1"
        assert book.navigation.lists[0].label == "Figures"
        assert book.navigation.lists[0].entries[0].fragment == "f1"


def test_cover_detection_prefers_epub3_property_and_exposes_rendition_metadata():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>Fixed</dc:title>
  <meta property="rendition:layout">pre-paginated</meta>
  <meta property="rendition:orientation">landscape</meta>
  <meta property="rendition:spread">both</meta>
  <meta property="rendition:flow">paginated</meta>
 </metadata>
 <manifest>
  <item id="cover" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/>
  <item id="chap" href="chapter.xhtml" media-type="application/xhtml+xml"/>
 </manifest>
 <spine><itemref idref="chap"/></spine>
</package>'''
    with open_epub(make_custom_epub(opf, {"cover.jpg": "jpeg", "chapter.xhtml": "<html/>"})) as book:
        assert book.cover is not None
        assert book.cover.resource.id == "cover"
        assert book.cover.method == "epub3-cover-image"
        assert book.package.rendition.is_fixed_layout
        assert book.package.rendition.orientation == "landscape"
        assert book.package.rendition.spread == "both"
        assert book.package.rendition.flow == "paginated"


def test_epub2_legacy_cover_metadata_fallback():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>Legacy cover</dc:title><meta name="cover" content="img"/>
 </metadata>
 <manifest>
  <item id="img" href="cover.jpg" media-type="image/jpeg"/>
  <item id="chap" href="chapter.xhtml" media-type="application/xhtml+xml"/>
 </manifest>
 <spine><itemref idref="chap"/></spine>
</package>'''
    with open_epub(make_custom_epub(opf, {"cover.jpg": "jpeg", "chapter.xhtml": "<html/>"})) as book:
        assert book.cover is not None
        assert book.cover.resource.id == "img"
        assert book.cover.method == "epub2-meta-cover"


def test_malformed_navigation_is_diagnostic_not_fatal():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Broken nav</dc:title></metadata>
 <manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="chap" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
 <spine><itemref idref="chap"/></spine>
</package>'''
    with open_epub(make_custom_epub(opf, {"nav.xhtml": "<html><nav>", "chapter.xhtml": "<html/>"})) as book:
        assert book.navigation is None
        assert any(d.code == "EPUB_MALFORMED_NAVIGATION" for d in book.diagnostics)


def test_text_extraction_skips_script_style_and_preserves_blocks():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Text</dc:title></metadata>
 <manifest><item id="chap" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
 <spine><itemref idref="chap"/></spine></package>'''
    xhtml = '''<html xmlns="http://www.w3.org/1999/xhtml"><head><style>SECRET CSS</style><script>SECRET JS</script></head><body>
      <h1>Chapter One</h1><p>Hello <em>world</em>.</p><ul><li>First</li><li>Second</li></ul><blockquote>Quoted words</blockquote>
    </body></html>'''
    with open_epub(make_custom_epub(opf, {"chapter.xhtml": xhtml})) as book:
        doc = book.extract_document("chap")
        assert "SECRET" not in doc.text
        assert "Chapter One" in doc.text
        assert "Hello world." in doc.text
        assert any(block.kind == "heading" and block.text == "Chapter One" for block in doc.blocks)
        assert any(block.kind == "paragraph" and block.text == "Hello world." for block in doc.blocks)
        assert [block.text for block in doc.blocks if block.kind == "list-item"] == ["First", "Second"]


def test_iter_text_uses_linear_reading_order_and_skips_non_documents():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Order</dc:title></metadata>
 <manifest>
  <item id="a" href="a.xhtml" media-type="application/xhtml+xml"/>
  <item id="img" href="x.jpg" media-type="image/jpeg"/>
  <item id="b" href="b.xhtml" media-type="application/xhtml+xml"/>
 </manifest>
 <spine><itemref idref="a"/><itemref idref="img"/><itemref idref="b" linear="no"/></spine></package>'''
    with open_epub(make_custom_epub(opf, {"a.xhtml": "<html><body><p>A</p></body></html>", "x.jpg": "x", "b.xhtml": "<html><body><p>B</p></body></html>"})) as book:
        assert [doc.text for doc in book.iter_text()] == ["A"]
        assert [doc.text for doc in book.iter_text(linear_only=False)] == ["A", "B"]


def test_toc_document_semantics_use_manifest_and_xhtml_evidence():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>TOC</dc:title></metadata>
 <manifest>
  <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
 </manifest>
 <spine><itemref idref="nav"/><itemref idref="chapter"/></spine></package>'''
    nav = '''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body>
      <nav epub:type="toc"><h1>Contents</h1><ol><li><a href="chapter.xhtml">Chapter</a></li></ol></nav>
    </body></html>'''
    chapter = "<html xmlns='http://www.w3.org/1999/xhtml'><body><h1>Chapter</h1><p>Story text.</p></body></html>"
    with open_epub(make_custom_epub(opf, {"nav.xhtml": nav, "chapter.xhtml": chapter})) as book:
        documents = tuple(book.iter_documents())
        toc = documents[0].semantic("toc")
        assert toc is not None
        assert toc.confidence == 1.0
        assert set(toc.evidence) == {
            "xhtml-semantic-marker",
            "manifest-nav-property",
            "navigation-source",
        }
        assert not documents[1].has_semantic("toc")


def test_toc_document_semantics_use_epub2_guide_reference():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>TOC</dc:title></metadata>
 <manifest><item id="contents" href="contents.xhtml" media-type="application/xhtml+xml"/></manifest>
 <spine><itemref idref="contents"/></spine>
 <guide><reference type="toc" title="Contents" href="contents.xhtml"/></guide></package>'''
    contents = "<html xmlns='http://www.w3.org/1999/xhtml'><body><h1>Contents</h1></body></html>"
    with open_epub(make_custom_epub(opf, {"contents.xhtml": contents})) as book:
        document = next(book.iter_documents())
        assert document.has_semantic("toc", minimum_confidence=0.9)
        assert "package-guide-reference" in document.semantic("toc").evidence


def test_toc_heuristic_is_high_confidence_only_with_title_and_link_list():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>TOC</dc:title></metadata>
 <manifest><item id="contents" href="contents.xhtml" media-type="application/xhtml+xml"/></manifest>
 <spine><itemref idref="contents"/></spine></package>'''
    contents = '''<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Contents</h1><ol>
      <li><a href="one.xhtml">Chapter One</a></li>
      <li><a href="two.xhtml">Chapter Two</a></li>
      <li><a href="three.xhtml">Chapter Three</a></li>
    </ol></body></html>'''
    with open_epub(make_custom_epub(opf, {"contents.xhtml": contents})) as book:
        document = next(book.iter_documents())
        assert document.has_semantic("toc", minimum_confidence=0.9)
        assert document.semantic("toc").evidence == ("toc-title", "link-list-pattern")


def test_toc_title_without_structural_evidence_remains_low_confidence():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>TOC</dc:title></metadata>
 <manifest><item id="contents" href="contents.xhtml" media-type="application/xhtml+xml"/></manifest>
 <spine><itemref idref="contents"/></spine></package>'''
    contents = "<html xmlns='http://www.w3.org/1999/xhtml'><body><h1>Contents</h1><p>A reflective essay.</p></body></html>"
    with open_epub(make_custom_epub(opf, {"contents.xhtml": contents})) as book:
        document = next(book.iter_documents())
        assert document.has_semantic("toc", minimum_confidence=0.65)
        assert not document.has_semantic("toc", minimum_confidence=0.9)


def test_validation_reports_missing_resource_and_required_metadata():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Validation</dc:title></metadata>
 <manifest><item id="chap" href="missing.xhtml" media-type="application/xhtml+xml"/></manifest>
 <spine><itemref idref="chap"/></spine></package>'''
    with open_epub(make_custom_epub(opf, {})) as book:
        codes = {issue.code for issue in book.validate()}
        assert "EPUB_METADATA_IDENTIFIER_MISSING" in codes
        assert "EPUB_METADATA_LANGUAGE_MISSING" in codes
        assert "EPUB_MANIFEST_RESOURCE_MISSING" in codes
        assert "EPUB_MODIFIED_MISSING" in codes


def test_validation_detects_fallback_cycle():
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>X</dc:title><dc:identifier>id</dc:identifier><dc:language>en</dc:language></metadata>
 <manifest>
  <item id="a" href="a.bin" media-type="application/x-a" fallback="b"/>
  <item id="b" href="b.bin" media-type="application/x-b" fallback="a"/>
  <item id="chap" href="chapter.xhtml" media-type="application/xhtml+xml"/>
 </manifest><spine><itemref idref="chap"/></spine></package>'''
    with open_epub(make_custom_epub(opf, {"a.bin": "a", "b.bin": "b", "chapter.xhtml": "<html/>"})) as book:
        assert any(issue.code == "EPUB_FALLBACK_CYCLE" for issue in book.validate())


def make_epub_with_encryption(encryption_xml: str, *, algorithm_resource: str = "EPUB/font.otf") -> io.BytesIO:
    opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Encrypted</dc:title><dc:identifier>id</dc:identifier><dc:language>en</dc:language></metadata>
 <manifest><item id="chap" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="font" href="font.otf" media-type="application/vnd.ms-opentype"/></manifest>
 <spine><itemref idref="chap"/></spine></package>'''
    bio = io.BytesIO()
    container_xml = '''<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'''
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("META-INF/encryption.xml", encryption_xml)
        zf.writestr("EPUB/package.opf", opf)
        zf.writestr("EPUB/chapter.xhtml", "<html/>")
        zf.writestr(algorithm_resource, "font")
    bio.seek(0)
    return bio


def test_font_obfuscation_is_identified_without_treating_it_as_drm():
    encryption = '''<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
 <enc:EncryptedData><enc:EncryptionMethod Algorithm="http://www.idpf.org/2008/embedding"/><enc:CipherData><enc:CipherReference URI="EPUB/font.otf"/></enc:CipherData></enc:EncryptedData>
</encryption>'''
    with open_epub(make_epub_with_encryption(encryption)) as book:
        assert len(book.encryption.resources) == 1
        assert book.encryption.resources[0].kind == "font-obfuscation-idpf"
        assert book.encryption.resources[0].resolved_path == "EPUB/font.otf"
        assert not book.encryption.has_unsupported_drm
        assert not any(d.code == "EPUB_UNSUPPORTED_ENCRYPTION" for d in book.diagnostics)


def test_unknown_encryption_is_reported_but_does_not_block_structural_parsing():
    encryption = '''<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
 <enc:EncryptedData><enc:EncryptionMethod Algorithm="urn:example:drm"/><enc:CipherData><enc:CipherReference URI="EPUB/font.otf"/></enc:CipherData></enc:EncryptedData>
</encryption>'''
    with open_epub(make_epub_with_encryption(encryption)) as book:
        assert book.metadata.primary_title == "Encrypted"
        assert book.encryption.has_unsupported_drm
        assert any(d.code == "EPUB_UNSUPPORTED_ENCRYPTION" for d in book.diagnostics)


def test_uri_rejects_malformed_percent_escape_and_encoded_escape():
    from pubparser.errors import ResourceError
    from pubparser.uri import resolve_reference

    with pytest.raises(ResourceError):
        resolve_reference("EPUB/package.opf", "chapter%ZZ.xhtml")
    with pytest.raises(ResourceError):
        resolve_reference("EPUB/package.opf", "%2e%2e/%2e%2e/outside.xhtml")


def test_xml_nesting_depth_limit_is_enforced():
    nested = "<x>" * 10 + "</x>" * 10
    container = f'''<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf"/></rootfiles>{nested}</container>'''
    limits = SecurityLimits(max_xml_depth=8)
    with pytest.raises(ContainerError):
        open_epub(make_epub(container_xml=container), limits=limits)
