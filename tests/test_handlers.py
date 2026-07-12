import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot.handlers import MAX_MESSAGE_LENGTH, handle_message


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
@pytest.mark.asyncio
async def test_handle_message_sends_long_text_as_file_attachment():
    channel = FakeDMChannel()
    channel.send = AsyncMock()

    message = MagicMock()
    message.author.bot = False
    message.author.id = 456
    message.channel = channel
    message.content = "status report"
    message.attachments = []

    user = MagicMock()
    user.timezone_set = True

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=None)

    long_text = "A" * (MAX_MESSAGE_LENGTH + 1)

    with patch("bot.handlers.async_session", return_value=session_cm), patch(
        "bot.handlers.get_or_create_user", new_callable=AsyncMock, return_value=user
    ), patch(
        "bot.handlers.extract_text_from_message",
        new_callable=AsyncMock,
        return_value={"text": "status report", "type": "text", "language": "en"},
    ), patch(
        "bot.handlers._is_help_request", new_callable=AsyncMock, return_value=False
    ), patch(
        "bot.handlers._is_timezone_change_request", new_callable=AsyncMock, return_value=False
    ), patch(
        "bot.handlers._is_summary_time_change_request", new_callable=AsyncMock, return_value=False
    ), patch(
        "bot.handlers.run_agent", new_callable=AsyncMock, return_value=(long_text, [])
    ):
        await handle_message(message)

    assert channel.send.called
    # Find the call that sent the file attachment.
    file_calls = [
        call for call in channel.send.call_args_list
        if call.kwargs.get("file") is not None
    ]
    assert len(file_calls) == 1
    sent_file = file_calls[0].kwargs["file"]
    assert isinstance(sent_file, discord.File)
    assert sent_file.filename == "report.txt"
    assert sent_file.fp.read() == long_text.encode("utf-8")


@pytest.mark.asyncio
async def test_handle_message_sends_short_text_as_normal_message():
    channel = FakeDMChannel()
    channel.send = AsyncMock()

    message = MagicMock()
    message.author.bot = False
    message.author.id = 789
    message.channel = channel
    message.content = "hello"
    message.attachments = []

    user = MagicMock()
    user.timezone_set = True

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=None)

    short_text = "Short reply"

    with patch("bot.handlers.async_session", return_value=session_cm), patch(
        "bot.handlers.get_or_create_user", new_callable=AsyncMock, return_value=user
    ), patch(
        "bot.handlers.extract_text_from_message",
        new_callable=AsyncMock,
        return_value={"text": "hello", "type": "text", "language": "en"},
    ), patch(
        "bot.handlers._is_help_request", new_callable=AsyncMock, return_value=False
    ), patch(
        "bot.handlers._is_timezone_change_request", new_callable=AsyncMock, return_value=False
    ), patch(
        "bot.handlers._is_summary_time_change_request", new_callable=AsyncMock, return_value=False
    ), patch(
        "bot.handlers.run_agent", new_callable=AsyncMock, return_value=(short_text, [])
    ):
        await handle_message(message)

    channel.send.assert_called_once_with(short_text)

