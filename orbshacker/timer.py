"""
timer.py – Fake game process: a standalone countdown timer with self-cleanup.

This module is both the runtime used by ``--timer-mode`` and the source that
``orbshacker.faker.build_timer_script`` inlines (together with bake.py and
janitor.py) into generated ``_*_orbshacker_timer_*.pyw`` files. Because of
that it stays stdlib-only and only imports package siblings behind a
try/except that fails harmlessly in the inlined form.
"""

import sys
import time
import tkinter as tk
from pathlib import Path

try:
    from .bake import has_baked_config, load_baked_config
    from .janitor import spawn_self_destruct
except ImportError:
    pass

WINDOW_TITLE = "Timer"
WINDOW_SIZE = "400x250"
BG_COLOR = "#1a1a1a"
TEXT_COLOR = "#e0e0e0"
SECONDARY_COLOR = "#666666"
DONE_COLOR = "#ff6b6b"
DEFAULT_MINUTES = 15
CLOSE_GRACE_PERIOD_SECONDS = 10
BAKED_CONFIG_KEYS = (
    "TARGET_EXE",
    "TIMER_MINUTES",
    "AUTO_CLOSE",
    "AUTO_DELETE_ON_TIMER_END",
    "STEAM_MANIFEST_PATH",
    "CLEANUP_DIRS",
    "EXTRA_FILES",
    "SHARED_FILES",
    "TK_SUPPORT_DIRS",
)


def resolve_config(minutes=None) -> dict:
    """Merge defaults, package settings, baked config and explicit overrides."""
    cfg = {
        "TARGET_EXE": None,
        "TIMER_MINUTES": DEFAULT_MINUTES,
        "AUTO_CLOSE": True,
        "AUTO_DELETE_ON_TIMER_END": True,
        "STEAM_MANIFEST_PATH": None,
        "CLEANUP_DIRS": [],
        "EXTRA_FILES": [],
        "SHARED_FILES": [],
        "TK_SUPPORT_DIRS": [],
    }
    if __package__:
        try:
            from . import config

            cfg["TIMER_MINUTES"] = config.TIMER_MINUTES
            cfg["AUTO_CLOSE"] = config.AUTO_CLOSE
            cfg["AUTO_DELETE_ON_TIMER_END"] = config.AUTO_DELETE_ON_TIMER_END
            cfg["STEAM_MANIFEST_PATH"] = config.STEAM_MANIFEST_PATH
        except Exception:
            pass
    baked = globals().get("ORBSHACKER_BAKED_CONFIG")
    if baked is None and globals().get("load_baked_config") is not None:
        try:
            baked = load_baked_config(sys.executable)
        except Exception:
            baked = None
    if isinstance(baked, dict):
        for key in BAKED_CONFIG_KEYS:
            if baked.get(key) is not None:
                cfg[key] = baked[key]
    if minutes is not None:
        cfg["TIMER_MINUTES"] = minutes
    return cfg


def parse_timer_args(argv=None) -> int | None:
    """Return the minutes given as ``--timer-mode N``, or None when absent/unparseable."""
    argv = list(sys.argv if argv is None else argv)
    if "--timer-mode" not in argv:
        return None
    idx = argv.index("--timer-mode")
    if idx + 1 < len(argv):
        try:
            return int(argv[idx + 1])
        except ValueError:
            return None
    return None


def _other_fakes_in(folder, own) -> bool:
    """True when *folder* still holds faked files that are not in *own*."""
    import os
    from pathlib import Path

    folder = Path(folder)
    if not folder.is_dir():
        return False
    own_keys = {os.path.normcase(str(p)) for p in own}
    for entry in folder.iterdir():
        if entry.suffix.lower() not in (".exe", ".py", ".pyw"):
            continue
        if os.path.normcase(str(entry)) in own_keys:
            continue
        if has_baked_config(entry):
            return True
    return False


def cleanup_targets(cfg: dict) -> tuple[list, list]:
    """Return (files, dirs) a finished faked process should delete.

    Only files carrying an orbshacker baked config are deleted, plus the exe
    named by ``TARGET_EXE`` in our own baked config (source-mode pythonw copies
    stay byte-identical and carry no marker). Shared runtime files are deleted
    only when no other faked game is left in their folder.
    """
    import os
    from pathlib import Path

    files = []
    exe = Path(sys.executable)
    target = cfg.get("TARGET_EXE")
    target_matches = bool(target) and os.path.normcase(str(target)) == os.path.normcase(str(exe))
    if has_baked_config(exe) or target_matches:
        files.append(exe)
    if sys.argv and sys.argv[0]:
        script = Path(sys.argv[0])
        same_as_exe = os.path.normcase(str(script)) == os.path.normcase(str(exe))
        if not same_as_exe and script.suffix.lower() in (".py", ".pyw") and has_baked_config(script):
            files.append(script)
    manifest = cfg.get("STEAM_MANIFEST_PATH")
    if manifest:
        files.append(Path(manifest))
    files.extend(Path(p) for p in cfg.get("EXTRA_FILES", []) if p)
    shared = [Path(p) for p in cfg.get("SHARED_FILES", []) if p]
    for p in shared:
        if not _other_fakes_in(p.parent, list(files) + shared):
            files.append(p)
    dirs = [Path(p) for p in cfg.get("CLEANUP_DIRS", []) if p]
    return files, dirs


