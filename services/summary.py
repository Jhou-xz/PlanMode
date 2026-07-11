from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from database.core import async_session
from database.crud import get_messages_since, get_upcoming_reminders
from database.models import User
from llm.deepseek_client import stream_chat_completion
from services.memory import format_memories, get_memories_for_prompt


async def generate_daily_summary(session: AsyncSession, user: User) -> str:
    tz = ZoneInfo(user.timezone)
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    tomorrow_start = today_start + timedelta(days=1)

    messages = await get_messages_since(session, user.id, yesterday_start)
    reminders_today = await get_upcoming_reminders(session, user.id, today_start, tomorrow_start)
    reminders_tomorrow = await get_upcoming_reminders(
        session, user.id, tomorrow_start, tomorrow_start + timedelta(days=1)
    )
    memories = await get_memories_for_prompt(session, user.id, limit=10)

    prompt = f"""You are Plan Mode. Write a friendly daily summary for the user in their language.

Yesterday's messages:
{[m.original_text for m in messages if m.original_text]}

Today's reminders:
{[r.title for r in reminders_today]}

Tomorrow's reminders:
{[r.title for r in reminders_tomorrow]}

{format_memories(memories)}

Summarize what happened yesterday and what is coming up tomorrow. Be concise and warm.
"""

    return await stream_chat_completion(
        [{"role": "user", "content": prompt}],
        json_mode=False,
        temperature=0.3,
    )


async def send_daily_summary(user_id: int):
    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            return
        text = await generate_daily_summary(session, user)
        from bot.client import bot
        discord_user = await bot.fetch_user(int(user.discord_user_id))
        if discord_user:
            await discord_user.send(f"📋 Daily Summary\n\n{text[:1800]}")
