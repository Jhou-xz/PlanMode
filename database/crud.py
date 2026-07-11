from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User, Message, Reminder, Idea, Memory


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
    return user


async def set_user_timezone(session: AsyncSession, user: User, timezone: str) -> User:
    user.timezone = timezone
    user.timezone_set = True
    await session.commit()
    await session.refresh(user)
    return user


async def create_message(
    session: AsyncSession,
    user_id: int,
    raw_type: str,
    original_text: Optional[str],
    attachment_urls: List[str],
    parsed_intent: Optional[str],
    parsed_entities: Optional[dict],
    role: str = "user",
) -> Message:
    msg = Message(
        user_id=user_id,
        role=role,
        raw_type=raw_type,
        original_text=original_text,
        attachment_urls=attachment_urls,
        parsed_intent=parsed_intent,
        parsed_entities=parsed_entities,
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


async def create_reminder(
    session: AsyncSession,
    user_id: int,
    source_message_id: Optional[int],
    title: str,
    description: Optional[str],
    remind_at: datetime,
) -> Reminder:
    r = Reminder(
        user_id=user_id,
        source_message_id=source_message_id,
        title=title,
        description=description,
        remind_at=remind_at,
    )
    session.add(r)
    await session.commit()
    await session.refresh(r)
    return r


async def create_idea(
    session: AsyncSession,
    user_id: int,
    source_message_id: Optional[int],
    content: str,
    category: Optional[str],
) -> Idea:
    i = Idea(
        user_id=user_id,
        source_message_id=source_message_id,
        content=content,
        category=category,
    )
    session.add(i)
    await session.commit()
    await session.refresh(i)
    return i


async def get_ideas(
    session: AsyncSession,
    user_id: int,
    limit: int = 50,
    since: Optional[datetime] = None,
) -> List[Idea]:
    stmt = (
        select(Idea)
        .where(Idea.user_id == user_id)
        .order_by(desc(Idea.created_at))
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(Idea.created_at >= since)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_ideas_since(
    session: AsyncSession, user_id: int, since: datetime
) -> List[Idea]:
    return await get_ideas(session, user_id, since=since, limit=1000)


async def get_reminder_by_id(session: AsyncSession, reminder_id: int) -> Optional[Reminder]:
    result = await session.execute(select(Reminder).where(Reminder.id == reminder_id))
    return result.scalar_one_or_none()


async def mark_reminder_sent(session: AsyncSession, reminder: Reminder) -> None:
    from database.models import utc_now
    reminder.sent_at = utc_now()
    await session.commit()


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


async def get_upcoming_reminders(
    session: AsyncSession,
    user_id: int,
    start: datetime,
    end: datetime,
) -> List[Reminder]:
    result = await session.execute(
        select(Reminder)
        .where(Reminder.user_id == user_id)
        .where(Reminder.remind_at >= start)
        .where(Reminder.remind_at < end)
        .where(Reminder.is_done == False)
        .order_by(Reminder.remind_at)
    )
    return result.scalars().all()


async def get_recent_messages_for_prompt(
    session: AsyncSession,
    user_id: int,
    limit: int = 15,
) -> List[Message]:
    """Return the most recent user/assistant messages, oldest first."""
    result = await session.execute(
        select(Message)
        .where(Message.user_id == user_id)
        .where(Message.role.in_(["user", "assistant"]))
        .where(Message.original_text.isnot(None))
        .order_by(desc(Message.created_at))
        .limit(limit)
    )
    messages = result.scalars().all()
    return list(reversed(messages))
