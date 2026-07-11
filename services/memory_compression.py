from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Message, User
from database.core import async_session
from llm.deepseek_client import parse_json_completion
from services.memory import save_memories


async def compress_old_messages(session: AsyncSession, user: User):
    cutoff = datetime.now() - timedelta(days=7)
    result = await session.execute(
        select(Message)
        .where(Message.user_id == user.id)
        .where(Message.created_at < cutoff)
        .where(Message.compressed.is_(False))
        .order_by(Message.created_at)
        .limit(200)
    )
    messages = result.scalars().all()
    if not messages:
        return

    texts = [f"{m.created_at.isoformat()}: {m.original_text}" for m in messages if m.original_text]
    if not texts:
        return

    prompt = f"""Summarize the following user messages into a JSON array of memory entries.
Each entry has: category (preference|fact|goal|routine), content, importance (1-5).

Messages:
{chr(10).join(texts)}

Return only JSON:
{{
  "memories": [
    {{"category": "preference", "content": "...", "importance": 4}}
  ]
}}"""

    parsed = await parse_json_completion([{"role": "user", "content": prompt}], temperature=0.2)
    memories = parsed.get("memories", [])

    source_ids = [m.id for m in messages]
    await save_memories(
        session,
        user.id,
        [{**mem, "source_message_ids": source_ids} for mem in memories],
    )

    for m in messages:
        m.compressed = True
    await session.commit()


async def compress_user_memory(user_id: int):
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user:
            await compress_old_messages(session, user)
