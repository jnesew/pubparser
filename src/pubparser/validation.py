from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from zipfile import ZIP_STORED

from .diagnostics import Diagnostic, Severity
from .models import NavigationEntry

_EXPECTED_MEDIA_TYPES = {
    ".xhtml": "application/xhtml+xml",
    ".html": "application/xhtml+xml",
    ".htm": "application/xhtml+xml",
    ".css": "text/css",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ncx": "application/x-dtbncx+xml",
}


def _is_remote(href: str) -> bool:
    parts = urlsplit(href)
    return bool(parts.scheme or parts.netloc)


def _walk_navigation(entries: tuple[NavigationEntry, ...]):
    for entry in entries:
        yield entry
        yield from _walk_navigation(entry.children)


def validate_book(book, *, include_parse_diagnostics: bool = True) -> tuple[Diagnostic, ...]:
    issues: list[Diagnostic] = list(book.diagnostics) if include_parse_diagnostics else []
    package = book.package
    archive = book._archive

    if not archive.exists("mimetype"):
        issues.append(Diagnostic(Severity.ERROR, "EPUB_MIMETYPE_MISSING", "EPUB archive has no mimetype file"))
    else:
        try:
            mimetype = archive.read_bytes("mimetype", max_size=128)
            info = archive.info("mimetype")
        except Exception as exc:
            issues.append(Diagnostic(Severity.ERROR, "EPUB_MIMETYPE_UNREADABLE", str(exc), "mimetype"))
        else:
            if mimetype != b"application/epub+zip":
                issues.append(Diagnostic(Severity.ERROR, "EPUB_MIMETYPE_INVALID", "mimetype content is not exactly application/epub+zip", "mimetype"))
            if info.compress_type != ZIP_STORED:
                issues.append(Diagnostic(Severity.ERROR, "EPUB_MIMETYPE_COMPRESSED", "mimetype entry must be stored without compression", "mimetype"))
            if archive.names and archive.names[0] != "mimetype":
                issues.append(Diagnostic(Severity.WARNING, "EPUB_MIMETYPE_NOT_FIRST", "mimetype should be the first ZIP entry", "mimetype"))

    for name in ("title", "identifier", "language"):
        if not package.metadata.first(name):
            issues.append(Diagnostic(Severity.ERROR, f"EPUB_METADATA_{name.upper()}_MISSING", f"Required dc:{name} metadata is missing", package.package_path))
    if package.version and package.version.startswith("3"):
        modified = tuple(item for item in package.metadata.meta if item.property == "dcterms:modified" and not item.refines)
        if not modified:
            issues.append(Diagnostic(Severity.ERROR, "EPUB_MODIFIED_MISSING", "EPUB 3 package has no unrefined dcterms:modified metadata", package.package_path))
        elif len(modified) > 1:
            issues.append(Diagnostic(Severity.ERROR, "EPUB_MULTIPLE_MODIFIED", "EPUB 3 package must contain exactly one unrefined dcterms:modified property", package.package_path))
        nav_items = [item for item in package.manifest if "nav" in item.properties]
        if not nav_items:
            issues.append(Diagnostic(Severity.ERROR, "EPUB_NAV_DOCUMENT_MISSING", "EPUB 3 package has no manifest item with the nav property", package.package_path))
        elif len(nav_items) > 1:
            issues.append(Diagnostic(Severity.ERROR, "EPUB_MULTIPLE_NAV_DOCUMENTS", "EPUB 3 package has more than one manifest item with the nav property", package.package_path))
        elif nav_items[0].media_type != "application/xhtml+xml":
            issues.append(Diagnostic(Severity.ERROR, "EPUB_NAV_MEDIA_TYPE_INVALID", "EPUB navigation document must have media type application/xhtml+xml", package.package_path))

    if package.unique_identifier:
        ids = {value.id for value in package.metadata.values if value.id}
        if package.unique_identifier not in ids:
            issues.append(Diagnostic(Severity.ERROR, "EPUB_UNIQUE_IDENTIFIER_TARGET_MISSING", f"unique-identifier points to missing metadata id: {package.unique_identifier}", package.package_path))

    path_counts = Counter(item.resolved_path for item in package.manifest if not _is_remote(item.href))
    for path, count in path_counts.items():
        if count > 1:
            issues.append(Diagnostic(Severity.WARNING, "EPUB_DUPLICATE_MANIFEST_PATH", f"Multiple manifest items resolve to the same resource: {path}", package.package_path))

    for item in package.manifest:
        if _is_remote(item.href):
            continue
        if not archive.exists(item.resolved_path):
            issues.append(Diagnostic(Severity.ERROR, "EPUB_MANIFEST_RESOURCE_MISSING", f"Manifest resource not found: {item.href}", item.resolved_path))
        suffix = PurePosixPath(urlsplit(item.href).path).suffix.lower()
        expected = _EXPECTED_MEDIA_TYPES.get(suffix)
        if expected and item.media_type != expected:
            issues.append(Diagnostic(Severity.WARNING, "EPUB_MEDIA_TYPE_MISMATCH", f"{item.href} declares {item.media_type}; expected {expected} for {suffix}", package.package_path))

    by_id = {item.id: item for item in package.manifest}
    for item in package.manifest:
        if item.fallback and item.fallback not in by_id:
            issues.append(Diagnostic(Severity.ERROR, "EPUB_FALLBACK_TARGET_MISSING", f"Fallback target does not exist: {item.id} -> {item.fallback}", package.package_path))
            continue
        seen: set[str] = set()
        current = item
        while current.fallback:
            if current.id in seen:
                issues.append(Diagnostic(Severity.ERROR, "EPUB_FALLBACK_CYCLE", f"Fallback cycle includes manifest item: {current.id}", package.package_path))
                break
            seen.add(current.id)
            next_item = by_id.get(current.fallback)
            if next_item is None:
                break
            current = next_item

    if book.navigation is not None:
        groups = (book.navigation.toc, book.navigation.landmarks, book.navigation.page_list)
        for entries in groups:
            for entry in _walk_navigation(entries):
                if entry.path is not None and not archive.exists(entry.path):
                    issues.append(Diagnostic(Severity.ERROR, "EPUB_NAV_TARGET_MISSING", f"Navigation target not found: {entry.href}", book.navigation.source_path))
        for nav_list in book.navigation.lists:
            for entry in _walk_navigation(nav_list.entries):
                if entry.path is not None and not archive.exists(entry.path):
                    issues.append(Diagnostic(Severity.ERROR, "EPUB_NAV_TARGET_MISSING", f"Navigation target not found: {entry.href}", book.navigation.source_path))

    for encrypted in book.encryption.resources:
        if encrypted.resolved_path is not None and not archive.exists(encrypted.resolved_path):
            issues.append(Diagnostic(Severity.ERROR, "EPUB_ENCRYPTED_RESOURCE_MISSING", f"Encrypted resource not found: {encrypted.uri}", "META-INF/encryption.xml"))

    unique: list[Diagnostic] = []
    seen_issues: set[tuple[object, ...]] = set()
    for issue in issues:
        key = (issue.severity, issue.code, issue.message, issue.resource)
        if key not in seen_issues:
            seen_issues.add(key)
            unique.append(issue)
    return tuple(unique)
