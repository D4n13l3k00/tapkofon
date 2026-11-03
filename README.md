<div align="center">

# 👞 Tapkofon

![Telegram](https://img.shields.io/badge/Telegram-blue?style=flat&logo=telegram)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-Ruff-D7FF64)](https://docs.astral.sh/ruff/)
![GitHub contributors](https://img.shields.io/github/contributors/D4n13l3k00/tapkofon)
![GitHub license](https://img.shields.io/github/license/D4n13l3k00/tapkofon)

[![Checks](https://github.com/D4n13l3k00/tapkofon/actions/workflows/ci.yml/badge.svg)](https://github.com/D4n13l3k00/tapkofon/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/D4n13l3k00/tapkofon)](https://github.com/D4n13l3k00/tapkofon/releases/latest)

### Представляю вам свой мини-проект **Tapkofon** - минималистичный веб-клиент Telegram'а на Telethon, FastAPI, сделанный преимущественно для кнопочных телефонов

</div>

Минималистичный веб-клиент Telegram для кнопочных телефонов и медленного интернета.
Обычный HTML, формы и cookies, без JavaScript. Работает на Telethon и FastAPI.
[Идея microclient](https://github.com/xadjilut/microclient).

---

### 📜 Для чего это / Где это можно использовать?

- Когда доступ только к кнопочному телефону `(ex. Гос.служба)`
- Устройство, поддерживающее только html и куки `(ex. Кнопочные телефоны)`
- Место с очень низкой скоростью интернета
- Для постоянного использования (мазохизм)

---

### 💖 Фишки

- Вход по номеру или QR, включая облачный пароль.
- Чаты, ответы, редактирование и удаление сообщений, вложения.
- Непрочитанные и избранные чаты, черновики и быстрые ответы.
- Кэш файлов, сжатие фото и аватарок, текстовый режим.
- Конвертация аудио в MP3 и распознавание речи через Google. Распознавание можно отключить.
- Смайлики превращаются в текст (тапики не поддерживают современные юникод смайлики).
- Просмотр профиля пользователя (аватарка, юзерка, био).
- Пароль доступа к клиенту.

---

### 😢 Баги (куда же без багов?)

Если найдешь баг, [пиши сюда](https://t.me/D4n13l3k00).

---

## 🔝 Быстрый старт

Рекомендуется [uv](https://docs.astral.sh/uv/getting-started/installation/). Он установит приложение в отдельное окружение и при необходимости скачает Python 3.14.

```console
uv tool install --python 3.14 https://github.com/D4n13l3k00/tapkofon/releases/download/v2.0.0/tapkofon-2.0.0-py3-none-any.whl
tapkofon
```

Откройте <http://127.0.0.1:8888>. При первом запуске создаётся `session/config.toml`. Остановите сервер, укажите в нём свои `api_id` и `api_hash` из [my.telegram.org/apps](https://my.telegram.org/apps), затем запустите снова и войдите в Telegram.

Если команда не найдена, выполните `uv tool update-shell` и откройте новый терминал. В PyPI пакет не опубликован, установка идёт из GitHub Releases.

---

## 🔻 Установка

### Через pipx 📦

Нужны [pipx](https://pipx.pypa.io/stable/installation/) и установленный Python 3.12 или новее. Пример для Python 3.14:

```console
pipx install --python 3.14 https://github.com/D4n13l3k00/tapkofon/releases/download/v2.0.0/tapkofon-2.0.0-py3-none-any.whl
tapkofon
```

Если pipx не находит Python, укажите путь к интерпретатору вместо `3.14`. Если не найдена команда `tapkofon`, выполните `pipx ensurepath` и откройте новый терминал.

Установка через **pip не рекомендуется**. Если используете его, устанавливайте wheel из [релиза](https://github.com/D4n13l3k00/tapkofon/releases/latest) только в отдельный venv, не в системный Python.

---

### FFmpeg

Для конвертации аудио и распознавания речи нужен FFmpeg в `PATH`:

- Linux: `sudo apt install ffmpeg`
- Windows: `winget install Gyan.FFmpeg`
- macOS: `brew install ffmpeg`

---

### Запуск 🚀

```console
tapkofon                              # запуск на localhost:8888
tapkofon serve --host 0.0.0.0          # доступ с телефона
tapkofon password set                 # пароль доступа
tapkofon login --qr                   # вход из терминала при остановленном сервере
tapkofon --help                       # остальные команды
```

Перед доступом извне задайте пароль. Для интернета используйте HTTPS и `cookie_secure = true` в конфиге. Один экземпляр приложения работает с одним Telegram-аккаунтом. Не запускайте несколько workers с одной сессией.

---

### Сессия и настройки

Данные лежат в `session/` относительно папки запуска. Для постоянного пути задайте `TAPKOFON_DATA_DIR` или `--data-dir` перед подкомандой:

```console
tapkofon --data-dir "C:/Users/USERNAME/AppData/Local/tapkofon" serve
```

В примере замените `USERNAME` своим именем пользователя. Для всех команд используйте тот же каталог.

- `config.toml`: Telegram API и серверные параметры. После изменения перезапустите сервер.
- `session.session`: авторизация Telegram. Не передавайте этот файл другим.
- `tapkofon.sqlite3`: настройки, черновики, избранное и веб-сессии.
- `cache/`: скачанные файлы.

Настройки клиента доступны в вебе, общие настройки и пароль на `/admin`. Базы не зашифрованы, поэтому закройте посторонним доступ к каталогу данных.

---

### Обновление

Остановите сервер и сохраните копию каталога данных. Повторите команду установки с `--force` и ссылкой на wheel нужного [релиза](https://github.com/D4n13l3k00/tapkofon/releases). Запустите приложение с прежним каталогом данных.

Старый `run.sh` заменён командой `tapkofon`. Изменения версии перечислены в [CHANGELOG.md](CHANGELOG.md).

---

### 5? Докер 🐳

```console
git clone https://github.com/D4n13l3k00/tapkofon.git
cd tapkofon
docker compose up --build -d
```

Порт по умолчанию `127.0.0.1:8888`, данные в `./session/`. На Linux перед запуском создайте каталог с правами для UID 1000: `mkdir -p session && sudo chown 1000:1000 session`.

Пароль: `docker compose exec tapkofon tapkofon password set`.

---

## Разработка

В клонированном репозитории:

```console
uv sync --locked
uv run tapkofon serve --reload
uv run ruff check .
uv run pyright
uv run pytest -q
uv build
```

---

### P.S 🤫

Не забудьте свои `api_id` и `api_hash`. Без них вход в Telegram не заработает.

---

# Лицензия

[AGPL-3.0-or-later](LICENSE)
