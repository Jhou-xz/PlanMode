import json
from typing import AsyncIterator, Optional
import openai
from config.settings import settings

_client = openai.AsyncOpenAI(
    api_key=settings.deepseek_api_key,
    base_url="https://api.deepseek.com",
)


async def stream_chat_completion(
    messages: list,
    json_mode: bool = False,
    temperature: float = 0.2,
) -> str:
    """Stream a chat completion and return the full collected text."""
    kwargs = {
        "model": "deepseek-v4-pro",
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    chunks: list[str] = []
    async for chunk in await _client.chat.completions.create(**kwargs):
        delta = chunk.choices[0].delta.content
        if delta:
            chunks.append(delta)

    return "".join(chunks)


async def chat_completion(
    messages: list,
    json_mode: bool = False,
    temperature: float = 0.2,
) -> str:
    """Non-streaming wrapper. Prefer stream_chat_completion for consistency."""
    kwargs = {
        "model": "deepseek-v4-pro",
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = await _client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


async def parse_json_completion(
    messages: list,
    temperature: float = 0.2,
) -> dict:
    text = await stream_chat_completion(messages, json_mode=True, temperature=temperature)
    return json.loads(text)
