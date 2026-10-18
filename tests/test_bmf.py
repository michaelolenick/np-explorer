"""bmf.changed(): which BMF files the IRS has republished since our copy."""

import os

from loader import bmf, irs


def _setup(monkeypatch, tmp_path, remote):
    monkeypatch.setattr(irs, "RAW_DIR", tmp_path)
    monkeypatch.setattr(irs, "BMF_FILES", ["eo1", "eo2", "eo3"])
    monkeypatch.setattr(irs, "remote_mtime", lambda url: remote.get(url.rsplit("/", 1)[-1][:-4]))
    (tmp_path / "bmf").mkdir()


def _local(tmp_path, name, mtime):
    p = tmp_path / "bmf" / f"{name}.csv"
    p.write_text("EIN\n")
    os.utime(p, (mtime, mtime))


def test_newer_irs_copy_is_stale(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {"eo1": 2_000, "eo2": 1_000, "eo3": 1_000})
    for name in ("eo1", "eo2", "eo3"):
        _local(tmp_path, name, 1_000)
    assert bmf.changed() == ["eo1"]


def test_missing_file_is_stale(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {"eo1": 1_000, "eo2": 1_000, "eo3": 1_000})
    _local(tmp_path, "eo1", 1_000)
    _local(tmp_path, "eo3", 1_000)
    assert bmf.changed() == ["eo2"]


def test_unknown_irs_date_keeps_our_copy(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, {})
    for name in ("eo1", "eo2", "eo3"):
        _local(tmp_path, name, 1_000)
    assert bmf.changed() == []
