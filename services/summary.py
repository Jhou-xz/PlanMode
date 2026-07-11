from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from database.core import async_session
from database import crud
from database.models import User
from llm.deepseek_client import stream_chat_completion
from services.memory import format_memories, get_memories_for_prompt


async def generate_daily_summary(session: AsyncSession, user: User) -> str:
    tz = ZoneInfo(user.timezone)
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    tomorrow_start = today_start + timedelta(days=1)

    messages = await crud.get_messages_since(session, user.id, yesterday_start)
    today_items = await crud.get_items_for_time_range(session, user.id, today_start, tomorrow_start)
    tomorrow_items = await crud.get_items_for_time_range(
        session, user.id, tomorrow_start, tomorrow_start + timedelta(days=1)
    )
    memories = await get_memories_for_prompt(session, user.id, limit=10)

    prompt = f"""You are Plan Mode. Write a friendly daily summary for the user in their language.

Yesterday's messages:
{[m.content for m in messages if m.content]}

Today's scheduled items:
{[i.title for i in today_items]}

Tomorrow's scheduled items:
{[i.title for i in tomorrow_items]}

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
