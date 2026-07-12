# AGENTS.md — Plan Mode

> This file is written for AI coding agents. It assumes you know nothing about the project and need accurate, project-specific facts rather than generic advice. The project language is English.

## Project overview

**Plan Mode** is a personal AI assistant delivered as a Discord DM bot. A user sends the bot text, voice, or image messages; the bot parses intent, stores structured data in PostgreSQL, and replies in Discord DMs. It can manage schedules, tasks, ideas, reminders, daily summaries, and a weekly schedule image.

Key facts:

- Discord-only interface, DMs only (`bot/handlers.py` ignores non-DM channels).
- Multi-modal input: text, voice messages (faster-whisper transcription), image attachments (DeepSeek multimodal + optional OCR fallback).
- Uses **DeepSeek** as the LLM backend (`deepseek-v4-pro` model, via the OpenAI-compatible API at `https://api.deepseek.com`).
- Persistent storage in **PostgreSQL** using async SQLAlchemy + `asyncpg`.
- Background jobs via **APScheduler** (`AsyncIOScheduler`): reminder DMs, daily summaries, weekly memory compression.
- Currently **English-only replies** are enforced by the system prompt in `llm/prompts.py`; the `language` field returned from message extraction is always `"en"` and the test suite enforces English responses.

## Technology stack

- **Language:** Python >=3.12 (project metadata declares 3.12; code uses `|` union syntax).
- **Package manager / build:** `pip` + `setuptools`, configured in `pyproject.toml`.
- **Discord SDK:** `discord.py>=2.4.0` (`discord.Client`, not commands extension).
- **LLM client:** `openai>=1.35.0` pointed at DeepSeek.
- **Database:** `sqlalchemy[asyncio]>=2.0.0`, `asyncpg>=0.29.0`, PostgreSQL JSONB columns.
- **Scheduler:** `apscheduler>=3.10.0`.
- **Voice transcription:** `faster-whisper>=1.0.0`, using `ffmpeg` (installed by `deploy/setup.sh`).
- **Image generation:** `pillow>=10.0.0`; optional OCR via system `tesseract-ocr` + `pytesseract`.
- **HTTP downloads:** `aiohttp>=3.9.0`.
- **Configuration:** `pydantic-settings>=2.2.0` reading `.env`.
- **Dev tooling:** `pytest>=8.0`, `pytest-asyncio>=0.23`, `ruff>=0.4.0`, `mypy>=1.10.0`.
- **Declared but unused:** `fastapi>=0.110.0` and `uvicorn[standard]>=0.29.0` are in `pyproject.toml` but there is no web server, API, or webhook code in the repository.

## Project structure

