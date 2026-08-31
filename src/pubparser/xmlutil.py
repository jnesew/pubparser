from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .errors import EpubError

_FORBIDDEN_XML = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def namespace_uri(tag: str) -> str | None:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return None


def parse_xml_safely(data: bytes, *, resource: str = "XML document", max_depth: int = 256) -> ET.Element:
    if _FORBIDDEN_XML.search(data):
        raise EpubError(f"unsafe XML declaration in {resource}")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise EpubError(f"malformed XML in {resource}: {exc}") from exc

    stack = [(root, 1)]
    while stack:
        elem, depth = stack.pop()
        if depth > max_depth:
            raise EpubError(f"XML nesting depth exceeds limit in {resource}")
        stack.extend((child, depth + 1) for child in elem)
    return root
