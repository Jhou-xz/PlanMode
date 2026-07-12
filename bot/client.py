import discord
import logging

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

bot = discord.Client(intents=intents)

logger = logging.getLogger(__name__)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id {bot.user.id})")


@bot.event
async def on_error(event_method, *args, **kwargs):
    logger.exception("Discord error in %s", event_method)
