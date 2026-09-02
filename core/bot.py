import json
import discord
from discord.ext import commands
from config.settings import Settings
from core.event_handler import setup_event_handlers
from core.message_router import MessageRouter


def create_bot():
    settings = Settings()

    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True
    intents.members = True
    intents.presences = True

    if settings.BOT_PREFIXES:
        prefixes = settings.BOT_PREFIXES
    else:
        with open("config/prefixes.json", encoding="utf-8") as f:
            prefix_data = json.load(f)
            prefixes = prefix_data["prefixes"]

    bot = commands.Bot(command_prefix=prefixes, intents=intents)
    bot.settings = settings
    bot.router = MessageRouter(bot, settings)

    setup_event_handlers(bot)

    return bot
