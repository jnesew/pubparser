from __future__ import annotations

from dataclasses import replace

from .diagnostics import Diagnostic, Severity
from .models import Cover, DocumentSemantic, ExtractedDocument, Navigation, Package


def _merge_semantic(
    document: ExtractedDocument,
    role: str,
    confidence: float,
    evidence: str,
) -> ExtractedDocument:
    existing = document.semantic(role)
    if existing is None:
        semantic = DocumentSemantic(role, confidence, (evidence,))
        return replace(document, semantics=document.semantics + (semantic,))

    merged = DocumentSemantic(
        role=role,
        confidence=max(existing.confidence, confidence),
        evidence=tuple(dict.fromkeys((*existing.evidence, evidence))),
    )
    return replace(
        document,
        semantics=tuple(item for item in document.semantics if item.role != role) + (merged,),
    )


def classify_document(
    package: Package,
    navigation: Navigation | None,
    document: ExtractedDocument,
) -> ExtractedDocument:
    """Augment markup semantics with package-level, non-destructive hints."""
    resource = document.resource
    classified = document
    if "nav" in resource.properties:
        classified = _merge_semantic(classified, "toc", 1.0, "manifest-nav-property")
    if navigation is not None and navigation.source_path == resource.resolved_path:
        classified = _merge_semantic(classified, "toc", 1.0, "navigation-source")
    for reference in package.guide:
        reference_types = {token.casefold() for token in reference.type.split()}
        if reference.resolved_path == resource.resolved_path and reference_types & {"toc", "contents"}:
            classified = _merge_semantic(classified, "toc", 0.98, "package-guide-reference")
    return classified


def detect_cover(package: Package) -> tuple[Cover | None, tuple[Diagnostic, ...]]:
    diagnostics: list[Diagnostic] = []
    property_items = [item for item in package.manifest if "cover-image" in item.properties]
    if property_items:
        if len(property_items) > 1:
            diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_MULTIPLE_COVER_IMAGES", "Multiple manifest items have the cover-image property; using the first", package.package_path))
        return Cover(property_items[0], "epub3-cover-image"), tuple(diagnostics)

    legacy = package.metadata.legacy_meta("cover")
    for meta in legacy:
        cover_id = meta.content or meta.value
        if not cover_id:
            continue
        item = package.manifest_by_id(cover_id)
        if item is not None:
            return Cover(item, "epub2-meta-cover"), tuple(diagnostics)
        diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_COVER_ID_MISSING", f"Legacy cover metadata references unknown manifest id: {cover_id}", package.package_path))

    for ref in package.guide:
        if ref.type.lower() != "cover" or ref.resolved_path is None:
            continue
        item = package.manifest_by_path(ref.resolved_path)
        if item is not None:
            return Cover(item, "epub2-guide-cover"), tuple(diagnostics)
        diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_GUIDE_COVER_NOT_IN_MANIFEST", f"Guide cover target is not in manifest: {ref.href}", package.package_path))

    return None, tuple(diagnostics)