```
.
├── main.py                 # Entry point: logging, init DB, start scheduler + Discord bot
├── pyproject.toml          # Package metadata, dependencies, pytest/mypy/ruff config
├── .env.example            # Template for required environment variables
├── README.md               # Human-facing setup and usage guide
├── AGENTS.md               # This file
│
├── bot/                    # Discord client and message handling
│   ├── client.py           # discord.Client setup, intents, on_ready/on_error
│   └── handlers.py         # DM message handler, voice/image extraction, timezone logic
│
├── config/                 # Runtime configuration
│   └── settings.py         # Pydantic Settings class reading .env
│
├── database/               # SQLAlchemy async ORM and CRUD
│   ├── core.py             # Engine, async_session, init_db()
│   ├── models.py           # Declarative models: User, Section, Item, Reminder, Memory, Message
│   └── crud.py             # Async CRUD helpers, DEFAULT_SYSTEM_SECTIONS
│
├── llm/                    # DeepSeek / OpenAI client and prompts
│   ├── deepseek_client.py  # Async chat completions (streaming, non-streaming, JSON)
│   └── prompts.py          # System prompt, tool instructions, formatting headers
│
├── services/               # Business logic and tool implementations
│   ├── agent.py            # Tool-calling agent loop, memory extraction, message persistence
│   ├── scheduler.py        # APScheduler jobs for reminders, summaries, memory compression
│   ├── summary.py          # Daily summary generation + DM delivery
│   ├── memory.py           # Memory retrieval, deduplication, saving, formatting
│   ├── memory_compression.py # Summarize old messages into memories weekly
│   ├── daily_view.py       # Text + image daily plan rendering
│   ├── schedule_image.py   # Weekly schedule PNG generation (Monday-Sunday)
│   ├── status_report.py    # Full status report across sections
│   ├── timezone.py         # Timezone resolution (aliases, fuzzy, LLM fallback)
│   ├── transcription.py    # faster-whisper voice-to-text
│   ├── image_handler.py    # Download Discord image attachments, base64, optional OCR
│   └── tools/              # Agent tool implementations
│       ├── __init__.py     # TOOL_SCHEMAS, TOOL_FUNCTIONS, TERMINAL_TOOLS, execute_tool_call
│       ├── items.py        # create_item, update_item, delete_item, mark_item_done, search_items
│       ├── sections.py     # create_section
│       ├── reminders.py    # set_reminder, delete_reminder
│       ├── views.py        # query_status_report, generate_daily_list_view, generate_weekly_image
│       └── messaging.py    # send_message, ask_user (terminal tools)
│
├── utils/                  # Shared helpers
│   ├── audio.py
│   ├── time.py             # ISO 8601 datetime parsing in user timezone
│   └── tool_result.py      # Standardized tool result envelope
│
├── scripts/                # One-off utilities
│   ├── init_db.py          # Create all SQLAlchemy tables
│   ├── test_db.py          # Quick DB connectivity test
│   └── test_deepseek.py    # Quick DeepSeek API test
│
├── deploy/                 # Production deployment artifacts
│   ├── setup.sh            # Ubuntu 24.04 root setup script
│   └── plan-mode.service   # systemd unit file
│
└── tests/                  # pytest suite
    ├── conftest.py         # async PostgreSQL session fixture (creates/drops tables per test)
    ├── test_handlers.py
    ├── test_language.py
    ├── test_memory.py
    ├── test_memory_compression.py
    ├── test_schedule_image.py
    ├── test_scheduler.py
    ├── test_summary.py
    └── test_tools.py       # Tool registry, schemas, dispatch, and confirmation flow
```

All `__init__.py` files in top-level packages are empty. Imports cross packages directly (e.g., `from config.settings import settings`).

## Configuration

Copy `.env.example` to `.env` and fill in values. `config/settings.py` reads `.env` via Pydantic.

Required variables:

| Variable | Purpose |
| --- | --- |
| `DISCORD_BOT_TOKEN` | Discord bot token |
| `DEEPSEEK_API_KEY` | DeepSeek API key |
| `DATABASE_URL` | asyncpg URL, e.g. `postgresql+asyncpg://planmode:password@localhost:5432/planmode` |

Optional variables with defaults:

