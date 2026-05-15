import asyncio
import logging

from fastapi import FastAPI

from . import config
from .queue import MessageQueue, NullQueue
from .routers.messages import router as messages_router
from .routers.notify import router as notify_router
from .routers.send import router as send_router
from .routers.webhooks import router as webhooks_router
from .transports.signal import start_signal_consumer
from .transports.telegram import start_telegram_consumer
from .transports.whatsapp import ensure_webhook as ensure_whatsapp_webhook

logger = logging.getLogger(__name__)

app = FastAPI(title="Switchboard", description="Multi-transport messaging hub")

app.include_router(send_router, prefix="/api/v1")
app.include_router(notify_router, prefix="/api/v1")
app.include_router(messages_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")


@app.on_event("startup")
async def startup():
    queue: MessageQueue

    if config.REDIS_URL:
        try:
            from .queue.redis_queue import RedisQueue
            queue = RedisQueue(config.REDIS_URL)
            logger.info("Redis queue connected: %s", config.REDIS_URL)
        except Exception:
            logger.warning("Failed to connect Redis queue, falling back to NullQueue", exc_info=True)
            queue = NullQueue()
    else:
        logger.warning("REDIS_URL not set — using NullQueue (messages will not be persisted)")
        queue = NullQueue()

    app.state.queue = queue

    asyncio.create_task(_run(ensure_whatsapp_webhook(), "whatsapp-webhook-register"))
    asyncio.create_task(_run(start_signal_consumer(queue), "signal-consumer"))
    asyncio.create_task(_run(start_telegram_consumer(queue), "telegram-consumer"))


async def _run(coro, name: str):
    try:
        await coro
    except Exception:
        logger.exception("Background task %s crashed", name)
