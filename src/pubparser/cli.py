from __future__ import annotations

import argparse
import json
from pathlib import Path

from .book import open_epub
from .diagnostics import Severity
from .models import NavigationEntry
from .normalizers import normalize_project_gutenberg


def _diagnostic_dict(d) -> dict[str, object]:
    return {"severity": d.severity.value, "code": d.code, "message": d.message, "resource": d.resource}


def _book_info(path: Path) -> dict[str, object]:
    with open_epub(path) as book:
        return {
            "version": book.package.version,
            "package_path": book.package.package_path,
            "title": book.metadata.primary_title,
            "authors": list(book.metadata.creators),
            "language": book.metadata.primary_language,
            "manifest_items": len(book.manifest),
            "spine_items": len(book.spine),
            "navigation_source": book.navigation.source if book.navigation else None,
            "toc_entries": len(book.navigation.toc) if book.navigation else 0,
            "cover_id": book.cover.resource.id if book.cover else None,
            "cover_method": book.cover.method if book.cover else None,
            "page_progression_direction": book.package.page_progression_direction,
            "encrypted_resources": len(book.encryption.resources),
            "unsupported_encryption": book.encryption.has_unsupported_drm,
            "rendition": {
                "layout": book.package.rendition.layout,
                "orientation": book.package.rendition.orientation,
                "spread": book.package.rendition.spread,
                "flow": book.package.rendition.flow,
            },
            "diagnostics": [_diagnostic_dict(d) for d in book.diagnostics],
        }


def _entry_dict(entry: NavigationEntry) -> dict[str, object]:
    return {
        "label": entry.label,
        "href": entry.href,
        "path": entry.path,
        "fragment": entry.fragment,
        "children": [_entry_dict(child) for child in entry.children],
    }


