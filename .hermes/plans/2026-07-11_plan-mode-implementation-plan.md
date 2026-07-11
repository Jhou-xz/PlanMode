# Plan Mode — Implementation Plan

> **Status:** Research & planning phase. **Do not start coding** until this plan is approved.
>
> **For OpenCode execution:** After approval, implement task-by-task using TDD-style commits. The plan is meant to be copied into subagent prompts.

---

## Goal

Build a personal AI assistant called **Plan Mode** that lives inside a Discord bot. A single user (one bot per user) sends text, voice, or image messages to the bot. The bot extracts reminders, events, ideas, and queries; stores everything in a clean PostgreSQL structure; and reminds the user, answers questions, sends a daily summary, and renders a weekly schedule graphic — all delivered via Discord DM.

---

## Architecture Overview

A single Python process runs three long-lived services inside the same `asyncio` event loop:

1. **Discord bot** (`discord.py`) — receives user messages and sends replies.
2. **FastAPI app** — health check, optional admin endpoints, future webhook surface.
3. **APScheduler** (`AsyncIOScheduler`) — fires reminders and daily summaries.

All services share the same PostgreSQL database via **SQLAlchemy 2.0 async** (`asyncpg`).

For scale later, the codebase is structured so each user can be run as a separate process with their own Discord bot token and DeepSeek API key, but the MVP is one user per deployed instance.

---

## Tech Stack & Why

| Component | Choice | Reason |
|---|---|---|
| Language | Python 3.12 | Best ecosystem for Discord bots + ML + async web |
| Discord SDK | `discord.py` 2.x | Mature, async-native, supports attachments, DMs, voice-message flags |
| LLM | DeepSeek API (`deepseek-v4-pro`) | User requested; OpenAI-compatible, strong instruction following, JSON mode, multilingual |
| STT | `faster-whisper` (local) | User requested; offline, multilingual, low cost after setup |
| Web backend | FastAPI + SQLAlchemy 2.0 async + `asyncpg` | Lighter than Django for a bot; native async; fast to develop |
| Scheduler | APScheduler `AsyncIOScheduler` | Proven, integrates with `asyncio`, supports cron |
| Database | PostgreSQL 15+ | Robust, handles time zones, JSON, future-proof |
| Image rendering | Pillow + custom layout | No browser needed, fast, lightweight, good enough for a weekly schedule |
| Deployment | VPS + systemd + venv | Simplest MVP path; Docker Compose can be added later |
| Secrets | `.env` + `pydantic-settings` | Standard, safe, easy to rotate |

---

## Data Model

```python
# Core tables (SQLAlchemy models)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    discord_user_id: Mapped[str] = mapped_column(unique=True, index=True)
    discord_username: Mapped[str | None]
    timezone: Mapped[str] = mapped_column(default="UTC")        # IANA tz, e.g. "Asia/Shanghai"
    summary_time: Mapped[time] = mapped_column(default="22:00") # 10 PM default
    preferred_language: Mapped[str | None]                       # NULL = auto-detect
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    raw_type: Mapped[str]  # "text" | "voice" | "image" | "mixed"
    original_text: Mapped[str | None]      # text body or transcribed voice
    attachment_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    # denormalized copy of what the LLM understood, for debugging/retrieval
    parsed_intent: Mapped[str | None]      # e.g. "reminder", "idea", "query"
    parsed_entities: Mapped[dict | None] = mapped_column(JSON)
    compressed: Mapped[bool] = mapped_column(default=False)  # true after memory compression job
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"))
    title: Mapped[str]
    description: Mapped[str | None]
    remind_at: Mapped[datetime] = mapped_column(index=True)  # UTC, displayed in user tz
    is_done: Mapped[bool] = mapped_column(default=False)
    sent_at: Mapped[datetime | None]  # when the reminder was actually delivered
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

class Idea(Base):
    __tablename__ = "ideas"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"))
    content: Mapped[str]
    category: Mapped[str | None]  # auto-categorized by LLM
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(default="preference")  # preference | fact | goal | routine
    content: Mapped[str]
    importance: Mapped[int] = mapped_column(default=1)  # 1-5, used for ranking
    source_message_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    compressed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now)
```

