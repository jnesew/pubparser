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


def parse_xml_safely(data: bytes, *, resource: str = "XML document") -> ET.Element:
    if _FORBIDDEN_XML.search(data):
        raise EpubError(f"unsafe XML declaration in {resource}")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise EpubError(f"malformed XML in {resource}: {exc}") from exc
