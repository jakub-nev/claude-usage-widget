# Claude Usage Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Windows always-on-top desktop widget (floating panel + thin-bar mode) that shows the percentage of the Claude subscription usage limit consumed until the next reset, mirroring Claude Code's `/usage`.

**Architecture:** Three layers — a data layer (`usage_source.py`) that returns a normalized `UsageSnapshot` by trying a **live** source (Anthropic OAuth usage endpoint) then a **local** fallback (token aggregation from `~/.claude` logs); a tkinter UI layer (`widget.py`) with two switchable modes; and a small JSON config. Live and local fetchers are isolated modules behind a common `fetch()` signature so endpoint changes touch one file only.

**Tech Stack:** Python 3.11, tkinter (stdlib), `urllib`/`json`/`http` (stdlib). No pip dependencies. pytest for tests (dev-only).

**Verified facts (from the installed Claude Code binary, 2026-06-13):**
- Usage endpoint: `GET https://api.anthropic.com/api/oauth/usage`
  - Headers: `Authorization: Bearer <accessToken>`, `anthropic-beta: oauth-2025-04-20`, `Content-Type: application/json`
  - Response JSON contains objects `five_hour` and `seven_day`, each with `utilization` (number) and `resets_at` (ISO-8601 string). Treat `weekly` as an alias of `seven_day`.
- Token refresh: `POST https://platform.claude.com/v1/oauth/token`
  - Body JSON: `{"grant_type":"refresh_token","refresh_token":<refreshToken>,"client_id":"9d1c250a-e61b-44d9-88ed-5944d1962f5e"}`
  - Response JSON: `{"access_token":...,"refresh_token":...,"expires_in":<seconds>}`
- Credentials file: `~/.claude/.credentials.json` → key `claudeAiOauth` → `{accessToken, refreshToken, expiresAt (epoch ms), subscriptionType, scopes}`
- Session logs: `~/.claude/projects/**/*.jsonl`, one JSON object per line. Assistant lines look like `{"type":"assistant","timestamp":"2026-06-11T23:10:42.219Z","message":{"model":"...","usage":{"input_tokens":..,"output_tokens":..,"cache_creation_input_tokens":..,"cache_read_input_tokens":..}}}`.

> **Implementation note on the live response shape:** the exact numeric scale of `utilization` (0–1 vs 0–100) is confirmed empirically in Task 5, Step 1 (a one-time manual probe that prints the raw JSON). The parser in Task 6 normalizes to 0–100 based on that observation; the plan codes it defensively (values ≤ 1 are treated as a fraction and multiplied by 100).

---

## File Structure

```
usage/
  widget.py              # tkinter UI + entry point (Tasks 8-11)
  usage_source.py        # get_snapshot() orchestration + fallback (Task 7)
  models.py              # WindowUsage, UsageSnapshot dataclasses (Task 2)
  config.py              # load/save config.json, defaults (Task 3)
  sources/
    __init__.py
    local.py             # log aggregation + budget->percent (Task 4)
    auth.py              # credentials read + token refresh (Task 5)
    live.py              # /api/oauth/usage call + parse (Task 6)
  tests/
    __init__.py
    fixtures/
      sample_session.jsonl
      sample_credentials.json
      sample_usage_response.json
    test_models.py
    test_local.py
    test_config.py
    test_auth.py
    test_live.py
    test_usage_source.py
  run.bat                # convenience launcher (Task 12)
  README.md              # how to run / autostart (Task 12)
  .gitignore
  requirements-dev.txt   # pytest only
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `E:/Documents/usage/.gitignore`
- Create: `E:/Documents/usage/requirements-dev.txt`
- Create: `E:/Documents/usage/sources/__init__.py` (empty)
- Create: `E:/Documents/usage/tests/__init__.py` (empty)

- [ ] **Step 1: Initialize git**

Run:
```bash
cd E:/Documents/usage && git init && git add docs && git commit -m "docs: add design spec and implementation plan"
```
Expected: a commit is created containing the `docs/` tree.

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
config.json
widget.log
.credentials*.json
```

- [ ] **Step 3: Create `requirements-dev.txt`**

```
pytest>=8.0
```

- [ ] **Step 4: Create empty package files**

Create `sources/__init__.py` and `tests/__init__.py`, both empty files.

- [ ] **Step 5: Verify pytest runs (no tests yet)**

Run: `cd E:/Documents/usage && python -m pytest -q`
Expected: "no tests ran" (exit code 5) — confirms pytest is importable. If pytest is missing, run `python -m pip install pytest` first.

- [ ] **Step 6: Commit**

```bash
cd E:/Documents/usage && git add .gitignore requirements-dev.txt sources tests && git commit -m "chore: scaffold project structure"
```

---

## Task 2: Data model (`models.py`)

