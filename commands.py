"""Slash command router implementing all 16 NOBAX V2 commands."""

from __future__ import annotations

import difflib
import getpass
import os
import py_compile
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ai import GeminiClient
from config import AVAILABLE_MODELS, BRANDING, VERSION, ConfigManager, StatsTracker
from file_manager import FileManager
from history import HistoryManager
from ui import TerminalUI, Theme


LANG_EXT_MAP = {
    "python": "output.py",
    "py": "output.py",
    "bash": "script.sh",
    "sh": "script.sh",
    "javascript": "app.js",
    "js": "app.js",
    "html": "index.html",
    "css": "style.css",
    "json": "data.json",
    "sql": "query.sql",
    "c": "main.c",
    "cpp": "main.cpp",
    "java": "Main.java",
    "go": "main.go",
    "rust": "main.rs",
    "php": "index.php",
    "markdown": "notes.md",
    "md": "notes.md",
}

DEV_QUOTES = [
    "Kode yang bersih selalu terlihat seperti ditulis oleh orang yang peduli. — Robert C. Martin",
    "Pertama selesaikan masalahnya, baru tulis kodenya. — John Johnson",
    "Di Termux, satu baris script Python bisa menghemat ribuan klik.",
    "Jangan takut menimpa file di NOBAX V2 — /undo selalu siap menyelamatkanmu!",
]


