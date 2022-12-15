# Copyright 2022 d4n13l3k00.
# SPDX-License-Identifier: 	AGPL-3.0-or-later
from pathlib import Path

import toml


class Config:
    def __init__(self):
        self.config_path = Path.cwd().parent / "session" / "config.toml"
        self.default_config = {
            "api_id": 8,
            "api_hash": "7245de8e747a0d6fbe11f7cc14fcc0bb",
            "passwd": "",
            "pic_quality": 80,
            "pic_max_size": 256,
            "pic_format": "jpeg",
            "pic_avatar_max_size": 256,
            "msg_regex_tme": True,
            "msg_replace_regex": r"(https?://)?t\.me/(?P<chat>[A-Za-z0-9-_]{3,20})/?\d*",
            "msg_regex_to": r"/chat/\g<chat>",
            "recognize_lang": "ru-RU",
        }

        self.config = self.default_config

        if not Path(self.config_path).exists():
            with self.config_path.open("w") as f:
                toml.dump(self.default_config, f)
        else:
            with self.config_path.open("r") as f:
                self.config = toml.load(f)

        for key, value in self.config.items():
            if key in self.config:
                setattr(self, key, value)
            else:
                raise KeyError(f"Unknown key: {key}")
