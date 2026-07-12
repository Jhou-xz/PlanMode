from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud


def _parse_iso_datetime(value, user_timezone: str) -> datetime | None:
    """Parse an ISO 8601 string into a timezone-aware datetime in the user's timezone."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(ZoneInfo(user_timezone))
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(user_timezone))
        return dt.astimezone(ZoneInfo(user_timezone))
    except Exception:
        return None


async def set_reminder(session: AsyncSession, user, **kwargs) -> dict:
    item_id = kwargs.get("item_id")
    remind_at = kwargs.get("remind_at")
    message = kwargs.get("message")

    item = await crud.get_item(session, item_id)
    if item is None:
        return {"error": f"Item {item_id} not found"}

    if remind_at is None:
        if item.start_time is None:
            return {
                "error": "Item has no start_time; provide a remind_at explicitly or add a start_time to the item."
            }
        remind_at_dt = item.start_time - timedelta(minutes=15)
    else:
        remind_at_dt = _parse_iso_datetime(remind_at, user.timezone)
        if remind_at_dt is None:
            return {"error": f"Invalid ISO 8601 datetime for remind_at: {remind_at!r}"}

    now = datetime.now(ZoneInfo(user.timezone))
    if remind_at_dt <= now:
        return {"error": "Reminder time must be in the future"}

    reminder = await crud.create_reminder(
        session=session,
        item_id=item.id,
        remind_at=remind_at_dt,
        message=message or f"Reminder: {item.title}",
    )
    return {
        "success": True,
        "reminder_id": reminder.id,
        "remind_at": reminder.remind_at.isoformat(),
    }


async def delete_reminder(session: AsyncSession, user, **kwargs) -> dict:
    reminder_id = kwargs.get("reminder_id")
    if not reminder_id:
        return {"error": "reminder_id is required"}
    success = await crud.delete_reminder(session, reminder_id)
    if not success:
        return {"error": f"Reminder {reminder_id} not found"}
    return {"success": True, "message": f"Reminder {reminder_id} deleted"}
