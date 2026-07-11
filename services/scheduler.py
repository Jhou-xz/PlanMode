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


scheduler = AsyncIOScheduler()


async def send_reminder(reminder_id: int):
    async with async_session() as session:
        reminder = await get_reminder_by_id(session, reminder_id)
        if not reminder or reminder.sent_at:
            return

        user = await session.get(User, reminder.user_id)
        if not user:
            return

        discord_user = await bot.fetch_user(int(user.discord_user_id))
        if discord_user:
            await discord_user.send(f"⏰ Reminder: {reminder.title}")

        await mark_reminder_sent(session, reminder)


def schedule_reminder(reminder: Reminder):
    scheduler.add_job(
        send_reminder,
        trigger=DateTrigger(run_date=reminder.remind_at),
        args=[reminder.id],
        id=f"reminder_{reminder.id}",
        replace_existing=True,
    )


def schedule_daily_summary(user: User):
    hour, minute = map(int, user.summary_time.strftime("%H:%M").split(":"))
    scheduler.add_job(
        send_daily_summary,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=user.timezone),
        args=[user.id],
        id=f"daily_summary_{user.id}",
        replace_existing=True,
    )


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
    scheduler.add_job(
        compress_user_memory,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0, timezone=user.timezone),
        args=[user.id],
        id=f"memory_compression_{user.id}",
        replace_existing=True,
    )


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
