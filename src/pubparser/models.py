from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetadataValue:
    name: str
    value: str
    id: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Metadata:
    values: tuple[MetadataValue, ...] = ()

    def all(self, name: str) -> tuple[str, ...]:
        return tuple(item.value for item in self.values if item.name == name)

    def first(self, name: str) -> str | None:
        values = self.all(name)
        return values[0] if values else None

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
class Package:
    version: str | None
    unique_identifier: str | None
    package_path: str
    metadata: Metadata
    manifest: tuple[ManifestItem, ...]
    spine: tuple[SpineItem, ...]
    page_progression_direction: str | None = None

    def manifest_by_id(self, item_id: str) -> ManifestItem | None:
        return next((item for item in self.manifest if item.id == item_id), None)

    @property
    def linear_spine(self) -> tuple[SpineItem, ...]:
        return tuple(item for item in self.spine if item.linear)
