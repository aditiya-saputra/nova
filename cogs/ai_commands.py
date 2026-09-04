import discord
from discord.ext import commands
from utils.logger import get_logger

logger = get_logger(__name__)


class AICommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _ai_answer(self, ctx, question: str):
        """Jalur prefix (!ask/!ai): pakai session + Gemini, catat ke history."""
        gemini = getattr(self.bot, "gemini", None)
        session_manager = getattr(self.bot, "session_manager", None)
        history_store = getattr(self.bot, "history_store", None)
        context_builder = getattr(self.bot, "context_builder", None)
        if not gemini:
            await ctx.send("AI service not configured.")
            return
        channel_key = f"channel_{ctx.channel.id}"
        try:
            async with ctx.typing():
                metadata = {
                    "user_id": ctx.author.id,
                    "user_name": ctx.author.display_name,
                    "channel_id": ctx.channel.id,
                    "channel_name": getattr(ctx.channel, "name", "DM"),
                    "timestamp": ctx.message.created_at.isoformat(),
                    "trigger_type": "prefix_command",
                    "guild_id": ctx.guild.id if ctx.guild else None,
                    "guild_name": ctx.guild.name if ctx.guild else None,
                }
                nuggets = []
                try:
                    if hasattr(self.bot, "rag_store") and context_builder:
                        nuggets = await self.bot.message_handler._retrieve_facts(question, ctx.channel.id)
                except Exception:
                    nuggets = []
                system_prompt = context_builder.build_system_prompt(metadata, nuggets) if context_builder else ""
                prompt = f"{system_prompt}\n\nUser: {question}" if system_prompt else question
                history = []
                if session_manager:
                    session_manager.add_message(channel_key, "user", question)
                    hist = session_manager.get_history(channel_key)[:-1]
                    history = [
                        {"role": m["role"], "parts": [{"text": m["content"]}]}
                        for m in hist[-20:] if m["role"] in ("user", "model", "system")
                    ]
                if history_store:
                    history_store.append_message(channel_key, ctx.author.id, "user", question)
                response = await gemini.generate(prompt, history=history or None)
                if session_manager:
                    session_manager.add_message(channel_key, "assistant", response)
                if history_store:
                    history_store.append_message(channel_key, ctx.author.id, "assistant", response)
            # Discord limit 2000 char — potong aman.
            for chunk in [response[i:i + 1900] for i in range(0, len(response), 1900)] or ["(empty)"]:
                await ctx.send(chunk)
        except Exception as e:
            logger.error(f"AI prefix command error: {e}")
            await ctx.send(f"Error: {e}")

    @commands.command(name="ask")
    async def ask(self, ctx, *, question: str):
        await self._ai_answer(ctx, question)

    @commands.command(name="ai")
    async def ai(self, ctx, *, prompt: str):
        await self._ai_answer(ctx, prompt)

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
