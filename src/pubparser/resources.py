from __future__ import annotations

import codecs
import re
from contextlib import contextmanager
from typing import BinaryIO, Iterable, Iterator
from urllib.parse import urlsplit

from .archive import EpubArchive
from .errors import ResourceError
from .models import ManifestItem

_XML_ENCODING = re.compile(br"<\?xml\s+[^>]*encoding\s*=\s*['\"]\s*([A-Za-z0-9._:-]+)\s*['\"]", re.IGNORECASE)
_CSS_CHARSET = re.compile(br'^\s*@charset\s+["\']([^"\']+)["\']\s*;', re.IGNORECASE)


def _detected_encoding(data: bytes) -> str:
    if data.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if data.startswith(codecs.BOM_UTF32_LE) or data.startswith(codecs.BOM_UTF32_BE):
        return "utf-32"
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"
    header = data[:512]
    match = _XML_ENCODING.search(header) or _CSS_CHARSET.search(header)
    if match:
        try:
            return match.group(1).decode("ascii")
        except UnicodeDecodeError:
            pass
    return "utf-8"


class Resource:
    """Lazy handle for one manifest resource.

    A resource is bound to its owning :class:`EpubBook` archive session and is
    therefore only readable until the book is closed. Metadata remains usable
    after close.
    """

    __slots__ = ("_archive", "item")

    def __init__(self, archive: EpubArchive, item: ManifestItem):
        self._archive = archive
        self.item = item

    @property
    def id(self) -> str:
        return self.item.id

    @property
    def href(self) -> str:
        return self.item.href

    @property
    def resolved_path(self) -> str:
        return self.item.resolved_path

    @property
    def media_type(self) -> str:
        return self.item.media_type

    @property
    def properties(self) -> frozenset[str]:
        return self.item.properties

    @property
    def fallback(self) -> str | None:
        return self.item.fallback

    @property
    def media_overlay(self) -> str | None:
        return self.item.media_overlay

    @property
    def is_remote(self) -> bool:
        parts = urlsplit(self.item.href)
        return bool(parts.scheme or parts.netloc)

    @property
    def exists(self) -> bool:
        return False if self.is_remote else self._archive.exists(self.item.resolved_path)

    def _require_local(self) -> None:
        if self.is_remote:
            raise ResourceError(f"remote resource is not fetched automatically: {self.item.href}")

    @contextmanager
    def open(self) -> Iterator[BinaryIO]:
        self._require_local()
        with self._archive.open_resource(self.item.resolved_path) as stream:
            yield stream

    def read_bytes(self, *, max_size: int | None = None) -> bytes:
        self._require_local()
        return self._archive.read_bytes(self.item.resolved_path, max_size=max_size)

    def read_text(self, *, encoding: str | None = None, errors: str = "strict", max_size: int | None = None) -> str:
        data = self.read_bytes(max_size=max_size)
        selected = encoding or _detected_encoding(data)
        try:
            return data.decode(selected, errors=errors)
        except (LookupError, UnicodeDecodeError) as exc:
            raise ResourceError(f"cannot decode {self.item.href} using {selected}: {exc}") from exc

    def __repr__(self) -> str:
        return f"Resource(id={self.id!r}, media_type={self.media_type!r}, href={self.href!r})"


class ResourceCollection:
    """Ordered lazy resource handles for a publication manifest."""

    __slots__ = ("_items", "_by_id", "_by_path")

    def __init__(self, archive: EpubArchive, manifest: Iterable[ManifestItem]):
        items = tuple(Resource(archive, item) for item in manifest)
        self._items = items
        self._by_id = {resource.id: resource for resource in items}
        self._by_path = {
            resource.resolved_path: resource
            for resource in items
            if not resource.is_remote
        }

    def __iter__(self) -> Iterator[Resource]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, key: int | slice | str):
        if isinstance(key, (int, slice)):
            return self._items[key]
        try:
            return self._by_id[key]
        except KeyError as exc:
            raise KeyError(key) from exc

    def by_id(self, item_id: str) -> Resource | None:
        return self._by_id.get(item_id)

    def by_path(self, path: str) -> Resource | None:
        return self._by_path.get(path)

    def by_media_type(self, media_type: str) -> tuple[Resource, ...]:
        return tuple(resource for resource in self._items if resource.media_type == media_type)

    def with_property(self, property_name: str) -> tuple[Resource, ...]:
        return tuple(resource for resource in self._items if property_name in resource.properties)
