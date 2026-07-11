import discord
from datetime import datetime
from zoneinfo import ZoneInfo
from database.crud import (
    get_or_create_user,
    set_user_timezone,
    create_message,
    create_reminder,
    create_idea,
    get_recent_messages_for_prompt,
)
from database.core import async_session
from llm.deepseek_client import chat_completion
from services.transcription import transcribe_audio
from services.image_handler import build_image_content
from services.intent_parser import parse_intent
from services.memory import get_memories_for_prompt, save_memories
from services.queries import answer_query
from services.schedule_image import generate_weekly_image
from services.scheduler import (
    schedule_reminder,
    schedule_daily_summary,
    schedule_memory_compression,
)
from services.timezone import resolve_timezone, build_timezone_prompt
from services.date_parser import parse_reminder_datetime, ReminderDateError


def _is_timezone_skip(text: str) -> bool:
    return text.lower().strip() in {"skip", "utc", "gmt", "utc+0", "gmt+0"}


async def _is_timezone_change_request(text: str) -> bool:
    t = text.lower().strip()
    return t.startswith(("set timezone", "change timezone", "my timezone is", "timezone is", "set my timezone"))


async def _llm_parse_timezone(text: str) -> str:
    try:
        return await chat_completion(build_timezone_prompt(text), json_mode=False, temperature=0.0)
    except Exception:
        return "UNKNOWN"


async def _handle_timezone_input(message: discord.Message, user, session):
    text = message.content.strip()

    if _is_timezone_skip(text):
        await set_user_timezone(session, user, "UTC")
        schedule_daily_summary(user)
        schedule_memory_compression(user)
        await message.channel.send("Got it — I'll use UTC. You can change it anytime by saying 'set my timezone to ...'")
        return True

    tz = await resolve_timezone(text, llm_parse_fn=_llm_parse_timezone)
    if tz:
        await set_user_timezone(session, user, tz)
        schedule_daily_summary(user)
        schedule_memory_compression(user)
        await message.channel.send(f"Got it — timezone set to {tz}.")
        return True

    await message.channel.send(
        "I didn't recognize that timezone. Could you tell me a nearby city or country? "
        "(e.g. `Shanghai`, `New York`, `Germany`, or `UTC`)"
    )
    return True


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


async def handle_message(message: discord.Message):
    if message.author.bot or not isinstance(message.channel, discord.DMChannel):
        return

    async with async_session() as session:
        user = await get_or_create_user(
            session,
            discord_user_id=str(message.author.id),
            discord_username=str(message.author),
        )

        extracted = await extract_text_from_message(message)
        if extracted["type"] == "voice" and extracted["text"]:
            await message.channel.send(f"🎤 I heard: {extracted['text'][:1900]}")

        # Default timezone is Asia/Shanghai. Only change if user explicitly asks.
        if await _is_timezone_change_request(extracted["text"]):
            handled = await _handle_timezone_input(message, user, session)
            if handled:
                return

        has_image = any(
            a.content_type and a.content_type.startswith("image/")
            for a in message.attachments
        )
        images_b64 = await build_image_content(message) if has_image else []

        history = await get_recent_messages_for_prompt(session, user.id, limit=15)
        memories = await get_memories_for_prompt(session, user.id, limit=20)
        parsed = await parse_intent(
            extracted["text"], user.timezone, memories, history, images_b64
        )

        raw_type = "mixed" if (images_b64 and extracted["type"] != "text") else extracted["type"]
        msg = await create_message(
            session,
            user.id,
            raw_type,
            extracted["text"],
            [a.url for a in message.attachments],
            parsed.get("intent"),
            parsed.get("entities"),
            role="user",
        )

        if parsed.get("new_memories"):
            await save_memories(session, user.id, parsed["new_memories"])

        response_text = parsed.get("response_text", "Got it.")
        schedule_image_path = ""

        if "schedule_reminder" in parsed.get("actions", []) and parsed["entities"].get("reminder"):
            r = parsed["entities"]["reminder"]
            try:
                remind_at = await parse_reminder_datetime(
                    r["remind_at"],
                    r.get("original_time_expression"),
                    user.timezone,
                )
                reminder = await create_reminder(
                    session, user.id, msg.id, r["title"], r.get("description"), remind_at
                )
                schedule_reminder(reminder)
            except ReminderDateError as exc:
                response_text = exc.message

        if "store_idea" in parsed.get("actions", []) and parsed["entities"].get("idea"):
            i = parsed["entities"]["idea"]
            await create_idea(session, user.id, msg.id, i["content"], i.get("category"))

        query_result = ""
        if parsed.get("intent") == "query" and parsed["entities"].get("query"):
            q = parsed["entities"]["query"]
            query_result = await answer_query(
                session, user, extracted["text"], q.get("question_type", "upcoming")
            )
        elif parsed.get("intent") == "schedule_request":
            week_start = None
            sr = parsed["entities"].get("schedule_request") or {}
            if sr.get("week_start"):
                try:
                    from datetime import datetime as dt
                    week_start = dt.fromisoformat(sr["week_start"])
                except Exception:
                    pass
            schedule_image_path = await generate_weekly_image(session, user, week_start)

        if query_result:
            response_text = query_result
        await message.channel.send(response_text[:1900])
        if schedule_image_path:
            await message.channel.send(file=discord.File(schedule_image_path))

        # Persist the assistant's response so it appears in future history.
        await create_message(
            session,
            user.id,
            "text",
            response_text[:1900],
            [],
            parsed.get("intent"),
            None,
            role="assistant",
        )

        if parsed.get("language"):
            user.preferred_language = parsed["language"]
            await session.commit()
