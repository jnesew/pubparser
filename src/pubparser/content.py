from __future__ import annotations

import codecs
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from .errors import ResourceError
from .modes import ParsingMode, coerce_parsing_mode
from .models import ContentBlock, ExtractedDocument, ManifestItem
from .xmlutil import local_name, parse_xml_safely

_WS = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n\s*\n+")
_SKIP = {"script", "style", "noscript", "template"}
_HTML5_DOCTYPE = re.compile(br"<!\s*DOCTYPE\s+html\s*>", re.IGNORECASE)
_W3C_XHTML_DOCTYPE = re.compile(
    br"""<!\s*DOCTYPE\s+html\s+PUBLIC\s+
    ['\"]-//W3C//DTD\s+XHTML\s+(?:1\.0\s+(?:Strict|Transitional|Frameset)|1\.1)//EN['\"]\s+
    ['\"]https?://www\.w3\.org/TR/xhtml(?:1/DTD/xhtml1-(?:strict|transitional|frameset)\.dtd|11/DTD/xhtml11\.dtd)['\"]\s*>""",
    re.IGNORECASE | re.VERBOSE,
)
_UNSAFE_COMPAT_DECL = re.compile(br"<!\s*(?:DOCTYPE|ENTITY|ELEMENT|ATTLIST|NOTATION)\b", re.IGNORECASE)
_XML_ENCODING = re.compile(br"<\?xml\s+[^>]*encoding\s*=\s*['\"]\s*([A-Za-z0-9._:-]+)\s*['\"]", re.IGNORECASE)
_BLOCK = {
    "address", "article", "aside", "blockquote", "dd", "div", "dl", "dt", "figcaption",
    "figure", "footer", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_HEADING = {f"h{level}" for level in range(1, 7)}


def _strip_safe_content_doctype(data: bytes) -> bytes:
    """Remove only the inert HTML5 and canonical W3C XHTML doctypes.

    ElementTree does not need these declarations. Restricting the accepted
    external identifiers keeps entity definitions, internal subsets, and
    arbitrary external system identifiers on the existing rejection path.
    """
    return _W3C_XHTML_DOCTYPE.sub(b"", _HTML5_DOCTYPE.sub(b"", data))


def _visible_text(elem) -> str:
    if local_name(elem.tag).lower() in _SKIP:
        return ""
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        if local_name(child.tag).lower() not in _SKIP:
            parts.append(_visible_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _normalize_inline(value: str) -> str:
    return _WS.sub(" ", value.replace("\u00a0", " ")).strip()


def _plain_from_tree(root) -> str:
    body = next((elem for elem in root.iter() if local_name(elem.tag).lower() == "body"), root)
    chunks: list[str] = []

    def walk(elem) -> None:
        tag = local_name(elem.tag).lower()
        if tag in _SKIP:
            return
        if elem.text:
            chunks.append(elem.text)
        for child in elem:
            child_tag = local_name(child.tag).lower()
            is_block = child_tag in _BLOCK or child_tag in _HEADING
            if is_block and chunks and not chunks[-1].endswith("\n"):
                chunks.append("\n")
            walk(child)
            if is_block:
                chunks.append("\n")
            if child.tail:
                chunks.append(child.tail)

    walk(body)
    lines = [_normalize_inline(line) for line in "".join(chunks).splitlines()]
    text = "\n".join(line for line in lines if line)
    return _BLANKS.sub("\n", text).strip()


def _structured_blocks(root) -> tuple[ContentBlock, ...]:
    body = next((elem for elem in root.iter() if local_name(elem.tag).lower() == "body"), root)
    blocks: list[ContentBlock] = []
    for elem in body.iter():
        tag = local_name(elem.tag).lower()
        if tag in _SKIP:
            continue
        text = _normalize_inline(_visible_text(elem))
        if not text:
            continue
        if tag in _HEADING:
            blocks.append(ContentBlock("heading", text, int(tag[1])))
        elif tag == "p":
            blocks.append(ContentBlock("paragraph", text))
        elif tag == "li":
            blocks.append(ContentBlock("list-item", text))
        elif tag == "blockquote":
            blocks.append(ContentBlock("blockquote", text))
        elif tag == "table":
            blocks.append(ContentBlock("table", text))
    return tuple(blocks)


def _document_title(root, resource: ManifestItem) -> tuple[str, str]:
    body = next((elem for elem in root.iter() if local_name(elem.tag).lower() == "body"), root)
    for preferred in ("h1", "h2"):
        for elem in body.iter():
            if local_name(elem.tag).lower() != preferred:
                continue
            text = _normalize_inline(_visible_text(elem))
            if text:
                return text, preferred
    for elem in root.iter():
        if local_name(elem.tag).lower() != "title":
            continue
        text = _normalize_inline(_visible_text(elem))
        if text:
            return text, "title"
    return resource.id, "resource-id"


def _decode_compat_markup(data: bytes, resource: ManifestItem) -> str:
    if data.startswith(codecs.BOM_UTF8):
        encoding = "utf-8-sig"
    elif data.startswith(codecs.BOM_UTF32_LE) or data.startswith(codecs.BOM_UTF32_BE):
        encoding = "utf-32"
    elif data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        encoding = "utf-16"
    else:
        match = _XML_ENCODING.search(data[:512])
        if match:
            try:
                encoding = match.group(1).decode("ascii")
            except UnicodeDecodeError as exc:
                raise ResourceError(f"invalid declared encoding in {resource.resolved_path}") from exc
        else:
            encoding = "utf-8"
    try:
        return data.decode(encoding)
    except (LookupError, UnicodeDecodeError) as exc:
        raise ResourceError(f"cannot decode {resource.resolved_path} using {encoding}: {exc}") from exc


class _CompatTreeBuilder(HTMLParser):
    def __init__(self, *, max_depth: int):
        super().__init__(convert_charrefs=True)
        self.root = ET.Element("html")
        self._stack = [self.root]
        self._max_depth = max_depth

    def _close_open(self, predicate) -> None:
        for index in range(len(self._stack) - 1, 0, -1):
            if predicate(self._stack[index].tag):
                del self._stack[index:]
                return

    def _prepare_start(self, tag: str) -> None:
        if tag in _BLOCK or tag in _HEADING:
            self._close_open(lambda open_tag: open_tag == "p")
        if tag in _BLOCK:
            self._close_open(lambda open_tag: open_tag in _HEADING)
        if tag == "li":
            self._close_open(lambda open_tag: open_tag == "li")
        if tag in _HEADING:
            self._close_open(lambda open_tag: open_tag in _HEADING)

    def _append_text(self, text: str) -> None:
        if not text:
            return
        parent = self._stack[-1]
        if len(parent):
            child = parent[-1]
            child.tail = (child.tail or "") + text
        else:
            parent.text = (parent.text or "") + text

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized = tag.lower()
        self._prepare_start(normalized)
        attributes = {str(key): value or "" for key, value in attrs}
        elem = ET.SubElement(self._stack[-1], normalized, attributes)
        if normalized in _VOID:
            return
        if len(self._stack) >= self._max_depth:
            raise ValueError("HTML nesting depth exceeds limit")
        self._stack.append(elem)

    def handle_startendtag(self, tag: str, attrs) -> None:
        normalized = tag.lower()
        attributes = {str(key): value or "" for key, value in attrs}
        ET.SubElement(self._stack[-1], normalized, attributes)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == normalized:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._append_text(data)

    def handle_decl(self, decl: str) -> None:
        raise ValueError(f"unsupported HTML declaration: {decl}")

    def unknown_decl(self, data: str) -> None:
        raise ValueError(f"unsupported HTML declaration: {data}")


def _parse_compat_html(data: bytes, resource: ManifestItem, *, max_depth: int):
    safe_data = _strip_safe_content_doctype(data)
    if _UNSAFE_COMPAT_DECL.search(safe_data):
        raise ResourceError(f"unsafe markup declaration in {resource.resolved_path}")
    text = _decode_compat_markup(safe_data, resource)
    parser = _CompatTreeBuilder(max_depth=max_depth)
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:
        raise ResourceError(f"cannot recover malformed HTML from {resource.resolved_path}: {exc}") from exc
    return parser.root


def extract_xhtml(
    data: bytes,
    resource: ManifestItem,
    *,
    structured: bool = True,
    max_depth: int = 256,
    mode: ParsingMode | str = ParsingMode.NORMAL,
) -> ExtractedDocument:
    parsing_mode = coerce_parsing_mode(mode)
    safe_data = _strip_safe_content_doctype(data)
    try:
        root = parse_xml_safely(safe_data, resource=resource.resolved_path, max_depth=max_depth)
    except Exception as exc:
        if parsing_mode is not ParsingMode.COMPATIBILITY or _UNSAFE_COMPAT_DECL.search(safe_data):
            raise ResourceError(f"cannot extract XHTML text from {resource.resolved_path}: {exc}") from exc
        root = _parse_compat_html(data, resource, max_depth=max_depth)

    text = _plain_from_tree(root)
    blocks = _structured_blocks(root) if structured else ()
    title, title_source = _document_title(root, resource)
    return ExtractedDocument(
        resource=resource,
        text=text,
        blocks=blocks,
        title=title,
        title_source=title_source,
    )