def _print_toc(entries: tuple[NavigationEntry, ...], depth: int = 0) -> None:
    for entry in entries:
        suffix = f" -> {entry.href}" if entry.href else ""
        print(f"{'  ' * depth}{entry.label}{suffix}")
        _print_toc(entry.children, depth + 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="epubtool")
    sub = parser.add_subparsers(dest="command", required=True)

    info = sub.add_parser("info", help="show basic EPUB package information")
    info.add_argument("book", type=Path)
    info.add_argument("--json", action="store_true", dest="as_json")

    metadata = sub.add_parser("metadata", help="show package metadata")
    metadata.add_argument("book", type=Path)
    metadata.add_argument("--json", action="store_true", dest="as_json")

    spine = sub.add_parser("spine", help="show package reading order")
    spine.add_argument("book", type=Path)
    spine.add_argument("--json", action="store_true", dest="as_json")

    files = sub.add_parser("files", help="list manifest resources")
    files.add_argument("book", type=Path)
    files.add_argument("--media-type")
    files.add_argument("--property")
    files.add_argument("--json", action="store_true", dest="as_json")

    toc = sub.add_parser("toc", help="show normalized table of contents")
    toc.add_argument("book", type=Path)
    toc.add_argument("--json", action="store_true", dest="as_json")

    text = sub.add_parser("text", help="extract text in spine order")
    text.add_argument("book", type=Path)
    text.add_argument("--clean-gutenberg", action="store_true")
    text.add_argument("--json", action="store_true", dest="as_json")

    validate = sub.add_parser("validate", help="run structural validation checks")
    validate.add_argument("book", type=Path)
    validate.add_argument("--json", action="store_true", dest="as_json")

    args = parser.parse_args(argv)
    if args.command == "info":
        data = _book_info(args.book)
        if args.as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"Title: {data['title'] or ''}")
            print(f"Author: {', '.join(data['authors'])}")
            print(f"Language: {data['language'] or ''}")
            print(f"EPUB version: {data['version'] or ''}")
            print(f"Package: {data['package_path']}")
            print(f"Manifest items: {data['manifest_items']}")
            print(f"Spine items: {data['spine_items']}")
            print(f"Navigation: {data['navigation_source'] or 'none'} ({data['toc_entries']} top-level entries)")
            print(f"Cover: {data['cover_id'] or 'none'}")
            print(f"Encrypted resources: {data['encrypted_resources']}")
        return 0

    if args.command == "metadata":
        with open_epub(args.book) as book:
            data = {
                "dc": [
                    {"name": item.name, "value": item.value, "id": item.id, "attributes": dict(item.attributes)}
                    for item in book.metadata.values
                ],
                "meta": [
                    {
                        "property": item.property, "value": item.value, "id": item.id,
                        "refines": item.refines, "scheme": item.scheme,
                        "name": item.name, "content": item.content,
                        "attributes": dict(item.attributes),
                    }
                    for item in book.metadata.meta
                ],
            }
            if args.as_json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                for item in book.metadata.values:
                    suffix = f" [{item.id}]" if item.id else ""
                    print(f"{item.name}{suffix}: {item.value}")
                for item in book.metadata.meta:
                    key = item.property or item.name or "meta"
                    suffix = f" refines={item.refines}" if item.refines else ""
                    print(f"{key}{suffix}: {item.value}")
        return 0

    if args.command == "spine":
        with open_epub(args.book) as book:
            data = [
                {
                    "position": item.position,
                    "idref": item.idref,
                    "linear": item.linear,
                    "properties": sorted(item.properties),
                    "href": item.resource.href if item.resource else None,
                    "media_type": item.resource.media_type if item.resource else None,
                }
                for item in book.spine
            ]
            if args.as_json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                for item in data:
                    marker = "linear" if item["linear"] else "non-linear"
                    print(f"{item['position']:>4} {item['idref']} [{marker}] -> {item['href'] or '<missing>'}")
        return 0

    if args.command == "files":
        with open_epub(args.book) as book:
            resources = tuple(book.resources)
            if args.media_type:
                resources = tuple(resource for resource in resources if resource.media_type == args.media_type)
            if args.property:
                resources = tuple(resource for resource in resources if args.property in resource.properties)
            data = [
                {
                    "id": resource.id,
                    "href": resource.href,
                    "path": resource.resolved_path if not resource.is_remote else None,
                    "media_type": resource.media_type,
                    "properties": sorted(resource.properties),
                    "remote": resource.is_remote,
                    "exists": resource.exists,
                }
                for resource in resources
            ]
            if args.as_json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                for item in data:
                    props = f" properties={','.join(item['properties'])}" if item["properties"] else ""
                    print(f"{item['id']}\t{item['media_type']}\t{item['href']}{props}")
        return 0

    if args.command == "toc":
        with open_epub(args.book) as book:
            entries = book.navigation.toc if book.navigation else ()
            if args.as_json:
                print(json.dumps([_entry_dict(entry) for entry in entries], ensure_ascii=False, indent=2))
            else:
                _print_toc(entries)
        return 0

    if args.command == "text":
        with open_epub(args.book) as book:
            normalization = normalize_project_gutenberg(book) if args.clean_gutenberg else None
            documents = list(book.iter_text(structured=False, normalization=normalization))
            if args.as_json:
                print(json.dumps([
                    {"id": doc.resource.id, "href": doc.resource.href, "text": doc.text}
                    for doc in documents
                ], ensure_ascii=False, indent=2))
            else:
                print("\n\n".join(doc.text for doc in documents if doc.text))
        return 0

    if args.command == "validate":
        with open_epub(args.book) as book:
            issues = book.validate()
            if args.as_json:
                print(json.dumps([_diagnostic_dict(d) for d in issues], ensure_ascii=False, indent=2))
            else:
                for issue in issues:
                    resource = f" [{issue.resource}]" if issue.resource else ""
                    print(f"{issue.severity.value.upper()} {issue.code}{resource}: {issue.message}")
                if not issues:
                    print("No issues found.")
            return 1 if any(issue.severity in {Severity.ERROR, Severity.FATAL} for issue in issues) else 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
