import discord
from discord import app_commands
from discord.ext import commands
from utils.logger import get_logger

logger = get_logger(__name__)


class Voice(commands.Cog):
    """Voice channel AFK — Nova duduk di voice channel tanpa ngapa-ngapain."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="afk", description="Nova masuk voice channel dan AFK di sana")
    @app_commands.describe(channel="Voice channel target (optional, default: channel kamu sekarang)")
    async def afk_slash(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel = None,
    ):
        await interaction.response.defer(ephemeral=True)

        # Cek user sudah di voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send(
                "Masuk voice channel dulu dong, baka! Aku nggak mau sendirian. (￣ω￣;)",
                ephemeral=True,
            )
            return

        target = channel or interaction.user.voice.channel

        # Cek bot punya permission
        perms = target.permissions_for(interaction.guild.me)
        if not perms.connect or not perms.speak:
            await interaction.followup.send(
                f"Aku nggak punya izin masuk **{target.name}**. "
                "Kasih aku permission `Connect` + `Speak` dulu!",
                ephemeral=True,
            )
            return

        # Cek bot sudah di voice channel lain
        if interaction.guild.voice_client:
            vc = interaction.guild.voice_client
            if vc.channel.id == target.id:
                await interaction.followup.send(
                    "Aku udah di sini, bodoh! (￣▽￣*)ゞ",
                    ephemeral=True,
                )
                return
            await vc.disconnect()

        # Join voice channel
        try:
            await target.connect(self_deaf=True)
        except Exception as e:
            logger.error(f"Voice join error: {e}")
            await interaction.followup.send(
                f"Gagal masuk voice channel: {e}",
                ephemeral=True,
            )
            return

        # Set activity
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"AFK di #{target.name} | !commands",
            )
        )

        logger.info(f"Nova AFK di voice channel: {target.name} ({target.id})")
        await interaction.followup.send(
            f"Oke, aku AFK di **{target.name}**. "
            "Jangan ganggu aku ya! ...tapi kalau mau ngobrol sih bolehlah. (￣ω￣;)",
            ephemeral=False,
        )

    @app_commands.command(name="unafk", description="Nova keluar dari voice channel")
    async def unafk_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        vc = interaction.guild.voice_client
        if not vc:
            await interaction.followup.send(
                "Aku nggak di voice channel mana-mana, bodoh! (ー_ー)!!",
                ephemeral=True,
            )
            return

        channel_name = vc.channel.name
        await vc.disconnect()

        # Reset activity
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="your messages | !commands",
            )
        )

        logger.info(f"Nova keluar dari voice channel: {channel_name}")
        await interaction.followup.send(
            f"Hmph! Aku keluar dari **{channel_name}**. "
            "Bukan karena aku mau lho, cuma bosan aja! (~˘▾˘)~",
            ephemeral=False,
        )

    @commands.command(name="afk")
    async def afk_prefix(self, ctx):
        """Prefix command: !afk"""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("Masuk voice channel dulu dong, baka! (￣ω￣;)")
            return

        target = ctx.author.voice.channel
        perms = target.permissions_for(ctx.guild.me)
        if not perms.connect or not perms.speak:
            await ctx.send(f"Aku nggak punya izin masuk **{target.name}**.")
            return

        if ctx.guild.voice_client:
            vc = ctx.guild.voice_client
            if vc.channel.id == target.id:
                await ctx.send("Aku udah di sini, bodoh! (￣▽￣*)ゞ")
                return
            await vc.disconnect()

        try:
            await target.connect(self_deaf=True)
        except Exception as e:
            await ctx.send(f"Gagal masuk voice channel: {e}")
            return

        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"AFK di #{target.name} | !commands",
            )
        )
        await ctx.send(
            f"Oke, aku AFK di **{target.name}**. "
            "Jangan ganggu aku ya! ...tapi kalau mau ngobrol sih bolehlah. (￣ω￣;)"
        )

    @commands.command(name="unafk")
    async def unafk_prefix(self, ctx):
        """Prefix command: !unafk"""
        vc = ctx.guild.voice_client
        if not vc:
            await ctx.send("Aku nggak di voice channel mana-mana, bodoh! (ー_ー)!!")
            return

        channel_name = vc.channel.name
        await vc.disconnect()

        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="your messages | !commands",
            )
        )
        await ctx.send(
            f"Hmph! Aku keluar dari **{channel_name}**. "
            "Bukan karena aku mau lho, cuma bosan aja! (~˘▾˘)~"
        )




async def setup(bot):
    await bot.add_cog(Voice(bot))
