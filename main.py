#!/usr/bin/env python3
"""Main entry point for NOBAX V2 (NOBAX NOBAX@TERMUX)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

try:
    import readline  # noqa: F401
except ImportError:
    pass

from ai import GeminiClient
from commands import CommandRouter
from config import BRANDING, PROMPT_LABEL, VERSION, ConfigManager, StatsTracker
from file_manager import FileManager
from history import HistoryManager
from ui import TerminalUI


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="nobax",
        description=f"{BRANDING} v{VERSION} - Termux CLI AI Assistant",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="store_true",
        help="Tampilkan versi aplikasi lalu keluar",
    )
    parser.add_argument(
        "--no-anim",
        action="store_true",
        help="Lewati animasi logo saat startup",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default="",
        help="Tentukan direktori kerja proyek",
    )
    return parser.parse_args(argv)


def run_app(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.version:
        print(f"{BRANDING} v{VERSION}")
        return 0

    config = ConfigManager()
    if args.workspace:
        ok, msg = config.set_workspace_path(args.workspace)
        if not ok:
            print(f"[!] {msg}", file=sys.stderr)

    stats = StatsTracker()
    ui = TerminalUI(prompt_label=PROMPT_LABEL)
    ai = GeminiClient(config=config)
    file_manager = FileManager(config=config)
    history = HistoryManager()
    router = CommandRouter(
        config=config,
        stats=stats,
        ui=ui,
        ai=ai,
        file_manager=file_manager,
        history=history,
    )

    ui.clear_screen()
    connected, status_txt = ai.get_status()
    animate = bool(config.get("startup_animation", True)) and not args.no_anim
    ui.render_banner(
        version=VERSION,
        connected=connected,
        status_text=status_txt,
        model=str(config.get("model", "gemini-2.5-flash")),
        workspace=str(file_manager.workspace),
        active_file=router.active_file,
        animate=animate,
    )

    if not ai.is_configured():
        ui.print_warning(
            "API key Gemini belum diatur. Ketik /key untuk memasang API key Anda."
        )

    while not router.should_exit:
        try:
            user_input = ui.read_input()
        except KeyboardInterrupt:
            print()
            ui.print_info("Tekan /quit untuk keluar dari aplikasi.")
            continue
        except EOFError:
            print()
            router.cmd_quit("")
            break

        cleaned = user_input.strip()
        if not cleaned:
            continue

        if cleaned.startswith("/"):
            router.execute(cleaned)
            continue

        history.add_message("user", cleaned)
        stats.increment("total_prompts", save=True)
        context_msgs = history.get_context_messages(
            max_turns=int(config.get("max_history_turns", 12))
        )
        file_ctx = router.get_active_file_context()

        if bool(config.get("stream_response", True)):
            try:
                stream_iter = ai.stream_reply(
                    user_prompt=cleaned,
                    history_messages=context_msgs,
                    active_file_context=file_ctx,
                )
                reply_text, _ = ui.render_ai_stream(stream_iter)
                if reply_text:
                    history.add_message("assistant", reply_text)
                    stats.increment("total_responses", save=True)
            except RuntimeError as err:
                ui.print_error(str(err))
        else:
            with ui.spinner("NOBAX sedang berpikir"):
                response = ai.generate_reply(
                    user_prompt=cleaned,
                    history_messages=context_msgs,
                    active_file_context=file_ctx,
                )

            if response.ok:
                history.add_message("assistant", response.text)
                stats.increment("total_responses", save=True)
                ui.render_ai_response(response.text, latency_ms=response.latency_ms)
            else:
                ui.print_error(response.error)

    return 0


if __name__ == "__main__":
    raise SystemExit(run_app())
