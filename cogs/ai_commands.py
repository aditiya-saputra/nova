import discord
from discord.ext import commands
from utils.logger import get_logger

logger = get_logger(__name__)


class AICommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ask")
    async def ask(self, ctx, *, question: str):
        await ctx.send(f"Processing: {question}")

    @commands.command(name="ai")
    async def ai(self, ctx, *, prompt: str):
        await ctx.send(f"AI Response for: {prompt}")

    @commands.command(name="commands")
    async def commands_list(self, ctx):
        embed = discord.Embed(
            title="Nova AI Bot - Commands",
            description="Available commands",
            color=discord.Color.blue()
        )
        embed.add_field(name="!ask <question>", value="Ask a question", inline=False)
        embed.add_field(name="!ai <prompt>", value="AI prompt", inline=False)
        embed.add_field(name="!commands", value="Show this help", inline=False)
        embed.add_field(name="!status", value="Show bot status", inline=False)
        embed.add_field(name="!info", value="Show detailed bot stats", inline=False)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AICommands(bot))
