import json
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo
from llm.deepseek_client import parse_json_completion
from llm import prompts
from services.memory import format_memories, get_memories_for_prompt
from database.models import Memory


async def build_messages(
    user_text: str,
    timezone: str,
    memories: List[Memory],
    images_b64: Optional[List[str]] = None,
) -> List[dict]:
    memory_text = format_memories(memories)
    system_content = prompts.BASE_SYSTEM_PROMPT + "\n\n" + memory_text + "\n\n" + prompts.INTENT_SCHEMA_EXPLANATION

    user_content: List[dict] = [{"type": "text", "text": user_text}]
    if images_b64:
        for b64 in images_b64:
            user_content.append({"type": "image_url", "image_url": {"url": b64}})

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


async def parse_intent(
    user_text: str,
    timezone: str,
    memories: List[Memory],
    images_b64: Optional[List[str]] = None,
) -> dict:
    messages = await build_messages(user_text, timezone, memories, images_b64)
    return await parse_json_completion(messages, temperature=0.2)
