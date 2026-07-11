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
