"""loader/sec_bulk.py: the weekly refresh loads every quarter after the newest one loaded and skips unpublished
ones (404) without failing."""

from loader import sec_bulk as S


def test_refresh_loads_every_new_quarter_and_skips_404(monkeypatch):
    calls = {"form345": [], "formd": []}
    monkeypatch.setattr(S, "quarters", lambda first: ["2025q4", "2026q1", "2026q2", "2026q3", "2026q4"])
    monkeypatch.setattr(S, "_newest", lambda ds: {"form345": "2026q1", "formd": "2026q3"}[ds])
    monkeypatch.setattr(S, "form345_files", lambda: {"2026q2": "u2", "2026q3": "u3"})
    monkeypatch.setattr(S, "formd_files", lambda: {})

    def insider(q, status, url=None):
        calls["form345"].append((q, url))
        return 0 if q == "2026q4" else 100            # 2026q4: not published yet

    def formd(q, status, url=None):
        calls["formd"].append(q)
        return 0
    monkeypatch.setattr(S, "load_insider_quarter", insider)
    monkeypatch.setattr(S, "load_formd_quarter", formd)
    monkeypatch.setattr(S, "load_exec_pay", lambda status: 5)
    monkeypatch.setattr(S, "boards", lambda status: None)
    import app.corporate
    import loader.buybacks
    built = []
    monkeypatch.setattr(app.corporate, "build", lambda status, offerings=True: built.append(offerings))
    monkeypatch.setattr(loader.buybacks, "plans", lambda status: None)
    monkeypatch.setattr(loader.buybacks, "sales", lambda status: None)
    out = S.refresh(status=lambda m: None)
    assert calls["form345"] == [("2026q2", "u2"), ("2026q3", "u3"), ("2026q4", None)]
    assert calls["formd"] == ["2026q4"]
    assert out["form345"] == ["2026q2", "2026q3"] and out["formd"] == []
    assert built == [False]                           # no new Form D: offerings not rebuilt


def test_form345_links_from_page(monkeypatch):
    html = ('<a href="/files/structureddata/data/insider-transactions-data-sets/2026q1_form345.zip">'
            '<a href="/files/datastandardsinnovation/data/insider-transactions-data-sets/2026q2_form345.zip">')
    monkeypatch.setattr(S, "_get", lambda url: html.encode())
    got = S.form345_files()
    assert got["2026q2"].startswith("https://www.sec.gov/files/datastandardsinnovation/")
    assert set(got) == {"2026q1", "2026q2"}
