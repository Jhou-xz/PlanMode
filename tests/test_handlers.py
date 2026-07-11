from unittest.mock import MagicMock, AsyncMock, patch
import discord
from sqlalchemy import update
from database.crud import get_or_create_user
from database.models import User
from bot.handlers import handle_message


def _make_message(content: str, user_id: str = "123456"):
    msg = MagicMock(spec=discord.Message)
    msg.author.bot = False
    msg.author.id = int(user_id)
    msg.author.__str__ = MagicMock(return_value=f"testuser#{user_id}")
    msg.channel = MagicMock(spec=discord.DMChannel)
    msg.content = content
    msg.attachments = []
    msg.flags.voice = False
    msg.channel.send = AsyncMock()
    return msg


def _patch_session(session):
    """Return a patch that makes bot.handlers.async_session yield the test session."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return patch("bot.handlers.async_session", return_value=ctx)


async def _setup_user(session, discord_user_id: str, timezone: str):
    user = await get_or_create_user(session, discord_user_id=discord_user_id, discord_username="testuser")
    await session.execute(
        update(User).where(User.id == user.id).values(timezone=timezone, timezone_set=True)
    )
    await session.commit()
    return user


async def test_handler_saves_preferred_language_en(session):
    await _setup_user(session, "123456", "Asia/Shanghai")
    msg = _make_message("Hello, how are you?", user_id="123456")
    mock_parsed = {
        "intent": "chat",
        "language": "en",
        "response_text": "I'm doing well, thanks!",
        "entities": {},
        "actions": [],
        "new_memories": [],
    }

    with _patch_session(session):
        with patch("bot.handlers.parse_intent", new=AsyncMock(return_value=mock_parsed)):
            with patch("bot.handlers.extract_text_from_message", new=AsyncMock(return_value={"text": "Hello, how are you?", "type": "text", "language": None})):
                with patch("bot.handlers.build_image_content", new=AsyncMock(return_value=[])):
                    await handle_message(msg)

    user = await _setup_user(session, "123456", "Asia/Shanghai")  # re-fetch to refresh
    await session.refresh(user)
    assert user.preferred_language == "en"
    msg.channel.send.assert_awaited_with("I'm doing well, thanks!")


async def test_handler_saves_preferred_language_zh(session):
    await _setup_user(session, "654321", "Asia/Shanghai")
    msg = _make_message("你好，最近怎么样？", user_id="654321")
    mock_parsed = {
        "intent": "chat",
        "language": "zh",
        "response_text": "我很好，谢谢！",
        "entities": {},
        "actions": [],
        "new_memories": [],
    }

    with _patch_session(session):
        with patch("bot.handlers.parse_intent", new=AsyncMock(return_value=mock_parsed)):
            with patch("bot.handlers.extract_text_from_message", new=AsyncMock(return_value={"text": "你好，最近怎么样？", "type": "text", "language": None})):
                with patch("bot.handlers.build_image_content", new=AsyncMock(return_value=[])):
                    await handle_message(msg)

    user = await _setup_user(session, "654321", "Asia/Shanghai")
    await session.refresh(user)
    assert user.preferred_language == "zh"
    msg.channel.send.assert_awaited_with("我很好，谢谢！")
