from __future__ import annotations

import re
from typing import Protocol

from .models import NormalizationResult, RemovedRange

_START = re.compile(r"\*{3}\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK\b.*?\*{3}", re.IGNORECASE)
_END = re.compile(r"\*{3}\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK\b.*?\*{3}", re.IGNORECASE)


class SourceNormalizer(Protocol):
    def detect(self, book) -> bool: ...
    def normalize(self, book) -> NormalizationResult: ...


class ProjectGutenbergNormalizer:
    source = "project_gutenberg"

    def detect(self, book) -> bool:
        values = (
            book.metadata.primary_identifier,
            *book.metadata.all("source"),
        )
        if any(value and "gutenberg.org" in value.lower() for value in values):
            return True
        for item in book.package.linear_spine[:2] + book.package.linear_spine[-2:]:
            if item.resource is None or item.resource.media_type != "application/xhtml+xml":
                continue
            try:
                text = book.extract_document(item.resource.id, structured=False).text
            except Exception:
                continue
            if _START.search(text) or _END.search(text):
                return True
        return False

    def normalize(self, book) -> NormalizationResult:
        if not self.detect(book):
            return NormalizationResult(source=self.source, detected=False, changed=False)

        removed: list[RemovedRange] = []
        warnings: list[str] = []
        for spine_item in book.package.linear_spine:
            resource = spine_item.resource
            if resource is None or resource.media_type != "application/xhtml+xml":
                continue
            try:
                text = book.extract_document(resource.id, structured=False).text
            except Exception as exc:
                warnings.append(f"Could not inspect {resource.href}: {exc}")
                continue

            start = _START.search(text)
            end = _END.search(text)
            if start:
                removed.append(RemovedRange(resource.id, 0, start.end(), "Project Gutenberg distribution header"))
            if end:
                range_start = end.start()
                if resource.id.lower() in {"pg-footer", "gutenberg-footer"}:
                    range_start = 0
                removed.append(RemovedRange(resource.id, range_start, len(text), "Project Gutenberg distribution footer/license"))

        return NormalizationResult(
            source=self.source,
            detected=True,
            changed=bool(removed),
            removed_ranges=tuple(removed),
            warnings=tuple(warnings),
        )


def normalize_project_gutenberg(book) -> NormalizationResult:
    return ProjectGutenbergNormalizer().normalize(book)
