from __future__ import annotations

import tomllib
from pathlib import Path

from pubparser.cli import entrypoint


ROOT = Path(__file__).parents[1]


def test_project_metadata_uses_pep639_license_expression_without_legacy_classifier():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert project["version"] == "0.2.0.dev0"
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert "License :: OSI Approved :: MIT License" not in project["classifiers"]
    assert project["scripts"]["epubtool"] == "pubparser.cli:entrypoint"
    assert callable(entrypoint)
