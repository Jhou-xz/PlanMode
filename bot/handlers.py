import discord
from datetime import datetime
from zoneinfo import ZoneInfo
from database.crud import (
    get_or_create_user,
    set_user_timezone,
    create_message,
    create_reminder,
    create_idea,
)
from database.core import async_session
from services.transcription import transcribe_audio
from services.image_handler import build_image_content
from services.intent_parser import parse_intent
from services.memory import get_memories_for_prompt, save_memories


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

        if user.timezone == "UTC":
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
                    await message.channel.send(
                        "Please send a valid IANA timezone like `Asia/Shanghai`."
                    )
                    return

        extracted = await extract_text_from_message(message)
        has_image = any(
            a.content_type and a.content_type.startswith("image/")
            for a in message.attachments
        )
        images_b64 = await build_image_content(message) if has_image else []

        memories = await get_memories_for_prompt(session, user.id, limit=10)
        parsed = await parse_intent(extracted["text"], user.timezone, memories, images_b64)

        raw_type = "mixed" if (images_b64 and extracted["type"] != "text") else extracted["type"]
        msg = await create_message(
            session,
            user.id,
            raw_type,
            extracted["text"],
            [a.url for a in message.attachments],
            parsed.get("intent"),
            parsed.get("entities"),
        )

        if parsed.get("new_memories"):
            await save_memories(session, user.id, parsed["new_memories"])

        if "schedule_reminder" in parsed.get("actions", []) and parsed["entities"].get("reminder"):
            r = parsed["entities"]["reminder"]
            remind_at = datetime.fromisoformat(r["remind_at"])
            await create_reminder(
                session, user.id, msg.id, r["title"], r.get("description"), remind_at
            )

        if "store_idea" in parsed.get("actions", []) and parsed["entities"].get("idea"):
            i = parsed["entities"]["idea"]
            await create_idea(session, user.id, msg.id, i["content"], i.get("category"))

        response_text = parsed.get("response_text", "Got it.")
        await message.channel.send(response_text[:1900])

        if parsed.get("language"):
            user.preferred_language = parsed["language"]
            await session.commit()
