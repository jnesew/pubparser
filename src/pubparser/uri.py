from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from urllib.parse import unquote, urlsplit

from .archive import normalize_archive_path
from .errors import ResourceError, UnsafeArchiveError

_BAD_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    kind: str
    path: str | None
    fragment: str | None
    original: str


def _decode_component(value: str, *, href: str) -> str:
    if _BAD_PERCENT.search(value):
        raise ResourceError(f"malformed percent escape in EPUB URI: {href!r}")
    try:
        return unquote(value, errors="strict")
    except UnicodeDecodeError as exc:
        raise ResourceError(f"invalid UTF-8 percent escape in EPUB URI: {href!r}") from exc


def resolve_reference(base_path: str, href: str) -> ResolvedReference:
    if "\x00" in href:
        raise ResourceError("EPUB URI contains NUL")
    parts = urlsplit(href)
    fragment = _decode_component(parts.fragment, href=href) if parts.fragment else None
    if parts.scheme or parts.netloc:
        return ResolvedReference("remote", None, fragment, href)
    if not parts.path:
        return ResolvedReference("fragment", normalize_archive_path(base_path), fragment, href)
    decoded = _decode_component(parts.path, href=href)
    if decoded.startswith("/"):
        raise ResourceError(f"absolute EPUB-local URI is invalid: {href!r}")
    joined = str(PurePosixPath(base_path).parent / decoded)
    try:
        normalized = normalize_archive_path(joined)
    except UnsafeArchiveError as exc:
        raise ResourceError(f"reference escapes EPUB root: {href!r}") from exc
    return ResolvedReference("internal", normalized, fragment, href)
