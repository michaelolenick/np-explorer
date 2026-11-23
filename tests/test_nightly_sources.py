"""Each nightly source fails on its own with a clear message (2026-11-23)."""
import subprocess
from pathlib import Path

import pytest

from loader import fred, state_files

ROOT = Path(__file__).resolve().parent.parent


def test_state_file_403_reports_exit_code_and_status(tmp_path, monkeypatch):
    monkeypatch.setattr(state_files, "ROOT", tmp_path)

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="403", stderr="")

    monkeypatch.setattr(state_files.subprocess, "run", fake_run)
    with pytest.raises(state_files.DownloadFailed) as e:
        state_files.fetch("ak")
    assert "curl exit 0" in str(e.value) and "HTTP 403" in str(e.value)
    assert not state_files.path("ak").exists()          # a block page never lands as the data file


def test_fred_search_stops_at_the_five_thousand_cap(monkeypatch):
    calls = []

    class C:
        def api(self, path, cache=None, max_age=None, **p):
            calls.append(p["offset"])
            if p["offset"] >= 5000:
                raise fred.NotFound("Exceeded 5000 maximum searchable results")
            return {"seriess": [{"id": f"S{p['offset']}-{i}"} for i in range(p["limit"])], "count": 25000}

    out = fred.search_all(C(), "Resident Population in County")
    assert len(out) == 5000 and max(calls) == 4000


def test_nightly_sh_runs_every_source_through_src():
    text = (ROOT / "scripts" / "nightly.sh").read_text()
    assert "src() {" in text
    assert 'src "fred refresh"' in text and 'src "business registry"' in text
    r = subprocess.run(["sh", "-n", str(ROOT / "scripts" / "nightly.sh")])
    assert r.returncode == 0
