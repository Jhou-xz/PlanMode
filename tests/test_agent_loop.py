from unittest.mock import AsyncMock, MagicMock, patch

from database.crud import get_or_create_user
from services.agent import MAX_ITERATIONS, run_agent


class FakeToolCall:
    def __init__(self, name: str, arguments: str, call_id: str = "call_1"):
        self.id = call_id
        self.type = "function"
        self.function = MagicMock()
        self.function.name = name
        self.function.arguments = arguments


async def test_agent_loop_respects_max_iterations(session):
    user = await get_or_create_user(
        session, discord_user_id="100000000000000300", discord_username="maxiter"
    )

    call_count = 0

    def make_response(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = None
        response.choices[0].message.tool_calls = [
            FakeToolCall(
                "query_status_report", "{}", f"call_status_{call_count}"
            )
        ]
        return response

    with (
        patch(
            "services.agent.chat_completion",
            new_callable=AsyncMock,
            side_effect=make_response,
        ),
        patch(
            "services.agent.chat_completion_text",
            new_callable=AsyncMock,
            return_value='{"memories": []}',
        ),
        patch(
            "services.agent.execute_tool_call",
            new_callable=AsyncMock,
            return_value={"success": True, "report": "All sections are clear."},
        ),
    ):
        final_text, image_paths = await run_agent(session, user, "status report")

    assert call_count == MAX_ITERATIONS
    assert "too long" in final_text.lower()
    assert image_paths == []
