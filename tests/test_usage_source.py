from datetime import datetime, timezone

from models import WindowUsage, UsageSnapshot
from usage_source import UsageProvider


def _snap(source, pct):
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    return UsageSnapshot(
        five_hour=WindowUsage(pct, now), weekly=WindowUsage(pct, now),
        source=source, stale=False, error=None, fetched_at=now,
    )


def test_uses_live_when_available():
    prov = UsageProvider(
        live_fetch=lambda: _snap("live", 30.0),
        local_fetch=lambda: _snap("local", 99.0),
    )
    snap = prov.get_snapshot()
    assert snap.source == "live"
    assert snap.five_hour.percent == 30.0


def test_falls_back_to_local_on_live_error():
    def boom():
        raise RuntimeError("live down")

    prov = UsageProvider(
        live_fetch=boom,
        local_fetch=lambda: _snap("local", 55.0),
    )
    snap = prov.get_snapshot()
    assert snap.source == "local"
    assert snap.five_hour.percent == 55.0


def test_returns_stale_last_known_when_all_fail():
    calls = {"n": 0}

    def live_ok_then_fail():
        calls["n"] += 1
        if calls["n"] == 1:
            return _snap("live", 20.0)
        raise RuntimeError("down")

    def local_fail():
        raise RuntimeError("no logs")

    prov = UsageProvider(live_fetch=live_ok_then_fail, local_fetch=local_fail)
    first = prov.get_snapshot()
    assert first.stale is False and first.source == "live"

    second = prov.get_snapshot()
    assert second.stale is True
    assert second.five_hour.percent == 20.0          # last-known values retained
    assert second.error is not None


def test_first_call_total_failure_returns_error_snapshot():
    def fail():
        raise RuntimeError("nope")

    prov = UsageProvider(live_fetch=fail, local_fetch=fail)
    snap = prov.get_snapshot()
    assert snap.stale is True
    assert snap.five_hour is None
    assert snap.error is not None
