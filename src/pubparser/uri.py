from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from .archive import normalize_archive_path
from .errors import ResourceError, UnsafeArchiveError


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    kind: str
    path: str | None
    fragment: str | None
    original: str


def resolve_reference(base_path: str, href: str) -> ResolvedReference:
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        return ResolvedReference("remote", None, parts.fragment or None, href)
    if not parts.path:
        return ResolvedReference("fragment", normalize_archive_path(base_path), parts.fragment or None, href)
    decoded = unquote(parts.path)
    if decoded.startswith("/"):
        raise ResourceError(f"absolute EPUB-local URI is invalid: {href!r}")
    joined = str(PurePosixPath(base_path).parent / decoded)
    try:
        normalized = normalize_archive_path(joined)
    except UnsafeArchiveError as exc:
        raise ResourceError(f"reference escapes EPUB root: {href!r}") from exc
    return ResolvedReference("internal", normalized, parts.fragment or None, href)
