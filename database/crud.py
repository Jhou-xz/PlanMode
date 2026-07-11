from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, desc, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, Section, Item, Reminder, Memory, Message


DEFAULT_SYSTEM_SECTIONS = [
    {
        "name": "Schedule",
        "slug": "schedule",
        "section_type": "system",
        "schema": None,
        "view_config": {"default_view": "calendar", "views": ["calendar", "sheet"]},
    },
    {
        "name": "Tasks",
        "slug": "tasks",
        "section_type": "system",
        "schema": None,
        "view_config": {"default_view": "list", "views": ["list", "kanban"]},
    },
    {
        "name": "Idea Hub",
        "slug": "idea-hub",
        "section_type": "system",
        "schema": None,
        "view_config": {"default_view": "list", "views": ["list", "sheet"]},
    },
    {
        "name": "Completed",
        "slug": "completed",
        "section_type": "system",
        "schema": None,
        "view_config": {"default_view": "list", "views": ["list"]},
    },
]


async def get_or_create_user(
    session: AsyncSession,
    discord_user_id: str,
    discord_username: str | None = None,
) -> User:
    result = await session.execute(
        select(User).where(User.discord_user_id == discord_user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            discord_user_id=discord_user_id,
            discord_username=discord_username,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await ensure_system_sections(session, user.id)
    return user


async def set_user_timezone(session: AsyncSession, user: User, timezone: str) -> User:
    user.timezone = timezone
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_discord_id(session: AsyncSession, discord_user_id: str) -> Optional[User]:
    result = await session.execute(select(User).where(User.discord_user_id == discord_user_id))
    return result.scalar_one_or_none()


async def ensure_system_sections(session: AsyncSession, user_id: int) -> List[Section]:
    result = await session.execute(select(Section).where(Section.user_id == user_id))
    existing = {s.slug for s in result.scalars().all()}
    created = []
    for spec in DEFAULT_SYSTEM_SECTIONS:
        if spec["slug"] in existing:
            continue
        section = Section(user_id=user_id, **spec)
        session.add(section)
        created.append(section)
    if created:
        await session.commit()
        for section in created:
            await session.refresh(section)
    return created


async def create_section(
    session: AsyncSession,
    user_id: int,
    name: str,
    schema: Optional[dict] = None,
    view_config: Optional[dict] = None,
) -> Section:
    slug = _slugify(name)
    # Ensure uniqueness by appending a counter if needed
    base_slug = slug
    counter = 1
    while True:
        existing = await session.execute(
            select(Section).where(Section.user_id == user_id, Section.slug == slug)
        )
        if existing.scalar_one_or_none() is None:
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    section = Section(
        user_id=user_id,
        name=name,
        slug=slug,
        section_type="custom",
        schema=schema,
        view_config=view_config or {"default_view": "list", "views": ["list"]},
    )
    session.add(section)
    await session.commit()
    await session.refresh(section)
    return section


async def get_section_by_name(session: AsyncSession, user_id: int, name: str) -> Optional[Section]:
    result = await session.execute(
        select(Section).where(
            Section.user_id == user_id,
            func.lower(Section.name) == func.lower(name),
            Section.is_archived.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def get_section_by_slug(session: AsyncSession, user_id: int, slug: str) -> Optional[Section]:
    result = await session.execute(
        select(Section).where(
            Section.user_id == user_id,
            Section.slug == slug,
            Section.is_archived.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def list_sections(session: AsyncSession, user_id: int) -> List[Section]:
    result = await session.execute(
        select(Section)
        .where(Section.user_id == user_id, Section.is_archived.is_(False))
        .order_by(Section.created_at)
    )
    return result.scalars().all()


async def create_item(
    session: AsyncSession,
    user_id: int,
    section_id: int,
    title: str,
    content: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    due_date: Optional[datetime] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[dict] = None,
) -> Item:
    item = Item(
        user_id=user_id,
        section_id=section_id,
        title=title,
        content=content,
        start_time=start_time,
        end_time=end_time,
        due_date=due_date,
        status=status or "todo",
        priority=priority if priority is not None else 3,
        tags=tags or [],
        custom_fields=metadata,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def get_item(session: AsyncSession, item_id: int) -> Optional[Item]:
    result = await session.execute(select(Item).where(Item.id == item_id))
    return result.scalar_one_or_none()


async def get_item_with_section(session: AsyncSession, item_id: int) -> Optional[Item]:
    result = await session.execute(select(Item).where(Item.id == item_id))
    return result.scalar_one_or_none()


async def update_item(session: AsyncSession, item_id: int, **fields) -> Optional[Item]:
    item = await get_item(session, item_id)
    if item is None:
        return None
    for key, value in fields.items():
        if hasattr(item, key):
            setattr(item, key, value)
    await session.commit()
    await session.refresh(item)
    return item


async def delete_item(session: AsyncSession, item_id: int) -> bool:
    item = await get_item(session, item_id)
    if item is None:
        return False
    await session.delete(item)
    await session.commit()
    return True


async def mark_item_done(session: AsyncSession, item_id: int) -> Optional[Item]:
    item = await get_item(session, item_id)
    if item is None:
        return None

    completed_section = await get_section_by_slug(session, item.user_id, "completed")
    if completed_section is None:
        completed_section = await ensure_system_sections(session, item.user_id)
        completed_section = await get_section_by_slug(session, item.user_id, "completed")

    item.status = "done"
    item.is_archived = True
    if completed_section:
        item.section_id = completed_section.id
    await session.commit()
    await session.refresh(item)
    return item


async def search_items(
    session: AsyncSession,
    user_id: int,
    query: Optional[str] = None,
    section_name: Optional[str] = None,
    status: Optional[str] = None,
    time_range: Optional[tuple] = None,
    tags: Optional[List[str]] = None,
    limit: int = 20,
) -> List[Item]:
    stmt = select(Item).where(Item.user_id == user_id)

    if section_name:
        section = await get_section_by_name(session, user_id, section_name)
        if section:
            stmt = stmt.where(Item.section_id == section.id)

    if status:
        stmt = stmt.where(Item.status == status)

    if time_range:
        start, end = time_range
        if start and end:
            stmt = stmt.where(
                or_(
                    Item.start_time.between(start, end),
                    Item.due_date.between(start, end),
                )
            )
        elif start:
            stmt = stmt.where(
                or_(
                    Item.start_time >= start,
                    Item.due_date >= start,
                )
            )

    if tags:
        stmt = stmt.where(Item.tags.overlap(tags))  # type: ignore[attr-defined]

    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            or_(
                Item.title.ilike(like),
                Item.content.ilike(like),
            )
        )

    stmt = stmt.order_by(desc(Item.created_at)).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_items_for_time_range(
    session: AsyncSession,
    user_id: int,
    start: datetime,
    end: datetime,
    section_name: Optional[str] = None,
) -> List[Item]:
    stmt = (
        select(Item)
        .where(Item.user_id == user_id)
        .where(Item.is_archived.is_(False))
        .where(
            or_(
                Item.start_time.between(start, end),
                Item.due_date.between(start, end),
            )
        )
        .order_by(Item.start_time, Item.due_date)
    )
    if section_name:
        section = await get_section_by_name(session, user_id, section_name)
        if section:
            stmt = stmt.where(Item.section_id == section.id)
    result = await session.execute(stmt)
    return result.scalars().all()


async def create_reminder(
    session: AsyncSession,
    item_id: int,
    remind_at: datetime,
    message: Optional[str] = None,
) -> Reminder:
    reminder = Reminder(item_id=item_id, remind_at=remind_at, message=message)
    session.add(reminder)
    await session.commit()
    await session.refresh(reminder)
    return reminder


async def get_reminder_by_id(session: AsyncSession, reminder_id: int) -> Optional[Reminder]:
    result = await session.execute(select(Reminder).where(Reminder.id == reminder_id))
    return result.scalar_one_or_none()


async def delete_reminder(session: AsyncSession, reminder_id: int) -> bool:
    reminder = await get_reminder_by_id(session, reminder_id)
    if reminder is None:
        return False
    await session.delete(reminder)
    await session.commit()
    return True


async def get_upcoming_reminders(
    session: AsyncSession,
    start: datetime,
    end: datetime,
) -> List[Reminder]:
    result = await session.execute(
        select(Reminder)
        .where(Reminder.remind_at >= start)
        .where(Reminder.remind_at < end)
        .where(Reminder.sent_at.is_(None))
        .order_by(Reminder.remind_at)
    )
    return result.scalars().all()


async def get_unsent_reminders_before(session: AsyncSession, before: datetime) -> List[Reminder]:
    result = await session.execute(
        select(Reminder)
        .where(Reminder.remind_at <= before)
        .where(Reminder.sent_at.is_(None))
        .order_by(Reminder.remind_at)
    )
    return result.scalars().all()


async def mark_reminder_sent(session: AsyncSession, reminder: Reminder) -> None:
    from database.models import utc_now
    reminder.sent_at = utc_now()
    await session.commit()


async def create_memory(
    session: AsyncSession,
    user_id: int,
    content: str,
    category: str = "preference",
    importance: int = 1,
    source_item_id: Optional[int] = None,
) -> Memory:
    memory = Memory(
        user_id=user_id,
        content=content,
        category=category,
        importance=importance,
        source_item_id=source_item_id,
    )
    session.add(memory)
    await session.commit()
    await session.refresh(memory)
    return memory


async def create_message(
    session: AsyncSession,
    user_id: int,
    role: str,
    content: str,
    raw_type: str = "text",
    tool_calls: Optional[dict] = None,
) -> Message:
    msg = Message(
        user_id=user_id,
        role=role,
        content=content,
        raw_type=raw_type,
        tool_calls=tool_calls,
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


async def get_recent_messages_for_prompt(
    session: AsyncSession,
    user_id: int,
    limit: int = 15,
) -> List[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.user_id == user_id)
        .where(Message.role.in_(["user", "assistant"]))
        .order_by(desc(Message.created_at))
        .limit(limit)
    )
    messages = result.scalars().all()
    return list(reversed(messages))


async def get_messages_since(
    session: AsyncSession, user_id: int, since: datetime
) -> List[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.user_id == user_id)
        .where(Message.created_at >= since)
        .order_by(desc(Message.created_at))
    )
    return result.scalars().all()


def _slugify(name: str) -> str:
    import re
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug
