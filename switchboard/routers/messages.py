from urllib.parse import quote

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from .auth import require_api_key
from .. import config
from ..queue import IncomingMessage
from ..transports import whatsapp

router = APIRouter(prefix="/messages", dependencies=[Depends(require_api_key)])


@router.get("/{message_ref}/attachments")
async def list_message_attachments(message_ref: str):
    message = await _load_message(message_ref)
    return {
        "message_id": message.message_id,
        "stream_id": message_ref if "-" in message_ref else None,
        "transport": message.transport,
        "attachments": _attachments_for(message),
    }


@router.get("/{message_ref}/attachments/{attachment_index}")
async def get_message_attachment(message_ref: str, attachment_index: int):
    message = await _load_message(message_ref)
    if message.transport != "whatsapp":
        raise HTTPException(status_code=501, detail=f"Attachment download is not implemented for {message.transport}")

    try:
        attachment = await whatsapp.download_attachment(message.raw, attachment_index)
    except IndexError:
        raise HTTPException(status_code=404, detail="Attachment not found")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not download attachment: {exc}") from exc

    filename = quote(attachment.filename)
    return Response(
        content=attachment.content,
        media_type=attachment.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


def _attachments_for(message: IncomingMessage) -> list[dict]:
    if message.transport == "whatsapp":
        return [attachment.__dict__ for attachment in whatsapp.list_attachments(message.raw)]
    return []


async def _load_message(message_ref: str) -> IncomingMessage:
    redis = aioredis.from_url(config.REDIS_URL, decode_responses=False)
    try:
        if "-" in message_ref:
            rows = await redis.xrange("switchboard:incoming", min=message_ref, max=message_ref, count=1)
            if rows:
                return IncomingMessage.from_redis_fields(rows[0][1])
        else:
            rows = await redis.xrevrange("switchboard:incoming", count=1000)
            for _entry_id, fields in rows:
                if fields.get(b"message_id", b"").decode() == message_ref:
                    return IncomingMessage.from_redis_fields(fields)
    finally:
        await redis.aclose()

    raise HTTPException(status_code=404, detail="Message not found")
