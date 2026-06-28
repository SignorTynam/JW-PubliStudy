from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


VALID_ROLES = {"user", "assistant", "system"}


@dataclass
class ChatMessage:
    id: str
    role: str
    content: str
    created_at: str
    sources: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(cls, role: str, content: str, sources: list[dict[str, Any]] | None = None) -> "ChatMessage":
        return cls(
            id=str(uuid4()),
            role=role if role in VALID_ROLES else "user",
            content=content,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            sources=sources or [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
            "sources": self.sources,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatMessage":
        sources = data.get("sources")
        return cls(
            id=_string_value(data.get("id"), str(uuid4())),
            role=_role_value(data.get("role")),
            content=_string_value(data.get("content"), ""),
            created_at=_string_value(data.get("created_at"), ""),
            sources=sources if isinstance(sources, list) else [],
        )


def _string_value(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) else fallback


def _role_value(value: Any) -> str:
    return value if isinstance(value, str) and value in VALID_ROLES else "user"
