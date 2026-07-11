# Plan Mode — OpenCode Detailed Execution Plan

> **For OpenCode / Kimi execution.** This document expands every task into copy-pasteable code, exact commands, and explicit success criteria. Implement one task at a time, commit, and verify before moving on.

---

## Global Rules for OpenCode

1. **One task = one commit.** Do not batch tasks.
2. **Write the test/verification first, run it, then implement.**
3. **Never commit secrets.** `.env` and `.env.example` are the only places for API keys; `.env` is in `.gitignore`.
4. **All DB code is async.** Use `asyncpg`, SQLAlchemy 2.0 async, and `AsyncSession` everywhere.
5. **All datetimes stored as UTC.** Convert to the user's timezone only for display and cron triggers.
6. **DeepSeek client is streaming-first.** Use `stream=True`, collect the final string, and return it.
7. **Ask the user for timezone on first DM.** If `User.timezone == "UTC"`, ask before doing anything else.
8. **Memory is injected into every prompt.** Retrieve top memories by importance/recency before calling DeepSeek.

---

## Task 1: Bootstrap Project and Dependencies

### Objective
Create the project directory, install dependencies, and verify the environment.

### Files to create
- `pyproject.toml`
- `.env.example`
- `.gitignore`
- `config/settings.py`

### Step 1: `pyproject.toml`

```toml
[project]
name = "plan-mode"
version = "0.1.0"
description = "Personal AI assistant delivered as a Discord bot"
requires-python = ">=3.12"
dependencies = [
    "discord.py>=2.4.0",
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.29.0",
    "apscheduler>=3.10.0",
    "openai>=1.35.0",
    "faster-whisper>=1.0.0",
    "pillow>=10.0.0",
    "pydantic-settings>=2.2.0",
    "python-dotenv>=1.0.0",
    "tzdata>=2024.1",
    "pydub>=0.25.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "ruff>=0.4.0", "mypy>=1.10.0"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
```

### Step 2: `.env.example`

```bash
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DATABASE_URL=postgresql+asyncpg://planmode:password@localhost:5432/planmode
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
SUMMARY_DEFAULT_TIME=22:00
```

### Step 3: `.gitignore`

```gitignore
.env
.venv/
__pycache__/
*.pyc
*.pyo
*.egg-info/
.pytest_cache/
.mypy_cache/
*.log
*.ogg
*.mp3
*.wav
*.png
tmp/
```

### Step 4: `config/settings.py`

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    discord_bot_token: str
    deepseek_api_key: str
    database_url: str
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    summary_default_time: str = "22:00"
    memory_top_n: int = 10
    memory_compression_threshold: int = 500

    class Config:
        env_file = ".env"

settings = Settings()
```

### Step 5: Verify

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -c "import discord, fastapi, sqlalchemy, apscheduler, openai, faster_whisper, PIL, pydub; print('all imports ok')"
```

Expected: prints `all imports ok`.

### Definition of Done
- [ ] `pyproject.toml`, `.env.example`, `.gitignore`, `config/settings.py` exist.
- [ ] `pip install -e ".[dev]"` succeeds.
- [ ] Import test passes.
- [ ] First commit pushed.

---

## Task 2: Database Schema and SQLAlchemy Models

### Objective
Create async PostgreSQL models for `User`, `Message`, `Reminder`, `Idea`, and `Memory`.

### Files to create
- `database/__init__.py`
- `database/core.py`
- `database/models.py`
- `scripts/init_db.py`

### Step 1: `database/models.py`

```python
from datetime import datetime, time
from typing import List, Optional
from sqlalchemy import ForeignKey, JSON, String, Boolean, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    discord_username: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    summary_time: Mapped[time] = mapped_column(default="22:00")
    preferred_language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    raw_type: Mapped[str] = mapped_column(String(32))  # text | voice | image | mixed
    original_text: Mapped[Optional[str]] = mapped_column(nullable=True)
    attachment_urls: Mapped[List[str]] = mapped_column(JSON, default=list)
    parsed_intent: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    parsed_entities: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    compressed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_message_id: Mapped[Optional[int]] = mapped_column(ForeignKey("messages.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[Optional[str]] = mapped_column(nullable=True)
    remind_at: Mapped[datetime] = mapped_column(index=True)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_message_id: Mapped[Optional[int]] = mapped_column(ForeignKey("messages.id"), nullable=True)
    content: Mapped[str]
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(32), default="preference")
    content: Mapped[str]
    importance: Mapped[int] = mapped_column(Integer, default=1)
    source_message_ids: Mapped[List[int]] = mapped_column(JSON, default=list)
    compressed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now)
```

