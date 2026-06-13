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
