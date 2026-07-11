import os
from datetime import datetime, timezone, timedelta
from database.crud import get_or_create_user, create_item, get_section_by_slug
from services.schedule_image import generate_weekly_image


async def test_generate_weekly_image(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000005", discord_username="image")
    section = await get_section_by_slug(session, user.id, "schedule")

    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    tuesday = monday + timedelta(days=1, hours=10)
    wednesday = monday + timedelta(days=2, hours=14)

    await create_item(
        session, user.id, section.id, "Team meeting", start_time=tuesday
    )
    await create_item(
        session, user.id, section.id, "Doctor appointment", start_time=wednesday
    )

    path = await generate_weekly_image(session, user)
    assert os.path.exists(path)
    assert path.endswith(".png")
    os.unlink(path)
