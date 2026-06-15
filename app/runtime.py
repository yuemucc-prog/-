from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "BossLoopTimer"


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            return Path(bundle_dir)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def app_home() -> Path:
    override = os.getenv("BOSS_TIMER_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        roaming = os.getenv("APPDATA")
        base = Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
        return base / APP_NAME
    return resource_root()


def db_path() -> Path:
    override = os.getenv("BOSS_TIMER_DB_PATH")
    if override:
        return Path(override).expanduser()
    data_dir_override = os.getenv("BOSS_TIMER_DATA_DIR")
    if data_dir_override:
        return Path(data_dir_override).expanduser() / "boss_timer.db"
    if getattr(sys, "frozen", False) or os.name == "nt":
        return app_home() / "data" / "boss_timer.db"
    return resource_root() / "data" / "boss_timer.db"
