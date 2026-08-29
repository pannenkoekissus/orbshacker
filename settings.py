from pathlib import Path
# ╔═══════════════════════════════════════════════════════════╗
# ║             ORBSHACKER – USER SETTINGS                   ║
# ║  Edit values here. The app reads from this file.         ║
# ╚═══════════════════════════════════════════════════════════╝

# ── Destination folder for faked executables (defaults to Desktop) ──
CHOSEN_FOLDER = Path.home() / "Desktop"

# ── Automatically delete faked executables and processes on exit ──
AUTO_DELETE = False

# ── Timer duration (in minutes) – Discord quests normally require 15 minutes ──
TIMER_MINUTES = 15
