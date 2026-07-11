from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone
from database.crud import get_or_create_user, create_message
from services.queries import answer_query


async def test_answer_query_today_messages(session):
    user = await get_or_create_user(session, discord_user_id="query_user", discord_username="query")
    await create_message(
        session,
        user_id=user.id,
        raw_type="text",
        original_text="meeting notes",
        attachment_urls=[],
        parsed_intent="chat",
        parsed_entities={},
    )

    with patch("services.queries.stream_chat_completion", new=AsyncMock(return_value="You have meeting notes today.")) as mock_stream:
        result = await answer_query(session, user, "What did I send today?", "today_messages")
        assert result == "You have meeting notes today."
        mock_stream.assert_awaited_once()
