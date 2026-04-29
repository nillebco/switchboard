import base64
import logging
import time

import httpx

from .. import config
from ..queue import IncomingMessage

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {"token": config.WUZAPI_TOKEN}


def _phone_field(recipient: str) -> str:
    if recipient.endswith("@g.us"):
        return recipient
    return recipient.split("@")[0].split(":")[0].lstrip("+")


async def send(recipient: str, message: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://{config.WUZAPI_URL}/chat/send/text",
            headers=_headers(),
            json={"Phone": _phone_field(recipient), "Body": message},
            timeout=15,
        )
        resp.raise_for_status()


async def send_file(recipient: str, file_bytes: bytes, filename: str, content_type: str, caption: str = "") -> None:
    b64 = base64.b64encode(file_bytes).decode()
    phone = _phone_field(recipient)
    if content_type.startswith("image/"):
        endpoint, payload = "/chat/send/image", {"Phone": phone, "Image": b64, "Caption": caption}
    elif content_type.startswith("audio/"):
        endpoint, payload = "/chat/send/audio", {"Phone": phone, "Audio": b64}
    elif content_type.startswith("video/"):
        endpoint, payload = "/chat/send/video", {"Phone": phone, "Video": b64, "Caption": caption}
    else:
        endpoint, payload = "/chat/send/document", {"Phone": phone, "Document": b64, "FileName": filename, "Caption": caption}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://{config.WUZAPI_URL}{endpoint}",
            headers=_headers(),
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()


async def list_contacts() -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://{config.WUZAPI_URL}/user/contacts",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    contacts = resp.json().get("data", {})
    return [
        {
            "id": jid,
            "name": info.get("FullName") or info.get("PushName") or info.get("BusinessName") or "",
        }
        for jid, info in contacts.items()
        if info.get("Found")
    ]


async def list_groups() -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"http://{config.WUZAPI_URL}/group/list",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    groups = resp.json().get("data", {}).get("Groups", [])
    return [
        {"id": g.get("JID"), "name": g.get("Name"), "participants": g.get("Participants")}
        for g in groups
    ]


def normalize_webhook(body: dict) -> IncomingMessage | None:
    json_data = body.get("jsonData", {})
    if isinstance(json_data, str):
        import json
        try:
            json_data = json.loads(json_data)
        except Exception:
            return None

    event = json_data.get("event", {})
    if not event or json_data.get("type") != "Message" and event.get("type") != "Message":
        return None

    info = event.get("Info", {})
    message = event.get("Message", {})

    if info.get("IsFromMe"):
        return None

    sender = info.get("Sender", "") or info.get("SenderAlt", "")
    if not sender:
        return None

    chat = info.get("Chat", "")
    group_id = chat if chat.endswith("@g.us") else None

    text = (
        message.get("conversation")
        or (message.get("extendedTextMessage") or {}).get("text")
        or (message.get("imageMessage") or {}).get("caption")
        or (message.get("documentMessage") or {}).get("caption")
    )

    number = sender.split("@")[0].split(":")[0]
    source = f"+{number}"

    return IncomingMessage(
        transport="whatsapp",
        sender=source,
        recipient=config.WUZAPI_TOKEN,
        text=text,
        message_id=info.get("ID", str(int(time.time()))),
        timestamp=info.get("Timestamp", int(time.time())),
        group_id=group_id,
        raw=body,
    )
