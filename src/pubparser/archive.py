from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterator
from zipfile import BadZipFile, ZipFile, ZipInfo

from .errors import InvalidArchiveError, ResourceError, UnsafeArchiveError
from .security import DEFAULT_LIMITS, SecurityLimits


def normalize_archive_path(name: str) -> str:
    if not name or "\\" in name:
        if "\\" in name:
            raise UnsafeArchiveError(f"archive path uses backslashes: {name!r}")
        raise UnsafeArchiveError("archive path is empty")
    path = PurePosixPath(name)
    if path.is_absolute():
        raise UnsafeArchiveError(f"absolute archive path: {name!r}")
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise UnsafeArchiveError(f"archive path escapes root: {name!r}")
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise UnsafeArchiveError(f"archive path resolves to root: {name!r}")
    return "/".join(parts)


class EpubArchive:
    """Security-checked, lazy access to the EPUB ZIP container."""

    def __init__(self, source: str | Path | BinaryIO, *, limits: SecurityLimits = DEFAULT_LIMITS):
        self._source = source
        self.limits = limits
        self._zip: ZipFile | None = None
        self._entries: dict[str, ZipInfo] = {}

    def __enter__(self) -> "EpubArchive":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def open(self) -> "EpubArchive":
        if self._zip is not None:
            return self
        try:
            archive = ZipFile(self._source, "r")
            infos = archive.infolist()
        except (BadZipFile, OSError) as exc:
            raise InvalidArchiveError(str(exc)) from exc
        try:
            self._entries = self._validate_entries(infos)
        except Exception:
            archive.close()
            raise
        self._zip = archive
        return self

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None
        self._entries = {}

    @property
    def names(self) -> tuple[str, ...]:
        self._require_open()
        return tuple(self._entries)

    def exists(self, path: str) -> bool:
        self._require_open()
        try:
            path = normalize_archive_path(path)
        except UnsafeArchiveError:
            return False
        return path in self._entries

    def info(self, path: str) -> ZipInfo:
        self._require_open()
        normalized = normalize_archive_path(path)
        try:
            return self._entries[normalized]
        except KeyError as exc:
            raise ResourceError(f"resource not found: {normalized}") from exc

    @contextmanager
    def open_resource(self, path: str) -> Iterator[BinaryIO]:
        self._require_open()
        normalized = normalize_archive_path(path)
        info = self.info(normalized)
        if info.file_size > self.limits.max_resource_size:
            raise UnsafeArchiveError(f"resource exceeds size limit: {normalized}")
        assert self._zip is not None
        with self._zip.open(info, "r") as stream:
            yield stream

    def read_bytes(self, path: str, *, max_size: int | None = None) -> bytes:
        info = self.info(path)
        effective_limit = self.limits.max_resource_size if max_size is None else min(max_size, self.limits.max_resource_size)
        if info.file_size > effective_limit:
            raise UnsafeArchiveError(f"resource exceeds size limit: {path}")
        with self.open_resource(path) as stream:
            data = stream.read(effective_limit + 1)
        if len(data) > effective_limit:
            raise UnsafeArchiveError(f"resource expanded beyond size limit: {path}")
        return data

    def _require_open(self) -> None:
        if self._zip is None:
            raise RuntimeError("archive is not open")

    def _validate_entries(self, infos: list[ZipInfo]) -> dict[str, ZipInfo]:
        if len(infos) > self.limits.max_entries:
            raise UnsafeArchiveError("archive entry count exceeds limit")
        entries: dict[str, ZipInfo] = {}
        total = 0
        for info in infos:
            if info.is_dir():
                continue
            normalized = normalize_archive_path(info.filename)
            if normalized in entries:
                raise UnsafeArchiveError(f"duplicate archive path after normalization: {normalized}")
            if info.file_size < 0 or info.compress_size < 0:
                raise UnsafeArchiveError(f"invalid ZIP size metadata: {normalized}")
            if info.file_size > self.limits.max_resource_size:
                raise UnsafeArchiveError(f"resource exceeds size limit: {normalized}")
            total += info.file_size
            if total > self.limits.max_total_uncompressed_size:
                raise UnsafeArchiveError("archive expanded size exceeds limit")
            if info.file_size:
                if info.compress_size == 0:
                    raise UnsafeArchiveError(f"non-empty resource has zero compressed size: {normalized}")
                ratio = info.file_size / info.compress_size
                if ratio > self.limits.max_expansion_ratio:
                    raise UnsafeArchiveError(f"resource expansion ratio exceeds limit: {normalized}")
            entries[normalized] = info
        return entries