**Notes:**
- All datetime storage is UTC; display is converted to the user's `timezone`.
- `Message` keeps a raw log of every user input so the daily summary and "what did I say today" queries can reason over full context.

---

## Memory System (User Preferences & Long-Term Context)

Plan Mode needs a memory layer similar to Hermes Agent: a compressed, queryable store of user preferences, facts, and routines that survives beyond the immediate conversation window.

### How it works

1. **Short-term context:** Recent messages (last ~50) and upcoming reminders are included in every prompt.
2. **Long-term memory:** A `memories` table stores compressed facts.
3. **Memory creation:** On every user message, DeepSeek returns `new_memories` (array of `{category, content, importance}`). The bot saves new or updated memory entries.
4. **Memory retrieval:** Before sending a prompt to DeepSeek, the bot retrieves relevant memories from the `memories` table. For the MVP, retrieve the top-N by importance and recency.
5. **Memory compression:** A scheduled job runs weekly (or when message count > 500) to compress old messages into new memory entries and mark the source messages as "compressed".

### Memory table

See `Memory` model in the Data Model section.

### Memory categories

- `preference` — how the user likes things done (e.g., "prefers short replies", "hates morning meetings").
- `fact` — stable facts about the user (e.g., "works at X", "lives in Shanghai").
- `goal` — long-term goals (e.g., "learn Spanish", "launch startup").
- `routine` — recurring patterns (e.g., "gym every Tuesday evening").

### Memory prompt section

```
Relevant memories about the user:
- [preference] User prefers concise replies. (importance: 4)
- [fact] User lives in Shanghai, timezone Asia/Shanghai. (importance: 5)
- [goal] User wants to build a SaaS product. (importance: 3)

Recent messages: ...
Upcoming reminders: ...

Current input: ...
```

### Compression job

- Trigger: weekly cron, or when `messages` count for a user exceeds 500.
- Action: Take messages older than 7 days, ask DeepSeek to summarize them into new memory entries, then mark those messages as `compressed=True`.
- Always preserve the original `Message` rows; just set a flag so future compression jobs skip them.

### Memory updates

If DeepSeek returns a memory that contradicts an existing one, the bot should update the existing memory's `content` and `updated_at` rather than creating a duplicate. For the MVP, a simple string-match or semantic search is optional; we can rely on DeepSeek to return fresh, non-conflicting facts.

---

## Input Processing Pipeline

```
Discord message
    │
    ├─ text ───────────────┐
    ├─ voice attachment ───┤
    │   └─ faster-whisper → text (language auto-detected)
    ├─ image attachment(s)─┤
    │   └─ download, base64, send to DeepSeek with prompt
    └─ mixed  ─────────────┘
              │
              ▼
    Build prompt: system persona + recent messages + user context + **relevant memories** + extracted text
              |
              v
    DeepSeek API (deepseek-v4-pro, JSON mode, streaming collected, temperature 0.2)
              |
              v
    Structured JSON response
        {
          "intent": "reminder" | "idea" | "query" | "summary_request" | "schedule_request" | "chat",
          "language": "en" | "zh" | "es" | ...,
          "response_text": "natural reply in the same language",
          "entities": { ... },
          "actions": [ "schedule_reminder", "store_idea", ... ],
          "new_memories": [
            {"category": "preference", "content": "User dislikes morning meetings", "importance": 3}
          ]
        }
              |
              v
    Persist Message, Reminder, Idea, **new Memory entries**
    Execute actions (schedule APScheduler job, run query, generate image)
              |
              v
    Stream DeepSeek response, collect full text, send Discord DM reply
```

---

## DeepSeek JSON Schema

