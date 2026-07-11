from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import (
    get_messages_since,
    get_upcoming_reminders,
    get_ideas,
    get_ideas_since,
    get_recent_messages_for_prompt,
)
from database.models import User
from services.memory import get_memories_for_prompt


async def build_status_report(session: AsyncSession, user: User) -> str:
    tz = ZoneInfo(user.timezone)
    now = datetime.now(tz)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Fetch all relevant data
    reminders = await get_upcoming_reminders(
        session, user.id, now, now + timedelta(days=30)
    )
    ideas = await get_ideas(session, user.id, limit=50)
    today_messages = await get_messages_since(session, user.id, day_start)
    week_messages = await get_messages_since(session, user.id, week_start)
    memories = await get_memories_for_prompt(session, user.id, limit=30)

    lines = []
    lines.append(f"📋 **Status Report for {user.discord_username or 'You'}**")
    lines.append(f"🕐 Current time: {now.strftime('%Y-%m-%d %H:%M')} ({user.timezone})")
    lines.append("")

    # Upcoming reminders
    lines.append("⏰ **Upcoming Reminders**")
    if reminders:
        for r in reminders[:10]:
            r_local = r.remind_at.astimezone(tz)
            lines.append(f"- {r.title} at {r_local.strftime('%Y-%m-%d %H:%M')}")
        if len(reminders) > 10:
            lines.append(f"- ... and {len(reminders) - 10} more")
    else:
        lines.append("- No upcoming reminders.")
    lines.append("")

    # Ideas
    lines.append("💡 **Ideas**")
    if ideas:
        for i in ideas[:10]:
            lines.append(f"- {i.content}")
        if len(ideas) > 10:
            lines.append(f"- ... and {len(ideas) - 10} more")
    else:
        lines.append("- No ideas stored.")
    lines.append("")

    # Memories
    lines.append("🧠 **Memories About You**")
    if memories:
        for m in memories[:10]:
            lines.append(f"- [{m.category}] {m.content}")
    else:
        lines.append("- No memories yet.")
    lines.append("")

    # Activity summary
    lines.append("📊 **Activity Summary**")
    lines.append(f"- Messages today: {len(today_messages)}")
    lines.append(f"- Messages this week: {len(week_messages)}")
    lines.append(f"- Total reminders (upcoming 30 days): {len(reminders)}")
    lines.append(f"- Total ideas stored: {len(ideas)}")
    lines.append(f"- Total memories: {len(memories)}")

    return "\n".join(lines)
