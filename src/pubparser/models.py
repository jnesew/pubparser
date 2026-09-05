from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetadataValue:
    name: str
    value: str
    id: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class MetaProperty:
    property: str | None
    value: str
    id: str | None = None
    refines: str | None = None
    scheme: str | None = None
    name: str | None = None
    content: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Metadata:
    values: tuple[MetadataValue, ...] = ()
    meta: tuple[MetaProperty, ...] = ()

    def all(self, name: str) -> tuple[str, ...]:
        return tuple(item.value for item in self.values if item.name == name)

    def first(self, name: str) -> str | None:
        values = self.all(name)
        return values[0] if values else None

    def property_values(self, property_name: str) -> tuple[str, ...]:
        return tuple(item.value for item in self.meta if item.property == property_name)

    def property_value(self, property_name: str) -> str | None:
        values = self.property_values(property_name)
        return values[0] if values else None

    def legacy_meta(self, name: str) -> tuple[MetaProperty, ...]:
        return tuple(item for item in self.meta if item.name == name)

    @property
    def primary_title(self) -> str | None:
        return self.first("title")

    @property
    def creators(self) -> tuple[str, ...]:
        return self.all("creator")

    @property
    def primary_author(self) -> str | None:
        return self.first("creator")

    @property
    def primary_language(self) -> str | None:
        return self.first("language")

    @property
    def primary_identifier(self) -> str | None:
        return self.first("identifier")


@dataclass(frozen=True, slots=True)
class ManifestItem:
    id: str
    href: str
    resolved_path: str
    media_type: str
    properties: frozenset[str] = frozenset()
    fallback: str | None = None
    media_overlay: str | None = None


@dataclass(frozen=True, slots=True)
class SpineItem:
    idref: str
    linear: bool
    properties: frozenset[str]
    position: int
    resource: ManifestItem | None = None


@dataclass(frozen=True, slots=True)
class GuideReference:
    type: str
    href: str
    resolved_path: str | None
    title: str | None = None
    fragment: str | None = None


@dataclass(frozen=True, slots=True)
class RenditionMetadata:
    layout: str | None = None
    orientation: str | None = None
    spread: str | None = None
    flow: str | None = None

    @property
    def is_fixed_layout(self) -> bool:
        return self.layout == "pre-paginated"


@dataclass(frozen=True, slots=True)
class Package:
    version: str | None
    unique_identifier: str | None
    package_path: str
    metadata: Metadata
    manifest: tuple[ManifestItem, ...]
    spine: tuple[SpineItem, ...]
    page_progression_direction: str | None = None
    spine_toc: str | None = None
    guide: tuple[GuideReference, ...] = ()
    rendition: RenditionMetadata = RenditionMetadata()

    def manifest_by_id(self, item_id: str) -> ManifestItem | None:
        return next((item for item in self.manifest if item.id == item_id), None)

    def manifest_by_path(self, path: str) -> ManifestItem | None:
        return next((item for item in self.manifest if item.resolved_path == path), None)

    @property
    def linear_spine(self) -> tuple[SpineItem, ...]:
        return tuple(item for item in self.spine if item.linear)


@dataclass(frozen=True, slots=True)
class NavigationEntry:
    label: str
    href: str | None
    path: str | None
    fragment: str | None = None
    children: tuple["NavigationEntry", ...] = ()


@dataclass(frozen=True, slots=True)
class NavigationList:
    label: str | None
    entries: tuple[NavigationEntry, ...]
    type: str | None = None


@dataclass(frozen=True, slots=True)
class Navigation:
    toc: tuple[NavigationEntry, ...] = ()
    landmarks: tuple[NavigationEntry, ...] = ()
    page_list: tuple[NavigationEntry, ...] = ()
    lists: tuple[NavigationList, ...] = ()
    source: str | None = None
    source_path: str | None = None


@dataclass(frozen=True, slots=True)
class Cover:
    resource: ManifestItem
    method: str


@dataclass(frozen=True, slots=True)
class ContentBlock:
    kind: str
    text: str
    level: int | None = None


@dataclass(frozen=True, slots=True)
class DocumentSemantic:
    """A non-destructive semantic classification for an extracted document."""

    role: str
    confidence: float
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.role:
            raise ValueError("document semantic role cannot be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("document semantic confidence must be between 0.0 and 1.0")


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    resource: ManifestItem
    text: str
    blocks: tuple[ContentBlock, ...] = ()
    title: str | None = None
    title_source: str | None = None
    semantics: tuple[DocumentSemantic, ...] = ()

    def semantic(self, role: str) -> DocumentSemantic | None:
        """Return the strongest semantic classification for ``role``."""
        candidates = (item for item in self.semantics if item.role == role)
        return max(candidates, key=lambda item: item.confidence, default=None)

    def has_semantic(self, role: str, *, minimum_confidence: float = 0.0) -> bool:
        match = self.semantic(role)
        return match is not None and match.confidence >= minimum_confidence


@dataclass(frozen=True, slots=True)
class RemovedRange:
    resource_id: str
    start: int
    end: int
    reason: str


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    source: str
    detected: bool
    changed: bool
    removed_ranges: tuple[RemovedRange, ...] = ()
    warnings: tuple[str, ...] = ()

    def apply(self, resource_id: str, text: str) -> str:
        ranges = sorted(
            (item for item in self.removed_ranges if item.resource_id == resource_id),
            key=lambda item: item.start,
            reverse=True,
        )
        value = text
        for item in ranges:
            start = max(0, min(len(value), item.start))
            end = max(start, min(len(value), item.end))
            value = value[:start] + value[end:]
        return value.strip()


@dataclass(frozen=True, slots=True)
class EncryptedResource:
    uri: str
    resolved_path: str | None
    algorithm: str | None
    kind: str


@dataclass(frozen=True, slots=True)
class EncryptionInfo:
    resources: tuple[EncryptedResource, ...] = ()

    @property
    def has_encryption(self) -> bool:
        return bool(self.resources)

    @property
    def has_unsupported_drm(self) -> bool:
        return any(item.kind == "unsupported-encryption" for item in self.resources)
