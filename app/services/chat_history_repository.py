from __future__ import annotations

import json

from app.models.chat_message import ChatMessage
from app.paths import AppPaths


class ChatHistoryRepository:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self._paths = paths or AppPaths()

    def list_messages(self) -> list[ChatMessage]:
        path = self._paths.chat_history_file
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [ChatMessage.from_dict(item) for item in data if isinstance(item, dict)]

    def add_message(self, message: ChatMessage) -> None:
        messages = self.list_messages()
        messages.append(message)
        self.save_messages(messages)

    def clear_history(self) -> None:
        self.save_messages([])

    def save_messages(self, messages: list[ChatMessage]) -> None:
        path = self._paths.chat_history_file
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = path.with_suffix(".json.tmp")
        try:
            with temp_file.open("w", encoding="utf-8") as file:
                json.dump([message.to_dict() for message in messages], file, ensure_ascii=False, indent=2)
            temp_file.replace(path)
        except OSError:
            temp_file.unlink(missing_ok=True)
