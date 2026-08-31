from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pubparser import open_epub


FIXTURE = Path(__file__).parent / "fixtures" / "real" / "pg35" / "pg35-images-3.epub"
EXPECTED_SHA256 = "5bb9169caeca3866d7e62eac8ea24ba8be98cc6cf7d004acd227ddd12a110126"


def test_project_gutenberg_35_real_world_epub() -> None:
    if not FIXTURE.exists():
        pytest.skip("real EPUB fixture not present; run tests/fixtures/real/pg35/fetch_fixture.py")

    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == EXPECTED_SHA256

    with open_epub(FIXTURE) as book:
        assert book.package.version == "3.0"
        assert book.metadata.primary_title == "The Time Machine"
        assert book.metadata.primary_author == "H. G. Wells"
        assert book.metadata.primary_identifier == "http://www.gutenberg.org/35"
        assert len(book.manifest) == 26
        assert len(book.spine) == 20
        assert len(book.package.linear_spine) == 20
        assert book.diagnostics == ()

        nav = book.package.manifest_by_id("ncx")
        ncx = book.package.manifest_by_id("ncx2")
        cover = book.package.manifest_by_id("id-2116201983663974118")

        assert nav is not None and "nav" in nav.properties
        assert ncx is not None and ncx.media_type == "application/x-dtbncx+xml"
        assert cover is not None and "cover-image" in cover.properties
