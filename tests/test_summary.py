from unittest.mock import patch
from database.crud import get_or_create_user
from services.scheduler import scheduler, schedule_daily_summary, schedule_all_daily_summaries


async def test_schedule_daily_summary_adds_cron_job(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000008", discord_username="summary")
    schedule_daily_summary(user)
    job = scheduler.get_job(f"daily_summary_{user.id}")
    assert job is not None
    scheduler.remove_job(f"daily_summary_{user.id}")


async def test_schedule_all_daily_summaries(session):
    user1 = await get_or_create_user(session, discord_user_id="100000000000000009", discord_username="all1")
    user2 = await get_or_create_user(session, discord_user_id="100000000000000010", discord_username="all2")
    await schedule_all_daily_summaries(session)
    assert scheduler.get_job(f"daily_summary_{user1.id}") is not None
    assert scheduler.get_job(f"daily_summary_{user2.id}") is not None
    scheduler.remove_job(f"daily_summary_{user1.id}")
    scheduler.remove_job(f"daily_summary_{user2.id}")
