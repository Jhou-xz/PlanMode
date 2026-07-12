import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot.handlers import handle_message


class FakeDMChannel(discord.DMChannel):
    def __init__(self):
        self.typing_entered = False
        self.typing_exited = False

    def typing(self):
        channel = self

        class TypingContextManager:
            async def __aenter__(self):
                channel.typing_entered = True

            async def __aexit__(self, exc_type, exc, tb):
                channel.typing_exited = True
                return False

        return TypingContextManager()


@pytest.mark.asyncio
async def test_handle_message_sends_error_dm_and_uses_typing_on_exception():
    channel = FakeDMChannel()
    channel.send = AsyncMock()

    message = MagicMock()
    message.author.bot = False
    message.author.id = 123
    message.channel = channel
    message.content = "hello"
    message.attachments = []

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("bot.handlers.async_session", return_value=session_cm), patch(
        "bot.handlers.get_or_create_user", new_callable=AsyncMock
    ), patch(
        "bot.handlers.extract_text_from_message",
        new_callable=AsyncMock,
        return_value={"text": "hello", "type": "text", "language": "en"},
    ), patch(
        "bot.handlers._is_timezone_change_request", new_callable=AsyncMock, return_value=False
    ), patch(
        "bot.handlers.build_image_content", new_callable=AsyncMock, return_value=[]
    ), patch(
        "bot.handlers.run_agent", new_callable=AsyncMock, side_effect=RuntimeError("boom")
    ):
        await handle_message(message)

    assert channel.typing_entered is True
    assert channel.typing_exited is True
    channel.send.assert_called_once_with(
        "I ran into a problem. The error has been logged."
    )
