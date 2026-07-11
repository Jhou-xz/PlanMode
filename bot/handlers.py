import discord
from database.crud import get_or_create_user
from database.core import async_session
from services.transcription import transcribe_audio


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
