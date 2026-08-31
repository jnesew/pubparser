from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from .archive import EpubArchive
from .container import Container, parse_container
from .diagnostics import Diagnostic
from .models import Package
from .package import parse_package
from .security import DEFAULT_LIMITS, SecurityLimits


class EpubBook:
    def __init__(self, archive: EpubArchive, container: Container, package: Package, diagnostics: tuple[Diagnostic, ...]):
        self._archive = archive
        self.container = container
        self.package = package
        self.diagnostics = diagnostics

    def __enter__(self) -> "EpubBook":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def metadata(self):
        return self.package.metadata

    @property
    def manifest(self):
        return self.package.manifest

    @property
    def spine(self):
        return self.package.spine

    def read_resource(self, manifest_id: str) -> bytes:
        item = self.package.manifest_by_id(manifest_id)
        if item is None:
            raise KeyError(manifest_id)
        return self._archive.read_bytes(item.resolved_path)

    def close(self) -> None:
        self._archive.close()


def open_epub(source: str | Path | BinaryIO, *, limits: SecurityLimits = DEFAULT_LIMITS) -> EpubBook:
    archive = EpubArchive(source, limits=limits).open()
    try:
        container = parse_container(archive)
        package, diagnostics = parse_package(archive, container.default_rootfile.full_path)
        return EpubBook(archive, container, package, diagnostics)
    except Exception:
        archive.close()
        raise
