from datetime import datetime, timezone, timedelta
from pathlib import Path

from sources import local

FIX = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def test_iter_usage_events_skips_non_usage_lines():
    events = list(local.iter_usage_events([FIX]))
    # 3 assistant lines have usage; user line and usage-less line skipped
    assert len(events) == 3
    for ts, tokens in events:
        assert ts.tzinfo is not None
        assert tokens > 0


def test_aggregate_window_sums_and_resets():
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    events = list(local.iter_usage_events([FIX]))
    total, resets_at = local.aggregate_window(events, now, timedelta(hours=5))
    # within 5h: 11:00 (1500) + 11:30 (3500) = 5000; 06-08 line excluded
    assert total == 5000
    # reset = oldest in-window event (11:00) + 5h
    assert resets_at == datetime(2026, 6, 13, 16, 0, tzinfo=timezone.utc)


def test_aggregate_window_empty_returns_none_reset():
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    events = list(local.iter_usage_events([FIX]))
    total, resets_at = local.aggregate_window(events, now, timedelta(hours=5))
    assert total == 0
    assert resets_at is None


def test_fetch_builds_snapshot_with_percent():
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    budgets = {"five_hour": 10000, "weekly": 20000}
    snap = local.fetch(now=now, budgets=budgets, paths=[FIX])
    assert snap.source == "local"
    assert snap.stale is False
    # five_hour: 5000/10000 = 50%
    assert abs(snap.five_hour.percent - 50.0) < 1e-6
    # weekly: 5000 + 4000(06-08) = 9000 / 20000 = 45%
    assert abs(snap.weekly.percent - 45.0) < 1e-6


def test_fetch_caps_percent_at_100():
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    snap = local.fetch(now=now, budgets={"five_hour": 100, "weekly": 100}, paths=[FIX])
    assert snap.five_hour.percent == 100.0
