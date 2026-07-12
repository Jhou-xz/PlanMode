import json
from typing import Any, Awaitable, Callable, Dict, List, Type, cast

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from services.tools.items import (
    confirm_delete_item,
    create_item,
    delete_item,
    mark_item_done,
    search_items,
    update_item,
)
from services.tools.memory_tools import (
    confirm_delete_memory,
    delete_memory,
    save_memory,
    search_memories,
)
from services.tools.messaging import ask_user, send_message
from services.tools.reasoning import reasoning
from services.tools.reminders import (
    confirm_delete_reminder,
    delete_reminder,
    get_reminder,
    list_reminders,
    set_reminder,
)
from services.tools.schemas import (
    AskUserInput,
    CreateItemInput,
    CreateSectionInput,
    EmptyInput,
    ItemIdInput,
    ListRemindersInput,
    MemoryIdInput,
    OptionalDateInput,
    OptionalWeekStartInput,
    ReminderIdInput,
    ReasoningInput,
    SaveMemoryInput,
    SearchItemsInput,
    SearchMemoriesInput,
    SectionIdInput,
    SendMessageInput,
    SetReminderInput,
    UpdateItemInput,
    UpdateSectionInput,
)
from services.tools.sections import (
    confirm_delete_section,
    create_section,
    delete_section,
    list_sections,
    update_section,
)
from services.tools.views import (
    generate_daily_image,
    generate_daily_list_view,
    generate_weekly_image,
    query_status_report,
)


ToolHandler = Callable[..., Awaitable[Any]]


class ToolDefinition:
    def __init__(
        self,
        handler: ToolHandler,
        input_model: Type[BaseModel],
        terminal: bool = False,
        hidden: bool = False,
        description: str | None = None,
    ) -> None:
        self.handler = handler
        self.input_model = input_model
        self.terminal = terminal
        self.hidden = hidden
        self.description = description

    def schema(self) -> dict:
        schema = self.input_model.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": self.handler.__name__,
                "description": self.description or self.handler.__doc__ or f"Call {self.handler.__name__}.",
                "parameters": schema,
            },
        }


