from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class WindowUsage:
    """One rate-limit window: percent used (0..100) and when it resets."""
    percent: float
    resets_at: Optional[datetime]


@dataclass
class UsageSnapshot:
    """Normalized usage from whichever source succeeded."""
    five_hour: Optional[WindowUsage]
    weekly: Optional[WindowUsage]
    source: str            # "live" | "local"
    stale: bool            # True if this is last-known data after a failure
    error: Optional[str]   # short message for the status dot / log
    fetched_at: datetime