| Variable | Default | Purpose |
| --- | --- | --- |
| `WHISPER_MODEL` | `base` | faster-whisper model size |
| `WHISPER_DEVICE` | `cpu` | faster-whisper device |
| `SUMMARY_DEFAULT_TIME` | `22:00` | Default daily summary time for new users |
| `MEMORY_TOP_N` | `10` | (configured but unused at time of writing) |
| `MEMORY_COMPRESSION_THRESHOLD` | `500` | (configured but unused at time of writing) |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG` or `INFO`) |

## Runtime architecture

1. `main.py` runs:
   - `setup_logging()` → logs to stdout and a hardcoded rotating file at `/root/plan-mode-project/bot.log`.
   - `init_db()` → creates missing tables via SQLAlchemy metadata.
   - Starts `APScheduler`.
   - Schedules daily summaries and memory compression for every existing user.
   - Calls `bot.start(settings.discord_bot_token)`.
2. `bot/client.py` is a plain `discord.Client` with `message_content` and `dm_messages` intents.
3. `bot/handlers.py::handle_message` processes each DM:
   - Ignores bots and non-DM channels.
   - Creates/retrieves the `User` record.
   - Greets first-time users and asks for timezone / summary time until `User.timezone_set` is true.
   - Extracts text (voice messages and audio attachments → `services/transcription.py`, image stays as attachment).
   - Short-circuits timezone change requests, summary-time change requests, and help requests.
   - Base64-encodes image attachments via `services/image_handler.py` (respects count and size limits).
   - Calls `services/agent.py::run_agent`.
   - Sends the text reply (split into chunks if too long) and any returned image files.
4. `services/agent.py::run_agent` is the core loop:
   - Loads recent messages, ranked memories, and relevant items.
   - Builds a system prompt from `llm/prompts.py` (includes few-shot examples, item-resolution rules, and guardrails).
   - Calls the LLM with `TOOL_SCHEMAS` (max 6 iterations).
   - Executes action tools first, then terminal tools (`send_message` / `ask_user`).
   - Always appends a matching `role: "tool"` result for every tool call, including terminal tools.
   - Extracts memories from the exchange and saves them.
   - Persists the user and assistant messages.
5. `services/scheduler.py` manages background jobs:
   - Reminder jobs are `DateTrigger` jobs named `reminder_<id>`. New reminders created via tools are scheduled immediately; pending reminders are scheduled on startup.
   - Daily summaries are `CronTrigger` jobs named `daily_summary_<user_id>` at `user.summary_time` in the user's timezone.
   - Memory compression is a `CronTrigger` job named `memory_compression_<user_id>` running Sundays at 02:00 in the user's timezone.

## Database model

Managed by `database/models.py` using `DeclarativeBase` and SQLAlchemy 2.0 mapped-column syntax.

- `User` — Discord user identity, timezone, summary time, preferred language.
- `Section` — User-defined or system sections (`Schedule`, `Tasks`, `Idea Hub`, `Completed`). `section_type` is `system` or `custom`.
- `Item` — The core entity stored in a section; supports title, content, start/end time, due date, status, priority, tags, custom JSONB fields.
- `Reminder` — Linked to an `Item`, fires at `remind_at`.
- `Memory` — Free-form facts/preferences/goals/routines about the user, with importance.
- `Message` — Conversation history; `compressed` flag for memory compression.

There are **no database migrations** (no Alembic). Schema changes require re-running `scripts/init_db.py` or manually altering the database.

## Agent and tools

Tools are declared in `services/tools/__init__.py` via `ToolDefinition` objects:

- `TOOL_SCHEMAS` — JSON schemas generated from Pydantic models in `services/tools/schemas.py` and passed to the LLM.
- `TOOL_FUNCTIONS` — Mapping of name → async function.
- `TERMINAL_TOOLS` — `send_message`, `ask_user` (terminate the loop and return to user).

When adding a tool, define a Pydantic input model in `services/tools/schemas.py`, implement the handler in the appropriate module, and register it in `services/tools/__init__.py`. The schema, handler, and terminal flag are co-located in `ToolDefinition`. Update `llm/prompts.py` if the available-tool list or behavior changes.

Tool modules:

- `schemas.py`: Pydantic input models for every tool; single source of truth for parameters and validation.
- `items.py`: typed handlers for create, update, delete, mark-done, and search; parses ISO 8601 datetimes and schedules default 15-minute reminders for events with `start_time`.
- `sections.py`: create, list, update, and delete sections (system sections cannot be deleted).
- `reminders.py`: set, list, get, and delete reminders; schedules new reminders immediately.
- `views.py`: wrappers around status report, daily list view, weekly image, and daily image generation.
- `memory_tools.py`: save, search, and delete stored memories.
- `messaging.py`: terminal tools returning a `ToolResult` with `final_response`.
- `reasoning.py`: internal no-op tool for the model to think out loud.

Destructive actions (`delete_item`, `delete_section`, `delete_reminder`, `delete_memory`) require user confirmation. The first tool call returns a confirmation prompt; the matching `confirm_delete_*` tool performs the deletion after the user confirms.

## Build and run commands

Local development (from `README.md`):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# edit .env with your keys
python scripts/init_db.py
python main.py
```

One-off helper scripts:

```bash
python scripts/test_db.py      # verify DB connectivity
python scripts/test_deepseek.py # verify DeepSeek API key
```

Lint / type-check:

```bash
ruff check .
ruff format .
mypy .
```

