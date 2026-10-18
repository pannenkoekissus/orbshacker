# debug.py
"""
Simple file-based debug logger.

Usage:
    from debug import debug

    debug("Timer started")
    debug(f"Remaining: {remaining}s")
    debug("Something broke", exc=e)   # optional exception
"""

import sys
import time
import traceback
from pathlib import Path

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
# Resolve the log next to the running script (or .exe when frozen).
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).parent
else:
    _BASE_DIR = Path(sys.argv[0]).resolve().parent if sys.argv[0] else Path.cwd()

LOG_PATH = _BASE_DIR / "debug.txt"

# Set to False to silence all debug() calls without removing them.
ENABLED = True

# Optional per-call prefix toggle. e.g. "[14:32:07.123] Timer started"
TIMESTAMP = True


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def debug(text, exc=None, *, timestamp=None, prefix=None):
    """
    Append a line (or an exception traceback) to debug.txt.

    Parameters
    ----------
    text : str
        Message to log.
    exc : BaseException, optional
        If provided, its traceback is appended after `text`.
    timestamp : bool, optional
        Override the module-level TIMESTAMP setting for this call.
    prefix : str, optional
        Extra label inserted before the message, e.g. "[TimerApp]".
    """
    if not ENABLED:
        return

    use_ts = TIMESTAMP if timestamp is None else timestamp

    parts = []
    if use_ts:
        parts.append(_now())
    if prefix:
        parts.append(f"[{prefix}]")
    parts.append(str(text))

    line = " ".join(parts)

    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip()
        line = f"{line}\n{tb}"

    _write(line)


def debug_clear():
    """Truncate debug.txt."""
    try:
        LOG_PATH.write_text("", encoding="utf-8")
    except OSError:
        pass


def debug_path():
    """Return the absolute path of the log file (useful for 'open log' buttons)."""
    return str(LOG_PATH)


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------
def _now():
    return time.strftime("[%H:%M:%S", time.localtime()) + f".{int(time.time() * 1000) % 1000:03d}]"


def _write(line):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        # Never let logging crash the app.
        pass
