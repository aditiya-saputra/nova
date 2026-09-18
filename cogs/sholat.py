import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from utils.logger import get_logger
from utils.time_utils import WIB
from memory.scheduled_jobs import load_sholat_config, save_sholat_config

logger = get_logger(__name__)


class Sholat(commands.Cog):
    """Jadwal Sholat & Auto-Reminder"""

    def __init__(self, bot):
        self.bot = bot

    @property
    def client(self):
        return getattr(self.bot, "sholat_client", None)

    def _get_config(self) -> dict:
        return load_sholat_config()

    def _save_config(self, config: dict):
        save_sholat_config(config)

    def _build_embed(self, data: dict, title: str = None) -> discord.Embed:
        """Build embed dari jadwal sholat data."""
        times = data.get("times", {})
        city = data.get("city", "N/A")
        province = data.get("province", "")
        date_str = data.get("date", "")
        hijri = data.get("hijri", "")
        source = data.get("source", "")

        location = f"{city}" + (f", {province}" if province else "")

        if not title:
            # Format tanggal cantik
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                hari = dt.strftime("%A")
                tgl = dt.strftime("%d %B %Y")
                title = f"🕌 Jadwal Sholat — {location}"
                header = f"📅 {hari}, {tgl}"
            except ValueError:
                title = f"🕌 Jadwal Sholat — {location}"
                header = f"📅 {date_str}"
        else:
            header = date_str

        embed = discord.Embed(title=title, color=discord.Color.teal())

        if hijri:
            header += f"\n🌙 {hijri}"

        embed.description = header

        # Tabel waktu sholat
        lines = []
        emoji_map = {
            "imsak": "🌙", "subuh": "🌅", "terbit": "☀️", "dhuha": "🌤️",
            "dzuhur": "🌞", "ashar": "🌇", "maghrib": "🌆", "isya": "🌃",
        }
        for key, label in [
            ("imsak", "Imsak"), ("subuh", "Subuh"), ("terbit", "Terbit"),
            ("dhuha", "Dhuha"), ("dzuhur", "Dzuhur"), ("ashar", "Ashar"),
            ("maghrib", "Maghrib"), ("isya", "Isya"),
        ]:
            t = times.get(key, "")
            if t:
                emoji = emoji_map.get(key, "🕌")
                lines.append(f"{emoji} **{label}** — {t}")

        embed.add_field(name="Waktu Sholat", value="\n".join(lines), inline=False)

        source_label = "myQuran (Kementerian Agama RI)" if source == "myquran" else "AlAdhan API"
        embed.set_footer(text=f"📡 Sumber: {source_label}")

        return embed

    @app_commands.command(name="sholat", description="Lihat jadwal sholat hari ini")
    @app_commands.describe(days="Lihat jadwal N hari ke depan (1-30, default: hari ini)")
    async def sholat_today(self, interaction: discord.Interaction, days: int = 0):
        await interaction.response.defer(ephemeral=True)

        if not self.client:
            await interaction.followup.send("Sholat client belum terkonfigurasi.", ephemeral=True)
            return

        if days < 0 or days > 30:
            await interaction.followup.send("Hari harus antara 0-30! (0 = hari ini)", ephemeral=True)
            return

        if days == 0:
            # Hari ini
            data = await self.client.get_today()
            if not data:
                await interaction.followup.send(
                    "Gagal mengambil jadwal sholat. Coba lagi nanti ya!",
                    ephemeral=True,
                )
                return
            embed = self._build_embed(data)
            await interaction.followup.send(embed=embed, ephemeral=False)
        else:
            # N hari ke depan
            results = await self.client.get_range(days)
            if not results:
                await interaction.followup.send(
                    "Gagal mengambil jadwal sholat. Coba lagi nanti ya!",
                    ephemeral=True,
                )
                return

            # Kirim beberapa embed (max 5 per message, sisanya followup)
            batch_size = 5
            for i in range(0, len(results), batch_size):
                batch = results[i:i + batch_size]
                embeds = [self._build_embed(d) for d in batch]
                if i == 0:
                    await interaction.followup.send(embeds=embeds, ephemeral=False)
                else:
                    await interaction.followup.send(embeds=embeds, ephemeral=False)
                if i + batch_size < len(results):
                    import asyncio
                    await asyncio.sleep(0.5)

    @app_commands.command(name="sholat-kiblat", description="Lihat arah kiblat dari kota kamu")
    async def sholat_qibla(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not self.client:
            await interaction.followup.send("Sholat client belum terkonfigurasi.", ephemeral=True)
            return

        qibla = await self.client.get_qibla()
        if not qibla:
            await interaction.followup.send(
                "Gagal mengambil arah kiblat. Pastikan SHOLAT_LAT & SHOLAT_LNG sudah diisi di `.env`!",
                ephemeral=True,
            )
            return

        direction = qibla.get("direction", 0)
        lat = qibla.get("latitude", 0)
        lng = qibla.get("longitude", 0)

        # Compass visual (sederhana)
        dirs = ["Utara", "Timur Laut", "Timur", "Tenggara", "Selatan", "Barat Daya", "Barat", "Barat Laut"]
        idx = round(direction / 45) % 8
        compass = dirs[idx]

        embed = discord.Embed(
            title="🕌 Arah Kiblat",
            color=discord.Color.teal(),
        )
        embed.description = (
            f"📍 Koordinat: `{lat:.4f}`, `{lng:.4f}`\n"
            f"🧭 Arah: **{direction:.1f}°** dari Utara ({compass})\n\n"
            f"Dari lokasi kamu, arah kiblat menghadap ke **{compass}**."
        )
        embed.set_footer(text="📡 Sumber: AlAdhan API")

        await interaction.followup.send(embed=embed, ephemeral=False)

    @app_commands.command(name="sholat-status", description="Cek konfigurasi sholat saat ini")
    async def sholat_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not self.client:
            await interaction.followup.send("Sholat client belum terkonfigurasi.", ephemeral=True)
            return

        config = self._get_config()
        enabled = self.client.enabled
        channel_id = config.get("channel_id", 0)
        role_id = config.get("role_id", 0)
        city_name = self.client.city_name or config.get("city_name", "Belum diatur")
        method = self.client.method

        method_names = {
            1: "Muslim World League (MWL)",
            2: "Islamic Society of North America (ISNA)",
            3: "Egyptian General Authority",
            5: "University of Islamic Sciences, Karachi",
            8: "Gulf Region (Kemenag)",
            11: "Singapore",
        }

        channel_mention = f"<#{channel_id}>" if channel_id else "Belum diatur"
        role_mention = f"<@&{role_id}>" if role_id else "Tidak ada"

        embed = discord.Embed(
            title="🕌 Konfigurasi Sholat",
            color=discord.Color.teal(),
        )
        fields = [
            ("📍 Kota", city_name, True),
            ("🧮 Method", method_names.get(method, f"Method #{method}"), True),
            ("📢 Channel Reminder", channel_mention, True),
            ("🔔 Role Mention", role_mention, True),
            ("⏱️ Reminder", f"{self.client.settings.SHOLAT_REMINDER_MINUTES} menit sebelum sholat", True),
            ("✅ Status", "Aktif" if enabled else "Nonaktif", True),
        ]
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Admin commands ---

    @app_commands.command(name="sholat-set-channel", description="Set channel untuk auto-reminder sholat (admin)")
    @app_commands.describe(channel="Channel untuk reminder sholat")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sholat_set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)

        config = self._get_config()
        config["channel_id"] = channel.id
        config["enabled"] = True
        self._save_config(config)

        await interaction.followup.send(
            f"Oke! Reminder sholat akan dikirim ke {channel.mention}. "
            "Jangan lupa assign role-nya ya! (￣▽￣*)ゞ",
            ephemeral=True,
        )

    @app_commands.command(name="sholat-set-role", description="Set role untuk mention di reminder sholat (admin)")
    @app_commands.describe(role="Role untuk di-mention saat reminder")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sholat_set_role(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)

        config = self._get_config()
        config["role_id"] = role.id
        self._save_config(config)

        await interaction.followup.send(
            f"Role {role.mention} akan di-mention setiap reminder sholat. "
            "User bisa assign role ini ke diri sendiri untuk dapat notifikasi! (｡•̀ᴗ-)✧",
            ephemeral=True,
        )

    @app_commands.command(name="sholat-set-city", description="Set kota untuk jadwal sholat (admin)")
    @app_commands.describe(city="Nama kota (contoh: Jakarta, Bandung, Surabaya)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sholat_set_city(self, interaction: discord.Interaction, city: str):
        await interaction.response.defer(ephemeral=True)

        if not self.client:
            await interaction.followup.send("Sholat client belum terkonfigurasi.", ephemeral=True)
            return

        # Cari kota di myQuran
        results = await self.client.search_city(city)
        if not results:
            await interaction.followup.send(
                f"Kota **{city}** nggak ditemukan di myQuran. "
                "Coba pakai nama lengkap (contoh: `Kota Jakarta`, `Kabupaten Bandung`)",
                ephemeral=True,
            )
            return

        if len(results) == 1:
            selected = results[0]
        else:
            # multiple results — show first 5
            options = results[:5]
            desc = "\n".join(f"• **{r['name']}**" for r in options)
            await interaction.followup.send(
                f"Ketemu beberapa kota! Pilih salah satu:\n\n{desc}\n\n"
                "Ketik nama kota yang tepat ya!",
                ephemeral=True,
            )
            return

        # Update config
        config = self._get_config()
        config["city_id"] = selected["id"]
        config["city_name"] = selected["name"]
        self._save_config(config)

        # Update runtime
        self.client.city_id = selected["id"]
        self.client.city_name = selected["name"]
        # Clear cache
        self.client._cache.clear()
        self.client._cache_date = None

        await interaction.followup.send(
            f"Kota diatur ke **{selected['name']}**. "
            "Jadwal sholat akan menggunakan data kota ini. (￣ω￣;)",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Sholat(bot))
