from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from .auth import require_api_key
from ..transports import signal, telegram, whatsapp

router = APIRouter(prefix="/send")


class SendRequest(BaseModel):
    recipient: str
    message: str


@router.post("", dependencies=[Depends(require_api_key)])
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


@router.post("/file", dependencies=[Depends(require_api_key)])
async def send_file(
    transport: Literal["signal", "telegram", "whatsapp"] = "signal",
    recipient: str = Form(...),
    caption: str = Form(""),
    file: UploadFile = File(...),
):
    filename = file.filename or "file"
    content_type = file.content_type or "application/octet-stream"
    if transport == "signal":
        await signal.send_file_from_reader(recipient, file.read, filename, content_type, caption)
    elif transport == "telegram":
        file_bytes = await file.read()
        await telegram.send_file(recipient, file_bytes, filename, content_type, caption)
    elif transport == "whatsapp":
        file_bytes = await file.read()
        await whatsapp.send_file(recipient, file_bytes, filename, content_type, caption)
    return {"status": "ok", "recipient": recipient, "transport": transport, "filename": filename}


@router.get("/groups", dependencies=[Depends(require_api_key)])
async def list_groups(transport: Literal["signal", "whatsapp"] = "signal"):
    if transport == "whatsapp":
        return await whatsapp.list_groups()
    return await signal.list_groups()


@router.get("/contacts", dependencies=[Depends(require_api_key)])
async def list_contacts(transport: Literal["signal", "whatsapp"] = "signal"):
    if transport == "whatsapp":
        return await whatsapp.list_contacts()
    return await signal.list_contacts()
