import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from database.core import async_session
from database.models import Reminder, User
from database.crud import get_reminder_by_id, mark_reminder_sent
from bot.client import bot
from services.summary import send_daily_summary
from services.memory_compression import compress_user_memory


logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def send_reminder(reminder_id: int, session: AsyncSession | None = None):
    if session is None:
        async with async_session() as session:
            await _do_send_reminder(reminder_id, session)
    else:
        await _do_send_reminder(reminder_id, session)


async def _do_send_reminder(reminder_id: int, session: AsyncSession):
    logger.info("Firing reminder job id=%s", reminder_id)
    reminder = await get_reminder_by_id(session, reminder_id)
    if not reminder or reminder.sent_at:
        logger.info("Skipping reminder id=%s (not found or already sent)", reminder_id)
        return

    user = await session.get(User, reminder.user_id)
    if not user:
        logger.warning("Skipping reminder id=%s: user not found", reminder_id)
        return

    discord_user = await bot.fetch_user(int(user.discord_user_id))
    if discord_user:
        await discord_user.send(f"⏰ Reminder: {reminder.title}")
        logger.info("Sent reminder id=%s to discord user %s", reminder_id, user.discord_user_id)
    else:
        logger.warning("Could not fetch Discord user %s for reminder id=%s", user.discord_user_id, reminder_id)

    await mark_reminder_sent(session, reminder)


def schedule_reminder(reminder: Reminder):
    now = datetime.now(timezone.utc)
    if reminder.remind_at.tzinfo is None:
        logger.error("Refusing to schedule reminder id=%s without timezone info", reminder.id)
        return

    if reminder.remind_at <= now:
        logger.warning(
            "Refusing to schedule reminder id=%s in the past (remind_at=%s, now=%s)",
            reminder.id,
            reminder.remind_at.isoformat(),
            now.isoformat(),
        )
        return

    job_id = f"reminder_{reminder.id}"
    scheduler.add_job(
        send_reminder,
        trigger=DateTrigger(run_date=reminder.remind_at),
        args=[reminder.id],
        id=job_id,
        replace_existing=True,
    )
    logger.info(
        "Scheduled reminder id=%s at %s (job_id=%s)",
        reminder.id,
        reminder.remind_at.isoformat(),
        job_id,
    )


def schedule_daily_summary(user: User):
    hour, minute = map(int, user.summary_time.strftime("%H:%M").split(":"))
    job_id = f"daily_summary_{user.id}"
    scheduler.add_job(
        send_daily_summary,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=user.timezone),
        args=[user.id],
        id=job_id,
        replace_existing=True,
    )
    logger.info("Scheduled daily summary for user id=%s at %s:%s (%s)", user.id, hour, minute, user.timezone)


async def schedule_all_daily_summaries(session: AsyncSession | None = None):
    if session is None:
        async with async_session() as session:
            await _do_schedule_all_daily_summaries(session)
    else:
        await _do_schedule_all_daily_summaries(session)


async def _do_schedule_all_daily_summaries(session: AsyncSession):
    result = await session.execute(select(User))
    users = result.scalars().all()
    for user in users:
        schedule_daily_summary(user)


def schedule_memory_compression(user: User):
    job_id = f"memory_compression_{user.id}"
    scheduler.add_job(
        compress_user_memory,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0, timezone=user.timezone),
        args=[user.id],
        id=job_id,
        replace_existing=True,
    )
    logger.info("Scheduled memory compression for user id=%s", user.id)


async def schedule_all_memory_compression(session: AsyncSession | None = None):
    if session is None:
        async with async_session() as session:
            await _do_schedule_all_memory_compression(session)
    else:
        await _do_schedule_all_memory_compression(session)


async def _do_schedule_all_memory_compression(session: AsyncSession):
    result = await session.execute(select(User))
    users = result.scalars().all()
    for user in users:
        schedule_memory_compression(user)
