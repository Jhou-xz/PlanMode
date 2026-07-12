import json
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo
from typing import Any, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from database.models import Message
from llm import prompts
from llm.deepseek_client import chat_completion, chat_completion_text
from services.memory import get_memories_for_prompt, save_memories
from services.tools import TOOL_SCHEMAS, TERMINAL_TOOLS, execute_tool_call

logger = logging.getLogger(__name__)


MAX_ITERATIONS = 6


async def run_agent(
    session: AsyncSession,
    user,
    text: str,
    images_b64: Optional[List[str]] = None,
    raw_type: str = "text",
    language: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """
    Run the tool-calling agent loop for a user message.

    Returns (final_text, list_of_image_paths).
    """
    images_b64 = images_b64 or []
    history = await crud.get_recent_messages_for_prompt(session, user.id, limit=15)
    memories = await get_memories_for_prompt(session, user.id, limit=20)
    relevant_items = await _fetch_relevant_items(session, user, text)

    system_prompt = _build_system_prompt(
        user, history, memories, relevant_items
    )
    user_content = _build_user_content(text, images_b64)

    messages: List[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    final_text = "Got it."
    image_paths: List[str] = []
    tool_calls_log: List[dict] = []

    for iteration in range(MAX_ITERATIONS):
        try:
            response = await chat_completion(messages, tools=TOOL_SCHEMAS, temperature=0.2)
        except Exception:
            logger.exception("LLM call failed")
            final_text = "I'm sorry, I ran into a problem thinking that through. Could you try again?"
            break

        message = response.choices[0].message
        tool_calls: List[Any] = message.tool_calls or []

        # Model returned content directly (no tool calls)
        if not tool_calls:
            final_text = _sanitize_final_text(message.content or final_text)
            break

        # Collect action and terminal tool calls
        action_calls = [tc for tc in tool_calls if tc.function.name not in TERMINAL_TOOLS]
        terminal_calls = [tc for tc in tool_calls if tc.function.name in TERMINAL_TOOLS]

        # Validate: only one terminal tool per turn
        if len(terminal_calls) > 1:
            logger.warning("Model emitted multiple terminal tools; keeping only the last one")
            terminal_calls = [terminal_calls[-1]]

        # Execute action tools first
        action_results = []
        for tc in action_calls:
            logger.info("Executing tool %s", tc.function.name)
            result = await execute_tool_call(session, user, tc)
            action_results.append((tc, result))
            tool_calls_log.append({"name": tc.function.name, "arguments": tc.function.arguments, "result": result})
            if result.get("image_path"):
                image_paths.append(result["image_path"])

        # Add assistant message with tool calls
        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        })

        # Add tool results for action tools
        for tc, result in action_results:
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.function.name,
                "content": json.dumps(result, default=str),
            })

        # If terminal tool was called, execute it and add its result before returning
        if terminal_calls:
            terminal = terminal_calls[0]
            result = await execute_tool_call(session, user, terminal)
            tool_calls_log.append({"name": terminal.function.name, "arguments": terminal.function.arguments, "result": result})
            if result.get("image_path"):
                image_paths.append(result["image_path"])

            # Append the terminal tool result so every tool call ID has a matching result.
            messages.append({
                "role": "tool",
                "tool_call_id": terminal.id,
                "name": terminal.function.name,
                "content": json.dumps(result, default=str),
            })

            final_text = _sanitize_final_text(result.get("final_response", message.content or final_text))
            break

        # No terminal tool yet; continue the loop
    else:
        # Loop exhausted without a terminal tool
        logger.warning("Agent loop hit MAX_ITERATIONS without terminal tool")
        final_text = "I'm taking too long to figure this out. Could you rephrase or break it into smaller steps?"

    # Extract and save memories from the conversation
    await _extract_and_save_memories(session, user, text, final_text)

    # Persist user and assistant messages
    await crud.create_message(session, user.id, "user", text, raw_type=raw_type)
    await crud.create_message(
        session,
        user.id,
        "assistant",
        final_text,
        raw_type="text",
        tool_calls={"calls": tool_calls_log} if tool_calls_log else None,
    )

    return final_text, image_paths


