import asyncio
import random
import discord
from discord.ext import commands, tasks
from utils.logger import get_logger

logger = get_logger(__name__)


class DynamicPresence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.status_index = 0
        self.total_tokens = 0
        self.total_messages = 0
        self.total_queries = 0

        self.statuses = [
            {"type": "listening", "text": "your messages | !commands"},
            {"type": "listening", "text": "to your thoughts..."},
            {"type": "watching", "text": "{guilds} servers"},
            {"type": "watching", "text": "{users} users"},
            {"type": "playing", "text": "with AI models"},
            {"type": "playing", "text": "with your questions"},
            {"type": "competing", "text": "against boredom"},
            {"type": "competing", "text": "to impress you"},
            {"type": "playing", "text": "Nova Bot v1.0"},
            {"type": "playing", "text": "with Gemini & Groq"},
            {"type": "listening", "text": "your secrets..."},
            {"type": "watching", "text": "{users} people"},
            {"type": "competing", "text": "to be the best AI"},
            {"type": "playing", "text": "with {tokens} tokens"},
            {"type": "listening", "text": "carefully..."},
            {"type": "watching", "text": "for new messages"},
            {"type": "playing", "text": "hard to get"},
            {"type": "listening", "text": "{queries} queries today"},
        ]

        self.presence_loop.start()
        self.stats_loop.start()

    @tasks.loop(minutes=3)
    async def presence_loop(self):
        try:
            status = self.statuses[self.status_index]
            activity_type = status["type"]
            text = status["text"]

            text = text.format(
                guilds=len(self.bot.guilds),
                users=sum(g.member_count or 0 for g in self.bot.guilds),
                channel="#general",
                tokens=self.total_tokens,
                queries=self.total_queries
            )

            if activity_type == "listening":
                activity = discord.Activity(
                    type=discord.ActivityType.listening,
                    name=text
                )
            elif activity_type == "watching":
                activity = discord.Activity(
                    type=discord.ActivityType.watching,
                    name=text
                )
            elif activity_type == "playing":
                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    name=text
                )
            elif activity_type == "competing":
                activity = discord.Activity(
                    type=discord.ActivityType.competing,
                    name=text
                )
            else:
                activity = discord.Activity(
                    type=discord.ActivityType.listening,
                    name=text
                )

            await self.bot.change_presence(activity=activity)

            self.status_index = (self.status_index + 1) % len(self.statuses)

        except Exception as e:
            logger.error(f"Presence update error: {e}")

    @presence_loop.before_loop
    async def before_presence_loop(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=5)
    async def stats_loop(self):
        try:
            self.total_tokens = 0
            self.total_messages = 0

            for key, messages in self.bot.session_manager.sessions.items():
                self.total_messages += len(messages)

            for key, usage in self.bot.session_manager.token_counts.items():
                self.total_tokens += usage

            self.total_queries = self.total_messages // 2

        except Exception as e:
            logger.error(f"Stats update error: {e}")

    @stats_loop.before_loop
    async def before_stats_loop(self):
        await self.bot.wait_until_ready()

    def add_tokens(self, count):
        self.total_tokens += count

    def add_message(self):
        self.total_messages += 1

    def add_query(self):
        self.total_queries += 1

    @commands.command(name="info")
    async def info_command(self, ctx):
        embed = discord.Embed(
            title="Nova Status",
            color=discord.Color.teal()
        )

        status_text = self.statuses[(self.status_index - 1) % len(self.statuses)]["text"]
        embed.add_field(name="Current Status", value=status_text, inline=False)

        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Users", value=str(sum(g.member_count or 0 for g in self.bot.guilds)), inline=True)
        embed.add_field(name="Sessions", value=str(len(self.bot.session_manager.sessions)), inline=True)
        embed.add_field(name="Total Tokens", value=f"{self.total_tokens:,}", inline=True)
        embed.add_field(name="Total Messages", value=str(self.total_messages), inline=True)
        embed.add_field(name="Total Queries", value=str(self.total_queries), inline=True)
        embed.add_field(name="Latency", value=f"{self.bot.latency * 1000:.0f}ms", inline=True)
        embed.add_field(name="Uptime", value=f"{self.get_uptime()}", inline=True)

        await ctx.send(embed=embed)

    def get_uptime(self):
        if hasattr(self.bot, 'start_time'):
            import datetime
            uptime = datetime.datetime.now() - self.bot.start_time
            hours, remainder = divmod(int(uptime.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours}h {minutes}m {seconds}s"
        return "Unknown"

    def cog_unload(self):
        self.presence_loop.cancel()
        self.stats_loop.cancel()


async def setup(bot):
    import datetime
    bot.start_time = datetime.datetime.now()
    await bot.add_cog(DynamicPresence(bot))
