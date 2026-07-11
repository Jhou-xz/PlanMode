from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_upcoming_reminders


async def generate_weekly_image(
    session: AsyncSession,
    user,
    week_start: Optional[datetime] = None,
) -> str:
    tz = ZoneInfo(user.timezone)
    now = datetime.now(tz)

    if week_start is None:
        monday = now - timedelta(days=now.weekday())
    else:
        monday = week_start.astimezone(tz)

    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    # Ensure it starts on a Monday
    monday = monday - timedelta(days=monday.weekday())
    sunday = monday + timedelta(days=6)

    reminders = await get_upcoming_reminders(session, user.id, monday, monday + timedelta(days=7))

    width, height = 1400, 800
    img = Image.new("RGB", (width, height), color="#1e1e2e")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
        header_font = font
        small_font = font

    draw.text(
        (40, 30),
        f"Plan Mode — Week of {monday.strftime('%b %d')} to {sunday.strftime('%b %d, %Y')}",
        fill="white",
        font=header_font,
    )

    col_width = (width - 80) // 7
    for i in range(7):
        day = monday + timedelta(days=i)
        x = 40 + i * col_width
        draw.rectangle([x, 100, x + col_width - 10, height - 40], outline="#444466", width=2)
        draw.text((x + 10, 110), day.strftime("%a\n%m/%d"), fill="#a6e3a1", font=font)

    # Sort reminders by time and lay them out per day
    by_day: dict[int, list] = {i: [] for i in range(7)}
    for r in reminders:
        r_local = r.remind_at.astimezone(tz)
        day_index = (r_local.date() - monday.date()).days
        if 0 <= day_index < 7:
            by_day[day_index].append(r)

    for day_index, reminders_in_day in by_day.items():
        x = 40 + day_index * col_width
        reminders_in_day.sort(key=lambda r: r.remind_at)
        y = 160
        for r in reminders_in_day:
            r_local = r.remind_at.astimezone(tz)
            title = r.title[:22]
            time_str = r_local.strftime("%H:%M")
            draw.rectangle([x + 10, y, x + col_width - 20, y + 45], fill="#89b4fa")
            draw.text((x + 15, y + 5), time_str, fill="black", font=small_font)
            draw.text((x + 15, y + 22), title, fill="black", font=small_font)
            y += 55

    if not any(by_day.values()):
        draw.text(
            (width // 2 - 200, height // 2),
            "No reminders or events scheduled for this week yet.",
            fill="#7f849c",
            font=font,
        )

    path = f"/tmp/schedule_{user.id}.png"
    img.save(path)
    return path
