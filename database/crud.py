from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User


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
    await session.commit()
    await session.refresh(user)
    return user
