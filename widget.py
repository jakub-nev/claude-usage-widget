import logging
import threading
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path

from config import load_config, save_config
from models import UsageSnapshot
from usage_source import UsageProvider

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
        self._last_snap = None

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
        self._last_snap = snap

        def line(prefix, w):
            if w is None:
                return f"{prefix}  --%"
            return f"{prefix}  {w.percent:.0f}%  ({fmt_countdown(w.resets_at)})"
        self.fh_label.config(text=line("5h", snap.five_hour))
        self.wk_label.config(text=line("7d", snap.weekly))
        color = DOT.get(snap.source, DOT["none"])
        self.status.config(fg=(DIM if snap.stale else color))

    def refresh_countdown(self):
        if self._last_snap is not None:
            self.render(self._last_snap)

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


if __name__ == "__main__":
    main()