### Step 2: `database/core.py`

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from config.settings import settings
from database.models import Base

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### Step 3: `scripts/init_db.py`

```python
import asyncio
from database.core import init_db


async def main():
    await init_db()
    print("database initialized")


if __name__ == "__main__":
    asyncio.run(main())
```

### Step 4: Verify

```bash
# Ensure PostgreSQL is running and the database exists
createdb -U planmode planmode  # if needed
python scripts/init_db.py
```

Expected: `database initialized` and all five tables appear in PostgreSQL.

### Definition of Done
- [ ] All five models exist and are importable.
- [ ] `scripts/init_db.py` creates all tables without errors.
- [ ] `User.timezone` defaults to `UTC` and `summary_time` defaults to `22:00`.
- [ ] Commit.

---

## Task 3: DeepSeek Async Client with Streaming

### Objective
Build a reusable streaming DeepSeek client with JSON and text modes.

### Files to create
- `llm/__init__.py`
- `llm/deepseek_client.py`
- `llm/prompts.py` (initial skeleton)

### Step 1: `llm/deepseek_client.py`

```python
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
```

### Step 2: `llm/prompts.py` (skeleton)

```python
BASE_SYSTEM_PROMPT = """You are Plan Mode, a helpful personal assistant running inside a Discord bot.
The user sends you text, voice, or image messages. Your job is to understand the user's intent, extract structured information, and reply naturally.

Always respond in the SAME LANGUAGE the user used.
All datetimes must be ISO 8601 with timezone offset, in the user's timezone.

When you learn a new preference, fact, goal, or routine about the user, include it in `new_memories`.
"""
```

### Step 3: Verify

Create `scripts/test_deepseek.py`:

```python
import asyncio
from llm.deepseek_client import stream_chat_completion

async def main():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello and nothing else."},
    ]
    reply = await stream_chat_completion(messages, json_mode=False, temperature=0.2)
    print(f"reply: {reply}")

if __name__ == "__main__":
    asyncio.run(main())
```

Run:

```bash
python scripts/test_deepseek.py
```

Expected: A non-empty greeting is printed.

### Definition of Done
- [ ] `stream_chat_completion` returns a full string from a streamed response.
- [ ] `parse_json_completion` returns a parsed dict.
- [ ] `scripts/test_deepseek.py` prints a valid reply.
- [ ] Commit.

---

## Task 4: Discord Bot Client and First-Message Timezone Handler

### Objective
Connect to Discord, receive DMs, and ask for timezone on first interaction.

### Files to create
- `bot/__init__.py`
- `bot/client.py`
- `bot/handlers.py`
- `main.py`

### Step 1: `bot/client.py`

```python
import discord
from config.settings import settings

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

bot = discord.Client(intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id {bot.user.id})")
```

### Step 2: `bot/handlers.py`

```python
import discord
from database.crud import get_or_create_user
from database.core import async_session


async def handle_message(message: discord.Message):
    if message.author.bot:
        return
    if not isinstance(message.channel, discord.DMChannel):
        return

    async with async_session() as session:
        user = await get_or_create_user(
            session,
            discord_user_id=str(message.author.id),
            discord_username=str(message.author),
        )

        # Ask for timezone on first interaction if still default
        if user.timezone == "UTC" and message.content.strip().lower() not in ["utc", "skip"]:
            await message.channel.send(
                "Hi! I'm Plan Mode. To schedule reminders correctly, what timezone are you in?\n"
                "Reply with an IANA timezone like `Asia/Shanghai`, `Europe/Berlin`, or `America/New_York`."
            )
            return

        # Echo for now; full pipeline in later tasks
        await message.channel.send(f"Received: {message.content[:500]}")
```

### Step 3: `database/crud.py` (initial helpers)

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import User


