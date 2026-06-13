# Claude Usage Widget — Design

**Date:** 2026-06-13
**Status:** Approved (pending spec review)

## Goal

A Windows desktop widget that shows, at a glance, **how much of the Claude
usage limit has been consumed until the next reset** — mirroring what the
Claude Code `/usage` command displays (5-hour rolling window and weekly
window, each with a percentage and reset time).

Two visual modes ship in one app so the user can compare and choose:

1. **Floating widget** — small always-on-top panel on the desktop.
2. **Thin bar** — slim always-on-top strip pinned to a screen edge.

## Stack

- **Python 3.11 + tkinter** (already installed; tkinter ships with Python).
- **Standard library only** — `urllib` for HTTPS, `json`, `tkinter`. No pip
  dependencies, so the app runs by double-clicking with nothing to install.
- Optional later: package to a single `.exe` with PyInstaller.

## Where the data comes from

Claude Code's `/usage` is authenticated server-side: Claude Code sends the
user's OAuth token to Anthropic and renders the returned utilization. That
live percentage is **not stored locally** — verified by inspecting
`~/.claude/` (only `stats-cache.json` daily token totals and
`.credentials.json` auth material exist; session `.jsonl` logs carry raw
token counts but no rate-limit fields).

Therefore the widget uses two sources behind one interface:

- **Live (primary):** read the OAuth token from `~/.claude/.credentials.json`
  (`claudeAiOauth.accessToken`), refresh via `refreshToken` when expired, call
  the same usage endpoint `/usage` uses, parse the 5h + weekly utilization and
  reset timestamps. Produces the exact numbers `/usage` shows.
- **Local (fallback):** sum tokens from session `.jsonl` files (and/or
  `stats-cache.json`) within the rolling windows, divide by a user-calibrated
  budget to estimate a percentage. Fully offline, never breaks.

### Caveat (explicitly accepted)

The live endpoint is **internal/undocumented**, not a published public API. It
uses the user's own token for the user's own data (low risk), but a future
Claude Code update could change it. The exact endpoint URL/shape will be
**verified once during implementation** against the real local install. If it
cannot be confirmed reliably, the app ships with local-as-primary and keeps
live behind a flag. The live and local fetchers are isolated so only one file
changes if the endpoint moves.

## Architecture

Three cleanly separated layers.

### 1. Data layer — `usage_source.py`

Normalizes everything to a single dataclass:

```python
@dataclass
class WindowUsage:
    percent: float          # 0..100
    resets_at: datetime     # when this window resets

@dataclass
class UsageSnapshot:
    five_hour: WindowUsage | None
    weekly: WindowUsage | None
    source: str             # "live" | "local"
    stale: bool             # last fetch failed; values are last-known
    error: str | None       # short message for the status dot / log
    fetched_at: datetime
```

`get_snapshot()` tries **live → local** and returns the first success,
tagging `source` accordingly. Live and local live in separate modules
(`sources/live.py`, `sources/local.py`) behind a common `fetch()` signature.

- `sources/live.py`: token read + refresh + HTTPS call + parse.
- `sources/local.py`: rolling-window token aggregation + budget→percent.

### 2. UI layer — `widget.py` (tkinter)

Frameless (`overrideredirect`), always-on-top (`-topmost`), draggable by
click-drag on the body. Two modes in the same window:

- **Floating widget:** rounded panel showing both windows as labeled progress
  bars with `%`, a reset countdown (`resets in 2h 14m`), and a small source
  dot (`live` = green, `approx` = amber, `stale` = grey).
- **Thin bar:** slim strip showing the featured window's `%` + mini countdown.

**Right-click context menu:** switch mode · recalibrate budget · choose
featured window (5h vs weekly) · quit.

Polling: a background thread calls `get_snapshot()` every ~60s (configurable)
and marshals results to the Tk main thread via `after()`. The UI thread never
blocks on I/O.

### 3. Config + entry point

- `config.json`: window position, mode, poll interval seconds, calibration
  budgets (per window), featured window.
- Entry: `python widget.py`. A generated `run.bat` and an optional Startup-
  folder shortcut allow auto-launch on login.

## Data flow

```
timer (~60s, bg thread)
  -> usage_source.get_snapshot()
       -> sources/live.fetch()   (token read/refresh, HTTPS, parse)
            on failure ->
       -> sources/local.fetch()  (jsonl/stats aggregation, budget %)
  -> marshal to Tk main thread (after())
  -> update bars / labels / countdown / source dot
```

## Error handling

- **Token expired:** auto-refresh via `refreshToken`. If refresh fails → local
  fallback + `approx` dot. Never prompts for login, never crashes.
- **Endpoint changed / network down:** local fallback. If that also fails →
  keep last-known values, dim them, show `stale` dot + "updated Xm ago".
- **No local data / first run:** show `--%` placeholder and prompt to
  calibrate.
- All fetching is off the UI thread; exceptions are caught, appended to
  `widget.log`, and surfaced as the status dot. The window stays alive.

## Testing

- **Unit tests (pytest):**
  - rolling-window token aggregation (window boundaries, midnight/weekly
    reset edges),
  - budget → percent calculation,
  - `UsageSnapshot` normalization,
  - live→local fallback decision (live HTTP mocked, token refresh mocked).
  - Fixtures: a couple of trimmed `.jsonl` samples + a sample credentials blob.
- **Manual UI check:** launch both modes; verify always-on-top, dragging, mode
  switch, ticking countdown, and source/stale dots under forced failures.
- **Endpoint verification:** confirm the live usage endpoint once against the
  real install during implementation.

## Out of scope (YAGNI)

- System-tray icon (user chose floating + thin-bar modes only).
- Cost/$ estimates, per-project breakdowns, historical charts.
- Multi-account support.
- Anything touching the Anthropic developer/billing API (this is Claude Code
  subscription usage only).

## File layout

```
usage/
  widget.py              # tkinter UI, entry point
  usage_source.py        # get_snapshot(), UsageSnapshot dataclass
  sources/
    live.py              # OAuth read/refresh + usage endpoint
    local.py             # jsonl/stats aggregation + budget %
  config.json            # created on first run
  run.bat                # convenience launcher
  tests/
    test_local.py
    test_snapshot.py
    fixtures/
  widget.log             # runtime log (gitignored)
  docs/superpowers/specs/2026-06-13-claude-usage-widget-design.md
```
