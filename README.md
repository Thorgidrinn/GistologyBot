# GistologyBot

Telegram-бот по гистологии.

## Локальный запуск

1. Установите зависимости: `pip install -r requirements.txt`.
2. Задайте переменную окружения `BOT_TOKEN`.
3. Запустите: `python bot.py`.

## Запуск на Render

Бот поддерживает два режима:

- локально — Telegram long polling;
- на Render Web Service — Telegram webhook и HTTP-порт Render.

Для Render Web Service:

- Build Command: `pip install -r requirements.txt`
- Start Command: `python bot.py`
- Environment Variable: `BOT_TOKEN` = токен бота
- Environment Variable: `ALLOWED_USER_IDS` = ID через запятую, например `764620701,123456789`

Render автоматически предоставляет `RENDER_EXTERNAL_URL` и `PORT`, поэтому их вручную задавать не нужно.

Если используется Persistent Disk, добавьте переменную `DATABASE_PATH=/var/data/users.db` и подключите диск с mount path `/var/data`. Важные данные SQLite тогда переживут перезапуски и новые деплои.

Список доступа и статистика хранятся в SQLite-файле `users.db`, который создаётся автоматически при старте. Без Persistent Disk файл на Render будет потерян при перезапуске/новом деплое.

Не добавляйте токен, `users.db` и логи в Git.
