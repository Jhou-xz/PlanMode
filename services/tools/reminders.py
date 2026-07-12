from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from services.scheduler import schedule_reminder
from services.tools.schemas import ListRemindersInput, ReminderIdInput, SetReminderInput
from utils.time import parse_iso_datetime
from utils.tool_result import ToolResult


async def set_reminder(session: AsyncSession, user, input: SetReminderInput) -> ToolResult:
    item = await crud.get_item(session, input.item_id)
    if item is None:
        return ToolResult.error(f"Item {input.item_id} not found")

    remind_at_dt: datetime | None
    if input.remind_at is None:
        if item.start_time is None:
            return ToolResult.error(
                "Item has no start_time; provide a remind_at explicitly or add a start_time to the item."
            )
        remind_at_dt = item.start_time - timedelta(minutes=15)
    else:
        remind_at_dt = parse_iso_datetime(input.remind_at, user.timezone)
        if remind_at_dt is None:
            return ToolResult.error(f"Invalid ISO 8601 datetime for remind_at: {input.remind_at!r}")

    now = datetime.now(ZoneInfo(user.timezone))
    if remind_at_dt <= now:
        return ToolResult.error("Reminder time must be in the future")

    reminder = await crud.create_reminder(
        session=session,
        item_id=item.id,
        remind_at=remind_at_dt,
        message=input.message or f"Reminder: {item.title}",
    )

    # Schedule the live job so the reminder actually fires.
    schedule_reminder(reminder)

    return ToolResult.success(
        reminder_id=reminder.id,
        remind_at=reminder.remind_at.isoformat(),
    )


async def list_reminders(session: AsyncSession, user, input: ListRemindersInput) -> ToolResult:
    item_id = input.item_id
    reminders = await crud.get_reminders_for_user(session, user.id, item_id=item_id)
    return ToolResult.success(
        count=len(reminders),
        reminders=[
            {
                "id": r.id,
                "item_id": r.item_id,
                "remind_at": r.remind_at.isoformat(),
                "message": r.message,
                "sent": r.sent_at is not None,
            }
            for r in reminders
        ],
    )


async def get_reminder(session: AsyncSession, user, input: ReminderIdInput) -> ToolResult:
    reminder = await crud.get_reminder_by_id(session, input.reminder_id)
    if reminder is None:
        return ToolResult.error(f"Reminder {input.reminder_id} not found")
    return ToolResult.success(
        id=reminder.id,
        item_id=reminder.item_id,
        remind_at=reminder.remind_at.isoformat(),
        message=reminder.message,
        sent=reminder.sent_at is not None,
    )


async def delete_reminder(session: AsyncSession, user, input: ReminderIdInput) -> ToolResult:
    reminder = await crud.get_reminder_by_id(session, input.reminder_id)
    if reminder is None:
        return ToolResult.error(f"Reminder {input.reminder_id} not found")
    return ToolResult.error(
        "This will permanently delete the reminder. Ask the user to confirm before proceeding.",
        needs_confirmation=True,
        reminder_id=input.reminder_id,
    )


async def confirm_delete_reminder(session: AsyncSession, user, input: ReminderIdInput) -> ToolResult:
    success = await crud.delete_reminder(session, input.reminder_id)
    if not success:
        return ToolResult.error(f"Reminder {input.reminder_id} not found")
    return ToolResult.success(message=f"Reminder {input.reminder_id} deleted")
