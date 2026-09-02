import discord
from discord.ext import commands
from utils.logger import get_logger

logger = get_logger(__name__)


class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx):
        channel_key = f"channel_{ctx.channel.id}"
        self.bot.session_manager.clear(channel_key)
        await ctx.send("Conversation history cleared.")

    @commands.command(name="stats")
    @commands.has_permissions(manage_messages=True)
    async def stats(self, ctx):
        channel_key = f"channel_{ctx.channel.id}"
        tokens = self.bot.session_manager.get_token_count(channel_key)
        usage = self.bot.session_manager.get_token_usage(channel_key)

        embed = discord.Embed(
            title="Bot Statistics",
            color=discord.Color.green()
        )
        embed.add_field(name="Channel Tokens", value=f"{tokens:,}", inline=True)
        embed.add_field(name="Context Usage", value=f"{usage:.1%}", inline=True)
        embed.add_field(name="Gemini Keys", value=len(self.bot.settings.GEMINI_API_KEYS), inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="status")
    async def status(self, ctx):
        embed = discord.Embed(
            title="Bot Status",
            color=discord.Color.green()
        )
        embed.add_field(name="Status", value="Online", inline=True)
        embed.add_field(name="Latency", value=f"{self.bot.latency * 1000:.0f}ms", inline=True)
        embed.add_field(name="Guilds", value=len(self.bot.guilds), inline=True)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AdminCommands(bot))
