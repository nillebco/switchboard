import logging

from fastapi import APIRouter, Request

from ...queue import MessageQueue
from ...transports.whatsapp import normalize_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp")


@router.post("")
async def handle_whatsapp_webhook(request: Request):
    content_type = request.headers.get("content-type", "")
    if "form" in content_type:
        from urllib.parse import parse_qs
        raw = await request.body()
        parsed = parse_qs(raw.decode())
        body = {k: v[0] for k, v in parsed.items()}
    else:
        body = await request.json()

    incoming = normalize_webhook(body)
    if incoming is None:
        return {"status": "ignored"}

    queue: MessageQueue = request.app.state.queue
    await queue.publish(incoming)
    logger.info("whatsapp webhook queued: %s from %s", incoming.message_id, incoming.sender)
    return {"status": "ok"}
