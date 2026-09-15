import re
import discord
from utils.logger import get_logger
from utils.time_utils import to_wib_iso

logger = get_logger(__name__)

# Pola regex untuk mention Discord:
# - Role mention: <@&ROLE_ID>
# - User mention: <@USER_ID> atau <@!USER_ID>
ROLE_MENTION_RE = re.compile(r'<@&\d+>')
EVERYONE_MENTION_RE = re.compile(r'@(everyone|here)\b')


class MessageRouter:
    def __init__(self, bot, settings):
        self.bot = bot
        self.settings = settings

    def _strip_all_mentions(self, content):
        """Hapus semua mention Discord: bot, role, @everyone, @here.

        Return konten yang sudah bersih dari semua jenis mention.
        Berguna untuk menentukan apakah pesan hanya berisi mention tanpa konten bermakna.
        """
        # Hapus mention bot (user ID)
        content = content.replace(f"<@{self.bot.user.id}>", "")
        content = content.replace(f"<@!{self.bot.user.id}>", "")
        # Hapus role mention: <@&ROLE_ID>
        content = ROLE_MENTION_RE.sub("", content)
        # Hapus @everyone dan @here
        content = EVERYONE_MENTION_RE.sub("", content)
        return content.strip()

    def _is_only_mention_content(self, message):
        """Cek apakah pesan HANYA berisi mention (bot, role, @everyone, @here) tanpa konten bermakna.

        Return True jika setelah semua mention dihapus, tidak ada sisa teks bermakna.
        """
        content = message.content or ""
        cleaned = self._strip_all_mentions(content)
        return not cleaned

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
            # #ignore-role-mention: bersihkan role mention + @everyone/@here juga
            # agar pesan seperti "@Nova @everyone" tetap diproses, tapi "@everyone @role"
            # tanpa konten bermakna lainnya tidak memicu trigger.
            clean = self._strip_all_mentions(content)
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
            # #ignore-role-mention: bersihkan semua mention (bot + role + @everyone/@here)
            return self._strip_all_mentions(content)

        elif trigger_type == "reply_to_bot":
            # #ignore-role-mention: bersihkan semua mention (bot + role + @everyone/@here)
            return self._strip_all_mentions(content)

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
