from datetime import datetime, timezone
from models import WindowUsage, UsageSnapshot


def test_window_usage_holds_percent_and_reset():
    reset = datetime(2026, 6, 13, 18, 0, tzinfo=timezone.utc)
    w = WindowUsage(percent=42.5, resets_at=reset)
    assert w.percent == 42.5
    assert w.resets_at == reset


def test_snapshot_defaults_and_fields():
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    snap = UsageSnapshot(
        five_hour=WindowUsage(10.0, now),
        weekly=None,
        source="local",
        stale=False,
        error=None,
        fetched_at=now,
    )
    assert snap.source == "local"
    assert snap.weekly is None
    assert snap.five_hour.percent == 10.0
    assert snap.stale is False
