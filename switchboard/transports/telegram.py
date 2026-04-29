import io
import logging
import time

from telebot import async_telebot as telebot  # type: ignore
from telebot.types import Message  # type: ignore

from .. import config
from ..queue import IncomingMessage, MessageQueue

logger = logging.getLogger(__name__)


async def send(chat_id: str | int, message: str) -> None:
    token = config.TELEGRAM_TOKEN
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN not configured")
    bot = telebot.AsyncTeleBot(token)
    try:
        await bot.send_message(int(chat_id), message)
    finally:
        await bot.close_session()


async def send_file(chat_id: str | int, file_bytes: bytes, filename: str, content_type: str, caption: str = "") -> None:
    token = config.TELEGRAM_TOKEN
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN not configured")
    bot = telebot.AsyncTeleBot(token)
    try:
        buf = io.BytesIO(file_bytes)
        buf.name = filename
        if content_type.startswith("image/"):
            await bot.send_photo(int(chat_id), buf, caption=caption or None)
        elif content_type.startswith("audio/"):
            await bot.send_audio(int(chat_id), buf, caption=caption or None)
        elif content_type.startswith("video/"):
            await bot.send_video(int(chat_id), buf, caption=caption or None)
        else:
            await bot.send_document(int(chat_id), buf, caption=caption or None)
    finally:
        await bot.close_session()


async def start_telegram_consumer(queue: MessageQueue) -> None:
    token = config.TELEGRAM_TOKEN
    if not token:
        logger.warning("TELEGRAM_TOKEN not set — Telegram consumer disabled")
        return

    bot = telebot.AsyncTeleBot(token, parse_mode=None)

    @bot.message_handler(
        content_types=["audio", "photo", "voice", "video", "document", "text", "location", "contact", "sticker"]
    )
    async def _handle(message: Message):
        if message.from_user and message.from_user.is_bot:
            return

        text = message.text or message.caption or None
        source = str(message.from_user.id) if message.from_user else ""
        group_id = str(message.chat.id) if message.chat.type in ("group", "supergroup") else None

        incoming = IncomingMessage(
            transport="telegram",
            sender=source,
            recipient="@bot",
            text=text,
            message_id=str(message.message_id),
            timestamp=message.date or int(time.time()),
            group_id=group_id,
            raw=message.json,
        )
        try:
            await queue.publish(incoming)
        except Exception:
            logger.exception("Failed to publish Telegram message to queue")

    await bot.polling(timeout=500, request_timeout=600)
