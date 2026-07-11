from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_upcoming_reminders


async def generate_weekly_image(session: AsyncSession, user) -> str:
    tz = ZoneInfo(user.timezone)
    now = datetime.now(tz)
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)

    reminders = await get_upcoming_reminders(session, user.id, monday, monday + timedelta(days=7))

    width, height = 1400, 800
    img = Image.new("RGB", (width, height), color="#1e1e2e")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
        header_font = font

    draw.text((40, 30), f"Plan Mode — Week of {monday.strftime('%b %d')}", fill="white", font=header_font)

    col_width = (width - 80) // 7
    for i in range(7):
        day = monday + timedelta(days=i)
        x = 40 + i * col_width
        draw.rectangle([x, 100, x + col_width - 10, height - 40], outline="#444466", width=2)
        draw.text((x + 10, 110), day.strftime("%a %m/%d"), fill="#a6e3a1", font=font)

    for r in reminders:
        r_local = r.remind_at.astimezone(tz)
        day_index = (r_local.date() - monday.date()).days
        if 0 <= day_index < 7:
            x = 40 + day_index * col_width
            y = 150 + (r.id % 6) * 60
            draw.rectangle([x + 10, y, x + col_width - 20, y + 45], fill="#89b4fa")
            draw.text((x + 15, y + 5), r.title[:20], fill="black", font=font)

    path = f"/tmp/schedule_{user.id}.png"
    img.save(path)
    return path
