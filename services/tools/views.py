from sqlalchemy.ext.asyncio import AsyncSession

from services import daily_view, schedule_image, status_report
from services.tools.schemas import EmptyInput, OptionalDateInput, OptionalWeekStartInput
from utils.tool_result import ToolResult


async def query_status_report(session: AsyncSession, user, input: EmptyInput) -> ToolResult:
    text = await status_report.build_status_report(session, user)
    return ToolResult.success(status_report=text)


async def generate_daily_list_view(session: AsyncSession, user, input: OptionalDateInput) -> ToolResult:
    from utils.time import parse_iso_datetime

    date_dt = parse_iso_datetime(input.date, user.timezone) if input.date else None
    text = await daily_view.generate_daily_list_view(session, user, date_dt)
    return ToolResult.success(daily_view=text)


async def generate_weekly_image(session: AsyncSession, user, input: OptionalWeekStartInput) -> ToolResult:
    from utils.time import parse_iso_datetime

    week_start_dt = parse_iso_datetime(input.week_start, user.timezone) if input.week_start else None
    path = await schedule_image.generate_weekly_image(session, user, week_start_dt)
    return ToolResult.success(image_path=path)


async def generate_daily_image(session: AsyncSession, user, input: OptionalDateInput) -> ToolResult:
    from utils.time import parse_iso_datetime

    date_dt = parse_iso_datetime(input.date, user.timezone) if input.date else None
    path = await daily_view.generate_daily_list_image(session, user, date_dt)
    return ToolResult.success(image_path=path)