```json
{
  "intent": "reminder",
  "language": "en",
  "response_text": "Got it — I'll remind you about the David meeting 30 minutes before 4 PM tomorrow.",
  "entities": {
    "reminder": {
      "title": "Meeting with David",
      "description": "",
      "remind_at": "2026-07-12T15:30:00+08:00",
      "original_time_expression": "tomorrow at 4pm"
    }
  },
  "actions": ["schedule_reminder"],
  "new_memories": []
}
```

**Supported intents:**
- `reminder` — create a one-time reminder (default 30 min before if time is an event).
- `idea` — store a random idea/project note.
- `query` — answer from stored data (e.g., "what do I have tomorrow?").
- `summary_request` — user asks for today's summary immediately.
- `schedule_request` — user wants a weekly schedule graphic (Monday–Sunday).
- `chat` — generic conversation, no storage action.

---

## Discord Bot Behavior

- **DM-only for the MVP.** The bot listens to direct messages from the configured owner.
- **On first interaction:** If `User.timezone` is `UTC` (default) or not set, the bot asks the user: *"What city/timezone are you in? (e.g., Asia/Shanghai, Europe/Berlin)"* and stores the IANA timezone.
- **Attachments:**
  - Voice messages → `message.flags.voice` is True, audio attachment is downloaded.
  - Images → one or more image attachments are downloaded and sent to DeepSeek.
- **Replies:** All replies are sent as Discord DMs.
- **Streaming:** DeepSeek responses are streamed, collected in full, then sent as one Discord DM. Discord is not ideal for true typing-indicator streaming, so we stream the API but send the final message.
- **Command fallback:** If the user types something like `!schedule` or `!summary`, the bot also handles it as a shortcut, but natural language is the primary interface.

---

## Voice Handling (faster-whisper)

### Research findings
- Discord voice messages arrive as regular `discord.Message` objects with `message.flags.voice == True`.
- The audio attachment is typically an Ogg/Opus file.
- `discord.py` exposes `attachment.url` and `await attachment.read()` or `attachment.save(path)`.
- `faster-whisper` runs locally, supports CPU/CUDA, and auto-detects language unless told otherwise.

### Implementation
```python
from faster_whisper import WhisperModel
model = WhisperModel("base", device="cpu", compute_type="int8")
segments, info = model.transcribe("audio.ogg")
text = " ".join([seg.text for seg in segments])
language = info.language  # e.g. "zh", "en"
```

**Model choice:** Start with `base` (~150 MB, fast, good enough for short voice notes). Provide `config/whisper_model` env var to upgrade to `small` or `medium` later.

**Audio format:** Convert to WAV 16 kHz mono with `ffmpeg` / `pydub` if needed. `faster-whisper` accepts common formats directly, so try direct first.

---

## Image Handling

- Download image attachments via `attachment.read()`.
- Encode as base64 data URI.
- Send to DeepSeek V4 Pro using OpenAI-compatible multimodal `content` array:

```python
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": [
        {"type": "text", "text": user_text or "Describe this image and extract any relevant information."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
    ]}
]
```

**Risk/fallback:** If `deepseek-v4-pro` rejects image inputs during implementation, fall back to a local vision model or OCR (e.g., `easyocr` / `pytesseract`) and note it as a follow-up task. The plan is written assuming DeepSeek V4 Pro supports vision.

---

## Scheduling & Daily Summary

- **APScheduler `AsyncIOScheduler`** runs inside the same event loop as the bot.
- **Reminders:** When a reminder is created, add a one-time `DateTrigger` job. On fire, send the DM and mark `reminder.sent_at`.
- **Daily summary:** For each user, add a `CronTrigger` at the user's `summary_time` in their timezone. The job:
  1. Fetches messages from the last 24 hours and upcoming reminders.
  2. Calls DeepSeek with a summary prompt.
  3. Sends the summary as a DM.

---

## Weekly Schedule Graphic

- Generate a PNG with **Pillow**.
- Layout: 7 columns (Monday–Sunday), rows for hours or just a card list per day.
- Show upcoming reminders/events for the week, color-coded by category.
- Include the date range and a small header.
- Send as a Discord attachment.

