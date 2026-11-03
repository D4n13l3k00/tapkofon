# Copyright 2022 d4n13l3k00.
# SPDX-License-Identifier: AGPL-3.0-or-later
import html
import re
import shutil
from pathlib import Path

import emoji

from .config import Settings


def replacing_text(text: str, settings: Settings, enabled: bool | None = None) -> str:
    # Templates render this as HTML: escape Telegram content first.
    escaped = html.escape(emoji.demojize(text))
    replace_links = settings.msg_regex_tme if enabled is None else enabled
    if replace_links:

        def local_link(match: re.Match[str]) -> str:
            target = match.expand(settings.msg_regex_to)
            if not target.startswith("/chat/"):
                return html.escape(target)
            return f'<a href="{html.escape(target, quote=True)}">{match.group(0)}</a>'

        escaped = re.sub(settings.msg_replace_regex, local_link, escaped)
    return escaped.replace("\n", "<br>")


def clear_dir(folder: Path) -> None:
    if not folder.exists():
        return
    for path in folder.iterdir():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def get_size(folder: Path) -> int:
    return sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())


def humanize(num: float, suffix: str = "B") -> str:
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi"):
        if abs(num) < 1024 or unit == "Pi":
            return f"{num:.1f}{unit}{suffix}"
        num /= 1024
    raise AssertionError("Unreachable")


def cache_tree(folder: Path, prefix: str = "") -> str:
    if not folder.exists():
        return ""
    lines = []
    children = sorted(folder.iterdir(), key=lambda path: path.name.lower())
    for index, path in enumerate(children):
        last = index == len(children) - 1
        lines.append(f"{prefix}{'└──' if last else '├──'} {path.name}")
        if path.is_dir() and not path.is_symlink():
            lines.append(cache_tree(path, prefix + ("    " if last else "│   ")))
    return "\n".join(lines)
