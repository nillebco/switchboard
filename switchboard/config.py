import os

SIGNAL_CLI_URL: str = os.environ.get("SIGNAL_CLI_URL", "localhost:8080")
SIGNAL_PHONE_NUMBER: str = os.environ.get("SIGNAL_PHONE_NUMBER", "")

TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_TOKEN", "")

WUZAPI_URL: str = os.environ.get("WUZAPI_URL", "localhost:8080")
WUZAPI_TOKEN: str = os.environ.get("WUZAPI_TOKEN", "")

REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379")

API_KEY: str = os.environ.get("API_KEY", "")

NOTIFY_SIGNAL_GROUP_ID: str = os.environ.get("NOTIFY_SIGNAL_GROUP_ID", "")
NOTIFY_SIGNAL_PHONE: str = os.environ.get("NOTIFY_SIGNAL_PHONE", "")
NOTIFY_WHATSAPP_NUMBER: str = os.environ.get("NOTIFY_WHATSAPP_NUMBER", "")
NOTIFY_TELEGRAM_CHAT_ID: str = os.environ.get("NOTIFY_TELEGRAM_CHAT_ID", "")