**Future upgrade path:** Render HTML/CSS and screenshot with Playwright for a more polished look. Pillow is chosen for the MVP because it has no browser dependency.

---

## Multi-Language Behavior

- **Detect language** from the user's message (DeepSeek returns `language` field; faster-whisper also returns `language` for voice).
- **Store** the detected language in `User.preferred_language`.
- **Respond** in the same language. The system prompt instructs the model to mirror the user's language.

---

## Implementation Tasks

### Phase 1 — Project Skeleton & Infrastructure

#### Task 1: Create repository, dependencies, and environment
**Objective:** Bootstrap the project so it can run locally.

**Files:**
- Create: `.env.example`
- Create: `.gitignore`
- Create: `pyproject.toml` (or `requirements.txt`)
- Create: `config/settings.py`

**Step 1:** Write `pyproject.toml` with dependencies:
```toml
[project]
name = "plan-mode"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "discord.py",
    "fastapi",
    "uvicorn[standard]",
    "sqlalchemy[asyncio]",
    "asyncpg",
    "apscheduler",
    "openai",            # for DeepSeek OpenAI-compatible API
    "faster-whisper",
    "pillow",
    "pydantic-settings",
    "python-dotenv",
    "tzdata",            # for timezone handling on Linux
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "ruff", "mypy"]
```

**Step 2:** Write `.env.example`:
```bash
DISCORD_BOT_TOKEN=your_discord_bot_token
DEEPSEEK_API_KEY=your_deepseek_api_key
DATABASE_URL=postgresql+asyncpg://planmode:password@localhost:5432/planmode
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
SUMMARY_DEFAULT_TIME=22:00
```

**Step 3:** Write `config/settings.py` using `pydantic-settings`:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    discord_bot_token: str
    deepseek_api_key: str
    database_url: str
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    summary_default_time: str = "22:00"
    model_config = {"env_file": ".env"}
```

**Step 4:** Create a virtual environment, install dependencies, and run `python -c "import discord, fastapi, sqlalchemy, apscheduler, openai, faster_whisper, PIL; print('ok')"`.

**Step 5:** Commit.

---

#### Task 2: Set up PostgreSQL database and SQLAlchemy models
**Objective:** Create the persistent storage layer.

**Files:**
- Create: `database/core.py` (engine, session, base)
- Create: `database/models.py` (User, Message, Reminder, Idea)
- Create: `alembic.ini` + `migrations/` (or use `sqlalchemy.schema` for first schema)
- Create: `database/__init__.py`

**Step 1:** Write `database/models.py` (exact schema from Data Model section above).

**Step 2:** Write `database/core.py`:
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database.models import Base

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

**Step 3:** Create a small `scripts/init_db.py` that calls `init_db()` and run it successfully.

**Step 4:** Commit.

---

#### Task 3: Create DeepSeek client module
**Objective:** Wrap the DeepSeek API in a reusable async client.

**Files:**
- Create: `llm/deepseek_client.py`
- Create: `llm/prompts.py` (system prompts)

**Step 1:** Write `llm/deepseek_client.py`:
```python
import openai
from config.settings import settings

client = openai.AsyncOpenAI(
    api_key=settings.deepseek_api_key,
    base_url="https://api.deepseek.com",
)

async def chat_completion(messages: list, json_mode: bool = True, temperature: float = 0.2):
    response = await client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=messages,
        response_format={"type": "json_object"} if json_mode else None,
        temperature=temperature,
    )
    return response.choices[0].message.content
```

**Step 2:** Write a test script that sends a simple prompt and prints the response. Verify the API key works and the model name is accepted.

**Step 3:** Commit.

---

### Phase 2 — Discord Bot & Input Handling

#### Task 4: Discord bot connection and message receiving
**Objective:** The bot can connect to Discord and receive DMs.

**Files:**
- Create: `bot/client.py`
- Create: `bot/events.py`
- Create: `main.py`

**Step 1:** Write `bot/client.py`:
```python
import discord
from config.settings import settings

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not isinstance(message.channel, discord.DMChannel):
        return  # MVP: DMs only
    await handle_message(message)
