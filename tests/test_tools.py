from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock


from database.crud import get_or_create_user, get_section_by_slug
from services.scheduler import scheduler
from services.tools import TOOL_SCHEMAS, TERMINAL_TOOLS, execute_tool_call
from services.tools.schemas import CreateItemInput


class FakeToolCall:
    def __init__(self, name: str, arguments: str, call_id: str = "call_1"):
        self.id = call_id
        self.type = "function"
        self.function = MagicMock()
        self.function.name = name
        self.function.arguments = arguments


async def test_execute_tool_call_creates_item(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000100", discord_username="tools")
    await get_section_by_slug(session, user.id, "tasks")

    start_time = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
    iso = start_time.isoformat()

    call = FakeToolCall(
        "create_item",
        f'{{"section_name": "Tasks", "title": "Buy milk", "start_time": "{iso}"}}',
    )
    result = await execute_tool_call(session, user, call)

    assert result["success"] is True
    assert result["title"] == "Buy milk"
    assert result["section"] == "Tasks"
    assert result["reminder_set"] is True

    # The default reminder should be scheduled live.
    job = scheduler.get_job(f"reminder_{result['item_id']}")
    assert job is not None
    scheduler.remove_job(job.id)


async def test_execute_tool_call_validates_arguments(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000101", discord_username="validate")

    call = FakeToolCall("create_item", '{"title": "Missing section"}')
    result = await execute_tool_call(session, user, call)

    assert result["success"] is False
    assert "section_name" in result["error"]


async def test_execute_tool_call_unknown_tool(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000102", discord_username="unknown")

    call = FakeToolCall("not_a_real_tool", "{}")
    result = await execute_tool_call(session, user, call)

    assert result["success"] is False
    assert "Unknown tool" in result["error"]


async def test_execute_tool_call_delete_item_requires_confirmation(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000103", discord_username="delete")
    section = await get_section_by_slug(session, user.id, "tasks")
    from database.crud import create_item as crud_create_item

    item = await crud_create_item(session, user.id, section.id, "Temporary task")

    call = FakeToolCall("delete_item", f'{{"item_id": {item.id}}}')
    result = await execute_tool_call(session, user, call)

    assert result["success"] is False
    assert result.get("needs_confirmation") is True


async def test_terminal_tools_are_exposed_and_callable(session):
    assert "send_message" in TERMINAL_TOOLS
    assert "ask_user" in TERMINAL_TOOLS

    user = await get_or_create_user(session, discord_user_id="100000000000000104", discord_username="terminal")
    call = FakeToolCall("send_message", '{"text": "Hello!"}')
    result = await execute_tool_call(session, user, call)

    assert result["success"] is True
    assert result["final_response"] == "Hello!"
    assert result["type"] == "send_message"


def test_tool_schemas_generated_from_pydantic():
    names = {schema["function"]["name"] for schema in TOOL_SCHEMAS}
    assert "create_item" in names
    assert "update_item" in names
    assert "send_message" in names
    # Confirmation tools are exposed so the LLM can call them after user confirmation.
    assert "confirm_delete_item" in names
    # Reasoning tool is internal-only.
    assert "reasoning" not in names


async def test_create_item_input_model(session):
    user = await get_or_create_user(session, discord_user_id="100000000000000105", discord_username="input")
    input_model = CreateItemInput(section_name="Tasks", title="Test task", priority=5)

    from services.tools.items import create_item

    result = await create_item(session, user, input_model)
    assert result.to_dict()["success"] is True
    assert result.to_dict()["title"] == "Test task"
