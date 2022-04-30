# Copyright 2022 d4n13l3k00.
# SPDX-License-Identifier: 	AGPL-3.0-or-later

import os
import re
import shutil
from pathlib import Path

import emoji

import config


def replacing_text(text: str):
    return (
        re.sub(
            config.msg_replace_regex,
            config.msg_regex_to,
            emoji.demojize(text.replace("\n", "<br>")),
        )
        if config.msg_regex_tme
        else emoji.demojize(text.replace("\n", "<br>"))
    )


class DisplayablePath:
    display_filename_prefix_middle = "├──"
    display_filename_prefix_last = "└──"
    display_parent_prefix_middle = "    "
    display_parent_prefix_last = "│   "

    def __init__(self, path, parent_path, is_last):
        self.path = Path(str(path))
        self.parent = parent_path
        self.is_last = is_last
        self.depth = self.parent.depth + 1 if self.parent else 0

    @property
    def displayname(self):
        return f"{self.path.name}/" if self.path.is_dir() else self.path.name

    @classmethod
    def make_tree(cls, root, parent=None, is_last=False, criteria=None):
        root = Path(str(root))
        criteria = criteria or cls._default_criteria

        displayable_root = cls(root, parent, is_last)
        yield displayable_root

        children = sorted(
            [path for path in root.iterdir() if criteria(path)],
            key=lambda s: str(s).lower(),
        )
        for count, path in enumerate(children, start=1):
            is_last = count == len(children)
            if path.is_dir():
                yield from cls.make_tree(
                    path, parent=displayable_root, is_last=is_last, criteria=criteria
                )
            else:
                yield cls(path, displayable_root, is_last)

    @classmethod
    def _default_criteria(cls, path):
        return True

    @property
    def displayname(self):
        return f"{self.path.name}/" if self.path.is_dir() else self.path.name

    def displayable(self):
        if self.parent is None:
            return self.displayname

        _filename_prefix = (
            self.display_filename_prefix_last
            if self.is_last
            else self.display_filename_prefix_middle
        )

        parts = ["{!s} {!s}".format(_filename_prefix, self.displayname)]

        parent = self.parent
        while parent and parent.parent is not None:
            parts.append(
                self.display_parent_prefix_middle
                if parent.is_last
                else self.display_parent_prefix_last
            )
            parent = parent.parent

        return "".join(reversed(parts))


def clear_dir(folder):
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")


def get_size(start_path="."):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


def humanize(num: float, suffix: str = "B") -> str:
    for unit in ["", "Ki", "Mi", "Gi"]:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s"