```

**Step 2:** In `main.py`, start the bot:
```python
import asyncio
from bot.client import bot
from database.core import init_db

async def main():
    await init_db()
    await bot.start(settings.discord_bot_token)

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 3:** Run `main.py`, send a DM to the bot, and verify it logs the message.

**Step 4:** Commit.

---

#### Task 5: Voice message handling with faster-whisper
**Objective:** The bot can transcribe voice messages to text.

**Files:**
- Create: `services/transcription.py`
- Modify: `bot/events.py` (or `bot/handlers.py`)

**Step 1:** Write `services/transcription.py`:
```python
from faster_whisper import WhisperModel
from config.settings import settings

model = WhisperModel(
    settings.whisper_model,
    device=settings.whisper_device,
    compute_type="int8",
)

async def transcribe_audio(audio_bytes: bytes, filename: str = "audio.ogg") -> dict:
    # Save to tmp, transcribe, return {"text": ..., "language": ...}
```

**Step 2:** In `handle_message`, detect `message.flags.voice`, download the audio attachment with `await attachment.read()`, call `transcribe_audio`, and log the result.

**Step 3:** Send a test voice message to the bot and verify the transcription is correct.

**Step 4:** Commit.

---

#### Task 6: Image message handling
**Objective:** The bot can download and describe image attachments.

**Files:**
- Modify: `services/llm_input.py` (or `bot/handlers.py`)

**Step 1:** In `handle_message`, detect image attachments, download them with `await attachment.read()`, base64-encode them, and include them in the DeepSeek prompt.

**Step 2:** Write a helper `build_multimodal_content(text, images_b64)` that returns the OpenAI-style content array.

**Step 3:** Send a test image to the bot and verify DeepSeek describes it or extracts relevant info.

**Step 4:** Commit.

---

### Phase 3 — NLP & Storage

#### Task 7: Intent extraction and structured parsing with DeepSeek
**Objective:** Convert raw user input into structured JSON with intent, entities, and a reply.

**Files:**
- Create: `llm/prompts.py` (system prompt + JSON examples)
- Create: `services/intent_parser.py`

**Step 1:** Write the system prompt in `llm/prompts.py`:
```python
SYSTEM_PROMPT = """You are Plan Mode, a personal assistant. The user communicates with you via Discord.
Analyze the input and return JSON with keys: intent, language, response_text, entities, actions.
Intents: reminder, idea, query, summary_request, schedule_request, chat.
Respond in the same language as the user. Use ISO 8601 with timezone for any datetime.
Always infer a reasonable remind_at for reminders. If the user says "tomorrow at 4pm" and timezone is Asia/Shanghai, produce 2026-07-12T16:00:00+08:00."""
```

**Step 2:** Write `services/intent_parser.py`:
```python
async def parse_intent(user_text: str, images_b64: list = None, timezone: str = "UTC") -> dict:
    messages = build_messages(user_text, images_b64, timezone)
    raw = await chat_completion(messages, json_mode=True)
    return json.loads(raw)
```

**Step 3:** Write unit tests with sample inputs (English, Chinese, voice transcription) and verify the JSON structure.

**Step 4:** Commit.

---

#### Task 8: Persist messages, reminders, and ideas
**Objective:** Save parsed data into PostgreSQL.

**Files:**
- Create: `database/crud.py`
- Modify: `services/intent_parser.py` or `bot/handlers.py`

**Step 1:** Write CRUD helpers in `database/crud.py`:
- `get_or_create_user(discord_user_id, ...)`
- `create_message(...)`
- `create_reminder(...)`
- `create_idea(...)`
- `get_upcoming_reminders(user_id, after)`
- `get_messages_since(user_id, since)`

**Step 2:** In `handle_message`, after parsing, save the `Message` record and then any `Reminder` or `Idea` records.

**Step 3:** Run a test conversation and verify rows appear in the database.

**Step 4:** Commit.

---

### Phase 4 — Scheduling & Responses

