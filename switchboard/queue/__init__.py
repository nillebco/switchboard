import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable


@dataclass
class IncomingMessage:
    transport: str
    sender: str
    recipient: str
    text: str | None
    message_id: str
    timestamp: int
    group_id: str | None
    raw: dict = field(default_factory=dict)

    def to_redis_fields(self) -> dict[str, str]:
        return {
            "transport": self.transport,
            "sender": self.sender,
            "recipient": self.recipient,
            "text": self.text or "",
            "message_id": self.message_id,
            "timestamp": str(self.timestamp),
            "group_id": self.group_id or "",
            "raw": json.dumps(self.raw),
        }

    @classmethod
    def from_redis_fields(cls, fields: dict) -> "IncomingMessage":
        return cls(
            transport=fields[b"transport"].decode(),
            sender=fields[b"sender"].decode(),
            recipient=fields[b"recipient"].decode(),
            text=fields[b"text"].decode() or None,
            message_id=fields[b"message_id"].decode(),
            timestamp=int(fields[b"timestamp"].decode()),
            group_id=fields[b"group_id"].decode() or None,
            raw=json.loads(fields[b"raw"].decode()),
        )


@runtime_checkable
class MessageQueue(Protocol):
    async def publish(self, message: IncomingMessage) -> None: ...
    async def subscribe(self, group: str, consumer: str, handler: Callable[[IncomingMessage], Any]) -> None: ...


class NullQueue:
    async def publish(self, message: IncomingMessage) -> None:
        pass

    async def subscribe(self, group: str, consumer: str, handler: Callable[[IncomingMessage], Any]) -> None:
        pass
