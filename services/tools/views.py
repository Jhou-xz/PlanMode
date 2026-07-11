from sqlalchemy.ext.asyncio import AsyncSession
from database import crud
from services.tools._utils import parse_datetime
from services import daily_view, schedule_image, status_report


async def query_status_report(session: AsyncSession, user, **kwargs) -> dict:
    text = await status_report.build_status_report(session, user)
    return {"status_report": text}


async def generate_daily_list_view(session: AsyncSession, user, **kwargs) -> dict:
    date = kwargs.get("date")
    date_dt = parse_datetime(date, user.timezone) if date else None
    text = await daily_view.generate_daily_list_view(session, user, date_dt)
    return {"daily_view": text}


async def generate_weekly_image(session: AsyncSession, user, **kwargs) -> dict:
    week_start = kwargs.get("week_start")
    week_start_dt = parse_datetime(week_start, user.timezone) if week_start else None
    path = await schedule_image.generate_weekly_image(session, user, week_start_dt)
    return {"image_path": path}
