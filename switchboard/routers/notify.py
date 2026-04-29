from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from .. import config
from ..transports import signal, telegram, whatsapp

router = APIRouter(prefix="/notify")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _require_api_key(api_key: str = Depends(_api_key_header)):
    if not config.API_KEY or api_key != config.API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


class NotifyRequest(BaseModel):
    message: str


@router.post("", dependencies=[Depends(_require_api_key)])
async def notify(
    body: NotifyRequest,
    transport: Literal["signal", "telegram", "whatsapp"] = "signal",
):
    if transport == "telegram":
        chat_id = config.NOTIFY_TELEGRAM_CHAT_ID
        if not chat_id:
            raise HTTPException(status_code=424, detail="NOTIFY_TELEGRAM_CHAT_ID not configured")
        await telegram.send(chat_id, body.message)
        return {"status": "ok", "recipient": chat_id, "transport": "telegram"}

    if transport == "whatsapp":
        number = config.NOTIFY_WHATSAPP_NUMBER
        if not number:
            raise HTTPException(status_code=424, detail="NOTIFY_WHATSAPP_NUMBER not configured")
        await whatsapp.send(number, body.message)
        return {"status": "ok", "recipient": number, "transport": "whatsapp"}

    recipient = config.NOTIFY_SIGNAL_GROUP_ID or config.NOTIFY_SIGNAL_PHONE
    if not recipient:
        raise HTTPException(status_code=424, detail="NOTIFY_SIGNAL_GROUP_ID or NOTIFY_SIGNAL_PHONE not configured")
    await signal.send(recipient, body.message)
    return {"status": "ok", "recipient": recipient, "transport": "signal"}
