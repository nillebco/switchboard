# switchboard

A lightweight, transport-agnostic messaging hub. It receives incoming messages from Signal, WhatsApp, and Telegram, normalises them into a common event format, and publishes them to a Redis Stream. Agents subscribe to the stream and reply via the REST API — no transport knowledge required.

```
[Signal]     ─┐
[WhatsApp]   ─┤→ switchboard → Redis Stream "switchboard:incoming"
[Telegram]   ─┘       ↑
                  POST /api/v1/send  ← agents reply here
```

## Transports

| Transport | Incoming | Outgoing |
|-----------|----------|----------|
| Signal | WebSocket via [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) | `POST /v2/send` |
| WhatsApp | Webhook from [wuzapi](https://github.com/asternic/wuzapi) | `POST /chat/send/text` |
| Telegram | Long-polling via pyTelegramBotAPI | `sendMessage` |

## API

All endpoints require `X-API-Key` header.

```
POST /api/v1/send?transport=signal|whatsapp|telegram
     Body: {"recipient": "<id>", "message": "<text>"}

POST /api/v1/notify?transport=signal|whatsapp|telegram
     Body: {"message": "<text>"}
     Sends to the configured owner/notify target (no recipient needed)

GET  /api/v1/send/groups?transport=signal|whatsapp
     Lists groups the bot is a member of
```

Recipient formats:
- **Signal**: phone number (`+33612345678`) or group ID (`group.XXX…=`)
- **WhatsApp**: phone number or JID (`120363…@g.us` for groups)
- **Telegram**: chat ID (integer as string)

## Queue

Incoming messages are published to the Redis Stream `switchboard:incoming`.

### Event schema

```python
@dataclass
class IncomingMessage:
    transport: str        # "signal" | "whatsapp" | "telegram"
    sender: str           # phone number or user ID of the human sender
    recipient: str        # bot's own identifier (number, @handle, …)
    text: str | None      # message text, None for media-only messages
    message_id: str
    timestamp: int        # Unix timestamp
    group_id: str | None  # group ID if sent in a group, else None
    raw: dict             # original webhook/API payload
```

### Consuming the stream (Python example)

```python
import asyncio
import redis.asyncio as aioredis
import json

async def handle(fields: dict):
    transport = fields[b"transport"].decode()
    sender    = fields[b"sender"].decode()
    text      = fields[b"text"].decode() or None
    group_id  = fields[b"group_id"].decode() or None
    print(f"[{transport}] {sender}: {text}")
    # call POST /api/v1/send to reply

async def main():
    r = aioredis.from_url("redis://localhost:6379")
    try:
        await r.xgroup_create("switchboard:incoming", "my-agent", id="$", mkstream=True)
    except Exception:
        pass
    while True:
        results = await r.xreadgroup("my-agent", "worker-1", {"switchboard:incoming": ">"}, count=10, block=5000)
        for _stream, entries in results or []:
            for entry_id, fields in entries:
                await handle(fields)
                await r.xack("switchboard:incoming", "my-agent", entry_id)

asyncio.run(main())
```

## Setup

### 1. Configure

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Key variables:

| Variable | Description |
|---|---|
| `SIGNAL_PHONE_NUMBER` | Phone number registered in signal-cli (E.164) |
| `TELEGRAM_TOKEN` | Bot token from @BotFather |
| `WUZAPI_TOKEN` | wuzapi user token |
| `WUZAPI_ADMIN_TOKEN` | wuzapi admin token |
| `WUZAPI_GLOBAL_ENCRYPTION_KEY` | wuzapi encryption key |
| `WUZAPI_GLOBAL_HMAC_KEY` | wuzapi HMAC key |
| `REDIS_URL` | Redis connection URL (default: `redis://redis:6379`) |
| `API_KEY` | Key for protecting the REST API |
| `NOTIFY_SIGNAL_GROUP_ID` | Signal group ID to target with `/notify` |
| `NOTIFY_SIGNAL_PHONE` | Fallback Signal phone for `/notify` |
| `NOTIFY_WHATSAPP_NUMBER` | WhatsApp number for `/notify` |
| `NOTIFY_TELEGRAM_CHAT_ID` | Telegram chat ID for `/notify` |

### 2. Run

```bash
cp docker-compose.example.yml docker-compose.yml
# edit docker-compose.yml if needed (e.g. use external volumes from an existing setup)
docker compose up -d --build
```

The API is available at `http://localhost:8018`.

### WhatsApp webhook

Point wuzapi's webhook URL at:
```
http://<switchboard-host>:8018/api/v1/webhooks/whatsapp
```

### Signal & Telegram

Switchboard connects automatically on startup — Signal via WebSocket to signal-cli, Telegram via long-polling.

## Architecture notes

**Switchboard has no AI logic.** It is purely a transport hub. Agents subscribe to `switchboard:incoming`, process messages with whatever intelligence they need, and call `POST /api/v1/send` to reply. This keeps transports and agents independently deployable and replaceable.

If Redis is not configured (`REDIS_URL` unset), switchboard falls back to a `NullQueue` — messages are received and forwarded via the API but not persisted to any stream.

## License

MIT
