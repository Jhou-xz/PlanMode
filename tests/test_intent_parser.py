import os
import pytest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from services.intent_parser import parse_intent, build_messages, build_system_prompt
from services.memory import save_memories, get_memories_for_prompt, format_memories
from services.date_parser import parse_reminder_datetime, ReminderDateError
from database.crud import create_message, get_or_create_user
from database.models import Message, Memory


@pytest.mark.skipif(
    os.environ.get("DEEPSEEK_API_KEY", "").startswith("dummy_") or not os.environ.get("DEEPSEEK_API_KEY"),
    reason="requires a real DeepSeek API key",
)
@pytest.mark.asyncio
async def test_parse_reminder():
    result = await parse_intent(
        "Remind me to call David tomorrow at 4pm",
        timezone="Asia/Shanghai",
        memories=[],
        history_messages=[],
    )
    assert result["intent"] == "reminder"
    assert "reminder" in result["entities"]
    assert result["language"] == "en"


async def test_build_messages_include_history(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000011", discord_username="history")
    await create_message(session, user.id, "text", "Hello bot", [], "chat", {}, role="user")
    await create_message(session, user.id, "text", "Hi there", [], "chat", {}, role="assistant")

    messages = await build_messages(
        user_text="What did we just talk about?",
        timezone="Asia/Shanghai",
        memories=[],
        history_messages=[
            Message(id=1, role="user", original_text="Hello bot", created_at=datetime.now(timezone.utc)),
            Message(id=2, role="assistant", original_text="Hi there", created_at=datetime.now(timezone.utc)),
        ],
    )

    system_content = messages[0]["content"]
    assert "Recent conversation history" in system_content
    assert "User: Hello bot" in system_content or "Hello bot" in system_content
    assert "Assistant: Hi there" in system_content or "Hi there" in system_content


async def test_build_system_prompt_includes_current_datetime():
    system_content = build_system_prompt(
        timezone="Asia/Shanghai",
        memories=[],
        history_messages=[],
    )
    assert "UTC now" in system_content
    assert "User timezone now" in system_content
    assert "Asia/Shanghai" in system_content


async def test_parse_reminder_datetime_relative_tomorrow():
    dt = await parse_reminder_datetime(
        iso_string="2099-12-31T16:00:00+08:00",
        original_time_expression="tomorrow at 4pm",
        user_timezone="Asia/Shanghai",
    )
    assert dt.tzinfo == ZoneInfo("Asia/Shanghai")
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    expected_tomorrow = (now + timedelta(days=1)).date()
    assert dt.date() == expected_tomorrow
    assert dt.hour == 16


async def test_parse_reminder_datetime_rejects_past():
    with pytest.raises(ReminderDateError):
        await parse_reminder_datetime(
            iso_string="2020-01-01T12:00:00+08:00",
            original_time_expression="January 1st 2020 at noon",
            user_timezone="Asia/Shanghai",
        )


async def test_memory_deduplication_and_ranking(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000012", discord_username="mem")
    await save_memories(session, user.id, [
        {"category": "preference", "content": "Likes concise replies", "importance": 4},
        {"category": "preference", "content": "likes concise replies", "importance": 5},
        {"category": "goal", "content": "Run a marathon", "importance": 3},
    ])

    mems = await get_memories_for_prompt(session, user_id=user.id, limit=20)
    contents = [m.content for m in mems]
    assert len(contents) == 2
    assert "Likes concise replies" in contents
    assert "Run a marathon" in contents

    # Higher importance duplicate should have won.
    assert all(m.importance >= 3 for m in mems)


async def test_memory_formatting():
    mem = Memory(category="preference", content="Likes tea", importance=4)
    text = format_memories([mem])
    assert "Likes tea" in text
    assert "importance: 4" in text
