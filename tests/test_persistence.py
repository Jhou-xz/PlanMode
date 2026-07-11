from datetime import datetime, timezone
from database.crud import (
    get_or_create_user,
    set_user_timezone,
    create_message,
    create_reminder,
    create_idea,
    get_reminder_by_id,
)
from database.models import Message, Reminder, Idea


async def test_create_message(session):
    user = await get_or_create_user(session, discord_user_id="456", discord_username="persist")
    msg = await create_message(
        session,
        user_id=user.id,
        raw_type="text",
        original_text="hello world",
        attachment_urls=[],
        parsed_intent="chat",
        parsed_entities={},
    )
    assert msg.id is not None
    assert msg.original_text == "hello world"
    assert msg.parsed_intent == "chat"


async def test_create_reminder(session):
    user = await get_or_create_user(session, discord_user_id="789", discord_username="reminder")
    remind_at = datetime(2026, 7, 12, 10, 0, tzinfo=timezone.utc)
    r = await create_reminder(
        session,
        user_id=user.id,
        source_message_id=None,
        title="Call David",
        description="Important call",
        remind_at=remind_at,
    )
    fetched = await get_reminder_by_id(session, r.id)
    assert fetched is not None
    assert fetched.title == "Call David"
    assert fetched.remind_at == remind_at


async def test_create_idea(session):
    user = await get_or_create_user(session, discord_user_id="101", discord_username="idea")
    idea = await create_idea(
        session,
        user_id=user.id,
        source_message_id=None,
        content="Build a garden shed",
        category="project",
    )
    assert idea.id is not None
    assert idea.content == "Build a garden shed"
    assert idea.category == "project"


async def test_set_user_timezone(session):
    user = await get_or_create_user(session, discord_user_id="202", discord_username="tz")
    updated = await set_user_timezone(session, user, "Asia/Shanghai")
    assert updated.timezone == "Asia/Shanghai"
