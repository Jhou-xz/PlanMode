import pytest
from services.memory import get_memories_for_prompt, save_memories, format_memories
from database.crud import get_or_create_user


async def test_save_and_retrieve_memory(session):
    user = await get_or_create_user(session, discord_user_id="123", discord_username="tester")
    await save_memories(session, user_id=user.id, memories=[{"category": "preference", "content": "Likes concise replies", "importance": 4}])
    mems = await get_memories_for_prompt(session, user_id=user.id)
    assert len(mems) == 1
    assert mems[0].content == "Likes concise replies"
