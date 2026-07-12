from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from database import crud
from services import daily_view, schedule_image, status_report


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


async def query_status_report(session: AsyncSession, user, **kwargs) -> dict:
    text = await status_report.build_status_report(session, user)
    return {"status_report": text}


async def generate_daily_list_view(session: AsyncSession, user, **kwargs) -> dict:
    date = kwargs.get("date")
    if date is not None:
        date_dt = _parse_iso_datetime(date, user.timezone)
        if date_dt is None:
            return {"error": f"Invalid ISO 8601 date for date: {date!r}"}
    else:
        date_dt = None
    text = await daily_view.generate_daily_list_view(session, user, date_dt)
    return {"daily_view": text}


async def generate_weekly_image(session: AsyncSession, user, **kwargs) -> dict:
    week_start = kwargs.get("week_start")
    if week_start is not None:
        week_start_dt = _parse_iso_datetime(week_start, user.timezone)
        if week_start_dt is None:
            return {"error": f"Invalid ISO 8601 date for week_start: {week_start!r}"}
    else:
        week_start_dt = None
    path = await schedule_image.generate_weekly_image(session, user, week_start_dt)
    return {"image_path": path}
