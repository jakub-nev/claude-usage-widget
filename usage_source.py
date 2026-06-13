import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from models import UsageSnapshot
from sources import live as live_source
from sources import local as local_source

log = logging.getLogger("usage_widget")


def _default_live() -> UsageSnapshot:
    return live_source.fetch()


def _make_default_local(budgets: dict) -> Callable[[], UsageSnapshot]:
    def _fetch() -> UsageSnapshot:
        return local_source.fetch(budgets=budgets)
    return _fetch


class UsageProvider:
    """Tries live then local; retains last-known snapshot for stale display."""

    def __init__(self,
                 live_fetch: Callable[[], UsageSnapshot] = _default_live,
                 local_fetch: Optional[Callable[[], UsageSnapshot]] = None,
                 budgets: Optional[dict] = None):
        self._live = live_fetch
        self._local = local_fetch or _make_default_local(budgets or {})
        self._last_good: Optional[UsageSnapshot] = None

    def get_snapshot(self) -> UsageSnapshot:
        errors = []
        for name, fetch in (("live", self._live), ("local", self._local)):
            try:
                snap = fetch()
                self._last_good = snap
                return snap
            except Exception as exc:  # noqa: BLE001 - we degrade, never crash
                log.warning("%s source failed: %s", name, exc)
                errors.append(f"{name}: {exc}")

        msg = "; ".join(errors)
        if self._last_good is not None:
            lg = self._last_good
            return UsageSnapshot(
                five_hour=lg.five_hour, weekly=lg.weekly, source=lg.source,
                stale=True, error=msg, fetched_at=lg.fetched_at,
            )
        return UsageSnapshot(
            five_hour=None, weekly=None, source="none",
            stale=True, error=msg, fetched_at=datetime.now(timezone.utc),
        )
