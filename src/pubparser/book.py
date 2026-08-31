from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from .archive import EpubArchive
from .container import Container, parse_container
from .content import extract_xhtml
from .diagnostics import Diagnostic
from .encryption import parse_encryption
from .models import Cover, EncryptionInfo, ExtractedDocument, Navigation, NormalizationResult, Package
from .navigation import parse_navigation
from .package import parse_package
from .security import DEFAULT_LIMITS, SecurityLimits
from .semantics import detect_cover
from .validation import validate_book


class EpubBook:
    def __init__(
        self,
        archive: EpubArchive,
        container: Container,
        package: Package,
        navigation: Navigation | None,
        encryption: EncryptionInfo,
        cover: Cover | None,
        diagnostics: tuple[Diagnostic, ...],
    ):
        self._archive = archive
        self.container = container
        self.package = package
        self.navigation = navigation
        self.encryption = encryption
        self.cover = cover
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

    def extract_document(self, manifest_id: str, *, structured: bool = True) -> ExtractedDocument:
        item = self.package.manifest_by_id(manifest_id)
        if item is None:
            raise KeyError(manifest_id)
        if item.media_type not in {"application/xhtml+xml", "text/html"}:
            raise ValueError(f"resource {manifest_id!r} is not an XHTML/HTML document")
        return extract_xhtml(self._archive.read_bytes(item.resolved_path), item, structured=structured, max_depth=self._archive.limits.max_xml_depth)

    def iter_text(self, *, linear_only: bool = True, structured: bool = True, normalization: NormalizationResult | None = None):
        spine = self.package.linear_spine if linear_only else self.package.spine
        for spine_item in spine:
            resource = spine_item.resource
            if resource is None or resource.media_type not in {"application/xhtml+xml", "text/html"}:
                continue
            document = self.extract_document(resource.id, structured=structured)
            if normalization is not None:
                cleaned = normalization.apply(resource.id, document.text)
                document = ExtractedDocument(resource=document.resource, text=cleaned, blocks=document.blocks)
            yield document

    def extract_text(self, *, linear_only: bool = True, structured: bool = True, normalization: NormalizationResult | None = None) -> tuple[ExtractedDocument, ...]:
        return tuple(self.iter_text(linear_only=linear_only, structured=structured, normalization=normalization))

    def validate(self, *, include_parse_diagnostics: bool = True) -> tuple[Diagnostic, ...]:
        return validate_book(self, include_parse_diagnostics=include_parse_diagnostics)

    def close(self) -> None:
        self._archive.close()


def open_epub(source: str | Path | BinaryIO, *, limits: SecurityLimits = DEFAULT_LIMITS) -> EpubBook:
    archive = EpubArchive(source, limits=limits).open()
    try:
        container = parse_container(archive)
        package, package_diagnostics = parse_package(archive, container.default_rootfile.full_path)
        encryption, encryption_diagnostics = parse_encryption(archive)
        navigation, navigation_diagnostics = parse_navigation(archive, package)
        cover, cover_diagnostics = detect_cover(package)
        diagnostics = package_diagnostics + encryption_diagnostics + navigation_diagnostics + cover_diagnostics
        return EpubBook(archive, container, package, navigation, encryption, cover, diagnostics)
    except Exception:
        archive.close()
        raise
