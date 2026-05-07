import base64
from collections.abc import Awaitable, Callable
import json
import logging
import tempfile
import time
import uuid

import httpx
from signalbot import Command, Context, SignalBot  # type: ignore

from .. import config
from ..queue import IncomingMessage, MessageQueue

logger = logging.getLogger(__name__)

_UPLOAD_CHUNK_SIZE = 1024 * 1024


async def send(recipient: str, message: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://{config.SIGNAL_CLI_URL}/v2/send",
            json={"message": message, "number": config.SIGNAL_PHONE_NUMBER, "recipients": [recipient]},
            timeout=15,
        )
        resp.raise_for_status()


async def send_file(recipient: str, file_bytes: bytes, filename: str, content_type: str, caption: str = "") -> None:
    b64 = base64.b64encode(file_bytes).decode()
    payload: dict = {
        "message": caption or " ",  # signal-cli rejects requests with no message even when attachment is present
        "number": config.SIGNAL_PHONE_NUMBER,
        "recipients": [recipient],
        "base64_attachments": [f"data:{content_type};filename={filename};base64,{b64}"],
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://{config.SIGNAL_CLI_URL}/v2/send",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()


async def send_file_from_reader(
    recipient: str,
    read: Callable[[int], Awaitable[bytes]],
    filename: str,
    content_type: str,
    caption: str = "",
) -> None:
    with tempfile.TemporaryFile() as encoded_file:
        b64_size = await _write_base64_encoded(read, encoded_file)
        encoded_file.seek(0)

        marker = f"__SWITCHBOARD_ATTACHMENT_BASE64_{uuid.uuid4().hex}__"
        payload = {
            "message": caption or " ",  # signal-cli rejects requests with no message even when attachment is present
            "number": config.SIGNAL_PHONE_NUMBER,
            "recipients": [recipient],
            "base64_attachments": [f"data:{content_type};filename={filename};base64,{marker}"],
        }
        prefix, suffix = json.dumps(payload).split(marker)
        prefix_bytes = prefix.encode()
        suffix_bytes = suffix.encode()

        async def body_chunks():
            yield prefix_bytes
            while chunk := encoded_file.read(_UPLOAD_CHUNK_SIZE):
                yield chunk
            yield suffix_bytes

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://{config.SIGNAL_CLI_URL}/v2/send",
                content=body_chunks(),
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(prefix_bytes) + b64_size + len(suffix_bytes)),
                },
                timeout=120,
            )
            resp.raise_for_status()


async def _write_base64_encoded(read: Callable[[int], Awaitable[bytes]], encoded_file) -> int:
    pending = b""
    total = 0

    while chunk := await read(_UPLOAD_CHUNK_SIZE):
        chunk = pending + chunk
        remainder = len(chunk) % 3
        if remainder:
            pending = chunk[-remainder:]
            chunk = chunk[:-remainder]
        else:
            pending = b""

        if chunk:
            encoded = base64.b64encode(chunk)
            encoded_file.write(encoded)
            total += len(encoded)

    if pending:
        encoded = base64.b64encode(pending)
        encoded_file.write(encoded)
        total += len(encoded)

    return total


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


async def _load_contacts() -> dict[str, str]:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"http://{config.SIGNAL_CLI_URL}/v1/contacts/{config.SIGNAL_PHONE_NUMBER}",
                timeout=10,
            )
            if resp.status_code != 200:
                return {}
        return {
            c["number"]: (
                c.get("name") or (c.get("profile") or {}).get("given_name") or c.get("profile_name") or ""
            )
            for c in resp.json()
            if c.get("number")
        }
    except Exception:
        logger.warning("Could not load Signal contacts cache", exc_info=True)
        return {}


async def start_signal_consumer(queue: MessageQueue) -> None:
    if not config.SIGNAL_PHONE_NUMBER:
        logger.warning("SIGNAL_PHONE_NUMBER not set — Signal consumer disabled")
        return

    contacts: dict[str, str] = await _load_contacts()

    class _QueueCommand(Command):
        async def handle(self, c: Context):
            msg = c.message
            internal_group_id = msg.group
            text = msg.text
            message_id = str(msg.timestamp)

            sender = msg.source_number or msg.source or ""
            sender_name = contacts.get(sender, "")

            # Resolve internal group UUID → REST-API group ID + name
            group_id: str | None = None
            group_name = ""
            if internal_group_id:
                group_data = getattr(c.bot, "_groups_by_internal_id", {}).get(internal_group_id)
                if group_data:
                    group_id = group_data.get("id")        # group.XXX= format, usable by /send
                    group_name = group_data.get("name", "")
                else:
                    group_id = internal_group_id            # fallback: pass through as-is

            raw = {}
            if msg.raw_message:
                try:
                    raw = json.loads(msg.raw_message)
                except Exception:
                    pass

            await queue.publish(IncomingMessage(
                transport="signal",
                sender=sender,
                sender_name=sender_name,
                recipient=config.SIGNAL_PHONE_NUMBER,
                text=text,
                message_id=message_id,
                timestamp=msg.timestamp // 1000,
                group_id=group_id,
                group_name=group_name,
                raw=raw,
            ))

    bot = SignalBot(
        {"signal_service": config.SIGNAL_CLI_URL, "phone_number": config.SIGNAL_PHONE_NUMBER}
    )
    bot._detect_groups = _safe_detect_groups(bot)  # type: ignore[method-assign]
    bot.register(_QueueCommand())
    await bot._async_post_init()


def _safe_detect_groups(bot):
    original_detect_groups = bot._detect_groups

    async def detect_groups() -> None:
        try:
            await original_detect_groups()
        except Exception:
            bot.groups = []
            bot._groups_by_id = {}
            bot._groups_by_internal_id = {}
            bot._groups_by_name = {}
            logger.warning("Signal group detection failed; continuing without group cache", exc_info=True)

    return detect_groups
