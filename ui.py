"""Terminal UI renderer with red theme, readline-safe prompts, and live streaming."""

from __future__ import annotations

import os
import re
import shutil
import sys
import textwrap
import threading
import time
from contextlib import contextmanager
from typing import Iterable, Iterator


class Theme:
    """ANSI color palette tuned for a sharp crimson/red terminal aesthetic."""

    CRIMSON = "\033[38;5;196m"
    BLOOD = "\033[38;5;160m"
    DARK_RED = "\033[38;5;124m"
    SCARLET = "\033[38;5;203m"
    ROSE = "\033[38;5;210m"
    WHITE = "\033[97m"
    LIGHT_GRAY = "\033[38;5;250m"
    MUTED = "\033[38;5;242m"
    GREEN = "\033[38;5;46m"
    YELLOW = "\033[38;5;220m"
    CYAN = "\033[38;5;81m"
    CODE_BG = "\033[48;5;234m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


ASCII_LOGO_FULL = [
    "███╗   ██╗ ██████╗ ██████╗  █████╗ ██╗  ██╗",
    "████╗  ██║██╔═══██╗██╔══██╗██╔══██╗╚██╗██╔╝",
    "██╔██╗ ██║██║   ██║██████╔╝███████║ ╚███╔╝ ",
    "██║╚██╗██║██║   ██║██╔══██╗██╔══██║ ██╔██╗ ",
    "██║ ╚████║╚██████╔╝██████╔╝██║  ██║██╔╝ ██╗",
    "╚═╝  ╚═══╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝",
]

ASCII_LOGO_COMPACT = [
    "███╗  ██╗ ██████╗ ██████╗  █████╗ ██╗  ██╗",
    "████╗ ██║██╔═══██╗██╔══██╗██╔══██╗╚██╗██╔╝",
    "██╔██╗██║██║   ██║██████╔╝███████║ ╚███╔╝ ",
    "██║╚████║██║   ██║██╔══██╗██╔══██║ ██╔██╗ ",
    "██║ ╚███║╚██████╔╝██████╔╝██║  ██║██╔╝ ██╗",
    "╚═╝  ╚══╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝",
]


def rl_escape(ansi_code: str) -> str:
    """Wrap ANSI escape codes in readline non-printing markers (\001...\002).

    Prevents GNU readline in Termux from miscalculating prompt width when
    long user input wraps onto new lines or when Backspace is held down.
    """
    if "readline" in sys.modules:
        return f"\001{ansi_code}\002"
    return ansi_code


