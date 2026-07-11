from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud

# Color palette — modern dark UI with soft accents
BG_COLOR = "#0f0f1a"
CARD_COLOR = "#181825"
HEADER_COLOR = "#1e1e2e"
TEXT_COLOR = "#cdd6f4"
SUBTEXT_COLOR = "#a6adc8"
ACCENT_COLOR = "#89b4fa"
TODAY_ACCENT = "#f38ba8"
BORDER_COLOR = "#313244"
EVENT_COLORS = ["#89b4fa", "#a6e3a1", "#f9e2af", "#fab387", "#cba6f7", "#f38ba8", "#94e2d5"]


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
    monday = monday - timedelta(days=monday.weekday())
    sunday = monday + timedelta(days=6)

    items = await crud.get_items_for_time_range(
        session, user.id, monday, monday + timedelta(days=7)
    )

    width, height = 1600, 900
    img = Image.new("RGB", (width, height), color=BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Load fonts with fallbacks
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_day = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_event = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except Exception:
        font_title = font_day = font_event = font_small = ImageFont.load_default()

    # Header background
    draw.rectangle([0, 0, width, 110], fill=HEADER_COLOR)
    draw.text((40, 35), f"Plan Mode — {monday.strftime('%b %d')} to {sunday.strftime('%b %d, %Y')}",
              fill=TEXT_COLOR, font=font_title)
    draw.text((40, 78), f"Timezone: {user.timezone} • {len(items)} events",
              fill=SUBTEXT_COLOR, font=font_small)

    # Subtle decorative line
    draw.line([40, 105, width - 40, 105], fill=ACCENT_COLOR, width=2)

    # Layout: 7 equal columns
    margin = 40
    top = 140
    bottom = height - 40
    col_width = (width - margin * 2) // 7
    row_height = bottom - top

    today = now.date()

    # Group items by day
    by_day = {i: [] for i in range(7)}
    for item in items:
        event_time = item.start_time or item.due_date
        if event_time is None:
            continue
        local_time = event_time.astimezone(tz)
        day_index = (local_time.date() - monday.date()).days
        if 0 <= day_index < 7:
            by_day[day_index].append(item)

    for i in range(7):
        day = monday + timedelta(days=i)
        x = margin + i * col_width
        is_today = day.date() == today
        accent = TODAY_ACCENT if is_today else ACCENT_COLOR

        # Card background with rounded corners (simulated)
        draw.rectangle(
            [x, top, x + col_width - 12, bottom],
            fill=CARD_COLOR,
            outline=accent if is_today else BORDER_COLOR,
            width=2 if is_today else 1,
        )

        # Day header
        header_y = top + 8
        day_text = day.strftime("%A")
        date_text = day.strftime("%b %d")
        draw.text((x + 14, header_y), day_text, fill=accent, font=font_day)
        draw.text((x + 14, header_y + 30), date_text, fill=SUBTEXT_COLOR, font=font_small)

        # Events
        events = sorted(by_day[i], key=lambda i: i.start_time or i.due_date or i.created_at)
        y = top + 75
        for idx, item in enumerate(events):
            event_time = item.start_time or item.due_date
            local_time = event_time.astimezone(tz)
            time_str = local_time.strftime("%H:%M")
            color = EVENT_COLORS[idx % len(EVENT_COLORS)]
            # Event pill
            pill_height = 52
            draw.rounded_rectangle(
                [x + 10, y, x + col_width - 22, y + pill_height],
                radius=8,
                fill=color,
            )
            # Title (truncated)
            title = item.title[:22] if item.title else "(no title)"
            draw.text((x + 18, y + 6), title, fill="#11111b", font=font_event)
            draw.text((x + 18, y + 28), time_str, fill="#313244", font=font_small)
            y += pill_height + 10
            if y > bottom - 30:
                break

        # Empty day indicator
        if not events:
            draw.text(
                (x + 14, top + 90),
                "No events",
                fill="#45475a",
                font=font_small,
            )

    path = f"/tmp/schedule_{user.id}.png"
    img.save(path)
    return path
