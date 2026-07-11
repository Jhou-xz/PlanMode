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

    if query_type == "today_messages":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        messages = await get_messages_since(session, user.id, today_start)
    elif query_type == "upcoming":
        reminders = await get_upcoming_reminders(session, user.id, now, now + timedelta(days=7))
    elif query_type == "weekly":
        reminders = await get_upcoming_reminders(session, user.id, now, now + timedelta(days=7))

    memories = await get_memories_for_prompt(session, user.id, limit=10)

    prompt = f"""The user asks: {question}

Data:
Messages: {[m.original_text for m in messages if m.original_text]}
Reminders: {[r.title for r in reminders]}

{format_memories(memories)}

Answer in the user's language. Be concise.
"""

    return await stream_chat_completion(
        [{"role": "user", "content": prompt}],
        json_mode=False,
        temperature=0.3,
    )
