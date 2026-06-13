import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from models import UsageSnapshot
from sources import live as live_source

log = logging.getLogger("usage_widget")


def _default_live() -> UsageSnapshot:
    return live_source.fetch()


class UsageProvider:
    """Live-only usage with a last-known-good (stale) fallback.

    The live /api/oauth/usage endpoint is the only accurate source. When a
    fetch fails (e.g. HTTP 429 rate limiting, an expired token, or being
    offline) the most recent successful snapshot is returned marked stale,
    rather than a fabricated estimate. Before any successful fetch, an empty
    snapshot (None windows) is returned so the UI can show a placeholder.
    """

    def __init__(self, live_fetch: Callable[[], UsageSnapshot] = _default_live):
        self._live = live_fetch
        self._last_good: Optional[UsageSnapshot] = None

    def get_snapshot(self) -> UsageSnapshot:
        try:
            snap = self._live()
            self._last_good = snap
            return snap
        except Exception as exc:  # noqa: BLE001 - we degrade, never crash
            log.warning("live source failed: %s", exc)
            if self._last_good is not None:
                lg = self._last_good
                return UsageSnapshot(
                    five_hour=lg.five_hour, weekly=lg.weekly, source=lg.source,
                    stale=True, error=str(exc), fetched_at=lg.fetched_at,
                )
            return UsageSnapshot(
                five_hour=None, weekly=None, source="none",
                stale=True, error=str(exc), fetched_at=datetime.now(timezone.utc),
            )