> Note: `mypy` and `ruff` are configured only by presence in dev dependencies; there is no `[tool.ruff]` or per-file ignore configuration in `pyproject.toml`.

## Testing instructions

Run the suite with:

```bash
pytest
```

`pyproject.toml` sets `asyncio_mode = "auto"`, so async tests do not need explicit markers.

Important caveats:

- `tests/conftest.py` creates a real async PostgreSQL engine using `settings.database_url` from your `.env`.
- It creates all tables at test start, yields a session, and then deletes rows and drops tables after each test.
- **Do not run tests against a production database** — the fixture deletes all data in the configured `DATABASE_URL`.
- There is no in-memory SQLite fallback; PostgreSQL must be running and accessible.

## Code style guidelines

Follow the existing style:

- Use Python 3.12+ syntax (`str | None`, `dict`, `list`).
- Use SQLAlchemy 2.0 mapped-column style and `select()` / async sessions.
- Keep tool implementations stateless; they receive `(session, user, **kwargs)` and return `dict`.
- Prefer `logging.getLogger(__name__)` over print statements.
- Use explicit timezone-aware datetimes; `zoneinfo.ZoneInfo` is the canonical source of truth.
- When parsing LLM-provided datetimes, use `datetime.fromisoformat` and assume the user's timezone if none is provided.

## Deployment

The project includes an Ubuntu 24.04 deployment path:

1. Copy project files to `/opt/plan-mode`.
2. Place a valid `.env` at `/opt/plan-mode/.env`.
3. Run as root:

   ```bash
   sudo bash deploy/setup.sh
   ```

4. Manage with systemd:

   ```bash
   sudo systemctl status plan-mode
   sudo journalctl -u plan-mode -f
   ```

`deploy/setup.sh` installs Python 3.12, PostgreSQL, `ffmpeg`, `tesseract-ocr`, creates the `planmode` DB user/database, creates a system user, installs the venv, and enables/starts the systemd service.

`deploy/plan-mode.service` runs `/opt/plan-mode/.venv/bin/python -m main` with `PYTHONPATH=/opt/plan-mode` and `Restart=always`.

## Security and operational notes

- **Secrets live in `.env`**. Never commit `.env`; it is listed in `.gitignore`.
- **Discord token and DeepSeek key** are required; protect them as high-sensitivity credentials.
- **Hardcoded log path**: `main.py` writes logs to `/root/plan-mode-project/bot.log`. This path does not match the deployment directory `/opt/plan-mode`. If the bot runs as the `planmode` system user, that directory may not exist or may not be writable.
- **No migrations**: schema evolution is manual. Re-running `init_db.py` creates missing tables but does not alter existing columns.
- **No input sanitization beyond SQLAlchemy ORM**: CRUD uses bound parameters; avoid building raw SQL from user input.
- **Image attachments** are downloaded with `aiohttp` and base64-encoded for the LLM. There is no file-size or rate-limit guard in the current code.
- **OCR is optional**: `pytesseract` is imported inside a `try/except` and is not listed in `pyproject.toml`; it relies on the system `tesseract-ocr` package installed by `setup.sh`.
- **Tests can wipe data**: the pytest fixture deletes all rows in the configured `DATABASE_URL` after each test.

## Things to know before editing

- The `language` field returned by `extract_text_from_message` is hardcoded to `"en"`. Voice transcription returns a detected language internally, but the handler overwrites it. The LLM system prompt enforces English replies, and `tests/test_language.py` asserts this.
- `fastapi` / `uvicorn` are declared dependencies but no code imports them; they may be leftovers or intended for a future health-check endpoint.
- Memory deduplication uses `difflib.SequenceMatcher` with a 0.75 similarity threshold in `services/memory.py`.
- Weekly schedule images are rendered with DejaVu fonts at fixed paths under `/usr/share/fonts/truetype/dejavu/`; if those fonts are missing, Pillow falls back to the default bitmap font.
- The default user timezone in the model is `Asia/Shanghai`, but the handler treats `"skip"`/`"UTC"`/`"GMT"` as UTC and otherwise resolves the timezone via aliases/fuzzy match/LLM.
