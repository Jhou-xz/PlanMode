from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from services.scheduler import schedule_reminder
from services.tools.schemas import (
    CreateItemInput,
    ItemIdInput,
    SearchItemsInput,
    UpdateItemInput,
)
from utils.time import parse_iso_datetime
from utils.tool_result import ToolResult


async def create_item(session: AsyncSession, user, input: CreateItemInput) -> ToolResult:
    section = await crud.get_section_by_name(session, user.id, input.section_name)
    if section is None:
        return ToolResult.error(
            f"Section '{input.section_name}' not found. Ask the user before creating a new section, or use create_section first."
        )

    start_time = parse_iso_datetime(input.start_time, user.timezone)
    if input.start_time is not None and start_time is None:
        return ToolResult.error(f"Invalid ISO 8601 datetime for start_time: {input.start_time!r}")

    end_time = parse_iso_datetime(input.end_time, user.timezone)
    if input.end_time is not None and end_time is None:
        return ToolResult.error(f"Invalid ISO 8601 datetime for end_time: {input.end_time!r}")

    due_date = parse_iso_datetime(input.due_date, user.timezone)
    if input.due_date is not None and due_date is None:
        return ToolResult.error(f"Invalid ISO 8601 datetime for due_date: {input.due_date!r}")

    item = await crud.create_item(
        session=session,
        user_id=user.id,
        section_id=section.id,
        title=input.title,
        content=input.content,
        start_time=start_time,
        end_time=end_time,
        due_date=due_date,
        status=input.status or "todo",
        priority=input.priority if input.priority is not None else 3,
        tags=input.tags or [],
        metadata=input.metadata,
    )

    # Default 15-minute reminder for events with a start_time.
    if start_time:
        remind_at = start_time - timedelta(minutes=15)
        reminder = await crud.create_reminder(
            session=session,
            item_id=item.id,
            remind_at=remind_at,
            message=input.reminder_message or f"Reminder: {item.title} starts at {start_time.strftime('%H:%M')}",
        )
        schedule_reminder(reminder)

    return ToolResult.success(
        item_id=item.id,
        title=item.title,
        section=section.name,
        start_time=item.start_time.isoformat() if item.start_time else None,
        reminder_set=bool(start_time),
    )


async def update_item(session: AsyncSession, user, input: UpdateItemInput) -> ToolResult:
    fields: dict[str, Any] = {}
    if input.title is not None:
        fields["title"] = input.title
    if input.content is not None:
        fields["content"] = input.content
    if input.status is not None:
        fields["status"] = input.status
    if input.priority is not None:
        fields["priority"] = input.priority
    if input.tags is not None:
        fields["tags"] = input.tags
    if input.metadata is not None:
        fields["metadata"] = input.metadata

    if input.section_name is not None:
        section = await crud.get_section_by_name(session, user.id, input.section_name)
        if section is None:
            return ToolResult.error(f"Section '{input.section_name}' not found")
        fields["section_id"] = section.id

    for key in ("start_time", "end_time", "due_date"):
        value = getattr(input, key)
        if value is not None:
            parsed = parse_iso_datetime(value, user.timezone)
            if parsed is None:
                return ToolResult.error(f"Invalid ISO 8601 datetime for {key}: {value!r}")
            fields[key] = parsed

    if not fields:
        return ToolResult.error("No fields provided to update")

    updated = await crud.update_item(session, input.item_id, **fields)
    if updated is None:
        return ToolResult.error(f"Item {input.item_id} not found")
    return ToolResult.success(
        item_id=updated.id,
        title=updated.title,
        status=updated.status,
    )


async def delete_item(session: AsyncSession, user, input: ItemIdInput) -> ToolResult:
    item = await crud.get_item(session, input.item_id)
    if item is None:
        return ToolResult.error(f"Item {input.item_id} not found")
    # Require confirmation for destructive actions.
    return ToolResult.error(
        "This will permanently delete the item. Ask the user to confirm before proceeding.",
        needs_confirmation=True,
        item_id=input.item_id,
        title=item.title,
    )


async def confirm_delete_item(session: AsyncSession, user, input: ItemIdInput) -> ToolResult:
    success = await crud.delete_item(session, input.item_id)
    if not success:
        return ToolResult.error(f"Item {input.item_id} not found")
    return ToolResult.success(message=f"Item {input.item_id} deleted")


async def mark_item_done(session: AsyncSession, user, input: ItemIdInput) -> ToolResult:
    item = await crud.mark_item_done(session, input.item_id)
    if item is None:
        return ToolResult.error(f"Item {input.item_id} not found")
    return ToolResult.success(
        item_id=item.id,
        title=item.title,
        status=item.status,
        section=item.section.name if item.section else None,
    )


async def search_items(session: AsyncSession, user, input: SearchItemsInput) -> ToolResult:
    time_range = None
    if input.time_range:
        start = parse_iso_datetime(input.time_range.get("start"), user.timezone)
        if input.time_range.get("start") is not None and start is None:
            return ToolResult.error(f"Invalid ISO 8601 datetime for time_range.start: {input.time_range['start']!r}")
        end = parse_iso_datetime(input.time_range.get("end"), user.timezone)
        if input.time_range.get("end") is not None and end is None:
            return ToolResult.error(f"Invalid ISO 8601 datetime for time_range.end: {input.time_range['end']!r}")
        time_range = (start, end)

    items = await crud.search_items(
        session=session,
        user_id=user.id,
        query=input.query,
        section_name=input.section_name,
        status=input.status,
        time_range=time_range,
        tags=input.tags,
        limit=input.limit,
    )
    return ToolResult.success(
        count=len(items),
        items=[
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
    )
