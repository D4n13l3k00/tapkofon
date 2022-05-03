# Copyright 2022 d4n13l3k00.
# SPDX-License-Identifier: 	AGPL-3.0-or-later

import hashlib
import time

###############################
### /  Настройки  защиты  / ###
#    Желательно   изменить    #
###############################
passwd: str or None = None  # '1234'   # ! Код доступа (None - отключить)
access_cookie: str = hashlib.md5(
    str(time.time()).encode()  # ! Куки для доступа
).hexdigest()


###############################
### / Настройки  загрузок / ###
#   Изменять не обязательно   #
###############################
pic_quality: int = 80  # ? Качество катринки в % (для jpeg)
pic_max_size: int = 256  # ? Максимальная ширина/высота картинки в px
pic_format: str = "jpeg"  # ? Большинство тапиков едят только jpeg и gif
pic_avatar_max_size: int = 256  # ? Максимальная ширина/высота аватарки в px

###############################
### / Настройки сообщений / ###
#   Изменять не обязательно   #
###############################
# ? Замена t.me/*, t.me/*/id на /chat/*
msg_regex_tme: bool = True
# ? Регулярное выражение для поиска ссылок
msg_replace_regex: str = r"(https?://)?t\.me/(?P<chat>[A-Za-z0-9-_]{3,20})/?\d*"
# ? Замена на локал. ссылки
msg_regex_to: str = r"/chat/\g<chat>"
# ? Язык распознавания речи
recognize_lang = "ru-RU"

###############################
### / Настройки  Telethon / ###
#   Изменять не обязательно   #
###############################
api_id: int = 8  # ! API_ID
api_hash: str = "7245de8e747a0d6fbe11f7cc14fcc0bb"  # ! API_HASH