# Tools exposed to the LLM.
TOOL_DEFINITIONS: Dict[str, ToolDefinition] = {
    "create_item": ToolDefinition(
        create_item,
        CreateItemInput,
        description="Create a new item in a section. If the item has a start_time, a default 15-minute reminder is created automatically.",
    ),
    "update_item": ToolDefinition(
        update_item,
        UpdateItemInput,
        description="Update one or more fields of an existing item. Use section_name to move the item to another section.",
    ),
    "delete_item": ToolDefinition(
        delete_item,
        ItemIdInput,
        description="Request deletion of an item. The user must confirm; this tool returns a confirmation prompt rather than deleting immediately.",
    ),
    "confirm_delete_item": ToolDefinition(
        confirm_delete_item,
        ItemIdInput,
        description="Confirm and permanently delete an item. Only use this after the user has explicitly confirmed deletion.",
    ),
    "mark_item_done": ToolDefinition(
        mark_item_done,
        ItemIdInput,
        description="Mark an item as done and move it to the Completed section (archived).",
    ),
    "search_items": ToolDefinition(
        search_items,
        SearchItemsInput,
        description="Search items across sections. Use this to find existing items before updating, deleting, or marking them done.",
    ),
    "create_section": ToolDefinition(
        create_section,
        CreateSectionInput,
        description="Create a new custom section. Ask the user before creating sections unless you are sure.",
    ),
    "list_sections": ToolDefinition(
        list_sections,
        EmptyInput,
        description="List all sections for the user.",
    ),
    "update_section": ToolDefinition(
        update_section,
        UpdateSectionInput,
        description="Update a custom section's name or view configuration. System sections cannot be renamed.",
    ),
    "delete_section": ToolDefinition(
        delete_section,
        SectionIdInput,
        description="Request deletion of a custom section. The user must confirm; this tool returns a confirmation prompt rather than deleting immediately.",
    ),
    "confirm_delete_section": ToolDefinition(
        confirm_delete_section,
        SectionIdInput,
        description="Confirm and permanently delete a custom section and all its items. Only use this after the user has explicitly confirmed deletion.",
    ),
    "set_reminder": ToolDefinition(
        set_reminder,
        SetReminderInput,
        description="Set or update a reminder for an item. If remind_at is omitted, it defaults to 15 minutes before the item's start_time.",
    ),
    "list_reminders": ToolDefinition(
        list_reminders,
        ListRemindersInput,
        description="List reminders for the user, optionally filtered by item.",
    ),
    "get_reminder": ToolDefinition(
        get_reminder,
        ReminderIdInput,
        description="Get details of a specific reminder.",
    ),
    "delete_reminder": ToolDefinition(
        delete_reminder,
        ReminderIdInput,
        description="Request deletion of a reminder. The user must confirm; this tool returns a confirmation prompt rather than deleting immediately.",
    ),
    "confirm_delete_reminder": ToolDefinition(
        confirm_delete_reminder,
        ReminderIdInput,
        description="Confirm and permanently delete a reminder. Only use this after the user has explicitly confirmed deletion.",
    ),
    "query_status_report": ToolDefinition(
        query_status_report,
        EmptyInput,
        description="Generate a full status report across all sections.",
    ),
    "generate_daily_list_view": ToolDefinition(
        generate_daily_list_view,
        OptionalDateInput,
        description="Generate a text list of items for a date (defaults to today).",
    ),
    "generate_daily_image": ToolDefinition(
        generate_daily_image,
        OptionalDateInput,
        description="Generate a daily plan image for a date (defaults to today) and return the file path.",
    ),
    "generate_weekly_image": ToolDefinition(
        generate_weekly_image,
        OptionalWeekStartInput,
        description="Generate a weekly schedule PNG image and return the file path.",
    ),
    "save_memory": ToolDefinition(
        save_memory,
        SaveMemoryInput,
        description="Save a new memory about the user (preference, fact, goal, routine, or conversation style).",
    ),
    "search_memories": ToolDefinition(
        search_memories,
        SearchMemoriesInput,
        description="Search stored memories about the user.",
    ),
    "delete_memory": ToolDefinition(
        delete_memory,
        MemoryIdInput,
        description="Request deletion of a stored memory. The user must confirm; this tool returns a confirmation prompt rather than deleting immediately.",
    ),
    "confirm_delete_memory": ToolDefinition(
        confirm_delete_memory,
        MemoryIdInput,
        description="Confirm and permanently delete a stored memory. Only use this after the user has explicitly confirmed deletion.",
    ),
    "reasoning": ToolDefinition(
        reasoning,
        ReasoningInput,
        hidden=True,
        description="Think through a plan with no side effects. Use when the user request requires multiple steps.",
    ),
    "send_message": ToolDefinition(
        send_message,
        SendMessageInput,
        terminal=True,
        description="Send the final response to the user. Use this as the last tool when you are ready to reply.",
    ),
    "ask_user": ToolDefinition(
        ask_user,
        AskUserInput,
        terminal=True,
        description="Ask the user a clarifying question. Use this as the last tool when you need more information.",
    ),
}

# Hidden tools are not sent to the LLM but can be invoked internally.
EXPOSED_TOOL_DEFINITIONS = {name: td for name, td in TOOL_DEFINITIONS.items() if not td.hidden}

TOOL_SCHEMAS: List[dict] = [td.schema() for td in EXPOSED_TOOL_DEFINITIONS.values()]

TOOL_FUNCTIONS: Dict[str, ToolHandler] = {name: td.handler for name, td in TOOL_DEFINITIONS.items()}

TERMINAL_TOOLS = {name for name, td in TOOL_DEFINITIONS.items() if td.terminal}


async def execute_tool_call(
    session: AsyncSession,
    user,
    tool_call: Any,
) -> dict[str, Any]:
    name = tool_call.function.name
    definition = TOOL_DEFINITIONS.get(name)
    if definition is None:
        return {"success": False, "error": f"Unknown tool: {name}"}

    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError as exc:
        return {"success": False, "error": f"Invalid JSON arguments: {exc}"}

    input_model = definition.input_model
    if input_model is not None:
        try:
            validated = input_model.model_validate(args)
        except ValidationError as exc:
            return {"success": False, "error": f"Invalid arguments for {name}: {exc}"}
    else:
        validated = None

    try:
        result = await definition.handler(session, user, validated)
    except Exception as exc:
        return {"success": False, "error": f"Tool {name} failed: {exc}"}

    return cast(dict[str, Any], result if isinstance(result, dict) else result.to_dict())
