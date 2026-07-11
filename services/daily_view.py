from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud
from services.memory import format_memory_summary, get_memories_for_prompt


async def generate_daily_list_view(
    session: AsyncSession,
    user,
    date: datetime | None = None,
) -> str:
    tz = ZoneInfo(user.timezone)
    now = datetime.now(tz)

    if date is None:
        date = now

    day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    items = await crud.get_items_for_time_range(session, user.id, day_start, day_end)
    # Also include tasks that are due today but not archived
    due_items = await crud.search_items(
        session,
        user_id=user.id,
        status="todo",
        time_range=(day_start, day_end),
        limit=100,
    )
    # Merge without duplicates
    seen = {i.id for i in items}
    for i in due_items:
        if i.id not in seen:
            items.append(i)
            seen.add(i.id)

    items = sorted(items, key=lambda i: (i.start_time or i.due_date or i.created_at))

    memories = await get_memories_for_prompt(session, user.id, limit=5)

    lines = []
    lines.append(f"📅 **Daily Plan — {day_start.strftime('%A, %B %d')}** ({user.timezone})")
    lines.append("")

    if items:
        for item in items:
            time_str = ""
            if item.start_time:
                time_str = item.start_time.astimezone(tz).strftime("%H:%M")
            elif item.due_date:
                time_str = f"due {item.due_date.astimezone(tz).strftime('%H:%M')}"
            status_emoji = {"todo": "⬜", "in_progress": "🟦", "done": "✅", "archived": "📦", "cancelled": "❌"}.get(item.status, "⬜")
            section_name = item.section.name if item.section else ""
            lines.append(f"{status_emoji} **{item.title}** {time_str} *[{section_name}]*")
            if item.content:
                lines.append(f"   {item.content[:120]}")
    else:
        lines.append("No scheduled items or tasks for this day.")

    if memories:
        lines.append("")
        lines.append(format_memory_summary(memories))

    return "\n".join(lines)


async def generate_daily_list_image(
    session: AsyncSession,
    user,
    date: datetime | None = None,
) -> str:
    """Render the daily list as a simple image (optional)."""
    from PIL import Image, ImageDraw, ImageFont

    text = await generate_daily_list_view(session, user, date)
    width, height = 800, 600
    img = Image.new("RGB", (width, height), color="#0f0f1a")
    draw = ImageDraw.Draw(img)
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        font_body = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except Exception:
        font_title = font_body = ImageFont.load_default()

    draw.text((30, 30), "Daily Plan", fill="#cdd6f4", font=font_title)
    y = 80
    for line in text.split("\n"):
        draw.text((30, y), line, fill="#cdd6f4", font=font_body)
        y += 24
        if y > height - 30:
            break

    path = f"/tmp/daily_{user.id}.png"
    img.save(path)
    return path
