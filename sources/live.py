import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Callable, Optional

from models import WindowUsage, UsageSnapshot
from sources import auth

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
BETA_HEADER = "oauth-2025-04-20"


class LiveError(Exception):
    pass


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _window(block: Optional[dict]) -> Optional[WindowUsage]:
    if not isinstance(block, dict):
        return None
    raw = block.get("utilization")
    if raw is None:
        return None
    pct = float(raw)
    if pct <= 1.0:          # 0..1 fraction -> percent
        pct *= 100.0
    return WindowUsage(percent=pct, resets_at=_parse_ts(block.get("resets_at")))


def parse_usage(data: dict, fetched_at: datetime) -> UsageSnapshot:
    return UsageSnapshot(
        five_hour=_window(data.get("five_hour")),
        weekly=_window(data.get("seven_day") or data.get("weekly")),
        source="live",
        stale=False,
        error=None,
        fetched_at=fetched_at,
    )


def http_get_json(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise LiveError(f"usage request failed: {exc}") from exc


def fetch(get_token: Callable[[], str] = auth.get_access_token,
          http_get: Callable[[str, dict], dict] = http_get_json,
          now: Optional[datetime] = None) -> UsageSnapshot:
    now = now or datetime.now(timezone.utc)
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": BETA_HEADER,
        "Content-Type": "application/json",
    }
    data = http_get(USAGE_URL, headers)
    return parse_usage(data, fetched_at=now)
