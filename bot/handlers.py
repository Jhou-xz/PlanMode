import logging
from datetime import time

import discord

from database.core import async_session
from database.crud import get_or_create_user, set_user_summary_time, set_user_timezone
from services.agent import run_agent
from services.image_handler import build_image_content
from services.scheduler import schedule_daily_summary, schedule_memory_compression
from services.transcription import transcribe_audio
from services.timezone import resolve_timezone


logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 1900
MAX_IMAGE_ATTACHMENTS = 5
MAX_ATTACHMENT_SIZE_MB = 10

HELP_TEXT = """Here are some things you can ask me:

**Schedule & Tasks**
- "Lunch with Sarah tomorrow at 12"
- "Remind me to call Mom at 6pm"
- "What do I have today?"
- "Mark dentist appointment done"
- "Move my meeting to Thursday"

**Notes & Ideas**
- "Note down an idea for a photo shoot"
- "Create a section for Book Notes"

**Views**
- "Show my weekly schedule"
- "Show my daily plan"
- "Give me a status report"

**Settings**
- "Set my timezone to New York"
- "Change my summary time to 8am"

What would you like to do?
"""


async def extract_text_from_message(message: discord.Message) -> dict:
    """Returns {"text": str, "type": str, "language": str}."""
    text = message.content.strip()
    detected_type = "text"

    if message.flags.voice and message.attachments:
        audio = message.attachments[0]
        audio_bytes = await audio.read()
        result = await transcribe_audio(audio_bytes, filename=audio.filename)
        text = result["text"]
        detected_type = "voice"
    elif message.attachments:
        # Also transcribe regular audio attachments.
        audio_attachment: discord.Attachment | None = next(
            (a for a in message.attachments if a.content_type and a.content_type.startswith("audio/")),
            None,
        )
        if audio_attachment is not None:
            audio_bytes = await audio_attachment.read()
            result = await transcribe_audio(audio_bytes, filename=audio_attachment.filename)
            text = result["text"]
            detected_type = "voice"

    return {"text": text, "type": detected_type, "language": "en"}


async def _is_timezone_change_request(text: str) -> bool:
    t = text.lower().strip()
    return t.startswith(("set timezone", "change timezone", "my timezone is", "timezone is", "set my timezone"))


async def _is_summary_time_change_request(text: str) -> bool:
    t = text.lower().strip()
    return t.startswith(("change my summary time", "set my summary time", "summary time"))


async def _is_help_request(text: str) -> bool:
    t = text.lower().strip()
    return t in {"help", "?", "what can you do", "what can i ask"} or t.startswith("help me")


async def _llm_parse_timezone(text: str) -> str:
    from llm.deepseek_client import chat_completion_text
    from services.timezone import build_timezone_prompt
    try:
        return await chat_completion_text(build_timezone_prompt(text), temperature=0.0)
    except Exception:
        return "UNKNOWN"


async def _handle_timezone_input(message: discord.Message, user, session):
    text = message.content.strip()

    if text.lower().strip() in {"skip", "utc", "gmt", "utc+0", "gmt+0"}:
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


async def _handle_summary_time_input(message: discord.Message, user, session):
    text = message.content.strip().lower()
    # Try simple patterns first, then fall back to LLM if needed.
    parsed = _parse_summary_time(text)
    if parsed is None:
        parsed = await _llm_parse_summary_time(text)

    if parsed is None:
        await message.channel.send(
            "I didn't catch a time. Try something like 'change my summary time to 8am' or 'summary time 21:30'."
        )
        return True

    await set_user_summary_time(session, user, parsed)
    schedule_daily_summary(user)
    await message.channel.send(f"Got it — I'll send your daily summary at {parsed.strftime('%H:%M')} ({user.timezone}).")
    return True