class TerminalUI:
    """Handles all terminal rendering, banners, animations, and mobile layout."""

    def __init__(self, prompt_label: str = "Nobax@termux ❯") -> None:
        self.prompt_label = prompt_label

    @staticmethod
    def term_width() -> int:
        cols = shutil.get_terminal_size((54, 24)).columns
        return max(36, min(92, cols))

    @staticmethod
    def clear_screen() -> None:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        os.system("cls" if os.name == "nt" else "clear")

    @staticmethod
    def shorten_path(path_str: str, max_len: int = 32) -> str:
        home = os.path.expanduser("~")
        if path_str.startswith(home):
            path_str = "~" + path_str[len(home):]
        if len(path_str) <= max_len:
            return path_str
        return "…" + path_str[-(max_len - 1):]

    def render_banner(
        self,
        version: str,
        connected: bool,
        status_text: str,
        model: str,
        workspace: str,
        active_file: str | None = None,
        animate: bool = True,
    ) -> None:
        """Render the red NOBAX ASCII block logo, status panel, cpu and gpu,and command bar."""
        width = self.term_width()
        border = "━" * width
        thin_border = "─" * width

        print(f"{Theme.DARK_RED}{border}{Theme.RESET}")

        logo_lines = ASCII_LOGO_FULL if width >= 46 else ASCII_LOGO_COMPACT
        logo_colors = [
            Theme.CRIMSON,
            Theme.CRIMSON,
            Theme.BLOOD,
            Theme.BLOOD,
            Theme.SCARLET,
            Theme.DARK_RED,
        ]
        should_animate = animate and sys.stdout.isatty()

        for idx, line in enumerate(logo_lines):
            color = logo_colors[idx % len(logo_colors)]
            display_line = line[:width]
            pad = max(0, (width - len(display_line)) // 2)
            rendered = f"{' ' * pad}{color}{Theme.BOLD}{display_line}{Theme.RESET}"
            if should_animate:
                sys.stdout.write(rendered + "\n")
                sys.stdout.flush()
                time.sleep(0.04)
            else:
                print(rendered)

        tagline = f"NOBAX Nobax@TERMUX • v{version}"
        tag_pad = max(0, (width - len(tagline)) // 2)
        if should_animate:
            sys.stdout.write(" " * tag_pad)
            for ch in tagline:
                sys.stdout.write(f"{Theme.WHITE}{Theme.BOLD}{ch}{Theme.RESET}")
                sys.stdout.flush()
                time.sleep(0.006)
            print()
        else:
            print(f"{' ' * tag_pad}{Theme.WHITE}{Theme.BOLD}{tagline}{Theme.RESET}")

        print(f"{Theme.DARK_RED}{thin_border}{Theme.RESET}")

        if connected:
            status_badge = f"{Theme.GREEN}{Theme.BOLD}● {status_text}{Theme.RESET}"
        else:
            status_badge = f"{Theme.YELLOW}{Theme.BOLD}● {status_text}{Theme.RESET}"

        ws_short = self.shorten_path(workspace, max(18, width - 15))
        print(f" {Theme.SCARLET}AI Status :{Theme.RESET} {status_badge}")
        print(f" {Theme.SCARLET}Model     :{Theme.RESET} {Theme.LIGHT_GRAY}{model}{Theme.RESET}")
        print(f" {Theme.SCARLET}Workspace :{Theme.RESET} {Theme.LIGHT_GRAY}{ws_short}{Theme.RESET}")
        if active_file:
            print(
                f" {Theme.SCARLET}File Aktif:{Theme.RESET} "
                f"{Theme.ROSE}{Theme.BOLD}{active_file}{Theme.RESET}"
            )

        print(f"{Theme.DARK_RED}{thin_border}{Theme.RESET}")
        hint1 = " /new /past /open /show /edit /fix /run /save"
        hint2 = " /undo /list /stats /setting /key /fun /quit"
        print(f"{Theme.MUTED}{hint1[:width]}{Theme.RESET}")
        print(f"{Theme.MUTED}{hint2[:width]}{Theme.RESET}")
        print(f"{Theme.DARK_RED}{border}{Theme.RESET}")

    def prompt_text(self) -> str:
        """Build a single-line, readline-escaped prompt so long input wraps downward."""
        start_c = rl_escape(f"{Theme.CRIMSON}{Theme.BOLD}")
        end_c = rl_escape(Theme.RESET)
        return f"{start_c}{self.prompt_label}{end_c} "

    def styled_input(self, label: str) -> str:
        """Read input with readline-safe ANSI color escapes."""
        start_c = rl_escape(Theme.SCARLET)
        end_c = rl_escape(Theme.RESET)
        return input(f"{start_c}{label}{end_c}")

    def read_input(self, custom_prompt: str | None = None) -> str:
        if custom_prompt is not None:
            return input(custom_prompt)
        # Print newline BEFORE input() so readline never miscounts vertical rows
        sys.stdout.write("\n")
        sys.stdout.flush()
        return input(self.prompt_text())

    def confirm(self, question: str, default: bool = False) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        start_c = rl_escape(f"{Theme.SCARLET}{Theme.BOLD}")
        end_c = rl_escape(Theme.RESET)
        try:
            ans = input(
                f"{start_c}? {question} {suffix}: {end_c}"
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if not ans:
            return default
        return ans in {"y", "yes", "ya"}

    @contextmanager
    def spinner(self, label: str = "NOBAX sedang berpikir") -> Iterator[None]:
        """Animated red loading indicator while waiting for Gemini API."""
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        stop_event = threading.Event()
        start = time.monotonic()

        def _animate() -> None:
            idx = 0
            while not stop_event.is_set():
                elapsed = time.monotonic() - start
                frame = frames[idx % len(frames)]
                msg = (
                    f"\r\033[K{Theme.CRIMSON}{Theme.BOLD}{frame}{Theme.RESET} "
                    f"{Theme.ROSE}{label}...{Theme.RESET} "
                    f"{Theme.MUTED}[{elapsed:.1f}s]{Theme.RESET}"
                )
                sys.stdout.write(msg)
                sys.stdout.flush()
                idx += 1
                stop_event.wait(0.08)

        thread = threading.Thread(target=_animate, daemon=True)
        if sys.stdout.isatty():
            thread.start()
        try:
            yield
        finally:
            stop_event.set()
            if sys.stdout.isatty():
                thread.join(timeout=0.3)
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()

    def print_section(self, title: str) -> None:
        width = self.term_width()
        bar_len = max(4, width - len(title) - 5)
        print(
            f"\n{Theme.CRIMSON}{Theme.BOLD}━━ {title} "
            f"{Theme.DARK_RED}{'━' * bar_len}{Theme.RESET}"
        )

    def print_success(self, message: str) -> None:
        print(f"{Theme.GREEN}{Theme.BOLD}[✓]{Theme.RESET} {Theme.WHITE}{message}{Theme.RESET}")

    def print_error(self, message: str) -> None:
        print(f"{Theme.CRIMSON}{Theme.BOLD}[✗]{Theme.RESET} {Theme.ROSE}{message}{Theme.RESET}")

    def print_warning(self, message: str) -> None:
        print(f"{Theme.YELLOW}{Theme.BOLD}[!]{Theme.RESET} {Theme.LIGHT_GRAY}{message}{Theme.RESET}")

    def print_info(self, message: str) -> None:
        print(f"{Theme.SCARLET}{Theme.BOLD}[i]{Theme.RESET} {Theme.LIGHT_GRAY}{message}{Theme.RESET}")

    def render_ai_stream(self, chunks: Iterable[str]) -> tuple[str, int]:
        """Stream AI chunks live to terminal with word-wrapping inside the red frame."""
        width = self.term_width()
        max_content_w = max(24, width - 4)
        header = " NOBAX AI "
        side = max(4, width - len(header) - 2)
        start_time = time.monotonic()

        sys.stdout.write(
            f"\n{Theme.BLOOD}┌─{Theme.CRIMSON}{Theme.BOLD}{header}"
            f"{Theme.DARK_RED}{'─' * side}{Theme.RESET}\n"
        )
        sys.stdout.write(f"{Theme.BLOOD}│ {Theme.WHITE}")
        sys.stdout.flush()

        full_parts: list[str] = []
        line_buf = ""
        col = 0
        in_code = False

        def _flush_word(word: str) -> None:
            nonlocal col
            if not word:
                return
            prefix = f"{Theme.DARK_RED}  │ {Theme.CYAN}" if in_code else f"{Theme.BLOOD}│ {Theme.WHITE}"
            if col > 0 and col + len(word) > max_content_w:
                sys.stdout.write(f"\n{prefix}")
                col = 0
            sys.stdout.write(word)
            col += len(word)

        for chunk in chunks:
            if not chunk:
                continue
            full_parts.append(chunk)
            for ch in chunk:
                if ch == "\n":
                    stripped = line_buf.strip()
                    if stripped.startswith("```"):
                        if not in_code:
                            in_code = True
                            code_lang = stripped[3:].strip().upper() or "CODE"
                            tag = f" {code_lang} "
                            dash = max(4, width - len(tag) - 4)
                            sys.stdout.write(
                                f"\r\033[K{Theme.DARK_RED}  ┌─{Theme.SCARLET}{Theme.BOLD}{tag}"
                                f"{Theme.DARK_RED}{'─' * dash}{Theme.RESET}\n"
                                f"{Theme.DARK_RED}  │ {Theme.CYAN}"
                            )
                        else:
                            in_code = False
                            sys.stdout.write(
                                f"\r\033[K{Theme.DARK_RED}  └{'─' * max(8, width - 4)}{Theme.RESET}\n"
                                f"{Theme.BLOOD}│ {Theme.WHITE}"
                            )
                    else:
                        prefix = (
                            f"{Theme.DARK_RED}  │ {Theme.CYAN}"
                            if in_code
                            else f"{Theme.BLOOD}│ {Theme.WHITE}"
                        )
                        sys.stdout.write(f"\n{prefix}")
                    line_buf = ""
                    col = 0
                elif ch == " " and not in_code:
                    line_buf += ch
                    if col >= max_content_w:
                        sys.stdout.write(f"\n{Theme.BLOOD}│ {Theme.WHITE}")
                        col = 0
                    else:
                        sys.stdout.write(" ")
                        col += 1
                else:
                    line_buf += ch
                    if in_code:
                        sys.stdout.write(ch)
                        col += 1
                    else:
                        # Word wrap cleanly when reaching right margin
                        if col >= max_content_w:
                            sys.stdout.write(f"\n{Theme.BLOOD}│ {Theme.WHITE}")
                            col = 0
                        sys.stdout.write(ch)
                        col += 1
            sys.stdout.flush()

        if in_code:
            sys.stdout.write(
                f"\n{Theme.DARK_RED}  └{'─' * max(8, width - 4)}{Theme.RESET}"
            )

        latency_ms = int((time.monotonic() - start_time) * 1000)
        footer_tag = f" {latency_ms / 1000:.2f}s "
        footer_dash = max(4, width - len(footer_tag) - 2)
        sys.stdout.write(
            f"\n{Theme.DARK_RED}└{'─' * footer_dash}{Theme.MUTED}{footer_tag}{Theme.RESET}\n"
        )
        sys.stdout.flush()
        return "".join(full_parts).strip(), latency_ms

    def render_ai_response(self, content: str, latency_ms: int = 0) -> None:
        """Render AI markdown-lite response cleanly for mobile terminal screens."""
        width = self.term_width()
        header = " NOBAX AI "
        if latency_ms > 0:
            header += f"({latency_ms / 1000:.2f}s) "
        side = max(4, width - len(header) - 2)
        print(
            f"\n{Theme.BLOOD}┌─{Theme.CRIMSON}{Theme.BOLD}{header}"
            f"{Theme.DARK_RED}{'─' * side}{Theme.RESET}"
        )

        lines = content.splitlines()
        in_code = False

        for raw_line in lines:
            stripped = raw_line.strip()
            if stripped.startswith("```"):
                if not in_code:
                    in_code = True
                    code_lang = stripped[3:].strip().upper() or "CODE"
                    tag = f" {code_lang} "
                    dash = max(4, width - len(tag) - 4)
                    print(
                        f"{Theme.DARK_RED}  ┌─{Theme.SCARLET}{Theme.BOLD}{tag}"
                        f"{Theme.DARK_RED}{'─' * dash}{Theme.RESET}"
                    )
                else:
                    in_code = False
                    print(f"{Theme.DARK_RED}  └{'─' * max(8, width - 4)}{Theme.RESET}")
                continue

            if in_code:
                print(f"{Theme.DARK_RED}  │ {Theme.CYAN}{raw_line}{Theme.RESET}")
            else:
                if not stripped:
                    print()
                    continue
                wrapped = textwrap.wrap(
                    raw_line,
                    width=max(24, width - 3),
                    replace_whitespace=False,
                    drop_whitespace=False,
                )
                for wline in wrapped or [""]:
                    formatted = self._format_inline(wline)
                    print(f"{Theme.BLOOD}│ {Theme.WHITE}{formatted}{Theme.RESET}")

        if in_code:
            print(f"{Theme.DARK_RED}  └{'─' * max(8, width - 4)}{Theme.RESET}")

        print(f"{Theme.DARK_RED}└{'─' * max(8, width - 2)}{Theme.RESET}")

    @staticmethod
    def _format_inline(text: str) -> str:
        text = re.sub(
            r"\*\*(.+?)\*\*",
            f"{Theme.SCARLET}{Theme.BOLD}\1{Theme.RESET}{Theme.WHITE}",
            text,
        )
        text = re.sub(
            r"`([^`]+)`",
            f"{Theme.ROSE}\1{Theme.RESET}{Theme.WHITE}",
            text,
        )
        return text
