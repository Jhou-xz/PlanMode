from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from apscheduler.triggers.date import DateTrigger
from database.crud import get_or_create_user, create_reminder
from services.scheduler import scheduler, schedule_reminder, send_reminder


async def test_schedule_reminder_adds_job(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000001", discord_username="scheduler")
    remind_at = datetime(2099, 1, 1, 12, 0, tzinfo=timezone.utc)
    reminder = await create_reminder(
        session, user.id, None, "Test reminder", None, remind_at
    )
    schedule_reminder(reminder)
    job = scheduler.get_job(f"reminder_{reminder.id}")
    assert job is not None
    assert isinstance(job.trigger, DateTrigger)
    scheduler.remove_job(f"reminder_{reminder.id}")


async def test_schedule_reminder_rejects_past_date(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000002", discord_username="past")
    remind_at = datetime(2000, 1, 1, 12, 0, tzinfo=timezone.utc)
    reminder = await create_reminder(
        session, user.id, None, "Past reminder", None, remind_at
    )
    schedule_reminder(reminder)
    job = scheduler.get_job(f"reminder_{reminder.id}")
    assert job is None


async def test_send_reminder_skips_if_already_sent(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000003", discord_username="sent")
    remind_at = datetime(2099, 1, 1, 12, 0, tzinfo=timezone.utc)
    reminder = await create_reminder(
        session, user.id, None, "Sent reminder", None, remind_at
    )
    reminder.sent_at = datetime.now(timezone.utc)
    await session.commit()

    with patch("services.scheduler.bot.fetch_user", new=AsyncMock()) as mock_fetch:
        await send_reminder(reminder.id, session=session)
        mock_fetch.assert_not_awaited()


async def test_send_reminder_logs_and_sends_dm(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000004", discord_username="fire")
    remind_at = datetime(2099, 1, 1, 12, 0, tzinfo=timezone.utc)
    reminder = await create_reminder(
        session, user.id, None, "Fire reminder", None, remind_at
    )

    mock_user = MagicMock()
    mock_user.send = AsyncMock()

    with patch("services.scheduler.bot.fetch_user", new=AsyncMock(return_value=mock_user)) as mock_fetch:
        await send_reminder(reminder.id, session=session)
        mock_fetch.assert_awaited_once_with(int(user.discord_user_id))
        mock_user.send.assert_awaited_once()

    await session.refresh(reminder)
    assert reminder.sent_at is not None
