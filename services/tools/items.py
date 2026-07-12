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


async def create_item(session: AsyncSession, user, **kwargs) -> dict:
    section_name = kwargs.get("section_name")
    if not section_name:
        return {"error": "section_name is required"}

    section = await crud.get_section_by_name(session, user.id, section_name)
    if section is None:
        return {
            "error": f"Section '{section_name}' not found. Ask the user before creating a new section, or use create_section first."
        }

    start_time = _parse_iso_datetime(kwargs.get("start_time"), user.timezone)
    if kwargs.get("start_time") is not None and start_time is None:
        return {"error": f"Invalid ISO 8601 datetime for start_time: {kwargs.get('start_time')!r}"}

    end_time = _parse_iso_datetime(kwargs.get("end_time"), user.timezone)
    if kwargs.get("end_time") is not None and end_time is None:
        return {"error": f"Invalid ISO 8601 datetime for end_time: {kwargs.get('end_time')!r}"}

    due_date = _parse_iso_datetime(kwargs.get("due_date"), user.timezone)
    if kwargs.get("due_date") is not None and due_date is None:
        return {"error": f"Invalid ISO 8601 datetime for due_date: {kwargs.get('due_date')!r}"}

    item = await crud.create_item(
        session=session,
        user_id=user.id,
        section_id=section.id,
        title=kwargs.get("title", "Untitled"),
        content=kwargs.get("content"),
        start_time=start_time,
        end_time=end_time,
        due_date=due_date,
        status=kwargs.get("status") or "todo",
        priority=kwargs.get("priority") if kwargs.get("priority") is not None else 3,
        tags=kwargs.get("tags") or [],
        metadata=kwargs.get("metadata"),
    )

    # Default 15-minute reminder for events with a start_time
    if start_time and not kwargs.get("skip_default_reminder"):
        remind_at = start_time - timedelta(minutes=15)
        await crud.create_reminder(
            session=session,
            item_id=item.id,
            remind_at=remind_at,
            message=kwargs.get("reminder_message") or f"Reminder: {item.title} starts at {start_time.strftime('%H:%M')}",
        )

    return {
        "success": True,
        "item_id": item.id,
        "title": item.title,
        "section": section.name,
        "start_time": item.start_time.isoformat() if item.start_time else None,
        "reminder_set": bool(start_time),
    }


async def update_item(session: AsyncSession, user, **kwargs) -> dict:
    item_id = kwargs.get("item_id")
    if not item_id:
        return {"error": "item_id is required"}

    fields = {k: v for k, v in kwargs.items() if k != "item_id" and v is not None}
    if "section_name" in fields:
        section = await crud.get_section_by_name(session, user.id, fields.pop("section_name"))
        if section is None:
            return {"error": f"Section '{kwargs['section_name']}' not found"}
        fields["section_id"] = section.id

    for key in ("start_time", "end_time", "due_date"):
        if key in fields:
            parsed = _parse_iso_datetime(fields[key], user.timezone)
            if parsed is None:
                return {"error": f"Invalid ISO 8601 datetime for {key}: {fields[key]!r}"}
            fields[key] = parsed

    updated = await crud.update_item(session, item_id, **fields)
    if updated is None:
        return {"error": f"Item {item_id} not found"}
    return {
        "success": True,
        "item_id": updated.id,
        "title": updated.title,
        "status": updated.status,
    }


async def delete_item(session: AsyncSession, user, **kwargs) -> dict:
    item_id = kwargs.get("item_id")
    if not item_id:
        return {"error": "item_id is required"}
    success = await crud.delete_item(session, item_id)
    if not success:
        return {"error": f"Item {item_id} not found"}
    return {"success": True, "message": f"Item {item_id} deleted"}


async def mark_item_done(session: AsyncSession, user, **kwargs) -> dict:
    item_id = kwargs.get("item_id")
    if not item_id:
        return {"error": "item_id is required"}
    item = await crud.mark_item_done(session, item_id)
    if item is None:
        return {"error": f"Item {item_id} not found"}
    return {
        "success": True,
        "item_id": item.id,
        "title": item.title,
        "status": item.status,
        "section": item.section.name if item.section else None,
    }


async def search_items(session: AsyncSession, user, **kwargs) -> dict:
    time_range = None
    if kwargs.get("time_range"):
        tr = kwargs["time_range"]
        start = _parse_iso_datetime(tr.get("start"), user.timezone)
        if tr.get("start") is not None and start is None:
            return {"error": f"Invalid ISO 8601 datetime for time_range.start: {tr.get('start')!r}"}
        end = _parse_iso_datetime(tr.get("end"), user.timezone)
        if tr.get("end") is not None and end is None:
            return {"error": f"Invalid ISO 8601 datetime for time_range.end: {tr.get('end')!r}"}
        time_range = (start, end)

    items = await crud.search_items(
        session=session,
        user_id=user.id,
        query=kwargs.get("query"),
        section_name=kwargs.get("section_name"),
        status=kwargs.get("status"),
        time_range=time_range,
        tags=kwargs.get("tags"),
        limit=kwargs.get("limit", 20),
    )
    return {
        "count": len(items),
        "items": [
            {
                "id": i.id,
                "title": i.title,
                "section": i.section.name if i.section else None,
                "status": i.status,
                "start_time": i.start_time.isoformat() if i.start_time else None,
                "due_date": i.due_date.isoformat() if i.due_date else None,
                "tags": i.tags,
            }
            for i in items
        ],
    }
