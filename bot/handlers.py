import discord
from database.core import async_session
from database.crud import get_or_create_user, set_user_timezone
from services.agent import run_agent
from services.image_handler import build_image_content, ocr_image
from services.scheduler import schedule_daily_summary, schedule_memory_compression
from services.transcription import transcribe_audio
from services.timezone import resolve_timezone


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


async def _is_timezone_change_request(text: str) -> bool:
    t = text.lower().strip()
    return t.startswith(("set timezone", "change timezone", "my timezone is", "timezone is", "set my timezone"))


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

        if await _is_timezone_change_request(extracted["text"]):
            handled = await _handle_timezone_input(message, user, session)
            if handled:
                return

        has_image = any(
            a.content_type and a.content_type.startswith("image/")
            for a in message.attachments
        )
        images_b64 = await build_image_content(message) if has_image else []

        # If the LLM later rejects the image, we can fall back to OCR; the agent
        # will receive the image in the message content. We do not OCR here by
        # default to avoid extra work when the LLM succeeds.

        final_text, image_paths = await run_agent(
            session,
            user,
            extracted["text"],
            images_b64=images_b64,
            raw_type=extracted["type"],
        )

        await message.channel.send(final_text[:1900])

        files_to_send = []
        for path in image_paths:
            try:
                files_to_send.append(discord.File(path))
            except Exception:
                pass
        if files_to_send:
            await message.channel.send(files=files_to_send)

        if extracted.get("language"):
            user.preferred_language = extracted["language"]
            await session.commit()
