# Конфигурация бота.
# На Render задайте BOT_TOKEN в Environment Variables.
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "Переменная окружения BOT_TOKEN не задана. "
        "Укажите токен бота в настройках окружения."
    )

# Единственный администратор (его user_id)
ADMIN_USER_ID = 764620701


def _parse_allowed_user_ids(value):
    """Прочитать Telegram ID из строки вида: 123,456,789."""
    user_ids = set()
    for raw_user_id in value.split(','):
        raw_user_id = raw_user_id.strip()
        if not raw_user_id:
            continue
        try:
            user_id = int(raw_user_id)
        except ValueError:
            continue
        if user_id > 0:
            user_ids.add(user_id)
    return user_ids


# Задайте в Render через Environment Variables, например:
# ALLOWED_USER_IDS=764620701,123456789,987654321
ALLOWED_USER_IDS = _parse_allowed_user_ids(
    os.environ.get("ALLOWED_USER_IDS", "")
)

# Render автоматически предоставляет RENDER_EXTERNAL_URL для Web Service.
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "telegram-webhook")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")

# Убраны все настройки токенов и рефералов
