import asyncio
import discord
from core.bot import create_bot
from services.gemini_client import GeminiClient
from services.groq_client import GroqClient
from services.tavily_client import TavilyClient
from services.browserless_client import BrowserlessClient
from services.tool_executor import ToolExecutor
from memory.session_manager import SessionManager
from memory.history_store import HistoryStore
from memory.rag_store import RagStore
from memory.compaction_engine import CompactionEngine
from memory.audit_logger import AuditLogger
from memory.github_backup import GitHubBackup
from memory.scheduled_jobs import ScheduledJobs
from memory.mention_store import MentionStore
from core.context_builder import ContextBuilder
from handlers.message_handler import MessageHandler
from utils.logger import get_logger

logger = get_logger(__name__)


async def main():
    bot = create_bot()
    settings = bot.settings

    gemini = GeminiClient(settings)
    groq = GroqClient(settings)
    tavily = TavilyClient(settings)
    browserless = BrowserlessClient(settings)
    history_store = HistoryStore(settings)
    session_manager = SessionManager(settings, history_store)
    rag_store = RagStore(settings)
    context_builder = ContextBuilder(settings)
    audit_logger = AuditLogger(settings)
    github_backup = GitHubBackup(settings)
    mention_store = MentionStore(settings)
    compaction_engine = CompactionEngine(
        settings, session_manager, history_store, groq, context_builder, audit_logger
    )
    tool_executor = ToolExecutor(bot)

    for name, obj in {
        "gemini": gemini, "groq": groq, "tavily": tavily, "browserless": browserless,
        "session_manager": session_manager, "history_store": history_store,
        "rag_store": rag_store, "context_builder": context_builder,
        "audit_logger": audit_logger, "github_backup": github_backup,
        "mention_store": mention_store, "compaction_engine": compaction_engine,
        "tool_executor": tool_executor,
    }.items():
        setattr(bot, name, obj)

    github_backup.attach_audit(audit_logger)

    scheduled_jobs = ScheduledJobs(settings, audit_logger, github_backup)
    bot.scheduled_jobs = scheduled_jobs
    bot.welcome_back_enabled = True

    message_handler = MessageHandler(
        bot, settings, gemini, groq, rag_store, history_store,
        session_manager, context_builder, tool_executor,
        compaction_engine, audit_logger, github_backup, mention_store,
    )
    bot.message_handler = message_handler

    for ext in ("cogs.ai_commands", "cogs.admin_commands", "cogs.dynamic_presence", "cogs.slash_commands"):
        await bot.load_extension(ext)
    logger.info("Slash commands loaded!")

    if github_backup.backup_enabled:
        github_backup.init_repo()

    await scheduled_jobs.start()

    @bot.event
    async def on_message(message):
        message_handler.cache_message(message)
        if message.author.bot:
            return
        try:
            await message_handler.handle(message)
        except Exception as e:
            logger.error(f"Unhandled on_message error: {e}")
        finally:
            # Selalu teruskan ke command processor (discord.py best practice).
            # AI handler sudah skip pesan command via is_bot_command, jadi aman.
            try:
                await bot.process_commands(message)
            except Exception as e:
                logger.error(f"process_commands error: {e}")

    @bot.event
    async def on_message_delete(message):
        try:
            await message_handler.handle_delete(message)
        except Exception as e:
            logger.error(f"Unhandled on_message_delete error: {e}")

    @bot.event
    async def on_message_edit(before, after):
        try:
            await message_handler.handle_edit(before, after)
        except Exception as e:
            logger.error(f"Unhandled on_message_edit error: {e}")

    @bot.event
    async def on_presence_update(before, after):
        try:
            await message_handler.handle_presence(before, after)
        except Exception as e:
            logger.error(f"Unhandled on_presence_update error: {e}")

    try:
        await bot.start(settings.DISCORD_TOKEN)
    finally:
        try:
            await audit_logger.log_shutdown("normal")
        except Exception:
            pass
        try:
            await scheduled_jobs.stop()
        except Exception:
            pass
        try:
            if hasattr(groq, "aclose"):
                await groq.aclose()
        except Exception:
            pass
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
