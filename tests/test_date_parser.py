import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from services.date_parser import parse_reminder_datetime, ReminderDateError, parse_time_expression


TIMEZONE = "Asia/Shanghai"
TZ = ZoneInfo(TIMEZONE)


def _assert_within(actual: datetime, expected: datetime, seconds: int = 10) -> None:
    """Assert two datetimes are within ``seconds`` of each other."""
    assert abs((actual - expected).total_seconds()) <= seconds, (
        f"Expected {expected}, got {actual}"
    )


@pytest.mark.asyncio
async def test_parse_30_min_later():
    """"30 min later" should mean now + 30 minutes, not the 30th of the month."""
    now = datetime.now(TZ)
    dt = await parse_reminder_datetime(
        iso_string="2099-07-30T20:15:00+08:00",
        original_time_expression="30 min later",
        user_timezone=TIMEZONE,
    )
    assert dt.tzinfo == TZ
    _assert_within(dt, now + timedelta(minutes=30))


@pytest.mark.asyncio
async def test_parse_in_1_hour():
    """"in 1 hour" should mean now + 1 hour."""
    now = datetime.now(TZ)
    dt = await parse_reminder_datetime(
        iso_string="2099-07-30T20:15:00+08:00",
        original_time_expression="in 1 hour",
        user_timezone=TIMEZONE,
    )
    assert dt.tzinfo == TZ
    _assert_within(dt, now + timedelta(hours=1))


@pytest.mark.asyncio
async def test_parse_tomorrow_at_4pm():
    """"tomorrow at 4pm" should resolve to tomorrow at 16:00."""
    now = datetime.now(TZ)
    dt = await parse_reminder_datetime(
        iso_string="2099-07-30T20:15:00+08:00",
        original_time_expression="tomorrow at 4pm",
        user_timezone=TIMEZONE,
    )
    assert dt.tzinfo == TZ
    expected_date = (now + timedelta(days=1)).date()
    assert dt.date() == expected_date
    assert dt.hour == 16
    assert dt.minute == 0
    assert dt.second == 0


@pytest.mark.asyncio
async def test_parse_next_monday_at_9am():
    """"next Monday at 9am" should resolve to the next Monday at 09:00."""
    now = datetime.now(TZ)
    dt = await parse_reminder_datetime(
        iso_string="2099-07-30T20:15:00+08:00",
        original_time_expression="next Monday at 9am",
        user_timezone=TIMEZONE,
    )
    assert dt.tzinfo == TZ
    # dateparser with PREFER_DATES_FROM=future returns the nearest future Monday
    # (or the Monday after if today is already that Monday).
    days_until_monday = (7 - now.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    expected_date = (now + timedelta(days=days_until_monday)).date()
    assert dt.date() == expected_date
    assert dt.hour == 9
    assert dt.minute == 0
    assert dt.second == 0


@pytest.mark.asyncio
async def test_parse_in_2_days():
    """"in 2 days" should mean now + 2 days."""
    now = datetime.now(TZ)
    dt = await parse_reminder_datetime(
        iso_string="2099-07-30T20:15:00+08:00",
        original_time_expression="in 2 days",
        user_timezone=TIMEZONE,
    )
    assert dt.tzinfo == TZ
    expected = now + timedelta(days=2)
    _assert_within(dt, expected)


@pytest.mark.asyncio
async def test_rejects_past_dates():
    """A past date should raise ReminderDateError."""
    with pytest.raises(ReminderDateError):
        await parse_reminder_datetime(
            iso_string="2020-01-01T12:00:00+08:00",
            original_time_expression="yesterday at 9am",
            user_timezone=TIMEZONE,
        )


@pytest.mark.asyncio
async def test_uses_expression_over_llm_iso():
    """The natural-language expression must win over a plausible but wrong LLM ISO."""
    now = datetime.now(TZ)
    dt = await parse_reminder_datetime(
        iso_string="2099-07-30T20:15:00+08:00",
        original_time_expression="in 30 minutes",
        user_timezone=TIMEZONE,
    )
    _assert_within(dt, now + timedelta(minutes=30))


def test_parse_time_expression_normalizes_30_min_later():
    """parse_time_expression should handle colloquial "X min later" forms."""
    now = datetime.now(TZ)
    dt = parse_time_expression("30 min later", TIMEZONE, now)
    assert dt is not None
    assert dt.tzinfo == TZ
    _assert_within(dt, now + timedelta(minutes=30))


def test_parse_time_expression_normalizes_next_monday():
    """parse_time_expression should handle "next Monday at 9am"."""
    now = datetime.now(TZ)
    dt = parse_time_expression("next Monday at 9am", TIMEZONE, now)
    assert dt is not None
    assert dt.tzinfo == TZ
    days_until_monday = (7 - now.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    expected_date = (now + timedelta(days=days_until_monday)).date()
    assert dt.date() == expected_date
    assert dt.hour == 9
    assert dt.minute == 0
