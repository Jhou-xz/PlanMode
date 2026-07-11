from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import (
    get_messages_since,
    get_upcoming_reminders,
    get_ideas,
    get_ideas_since,
)
from database.models import User
from llm.deepseek_client import stream_chat_completion
from services.memory import format_memories, get_memories_for_prompt


async def answer_query(session: AsyncSession, user: User, question: str, query_type: str) -> str:
    tz = ZoneInfo(user.timezone)
    now = datetime.now(tz)
    messages = []
    reminders = []
    ideas = []
    time_label = "the requested time range"

    normalized = (query_type or "").lower().strip()

    if normalized in {"today", "today_messages", "messages_today"}:
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        messages = await get_messages_since(session, user.id, today_start)
        ideas = await get_ideas_since(session, user.id, today_start)
        time_label = "today"
    elif normalized in {"upcoming", "this_week", "weekly", "week"}:
        reminders = await get_upcoming_reminders(session, user.id, now, now + timedelta(days=7))
        time_label = "the next 7 days"
    elif normalized in {"ideas", "my_ideas", "past_ideas", "idea_list"}:
        ideas = await get_ideas(session, user.id, limit=50)
        time_label = "all time"
    elif normalized in {"past", "history", "recent", "messages"}:
        past_start = now - timedelta(days=7)
        messages = await get_messages_since(session, user.id, past_start)
        ideas = await get_ideas_since(session, user.id, past_start)
        time_label = "the last 7 days"
    else:
        # Default: pull a bit of everything for the last 7 days.
        past_start = now - timedelta(days=7)
        messages = await get_messages_since(session, user.id, past_start)
        reminders = await get_upcoming_reminders(session, user.id, now, now + timedelta(days=7))
        ideas = await get_ideas_since(session, user.id, past_start)
        time_label = "the last 7 days and upcoming week"

    memories = await get_memories_for_prompt(session, user.id, limit=10)

    message_texts = [m.original_text for m in messages if m.original_text]
    reminder_texts = [f"{r.title} at {r.remind_at.astimezone(tz).strftime('%Y-%m-%d %H:%M')}" for r in reminders]
    idea_texts = [f"- {i.content}" for i in ideas]

    if not message_texts and not reminder_texts and not idea_texts:
        return (
            f"I don't have any events, reminders, ideas, or messages recorded for {time_label} yet. "
            f"You can say things like 'Remind me to call mom at 5pm' or 'Idea: launch a newsletter'."
        )

    prompt = f"""The user asks: {question}

Data for {time_label}:
Reminders: {reminder_texts}
Ideas: {idea_texts}
Messages: {message_texts}

{format_memories(memories)}

Answer in the user's language. Be concise and direct. If the user asks about ideas, list the ideas clearly.
"""

    return await stream_chat_completion(
        [{"role": "user", "content": prompt}],
        json_mode=False,
        temperature=0.3,
    )
