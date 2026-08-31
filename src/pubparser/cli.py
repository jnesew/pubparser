from __future__ import annotations

import argparse
import json
from pathlib import Path

from .book import open_epub


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
            "diagnostics": [
                {"severity": d.severity.value, "code": d.code, "message": d.message, "resource": d.resource}
                for d in book.diagnostics
            ],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="epubtool")
    sub = parser.add_subparsers(dest="command", required=True)
    info = sub.add_parser("info", help="show basic EPUB package information")
    info.add_argument("book", type=Path)
    info.add_argument("--json", action="store_true", dest="as_json")
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
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
