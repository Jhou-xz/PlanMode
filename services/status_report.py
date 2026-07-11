from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud
from services.memory import format_memories, get_memories_for_prompt


async def build_status_report(session: AsyncSession, user) -> str:
    tz = ZoneInfo(user.timezone)
    now = datetime.now(tz)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    next_month = now + timedelta(days=30)

    sections = await crud.list_sections(session, user.id)
    upcoming_items = await crud.get_items_for_time_range(session, user.id, now, next_month)
    today_items = await crud.get_items_for_time_range(session, user.id, day_start, day_start + timedelta(days=1))
    memories = await get_memories_for_prompt(session, user.id, limit=30)
    today_messages = await crud.get_messages_since(session, user.id, day_start)
    week_messages = await crud.get_messages_since(session, user.id, week_start)

    lines = []
    lines.append(f"📋 **Status Report for {user.discord_username or 'You'}**")
    lines.append(f"🕐 Current time: {now.strftime('%Y-%m-%d %H:%M')} ({user.timezone})")
    lines.append("")

    for section in sections:
        items = [i for i in section.items if not i.is_archived]
        if not items and section.slug != "completed":
            continue
        lines.append(f"**{section.name}** ({len(items)})")
        for item in items[:10]:
            time_str = ""
            if item.start_time:
                time_str = item.start_time.astimezone(tz).strftime("%Y-%m-%d %H:%M")
            elif item.due_date:
                time_str = f"due {item.due_date.astimezone(tz).strftime('%Y-%m-%d %H:%M')}"
            status_emoji = {"todo": "⬜", "in_progress": "🟦", "done": "✅", "archived": "📦", "cancelled": "❌"}.get(item.status, "⬜")
            lines.append(f"{status_emoji} {item.title} {time_str}")
        if len(items) > 10:
            lines.append(f"- ... and {len(items) - 10} more")
        lines.append("")

    # Completed / archived summary
    completed = [i for i in upcoming_items if i.status == "done" or i.is_archived]
    if completed:
        lines.append(f"✅ **Completed recently** ({len(completed)})")
        for item in completed[:5]:
            lines.append(f"- {item.title}")
        lines.append("")

    # Memories
    lines.append("🧠 **Memories About You**")
    if memories:
        lines.append(format_memories(memories))
    else:
        lines.append("- No memories yet.")
    lines.append("")

    # Activity summary
    lines.append("📊 **Activity Summary**")
    lines.append(f"- Messages today: {len(today_messages)}")
    lines.append(f"- Messages this week: {len(week_messages)}")
    lines.append(f"- Upcoming items (next 30 days): {len(upcoming_items)}")
    lines.append(f"- Today's scheduled items: {len(today_items)}")
    lines.append(f"- Total memories: {len(memories)}")

    return "\n".join(lines)
