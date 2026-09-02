import sys
import discord
from discord.ext import commands
from utils.logger import get_logger
from utils.rich_presenter import rich

logger = get_logger(__name__)


def setup_event_handlers(bot):
    @bot.event
    async def on_ready():
        rich.startup_header()

        if hasattr(bot, "audit_logger"):
            try:
                await bot.audit_logger.log_startup(
                    bot.user.name if bot.user else "Nova",
                    len(bot.guilds),
                    len(bot.settings.GEMINI_API_KEYS),
                )
            except Exception:
                pass

        services = {
            "Discord Gateway": {
                "status": "ok",
                "details": f"Connected as {bot.user.name}"
            },
            "Gemini API": {
                "status": "ok" if bot.settings.GEMINI_API_KEYS else "error",
                "details": f"{len(bot.settings.GEMINI_API_KEYS)} key(s) loaded"
            },
            "Groq API": {
                "status": "ok" if bot.settings.GROQ_API_KEY else "error",
                "details": f"Heavy: {bot.settings.GROQ_MODEL_HEAVY}"
            },
            "Tavily Search": {
                "status": "ok" if bot.settings.TAVILY_API_KEY else "warning",
                "details": "Optional - for web search"
            },
            "Session Memory": {
                "status": "ok",
                "details": "In-memory + JSONL persistence"
            },
            "Micro-RAG": {
                "status": "ok",
                "details": f"TTL: {bot.settings.NUGGETS_TTL_DAYS} days, Top-K: {bot.settings.NUGGETS_TOP_K}"
            }
        }
        rich.service_status(services)

        models = {
            "Intent Analysis": {
                "model": bot.settings.GEMINI_MODEL,
                "provider": "Google"
            },
            "Response Gen": {
                "model": bot.settings.GEMINI_MODEL,
                "provider": "Google"
            },
            "Compaction": {
                "model": bot.settings.GROQ_MODEL_HEAVY,
                "provider": "Groq"
            },
            "RAG Extract": {
                "model": bot.settings.GROQ_MODEL_HEAVY,
                "provider": "Groq"
            },
            "RAG Retrieve": {
                "model": bot.settings.GROQ_MODEL_HEAVY,
                "provider": "Groq"
            },
            "Search Process": {
                "model": bot.settings.GROQ_MODEL_FAST,
                "provider": "Groq"
            }
        }
        rich.model_info(models)

        prefix_example = ", ".join(bot.command_prefix) if isinstance(bot.command_prefix, list) else bot.command_prefix
        triggers = [
            {"type": "Prefix Command", "example": prefix_example, "desc": "Use prefix before message"},
            {"type": "Direct Mention", "example": "@Nova hello", "desc": "Mention the bot"},
            {"type": "Reply to Bot", "example": "Reply to Nova's message", "desc": "Reply with/without mention"},
        ]
        rich.trigger_list(triggers)

        config = {
            "Prefixes": ", ".join(bot.command_prefix) if isinstance(bot.command_prefix, list) else bot.command_prefix,
            "Reply Mention": str(bot.settings.BOT_REPLY_MENTION),
            "Process Reply": str(bot.settings.PROCESS_REPLY_WITHOUT_MENTION),
            "Compaction Threshold": f"{bot.settings.COMPACTION_THRESHOLD:.0%}",
            "Session Timeout": f"{bot.settings.SESSION_TIMEOUT}s",
            "Context Limit": f"{bot.settings.GEMINI_CONTEXT_LIMIT:,} tokens",
        }
        rich.config_table(config)

        rich.ready_message(
            bot.user.name,
            len(bot.guilds),
            bot.latency
        )

        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="your messages | !commands"
            )
        )

        try:
            synced = await bot.tree.sync()
            logger.info(f"Slash commands synced: {len(synced)}")
        except Exception as e:
            logger.error(f"Slash command sync error: {e}")

    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        logger.error(f"Command error: {error}")
        rich.error_panel("Command Error", str(error))
        await ctx.send(f"Error: {str(error)}")

    @bot.event
    async def on_error(event, *args, **kwargs):
        logger.error(f"Event error in {event}: {sys.exc_info()}")
        rich.error_panel("Event Error", f"Error in {event}")
