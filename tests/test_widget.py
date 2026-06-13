from datetime import datetime, timedelta, timezone

from widget import bar_color, fmt_countdown, next_delay, GREEN, AMBER, RED


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


def test_next_delay_resets_on_success():
    assert next_delay(stale=False, current=1200, base=300) == 300


def test_next_delay_doubles_on_failure():
    assert next_delay(stale=True, current=300, base=300) == 600
    assert next_delay(stale=True, current=600, base=300) == 1200


def test_next_delay_caps_at_max():
    assert next_delay(stale=True, current=1800, base=300, max_delay=1800) == 1800
    assert next_delay(stale=True, current=1500, base=300, max_delay=1800) == 1800
