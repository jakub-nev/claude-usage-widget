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
