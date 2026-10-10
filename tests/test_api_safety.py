from pathlib import Path

import pytest

from floodlens.api import _safe_checkpoint, _safe_path


def test_safe_path_allows_configured_relative_data_path(tmp_path, monkeypatch):
    import floodlens.api as api
    monkeypatch.setattr(api, "_repo_root", tmp_path)
    allowed = tmp_path / "data" / "input.tif"
    allowed.parent.mkdir()
    allowed.write_bytes(b"fixture")
    assert _safe_path("data/input.tif", (tmp_path / "data",)) == allowed


def test_safe_path_rejects_traversal(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        _safe_path("../secret.tif", (tmp_path / "data",))


def test_checkpoint_requires_approved_manifest(tmp_path, monkeypatch):
    import floodlens.api as api
    monkeypatch.setattr(api, "_repo_root", tmp_path)
    monkeypatch.setattr(api, "_checkpoint_root", (tmp_path / "data/models").resolve())
    checkpoint = tmp_path / "data/models/model.pt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"not-a-checkpoint")
    with pytest.raises(ValueError, match="provenance"):
        _safe_checkpoint("data/models/model.pt")
