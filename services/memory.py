import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Memory


def _normalize_content(content: str) -> str:
    return re.sub(r"\s+", " ", content.strip().lower())


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize_content(a), _normalize_content(b)).ratio()


async def get_memories_for_prompt(
    session: AsyncSession,
    user_id: int,
    limit: int = 20,
) -> List[Memory]:
    """Retrieve top memories by importance and recency, deduplicated by content."""
    result = await session.execute(
        select(Memory)
        .where(Memory.user_id == user_id)
        .order_by(desc(Memory.importance), desc(Memory.updated_at))
        .limit(limit * 2)  # fetch more so dedup has a pool to choose from
    )
    candidates = result.scalars().all()

    deduped: List[Memory] = []
    for mem in candidates:
        if not any(_similar(mem.content, existing.content) > 0.75 for existing in deduped):
            deduped.append(mem)
        if len(deduped) >= limit:
            break
    return deduped


async def save_memories(
    session: AsyncSession,
    user_id: int,
    memories: List[dict],
) -> None:
    """Save new memories, avoiding duplicates against existing entries."""
    result = await session.execute(
        select(Memory)
        .where(Memory.user_id == user_id)
        .order_by(desc(Memory.created_at))
        .limit(200)
    )
    existing = result.scalars().all()

    for mem in memories:
        if not mem.get("content"):
            continue

        content = mem["content"]
        if any(_similar(content, e.content) > 0.75 for e in existing):
            continue

        importance = max(1, min(5, int(mem.get("importance", 1))))
        m = Memory(
            user_id=user_id,
            category=mem.get("category", "preference"),
            content=content,
            importance=importance,
            source_message_ids=mem.get("source_message_ids", []),
        )
        session.add(m)
        existing.append(m)

    await session.commit()


def format_memories(memories: List[Memory]) -> str:
    if not memories:
        return "No relevant memories yet."
    lines = ["Relevant memories about the user (higher importance = more important):"]
    for m in memories:
        lines.append(f"- [{m.category}] {m.content} (importance: {m.importance})")
    return "\n".join(lines)


def format_memory_summary(memories: List[Memory]) -> str:
    """A compact bullet list for shorter prompts."""
    if not memories:
        return "No relevant memories yet."
    return "\n".join(f"- [{m.category}] {m.content}" for m in memories)
