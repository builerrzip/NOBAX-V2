"""Persistent local conversation session manager for NOBAX V2."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from config import HISTORY_DIR, ensure_data_dirs


class HistoryManager:
    def __init__(self, history_dir: Path = HISTORY_DIR) -> None:
        ensure_data_dirs()
        self.history_dir = history_dir
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.current_session: dict[str, Any] = self._build_session_dict()

    @staticmethod
    def _build_session_dict(title: str = "") -> dict[str, Any]:
        now = datetime.now()
        session_id = f"sess_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
        return {
            "id": session_id,
            "title": title.strip() or "Percakapan Baru",
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "messages": [],
        }

    def _session_file(self, session_id: str) -> Path:
        safe_id = "".join(c for c in session_id if c.isalnum() or c in ("_", "-"))
        return self.history_dir / f"{safe_id}.json"

    def save_current(self) -> None:
        messages = self.current_session.get("messages", [])
        if not messages:
            return
        path = self._session_file(self.current_session["id"])
        self.current_session["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        path.write_text(json.dumps(self.current_session, indent=2, ensure_ascii=False), encoding="utf-8")

    def new_session(self, title: str = "") -> dict[str, Any]:
        self.save_current()
        self.current_session = self._build_session_dict(title=title)
        return self.current_session

    def add_message(self, role: str, content: str) -> None:
        clean = content.strip()
        if not clean:
            return
        messages: list[dict[str, str]] = self.current_session.setdefault("messages", [])
        if role == "user" and not messages and self.current_session.get("title") == "Percakapan Baru":
            snippet = " ".join(clean.split())
            self.current_session["title"] = snippet[:42] + "…" if len(snippet) > 42 else snippet
        messages.append(
            {
                "role": role,
                "content": clean,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        self.save_current()

    def get_context_messages(self, max_turns: int = 12) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = self.current_session.get("messages", [])
        limit = max(2, max_turns * 2)
        return messages[-limit:]

    def get_last_assistant_message(self) -> str | None:
        for msg in reversed(self.current_session.get("messages", [])):
            if msg.get("role") == "assistant" and msg.get("content"):
                return str(msg["content"])
        return None

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for path in self.history_dir.glob("sess_*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                msgs = data.get("messages", [])
                if not msgs:
                    continue
                sessions.append(
                    {
                        "id": str(data.get("id", path.stem)),
                        "title": str(data.get("title", "Tanpa Judul")),
                        "created_at": str(data.get("created_at", "-")),
                        "updated_at": str(data.get("updated_at", "-")),
                        "message_count": len(msgs),
                    }
                )
            except (OSError, json.JSONDecodeError):
                continue
        sessions.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return sessions

    def load_session(self, identifier: str) -> tuple[bool, str]:
        query = identifier.strip().lstrip("#")
        if not query:
            return False, "Masukkan ID atau nomor sesi yang ingin dibuka."
        sessions = self.list_sessions()
        target_id: str | None = None
        if query.isdigit():
            idx = int(query) - 1
            if 0 <= idx < len(sessions):
                target_id = sessions[idx]["id"]
            else:
                return False, f"Nomor sesi #{query} tidak ditemukan (total {len(sessions)} sesi)."
        else:
            for item in sessions:
                sid = item["id"]
                if sid == query or sid.endswith(query) or query in sid:
                    target_id = sid
                    break
        if not target_id:
            return False, f"Sesi percakapan '{identifier}' tidak ditemukan."
        path = self._session_file(target_id)
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.save_current()
            self.current_session = loaded
            return True, f"Sesi '{loaded.get('title', target_id)}' ({len(loaded['messages'])} pesan) dimuat."
        except (OSError, json.JSONDecodeError) as exc:
            return False, f"Gagal memuat sesi: {exc}"
