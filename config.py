"""Configuration and persistent statistics manager for NOBAX V2."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

APP_NAME = "NOBAX V2"
BRANDING = "NOBAX Nobax@TERMUX"
VERSION = "2.1.0"
PROMPT_LABEL = "Nobax@termux ❯"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
HISTORY_DIR = DATA_DIR / "history"
BACKUP_DIR = DATA_DIR / "backups"
CONFIG_FILE = DATA_DIR / "config.json"
STATS_FILE = DATA_DIR / "stats.json"

AVAILABLE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
]

DEFAULT_CONFIG: dict[str, Any] = {
    "api_key": "",
    "model": "gemini-2.5-flash",
    "temperature": 0.7,
    "max_output_tokens": 2048,
    "fast_mode": True,
    "stream_response": True,
    "workspace_dir": str(Path.cwd()),
    "startup_animation": True,
    "auto_context_file": True,
    "max_history_turns": 12,
    "timeout_seconds": 30,
}


def ensure_data_dirs() -> None:
    """Ensure internal data, history, and backup directories exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


class ConfigManager:
    """Manages persistent user settings and secure API key storage."""

    def __init__(self, config_path: Path = CONFIG_FILE) -> None:
        ensure_data_dirs()
        self.config_path = config_path
        self.data: dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        """Load configuration from disk, merging with defaults."""
        if not self.config_path.exists():
            self.save()
            return
        try:
            raw = self.config_path.read_text(encoding="utf-8")
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                merged = dict(DEFAULT_CONFIG)
                merged.update(loaded)
                self.data = merged
        except (OSError, json.JSONDecodeError):
            self.data = dict(DEFAULT_CONFIG)
            self.save()

    def save(self) -> None:
        """Persist configuration to disk with restricted file permissions."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.data, indent=2, ensure_ascii=False)
        self.config_path.write_text(payload, encoding="utf-8")
        try:
            os.chmod(self.config_path, 0o600)
        except OSError:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()

    def reset_defaults(self, keep_api_key: bool = True) -> None:
        saved_key = self.data.get("api_key", "") if keep_api_key else ""
        self.data = dict(DEFAULT_CONFIG)
        self.data["api_key"] = saved_key
        self.save()

    def get_api_key(self) -> str:
        """Return API key from secure config or GEMINI_API_KEY environment variable."""
        configured = str(self.data.get("api_key", "")).strip()
        if configured:
            return configured
        return os.environ.get("GEMINI_API_KEY", "").strip()

    def set_api_key(self, api_key: str) -> None:
        self.data["api_key"] = api_key.strip()
        self.save()

    def clear_api_key(self) -> None:
        self.data["api_key"] = ""
        self.save()

    def get_masked_api_key(self) -> str:
        key = self.get_api_key()
        if not key:
            return "Belum diatur"
        if len(key) <= 10:
            return "*" * len(key)
        return f"{key[:6]}••••••{key[-4:]}"

    def get_workspace_path(self) -> Path:
        """Return resolved workspace directory, falling back safely if invalid."""
        raw = str(self.data.get("workspace_dir", "")).strip()
        candidate = Path(raw).expanduser() if raw else Path.cwd()
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate.resolve()
        except OSError:
            fallback = BASE_DIR / "workspace"
            fallback.mkdir(parents=True, exist_ok=True)
            self.data["workspace_dir"] = str(fallback.resolve())
            self.save()
            return fallback.resolve()

    def set_workspace_path(self, new_path: str) -> tuple[bool, str]:
        target = Path(new_path).expanduser()
        if not target.is_absolute():
            target = (self.get_workspace_path() / target).resolve()
        else:
            target = target.resolve()
        try:
            target.mkdir(parents=True, exist_ok=True)
            if not target.is_dir():
                return False, f"Path bukan direktori: {target}"
            self.data["workspace_dir"] = str(target)
            self.save()
            return True, str(target)
        except OSError as exc:
            return False, f"Gagal mengatur workspace: {exc}"


class StatsTracker:
    """Tracks cumulative and session usage metrics locally."""

    DEFAULT_STATS: dict[str, int] = {
        "app_starts": 0,
        "total_prompts": 0,
        "total_responses": 0,
        "total_commands": 0,
        "files_created": 0,
        "files_edited": 0,
        "sessions_created": 0,
    }

    def __init__(self, stats_path: Path = STATS_FILE) -> None:
        ensure_data_dirs()
        self.stats_path = stats_path
        self.session_start = time.monotonic()
        self.session_prompts = 0
        self.session_commands = 0
        self.data: dict[str, int] = dict(self.DEFAULT_STATS)
        self.load()
        self.increment("app_starts", save=True)

    def load(self) -> None:
        if not self.stats_path.exists():
            self.save()
            return
        try:
            loaded = json.loads(self.stats_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key in self.DEFAULT_STATS:
                    if isinstance(loaded.get(key), int):
                        self.data[key] = loaded[key]
        except (OSError, json.JSONDecodeError):
            self.data = dict(self.DEFAULT_STATS)

    def save(self) -> None:
        try:
            self.stats_path.parent.mkdir(parents=True, exist_ok=True)
            self.stats_path.write_text(
                json.dumps(self.data, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def increment(self, metric: str, amount: int = 1, save: bool = True) -> None:
        self.data[metric] = self.data.get(metric, 0) + amount
        if metric == "total_prompts":
            self.session_prompts += amount
        elif metric == "total_commands":
            self.session_commands += amount
        if save:
            self.save()

    def uptime_formatted(self) -> str:
        elapsed = int(time.monotonic() - self.session_start)
        mins, secs = divmod(elapsed, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}j {mins}m {secs}d"
        if mins > 0:
            return f"{mins}m {secs}d"
        return f"{secs}d"