class TimerApp:
    def __init__(
        self,
        root,
        minutes=DEFAULT_MINUTES,
        auto_close=True,
        auto_delete=True,
        cleanup_files=None,
        cleanup_dirs=None,
        title: str = WINDOW_TITLE,
    ):
        self.root = root
        self.auto_delete = bool(auto_delete)
        self.cleanup_files = list(cleanup_files or [])
        self.cleanup_dirs = list(cleanup_dirs or [])

        root.title(title)
        root.geometry(WINDOW_SIZE)
        root.resizable(False, False)
        root.configure(bg=BG_COLOR)

        self.remaining = int(minutes) * 60
        self._deadline = time.monotonic() + self.remaining
        self.closing = False
        self.auto_close = tk.BooleanVar(master=root, value=bool(auto_close))

        self.auto_close_toggle = tk.Checkbutton(
            root,
            text="Close when timer ends",
            variable=self.auto_close,
            command=self.toggle_auto_close,
            font=("Segoe UI", 10),
            fg=TEXT_COLOR,
            bg=BG_COLOR,
            activeforeground=TEXT_COLOR,
            activebackground=BG_COLOR,
            cursor="hand2",
            selectcolor=BG_COLOR,
            bd=1,
        )
        self.auto_close_toggle.pack(pady=(15, 0))

        # --- Main timer label ---
        self.label = tk.Label(
            root,
            text=f"{int(minutes):02d}:00",
            font=("Consolas", 56, "bold"),
            fg=TEXT_COLOR,
            bg=BG_COLOR,
        )
        self.label.pack(expand=True)

        # --- Time adjustment controls (ported from TimerApp.txt) ---
        self.time_adjust_label = tk.Label(
            root,
            text="Add or reduce time",
            font=("Segoe UI", 9),
            fg=SECONDARY_COLOR,
            bg=BG_COLOR,
        )
        self.time_adjust_label.pack()

        self.time_adjust_frame = tk.Frame(root, bg=BG_COLOR)
        self.time_adjust_frame.pack(pady=(2, 10))

        self.minus_button = tk.Button(
            self.time_adjust_frame,
            text="-",
            command=lambda: self.adjust_time(-30),
            font=("Segoe UI", 18, "bold"),
            fg=TEXT_COLOR,
            bg=BG_COLOR,
            activeforeground=TEXT_COLOR,
            activebackground=BG_COLOR,
            cursor="hand2",
            width=2,
            height=1,
            padx=0,
            pady=0,
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        self.minus_button.pack(side="left")

        self.time_adjust_label_value = tk.Label(
            self.time_adjust_frame,
            text="30s",
            font=("Segoe UI", 10),
            fg=TEXT_COLOR,
            bg=BG_COLOR,
            padx=8,
        )
        self.time_adjust_label_value.pack(side="left")

        self.plus_button = tk.Button(
            self.time_adjust_frame,
            text="+",
            command=lambda: self.adjust_time(30),
            font=("Segoe UI", 14, "bold"),
            fg=TEXT_COLOR,
            bg=BG_COLOR,
            activeforeground=TEXT_COLOR,
            activebackground=BG_COLOR,
            cursor="hand2",
            width=2,
            height=1,
            padx=0,
            pady=0,
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        self.plus_button.pack(side="left")

        # --- Status label ---
        self.status = tk.Label(
            root,
            text="Running",
            font=("Segoe UI", 10),
            fg=SECONDARY_COLOR,
            bg=BG_COLOR,
        )
        self.status.pack(side="bottom", pady=20)

        self.update_time_adjust_buttons()
        self._tick()

    # ------------------------------------------------------------------
    # Tick loop — deadline based (from the second class)
    # ------------------------------------------------------------------
    def _tick(self):
        if self.closing:
            return  # close countdown owns the label now

        remaining = int(round(self._deadline - time.monotonic()))
        if remaining < 0:
            remaining = 0
        self.remaining = remaining

        m, s = divmod(remaining, 60)
        self.label.config(text=f"{m:02d}:{s:02d}")

        if remaining > 0:
            self.update_time_adjust_buttons()
            self.label.after(250, self._tick)
        else:
            self.label.config(text="00:00", fg=DONE_COLOR)
            self.status.config(text="Complete", fg=DONE_COLOR)
            self.update_time_adjust_buttons()
            self.root.update()

            # Mirrors the ordering in TimerApp.txt:
            # self-destruct takes priority, then auto-close, else idle at 00:00
            if self.auto_delete or self.auto_close.get():
                self.start_close_countdown()
            else:
                self.label.config(text="00:00", fg=DONE_COLOR)

    # ------------------------------------------------------------------
    # Auto-close
    # ------------------------------------------------------------------
    def toggle_auto_close(self) -> None:
        if self.auto_close.get() and self.remaining <= 0:
            if self.auto_delete:
                return
            self.start_close_countdown()

    # ------------------------------------------------------------------
    # Time adjustment
    # ------------------------------------------------------------------
    def adjust_time(self, seconds: int) -> None:
        if self.closing:
            return

        new_remaining = max(0, self.remaining + seconds)
        self.remaining = new_remaining
        # Rebase the deadline so the monotonic-based tick reflects the change.
        self._deadline = time.monotonic() + new_remaining

        m, s = divmod(new_remaining, 60)
        self.label.config(text=f"{m:02d}:{s:02d}", fg=TEXT_COLOR)
        if new_remaining > 0:
            self.status.config(text="Running", fg=SECONDARY_COLOR)

        self.update_time_adjust_buttons()

    def update_time_adjust_buttons(self) -> None:
        if self.closing:
            self.minus_button.config(state="disabled")
            self.plus_button.config(state="disabled")
            return

        minus_state = "disabled" if self.remaining <= 30 else "normal"
        plus_state = "disabled" if self.remaining <= 0 else "normal"

        self.minus_button.config(state=minus_state)
        self.plus_button.config(state=plus_state)

    # ------------------------------------------------------------------
    # Close countdown (ported from TimerApp.txt)
    # ------------------------------------------------------------------
    def start_close_countdown(self) -> None:
        if self.closing:
            return

        self.closing = True
        self.auto_close_toggle.config(state="disabled")
        self.minus_button.config(state="disabled")
        self.plus_button.config(state="disabled")
        self.label.config(font=("Consolas", 32, "bold"))
        self._close_countdown(CLOSE_GRACE_PERIOD_SECONDS)

    def _close_countdown(self, remaining: int) -> None:
        if remaining <= 0:
            if self.auto_delete:
                self.trigger_self_destruction()
            else:
                self.root.destroy()
            sys.exit(0)

        self.label.config(
            text=f"Closing in {remaining}",
            fg=DONE_COLOR,
        )

        self.root.after(
            1000,
            lambda: self._close_countdown(remaining - 1),
        )

    # ------------------------------------------------------------------
    # Self-destruction (uses the injected cleanup lists + helper)
    # ------------------------------------------------------------------
    def trigger_self_destruction(self) -> None:
        spawn_self_destruct(self.cleanup_files, self.cleanup_dirs)
        self.root.destroy()
        sys.exit(0)


def _setup_tk_environment(tk_support_dirs) -> None:
    """Point TCL_LIBRARY/TK_LIBRARY at the real install so tkinter works from anywhere."""
    import os

    for entry in tk_support_dirs or []:
        name = entry.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].lower()
        if name.startswith("tcl"):
            os.environ.setdefault("TCL_LIBRARY", entry)
        elif name.startswith("tk"):
            os.environ.setdefault("TK_LIBRARY", entry)


def run_timer(minutes=None) -> None:
    """Entry point for a faked game process or ``--timer-mode``."""
    cfg = resolve_config(minutes)
    _setup_tk_environment(cfg.get("TK_SUPPORT_DIRS"))
    import tkinter as tk

    # debug(f"Timer started with config: {cfg}")
    # debug(f"args: {sys.argv}")
    files, dirs = cleanup_targets(cfg)
    root = tk.Tk()
    try:
        root.iconbitmap(resource_path("orbshacker.ico"))
    except (tk.TclError, TypeError):
        pass
    title = sys.argv[1] if len(sys.argv) > 1 else "Timer (Failed to get title)"
    TimerApp(
        root,
        minutes=cfg["TIMER_MINUTES"],
        auto_close=cfg["AUTO_CLOSE"],
        auto_delete=cfg["AUTO_DELETE_ON_TIMER_END"],
        cleanup_files=files,
        cleanup_dirs=dirs,
        title=title,
    )
    root.mainloop()


def resource_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / name
    return None


def debug(text):
    import time
    from pathlib import Path

    try:
        with open(Path(__file__).resolve().parent / "debug.txt", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {text}\n")
    except OSError:
        pass


if __name__ == "__main__":
    run_timer()
