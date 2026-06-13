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
