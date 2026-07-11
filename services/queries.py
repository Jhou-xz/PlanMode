from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_messages_since, get_upcoming_reminders
from database.models import User
from llm.deepseek_client import stream_chat_completion
from services.memory import format_memories, get_memories_for_prompt


async def answer_query(session: AsyncSession, user: User, question: str, query_type: str) -> str:
    tz = ZoneInfo(user.timezone)
    now = datetime.now(tz)
    messages = []
    reminders = []
    time_label = ""

    if query_type == "today_messages":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        messages = await get_messages_since(session, user.id, today_start)
        time_label = "today"
    elif query_type == "upcoming":
        reminders = await get_upcoming_reminders(session, user.id, now, now + timedelta(days=7))
        time_label = "the next 7 days"
    elif query_type == "weekly":
        reminders = await get_upcoming_reminders(session, user.id, now, now + timedelta(days=7))
        time_label = "this week"

    memories = await get_memories_for_prompt(session, user.id, limit=10)

    message_texts = [m.original_text for m in messages if m.original_text]
    reminder_texts = [f"{r.title} at {r.remind_at.astimezone(tz).strftime('%Y-%m-%d %H:%M')}" for r in reminders]

    if not message_texts and not reminder_texts:
        return (
            f"I don't have any events, reminders, or messages recorded for {time_label} yet. "
            f"You can say things like 'Remind me to call mom at 5pm' or 'Idea: launch a newsletter'."
        )

    prompt = f"""The user asks: {question}

Data for {time_label}:
Messages: {message_texts}
Reminders: {reminder_texts}

{format_memories(memories)}

Answer in the user's language. Be concise and direct. Summarize the schedule if asked.
"""

    return await stream_chat_completion(
        [{"role": "user", "content": prompt}],
        json_mode=False,
        temperature=0.3,
    )
