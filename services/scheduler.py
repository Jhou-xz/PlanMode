from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from database.core import async_session
from database.models import Reminder, User
from database.crud import get_reminder_by_id, mark_reminder_sent
from bot.client import bot


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