#### Task 9: Reminder scheduler with APScheduler
**Objective:** The bot sends reminder DMs at the right time.

**Files:**
- Create: `services/scheduler.py`
- Modify: `database/crud.py` (add `mark_reminder_sent`)
- Modify: `bot/handlers.py`

**Step 1:** Initialize `AsyncIOScheduler` in `services/scheduler.py` and start it in `main.py`.

**Step 2:** Write a reminder job function `send_reminder(reminder_id)` that:
- Loads the reminder from the DB.
- Sends a Discord DM to the user.
- Marks `sent_at`.

**Step 3:** When a reminder is created, schedule it with `scheduler.add_job(send_reminder, trigger="date", run_date=reminder.remind_at, args=[reminder.id])`.

**Step 4:** Create a test reminder 1 minute in the future, wait, and verify the DM arrives.

**Step 5:** Commit.

---

#### Task 10: Daily summary job
**Objective:** Every day at the user's configured time, send a summary of today + tomorrow.

**Files:**
- Modify: `services/scheduler.py`
- Create: `services/summary.py`

**Step 1:** Write `generate_daily_summary(user_id)`:
- Fetch messages from the last 24 hours.
- Fetch reminders due today and tomorrow.
- Send a prompt to DeepSeek asking for a friendly summary.
- Return the text.

**Step 2:** Write `schedule_daily_summary(user)` that adds a `CronTrigger` at the user's `summary_time` in their timezone.

**Step 3:** On bot startup, load all users and schedule their daily summaries.

**Step 4:** Test by setting summary time to 1 minute from now and verifying the DM.

**Step 5:** Commit.

---

#### Task 11: Query handler
**Objective:** Answer "what do I have today?", "what did I say today?", and similar.

**Files:**
- Create: `services/queries.py`

**Step 1:** Implement query functions:
- `get_upcoming_events(user_id, days=7)`
- `get_today_messages(user_id)`
- `get_weekly_events(user_id)`

**Step 2:** In `handle_message`, when `intent == "query"`, call the appropriate query, build a prompt with the raw data, ask DeepSeek to summarize, and send the reply.

**Step 3:** Write tests for common queries.

**Step 4:** Commit.

---

### Phase 5 — Graphics & Polish

#### Task 12: Weekly schedule graphic generator
**Objective:** Generate a clean weekly schedule PNG and send it as an attachment.

**Files:**
- Create: `services/schedule_image.py`
- Modify: `bot/handlers.py`

**Step 1:** Write `generate_weekly_image(user_id, start_of_week)`:
- Load reminders for the week.
- Draw a 7-column grid using Pillow.
- Day names, dates, event cards, color-coded categories.
- Save to a temporary PNG.

**Step 2:** In `handle_message`, when `intent == "schedule_request"`, generate the image and send it with `message.channel.send(file=discord.File(...))`.

**Step 3:** Test the command and verify the image looks readable.

**Step 4:** Commit.

---

#### Task 13: Multi-language response handling
**Objective:** Ensure the bot responds in the user's input language.

**Files:**
- Modify: `llm/prompts.py` (strengthen language instruction)
- Modify: `database/crud.py` (store `preferred_language`)

**Step 1:** Update the system prompt to explicitly say: "Always reply in the same language the user used."

**Step 2:** In `handle_message`, when parsing returns `language`, update `User.preferred_language`.

**Step 3:** Send test messages in English and Chinese and verify responses match.

**Step 4:** Commit.

---

### Phase 6 — Deployment & Documentation

#### Task 14: VPS deployment with systemd
**Objective:** The bot runs 24/7 on a VPS.

**Files:**
- Create: `deploy/plan-mode.service`
- Create: `deploy/setup.sh`
- Modify: `main.py` (add `asyncio` graceful shutdown)

