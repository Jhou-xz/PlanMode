from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
from sqlalchemy import select
from database.crud import get_or_create_user, create_message
from services.memory_compression import compress_old_messages
from services.memory import get_memories_for_prompt
from database.models import Message


async def test_compress_old_messages(session):
    user = await get_or_create_user(session, discord_user_id="compress_user", discord_username="compress")
    old_time = datetime.now(timezone.utc) - timedelta(days=8)
    await create_message(
        session,
        user_id=user.id,
        raw_type="text",
        original_text="I love hiking on weekends.",
        attachment_urls=[],
        parsed_intent="chat",
        parsed_entities={},
    )
    # Update created_at to be old (direct SQL update via model)
    from database.models import Message
    msg = (await session.execute(select(Message).where(Message.user_id == user.id))).scalar_one()
    msg.created_at = old_time
    await session.commit()

    mock_response = {"memories": [{"category": "preference", "content": "Likes hiking", "importance": 3}]}
    with patch("services.memory_compression.parse_json_completion", new=AsyncMock(return_value=mock_response)):
        await compress_old_messages(session, user)

    mems = await get_memories_for_prompt(session, user.id)
    assert len(mems) == 1
    assert mems[0].content == "Likes hiking"

    # Message should be marked compressed
    await session.refresh(msg)
    assert msg.compressed is True
