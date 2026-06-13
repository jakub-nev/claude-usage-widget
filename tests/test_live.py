import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sources import live

FIX = json.loads(
    (Path(__file__).parent / "fixtures" / "sample_usage_response.json").read_text()
)


def test_parse_usage_response_normalizes_windows():
    snap = live.parse_usage(FIX, fetched_at=datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc))
    assert snap.source == "live"
    assert abs(snap.five_hour.percent - 37.5) < 1e-6
    assert snap.five_hour.resets_at == datetime(2026, 6, 13, 16, 0, tzinfo=timezone.utc)
    assert abs(snap.weekly.percent - 61.2) < 1e-6


def test_parse_treats_fraction_scale_as_percent():
    # if utilization comes as 0..1, it is scaled to 0..100
    data = {"five_hour": {"utilization": 0.42, "resets_at": "2026-06-13T16:00:00Z"},
            "seven_day": {"utilization": 0.10, "resets_at": "2026-06-18T09:00:00Z"}}
    snap = live.parse_usage(data, fetched_at=datetime(2026, 6, 13, tzinfo=timezone.utc))
    assert abs(snap.five_hour.percent - 42.0) < 1e-6
    assert abs(snap.weekly.percent - 10.0) < 1e-6


def test_fetch_uses_injected_token_and_http():
    captured = {}

    def fake_token():
        return "tok-123"

    def fake_get(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        return FIX

    snap = live.fetch(get_token=fake_token, http_get=fake_get,
                      now=datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc))
    assert snap.source == "live"
    assert captured["url"] == live.USAGE_URL
    assert captured["headers"]["Authorization"] == "Bearer tok-123"
    assert captured["headers"]["anthropic-beta"] == "oauth-2025-04-20"


def test_fetch_propagates_http_errors():
    def fake_token():
        return "tok"

    def boom(url, headers):
        raise live.LiveError("401 unauthorized")

    with pytest.raises(live.LiveError):
        live.fetch(get_token=fake_token, http_get=boom,
                   now=datetime(2026, 6, 13, tzinfo=timezone.utc))
