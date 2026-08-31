from __future__ import annotations

import re

from .archive import EpubArchive
from .diagnostics import Diagnostic, Severity
from .errors import EpubError, ResourceError
from .models import Navigation, NavigationEntry, NavigationList, Package
from .uri import resolve_reference
from .xmlutil import local_name, parse_xml_safely

EPUB_NS = "http://www.idpf.org/2007/ops"
_WS = re.compile(r"\s+")


def _text(elem) -> str:
    return _WS.sub(" ", "".join(elem.itertext())).strip()


def _epub_type(elem) -> frozenset[str]:
    value = elem.get(f"{{{EPUB_NS}}}type", "")
    return frozenset(value.split())


def _entry_from_href(label: str, href: str | None, base_path: str, children: tuple[NavigationEntry, ...], diagnostics: list[Diagnostic]) -> NavigationEntry:
    if not href:
        return NavigationEntry(label=label, href=None, path=None, fragment=None, children=children)
    try:
        ref = resolve_reference(base_path, href)
    except ResourceError as exc:
        diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_INVALID_NAV_HREF", str(exc), base_path))
        return NavigationEntry(label=label, href=href, path=None, fragment=None, children=children)
    path = ref.path if ref.kind in {"internal", "fragment"} else None
    return NavigationEntry(label=label, href=href, path=path, fragment=ref.fragment, children=children)


def _first_child(elem, name: str):
    return next((child for child in elem if local_name(child.tag) == name), None)


def _parse_xhtml_ol(ol, base_path: str, diagnostics: list[Diagnostic]) -> tuple[NavigationEntry, ...]:
    entries: list[NavigationEntry] = []
    for li in ol:
        if local_name(li.tag) != "li":
            continue
        target = next((child for child in li if local_name(child.tag) in {"a", "span"}), None)
        nested = next((child for child in li if local_name(child.tag) == "ol"), None)
        children = _parse_xhtml_ol(nested, base_path, diagnostics) if nested is not None else ()
        if target is None:
            if children:
                entries.extend(children)
            else:
                diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_NAV_ITEM_WITHOUT_LABEL", "Navigation list item has no label target", base_path))
            continue
        label = _text(target)
        href = target.get("href") if local_name(target.tag) == "a" else None
        entries.append(_entry_from_href(label, href, base_path, children, diagnostics))
    return tuple(entries)


def _parse_epub3_nav(archive: EpubArchive, package: Package, item) -> tuple[Navigation | None, tuple[Diagnostic, ...]]:
    diagnostics: list[Diagnostic] = []
    if not archive.exists(item.resolved_path):
        return None, (Diagnostic(Severity.ERROR, "EPUB_NAV_RESOURCE_MISSING", f"Navigation resource not found: {item.resolved_path}", package.package_path),)
    try:
        root = parse_xml_safely(archive.read_bytes(item.resolved_path, max_size=archive.limits.max_xml_size), resource=item.resolved_path, max_depth=archive.limits.max_xml_depth)
    except EpubError as exc:
        return None, (Diagnostic(Severity.ERROR, "EPUB_MALFORMED_NAVIGATION", str(exc), item.resolved_path),)

    toc: tuple[NavigationEntry, ...] = ()
    landmarks: tuple[NavigationEntry, ...] = ()
    page_list: tuple[NavigationEntry, ...] = ()
    extra_lists: list[NavigationList] = []

    for elem in root.iter():
        if local_name(elem.tag) != "nav":
            continue
        types = _epub_type(elem)
        ol = _first_child(elem, "ol")
        if ol is None:
            diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_NAV_WITHOUT_LIST", "Navigation element has no ordered list", item.resolved_path))
            continue
        entries = _parse_xhtml_ol(ol, item.resolved_path, diagnostics)
        label = elem.get("aria-label") or elem.get("title")
        if "toc" in types:
            if toc:
                diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_MULTIPLE_TOC_NAVS", "Multiple EPUB 3 table-of-contents nav elements found; keeping the first", item.resolved_path))
            else:
                toc = entries
        elif "landmarks" in types:
            landmarks = entries
        elif "page-list" in types:
            page_list = entries
        else:
            extra_lists.append(NavigationList(label=label, entries=entries, type=next(iter(types), None)))

    if not toc:
        diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_NAV_TOC_MISSING", "EPUB 3 Navigation Document has no toc nav", item.resolved_path))
    return Navigation(toc=toc, landmarks=landmarks, page_list=page_list, lists=tuple(extra_lists), source="epub3-nav", source_path=item.resolved_path), tuple(diagnostics)


