import asyncio
import logging
from typing import Any, Callable

import redis.asyncio as aioredis

from . import IncomingMessage

logger = logging.getLogger(__name__)

STREAM_KEY = "switchboard:incoming"
STREAM_MAXLEN = 10_000


class RedisQueue:
    def __init__(self, redis_url: str):
        self._redis = aioredis.from_url(redis_url, decode_responses=False)

    async def publish(self, message: IncomingMessage) -> None:
        await self._redis.xadd(STREAM_KEY, message.to_redis_fields(), maxlen=STREAM_MAXLEN, approximate=True)

    async def subscribe(self, group: str, consumer: str, handler: Callable[[IncomingMessage], Any]) -> None:
        try:
            await self._redis.xgroup_create(STREAM_KEY, group, id="$", mkstream=True)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        while True:
            try:
                results = await self._redis.xreadgroup(
                    group, consumer, {STREAM_KEY: ">"}, count=10, block=5000
                )
                for _stream, entries in results or []:
                    for entry_id, fields in entries:
                        try:
                            msg = IncomingMessage.from_redis_fields(fields)
                            await handler(msg)
                        except Exception:
                            logger.exception("Error handling message %s", entry_id)
                        finally:
                            await self._redis.xack(STREAM_KEY, group, entry_id)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Redis subscribe loop error, retrying in 2s")
                await asyncio.sleep(2)
