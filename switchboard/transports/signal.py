import logging
import time

import httpx
from signalbot import Command, Context, SignalBot  # type: ignore

from .. import config
from ..queue import IncomingMessage, MessageQueue

logger = logging.getLogger(__name__)


async def send(recipient: str, message: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://{config.SIGNAL_CLI_URL}/v2/send",
            json={"message": message, "number": config.SIGNAL_PHONE_NUMBER, "recipients": [recipient]},
            timeout=15,
        )
        resp.raise_for_status()


async def list_groups() -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://{config.SIGNAL_CLI_URL}/v1/groups/{config.SIGNAL_PHONE_NUMBER}",
            timeout=10,
        )
        resp.raise_for_status()
    return [
        {"id": g.get("id"), "name": g.get("name"), "members": g.get("members", [])}
        for g in resp.json()
    ]


async def list_contacts() -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://{config.SIGNAL_CLI_URL}/v1/contacts/{config.SIGNAL_PHONE_NUMBER}",
            timeout=10,
        )
        resp.raise_for_status()
    return [
        {
            "number": c.get("number"),
            "name": c.get("name") or (c.get("profile") or {}).get("given_name") or c.get("profile_name") or "",
            "username": c.get("username") or "",
        }
        for c in resp.json()
        if c.get("number")
    ]


async def start_signal_consumer(queue: MessageQueue) -> None:
    if not config.SIGNAL_PHONE_NUMBER:
        logger.warning("SIGNAL_PHONE_NUMBER not set — Signal consumer disabled")
        return

    class _QueueCommand(Command):
        async def handle(self, c: Context):
            msg = c.message
            source = getattr(msg, "source", None) or getattr(msg, "sender", None)
            group_id = getattr(msg, "group", None)
            text = getattr(msg, "text", None)
            message_id = getattr(msg, "timestamp", str(int(time.time())))

            incoming = IncomingMessage(
                transport="signal",
                sender=str(source or ""),
                recipient=config.SIGNAL_PHONE_NUMBER,
                text=text,
                message_id=str(message_id),
                timestamp=int(time.time()),
                group_id=group_id,
                raw={},
            )
            await queue.publish(incoming)

    bot = SignalBot(
        {"signal_service": config.SIGNAL_CLI_URL, "phone_number": config.SIGNAL_PHONE_NUMBER}
    )
    bot.register(_QueueCommand())
    await bot._async_post_init()
