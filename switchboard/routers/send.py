from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from .. import config
from ..transports import signal, telegram, whatsapp

router = APIRouter(prefix="/send")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _require_api_key(api_key: str = Depends(_api_key_header)):
    if not config.API_KEY or api_key != config.API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


class SendRequest(BaseModel):
    recipient: str
    message: str


@router.post("", dependencies=[Depends(_require_api_key)])
async def send(
    body: SendRequest,
    transport: Literal["signal", "telegram", "whatsapp"] = "signal",
):
    if transport == "telegram":
        await telegram.send(body.recipient, body.message)
    elif transport == "whatsapp":
        await whatsapp.send(body.recipient, body.message)
    else:
        await signal.send(body.recipient, body.message)
    return {"status": "ok", "recipient": body.recipient, "transport": transport}


@router.post("/file", dependencies=[Depends(_require_api_key)])
async def send_file(
    transport: Literal["signal", "telegram", "whatsapp"] = "signal",
    recipient: str = Form(...),
    caption: str = Form(""),
    file: UploadFile = File(...),
):
    file_bytes = await file.read()
    filename = file.filename or "file"
    content_type = file.content_type or "application/octet-stream"
    if transport == "telegram":
        await telegram.send_file(recipient, file_bytes, filename, content_type, caption)
    elif transport == "whatsapp":
        await whatsapp.send_file(recipient, file_bytes, filename, content_type, caption)
    else:
        await signal.send_file(recipient, file_bytes, filename, content_type, caption)
    return {"status": "ok", "recipient": recipient, "transport": transport, "filename": filename}


@router.get("/groups", dependencies=[Depends(_require_api_key)])
async def list_groups(transport: Literal["signal", "whatsapp"] = "signal"):
    if transport == "whatsapp":
        return await whatsapp.list_groups()
    return await signal.list_groups()


@router.get("/contacts", dependencies=[Depends(_require_api_key)])
async def list_contacts(transport: Literal["signal", "whatsapp"] = "signal"):
    if transport == "whatsapp":
        return await whatsapp.list_contacts()
    return await signal.list_contacts()