def _parse_summary_time(text: str) -> time | None:
    import re
    # Match "8am", "8:30am", "14:00", etc.
    pattern = re.compile(r"(\d{1,2}):?(\d{2})?\s*(am|pm)?")
    match = pattern.search(text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    ampm = match.group(3)
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if 0 <= hour < 24 and 0 <= minute < 60:
        return time(hour, minute)
    return None


async def _llm_parse_summary_time(text: str) -> time | None:
    from llm.deepseek_client import chat_completion_text
    prompt = (
        f"Extract the time from this message as HH:MM in 24-hour format. "
        f"Reply with only the time, or 'UNKNOWN' if there is no valid time.\n\nMessage: {text}"
    )
    try:
        raw = await chat_completion_text([{"role": "system", "content": prompt}], temperature=0.0)
        raw = raw.strip()
        if raw.upper() == "UNKNOWN":
            return None
        hour, minute = map(int, raw.split(":"))
        return time(hour, minute)
    except Exception:
        return None


async def _send_in_chunks(channel, text: str):
    """Split long replies across multiple Discord messages at paragraph boundaries."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        await channel.send(text)
        return

    paragraphs = text.split("\n\n")
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 > MAX_MESSAGE_LENGTH:
            if current:
                await channel.send(current)
                current = ""
        if len(paragraph) > MAX_MESSAGE_LENGTH:
            # Paragraph itself is too long; fall back to sentence splitting.
            sentences = paragraph.replace(". ", ".\n").split("\n")
            for sentence in sentences:
                if len(current) + len(sentence) + 1 > MAX_MESSAGE_LENGTH:
                    if current:
                        await channel.send(current)
                        current = ""
                current += (" " if current else "") + sentence
        else:
            current += ("\n\n" if current else "") + paragraph
    if current:
        await channel.send(current)


async def _send_image_files(channel, image_paths: list[str]):
    """Send generated images, falling back to text if any file fails."""
    files_to_send = []
    failed_paths = []
    for path in image_paths:
        try:
            files_to_send.append(discord.File(path))
        except Exception as exc:
            logger.warning("Failed to prepare image %s: %s", path, exc)
            failed_paths.append(path)

    if files_to_send:
        try:
            await channel.send(files=files_to_send)
        except Exception:
            logger.exception("Failed to send images")
            failed_paths.extend(image_paths)

    if failed_paths:
        await channel.send("I generated an image but couldn't send it. The text summary is above.")


async def handle_message(message: discord.Message):
    if message.author.bot or not isinstance(message.channel, discord.DMChannel):
        return

    async with message.channel.typing():
        try:
            async with async_session() as session:
                user = await get_or_create_user(
                    session,
                    discord_user_id=str(message.author.id),
                    discord_username=str(message.author),
                )

                extracted = await extract_text_from_message(message)
                if extracted["type"] == "voice" and extracted["text"]:
                    await message.channel.send(f"🎤 I heard: {extracted['text'][:MAX_MESSAGE_LENGTH]}")

                # Onboarding: first-time users need timezone and summary time.
                if not user.timezone_set:
                    handled = await _handle_onboarding(message, user, session)
                    if handled:
                        return

                if await _is_help_request(extracted["text"]):
                    await _send_in_chunks(message.channel, HELP_TEXT)
                    return

                if await _is_timezone_change_request(extracted["text"]):
                    handled = await _handle_timezone_input(message, user, session)
                    if handled:
                        return

                if await _is_summary_time_change_request(extracted["text"]):
                    handled = await _handle_summary_time_input(message, user, session)
                    if handled:
                        return

                has_image = any(
                    a.content_type and a.content_type.startswith("image/")
                    for a in message.attachments
                )
                images_b64 = await _build_limited_image_content(message) if has_image else []

                final_text, image_paths = await run_agent(
                    session,
                    user,
                    extracted["text"],
                    images_b64=images_b64,
                    raw_type=extracted["type"],
                    language=extracted["language"],
                )

                await _send_in_chunks(message.channel, final_text)

                if image_paths:
                    await _send_image_files(message.channel, image_paths)

        except Exception:
            logger.exception("Error handling message from %s", message.author)
            await message.channel.send("I ran into a problem. The error has been logged.")


async def _handle_onboarding(message: discord.Message, user, session) -> bool:
    text = message.content.strip()

    # If the message looks like a timezone request, handle it as the timezone answer.
    if await _is_timezone_change_request(text):
        handled: bool = await _handle_timezone_input(message, user, session)
        return handled

    # Otherwise, prompt for timezone first.
    await message.channel.send(
        "Hi! I'm Plan Mode, your personal scheduling assistant. "
        "To get started, what's your timezone? "
        "(e.g. `Shanghai`, `New York`, `Germany`, or `UTC`)"
    )
    return True


async def _build_limited_image_content(message: discord.Message) -> list[str]:
    """Build base64 image content, respecting count and size limits."""
    images = [
        a for a in message.attachments
        if a.content_type and a.content_type.startswith("image/")
    ][:MAX_IMAGE_ATTACHMENTS]

    oversized = []
    valid = []
    for attachment in images:
        if attachment.size and attachment.size > MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
            oversized.append(attachment.filename)
        else:
            valid.append(attachment)

    if oversized:
        await message.channel.send(
            f"Skipping oversized image(s): {', '.join(oversized)} (max {MAX_ATTACHMENT_SIZE_MB}MB each)."
        )

    if not valid:
        return []

    return await build_image_content(message, attachments=valid)
