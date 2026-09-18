import asyncio
import json
import aiohttp
from pathlib import Path
from datetime import datetime, timedelta, timezone
from utils.logger import get_logger
from utils.time_utils import WIB

logger = get_logger(__name__)

MYQURAN_BASE = "https://api.myquran.com/v3"
ALADHAN_BASE = "https://api.aladhan.com/v1"

# Nama sholat untuk reminder (keys -> display name)
PRAYER_NAMES = {
    "imsak": "Imsak",
    "subuh": "Subuh",
    "dhuha": "Dhuha",
    "dzuhur": "Dzuhur",
    "ashar": "Ashar",
    "maghrib": "Maghrib",
    "isya": "Isya",
}

# Nama sholat yang di-reminder (skip terbit/sunrise)
REMINDER_PRAYERS = ["imsak", "subuh", "dzuhur", "ashar", "maghrib", "isya"]


class SholatClient:
    """Client untuk jadwal sholat — myQuran (primary) + AlAdhan (fallback)."""

    def __init__(self, settings, gemini_client=None):
        self.settings = settings
        self.gemini = gemini_client
        self.city_id = getattr(settings, "SHOLAT_CITY_ID", "")
        self.city_name = getattr(settings, "SHOLAT_CITY_NAME", "")
        self.lat = getattr(settings, "SHOLAT_LAT", 0.0)
        self.lng = getattr(settings, "SHOLAT_LNG", 0.0)
        self.method = getattr(settings, "SHOLAT_METHOD", 8)
        self.timezone = getattr(settings, "SHOLAT_TIMEZONE", "Asia/Jakarta")
        self.enabled = getattr(settings, "SHOLAT_ENABLED", False)
        self._session: aiohttp.ClientSession | None = None
        self._personality: str | None = None
        # Cache: {date_str: normalized_data}
        self._cache: dict[str, dict] = {}
        self._cache_date: str | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def aclose(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _load_personality(self) -> str:
        if self._personality is not None:
            return self._personality
        personality_path = Path(__file__).resolve().parent.parent / "config" / "prompts" / "personality.txt"
        try:
            self._personality = personality_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("personality.txt not found — AI reminder disabled")
            self._personality = ""
        return self._personality

    async def _request(self, url: str) -> dict | None:
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"Sholat API {resp.status}: {url}")
                    return None
                return await resp.json()
        except Exception as e:
            logger.error(f"Sholat API error: {e}")
            return None

    # --- myQuran API ---

    async def _myquran_today(self) -> dict | None:
        if not self.city_id:
            return None
        url = f"{MYQURAN_BASE}/sholat/jadwal/{self.city_id}/today?tz={self.timezone}"
        data = await self._request(url)
        if not data or not data.get("status"):
            return None
        return data.get("data")

    async def _myquran_date(self, date_str: str) -> dict | None:
        if not self.city_id:
            return None
        url = f"{MYQURAN_BASE}/sholat/jadwal/{self.city_id}/{date_str}?tz={self.timezone}"
        data = await self._request(url)
        if not data or not data.get("status"):
            return None
        return data.get("data")

    def _normalize_myquran(self, raw: dict, date_str: str) -> dict | None:
        jadwal = raw.get("jadwal", {})
        day_data = jadwal.get(date_str)
        if not day_data:
            # coba key pertama
            for k, v in jadwal.items():
                day_data = v
                date_str = k
                break
        if not day_data:
            return None
        return {
            "city": raw.get("kabko", self.city_name),
            "province": raw.get("prov", ""),
            "times": {
                "imsak": day_data.get("imsak", ""),
                "subuh": day_data.get("subuh", ""),
                "terbit": day_data.get("terbit", ""),
                "dhuha": day_data.get("dhuha", ""),
                "dzuhur": day_data.get("dzuhur", ""),
                "ashar": day_data.get("ashar", ""),
                "maghrib": day_data.get("maghrib", ""),
                "isya": day_data.get("isya", ""),
            },
            "date": date_str,
            "source": "myquran",
        }

    # --- AlAdhan API (fallback) ---

    async def _aladhan_date(self, date_str: str) -> dict | None:
        url = (
            f"{ALADHAN_BASE}/timings/{date_str}"
            f"?latitude={self.lat}&longitude={self.lng}&method={self.method}"
        )
        data = await self._request(url)
        if not data or data.get("code") != 200:
            return None
        return data.get("data")

    def _normalize_aladhan(self, raw: dict, date_str: str) -> dict | None:
        timings = raw.get("timings", {})
        date_info = raw.get("date", {})
        hijri = date_info.get("hijri", {})
        hijri_str = ""
        if hijri:
            h_day = hijri.get("day", "")
            h_month = hijri.get("month", {})
            h_month_en = h_month.get("en", "") if isinstance(h_month, dict) else ""
            h_year = hijri.get("year", "")
            hijri_str = f"{h_day} {h_month_en} {h_year} H".strip()

        # Parse HH:MM — AlAdhan bisa return "HH:MM (timezone)" atau "HH:MM"
        def _clean_time(t: str) -> str:
            return t.split("(")[0].strip() if t else ""

        return {
            "city": self.city_name or "Lokasi Anda",
            "province": "",
            "times": {
                "imsak": _clean_time(timings.get("Imsak", "")),
                "subuh": _clean_time(timings.get("Fajr", "")),
                "terbit": _clean_time(timings.get("Sunrise", "")),
                "dhuha": "",
                "dzuhur": _clean_time(timings.get("Dhuhr", "")),
                "ashar": _clean_time(timings.get("Asr", "")),
                "maghrib": _clean_time(timings.get("Maghrib", "")),
                "isya": _clean_time(timings.get("Isha", "")),
            },
            "date": date_str,
            "hijri": hijri_str,
            "source": "aladhan",
        }

    # --- Public API ---

    async def get_today(self) -> dict | None:
        today = datetime.now(WIB).strftime("%Y-%m-%d")
        if self._cache_date == today and "today" in self._cache:
            return self._cache["today"]

        # Coba myQuran dulu
        raw = await self._myquran_today()
        if raw:
            result = self._normalize_myquran(raw, today)
            if result:
                self._cache["today"] = result
                self._cache_date = today
                return result

        # Fallback AlAdhan
        raw = await self._aladhan_date(today)
        if raw:
            result = self._normalize_aladhan(raw, today)
            if result:
                self._cache["today"] = result
                self._cache_date = today
                return result

        logger.error("Failed to fetch prayer times from both APIs")
        return None

    async def get_date(self, date_str: str) -> dict | None:
        """Ambil jadwal untuk tanggal tertentu (YYYY-MM-DD)."""
        cache_key = f"date_{date_str}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        raw = await self._myquran_date(date_str)
        if raw:
            result = self._normalize_myquran(raw, date_str)
            if result:
                self._cache[cache_key] = result
                return result

        raw = await self._aladhan_date(date_str)
        if raw:
            result = self._normalize_aladhan(raw, date_str)
            if result:
                self._cache[cache_key] = result
                return result

        return None

    async def get_range(self, days: int = 15) -> list[dict]:
        """Ambil jadwal untuk N hari ke depan."""
        results = []
        today = datetime.now(WIB)
        for i in range(days):
            d = today + timedelta(days=i)
            date_str = d.strftime("%Y-%m-%d")
            data = await self.get_date(date_str)
            if data:
                results.append(data)
            # Rate limit: jeda kecil antar request
            if i < days - 1:
                await asyncio.sleep(0.3)
        return results

    async def get_qibla(self) -> dict | None:
        """Arah kiblat dari koordinat kota."""
        if not self.lat or not self.lng:
            return None
        url = f"{ALADHAN_BASE}/qibla/{self.lat}/{self.lng}"
        data = await self._request(url)
        if not data or data.get("code") != 200:
            return None
        return data.get("data")

    async def search_city(self, query: str) -> list[dict]:
        """Cari kota di myQuran. Returns list of {id, name}."""
        url = f"{MYQURAN_BASE}/sholat/kabkota/cari/{query}"
        data = await self._request(url)
        if not data or not data.get("status"):
            return []
        return [{"id": item["id"], "name": item.get("lokasi", "")} for item in data.get("data", [])]

    def get_today_prayer_times(self) -> dict[str, str] | None:
        """Ambil waktu sholat hari ini dari cache (sync). Untuk scheduled_jobs."""
        today = datetime.now(WIB).strftime("%Y-%m-%d")
        cached = self._cache.get("today")
        if cached and cached.get("date") == today:
            # Return copy agar tidak ada data race dengan async writes.
            times = cached.get("times")
            return dict(times) if times else None
        return None

    # --- AI Reminder Generation ---

    async def generate_reminder(self, prayer_name: str, time_str: str, minutes_left: int) -> str:
        """Generate pesan reminder tsundere via Gemini. Fallback ke template statis."""
        if not self.gemini or not self.gemini.keys:
            return self._fallback_message(prayer_name, time_str, minutes_left)

        personality = self._load_personality()
        if not personality:
            return self._fallback_message(prayer_name, time_str, minutes_left)

        system_prompt = personality + "\n\n--- SHOLAT REMINDER ---\n"
        user_prompt = (
            f"Buat pesan pengingat sholat yang singkat (2-4 kalimat) dalam gaya Nova tsundere.\n\n"
            f"Info:\n"
            f"- Waktu sholat: {prayer_name} jam {time_str} WIB\n"
            f"- Sisa waktu: {minutes_left} menit lagi\n"
            f"- Kota: {self.city_name}\n\n"
            f"Aturan:\n"
            f"- Jangan panggil tool — langsung jawab saja\n"
            f"- Sertakan emoticon sholat (🕌) atau emoticon kuping kucing\n"
            f"- Tetap in-character sebagai Nova tsundere\n"
            f"- Pesan harus MEMANGGIL user untuk sholat, bukan hanya info\n"
            f"- Jangan pakai role mention, cukup pesan biasa\n"
        )

        try:
            result = await asyncio.wait_for(
                self.gemini.generate(user_prompt, system_instruction=system_prompt),
                timeout=15,
            )
            if result and result.strip():
                return result.strip()
        except asyncio.TimeoutError:
            logger.warning("Gemini reminder generation timeout — using fallback")
        except Exception as e:
            logger.error(f"Gemini reminder generation failed: {e}")

        return self._fallback_message(prayer_name, time_str, minutes_left)

    def _fallback_message(self, prayer_name: str, time_str: str, minutes_left: int) -> str:
        return (
            f"🕌 {self.city_name} — Waktu **{prayer_name}** tinggal **{minutes_left} menit** lagi! "
            f"Jam **{time_str}** WIB.\n"
            f"Jangan lupa sholat ya! (￣ω￣;)"
        )
