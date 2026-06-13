import logging
import threading
import tkinter as tk
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import messagebox, simpledialog

from config import load_config, save_config
from models import UsageSnapshot
from sources import local as local_source
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
    def __init__(self, root: tk.Tk, cfg, on_quit=None):
        self.root = root
        self.cfg = cfg
        self.on_quit = on_quit
        self._last_snap = None
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=BG)
        root.geometry(f"+{cfg.pos_x}+{cfg.pos_y}")
        self._apply_mode()

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

    def _build_bar(self):
        self.frame = tk.Frame(self.root, bg=BG, padx=10, pady=4)
        self.frame.pack()
        self.bar_label = tk.Label(self.frame, text="-- --%", bg=BG, fg=FG,
                                  font=("Segoe UI", 11, "bold"))
        self.bar_label.pack(side="left")
        self.status = tk.Label(self.frame, text="●", bg=BG, fg=DOT["none"],
                               font=("Segoe UI", 9))
        self.status.pack(side="left", padx=(8, 0))

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

    def refresh_countdown(self):
        if self._last_snap is not None:
            self.render(self._last_snap)

    def toggle_mode(self):
        self.cfg.mode = "bar" if self.cfg.mode == "floating" else "floating"
        self._apply_mode()
        save_config(self.cfg, CONFIG_PATH)

    def set_featured(self, which):
        self.cfg.featured = which
        save_config(self.cfg, CONFIG_PATH)
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


def main():
    cfg = load_config(CONFIG_PATH)
    root = tk.Tk()

    def on_close():
        stop.set()
        save_config(cfg, CONFIG_PATH)
        root.destroy()

    widget = Widget(root, cfg, on_quit=on_close)
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

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.bind("<Escape>", lambda e: on_close())
    root.mainloop()


if __name__ == "__main__":
    main()
