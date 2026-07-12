import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot.handlers import extract_text_from_message, handle_message
from services.agent import (
    _build_system_prompt,
    _format_history,
    _format_items,
    _format_memories,
    _sanitize_final_text,
    _strip_cjk,
)
from services.tools.items import create_item
from services.tools.schemas import CreateItemInput


class FakeDMChannel(discord.DMChannel):
    def __init__(self):
        self.typing_entered = False
        self.typing_exited = False

    def typing(self):
        channel = self

        class TypingContextManager:
            async def __aenter__(self):
                channel.typing_entered = True

            async def __aexit__(self, exc_type, exc, tb):
                channel.typing_exited = True
                return False

        return TypingContextManager()


@pytest.mark.asyncio
async def test_extract_text_from_message_returns_english_language_for_text():
    message = MagicMock()
    message.flags.voice = False
    message.content = "hello"
    message.attachments = []

    result = await extract_text_from_message(message)
    assert result["text"] == "hello"
    assert result["type"] == "text"
    assert result["language"] == "en"


@pytest.mark.asyncio
async def test_build_system_prompt_requires_english_only():
    user = MagicMock()
    user.timezone = "UTC"
    user.preferred_language = "zh-cn"

    prompt = _build_system_prompt(user, [], [], [])
    assert "ALWAYS respond in English only" in prompt
    assert "you MUST reply in English" in prompt


def test_sanitize_final_text_removes_cjk_and_cleans_whitespace():
    raw = "Hello 你好 world!\n\n\n\nこんにちは   안녕하세요"
    cleaned = _sanitize_final_text(raw)
    assert "你" not in cleaned
    assert "こん" not in cleaned
    assert "안녕" not in cleaned
    assert cleaned == "Hello world!"


@pytest.mark.asyncio
async def test_create_item_with_metadata_does_not_crash(session):
    from database.crud import get_or_create_user

    user = await get_or_create_user(session, discord_user_id="123", discord_username="tester")
    result = await create_item(
        session,
        user,
        CreateItemInput(
            section_name="Tasks",
            title="Call carmel",
            metadata={"priority": "high"},
        ),
    )
    result_dict = result.to_dict()
    assert result_dict.get("success") is True
    assert result_dict.get("title") == "Call carmel"


@pytest.mark.asyncio
async def test_handle_message_passes_english_language_to_run_agent():
    channel = FakeDMChannel()
    channel.send = AsyncMock()

    message = MagicMock()
    message.author.bot = False
    message.author.id = 123
    message.channel = channel
    message.content = "hi"
    message.attachments = []
    message.flags.voice = False

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=None)

    run_agent_mock = AsyncMock(return_value=("Hello!", []))

    with patch("bot.handlers.async_session", return_value=session_cm), patch(
        "bot.handlers.get_or_create_user", new_callable=AsyncMock
    ), patch(
        "bot.handlers._is_timezone_change_request", new_callable=AsyncMock, return_value=False
    ), patch(
        "bot.handlers.build_image_content", new_callable=AsyncMock, return_value=[]
    ), patch(
        "bot.handlers.run_agent", new=run_agent_mock
    ):
        await handle_message(message)

    assert run_agent_mock.called
    _, kwargs = run_agent_mock.call_args
    assert kwargs.get("language") == "en"


def test_strip_cjk_removes_cjk_characters():
    raw = "Hello 你好 world こんにちは 안녕하세요"
    cleaned = _strip_cjk(raw)
    assert cleaned == "Hello  world  "
    assert "你" not in cleaned
    assert "こん" not in cleaned
    assert "안녕" not in cleaned


def test_format_memories_strips_cjk():
    memory = MagicMock()
    memory.category = "preference"
    memory.content = "likes coffee 咖啡"
    memory.importance = 3

    formatted = _format_memories([memory])
    assert "咖啡" not in formatted
    assert "likes coffee " in formatted


def test_format_history_strips_cjk():
    message = MagicMock()
    message.created_at = None
    message.role = "user"
    message.content = "hi 你好"

    formatted = _format_history([message])
    assert "你好" not in formatted
    assert "hi " in formatted


def test_format_items_strips_cjk():
    section = MagicMock()
    section.name = "Tasks"

    item = MagicMock()
    item.section = section
    item.title = "meeting 会议"
    item.status = "todo"
    item.start_time = None
    item.due_date = None

    formatted = _format_items([item])
    assert "会议" not in formatted
    assert "meeting " in formatted


def test_build_system_prompt_strips_cjk_from_context():
    user = MagicMock()
    user.timezone = "UTC"
    user.preferred_language = "zh-cn"

    section = MagicMock()
    section.name = "Schedule"

    item = MagicMock()
    item.section = section
    item.title = "doctor 医生"
    item.status = "todo"
    item.start_time = None
    item.due_date = None

    message = MagicMock()
    message.created_at = None
    message.role = "assistant"
    message.content = "Done 完成"

    memory = MagicMock()
    memory.category = "fact"
    memory.content = "allergic to nuts 对坚果过敏"
    memory.importance = 4

    prompt = _build_system_prompt(user, [message], [memory], [item])
    assert "医生" not in prompt
    assert "完成" not in prompt
    assert "对坚果过敏" not in prompt
    assert "doctor " in prompt
    assert "Done " in prompt
    assert "allergic to nuts " in prompt
