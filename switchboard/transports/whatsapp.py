import base64
from dataclasses import dataclass
from datetime import datetime
import logging
import time
from typing import Any

import httpx

from .. import config
from ..queue import IncomingMessage

logger = logging.getLogger(__name__)

_MEDIA_MESSAGE_TYPES = {
    "audioMessage": ("audio", "/chat/downloadaudio"),
    "documentMessage": ("document", "/chat/downloaddocument"),
    "imageMessage": ("image", "/chat/downloadimage"),
    "stickerMessage": ("sticker", "/chat/downloadsticker"),
    "videoMessage": ("video", "/chat/downloadvideo"),
}


@dataclass(frozen=True)
class Attachment:
    index: int
    kind: str
    content_type: str
    filename: str
    size: int | None
    duration_seconds: int | None = None


@dataclass(frozen=True)
class DownloadedAttachment:
    content: bytes
    content_type: str
    filename: str


def _headers() -> dict:
    return {"token": config.WUZAPI_TOKEN}


def _phone_field(recipient: str) -> str:
    if recipient.endswith("@g.us"):
        return recipient
    return recipient.split("@")[0].split(":")[0].lstrip("+")


def list_attachments(raw: dict[str, Any]) -> list[Attachment]:
    event = _event_from_raw(raw)
    info = event.get("Info", {})
    message = event.get("Message", {})
    attachments: list[Attachment] = []

    for key, (kind, _endpoint) in _MEDIA_MESSAGE_TYPES.items():
        media = message.get(key)
        if not isinstance(media, dict):
            continue
        content_type = media.get("mimetype") or "application/octet-stream"
        filename = (
            media.get("fileName")
            or media.get("filename")
            or _default_filename(info.get("ID", "attachment"), kind, content_type)
        )
        attachments.append(
            Attachment(
                index=len(attachments),
                kind=kind,
                content_type=content_type,
                filename=filename,
                size=media.get("fileLength"),
                duration_seconds=media.get("seconds"),
            )
        )

    return attachments


async def download_attachment(raw: dict[str, Any], index: int) -> DownloadedAttachment:
    event = _event_from_raw(raw)
    info = event.get("Info", {})
    message = event.get("Message", {})
    current_index = 0

    for key, (kind, endpoint) in _MEDIA_MESSAGE_TYPES.items():
        media = message.get(key)
        if not isinstance(media, dict):
            continue
        if current_index != index:
            current_index += 1
            continue

        payload = _download_payload(media)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"http://{config.WUZAPI_URL}{endpoint}",
                headers=_headers(),
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()

        data = resp.json().get("data", {})
        content_type = data.get("Mimetype") or media.get("mimetype") or "application/octet-stream"
        data_url = data.get("Data")
        if not isinstance(data_url, str) or "," not in data_url:
            raise ValueError("Wuzapi response did not include attachment data")

        filename = (
            media.get("fileName")
            or media.get("filename")
            or _default_filename(info.get("ID", "attachment"), kind, content_type)
        )
        return DownloadedAttachment(
            content=base64.b64decode(data_url.split(",", 1)[1]),
            content_type=content_type,
            filename=filename,
        )

    raise IndexError("attachment not found")


def _event_from_raw(raw: dict[str, Any]) -> dict[str, Any]:
    json_data = raw.get("jsonData", {})
    if isinstance(json_data, str):
        import json

        json_data = json.loads(json_data)
    return json_data.get("event", {}) if isinstance(json_data, dict) else {}


def _download_payload(media: dict[str, Any]) -> dict[str, Any]:
    return {
        "Url": media.get("URL", ""),
        "DirectPath": media.get("directPath", ""),
        "MediaKey": media.get("mediaKey", ""),
        "Mimetype": media.get("mimetype", "application/octet-stream"),
        "FileEncSHA256": media.get("fileEncSHA256", ""),
        "FileSHA256": media.get("fileSHA256", ""),
        "FileLength": media.get("fileLength", 0),
    }


def _default_filename(message_id: str, kind: str, content_type: str) -> str:
    extension = {
        "audio/ogg": "ogg",
        "audio/mpeg": "mp3",
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "video/mp4": "mp4",
    }.get(content_type.split(";", 1)[0], "bin")
    return f"{message_id or 'attachment'}-{kind}.{extension}"


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
    data_uri = f"data:{content_type};base64,{base64.b64encode(file_bytes).decode()}"
    phone = _phone_field(recipient)
    if content_type.startswith("image/"):
        endpoint, payload = "/chat/send/image", {"Phone": phone, "Image": data_uri, "Caption": caption}
    elif content_type.startswith("audio/"):
        endpoint, payload = "/chat/send/audio", {"Phone": phone, "Audio": data_uri}
    elif content_type.startswith("video/"):
        endpoint, payload = "/chat/send/video", {"Phone": phone, "Video": data_uri, "Caption": caption}
    else:
        endpoint, payload = "/chat/send/document", {"Phone": phone, "Document": data_uri, "FileName": filename, "Caption": caption}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"http://{config.WUZAPI_URL}{endpoint}",
            headers=_headers(),
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()


async def ensure_webhook() -> None:
    if not config.WUZAPI_TOKEN or not config.WUZAPI_WEBHOOK_URL:
        return
    async with httpx.AsyncClient() as client:
        try:
            current = await client.get(
                f"http://{config.WUZAPI_URL}/webhook",
                headers=_headers(),
                timeout=5,
            )
            current.raise_for_status()
            data = current.json().get("data", {}) or {}
            if data.get("webhook") == config.WUZAPI_WEBHOOK_URL and "Message" in (data.get("subscribe") or []):
                return
            resp = await client.post(
                f"http://{config.WUZAPI_URL}/webhook",
                headers=_headers(),
                json={"WebhookURL": config.WUZAPI_WEBHOOK_URL, "Events": ["Message"]},
                timeout=5,
            )
            resp.raise_for_status()
            logger.info("wuzapi webhook registered: %s", config.WUZAPI_WEBHOOK_URL)
        except Exception:
            logger.warning("Failed to register wuzapi webhook", exc_info=True)


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
        timestamp=_parse_timestamp(info.get("Timestamp")),
        group_id=group_id,
        raw=body,
    )


def _parse_timestamp(value) -> int:
    if not value:
        return int(time.time())
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except ValueError:
        return int(datetime.fromisoformat(value).timestamp())
