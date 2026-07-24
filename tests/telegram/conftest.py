from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.db.models import UserStatus
from app.models.admin import AdminDetails


@dataclass
class FakeChat:
    id: int = 1


@dataclass
class FakeFromUser:
    full_name: str = "Test User"


class FakeState:
    def __init__(self):
        self._data: dict = {}
        self._state = None

    async def set_state(self, state):
        self._state = state

    async def get_state(self):
        return self._state

    async def clear(self):
        self._state = None
        self._data = {}

    async def update_data(self, **kwargs):
        self._data.update(kwargs)

    async def get_data(self):
        return dict(self._data)

    async def get_value(self, key, default=None):
        return self._data.get(key, default)


class FakeMessage:
    def __init__(self, text: str = "text", message_id: int = 100, chat_id: int = 1):
        self.text = text
        self.message_id = message_id
        self.chat = FakeChat(chat_id)
        self.from_user = FakeFromUser()
        self.bot = SimpleNamespace(delete_messages=AsyncMock())
        self.answer = AsyncMock(side_effect=self._new_message)
        self.reply = AsyncMock(side_effect=self._new_message)
        self.edit_text = AsyncMock()
        self.edit_reply_markup = AsyncMock()
        self.answer_document = AsyncMock()
        self.answer_photo = AsyncMock()
        self.delete = AsyncMock()

    async def _new_message(self, *args, **kwargs):
        return FakeMessage(message_id=self.message_id + 1, chat_id=self.chat.id)


class FakeCallbackQuery:
    def __init__(self, message: FakeMessage | None = None, data: str = "callback"):
        self.message = message or FakeMessage()
        self.data = data
        self.from_user = self.message.from_user
        self.bot = self.message.bot
        self.answer = AsyncMock()


class FakeInlineQuery:
    def __init__(self, query: str = ""):
        self.query = query
        self.answer = AsyncMock()


@pytest.fixture
def fake_state() -> FakeState:
    return FakeState()


@pytest.fixture
def fake_message() -> FakeMessage:
    return FakeMessage()


@pytest.fixture
def fake_callback() -> FakeCallbackQuery:
    return FakeCallbackQuery()


@pytest.fixture
def fake_inline_query() -> FakeInlineQuery:
    return FakeInlineQuery()


@pytest.fixture
def admin() -> AdminDetails:
    return AdminDetails(username="testadmin", is_sudo=True)


@pytest.fixture
def regular_admin() -> AdminDetails:
    return AdminDetails(username="owner", is_sudo=False)


@pytest.fixture
def fake_user():
    user = SimpleNamespace(
        id=11,
        username="alice",
        status=UserStatus.active,
        subscription_url="https://example.com/sub/alice",
        next_plan=None,
        admin=SimpleNamespace(username="owner"),
    )
    user.model_dump = lambda: {}
    return user
