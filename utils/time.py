from datetime import datetime
from zoneinfo import ZoneInfo


def parse_iso_datetime(value: datetime | str | None, user_timezone: str) -> datetime | None:
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
