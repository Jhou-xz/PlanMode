import json
from datetime import datetime, timezone as dt_timezone
from typing import List, Optional
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field, ValidationError
from llm.deepseek_client import parse_json_completion
from llm import prompts
from services.memory import format_memories
from services.date_parser import parse_time_expression
from database.models import Memory, Message


class MemoryEntry(BaseModel):
    category: str = "preference"
    content: str
    importance: int = Field(default=1, ge=1, le=5)
    source_message_ids: Optional[List[int]] = None


class ReminderEntity(BaseModel):
    title: str
    description: Optional[str] = None
    remind_at: str
    original_time_expression: Optional[str] = None


class IdeaEntity(BaseModel):
    content: str
    category: Optional[str] = None


class QueryEntity(BaseModel):
    question_type: Optional[str] = None
    time_range: Optional[str] = None


class ScheduleRequestEntity(BaseModel):
    week_start: Optional[str] = None


class IntentResponse(BaseModel):
    intent: str
    language: str
    response_text: str
    entities: dict = Field(default_factory=dict)
    actions: List[str] = Field(default_factory=list)
    new_memories: List[MemoryEntry] = Field(default_factory=list)


_INTENT_ENTITY_KEYS = {
    "reminder": "reminder",
    "idea": "idea",
    "query": "query",
    "schedule_request": "schedule_request",
    "summary_request": "",
    "chat": "",
}


def _format_history(messages: List[Message]) -> str:
    if not messages:
        return "No previous messages."
    lines = ["Recent conversation history:"]
    for m in messages:
        ts = m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else ""
        role = m.role.capitalize()
        text = (m.original_text or "")[:300].replace("\n", " ")
        lines.append(f"[{ts}] {role}: {text}")
    return "\n".join(lines)


def _build_datetime_context(timezone: str) -> str:
    tz = ZoneInfo(timezone)
    utc_now = datetime.now(dt_timezone.utc)
    local_now = datetime.now(tz)
    return (
        f"UTC now: {utc_now.isoformat()}\n"
        f"User timezone ({timezone}) now: {local_now.isoformat()}\n"
        f"User timezone: {timezone}"
    )


def build_system_prompt(
    timezone: str,
    memories: List[Memory],
    history_messages: List[Message],
) -> str:
    memory_text = format_memories(memories)
    history_text = _format_history(history_messages)
    utc_now = datetime.now(dt_timezone.utc)
    local_now = datetime.now(ZoneInfo(timezone))

    system_prompt = prompts.BASE_SYSTEM_PROMPT.format(
        utc_now=utc_now.isoformat(),
        local_now=local_now.isoformat(),
        timezone=timezone,
    )

    parts = [
        system_prompt,
        memory_text,
        history_text,
        prompts.INTENT_SCHEMA_EXPLANATION,
    ]
    return "\n\n".join(parts)


def _build_user_content(user_text: str, images_b64: Optional[List[str]] = None) -> List[dict]:
    content: List[dict] = [{"type": "text", "text": user_text}]
    if images_b64:
        for b64 in images_b64:
            content.append({"type": "image_url", "image_url": {"url": b64}})
    return content


async def build_messages(
    user_text: str,
    timezone: str,
    memories: List[Memory],
    history_messages: List[Message],
    images_b64: Optional[List[str]] = None,
) -> List[dict]:
    system_content = build_system_prompt(timezone, memories, history_messages)
    user_content = _build_user_content(user_text, images_b64)

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


async def parse_intent(
    user_text: str,
    timezone: str,
    memories: List[Memory],
    history_messages: List[Message],
    images_b64: Optional[List[str]] = None,
) -> dict:
    messages = await build_messages(
        user_text, timezone, memories, history_messages, images_b64
    )
    parsed = await parse_json_completion(messages, temperature=0.2)
    parsed = _rewrite_obviously_wrong_reminder_dates(parsed, timezone)

    try:
        validated = IntentResponse(**parsed)
        return validated.model_dump()
    except ValidationError as exc:
        # Return the raw parsed dict but inject a warning; downstream code
        # should still be able to read basic fields.
        parsed["_validation_error"] = str(exc)
        return parsed


async def parse_intent_without_history(
    user_text: str,
    timezone: str,
    memories: List[Memory],
    images_b64: Optional[List[str]] = None,
) -> dict:
    """Backwards-compatible wrapper for callers that do not pass history."""
    return await parse_intent(user_text, timezone, memories, [], images_b64)


def _rewrite_obviously_wrong_reminder_dates(parsed: dict, timezone: str) -> dict:
    """
    Post-process the LLM response to fix obviously wrong reminder dates.

    The user's natural-language time expression is the source of truth. If the
    LLM-generated ISO date disagrees on the year or month with the expression,
    overwrite the ISO date with the expression-derived datetime.
    """
    reminder = parsed.get("entities", {}).get("reminder")
    if not reminder or not reminder.get("original_time_expression") or not reminder.get("remind_at"):
        return parsed

    expr = reminder["original_time_expression"]
    iso = reminder["remind_at"]

    try:
        tz = ZoneInfo(timezone)
        now_local = datetime.now(tz)
        expr_dt = parse_time_expression(expr, timezone, now_local)
        if expr_dt is None:
            return parsed

        llm_dt = datetime.fromisoformat(iso)
        if llm_dt.tzinfo is None:
            llm_dt = llm_dt.replace(tzinfo=tz)
        llm_dt = llm_dt.astimezone(tz)

        # If the LLM got the year or month wrong, rewrite using the expression.
        if expr_dt.year != llm_dt.year or expr_dt.month != llm_dt.month:
            reminder["remind_at"] = expr_dt.isoformat()
    except Exception:
        # Don't break parsing if post-processing fails; the date parser will catch it.
        pass

    return parsed
