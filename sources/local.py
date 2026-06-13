import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional

from models import WindowUsage, UsageSnapshot

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
FIVE_HOURS = timedelta(hours=5)
SEVEN_DAYS = timedelta(days=7)

_TOKEN_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _parse_ts(value: str) -> datetime:
    # ISO-8601 with trailing Z
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def discover_log_paths(root: Path = CLAUDE_PROJECTS) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("*.jsonl"))


def iter_usage_events(paths: Iterable[Path]) -> Iterator[tuple[datetime, int]]:
    """Yield (timestamp, total_tokens) for each assistant line carrying usage."""
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") != "assistant":
                        continue
                    usage = (obj.get("message") or {}).get("usage")
                    ts = obj.get("timestamp")
                    if not isinstance(usage, dict) or not ts:
                        continue
                    total = sum(int(usage.get(k, 0) or 0) for k in _TOKEN_KEYS)
                    if total <= 0:
                        continue
                    yield _parse_ts(ts), total
        except OSError:
            continue


def aggregate_window(
    events: list[tuple[datetime, int]],
    now: datetime,
    window: timedelta,
) -> tuple[int, Optional[datetime]]:
    cutoff = now - window
    in_window = [(ts, tok) for ts, tok in events if ts >= cutoff]
    if not in_window:
        return 0, None
    total = sum(tok for _, tok in in_window)
    oldest = min(ts for ts, _ in in_window)
    return total, oldest + window


def _percent(total: int, budget: float) -> float:
    if not budget or budget <= 0:
        return 0.0
    return min(100.0, total / budget * 100.0)


def fetch(now: Optional[datetime] = None,
          budgets: Optional[dict] = None,
          paths: Optional[Iterable[Path]] = None) -> UsageSnapshot:
    now = now or datetime.now(timezone.utc)
    budgets = budgets or {"five_hour": 5_000_000, "weekly": 50_000_000}
    if paths is None:
        paths = discover_log_paths()
    events = list(iter_usage_events(paths))

    fh_total, fh_reset = aggregate_window(events, now, FIVE_HOURS)
    wk_total, wk_reset = aggregate_window(events, now, SEVEN_DAYS)

    return UsageSnapshot(
        five_hour=WindowUsage(_percent(fh_total, budgets.get("five_hour", 0)), fh_reset),
        weekly=WindowUsage(_percent(wk_total, budgets.get("weekly", 0)), wk_reset),
        source="local",
        stale=False,
        error=None,
        fetched_at=now,
    )
