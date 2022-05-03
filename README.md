
<div align="center">

# 👞 Tapkofon
![Telegram](https://img.shields.io/badge/Telegram-blue?style=flat&logo=telegram)
[![DeepSource](https://deepsource.io/gh/D4n13l3k00/tapkofon.svg/?label=resolved+issues)](https://deepsource.io/gh/D4n13l3k00/tapkofon/?ref=repository-badge)
![CodeStyle](https://img.shields.io/badge/code%20style-black-black)
![GitHub contributors](https://img.shields.io/github/contributors/D4n13l3k00/tapkofon)
![GitHub](https://img.shields.io/github/license/D4n13l3k00/tapkofon)

</div>


### Представляю вам свой мини-проект Tapkofon - минималистичный веб-клиент Telegram'а на Telethon, FastAPI, сделанный преимущественно для кнопочных телефонов

[Идея взята отсюда](https://github.com/xadjilut/microclient)

## 🔻 Установка

### 1. Установите Python 🐍

[Python](https://www.python.org/downloads/)

### 2. Клонируйте репозиторий 📩

Клонируйте репозиторий

```bash
git clone https://github.com/D4n13l3k00/tapkofon
cd tapkofon
```

### 3. Установите зависимости 📦

```bash
apt install ffmpeg -y

python3 -m pip install --user -r requirements.txt
```

### 4. Запуск 🚀

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Клиент будет доступен на порту `8000` (вы можете изменить его на любой другой)

Документация API на `/docs`

### 5? Докер 🐳

Билд: `docker build -t tapik .`

Создаём volume для сохранения сессии: `docker volume create tapik`

Запуск: `docker run -itd -p 8888:8888 -v tapik:/root tapik`

Так же доступен деплой на [Okteto](https://cloud.okteto.com/#/deploy?repository=https://github.com/D4n13l3k00/tapkofon)

### 💖 Фишки

- Пароль доступа (cookie) ([config.py](/config.py)). Пароль по умолчанию выключен, но вы можете его включить в конфиге.
- Система кэша (при загрузке файла он скачивается на сервер в кэш директорию, и оттуда отправляется вам)
- Конвертирование не mp3 аудио в mp3 для лучшей совместимости
- Распознавание речи в голосовых сообщениях
- Подгонка фото под определённый размер и сжатие([config.py](/config.py)) для лучшей совместимости
- Смайлики в сообщениях превращаются в текст (тапики не поддерживают соверменные юникод смайлики)
- Возможность просмотра профиля пользователя(аватарка, юзерка , био)

### 😢 Баги

- Не работает авторизация при включённом облачном пароле (только в вебе) (кто починит - буду благодарен)
- Если найдешь баг, [пиши сюда](https://t.me/D4n13l3k00)
