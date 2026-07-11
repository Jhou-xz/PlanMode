import json
from typing import Any, Callable, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from services.tools.items import create_item, update_item, delete_item, mark_item_done, search_items
from services.tools.sections import create_section
from services.tools.reminders import set_reminder, delete_reminder
from services.tools.views import query_status_report, generate_daily_list_view, generate_weekly_image
from services.tools.messaging import send_message, ask_user


ToolFn = Callable[[AsyncSession, Any, Dict], Any]


TERMINAL_TOOLS = {"send_message", "ask_user"}


TOOL_SCHEMAS: List[dict] = [
    {
        "type": "function",
        "function": {
            "name": "create_item",
            "description": "Create a new item in a section. If the item has a start_time, a default 15-minute reminder is created automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section_name": {
                        "type": "string",
                        "description": "Name of the section (e.g. 'Schedule', 'Tasks', 'Idea Hub'). Must already exist; use create_section if you need a new one."
                    },
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "start_time": {
                        "type": "string",
                        "description": "ISO 8601 datetime or natural language (e.g. 'next Tuesday at 3pm')."
                    },
                    "end_time": {"type": "string", "description": "ISO 8601 datetime or natural language."},
                    "due_date": {"type": "string", "description": "ISO 8601 datetime or natural language."},
                    "status": {
                        "type": "string",
                        "enum": ["todo", "done", "archived", "in_progress", "cancelled"],
                    },
                    "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object"},
                    "reminder_message": {"type": "string", "description": "Custom reminder text."},
                },
                "required": ["section_name", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_item",
            "description": "Update one or more fields of an existing item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "section_name": {"type": "string"},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                    "due_date": {"type": "string"},
                    "status": {"type": "string", "enum": ["todo", "done", "archived", "in_progress", "cancelled"]},
                    "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object"},
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_item",
            "description": "Permanently delete an item.",
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "integer"}},
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_item_done",
            "description": "Mark an item as done and move it to the Completed section (archived).",
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "integer"}},
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_items",
            "description": "Search items across sections.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "section_name": {"type": "string"},
                    "status": {"type": "string"},
                    "time_range": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string"},
                            "end": {"type": "string"},
                        },
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_section",
            "description": "Create a new custom section. Ask the user before creating sections unless you are sure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "schema": {"type": "object"},
                    "view_config": {"type": "object"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set or update a reminder for an item. If remind_at is omitted, it defaults to 15 minutes before the item's start_time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer"},
                    "remind_at": {"type": "string", "description": "ISO 8601 datetime or natural language."},
                    "message": {"type": "string"},
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_reminder",
            "description": "Delete a reminder by id.",
            "parameters": {
                "type": "object",
                "properties": {"reminder_id": {"type": "integer"}},
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_status_report",
            "description": "Generate a full status report across all sections.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_daily_list_view",
            "description": "Generate a text list of items for a date (defaults to today).",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "ISO 8601 date or natural language. Defaults to today."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_weekly_image",
            "description": "Generate a weekly schedule PNG image and return the file path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "week_start": {"type": "string", "description": "ISO 8601 date for Monday. Defaults to current week."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send the final response to the user. Use this as the last tool when you are ready to reply.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Ask the user a clarifying question. Use this as the last tool when you need more information.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
            },
        },
    },
]


TOOL_FUNCTIONS: Dict[str, ToolFn] = {
    "create_item": create_item,
    "update_item": update_item,
    "delete_item": delete_item,
    "mark_item_done": mark_item_done,
    "search_items": search_items,
    "create_section": create_section,
    "set_reminder": set_reminder,
    "delete_reminder": delete_reminder,
    "query_status_report": query_status_report,
    "generate_daily_list_view": generate_daily_list_view,
    "generate_weekly_image": generate_weekly_image,
    "send_message": send_message,
    "ask_user": ask_user,
}


async def execute_tool_call(
    session: AsyncSession,
    user,
    tool_call: Any,
) -> dict:
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}
    return await fn(session, user, **args)
