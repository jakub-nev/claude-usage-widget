from datetime import datetime, timezone

from models import WindowUsage, UsageSnapshot
from usage_source import UsageProvider


def _snap(source, pct):
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    return UsageSnapshot(
        five_hour=WindowUsage(pct, now), weekly=WindowUsage(pct, now),
        source=source, stale=False, error=None, fetched_at=now,
    )


def test_returns_live_when_available():
    prov = UsageProvider(live_fetch=lambda: _snap("live", 30.0))
    snap = prov.get_snapshot()
    assert snap.source == "live"
    assert snap.stale is False
    assert snap.five_hour.percent == 30.0


def test_returns_stale_last_known_live_when_fetch_fails():
    calls = {"n": 0}

    def live_ok_then_fail():
        calls["n"] += 1
        if calls["n"] == 1:
            return _snap("live", 20.0)
        raise RuntimeError("HTTP Error 429: Too Many Requests")

    prov = UsageProvider(live_fetch=live_ok_then_fail)
    first = prov.get_snapshot()
    assert first.stale is False and first.source == "live"

    second = prov.get_snapshot()
    assert second.stale is True
    assert second.source == "live"               # last real source retained
    assert second.five_hour.percent == 20.0      # last real values, not fabricated
    assert second.weekly.percent == 20.0
    assert "429" in second.error


def test_returns_empty_snapshot_when_live_never_succeeded():
    def always_fail():
        raise RuntimeError("HTTP Error 429: Too Many Requests")

    prov = UsageProvider(live_fetch=always_fail)
    snap = prov.get_snapshot()
    assert snap.stale is True
    assert snap.source == "none"
    assert snap.five_hour is None                # no fabricated local estimate
    assert snap.weekly is None
    assert snap.error is not None


def test_recovers_to_fresh_live_after_failure():
    calls = {"n": 0}

    def fail_then_ok():
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("429")
        return _snap("live", 55.0)

    prov = UsageProvider(live_fetch=fail_then_ok)
    prov.get_snapshot()                          # fail (empty)
    prov.get_snapshot()                          # fail (still empty)
    good = prov.get_snapshot()                   # recovered
    assert good.stale is False
    assert good.source == "live"
    assert good.five_hour.percent == 55.0
