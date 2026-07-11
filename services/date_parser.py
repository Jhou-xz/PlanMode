import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from dateparser import parse as dateparser_parse
from zoneinfo import ZoneInfo


class ReminderDateError(ValueError):
    """Raised when a parsed reminder datetime is invalid."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


# Common expressions that dateparser struggles with on its own.
# Normalize them into a shape dateparser reliably parses while preserving meaning.
_WEEKDAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"


def _normalize_time_expression(expression: str) -> str:
    """
    Rewrite colloquial/relative expressions into forms dateparser parses reliably.

    Examples:
        - "30 min later" -> "in 30 minutes"
        - "2 hours later" -> "in 2 hours"
        - "next Monday at 9am" -> "Monday at 9am"
    """
    normalized = expression.strip().lower()

    # "30 min later" / "30 minutes later" / "30 mins later" -> "in 30 minutes"
    normalized = re.sub(
        r"(\d+)\s*(?:min|mins|minutes?)\s*later",
        r"in \1 minutes",
        normalized,
    )
    # "1 hour later" / "2 hours later"
    normalized = re.sub(
        r"(\d+)\s*(?:hour|hours?)\s*later",
        r"in \1 hours",
        normalized,
    )
    # "1 day later" / "2 days later"
    normalized = re.sub(
        r"(\d+)\s*(?:day|days?)\s*later",
        r"in \1 days",
        normalized,
    )
    # "1 week later" / "2 weeks later"
    normalized = re.sub(
        r"(\d+)\s*(?:week|weeks?)\s*later",
        r"in \1 weeks",
        normalized,
    )
    # "1 month later" / "2 months later"
    normalized = re.sub(
        r"(\d+)\s*(?:month|months?)\s*later",
        r"in \1 months",
        normalized,
    )

    # dateparser handles "Monday at 9am" with PREFER_DATES_FROM=future
    # more reliably than "next Monday at 9am".
    normalized = re.sub(
        rf"next\s+({_WEEKDAYS})",
        r"\1",
        normalized,
    )

    return normalized


def _parse_with_dateparser(expression: str, user_timezone: str, now_local: datetime) -> Optional[datetime]:
    """Parse a natural-language time expression into a timezone-aware datetime."""
    normalized = _normalize_time_expression(expression)
    try:
        dp_result = dateparser_parse(
            normalized,
            settings={
                "RELATIVE_BASE": now_local,
                "TIMEZONE": user_timezone,
                "RETURN_AS_TIMEZONE_AWARE": True,
                "PREFER_DATES_FROM": "future",
            },
        )
        if dp_result:
            return dp_result.astimezone(ZoneInfo(user_timezone))
    except Exception:
        pass

    # If normalization failed, try the original expression as a last dateparser attempt.
    try:
        dp_result = dateparser_parse(
            expression,
            settings={
                "RELATIVE_BASE": now_local,
                "TIMEZONE": user_timezone,
                "RETURN_AS_TIMEZONE_AWARE": True,
                "PREFER_DATES_FROM": "future",
            },
        )
        if dp_result:
            return dp_result.astimezone(ZoneInfo(user_timezone))
    except Exception:
        pass

    return None


def parse_time_expression(expression: str, user_timezone: str, now_local: Optional[datetime] = None) -> Optional[datetime]:
    """Parse a natural-language time expression into a timezone-aware datetime."""
    tz = ZoneInfo(user_timezone)
    if now_local is None:
        now_local = datetime.now(tz)
    return _parse_with_dateparser(expression, user_timezone, now_local)


async def parse_reminder_datetime(
    iso_string: str,
    original_time_expression: Optional[str],
    user_timezone: str,
) -> datetime:
    """
    Parse and validate a reminder datetime.

    Priority:
    1. The original natural-language time expression (e.g. "30 min later",
       "tomorrow at 4pm", "next Monday at 9am") parsed with `dateparser`.
    2. LLM-provided ISO string, but only if it is in the future and within a
       reasonable range (not months or years ahead).

    Raises ReminderDateError if the datetime cannot be parsed or is not in the future.
    """
    tz = ZoneInfo(user_timezone)
    now_local = datetime.now(tz)
    # Reasonable scheduling window: allow up to one year ahead.
    max_future = now_local + timedelta(days=365)

    parsed_local: Optional[datetime] = None
    source = "unknown"

    # 1. Primary source of truth: the user's exact natural-language expression.
    if original_time_expression:
        parsed_local = _parse_with_dateparser(original_time_expression, user_timezone, now_local)
        if parsed_local:
            source = "dateparser"

    # 2. Fallback: LLM-provided ISO string. Only trust it if it is a reasonable,
    #    future datetime. Do not blindly accept far-future or malformed dates.
    if parsed_local is None and iso_string:
        try:
            iso_dt = datetime.fromisoformat(iso_string)
            if iso_dt.tzinfo is None:
                iso_dt = iso_dt.replace(tzinfo=tz)
            iso_dt = iso_dt.astimezone(tz)
            if now_local < iso_dt <= max_future:
                parsed_local = iso_dt
                source = "iso"
        except Exception:
            pass

    if parsed_local is None:
        raise ReminderDateError(
            "I couldn't understand that time. Could you rephrase it? "
            "For example: 'tomorrow at 3pm', 'in 30 minutes', or 'next Tuesday at 9am'."
        )

    # Reject past dates. A reminder must be in the future.
    if parsed_local <= now_local:
        raise ReminderDateError(
            "That time has already passed or is right now. "
            "Could you give me a future time?"
        )

    # Reject dates unreasonably far in the future.
    if parsed_local > max_future:
        raise ReminderDateError(
            "That date is too far in the future. "
            "Please choose a time within the next year."
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
