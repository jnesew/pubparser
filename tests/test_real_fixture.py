from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pubparser import normalize_project_gutenberg, open_epub


FIXTURE = Path(__file__).parent / "fixtures" / "real" / "pg35" / "pg35-images-3.epub"
EXPECTED_SHA256 = "5bb9169caeca3866d7e62eac8ea24ba8be98cc6cf7d004acd227ddd12a110126"


def require_fixture() -> Path:
    if not FIXTURE.exists():
        pytest.skip("real EPUB fixture not present; run tests/fixtures/real/pg35/fetch_fixture.py")
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == EXPECTED_SHA256
    return FIXTURE


def test_project_gutenberg_35_real_world_epub() -> None:
    with open_epub(require_fixture()) as book:
        assert book.package.version == "3.0"
        assert book.metadata.primary_title == "The Time Machine"
        assert book.metadata.primary_author == "H. G. Wells"
        assert book.metadata.primary_identifier == "http://www.gutenberg.org/35"
        assert book.metadata.property_value("dcterms:modified") == "2025-12-01T08:41:54Z"
        assert [m.value for m in book.metadata.meta if m.refines == "#author_0"] == [
            "Wells, H. G. (Herbert George)", "aut"
        ]
        assert len(book.manifest) == 26
        assert len(book.spine) == 20
        assert len(book.package.linear_spine) == 20
        assert book.navigation is not None
        assert book.navigation.source == "epub3-nav"
        assert len(book.navigation.toc) == 21
        assert book.navigation.toc[3].label == "I. Introduction"
        assert book.cover is not None
        assert book.cover.resource.id == "id-2116201983663974118"
        assert book.cover.method == "epub3-cover-image"
        assert book.diagnostics == ()

        nav = book.package.manifest_by_id("ncx")
        ncx = book.package.manifest_by_id("ncx2")
        cover = book.package.manifest_by_id("id-2116201983663974118")
        assert nav is not None and "nav" in nav.properties
        assert ncx is not None and ncx.media_type == "application/x-dtbncx+xml"
        assert cover is not None and "cover-image" in cover.properties


def test_project_gutenberg_normalizer_strips_distribution_boilerplate() -> None:
    with open_epub(require_fixture()) as book:
        result = normalize_project_gutenberg(book)
        assert result.detected
        assert result.changed
        assert any(r.resource_id == "pg-header" for r in result.removed_ranges)
        assert any(r.resource_id == "pg-footer" for r in result.removed_ranges)
        cleaned = {doc.resource.id: doc.text for doc in book.iter_text(normalization=result)}
        assert cleaned["pg-header"].startswith("The Time Machine")
        assert "START OF THE PROJECT GUTENBERG EBOOK" not in cleaned["pg-header"]
        assert cleaned["pg-footer"] == ""
        assert "FULL PROJECT GUTENBERG LICENSE" not in "\n".join(cleaned.values())


def test_project_gutenberg_35_validation_has_no_errors() -> None:
    with open_epub(require_fixture()) as book:
        issues = book.validate()
        assert not [issue for issue in issues if issue.severity.value in {"error", "fatal"}]