async def get_or_create_user(
    session: AsyncSession,
    discord_user_id: str,
    discord_username: str | None = None,
) -> User:
    result = await session.execute(
        select(User).where(User.discord_user_id == discord_user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            discord_user_id=discord_user_id,
            discord_username=discord_username,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def set_user_timezone(session: AsyncSession, user: User, timezone: str) -> User:
    user.timezone = timezone
    await session.commit()
    await session.refresh(user)
    return user
```

### Step 4: `main.py`

```python
import asyncio
from bot.client import bot
from bot.handlers import handle_message
from database.core import init_db


@bot.event
async def on_message(message):
    await handle_message(message)


async def main():
    await init_db()
    await bot.start(bot_config.discord_bot_token)


if __name__ == "__main__":
    asyncio.run(main())
```

### Step 5: Verify

Run `python main.py`, send a DM to the bot from a new account.

Expected: First DM gets the timezone question. Subsequent DMs are echoed.

### Definition of Done
- [ ] Bot connects to Discord and logs in.
- [ ] DMs from non-bot users are processed.
- [ ] First DM from a new user triggers timezone request.
- [ ] Commit.

---

## Task 5: Voice Message Transcription with faster-whisper

### Objective
Download Discord voice messages, transcribe them locally, and return text + language.

### Files to create
- `services/transcription.py`
- `utils/audio.py` (optional conversion helper)

### Step 1: `services/transcription.py`

```python
import tempfile
import os
from typing import Tuple
from faster_whisper import WhisperModel
from config.settings import settings

_model: WhisperModel | None = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type="int8",
        )
    return _model


async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg") -> dict:
    """Transcribe audio bytes. Returns {"text": str, "language": str}."""
    # Write to a temp file
    suffix = os.path.splitext(filename)[1] or ".ogg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model = get_model()
        segments, info = model.transcribe(tmp_path, beam_size=5)
        text = " ".join([seg.text.strip() for seg in segments]).strip()
        return {"text": text, "language": info.language}
    finally:
        os.unlink(tmp_path)
```

### Step 2: Update `bot/handlers.py` to handle voice

```python
async def extract_text_from_message(message: discord.Message) -> dict:
    """Returns {"text": str, "type": str, "language": str | None}"""
    text = message.content.strip()
    detected_type = "text"
    language = None

    if message.flags.voice and message.attachments:
        audio = message.attachments[0]
        audio_bytes = await audio.read()
        result = await transcribe_audio(audio_bytes, filename=audio.filename)
        text = result["text"]
        language = result["language"]
        detected_type = "voice"

    return {"text": text, "type": detected_type, "language": language}
```

### Step 3: Verify

Send a voice message to the bot. Expected: bot echoes the transcribed text.

### Definition of Done
- [ ] Voice messages are transcribed to text.
- [ ] Language code is returned.
- [ ] Audio temp files are cleaned up.
- [ ] Commit.

---

## Task 6: Image Message Handling with Fallback

### Objective
Download image attachments, pass them to DeepSeek, and have an OCR fallback.

### Files to create
- `services/image_handler.py`

### Step 1: `services/image_handler.py`

```python
import base64
from typing import List
import aiohttp
from io import BytesIO


async def download_attachment(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.read()


def bytes_to_b64_image(data: bytes, mime: str = "image/png") -> str:
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"


async def build_image_content(message: discord.Message) -> List[dict]:
    """Build OpenAI-style image_url content blocks from image attachments."""
    images = []
    for attachment in message.attachments:
        if not attachment.content_type or not attachment.content_type.startswith("image/"):
            continue
        data = await download_attachment(attachment.url)
        b64 = bytes_to_b64_image(data, mime=attachment.content_type)
        images.append({"type": "image_url", "image_url": {"url": b64}})
    return images
```

### Step 2: OCR fallback

```python
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False


def ocr_image(data: bytes) -> str:
    if not OCR_AVAILABLE:
        return ""
    img = Image.open(BytesIO(data))
    return pytesseract.image_to_string(img).strip()
```

### Step 3: Verify

Send an image with text. The bot should describe it or extract text.

### Definition of Done
- [ ] Images are downloaded and base64-encoded.
- [ ] DeepSeek multimodal content array is built correctly.
- [ ] If DeepSeek rejects images, OCR fallback is used.
- [ ] Commit.

---

## Task 7: Memory Retrieval and Storage

### Objective
Implement CRUD and prompt integration for the `Memory` table.

### Files to create
- `services/memory.py`

### Step 1: `services/memory.py`

```python
from datetime import datetime, timedelta
from typing import List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Memory


async def get_memories_for_prompt(session: AsyncSession, user_id: int, limit: int = 10) -> List[Memory]:
    """Retrieve top memories by importance and recency."""
    result = await session.execute(
        select(Memory)
        .where(Memory.user_id == user_id)
        .order_by(desc(Memory.importance), desc(Memory.updated_at))
        .limit(limit)
    )
    return result.scalars().all()


async def save_memories(session: AsyncSession, user_id: int, memories: List[dict]) -> None:
    for mem in memories:
        if not mem.get("content"):
            continue
        m = Memory(
            user_id=user_id,
            category=mem.get("category", "preference"),
            content=mem["content"],
            importance=mem.get("importance", 1),
            source_message_ids=mem.get("source_message_ids", []),
        )
        session.add(m)
    await session.commit()


def format_memories(memories: List[Memory]) -> str:
    if not memories:
        return "No relevant memories yet."
    lines = ["Relevant memories about the user:"]
    for m in memories:
        lines.append(f"- [{m.category}] {m.content} (importance: {m.importance})")
    return "\n".join(lines)
```

### Step 2: Add memory helper tests

```python
# tests/test_memory.py
import pytest
from services.memory import get_memories_for_prompt, save_memories, format_memories

async def test_save_and_retrieve_memory(session):
    await save_memories(session, user_id=1, memories=[{"category": "preference", "content": "Likes concise replies", "importance": 4}])
    mems = await get_memories_for_prompt(session, user_id=1)
    assert len(mems) == 1
    assert mems[0].content == "Likes concise replies"
```

### Definition of Done
- [ ] Memory CRUD works.
- [ ] Memories are formatted for prompts.
- [ ] Tests pass.
- [ ] Commit.

---

## Task 8: Intent Extraction and Structured Parsing

### Objective
Use DeepSeek to parse user intent into structured JSON, including `new_memories`.

### Files to create
- `services/intent_parser.py`
- `llm/prompts.py` (complete)

### Step 1: Complete `llm/prompts.py`

```python
BASE_SYSTEM_PROMPT = """You are Plan Mode, a helpful personal assistant running inside a Discord bot.
The user sends you text, voice, or image messages. Analyze the input and return a JSON object.

Always respond in the SAME LANGUAGE the user used.
All datetimes must be ISO 8601 with timezone offset, in the user's timezone.

When you learn something new about the user (preferences, facts, goals, routines), include it in `new_memories`.

Return JSON with this exact schema:
{
  "intent": "reminder" | "idea" | "query" | "summary_request" | "schedule_request" | "chat",
  "language": "en",
  "response_text": "natural reply in the same language",
  "entities": { ... },
  "actions": ["schedule_reminder"],
  "new_memories": [
    {"category": "preference", "content": "...", "importance": 1}
  ]
}
"""

INTENT_SCHEMA_EXPLANATION = """
Intent-specific entity shapes:
- reminder: entities.reminder = {title, description, remind_at, original_time_expression}
- idea: entities.idea = {content, category}
- query: entities.query = {question_type, time_range}
- schedule_request: entities.schedule_request = {week_start}
- chat: entities = {}
- summary_request: entities = {}
"""
```

### Step 2: `services/intent_parser.py`

```python
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
```

### Step 3: Verify with sample inputs

```python
# tests/test_intent_parser.py
import pytest
from services.intent_parser import parse_intent

@pytest.mark.asyncio
async def test_parse_reminder():
    result = await parse_intent(
        "Remind me to call David tomorrow at 4pm",
        timezone="Asia/Shanghai",
        memories=[],
    )
    assert result["intent"] == "reminder"
    assert "reminder" in result["entities"]
    assert result["language"] == "en"
```

### Definition of Done
- [ ] `parse_intent` returns valid JSON with `intent`, `language`, `response_text`, `entities`, `actions`, `new_memories`.
- [ ] Memories are injected into the system prompt.
- [ ] English and Chinese sample inputs work.
- [ ] Tests pass.
- [ ] Commit.

---

## Task 9: Persist Messages, Reminders, Ideas, and Memories

### Objective
Wire up the full handler so every user message is stored and acted on.

### Step 1: Expand `database/crud.py`

```python
async def create_message(session, user_id, raw_type, original_text, attachment_urls, parsed_intent, parsed_entities):
    msg = Message(
        user_id=user_id,
        raw_type=raw_type,
        original_text=original_text,
        attachment_urls=attachment_urls,
        parsed_intent=parsed_intent,
        parsed_entities=parsed_entities,
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


async def create_reminder(session, user_id, source_message_id, title, description, remind_at):
    r = Reminder(
        user_id=user_id,
        source_message_id=source_message_id,
        title=title,
        description=description,
        remind_at=remind_at,
    )
    session.add(r)
    await session.commit()
    await session.refresh(r)
    return r


async def create_idea(session, user_id, source_message_id, content, category):
    i = Idea(
        user_id=user_id,
        source_message_id=source_message_id,
        content=content,
        category=category,
    )
    session.add(i)
    await session.commit()
    await session.refresh(i)
    return i
```

### Step 2: Update `bot/handlers.py` to call the pipeline

```python
async def handle_message(message: discord.Message):
    if message.author.bot or not isinstance(message.channel, discord.DMChannel):
        return

    async with async_session() as session:
        user = await get_or_create_user(session, str(message.author.id), str(message.author))

        if user.timezone == "UTC":
            # Check if the user is setting timezone
            tz = message.content.strip()
            if tz in ["UTC", "skip"]:
                pass
            else:
                try:
                    ZoneInfo(tz)
                    await set_user_timezone(session, user, tz)
                    await message.channel.send(f"Timezone set to {tz}.")
                    return
                except Exception:
                    await message.channel.send("Please send a valid IANA timezone like `Asia/Shanghai`.")
                    return

        # Extract text and images
        extracted = await extract_text_from_message(message)
        images_b64 = await build_image_content(message) if any(a.content_type.startswith("image/") for a in message.attachments) else []

        memories = await get_memories_for_prompt(session, user.id, limit=10)
        parsed = await parse_intent(extracted["text"], user.timezone, memories, images_b64)

        raw_type = "mixed" if (images_b64 and extracted["type"] != "text") else (extracted["type"] if images_b64 else extracted["type"])
        msg = await create_message(
            session, user.id, raw_type, extracted["text"],
            [a.url for a in message.attachments],
            parsed.get("intent"), parsed.get("entities"),
        )

        # Save memories
        if parsed.get("new_memories"):
            await save_memories(session, user.id, parsed["new_memories"])

        # Execute actions
        if "schedule_reminder" in parsed.get("actions", []) and parsed["entities"].get("reminder"):
            r = parsed["entities"]["reminder"]
            remind_at = datetime.fromisoformat(r["remind_at"])
            await create_reminder(session, user.id, msg.id, r["title"], r.get("description"), remind_at)
            # schedule job will be added in Task 10

        if "store_idea" in parsed.get("actions", []) and parsed["entities"].get("idea"):
            i = parsed["entities"]["idea"]
            await create_idea(session, user.id, msg.id, i["content"], i.get("category"))

        # Reply
        response_text = parsed.get("response_text", "Got it.")
        await message.channel.send(response_text[:1900])

        # Update preferred language
        if parsed.get("language"):
            user.preferred_language = parsed["language"]
            await session.commit()
```

### Definition of Done
- [ ] Every user message creates a `Message` row.
- [ ] Reminders and ideas are saved when the intent matches.
- [ ] Memories are saved.
- [ ] Timezone is set on first interaction.
- [ ] Commit.

---

## Task 10: Reminder Scheduler with APScheduler

### Objective
Schedule and fire reminder jobs.

### Files to create
- `services/scheduler.py`

### Step 1: `services/scheduler.py`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from sqlalchemy.ext.asyncio import AsyncSession
from database.core import async_session
from database.models import Reminder, User
from database.crud import get_reminder_by_id, mark_reminder_sent

scheduler = AsyncIOScheduler()


async def send_reminder(reminder_id: int):
    async with async_session() as session:
        reminder = await get_reminder_by_id(session, reminder_id)
        if not reminder or reminder.sent_at:
            return

        user = await session.get(User, reminder.user_id)
        if not user:
            return

        # Fetch Discord user and send DM
        from bot.client import bot
        discord_user = await bot.fetch_user(int(user.discord_user_id))
        if discord_user:
            await discord_user.send(f"⏰ Reminder: {reminder.title}")

        await mark_reminder_sent(session, reminder)


def schedule_reminder(reminder: Reminder):
    scheduler.add_job(
        send_reminder,
        trigger=DateTrigger(run_date=reminder.remind_at),
        args=[reminder.id],
        id=f"reminder_{reminder.id}",
        replace_existing=True,
    )
```

### Step 2: Update `database/crud.py`

```python
async def get_reminder_by_id(session: AsyncSession, reminder_id: int) -> Reminder | None:
    result = await session.execute(select(Reminder).where(Reminder.id == reminder_id))
    return result.scalar_one_or_none()


async def mark_reminder_sent(session: AsyncSession, reminder: Reminder) -> None:
    reminder.sent_at = datetime.utcnow()
    await session.commit()
```

### Step 3: Start scheduler in `main.py`

```python
from services.scheduler import scheduler

async def main():
    await init_db()
    scheduler.start()
    await bot.start(settings.discord_bot_token)
```

### Step 4: Verify

Create a reminder 1 minute in the future. Expected: DM arrives at the exact time.

### Definition of Done
- [ ] Reminders are scheduled via APScheduler.
- [ ] Reminder DMs fire at the correct time.
- [ ] `sent_at` is set after delivery.
- [ ] Commit.

---

## Task 11: Daily Summary Job

### Objective
Send a daily summary at the user's configured time, in their timezone.

### Files to create
- `services/summary.py`

### Step 1: `services/summary.py`

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_messages_since, get_upcoming_reminders
from llm.deepseek_client import stream_chat_completion
from services.memory import format_memories, get_memories_for_prompt


async def generate_daily_summary(session: AsyncSession, user) -> str:
    tz = ZoneInfo(user.timezone)
    now = datetime.now(tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    tomorrow_start = today_start + timedelta(days=1)

    messages = await get_messages_since(session, user.id, yesterday_start)
    reminders_today = await get_upcoming_reminders(session, user.id, today_start, tomorrow_start)
    reminders_tomorrow = await get_upcoming_reminders(session, user.id, tomorrow_start, tomorrow_start + timedelta(days=1))
    memories = await get_memories_for_prompt(session, user.id, limit=10)

    prompt = f"""You are Plan Mode. Write a friendly daily summary for the user in their language.

Yesterday's messages:
{[m.original_text for m in messages if m.original_text]}

Today's reminders:
{[r.title for r in reminders_today]}

Tomorrow's reminders:
{[r.title for r in reminders_tomorrow]}

{format_memories(memories)}

Summarize what happened yesterday and what is coming up tomorrow. Be concise and warm.
"""

    return await stream_chat_completion(
        [{"role": "user", "content": prompt}],
        json_mode=False,
        temperature=0.3,
    )


async def send_daily_summary(user_id: int):
    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            return
        text = await generate_daily_summary(session, user)
        from bot.client import bot
        discord_user = await bot.fetch_user(int(user.discord_user_id))
        if discord_user:
            await discord_user.send(f"📋 Daily Summary\n\n{text[:1800]}")
```

### Step 2: Schedule in `services/scheduler.py`

```python
from apscheduler.triggers.cron import CronTrigger


def schedule_daily_summary(user):
    hour, minute = map(int, user.summary_time.strftime("%H:%M").split(":"))
    scheduler.add_job(
        send_daily_summary,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=user.timezone),
        args=[user.id],
        id=f"daily_summary_{user.id}",
        replace_existing=True,
    )
```

### Definition of Done
- [ ] Daily summary is generated using DeepSeek.
- [ ] Cron trigger respects user's timezone and `summary_time`.
- [ ] Summary is sent as a DM.
- [ ] Commit.

---

## Task 12: Query Handler

### Objective
Answer questions about upcoming events and today's messages.

### Files to create
- `services/queries.py`

### Step 1: `services/queries.py`

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_messages_since, get_upcoming_reminders
from llm.deepseek_client import stream_chat_completion
from services.memory import format_memories, get_memories_for_prompt


async def answer_query(session: AsyncSession, user, question: str, query_type: str) -> str:
    tz = ZoneInfo(user.timezone)
    now = datetime.now(tz)
    messages = []
    reminders = []

    if query_type == "today_messages":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        messages = await get_messages_since(session, user.id, today_start)
    elif query_type == "upcoming":
        reminders = await get_upcoming_reminders(session, user.id, now, now + timedelta(days=7))
    elif query_type == "weekly":
        reminders = await get_upcoming_reminders(session, user.id, now, now + timedelta(days=7))

    memories = await get_memories_for_prompt(session, user.id, limit=10)

    prompt = f"""The user asks: {question}

Data:
Messages: {[m.original_text for m in messages if m.original_text]}
Reminders: {[r.title for r in reminders]}

{format_memories(memories)}

Answer in the user's language. Be concise.
"""

    return await stream_chat_completion(
        [{"role": "user", "content": prompt}],
        json_mode=False,
        temperature=0.3,
    )
```

### Definition of Done
- [ ] Queries return natural answers from stored data.
- [ ] Memories are included in query context.
- [ ] Commit.

---

## Task 13: Memory Compression Job

### Objective
Periodically compress old messages into memory entries and mark them compressed.

### Files to create
- `services/memory_compression.py`

### Step 1: `services/memory_compression.py`

```python
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Message, User
from llm.deepseek_client import parse_json_completion
from services.memory import save_memories


async def compress_old_messages(session: AsyncSession, user: User):
    cutoff = datetime.utcnow() - timedelta(days=7)
    result = await session.execute(
        select(Message)
        .where(Message.user_id == user.id)
        .where(Message.created_at < cutoff)
        .where(Message.compressed == False)
        .order_by(Message.created_at)
        .limit(200)
    )
    messages = result.scalars().all()
    if not messages:
        return

    texts = [f"{m.created_at.isoformat()}: {m.original_text}" for m in messages if m.original_text]
    prompt = f"""Summarize the following user messages into a JSON array of memory entries.
Each entry has: category (preference|fact|goal|routine), content, importance (1-5).

Messages:
{chr(10).join(texts)}

Return only JSON:
{{
  "memories": [
    {{"category": "preference", "content": "...", "importance": 4}}
  ]
}}"""

    parsed = await parse_json_completion([{"role": "user", "content": prompt}], temperature=0.2)
    memories = parsed.get("memories", [])

    source_ids = [m.id for m in messages]
    await save_memories(session, user.id, [
        {**mem, "source_message_ids": source_ids} for mem in memories
    ])

    for m in messages:
        m.compressed = True
    await session.commit()
```

### Step 2: Schedule weekly compression

Add to `services/scheduler.py`:

```python
def schedule_memory_compression(user):
    scheduler.add_job(
        compress_user_memory,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0, timezone=user.timezone),
        args=[user.id],
        id=f"memory_compression_{user.id}",
    )


async def compress_user_memory(user_id: int):
    async with async_session() as session:
        user = await session.get(User, user_id)
        if user:
            await compress_old_messages(session, user)
```

### Definition of Done
- [ ] Old messages are compressed into memory entries.
- [ ] Compressed messages are marked.
- [ ] Compression runs weekly.
- [ ] Commit.

---

## Task 14: Weekly Schedule Graphic (Monday-Sunday)

### Objective
Generate a PNG showing the user's week and send it as a Discord attachment.

### Files to create
- `services/schedule_image.py`

### Step 1: `services/schedule_image.py`

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_upcoming_reminders


async def generate_weekly_image(session: AsyncSession, user) -> str:
    tz = ZoneInfo(user.timezone)
    now = datetime.now(tz)
    # Monday of current week
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)

    reminders = await get_upcoming_reminders(session, user.id, monday, monday + timedelta(days=7))

    width, height = 1400, 800
    img = Image.new("RGB", (width, height), color="#1e1e2e")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
        header_font = font

    draw.text((40, 30), f"Plan Mode — Week of {monday.strftime('%b %d')}", fill="white", font=header_font)

    col_width = (width - 80) // 7
    for i in range(7):
        day = monday + timedelta(days=i)
        x = 40 + i * col_width
        draw.rectangle([x, 100, x + col_width - 10, height - 40], outline="#444466", width=2)
        draw.text((x + 10, 110), day.strftime("%a %m/%d"), fill="#a6e3a1", font=font)

    # Draw reminders per day
    for r in reminders:
        r_local = r.remind_at.astimezone(tz)
        day_index = (r_local.date() - monday.date()).days
        if 0 <= day_index < 7:
            x = 40 + day_index * col_width
            y = 150 + (r.id % 6) * 60  # simple stacking
            draw.rectangle([x + 10, y, x + col_width - 20, y + 45], fill="#89b4fa")
            draw.text((x + 15, y + 5), r.title[:20], fill="black", font=font)

    path = f"/tmp/schedule_{user.id}.png"
    img.save(path)
    return path
```

### Definition of Done
- [ ] PNG is generated with Monday-Sunday layout.
- [ ] Reminders are placed on the correct day using the user's timezone.
- [ ] Image is sent as a Discord attachment.
- [ ] Commit.

---

## Task 15: Multi-Language Response Handling

### Objective
Ensure the bot mirrors the user's language.

### Steps
- System prompt already instructs DeepSeek to reply in the same language.
- Store detected language in `User.preferred_language` after every message (already done in Task 9).
- Add a test for Chinese and English inputs.

### Definition of Done
- [ ] Chinese input gets Chinese reply.
- [ ] English input gets English reply.
- [ ] Commit.

---

## Task 16: VPS Deployment with systemd

### Objective
Run the bot 24/7 on a VPS.

### Files to create
- `deploy/plan-mode.service`
- `deploy/setup.sh`

### Step 1: `deploy/plan-mode.service`

```ini
[Unit]
Description=Plan Mode Discord Bot
After=network.target

[Service]
User=planmode
Group=planmode
WorkingDirectory=/opt/plan-mode
Environment=PYTHONPATH=/opt/plan-mode
ExecStart=/opt/plan-mode/.venv/bin/python -m main
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Step 2: `deploy/setup.sh`

```bash
#!/bin/bash
set -e

# Run as root on Ubuntu 24.04
apt-get update
apt-get install -y python3.12 python3.12-venv python3-pip postgresql postgresql-contrib ffmpeg tesseract-ocr

# Create database user and database
sudo -u postgres psql -c "CREATE USER planmode WITH PASSWORD 'change_me';" || true
sudo -u postgres psql -c "CREATE DATABASE planmode OWNER planmode;" || true

# Create app user and directory
useradd -r -s /bin/false planmode || true
mkdir -p /opt/plan-mode
chown planmode:planmode /opt/plan-mode

# App code and venv are expected to be copied/installed by deploy script
cd /opt/plan-mode
python3.12 -m venv .venv
.venv/bin/pip install -e "."

# Copy service file and start
cp deploy/plan-mode.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable plan-mode.service
systemctl start plan-mode.service
```

### Definition of Done
- [ ] `deploy/plan-mode.service` and `deploy/setup.sh` exist.
- [ ] Service starts and restarts on boot.
- [ ] `journalctl -u plan-mode` shows bot logged in.
- [ ] Commit.

---

## Task 17: README and Configuration Guide

### Objective
Document the project for future you and the VPS deployment.

### `README.md` sections

1. What is Plan Mode
2. Required accounts and API keys
3. Local development setup
4. Environment variables
5. Discord bot setup (intents, DM permissions)
6. Example interactions (text, voice, image)
7. VPS deployment with `deploy/setup.sh`
8. Troubleshooting

### Definition of Done
- [ ] README covers setup, env vars, and deployment.
- [ ] Commit.

---

## Final Definition of Done for the Whole Project

- [ ] User can send text, voice, and image DMs to the bot.
- [ ] Bot extracts reminders, ideas, and queries; stores them in PostgreSQL.
- [ ] Bot asks for timezone on first interaction.
- [ ] Reminders fire via DM at the right time.
- [ ] Daily summary fires at the configured time in the user's timezone.
- [ ] Weekly schedule PNG is generated Monday-Sunday.
- [ ] Bot responds in the user's input language.
- [ ] Memory system stores preferences and compresses old messages weekly.
- [ ] Bot deploys on a VPS with systemd and runs 24/7.
- [ ] All secrets are in `.env` and never committed.

---

## Note for Executor

Do **not** start coding until the user explicitly approves this plan. After approval, proceed task-by-task in order. Each task should be committed independently with a clear message like:

```
task(1): bootstrap project and dependencies
task(2): add SQLAlchemy models and init_db script
task(3): add DeepSeek streaming client
...
```
