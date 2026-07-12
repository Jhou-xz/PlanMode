import json
import logging
from typing import Optional
import openai
from config.settings import settings

logger = logging.getLogger(__name__)

_client = openai.AsyncOpenAI(
    api_key=settings.deepseek_api_key,
    base_url="https://api.deepseek.com",
)


async def stream_chat_completion(
    messages: list,
    json_mode: bool = False,
    temperature: float = 0.2,
    tools: Optional[list] = None,
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
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

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
    tools: Optional[list] = None,
) -> openai.types.chat.ChatCompletion:
    """Non-streaming wrapper. Returns a ChatCompletion object."""
    kwargs = {
        "model": "deepseek-v4-pro",
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    return await _client.chat.completions.create(**kwargs)


async def chat_completion_text(
    messages: list,
    json_mode: bool = False,
    temperature: float = 0.2,
) -> str:
    """Convenience wrapper returning only the text content."""
    response = await chat_completion(messages, json_mode=json_mode, temperature=temperature)
    return response.choices[0].message.content or ""


async def parse_json_completion(
    messages: list,
    temperature: float = 0.2,
    max_retries: int = 2,
) -> dict:
    """Stream a JSON completion and parse it, retrying on malformed JSON."""
    last_error: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        text = await stream_chat_completion(messages, json_mode=True, temperature=temperature)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning(
                "JSON decode failed on attempt %d/%d: %s",
                attempt + 1,
                max_retries + 1,
                exc,
            )
    raise last_error or json.JSONDecodeError("malformed JSON", doc=text, pos=0)
