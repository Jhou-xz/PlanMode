from datetime import datetime
from zoneinfo import ZoneInfo
from services.date_parser import parse_time_expression


def parse_datetime(value, user_timezone: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo(user_timezone))
            return dt.astimezone(ZoneInfo(user_timezone))
        except ValueError:
            pass
        return parse_time_expression(value, user_timezone)
    return None
