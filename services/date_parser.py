from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from dateutil import parser as dateutil_parser
from dateparser import parse as dateparser_parse
from zoneinfo import ZoneInfo


class ReminderDateError(ValueError):
    """Raised when a parsed reminder datetime is invalid."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


async def parse_reminder_datetime(
    iso_string: str,
    original_time_expression: Optional[str],
    user_timezone: str,
) -> datetime:
    """
    Parse and validate a reminder datetime.

    Prefer parsing the original time expression via dateparser (natural language)
    with the current datetime in the user's timezone as the reference. Fall back
    to dateutil, then to the LLM-provided ISO string.

    Raises ReminderDateError if the datetime is more than 30 days in the past
    or has already passed.
    """
    tz = ZoneInfo(user_timezone)
    now_local = datetime.now(tz)

    parsed_local: Optional[datetime] = None

    if original_time_expression:
        # Try dateparser first for natural language like "tomorrow at 4pm".
        try:
            dp_result = dateparser_parse(
                original_time_expression,
                settings={"RELATIVE_BASE": now_local, "TIMEZONE": user_timezone, "RETURN_AS_TIMEZONE_AWARE": True},
            )
            if dp_result:
                parsed_local = dp_result
        except Exception:
            parsed_local = None

        # Fall back to dateutil if dateparser fails.
        if parsed_local is None:
            try:
                parsed_local = dateutil_parser.parse(
                    original_time_expression,
                    default=now_local,
                    fuzzy=True,
                )
                if parsed_local.tzinfo is None:
                    parsed_local = parsed_local.replace(tzinfo=tz)
            except Exception:
                parsed_local = None

    if parsed_local is None:
        try:
            parsed_local = datetime.fromisoformat(iso_string)
            if parsed_local.tzinfo is None:
                parsed_local = parsed_local.replace(tzinfo=tz)
        except Exception as exc:
            raise ReminderDateError(
                "I couldn't understand that time. Could you rephrase it? "
                "For example: 'tomorrow at 3pm' or 'next Tuesday at 9am'."
            ) from exc

    # Ensure the datetime is in the user's timezone and is timezone-aware.
    parsed_local = parsed_local.astimezone(tz)

    # Reject dates that are more than 30 days in the past.
    thirty_days_ago = now_local - timedelta(days=30)
    if parsed_local < thirty_days_ago:
        raise ReminderDateError(
            "That date looks like it's more than 30 days in the past. "
            "Please tell me a future date or a recent relative time like 'tomorrow'."
        )

    # Reject dates that have already passed.
    if parsed_local < now_local:
        raise ReminderDateError(
            "That time has already passed. Could you give me a future time?"
        )

    return parsed_local


async def validate_and_schedule_time(
    iso_string: str,
    original_time_expression: Optional[str],
    user_timezone: str,
) -> Tuple[datetime, Optional[str]]:
    """
    Convenience wrapper that returns (datetime, None) on success or
    (None, error_message) on failure.
    """
    try:
        dt = await parse_reminder_datetime(iso_string, original_time_expression, user_timezone)
        return dt, None
    except ReminderDateError as exc:
        return None, exc.message
