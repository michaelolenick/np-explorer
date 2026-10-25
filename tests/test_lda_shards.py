"""The lobbying backfill split: every filing period belongs to exactly one shard, and together the shards stay at
the API's 120 requests a minute."""

from loader import lda


def test_each_period_has_one_owner():
    years = list(range(2026, 1998, -1))
    allu = [(y, p) for y in years for p in lda.PERIODS]
    owned = []
    for i in range(4):
        u = lda.units(years, i, 4)
        assert sorted(u) == sorted(allu)              # each shard can reach every period (helps when done early)
        owned += u[: len([j for j in range(len(allu)) if j % 4 == i])]
    assert sorted(owned) == sorted(allu)              # but its own share comes first, and the shares don't overlap


def test_unsharded_is_newest_first():
    assert lda.units([2021, 2020]) == [(y, p) for y in (2021, 2020) for p in lda.PERIODS]


def test_shards_share_the_rate(monkeypatch):
    monkeypatch.setenv("LDA_API_KEY", "x")
    assert 60 / lda._gap(4) * 4 == 120
    assert 60 / lda._gap(1) == 120
    assert lda.shard_lock(0) != lda.CRAWL_LOCK
