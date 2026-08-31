from __future__ import annotations

import re

from .errors import ResourceError
from .models import ContentBlock, ExtractedDocument, ManifestItem
from .xmlutil import local_name, parse_xml_safely

_WS = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n\s*\n+")
_SKIP = {"script", "style", "noscript", "template"}
_HTML5_DOCTYPE = re.compile(br"<!\s*DOCTYPE\s+html\s*>", re.IGNORECASE)
_BLOCK = {
    "address", "article", "aside", "blockquote", "dd", "div", "dl", "dt", "figcaption",
    "figure", "footer", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}


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
            is_block = child_tag in _BLOCK or child_tag.startswith("h") and len(child_tag) == 2 and child_tag[1].isdigit()
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
        if len(tag) == 2 and tag[0] == "h" and tag[1] in "123456":
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


def extract_xhtml(data: bytes, resource: ManifestItem, *, structured: bool = True, max_depth: int = 256) -> ExtractedDocument:
    try:
        # EPUB XHTML commonly carries the inert HTML5 doctype. Strip only that
        # exact declaration; internal subsets and other DTD forms remain rejected.
        safe_data = _HTML5_DOCTYPE.sub(b"", data)
        root = parse_xml_safely(safe_data, resource=resource.resolved_path, max_depth=max_depth)
    except Exception as exc:
        raise ResourceError(f"cannot extract XHTML text from {resource.resolved_path}: {exc}") from exc
    text = _plain_from_tree(root)
    blocks = _structured_blocks(root) if structured else ()
    return ExtractedDocument(resource=resource, text=text, blocks=blocks)
