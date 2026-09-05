import discord
from utils.logger import get_logger
from utils.time_utils import to_wib_iso

logger = get_logger(__name__)


class MessageRouter:
    def __init__(self, bot, settings):
        self.bot = bot
        self.settings = settings

    def detect_trigger(self, message):
        if message.author.bot:
            return None

        # discord.py 2.7: message.interaction deprecated — pakai interaction_metadata saja.
        # Jangan akses message.interaction (memicu DeprecationWarning tiap pesan).
        if getattr(message, "interaction_metadata", None):
            return "slash_command"

        content = message.content or ""

        prefixes = self.bot.command_prefix
        if isinstance(prefixes, str):
            prefixes = [prefixes]

        for prefix in prefixes:
            if content.startswith(prefix):
                return "prefix_command"

        if self.bot.user.mentioned_in(message):
            clean = content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "").strip()
            if clean:
                return "direct_mention"

        if message.reference and message.reference.resolved:
            if message.reference.resolved.author.id == self.bot.user.id:
                return "reply_to_bot"

        return None

    def should_process_reply(self, message):
        if not message.reference:
            return True

        if self.settings.PROCESS_REPLY_WITHOUT_MENTION:
            return True

        if self.bot.user.mentioned_in(message):
            return True

        return False

    def is_bot_command(self, message):
        """True bila pesan adalah prefix-command terdaftar (agar AI tidak double-reply).

        Per Context7 discord.py: on_message yang override harus tetap panggil
        process_commands, jadi AI handler harus skip pesan command asli.
        """
        content = message.content or ""
        prefixes = self.bot.command_prefix
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        matched_prefix = None
        for prefix in prefixes:
            if content.startswith(prefix):
                matched_prefix = prefix
                break
        if not matched_prefix:
            return False
        rest = content[len(matched_prefix):].strip()
        if not rest:
            return False
        cmd_name = rest.split()[0].lower()
        try:
            return self.bot.get_command(cmd_name) is not None
        except Exception:
            return False

    def clean_content(self, message, trigger_type):
        content = message.content or ""

        if trigger_type == "prefix_command":
            prefixes = self.bot.command_prefix
            if isinstance(prefixes, str):
                prefixes = [prefixes]
            for prefix in prefixes:
                if content.startswith(prefix):
                    return content[len(prefix):].strip()

        elif trigger_type == "direct_mention":
            content = content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "")
            return content.strip()

        elif trigger_type == "reply_to_bot":
            content = content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "")
            return content.strip()

        return content

    def extract_metadata(self, message, trigger_type):
        metadata = {
            "user_id": message.author.id,
            "user_name": message.author.display_name,
            "channel_id": message.channel.id,
            "channel_name": getattr(message.channel, "name", "DM"),
            "timestamp": to_wib_iso(message.created_at),
            "trigger_type": trigger_type,
            "message_id": message.id,
            "guild_id": message.guild.id if message.guild else None,
            "guild_name": message.guild.name if message.guild else None,
        }

        if hasattr(message.channel, "thread") and message.channel.thread:
            metadata["thread_id"] = message.channel.thread.id
            metadata["thread_name"] = message.channel.thread.name

        if message.reference and message.reference.resolved:
            ref = message.reference.resolved
            metadata["parent_message"] = {
                "author": ref.author.display_name,
                "content": ref.content,
                "id": ref.id,
            }

        return metadata