def _ncx_label(elem) -> str:
    nav_label = _first_child(elem, "navLabel")
    if nav_label is None:
        return ""
    text_elem = next((child for child in nav_label.iter() if local_name(child.tag) == "text"), None)
    return _text(text_elem) if text_elem is not None else _text(nav_label)


def _parse_ncx_targets(parent, target_name: str, base_path: str, diagnostics: list[Diagnostic]) -> tuple[NavigationEntry, ...]:
    entries: list[NavigationEntry] = []
    for elem in parent:
        if local_name(elem.tag) != target_name:
            continue
        label = _ncx_label(elem)
        content = _first_child(elem, "content")
        href = content.get("src") if content is not None else None
        children = _parse_ncx_targets(elem, target_name, base_path, diagnostics)
        entries.append(_entry_from_href(label, href, base_path, children, diagnostics))
    return tuple(entries)


def _parse_ncx(archive: EpubArchive, package: Package, item) -> tuple[Navigation | None, tuple[Diagnostic, ...]]:
    diagnostics: list[Diagnostic] = []
    if not archive.exists(item.resolved_path):
        return None, (Diagnostic(Severity.ERROR, "EPUB_NCX_RESOURCE_MISSING", f"NCX resource not found: {item.resolved_path}", package.package_path),)
    try:
        root = parse_xml_safely(archive.read_bytes(item.resolved_path, max_size=archive.limits.max_xml_size), resource=item.resolved_path, max_depth=archive.limits.max_xml_depth)
    except EpubError as exc:
        return None, (Diagnostic(Severity.ERROR, "EPUB_MALFORMED_NCX", str(exc), item.resolved_path),)

    nav_map = next((elem for elem in root if local_name(elem.tag) == "navMap"), None)
    toc = _parse_ncx_targets(nav_map, "navPoint", item.resolved_path, diagnostics) if nav_map is not None else ()
    if not toc:
        diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_NCX_NAVMAP_MISSING", "NCX has no usable navMap", item.resolved_path))

    page_list_elem = next((elem for elem in root if local_name(elem.tag) == "pageList"), None)
    page_list = _parse_ncx_targets(page_list_elem, "pageTarget", item.resolved_path, diagnostics) if page_list_elem is not None else ()

    lists: list[NavigationList] = []
    for nav_list in (elem for elem in root if local_name(elem.tag) == "navList"):
        label = _ncx_label(nav_list) or None
        entries = _parse_ncx_targets(nav_list, "navTarget", item.resolved_path, diagnostics)
        lists.append(NavigationList(label=label, entries=entries, type="navList"))

    return Navigation(toc=toc, page_list=page_list, lists=tuple(lists), source="epub2-ncx", source_path=item.resolved_path), tuple(diagnostics)


def parse_navigation(archive: EpubArchive, package: Package) -> tuple[Navigation | None, tuple[Diagnostic, ...]]:
    nav_items = [item for item in package.manifest if "nav" in item.properties]
    diagnostics: list[Diagnostic] = []
    if nav_items:
        if len(nav_items) > 1:
            diagnostics.append(Diagnostic(Severity.WARNING, "EPUB_MULTIPLE_NAV_DOCUMENTS", "Multiple manifest items have the nav property; using the first", package.package_path))
        nav, nav_diagnostics = _parse_epub3_nav(archive, package, nav_items[0])
        diagnostics.extend(nav_diagnostics)
        if nav is not None:
            return nav, tuple(diagnostics)

    ncx_item = package.manifest_by_id(package.spine_toc) if package.spine_toc else None
    if ncx_item is None:
        ncx_item = next((item for item in package.manifest if item.media_type == "application/x-dtbncx+xml"), None)
    if ncx_item is not None:
        nav, nav_diagnostics = _parse_ncx(archive, package, ncx_item)
        diagnostics.extend(nav_diagnostics)
        return nav, tuple(diagnostics)

    return None, tuple(diagnostics)