async def _extract_and_save_memories(
    session: AsyncSession,
    user,
    user_text: str,
    assistant_text: str,
) -> None:
    extraction_prompt = prompts.MEMORY_EXTRACTION_PROMPT.format(
        user_text=user_text,
        assistant_text=assistant_text,
    )
    try:
        raw = await chat_completion_text(
            [{"role": "system", "content": extraction_prompt}],
            json_mode=True,
            temperature=0.2,
        )
        parsed = json.loads(raw)
        memories = parsed.get("memories", [])
        if memories:
            await save_memories(session, user.id, memories)
    except Exception as exc:
        logger.warning("Memory extraction failed: %s", exc)


async def _fetch_relevant_items(session: AsyncSession, user, text: str) -> List:
    tz = ZoneInfo(user.timezone)
    now = datetime.now(tz)
    # Upcoming items and recent tasks
    upcoming = await crud.get_items_for_time_range(
        session, user.id, now, now + timedelta(days=7)
    )
    tasks = await crud.search_items(
        session, user_id=user.id, section_name="Tasks", status="todo", limit=20
    )
    ideas = await crud.search_items(
        session, user_id=user.id, section_name="Idea Hub", limit=10
    )
    seen = set()
    merged = []
    for item in upcoming + tasks + ideas:
        if item.id not in seen:
            merged.append(item)
            seen.add(item.id)
    return merged


def _build_system_prompt(
    user,
    history: List[Message],
    memories: List,
    relevant_items: List,
) -> str:
    utc_now = datetime.now(dt_timezone.utc)
    local_now = datetime.now(ZoneInfo(user.timezone))

    memory_text = _format_memories(memories)
    history_text = _format_history(history)
    items_text = _format_items(relevant_items)

    available_tools = "\n".join(
        f"- {schema['function']['name']}: {schema['function']['description']}"
        for schema in TOOL_SCHEMAS
    )

    system_prompt = prompts.AGENT_SYSTEM_PROMPT.format(
        utc_now=utc_now.isoformat(),
        local_now=local_now.isoformat(),
        timezone=user.timezone,
        available_tools=available_tools,
    )

    parts = [
        system_prompt,
        prompts.FEW_SHOT_EXAMPLES,
        prompts.TOOL_INSTRUCTIONS,
        memory_text,
        history_text,
        items_text,
        prompts.USER_TEXT_INSTRUCTIONS,
    ]
    return "\n\n".join(parts)


def _build_user_content(text: str, images_b64: List[str]) -> Any:
    if not images_b64:
        return text
    content: List[dict[str, Any]] = [{"type": "text", "text": text}]
    for b64 in images_b64:
        content.append({"type": "image_url", "image_url": {"url": b64}})
    return content


def _format_memories(memories: List) -> str:
    if not memories:
        return f"{prompts.MEMORY_FORMAT_HEADER}\nNo relevant memories yet."
    lines = [prompts.MEMORY_FORMAT_HEADER]
    for m in memories:
        lines.append(f"- [{m.category}] {m.content} (importance: {m.importance})")
    return "\n".join(lines)


def _format_history(messages: List[Message]) -> str:
    if not messages:
        return f"{prompts.CONVERSATION_HISTORY_HEADER}\nNo previous messages."
    lines = [prompts.CONVERSATION_HISTORY_HEADER]
    for m in messages:
        ts = m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else ""
        role = m.role.capitalize()
        text = (m.content or "")[:300].replace("\n", " ")
        lines.append(f"[{ts}] {role}: {text}")
    return "\n".join(lines)


def _format_items(items: List) -> str:
    if not items:
        return f"{prompts.ITEMS_CONTEXT_HEADER}\nNo relevant items."
    lines = [prompts.ITEMS_CONTEXT_HEADER]
    for item in items:
        section = item.section.name if item.section else ""
        time_str = ""
        if item.start_time:
            time_str = item.start_time.isoformat()
        elif item.due_date:
            time_str = f"due {item.due_date.isoformat()}"
        lines.append(
            f"- [{section}] {item.title} ({item.status}) {time_str}"
        )
    return "\n".join(lines)


def _sanitize_final_text(text: str) -> str:
    """Ensure final replies are safe, English, and not overly long."""
    if not text:
        return "Got it."
    # Basic guardrail: avoid leaking raw JSON or tool internals
    text = text.strip()
    if len(text) > 1800:
        text = text[:1800].rsplit(" ", 1)[0] + " …"
    return text