**Files:**
- Create: `E:/Documents/usage/models.py`
- Test: `E:/Documents/usage/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
from datetime import datetime, timezone
from models import WindowUsage, UsageSnapshot


def test_window_usage_holds_percent_and_reset():
    reset = datetime(2026, 6, 13, 18, 0, tzinfo=timezone.utc)
    w = WindowUsage(percent=42.5, resets_at=reset)
    assert w.percent == 42.5
    assert w.resets_at == reset


def test_snapshot_defaults_and_fields():
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    snap = UsageSnapshot(
        five_hour=WindowUsage(10.0, now),
        weekly=None,
        source="local",
        stale=False,
        error=None,
        fetched_at=now,
    )
    assert snap.source == "local"
    assert snap.weekly is None
    assert snap.five_hour.percent == 10.0
    assert snap.stale is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:/Documents/usage && python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'models'`.

- [ ] **Step 3: Write minimal implementation**

`models.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd E:/Documents/usage && python -m pytest tests/test_models.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd E:/Documents/usage && git add models.py tests/test_models.py && git commit -m "feat: add UsageSnapshot data model"
```

---

## Task 3: Config (`config.py`)

**Files:**
- Create: `E:/Documents/usage/config.py`
- Test: `E:/Documents/usage/tests/test_config.py`

Config holds UI state and the local-fallback calibration budgets.

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
import json
from config import Config, load_config, save_config, DEFAULTS


def test_defaults_have_required_keys():
    for key in ("mode", "featured", "poll_seconds", "budgets", "pos_x", "pos_y"):
        assert key in DEFAULTS
    assert DEFAULTS["mode"] in ("floating", "bar")
    assert DEFAULTS["featured"] in ("five_hour", "weekly")


