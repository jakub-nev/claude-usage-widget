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
