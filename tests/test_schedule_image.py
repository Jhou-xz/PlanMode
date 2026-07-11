import os
from datetime import datetime, timezone, timedelta
from database.crud import get_or_create_user, create_reminder
from services.schedule_image import generate_weekly_image


async def test_generate_weekly_image(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000005", discord_username="image")
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    remind_at = monday.replace(hour=10, minute=0, second=0, microsecond=0)
    await create_reminder(session, user.id, None, "Team meeting", None, remind_at)

    path = await generate_weekly_image(session, user)
    assert os.path.exists(path)
    assert path.endswith(".png")
    os.unlink(path)
