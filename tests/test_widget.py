from datetime import datetime, timedelta, timezone

from widget import bar_color, fmt_countdown, GREEN, AMBER, RED


def test_bar_color_thresholds():
    assert bar_color(0) == GREEN
    assert bar_color(59.9) == GREEN
    assert bar_color(60) == AMBER
    assert bar_color(84.9) == AMBER
    assert bar_color(85) == RED
    assert bar_color(100) == RED


def test_fmt_countdown_none_and_past():
    assert fmt_countdown(None) == "--"
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert fmt_countdown(past) == "resetting…"


def test_fmt_countdown_hours_and_minutes():
    now = datetime.now(timezone.utc)
    assert "h" in fmt_countdown(now + timedelta(hours=2, minutes=14))
    assert fmt_countdown(now + timedelta(minutes=45)).endswith("m")