class CommandRouter:
    def __init__(
        self,
        config: ConfigManager,
        stats: StatsTracker,
        ui: TerminalUI,
        ai: GeminiClient,
        file_manager: FileManager,
        history: HistoryManager,
    ) -> None:
        self.config = config
        self.stats = stats
        self.ui = ui
        self.ai = ai
        self.files = file_manager
        self.history = history
        self.active_file: str | None = None
        self.should_exit: bool = False

    def get_active_file_context(self) -> tuple[str, str] | None:
        if not self.active_file:
            return None
        res = self.files.read_file(self.active_file)
        if res.ok:
            return res.rel_path, res.content
        return None

    def execute(self, raw_input: str) -> None:
        text = raw_input.strip()
        if not text.startswith("/"):
            return
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        self.stats.increment("total_commands", save=True)

        handlers = {
            "/new": self.cmd_new,
            "/past": self.cmd_past,
            "/open": self.cmd_open,
            "/show": self.cmd_show,
            "/edit": self.cmd_edit,
            "/fix": self.cmd_fix,
            "/run": self.cmd_run,
            "/save": self.cmd_save,
            "/undo": self.cmd_undo,
            "/list": self.cmd_list,
            "/stats": self.cmd_stats,
            "/setting": self.cmd_setting,
            "/key": self.cmd_key,
            "/quit": self.cmd_quit,
            "/exit": self.cmd_quit,
            "/reset_termix": self.cmd_reset_termix,
            "/fun": self.cmd_fun,
            "/help": self.cmd_help,
        }
        handler = handlers.get(cmd)
        if handler is None:
            self.ui.print_error(f"Perintah '{cmd}' tidak dikenal. Ketik /help untuk daftar perintah.")
            return
        handler(arg)

    def cmd_new(self, arg: str) -> None:
        session = self.history.new_session(title=arg)
        self.stats.increment("sessions_created", save=True)
        self.ui.print_success(f"Sesi baru dimulai: '{session['title']}' (ID: {session['id']}).")

    def cmd_past(self, arg: str) -> None:
        sessions = self.history.list_sessions()
        self.ui.print_section("RIWAYAT PERCAKAPAN (/past)")
        if not sessions:
            self.ui.print_info("Belum ada riwayat percakapan tersimpan.")
            return
        for idx, item in enumerate(sessions, start=1):
            is_cur = item["id"] == self.history.current_session.get("id")
            marker = f"{Theme.GREEN}●{Theme.RESET}" if is_cur else f"{Theme.DARK_RED}○{Theme.RESET}"
            print(f" {marker} {Theme.CRIMSON}{Theme.BOLD}[{idx}]{Theme.RESET} {Theme.WHITE}{item['title']}{Theme.RESET}")
            print(f"     {Theme.MUTED}ID: {item['id']} | {item['message_count']} pesan{Theme.RESET}")
        if arg:
            ok, msg = self.history.load_session(arg)
            (self.ui.print_success if ok else self.ui.print_error)(msg)
            return
        try:
            choice = self.ui.styled_input("\nBuka sesi nomor (atau Enter untuk batal): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice:
            ok, msg = self.history.load_session(choice)
            (self.ui.print_success if ok else self.ui.print_error)(msg)

    def cmd_open(self, arg: str) -> None:
        target = arg.strip()
        if not target:
            try:
                target = self.ui.styled_input("Masukkan nama file atau #nomor_sesi: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
        if not target:
            self.ui.print_warning("Operasi /open dibatalkan.")
            return
        if target.startswith("#") or target.startswith("sess_"):
            ok, msg = self.history.load_session(target)
            (self.ui.print_success if ok else self.ui.print_error)(msg)
            return
        res = self.files.read_file(target)
        if res.ok:
            self.active_file = res.rel_path
            lines = res.content.splitlines()
            self.ui.print_success(f"File dibuka: '{res.rel_path}' ({len(lines)} baris).")
            self._print_numbered_lines(lines[:18], start_line=1)
            if len(lines) > 18:
                self.ui.print_info(f"... {len(lines)} baris total. Gunakan /show untuk semua.")
            return
        self.ui.print_error(res.message)

    def cmd_show(self, arg: str) -> None:
        target = arg.strip() or (self.active_file or "")
        if not target:
            self.ui.print_error("Gunakan: /show <nama_file> atau buka file dengan /open.")
            return
        res = self.files.read_file(target)
        if not res.ok:
            self.ui.print_error(res.message)
            return
        self.active_file = res.rel_path
        lines = res.content.splitlines()
        self.ui.print_section(f"ISI FILE: {res.rel_path} ({len(lines)} baris)")
        if not lines:
            self.ui.print_info("(File kosong)")
            return
        self._print_numbered_lines(lines, start_line=1)

    def cmd_edit(self, arg: str) -> None:
        parts = arg.split(maxsplit=1) if arg else []
        target = ""
        inline_instruction = ""
        if parts:
            candidate = parts[0]
            if self.active_file and not (self.files.workspace / candidate).exists() and "." not in candidate:
                target = self.active_file
                inline_instruction = arg
            else:
                target = candidate
                inline_instruction = parts[1].strip() if len(parts) > 1 else ""
        elif self.active_file:
            target = self.active_file
        else:
            try:
                target = self.ui.styled_input("Nama file yang ingin diedit: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
        if not target:
            return
        read_res = self.files.read_file(target)
        if not read_res.ok:
            self.ui.print_error(read_res.message)
            return
        self.active_file = read_res.rel_path
        original_code = read_res.content
        if inline_instruction:
            self._ai_edit_file(read_res.rel_path, original_code, inline_instruction)
            return
        self.ui.print_section(f"EDIT FILE: {read_res.rel_path}")
        print(f" {Theme.CRIMSON}[1]{Theme.RESET} Edit dengan AI")
        print(f" {Theme.CRIMSON}[2]{Theme.RESET} Edit baris manual")
        print(f" {Theme.CRIMSON}[3]{Theme.RESET} Buka di nano/vi")
        print(f" {Theme.MUTED}[0] Batal{Theme.RESET}")
        try:
            mode = self.ui.styled_input("Pilih [1/2/3/0]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if mode == "1":
            instr = self.ui.styled_input("Instruksi perubahan: ").strip()
            if instr:
                self._ai_edit_file(read_res.rel_path, original_code, instr)
        elif mode == "2":
            self._manual_line_edit(read_res.rel_path, original_code)
        elif mode == "3":
            self._external_editor(read_res.rel_path, read_res.full_path)

    def _ai_edit_file(self, rel_path: str, original_code: str, instruction: str) -> None:
        prompt = (
            f"Edit file '{rel_path}' sesuai instruksi: {instruction}\n\n"
            f"```\n{original_code}\n```\n\n"
            "Berikan HANYA isi lengkap file baru dalam SATU blok kode markdown ```...```."
        )
        with self.ui.spinner(f"Mengedit {rel_path}"):
            resp = self.ai.generate_reply(prompt, history_messages=[])
        if not resp.ok:
            self.ui.print_error(resp.error)
            return
        blocks = self.ai.extract_code_blocks(resp.text)
        new_code = blocks[0][1] if blocks else resp.text.strip()
        self._show_diff(original_code, new_code, rel_path)
        if self.ui.confirm(f"Terapkan ke '{rel_path}'?", default=True):
            write_res = self.files.write_file(rel_path, new_code + "\n", action="edit")
            if write_res.ok:
                self.stats.increment("files_edited", save=True)
                self.ui.print_success(write_res.message)
            else:
                self.ui.print_error(write_res.message)

    def _manual_line_edit(self, rel_path: str, original_code: str) -> None:
        lines = original_code.splitlines()
        self._print_numbered_lines(lines, start_line=1)
        target_line = self.ui.styled_input("Nomor baris / append: ").strip().lower()
        if target_line == "append":
            lines.append(self.ui.styled_input("Teks baris baru: "))
        elif target_line.isdigit() and 1 <= int(target_line) <= len(lines):
            idx = int(target_line) - 1
            print(f"{Theme.MUTED}Lama: {lines[idx]}{Theme.RESET}")
            lines[idx] = self.ui.styled_input("Baru: ")
        else:
            self.ui.print_warning("Input tidak valid.")
            return
        write_res = self.files.write_file(rel_path, "\n".join(lines) + "\n", action="edit")
        if write_res.ok:
            self.stats.increment("files_edited", save=True)
            self.ui.print_success(write_res.message)

    def _external_editor(self, rel_path: str, full_path: Path | None) -> None:
        if not full_path:
            return
        editor = next((ed for ed in ("nano", "vim", "vi") if shutil.which(ed)), None)
        if not editor:
            self.ui.print_error("Editor nano/vi tidak ditemukan. Jalankan: pkg install nano")
            return
        self.files.create_backup(full_path, action="edit")
        subprocess.run([editor, str(full_path)], check=False)
        self.stats.increment("files_edited", save=True)
        self.ui.print_success(f"Selesai mengedit '{rel_path}' (backup tersedia untuk /undo).")

    def cmd_fix(self, arg: str) -> None:
        parts = arg.split(maxsplit=1) if arg else []
        target = ""
        error_note = ""
        if parts:
            candidate = parts[0]
            if (self.files.workspace / candidate).exists() or "." in candidate:
                target = candidate
                error_note = parts[1].strip() if len(parts) > 1 else ""
            elif self.active_file:
                target = self.active_file
                error_note = arg
            else:
                target = candidate
        elif self.active_file:
            target = self.active_file
        else:
            target = self.ui.styled_input("Nama file kode yang ingin diperbaiki: ").strip()
        if not target:
            return
        read_res = self.files.read_file(target)
        if not read_res.ok:
            self.ui.print_error(read_res.message)
            return
        self.active_file = read_res.rel_path
        code = read_res.content
        auto_diag = ""
        if read_res.full_path and read_res.full_path.suffix == ".py":
            try:
                py_compile.compile(str(read_res.full_path), doraise=True)
            except py_compile.PyCompileError as comp_err:
                auto_diag = f"Syntax error Python:\n{comp_err.msg}"
                self.ui.print_warning(f"Terdeteksi syntax error: {comp_err.msg}")
        diag_text = "\n\n".join(p for p in (auto_diag, error_note) if p) or "Periksa bug dan error."
        prompt = (
            f"Perbaiki bug pada '{read_res.rel_path}'.\nError:\n{diag_text}\n\n"
            f"```\n{code}\n```\n\n"
            "Jelaskan singkat penyebabnya, lalu berikan kode lengkap perbaikan dalam SATU blok ```...```."
        )
        with self.ui.spinner(f"Memperbaiki {read_res.rel_path}"):
            resp = self.ai.generate_reply(prompt, history_messages=[])
        if not resp.ok:
            self.ui.print_error(resp.error)
            return
        self.ui.render_ai_response(resp.text, latency_ms=resp.latency_ms)
        blocks = self.ai.extract_code_blocks(resp.text)
        if blocks and blocks[0][1].strip() != code.strip():
            if self.ui.confirm(f"Terapkan perbaikan ke '{read_res.rel_path}'?", default=True):
                write_res = self.files.write_file(read_res.rel_path, blocks[0][1] + "\n", action="fix")
                if write_res.ok:
                    self.stats.increment("files_edited", save=True)
                    self.ui.print_success(write_res.message)

    def cmd_run(self, arg: str) -> None:
        target = arg.strip() or (self.active_file or "")
        if not target:
            target = self.ui.styled_input("Nama file yang ingin dijalankan: ").strip()
        if not target:
            return
        try:
            full_path = self.files.resolve_safe_path(target)
        except (ValueError, PermissionError) as exc:
            self.ui.print_error(str(exc))
            return
        if not full_path.exists() or not full_path.is_file():
            self.ui.print_error(f"File tidak ditemukan: '{target}'.")
            return
        rel_path = self.files.to_rel_path(full_path)
        self.active_file = rel_path
        if not self.ui.confirm(f"Jalankan '{rel_path}' sekarang?", default=False):
            return
        runner_map = {
            ".py": [sys.executable, str(full_path)],
            ".sh": ["bash", str(full_path)],
            ".js": ["node", str(full_path)],
            ".php": ["php", str(full_path)],
        }
        cmd_list = runner_map.get(full_path.suffix.lower())
        if not cmd_list:
            self.ui.print_error(f"Ekstensi '{full_path.suffix}' belum didukung /run.")
            return
        self.ui.print_section(f"MENJALANKAN: {rel_path}")
        start = time.monotonic()
        proc = subprocess.run(cmd_list, cwd=str(self.files.workspace), capture_output=True, text=True, timeout=60)
        elapsed = time.monotonic() - start
        if proc.stdout:
            print(f"{Theme.WHITE}{proc.stdout.rstrip()}{Theme.RESET}")
        if proc.stderr:
            print(f"{Theme.ROSE}{proc.stderr.rstrip()}{Theme.RESET}")
        if proc.returncode == 0:
            self.ui.print_success(f"Selesai (0) dalam {elapsed:.2f}d.")
        else:
            self.ui.print_error(f"Exit code {proc.returncode} ({elapsed:.2f}d).")

    def cmd_save(self, arg: str) -> None:
        last_reply = self.history.get_last_assistant_message()
        if not last_reply:
            self.ui.print_error("Belum ada respons AI untuk disimpan.")
            return
        save_full = False
        filename = arg.strip()
        if filename.startswith("--full"):
            save_full = True
            filename = filename[6:].strip()
        blocks = self.ai.extract_code_blocks(last_reply)
        if blocks and not save_full:
            lang, code_content = max(blocks, key=lambda item: len(item[1]))
            content_to_save = code_content + "\n"
            suggested = LANG_EXT_MAP.get(lang, "output.txt")
        else:
            content_to_save = last_reply + "\n"
            suggested = "hasil_nobax.md"
        if not filename:
            entered = self.ui.styled_input(f"Simpan sebagai [{suggested}]: ").strip()
            filename = entered or suggested
        try:
            target = self.files.resolve_safe_path(filename)
        except (ValueError, PermissionError) as exc:
            self.ui.print_error(str(exc))
            return
        existed = target.exists()
        res = self.files.write_file(filename, content_to_save, action="save")
        if res.ok:
            self.active_file = res.rel_path
            self.stats.increment("files_edited" if existed else "files_created", save=True)
            self.ui.print_success(res.message)
        else:
            self.ui.print_error(res.message)

    def cmd_undo(self, arg: str) -> None:
        if arg.strip().lower() == "list":
            backups = self.files.list_backups()
            self.ui.print_section("DAFTAR BACKUP")
            for idx, item in enumerate(reversed(backups), start=1):
                print(f" {Theme.CRIMSON}[{idx}]{Theme.RESET} {item['rel_path']} ({item['timestamp']})")
            return
        res = self.files.undo_last()
        (self.ui.print_success if res.ok else self.ui.print_warning)(res.message)

    def cmd_list(self, arg: str) -> None:
        ok, header_path, items = self.files.list_files(arg)
        if not ok:
            self.ui.print_error(header_path)
            return
        self.ui.print_section(f"FILE WORKSPACE: {header_path}")
        if not items:
            self.ui.print_info("Direktori kerja masih kosong.")
            return
        for item in items:
            color = Theme.SCARLET if item["type"] == "DIR" else Theme.WHITE
            print(f" {Theme.CRIMSON}[{item['type']:<4}]{Theme.RESET} {color}{item['path']:<24}{Theme.RESET} {Theme.MUTED}{item['size']:>7}{Theme.RESET}")

    def cmd_stats(self, _arg: str) -> None:
        _, status_txt = self.ai.get_status()
        self.ui.print_section("STATISTIK NOBAX V2")
        rows = [
            ("Aplikasi", f"{BRANDING} v{VERSION}"),
            ("Status AI", status_txt),
            ("Model Aktif", str(self.config.get("model"))),
            ("Mode Cepat", "ON (thinkingBudget=0)" if self.config.get("fast_mode") else "OFF"),
            ("Live Stream", "ON" if self.config.get("stream_response") else "OFF"),
            ("API Key", self.config.get_masked_api_key()),
            ("Workspace", str(self.files.workspace)),
            ("Durasi Sesi", self.stats.uptime_formatted()),
            ("Prompt Total", str(self.stats.data["total_prompts"])),
            ("Backup Siap", str(len(self.files.list_backups()))),
        ]
        for label, val in rows:
            print(f" {Theme.SCARLET}{label:<16}:{Theme.RESET} {Theme.WHITE}{val}{Theme.RESET}")

    def cmd_setting(self, arg: str) -> None:
        if arg:
            parts = arg.split(maxsplit=1)
            key = parts[0].lower()
            val = parts[1].strip() if len(parts) > 1 else ""
            if key == "model" and val:
                self.config.set("model", val)
                self.ui.print_success(f"Model diubah ke '{val}'.")
                return
            if key == "workspace" and val:
                ok, msg = self.config.set_workspace_path(val)
                (self.ui.print_success if ok else self.ui.print_error)(msg)
                return

        self.ui.print_section("PENGATURAN NOBAX V2 (/setting)")
        print(f" {Theme.CRIMSON}[1]{Theme.RESET} Workspace Dir   : {self.files.workspace}")
        print(f" {Theme.CRIMSON}[2]{Theme.RESET} Model Gemini    : {self.config.get('model')}")
        print(f" {Theme.CRIMSON}[3]{Theme.RESET} Mode Cepat AI   : {'ON' if self.config.get('fast_mode') else 'OFF'}")
        print(f" {Theme.CRIMSON}[4]{Theme.RESET} Live Streaming  : {'ON' if self.config.get('stream_response') else 'OFF'}")
        print(f" {Theme.CRIMSON}[5]{Theme.RESET} Animasi Startup : {'ON' if self.config.get('startup_animation') else 'OFF'}")
        print(f" {Theme.MUTED}[0] Kembali{Theme.RESET}")

        choice = self.ui.styled_input("\nPilih [0-5]: ").strip()
        if choice == "1":
            new_ws = self.ui.styled_input("Path workspace baru: ").strip()
            if new_ws:
                ok, msg = self.config.set_workspace_path(new_ws)
                (self.ui.print_success if ok else self.ui.print_error)(msg)
        elif choice == "2":
            print(f"{Theme.MUTED}Pilihan: {', '.join(AVAILABLE_MODELS)}{Theme.RESET}")
            m = self.ui.styled_input("Nama model: ").strip()
            if m:
                self.config.set("model", m)
                self.ui.print_success(f"Model diubah ke '{m}'.")
        elif choice == "3":
            cur = bool(self.config.get("fast_mode", True))
            self.config.set("fast_mode", not cur)
            self.ui.print_success(f"Mode Cepat AI: {'ON' if not cur else 'OFF'}.")
        elif choice == "4":
            cur = bool(self.config.get("stream_response", True))
            self.config.set("stream_response", not cur)
            self.ui.print_success(f"Live Streaming: {'ON' if not cur else 'OFF'}.")
        elif choice == "5":
            cur = bool(self.config.get("startup_animation", True))
            self.config.set("startup_animation", not cur)
            self.ui.print_success(f"Animasi Startup: {'ON' if not cur else 'OFF'}.")

    def cmd_key(self, arg: str) -> None:
        parts = arg.split(maxsplit=1) if arg else []
        sub = parts[0].lower() if parts else ""
        val = parts[1].strip() if len(parts) > 1 else ""
        if sub == "set" and val:
            self.config.set_api_key(val)
            self.ui.print_success(f"API key disimpan ({self.config.get_masked_api_key()}).")
            with self.ui.spinner("Memverifikasi API key"):
                ok, msg = self.ai.verify_connection()
            (self.ui.print_success if ok else self.ui.print_warning)(msg)
            return
        if sub == "test":
            with self.ui.spinner("Menguji koneksi"):
                ok, msg = self.ai.verify_connection()
            (self.ui.print_success if ok else self.ui.print_error)(msg)
            return

        self.ui.print_section("GEMINI API KEY (/key)")
        print(f" Status: {self.config.get_masked_api_key()}")
        print(f" {Theme.CRIMSON}[1]{Theme.RESET} Pasang / Ganti API Key")
        print(f" {Theme.CRIMSON}[2]{Theme.RESET} Tes Koneksi")
        print(f" {Theme.CRIMSON}[3]{Theme.RESET} Hapus Key")
        print(f" {Theme.MUTED}[0] Kembali{Theme.RESET}")
        choice = self.ui.styled_input("\nPilih [0-3]: ").strip()
        if choice == "1":
            new_key = getpass.getpass("Tempel Gemini API Key: ").strip() if sys.stdin.isatty() else input("API Key: ").strip()
            if new_key:
                self.config.set_api_key(new_key)
                with self.ui.spinner("Memverifikasi API key"):
                    ok, msg = self.ai.verify_connection()
                (self.ui.print_success if ok else self.ui.print_warning)(msg)
        elif choice == "2":
            with self.ui.spinner("Menguji koneksi"):
                ok, msg = self.ai.verify_connection()
            (self.ui.print_success if ok else self.ui.print_error)(msg)
        elif choice == "3":
            self.config.clear_api_key()
            self.ui.print_success("API key dihapus.")

    def cmd_quit(self, _arg: str) -> None:
        self.history.save_current()
        self.stats.save()
        self.should_exit = True
        print(f"\n{Theme.CRIMSON}{Theme.BOLD}Sampai jumpa dari {BRANDING}!{Theme.RESET}\n")

    def cmd_reset_termix(self, _arg: str) -> None:
        self.ui.clear_screen()
        connected, status_txt = self.ai.get_status()
        self.ui.render_banner(
            version=VERSION,
            connected=connected,
            status_text=status_txt,
            model=str(self.config.get("model", "gemini-2.5-flash")),
            workspace=str(self.files.workspace),
            active_file=self.active_file,
            animate=False,
        )

    def cmd_fun(self, _arg: str) -> None:
        quote = random.choice(DEV_QUOTES)
        print(f"\n{Theme.CRIMSON}❝ {Theme.WHITE}{quote} {Theme.CRIMSON}❞{Theme.RESET}")

    def cmd_help(self, _arg: str) -> None:
        self.ui.print_section("DAFTAR PERINTAH NOBAX V2")
        for cmd_name, desc in [
            ("/new [judul]", "Sesi percakapan baru"),
            ("/past", "Riwayat percakapan"),
            ("/open <file>", "Buka file workspace"),
            ("/show [file]", "Tampilkan isi file"),
            ("/edit [file]", "Edit file (AI / manual / nano)"),
            ("/fix [file]", "Perbaiki bug kode"),
            ("/run [file]", "Jalankan script"),
            ("/save [file]", "Simpan kode terakhir dari AI"),
            ("/undo", "Batalkan perubahan file terakhir"),
            ("/list", "Daftar file workspace"),
            ("/stats", "Statistik & status mode cepat"),
            ("/setting", "Pengaturan model, fast mode, streaming"),
            ("/key", "Atur Gemini API key"),
            ("/reset_termix", "Bersihkan layar terminal"),
            ("/quit", "Keluar aplikasi"),
        ]:
            print(f" {Theme.CRIMSON}{Theme.BOLD}{cmd_name:<16}{Theme.RESET} {Theme.LIGHT_GRAY}{desc}{Theme.RESET}")

    @staticmethod
    def _print_numbered_lines(lines: list[str], start_line: int = 1) -> None:
        for idx, line in enumerate(lines, start=start_line):
            print(f"{Theme.DARK_RED}{idx:>4} │ {Theme.LIGHT_GRAY}{line}{Theme.RESET}")

    @staticmethod
    def _show_diff(old_text: str, new_text: str, filename: str) -> None:
        diff_lines = list(
            difflib.unified_diff(old_text.splitlines(), new_text.splitlines(), fromfile=filename, tofile=f"{filename} (baru)", lineterm="")
        )
        for line in diff_lines[:50]:
            color = Theme.GREEN if line.startswith("+") else (Theme.CRIMSON if line.startswith("-") else Theme.MUTED)
            print(f"{color}{line}{Theme.RESET}")
