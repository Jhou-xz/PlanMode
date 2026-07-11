from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from apscheduler.triggers.date import DateTrigger
from database.crud import get_or_create_user, create_reminder
from services.scheduler import scheduler, schedule_reminder, send_reminder


async def test_schedule_reminder_adds_job(session):
    user = await get_or_create_user(session, discord_user_id="scheduler_user", discord_username="scheduler")
    remind_at = datetime(2099, 1, 1, 12, 0, tzinfo=timezone.utc)
    reminder = await create_reminder(
        session, user.id, None, "Test reminder", None, remind_at
    )
    schedule_reminder(reminder)
    job = scheduler.get_job(f"reminder_{reminder.id}")
    assert job is not None
    assert isinstance(job.trigger, DateTrigger)
    scheduler.remove_job(f"reminder_{reminder.id}")


async def test_send_reminder_skips_if_already_sent(session):
    user = await get_or_create_user(session, discord_user_id="sent_user", discord_username="sent")
    remind_at = datetime(2099, 1, 1, 12, 0, tzinfo=timezone.utc)
    reminder = await create_reminder(
        session, user.id, None, "Sent reminder", None, remind_at
    )
    reminder.sent_at = datetime.now(timezone.utc)
    await session.commit()

    with patch("services.scheduler.bot.fetch_user", new=AsyncMock()) as mock_fetch:
        await send_reminder(reminder.id, session=session)
        mock_fetch.assert_not_awaited()
