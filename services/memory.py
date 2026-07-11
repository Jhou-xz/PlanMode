from datetime import datetime, timedelta
from typing import List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Memory


async def get_memories_for_prompt(session: AsyncSession, user_id: int, limit: int = 10) -> List[Memory]:
    """Retrieve top memories by importance and recency."""
    result = await session.execute(
        select(Memory)
        .where(Memory.user_id == user_id)
        .order_by(desc(Memory.importance), desc(Memory.updated_at))
        .limit(limit)
    )
    return result.scalars().all()


async def save_memories(session: AsyncSession, user_id: int, memories: List[dict]) -> None:
    for mem in memories:
        if not mem.get("content"):
            continue
        m = Memory(
            user_id=user_id,
            category=mem.get("category", "preference"),
            content=mem["content"],
            importance=mem.get("importance", 1),
            source_message_ids=mem.get("source_message_ids", []),
        )
        session.add(m)
    await session.commit()


def format_memories(memories: List[Memory]) -> str:
    if not memories:
        return "No relevant memories yet."
    lines = ["Relevant memories about the user:"]
    for m in memories:
        lines.append(f"- [{m.category}] {m.content} (importance: {m.importance})")
    return "\n".join(lines)