**Step 1:** Write `deploy/plan-mode.service`:
```ini
[Unit]
Description=Plan Mode Discord Bot
After=network.target

[Service]
User=planmode
WorkingDirectory=/opt/plan-mode
Environment=PYTHONPATH=/opt/plan-mode
ExecStart=/opt/plan-mode/.venv/bin/python -m main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Step 2:** Write `deploy/setup.sh` that installs Python, PostgreSQL, creates venv, sets up `.env`, and enables the service.

**Step 3:** Test the service on the VPS (or local VM) and verify it survives a reboot.

**Step 4:** Commit.

---

#### Task 15: README and configuration guide
**Objective:** Document how to run and configure the bot.

**Files:**
- Create: `README.md`

**Step 1:** Write README with:
- What it is
- Required accounts (Discord bot, DeepSeek API key, VPS)
- Installation steps
- Environment variables
- How to interact (examples in text, voice, image)
- How to deploy with systemd

**Step 2:** Commit.

---

## Project Directory Layout

```
plan-mode/
├── .env
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
├── main.py
├── config/
│   └── settings.py
├── database/
│   ├── __init__.py
│   ├── core.py
│   ├── models.py
│   └── crud.py
├── bot/
│   ├── __init__.py
│   ├── client.py
│   └── handlers.py
├── llm/
│   ├── __init__.py
│   ├── deepseek_client.py
│   └── prompts.py
├── services/
│   ├── __init__.py
│   ├── transcription.py
│   ├── intent_parser.py
│   ├── scheduler.py
│   ├── summary.py
│   ├── queries.py
│   └── schedule_image.py
├── deploy/
│   ├── setup.sh
│   └── plan-mode.service
└── tests/
    ├── __init__.py
    ├── test_intent_parser.py
    └── test_queries.py
```

---

## Deployment Plan

1. **VPS:** Ubuntu 24.04 LTS, 2 vCPU, 4 GB RAM (faster-whisper base model runs fine on CPU).
2. **PostgreSQL:** Install via `apt`, create `planmode` user and database.
3. **Code:** Clone repo to `/opt/plan-mode`, create Python venv, install dependencies.
4. **Secrets:** Place `.env` with Discord bot token, DeepSeek key, and DB URL.
5. **Systemd:** Copy `deploy/plan-mode.service`, enable/start.
6. **Discord bot token:** Create one bot per user in the Discord Developer Portal; enable `Message Content` and `Direct Messages` intents.

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| DeepSeek V4 Pro does not support image inputs in the exact OpenAI format | Medium | Try the standard `image_url` format first; if rejected, add an OCR/vision fallback task (e.g., `pytesseract` or a local vision model). |
| faster-whisper model too slow on VPS CPU | Low | Start with `base`; allow `WHISPER_MODEL` env var to switch to `tiny` or `small`. |
| Discord bot token + bot-per-user scaling | Medium | Keep user data isolated by process; each user gets their own bot token and service instance. |
| Timezone/DST handling | Low | Use `zoneinfo` + IANA tz names; store all datetimes as UTC. |
| DeepSeek API rate limits | Low | Retry with exponential backoff; implement request queue if needed. |
| Secrets leakage | Low | Keep secrets in `.env` only; never commit them. Use Pydantic settings. |

---

## Open Questions (Answered)

| # | Question | Decision |
|---|---|---|
| 1 | DeepSeek image fallback if images are rejected? | **Yes** — implement standard `image_url` format first; if rejected, add OCR/vision fallback. |
| 2 | Install `ffmpeg` on VPS for voice conversion? | **Yes** — install `ffmpeg` and `pydub` as fallback. |
| 3 | Timezone handling? | **Ask the user** for their timezone on first interaction; store IANA name. |
| 4 | Weekly schedule start day? | **Monday to Sunday**. |
| 5 | Streaming responses? | **Yes** — stream from DeepSeek, collect full text, then send one Discord DM. |
| 6 | Memory / user preferences? | **Yes** — implement memory table + compression job, similar to Hermes memory. |

---

## Next Step

Once this plan is approved, the implementation will be handed to **OpenCode** using the Kimi model as the executor, with this plan as the spec. The executor will work task-by-task, run tests, and commit frequently. **No code should be written before this plan is approved.**
