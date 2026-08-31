from __future__ import annotations

from .archive import EpubArchive
from .diagnostics import Diagnostic, Severity
from .errors import PackageError, ResourceError
from .models import (
    GuideReference,
    ManifestItem,
    Metadata,
    MetadataValue,
    MetaProperty,
    Package,
    RenditionMetadata,
    SpineItem,
)
from .uri import resolve_reference
from .xmlutil import local_name, parse_xml_safely

DC_ELEMENTS = {
    "title", "creator", "contributor", "language", "identifier", "publisher",
    "date", "subject", "description", "rights", "source", "relation",
    "coverage", "type", "format",
}


def _meta_value(elem) -> MetaProperty:
    text = "".join(elem.itertext()).strip()
    content = elem.get("content")
    return MetaProperty(
        property=elem.get("property"),
        value=text or content or "",
        id=elem.get("id"),
        refines=elem.get("refines"),
        scheme=elem.get("scheme"),
        name=elem.get("name"),
        content=content,
        attributes=tuple(sorted((k, v) for k, v in elem.attrib.items())),
    )


def parse_package(archive: EpubArchive, package_path: str) -> tuple[Package, tuple[Diagnostic, ...]]:
    if not archive.exists(package_path):
        raise PackageError(f"package document not found: {package_path}")
    try:
        data = archive.read_bytes(package_path, max_size=archive.limits.max_xml_size)
        root = parse_xml_safely(data, resource=package_path, max_depth=archive.limits.max_xml_depth)
    except Exception as exc:
        raise PackageError(str(exc)) from exc
    if local_name(root.tag) != "package":
        raise PackageError("package document root is not <package>")

    diagnostics: list[Diagnostic] = []
    metadata_values: list[MetadataValue] = []
    metadata_meta: list[MetaProperty] = []
    manifest: list[ManifestItem] = []
    manifest_ids: set[str] = set()

    metadata_elem = next((e for e in root if local_name(e.tag) == "metadata"), None)
    if metadata_elem is not None:
        for elem in metadata_elem:
            name = local_name(elem.tag)
            if name in DC_ELEMENTS:
                value = "".join(elem.itertext()).strip()
                attrs = tuple(sorted((k, v) for k, v in elem.attrib.items()))
                metadata_values.append(MetadataValue(name, value, elem.get("id"), attrs))
            elif name == "meta":
                metadata_meta.append(_meta_value(elem))

    metadata = Metadata(tuple(metadata_values), tuple(metadata_meta))

    manifest_elem = next((e for e in root if local_name(e.tag) == "manifest"), None)
    if manifest_elem is None:
        raise PackageError("package has no manifest")
    for elem in manifest_elem:
        if local_name(elem.tag) != "item":
            continue
        item_id = elem.get("id")
        href = elem.get("href")
        media_type = elem.get("media-type")
        if not item_id or not href or not media_type:
            diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_INCOMPLETE_MANIFEST_ITEM", "Manifest item is missing id, href, or media-type", package_path))
            continue
        if item_id in manifest_ids:
            diagnostics.append(Diagnostic(Severity.ERROR, "EPUB_DUPLICATE_MANIFEST_ID", f"Duplicate manifest id: {item_id}", package_path))
            continue
        try:
            ref = resolve_reference(package_path, href)
        except ResourceError as exc:
            diagnostics.append(Diagnostic(Severity.ERROR, "EPUB_INVALID_MANIFEST_HREF", str(exc), package_path))
            resolved_path = href
        else:
            if ref.kind != "internal" or ref.path is None:
                diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_REMOTE_MANIFEST_RESOURCE", f"Manifest resource is remote: {href}", package_path))
                resolved_path = href
            else:
                resolved_path = ref.path
        manifest_ids.add(item_id)
        manifest.append(ManifestItem(
            id=item_id,
            href=href,
            resolved_path=resolved_path,
            media_type=media_type,
            properties=frozenset(elem.get("properties", "").split()),
            fallback=elem.get("fallback"),
            media_overlay=elem.get("media-overlay"),
        ))

    by_id = {item.id: item for item in manifest}
    spine_elem = next((e for e in root if local_name(e.tag) == "spine"), None)
    if spine_elem is None:
        raise PackageError("package has no spine")
    spine: list[SpineItem] = []
    for pos, elem in enumerate(e for e in spine_elem if local_name(e.tag) == "itemref"):
        idref = elem.get("idref")
        if not idref:
            diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_SPINE_ITEM_MISSING_IDREF", "Spine item lacks idref", package_path))
            continue
        resource = by_id.get(idref)
        if resource is None:
            diagnostics.append(Diagnostic(Severity.ERROR, "EPUB_MISSING_MANIFEST_ITEM", f"Spine references unknown manifest id: {idref}", package_path))
        spine.append(SpineItem(
            idref=idref,
            linear=elem.get("linear", "yes").lower() != "no",
            properties=frozenset(elem.get("properties", "").split()),
            position=pos,
            resource=resource,
        ))

    guide: list[GuideReference] = []
    guide_elem = next((e for e in root if local_name(e.tag) == "guide"), None)
    if guide_elem is not None:
        for elem in guide_elem:
            if local_name(elem.tag) != "reference":
                continue
            ref_type = elem.get("type")
            href = elem.get("href")
            if not ref_type or not href:
                continue
            try:
                resolved = resolve_reference(package_path, href)
                resolved_path = resolved.path if resolved.kind in {"internal", "fragment"} else None
            except ResourceError:
                resolved_path = None
                diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_INVALID_GUIDE_HREF", f"Invalid guide reference: {href}", package_path))
            guide.append(GuideReference(ref_type, href, resolved_path, elem.get("title")))

    package = Package(
        version=root.get("version"),
        unique_identifier=root.get("unique-identifier"),
        package_path=package_path,
        metadata=metadata,
        manifest=tuple(manifest),
        spine=tuple(spine),
        page_progression_direction=spine_elem.get("page-progression-direction"),
        spine_toc=spine_elem.get("toc"),
        guide=tuple(guide),
        rendition=RenditionMetadata(
            layout=metadata.property_value("rendition:layout"),
            orientation=metadata.property_value("rendition:orientation"),
            spread=metadata.property_value("rendition:spread"),
            flow=metadata.property_value("rendition:flow"),
        ),
    )
    return package, tuple(diagnostics)