def test_load_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "config.json")
    assert cfg.mode == DEFAULTS["mode"]
    assert cfg.budgets["five_hour"] == DEFAULTS["budgets"]["five_hour"]


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    cfg = load_config(path)
    cfg.mode = "bar"
    cfg.budgets["weekly"] = 12345
    save_config(cfg, path)
    reloaded = load_config(path)
    assert reloaded.mode == "bar"
    assert reloaded.budgets["weekly"] == 12345


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"mode": "bar", "junk": 1}))
    cfg = load_config(path)
    assert cfg.mode == "bar"
    assert cfg.poll_seconds == DEFAULTS["poll_seconds"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:/Documents/usage && python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config'`.

- [ ] **Step 3: Write minimal implementation**

`config.py`:
```python
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

DEFAULTS = {
    "mode": "floating",        # "floating" | "bar"
    "featured": "five_hour",   # which window the bar mode shows
    "poll_seconds": 60,
    "budgets": {               # local-fallback token budgets per window
        "five_hour": 5_000_000,
        "weekly": 50_000_000,
    },
    "pos_x": 80,
    "pos_y": 80,
}


@dataclass
class Config:
    mode: str = DEFAULTS["mode"]
    featured: str = DEFAULTS["featured"]
    poll_seconds: int = DEFAULTS["poll_seconds"]
    budgets: dict = field(default_factory=lambda: dict(DEFAULTS["budgets"]))
    pos_x: int = DEFAULTS["pos_x"]
    pos_y: int = DEFAULTS["pos_y"]


def load_config(path) -> Config:
    path = Path(path)
    cfg = Config()
    if not path.exists():
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return cfg
    if isinstance(data.get("mode"), str):
        cfg.mode = data["mode"]
    if isinstance(data.get("featured"), str):
        cfg.featured = data["featured"]
    if isinstance(data.get("poll_seconds"), int):
        cfg.poll_seconds = data["poll_seconds"]
    if isinstance(data.get("budgets"), dict):
        cfg.budgets.update({k: v for k, v in data["budgets"].items()
                            if isinstance(v, (int, float))})
    if isinstance(data.get("pos_x"), int):
        cfg.pos_x = data["pos_x"]
    if isinstance(data.get("pos_y"), int):
        cfg.pos_y = data["pos_y"]
    return cfg


def save_config(cfg: Config, path) -> None:
    Path(path).write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd E:/Documents/usage && python -m pytest tests/test_config.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd E:/Documents/usage && git add config.py tests/test_config.py && git commit -m "feat: add config load/save with defaults"
```

---

## Task 4: Local source (`sources/local.py`)

**Files:**
- Create: `E:/Documents/usage/sources/local.py`
- Create: `E:/Documents/usage/tests/fixtures/sample_session.jsonl`
- Test: `E:/Documents/usage/tests/test_local.py`

Computes percentage by summing tokens in each rolling window and dividing by the configured budget.

- [ ] **Step 1: Create the fixture**

`tests/fixtures/sample_session.jsonl` (exact content — timestamps are relative-friendly fixed values; tests inject `now`):
```
{"type":"assistant","timestamp":"2026-06-13T11:00:00.000Z","message":{"model":"claude-opus-4-8","usage":{"input_tokens":1000,"output_tokens":500,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}}}
{"type":"assistant","timestamp":"2026-06-13T11:30:00.000Z","message":{"model":"claude-opus-4-8","usage":{"input_tokens":2000,"output_tokens":500,"cache_creation_input_tokens":1000,"cache_read_input_tokens":0}}}
{"type":"user","timestamp":"2026-06-13T11:31:00.000Z","message":{"role":"user","content":"hi"}}
{"type":"assistant","timestamp":"2026-06-08T09:00:00.000Z","message":{"model":"claude-sonnet-4-6","usage":{"input_tokens":4000,"output_tokens":0,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}}}
{"type":"assistant","timestamp":"2026-06-13T11:45:00.000Z","message":{"model":"claude-opus-4-8"}}
```
(Line 3 is a user line with no usage; line 5 is an assistant line missing `usage`. Both must be skipped.)

- [ ] **Step 2: Write the failing test**

`tests/test_local.py`:
```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd E:/Documents/usage && python -m pytest tests/test_local.py -v`
Expected: FAIL — `ImportError`/`AttributeError` (module/functions don't exist).

- [ ] **Step 4: Write minimal implementation**

`sources/local.py`:
```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd E:/Documents/usage && python -m pytest tests/test_local.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
cd E:/Documents/usage && git add sources/local.py tests/test_local.py tests/fixtures/sample_session.jsonl && git commit -m "feat: add local token-aggregation source"
```

---

## Task 5: Auth (`sources/auth.py`)

**Files:**
- Create: `E:/Documents/usage/sources/auth.py`
- Create: `E:/Documents/usage/tests/fixtures/sample_credentials.json`
- Test: `E:/Documents/usage/tests/test_auth.py`

Reads the OAuth token from `~/.claude/.credentials.json` and refreshes it when expired. The HTTP call is injected so it can be mocked.

- [ ] **Step 1: (Manual, one-time) Probe the real usage endpoint to confirm response shape**

This is a manual verification, not committed code. Run this throwaway snippet to see the live JSON (requires a valid, unexpired token in `.credentials.json`):
```bash
cd E:/Documents/usage && python -c "
import json, urllib.request
from pathlib import Path
c = json.loads((Path.home()/'.claude'/'.credentials.json').read_text())['claudeAiOauth']
req = urllib.request.Request('https://api.anthropic.com/api/oauth/usage',
    headers={'Authorization':'Bearer '+c['accessToken'],
             'anthropic-beta':'oauth-2025-04-20',
             'Content-Type':'application/json'})
print(urllib.request.urlopen(req, timeout=15).read().decode())
"
```
Expected: JSON containing `five_hour` and `seven_day` objects. **Record** whether `utilization` is on a 0–1 or 0–100 scale and the exact key names; save the printed body to `tests/fixtures/sample_usage_response.json` (used by Task 6). If the token is expired you'll get HTTP 401 — that's fine, proceed; Task 5 builds refresh and you can re-run afterward.

- [ ] **Step 2: Create the credentials fixture**

`tests/fixtures/sample_credentials.json`:
```json
{
  "claudeAiOauth": {
    "accessToken": "fake-access-token",
    "refreshToken": "fake-refresh-token",
    "expiresAt": 1781035661204,
    "subscriptionType": "max",
    "scopes": ["user:inference"]
  }
}
```

- [ ] **Step 3: Write the failing test**

`tests/test_auth.py`:
```python
import json
from pathlib import Path

import pytest

from sources import auth

FIX = Path(__file__).parent / "fixtures" / "sample_credentials.json"


def test_read_credentials_returns_oauth_block():
    creds = auth.read_credentials(FIX)
    assert creds["accessToken"] == "fake-access-token"
    assert creds["refreshToken"] == "fake-refresh-token"


def test_token_valid_when_not_expired():
    # expiresAt far in the future
    creds = {"accessToken": "tok", "refreshToken": "r", "expiresAt": 9_999_999_999_000}
    assert auth.is_expired(creds, now_ms=1_000_000_000_000) is False


def test_token_expired_when_past():
    creds = {"accessToken": "tok", "refreshToken": "r", "expiresAt": 1_000}
    assert auth.is_expired(creds, now_ms=2_000) is True


def test_get_access_token_returns_existing_when_valid(tmp_path):
    path = tmp_path / ".credentials.json"
    path.write_text(json.dumps({"claudeAiOauth": {
        "accessToken": "good", "refreshToken": "r", "expiresAt": 9_999_999_999_000}}))

    def fail_refresh(_):
        raise AssertionError("refresh should not be called")

    tok = auth.get_access_token(path, now_ms=1_000, refresh_http=fail_refresh)
    assert tok == "good"


def test_get_access_token_refreshes_when_expired(tmp_path):
    path = tmp_path / ".credentials.json"
    path.write_text(json.dumps({"claudeAiOauth": {
        "accessToken": "old", "refreshToken": "r1", "expiresAt": 1_000}}))

    def fake_refresh(refresh_token):
        assert refresh_token == "r1"
        return {"access_token": "new", "refresh_token": "r2", "expires_in": 3600}

    tok = auth.get_access_token(path, now_ms=2_000, refresh_http=fake_refresh)
    assert tok == "new"
    # file updated with new tokens
    saved = json.loads(path.read_text())["claudeAiOauth"]
    assert saved["accessToken"] == "new"
    assert saved["refreshToken"] == "r2"
    assert saved["expiresAt"] > 2_000


def test_get_access_token_raises_when_refresh_fails(tmp_path):
    path = tmp_path / ".credentials.json"
    path.write_text(json.dumps({"claudeAiOauth": {
        "accessToken": "old", "refreshToken": "r1", "expiresAt": 1_000}}))

    def broken_refresh(_):
        raise auth.AuthError("network down")

    with pytest.raises(auth.AuthError):
        auth.get_access_token(path, now_ms=2_000, refresh_http=broken_refresh)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd E:/Documents/usage && python -m pytest tests/test_auth.py -v`
Expected: FAIL — module/attributes missing.

- [ ] **Step 5: Write minimal implementation**

`sources/auth.py`:
```python
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Callable, Optional

CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"


class AuthError(Exception):
    pass


def read_credentials(path=CREDENTIALS_PATH) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    oauth = data.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        raise AuthError("no claudeAiOauth block in credentials")
    return oauth


def is_expired(creds: dict, now_ms: Optional[int] = None) -> bool:
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    expires_at = int(creds.get("expiresAt", 0))
    # treat as expired 60s early to avoid races
    return now_ms >= (expires_at - 60_000)


def refresh_via_http(refresh_token: str) -> dict:
    """POST to the OAuth token endpoint. Returns the parsed token response."""
    body = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise AuthError(f"token refresh failed: {exc}") from exc


def get_access_token(
    path=CREDENTIALS_PATH,
    now_ms: Optional[int] = None,
    refresh_http: Callable[[str], dict] = refresh_via_http,
) -> str:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    creds = data.get("claudeAiOauth") or {}
    if not is_expired(creds, now_ms):
        return creds["accessToken"]

    token_resp = refresh_http(creds["refreshToken"])  # may raise AuthError
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    creds["accessToken"] = token_resp["access_token"]
    if token_resp.get("refresh_token"):
        creds["refreshToken"] = token_resp["refresh_token"]
    creds["expiresAt"] = now_ms + int(token_resp.get("expires_in", 3600)) * 1000
    data["claudeAiOauth"] = creds
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return creds["accessToken"]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd E:/Documents/usage && python -m pytest tests/test_auth.py -v`
Expected: PASS (6 passed).

- [ ] **Step 7: Commit**

```bash
cd E:/Documents/usage && git add sources/auth.py tests/test_auth.py tests/fixtures/sample_credentials.json && git commit -m "feat: add OAuth credential read + token refresh"
```

---

## Task 6: Live source (`sources/live.py`)

**Files:**
- Create: `E:/Documents/usage/sources/live.py`
- Create: `E:/Documents/usage/tests/fixtures/sample_usage_response.json`
- Test: `E:/Documents/usage/tests/test_live.py`

Calls `/api/oauth/usage` and parses the response into a `UsageSnapshot`. The HTTP getter is injected for testing.

- [ ] **Step 1: Create the response fixture**

`tests/fixtures/sample_usage_response.json` (if Task 5 Step 1 captured a real body, use that instead — keep the same two keys):
```json
{
  "five_hour": {"utilization": 37.5, "resets_at": "2026-06-13T16:00:00Z"},
  "seven_day": {"utilization": 61.2, "resets_at": "2026-06-18T09:00:00Z"}
}
```

- [ ] **Step 2: Write the failing test**

`tests/test_live.py`:
```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd E:/Documents/usage && python -m pytest tests/test_live.py -v`
Expected: FAIL — module/attributes missing.

- [ ] **Step 4: Write minimal implementation**

`sources/live.py`:
```python
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
```

> Note: `auth.get_access_token` has parameters with defaults, so passing it as the zero-arg `get_token` default works (it reads the default credentials path). The orchestrator in Task 7 wraps it if needed.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd E:/Documents/usage && python -m pytest tests/test_live.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
cd E:/Documents/usage && git add sources/live.py tests/test_live.py tests/fixtures/sample_usage_response.json && git commit -m "feat: add live /api/oauth/usage source"
```

---

## Task 7: Orchestration (`usage_source.py`)

**Files:**
- Create: `E:/Documents/usage/usage_source.py`
- Test: `E:/Documents/usage/tests/test_usage_source.py`

Tries live, falls back to local; tracks last-known snapshot for `stale` handling.

- [ ] **Step 1: Write the failing test**

`tests/test_usage_source.py`:
```python
from datetime import datetime, timezone

from models import WindowUsage, UsageSnapshot
from usage_source import UsageProvider


def _snap(source, pct):
    now = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    return UsageSnapshot(
        five_hour=WindowUsage(pct, now), weekly=WindowUsage(pct, now),
        source=source, stale=False, error=None, fetched_at=now,
    )


def test_uses_live_when_available():
    prov = UsageProvider(
        live_fetch=lambda: _snap("live", 30.0),
        local_fetch=lambda: _snap("local", 99.0),
    )
    snap = prov.get_snapshot()
    assert snap.source == "live"
    assert snap.five_hour.percent == 30.0


def test_falls_back_to_local_on_live_error():
    def boom():
        raise RuntimeError("live down")

    prov = UsageProvider(
        live_fetch=boom,
        local_fetch=lambda: _snap("local", 55.0),
    )
    snap = prov.get_snapshot()
    assert snap.source == "local"
    assert snap.five_hour.percent == 55.0


def test_returns_stale_last_known_when_all_fail():
    calls = {"n": 0}

    def live_ok_then_fail():
        calls["n"] += 1
        if calls["n"] == 1:
            return _snap("live", 20.0)
        raise RuntimeError("down")

    def local_fail():
        raise RuntimeError("no logs")

    prov = UsageProvider(live_fetch=live_ok_then_fail, local_fetch=local_fail)
    first = prov.get_snapshot()
    assert first.stale is False and first.source == "live"

    second = prov.get_snapshot()
    assert second.stale is True
    assert second.five_hour.percent == 20.0          # last-known values retained
    assert second.error is not None


def test_first_call_total_failure_returns_error_snapshot():
    def fail():
        raise RuntimeError("nope")

    prov = UsageProvider(live_fetch=fail, local_fetch=fail)
    snap = prov.get_snapshot()
    assert snap.stale is True
    assert snap.five_hour is None
    assert snap.error is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd E:/Documents/usage && python -m pytest tests/test_usage_source.py -v`
Expected: FAIL — `ModuleNotFoundError`/`ImportError`.

- [ ] **Step 3: Write minimal implementation**

`usage_source.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd E:/Documents/usage && python -m pytest tests/test_usage_source.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the full suite**

Run: `cd E:/Documents/usage && python -m pytest -q`
Expected: all tests pass (models, config, local, auth, live, usage_source).

- [ ] **Step 6: Commit**

```bash
cd E:/Documents/usage && git add usage_source.py tests/test_usage_source.py && git commit -m "feat: add live->local fallback orchestration"
```

---

## Task 8: UI skeleton — floating mode (`widget.py`)

**Files:**
- Create: `E:/Documents/usage/widget.py`

tkinter is GUI; this and the next tasks are verified manually. Each step is small and ends with a visual check.

- [ ] **Step 1: Frameless always-on-top window with a render function**

`widget.py`:
```python
import logging
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path

from config import load_config, save_config
from models import UsageSnapshot

CONFIG_PATH = Path(__file__).with_name("config.json")
LOG_PATH = Path(__file__).with_name("widget.log")

logging.basicConfig(filename=LOG_PATH, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

BG = "#1e1e2e"
FG = "#cdd6f4"
DIM = "#6c7086"
DOT = {"live": "#a6e3a1", "local": "#f9e2af", "none": "#f38ba8"}


def fmt_countdown(resets_at):
    if resets_at is None:
        return "--"
    delta = resets_at - datetime.now(timezone.utc)
    secs = int(delta.total_seconds())
    if secs <= 0:
        return "resetting…"
    h, rem = divmod(secs, 3600)
    m = rem // 60
    return f"{h}h {m}m" if h else f"{m}m"


class Widget:
    def __init__(self, root: tk.Tk, cfg):
        self.root = root
        self.cfg = cfg
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=BG)
        root.geometry(f"+{cfg.pos_x}+{cfg.pos_y}")
        self._build_floating()
        self._bind_drag()

    def _build_floating(self):
        self.frame = tk.Frame(self.root, bg=BG, padx=12, pady=10)
        self.frame.pack()
        tk.Label(self.frame, text="Claude usage", bg=BG, fg=DIM,
                 font=("Segoe UI", 8)).pack(anchor="w")
        self.fh_label = tk.Label(self.frame, text="5h  --%", bg=BG, fg=FG,
                                 font=("Segoe UI", 13, "bold"))
        self.fh_label.pack(anchor="w")
        self.wk_label = tk.Label(self.frame, text="7d  --%", bg=BG, fg=FG,
                                 font=("Segoe UI", 13, "bold"))
        self.wk_label.pack(anchor="w")
        self.status = tk.Label(self.frame, text="●", bg=BG, fg=DOT["none"],
                               font=("Segoe UI", 8))
        self.status.pack(anchor="w")

    def render(self, snap: UsageSnapshot):
        def line(prefix, w):
            if w is None:
                return f"{prefix}  --%"
            return f"{prefix}  {w.percent:.0f}%  ({fmt_countdown(w.resets_at)})"
        self.fh_label.config(text=line("5h", snap.five_hour))
        self.wk_label.config(text=line("7d", snap.weekly))
        color = DOT.get(snap.source, DOT["none"])
        self.status.config(fg=(DIM if snap.stale else color))

    def _bind_drag(self):
        self._drag = (0, 0)
        for w in (self.root, self.frame):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

    def _start_drag(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _on_drag(self, e):
        x = e.x_root - self._drag[0]
        y = e.y_root - self._drag[1]
        self.root.geometry(f"+{x}+{y}")
        self.cfg.pos_x, self.cfg.pos_y = x, y


def main():
    cfg = load_config(CONFIG_PATH)
    root = tk.Tk()
    widget = Widget(root, cfg)
    # temporary sample render so we can see layout before wiring data
    from models import WindowUsage
    now = datetime.now(timezone.utc)
    widget.render(UsageSnapshot(
        five_hour=WindowUsage(37.0, now), weekly=WindowUsage(61.0, now),
        source="live", stale=False, error=None, fetched_at=now))

    def on_close():
        save_config(cfg, CONFIG_PATH)
        root.destroy()
    root.bind("<Escape>", lambda e: on_close())
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manual visual check**

Run: `cd E:/Documents/usage && python widget.py`
Expected: a small dark always-on-top panel showing `5h 37%` / `7d 61%` and a green dot. Drag it with the mouse; press `Esc` to close. Re-launch and confirm it reopens at the dragged position (position persisted to `config.json`).

- [ ] **Step 3: Commit**

```bash
cd E:/Documents/usage && git add widget.py && git commit -m "feat: floating widget UI skeleton with drag + persistence"
```

---

## Task 9: Live data polling on a background thread

**Files:**
- Modify: `E:/Documents/usage/widget.py`

- [ ] **Step 1: Add a poller that updates the UI via `after()`**

In `widget.py`, add imports at top:
```python
import threading
from usage_source import UsageProvider
```

Replace the temporary sample render block in `main()` with real polling. Replace the body of `main()` from the `widget = Widget(...)` line through `root.mainloop()` with:
```python
    widget = Widget(root, cfg)
    provider = UsageProvider(budgets=cfg.budgets)
    stop = threading.Event()

    def poll_loop():
        while not stop.is_set():
            try:
                snap = provider.get_snapshot()
                root.after(0, widget.render, snap)
            except Exception:                      # never let the thread die
                logging.exception("poll loop error")
            stop.wait(cfg.poll_seconds)

    threading.Thread(target=poll_loop, daemon=True).start()

    def tick():                                    # refresh countdown every 30s
        widget.refresh_countdown()
        root.after(30_000, tick)
    root.after(30_000, tick)

    def on_close():
        stop.set()
        save_config(cfg, CONFIG_PATH)
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.bind("<Escape>", lambda e: on_close())
    root.mainloop()
```

- [ ] **Step 2: Add countdown refresh + last-snapshot caching to `Widget`**

In `Widget.__init__`, add `self._last_snap = None` at the end. In `render()`, add `self._last_snap = snap` as the first line. Add this method to `Widget`:
```python
    def refresh_countdown(self):
        if self._last_snap is not None:
            self.render(self._last_snap)
```

- [ ] **Step 3: Manual check with real data**

Run: `cd E:/Documents/usage && python widget.py`
Expected: within a second or two the panel shows your real `5h`/`7d` percentages. Dot is green (`live`) if the token worked, amber (`local`) if it fell back. Cross-check the numbers against Claude Code's `/usage`. Leave it open ~1 minute to confirm it refreshes without flicker or crash.

- [ ] **Step 4: Force-fallback check**

Temporarily rename `~/.claude/.credentials.json` to `.credentials.bak`, relaunch: the dot should be amber (`local`) and percentages still render from logs. Restore the file afterward.

- [ ] **Step 5: Commit**

```bash
cd E:/Documents/usage && git add widget.py && git commit -m "feat: background polling + live data wiring"
```

---

## Task 10: Thin-bar mode + right-click menu

**Files:**
- Modify: `E:/Documents/usage/widget.py`

- [ ] **Step 1: Build both layouts and a mode switch**

Refactor `Widget` so it can render either layout. Replace `_build_floating` usage in `__init__` with a dispatcher; add `_build_bar` and `_apply_mode`. In `__init__`, after `self._last_snap = None`, replace the `self._build_floating()` call with `self._apply_mode()`.

Add these methods to `Widget`:
```python
    def _clear_frame(self):
        if getattr(self, "frame", None) is not None:
            self.frame.destroy()

    def _apply_mode(self):
        self._clear_frame()
        if self.cfg.mode == "bar":
            self._build_bar()
        else:
            self._build_floating()
        self._bind_drag()
        self._bind_menu()
        if self._last_snap is not None:
            self.render(self._last_snap)

    def _build_bar(self):
        self.frame = tk.Frame(self.root, bg=BG, padx=10, pady=4)
        self.frame.pack()
        self.bar_label = tk.Label(self.frame, text="-- --%", bg=BG, fg=FG,
                                  font=("Segoe UI", 11, "bold"))
        self.bar_label.pack(side="left")
        self.status = tk.Label(self.frame, text="●", bg=BG, fg=DOT["none"],
                               font=("Segoe UI", 9))
        self.status.pack(side="left", padx=(8, 0))

    def toggle_mode(self):
        self.cfg.mode = "bar" if self.cfg.mode == "floating" else "floating"
        self._apply_mode()

    def set_featured(self, which):
        self.cfg.featured = which
        if self._last_snap is not None:
            self.render(self._last_snap)
```

- [ ] **Step 2: Make `render` handle both layouts**

Replace `render` with:
```python
    def render(self, snap: UsageSnapshot):
        self._last_snap = snap
        color = DIM if snap.stale else DOT.get(snap.source, DOT["none"])

        def line(prefix, w):
            if w is None:
                return f"{prefix}  --%"
            return f"{prefix}  {w.percent:.0f}%  ({fmt_countdown(w.resets_at)})"

        if self.cfg.mode == "bar":
            w = snap.five_hour if self.cfg.featured == "five_hour" else snap.weekly
            label = "5h" if self.cfg.featured == "five_hour" else "7d"
            self.bar_label.config(text=line(label, w))
        else:
            self.fh_label.config(text=line("5h", snap.five_hour))
            self.wk_label.config(text=line("7d", snap.weekly))
        self.status.config(fg=color)
```

- [ ] **Step 3: Add the right-click context menu**

Add to `Widget`:
```python
    def _bind_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Switch mode (floating/bar)",
                              command=self.toggle_mode)
        feat = tk.Menu(self.menu, tearoff=0)
        feat.add_command(label="5-hour", command=lambda: self.set_featured("five_hour"))
        feat.add_command(label="Weekly", command=lambda: self.set_featured("weekly"))
        self.menu.add_cascade(label="Bar shows…", menu=feat)
        self.menu.add_command(label="Recalibrate local budget…",
                              command=self._recalibrate)
        self.menu.add_separator()
        self.menu.add_command(label="Quit", command=self._quit)
        for w in (self.root, self.frame):
            w.bind("<Button-3>", self._show_menu)

    def _show_menu(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)

    def _quit(self):
        if self.on_quit:
            self.on_quit()

    def _recalibrate(self):
        pass  # implemented in Task 11
```

In `__init__`, add a parameter `on_quit=None` and store `self.on_quit = on_quit`. In `main()`, pass `on_quit=on_close` when constructing `Widget` (move `on_close` definition above the `Widget(...)` construction, or assign `widget.on_quit = on_close` after defining `on_close`).

- [ ] **Step 4: Manual check**

Run: `cd E:/Documents/usage && python widget.py`
Expected: right-click shows the menu. "Switch mode" toggles between the two-line floating panel and the slim one-line bar. "Bar shows…" changes which window the bar displays. Mode persists across restarts (saved in `config.json`). "Quit" closes the app.

- [ ] **Step 5: Commit**

```bash
cd E:/Documents/usage && git add widget.py && git commit -m "feat: thin-bar mode and right-click menu"
```

---

## Task 11: Recalibrate budget dialog

**Files:**
- Modify: `E:/Documents/usage/widget.py`

Lets the user calibrate the local-fallback budget by entering the % `/usage` currently shows; back-computes the token budget from current in-window tokens.

- [ ] **Step 1: Implement `_recalibrate`**

Add imports at top of `widget.py`:
```python
from tkinter import simpledialog, messagebox
from datetime import timedelta
from sources import local as local_source
```

Replace the placeholder `_recalibrate` with:
```python
    def _recalibrate(self):
        which = self.cfg.featured
        window = timedelta(hours=5) if which == "five_hour" else timedelta(days=7)
        events = list(local_source.iter_usage_events(local_source.discover_log_paths()))
        total, _ = local_source.aggregate_window(events, datetime.now(timezone.utc), window)
        if total <= 0:
            messagebox.showinfo("Recalibrate",
                                "No recent token usage found to calibrate against.")
            return
        pct = simpledialog.askfloat(
            "Recalibrate",
            f"Open Claude Code, run /usage, and enter the {which} percentage it shows:",
            minvalue=0.1, maxvalue=100.0)
        if not pct:
            return
        budget = int(total / (pct / 100.0))
        self.cfg.budgets[which] = budget
        save_config(self.cfg, CONFIG_PATH)
        messagebox.showinfo(
            "Recalibrate",
            f"Set {which} budget to {budget:,} tokens "
            f"({total:,} tokens ≈ {pct:.0f}%).")
```

- [ ] **Step 2: Manual check**

Run: `cd E:/Documents/usage && python widget.py`
Expected: right-click → "Recalibrate local budget…". Enter a percentage (e.g. the number `/usage` shows). A confirmation dialog reports the new budget. Then rename `.credentials.json` to force local mode and confirm the local percentage now roughly matches what `/usage` showed. Restore the credentials file.

- [ ] **Step 3: Commit**

```bash
cd E:/Documents/usage && git add widget.py && git commit -m "feat: recalibrate local budget from /usage percentage"
```

---

## Task 12: Launcher, docs, autostart

**Files:**
- Create: `E:/Documents/usage/run.bat`
- Create: `E:/Documents/usage/README.md`

- [ ] **Step 1: Create `run.bat`**

`run.bat` (launches without a console window using `pythonw`):
```bat
@echo off
start "" pythonw "%~dp0widget.py"
```

- [ ] **Step 2: Create `README.md`**

`README.md`:
```markdown
# Claude Usage Widget

Always-on-top desktop widget showing how much of your Claude subscription
usage limit is consumed until the next reset (5-hour and weekly windows),
mirroring Claude Code's `/usage`.

## Run

Double-click `run.bat`, or:

    python widget.py

- **Drag** the widget to reposition (position is remembered).
- **Right-click** for the menu: switch between floating panel and thin bar,
  choose which window the bar shows, recalibrate the local fallback, or quit.
- **Esc** closes it.

A green dot = live numbers from Anthropic (exact, same as `/usage`).
Amber = local approximation from `~/.claude` logs (token unavailable).
Grey = stale (last fetch failed; showing last-known values).

## How it works

Primary source: the same authenticated endpoint `/usage` uses
(`/api/oauth/usage`), via your existing Claude Code OAuth token in
`~/.claude/.credentials.json` (refreshed automatically when expired).
If that's unavailable it falls back to summing tokens from your local session
logs against a calibrated budget (right-click → Recalibrate).

## Autostart on login (optional)

Press `Win+R`, type `shell:startup`, Enter. Create a shortcut to `run.bat`
in the folder that opens.

## Caveat

`/api/oauth/usage` is an internal Anthropic endpoint, not a public API. It
uses your own token for your own data, but a future Claude Code update could
change it; if that happens the widget falls back to the local approximation
until `sources/live.py` is updated.

## Tests

    python -m pytest -q
```

- [ ] **Step 3: Run the full test suite one final time**

Run: `cd E:/Documents/usage && python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 4: Final manual smoke test**

Run `run.bat`. Expected: widget appears with no console window, shows live data, survives a few minutes, both modes work, quit works.

- [ ] **Step 5: Commit**

```bash
cd E:/Documents/usage && git add run.bat README.md && git commit -m "docs: add launcher, README, and autostart instructions"
```

---

## Self-Review Notes (author)

- **Spec coverage:** live source (Tasks 5–6), local fallback (Task 4), normalized snapshot (Task 2), orchestration/fallback/stale (Task 7), floating + bar modes (Tasks 8/10), drag + always-on-top (Task 8), poll thread + countdown (Task 9), right-click menu incl. mode/featured/recalibrate/quit (Tasks 10–11), config (Task 3), error handling via stale dot + log (Tasks 7/9), token refresh (Task 5), launcher/autostart (Task 12). All spec sections mapped.
- **Type consistency:** `UsageSnapshot`/`WindowUsage` fields used identically across local, live, and orchestrator. `source` values: `"live"`, `"local"`, `"none"`. `weekly` is the normalized field name everywhere (live maps `seven_day`→`weekly`).
- **Known empirical check:** `utilization` scale (0–1 vs 0–100) is confirmed in Task 5 Step 1 and handled defensively in `live._window`.
```
