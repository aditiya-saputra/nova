import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from utils.logger import get_logger
from utils.time_utils import WIB

logger = get_logger(__name__)

SHOLAT_CONFIG_FILE = None  # Will be set from Settings.DATA_DIR


def _get_config_path():
    global SHOLAT_CONFIG_FILE
    if SHOLAT_CONFIG_FILE is None:
        from config.settings import Settings
        SHOLAT_CONFIG_FILE = str(Path(Settings.DATA_DIR) / "sholat_config.json")
    return SHOLAT_CONFIG_FILE


def load_sholat_config() -> dict:
    try:
        with open(_get_config_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_sholat_config(config: dict):
    config_path = _get_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


class ScheduledJobs:
    def __init__(self, settings, audit_logger=None, github_backup=None):
        self.settings = settings
        self.audit_logger = audit_logger
        self.github_backup = github_backup
        self.running = False
        self.last_prune_time = None
        # Sholat reminder
        self.sholat_client = None
        self._reminded_today: set[str] = set()
        self._reminder_date: str | None = None
        self._today_schedule: dict[str, str] | None = None
        self._schedule_fetch_date: str | None = None

    async def start(self):
        if self.running:
            return
        self.running = True
        asyncio.create_task(self.prune_loop())
        logger.info("Scheduled jobs started")

    async def stop(self):
        self.running = False
        logger.info("Scheduled jobs stopped")

    async def prune_loop(self):
        await asyncio.sleep(10)
        last_history_cleanup = None
        while self.running:
            try:
                now = datetime.now()
                if now.hour == 3 and (self.last_prune_time is None or
                    self.last_prune_time.date() < now.date()):
                    await self.run_ttl_prune()
                    self.last_prune_time = now
                if now.weekday() == 6 and now.hour == 4 and (
                    last_history_cleanup is None or last_history_cleanup.date() < now.date()
                ):
                    await self.run_cleanup_history()
                    last_history_cleanup = now

                # Sholat reminder: bandingkan dalam WIB agar cocok dengan API.
                now_wib = datetime.now(WIB)
                await self._check_sholat_reminder(now_wib)
            except Exception as e:
                logger.error(f"Prune loop error: {e}")

            await asyncio.sleep(60)

    async def run_ttl_prune(self):
        logger.info("Starting TTL prune job...")
        files_scanned = 0
        records_deleted = 0

        try:
            memories_dir = os.path.join(self.settings.DATA_DIR, "memories")
            if not os.path.exists(memories_dir):
                logger.info("No memories directory found")
                return

            cutoff_days = int(os.getenv("TTL_PRUNE_DAYS", str(self.settings.NUGGETS_TTL_DAYS)))
            cutoff_time = time.time() - (cutoff_days * 86400)

            for filename in os.listdir(memories_dir):
                if not filename.endswith(".jsonl"):
                    continue

                files_scanned += 1
                filepath = os.path.join(memories_dir, filename)

                try:
                    kept_records = []
                    deleted_count = 0

                    with open(filepath, "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                record = json.loads(line.strip())
                                ts = record.get("created_at") or record.get("timestamp") or 0
                                if isinstance(ts, str):
                                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                                if ts >= cutoff_time:
                                    kept_records.append(record)
                                else:
                                    deleted_count += 1
                            except json.JSONDecodeError:
                                # Line is not valid JSON — keep it as-is to avoid data loss
                                kept_records.append({"_raw": line.strip()})
                            except (KeyError, ValueError, TypeError):
                                # Parsed but invalid timestamp — keep the record
                                kept_records.append(record)

                    if deleted_count > 0:
                        with open(filepath, "w", encoding="utf-8") as f:
                            for record in kept_records:
                                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        records_deleted += deleted_count
                        logger.info(f"Pruned {deleted_count} records from {filename}")

                except Exception as e:
                    logger.error(f"Error pruning {filename}: {e}")

            if self.audit_logger:
                await self.audit_logger.log_ttl_prune(files_scanned, records_deleted)

            logger.info(f"TTL prune complete: {files_scanned} files, {records_deleted} records deleted")

            if self.github_backup and self.github_backup.backup_enabled:
                await self.github_backup.backup("ttl_prune")

        except Exception as e:
            logger.error(f"TTL prune error: {e}")
            if self.audit_logger:
                await self.audit_logger.log_error("ttl_prune", str(e))

    async def run_cleanup_history(self):
        logger.info("Starting history cleanup...")
        cleaned = 0

        try:
            history_dir = os.path.join(self.settings.DATA_DIR, "history")
            if not os.path.exists(history_dir):
                return

            cutoff_days = int(os.getenv("HISTORY_CLEANUP_DAYS", "7"))
            cutoff_time = time.time() - (cutoff_days * 86400)

            for filename in os.listdir(history_dir):
                if not filename.endswith(".jsonl"):
                    continue

                filepath = os.path.join(history_dir, filename)

                try:
                    kept_lines = []
                    file_cleaned = 0
                    with open(filepath, "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                entry = json.loads(line.strip())
                                ts = self._entry_timestamp(entry)
                                if ts is None or ts >= cutoff_time:
                                    kept_lines.append(line)
                                else:
                                    file_cleaned += 1
                            except json.JSONDecodeError:
                                kept_lines.append(line)

                    with open(filepath, "w", encoding="utf-8") as f:
                        f.writelines(kept_lines)
                    cleaned += file_cleaned

                except Exception as e:
                    logger.error(f"Error cleaning {filename}: {e}")

            logger.info(f"History cleanup complete: {cleaned} entries cleaned")

        except Exception as e:
            logger.error(f"History cleanup error: {e}")

    @staticmethod
    def _entry_timestamp(entry):
        ts = entry.get("timestamp")
        if ts is None or ts == "":
            return None
        if isinstance(ts, (int, float)):
            return float(ts)
        if isinstance(ts, str):
            # Terima ISO dengan 'Z' maupun offset; kembalikan None bila tak terparse
            # agar entry tidak terhapus diam-diam (fail-closed: keep).
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except (ValueError, TypeError):
                return None
        return None

    # --- Sholat Reminder ---

    async def _check_sholat_reminder(self, now: datetime):
        """Cek apakah waktunya kirim reminder sholat."""
        if not self.sholat_client or not self.sholat_client.enabled:
            return

        sholat_config = load_sholat_config()
        if not sholat_config.get("enabled") or not sholat_config.get("channel_id"):
            return

        # Reset reminded set jika tanggal berubah
        today_str = now.strftime("%Y-%m-%d")
        if self._reminder_date != today_str:
            self._reminded_today.clear()
            self._today_schedule = None
            self._schedule_fetch_date = None
            self._reminder_date = today_str

        # Fetch jadwal hari ini (cached)
        if self._schedule_fetch_date != today_str:
            self._today_schedule = self.sholat_client.get_today_prayer_times()
            self._schedule_fetch_date = today_str

        if not self._today_schedule:
            return

        # Cek setiap waktu sholat
        reminder_minutes = self.sholat_client.settings.SHOLAT_REMINDER_MINUTES
        from services.sholat_client import REMINDER_PRAYERS, PRAYER_NAMES

        for prayer_key in REMINDER_PRAYERS:
            if prayer_key in self._reminded_today:
                continue

            time_str = self._today_schedule.get(prayer_key, "")
            if not time_str:
                continue

            # Parse waktu sholat ke datetime hari ini
            try:
                h, m = map(int, time_str.split(":"))
                prayer_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            except (ValueError, AttributeError):
                continue

            # Cek apakah kita dalam window reminder (N menit sebelum sholat)
            diff = prayer_dt - now
            diff_minutes = diff.total_seconds() / 60

            if 0 <= diff_minutes <= reminder_minutes:
                await self._send_sholat_reminder(
                    prayer_key, PRAYER_NAMES.get(prayer_key, prayer_key),
                    time_str, reminder_minutes, sholat_config
                )
                self._reminded_today.add(prayer_key)

    async def _send_sholat_reminder(
        self, prayer_key: str, prayer_name: str, time_str: str,
        minutes_left: int, sholat_config: dict
    ):
        """Kirim reminder sholat ke channel yang dikonfigurasi."""
        try:
            # Generate pesan via Gemini
            message = await self.sholat_client.generate_reminder(
                prayer_name, time_str, minutes_left
            )

            # Tambah role mention jika dikonfigurasi — fallback ke SHOLAT_ROLE_ID dari env
            role_id = sholat_config.get("role_id") or getattr(self.sholat_client.settings, "SHOLAT_ROLE_ID", 0)
            if role_id:
                message = f"<@&{role_id}> {message}"

            channel_id = sholat_config.get("channel_id")
            if not channel_id:
                return

            # Kirim via bot
            bot = getattr(self.sholat_client, "_bot", None)
            if not bot:
                logger.warning("Bot reference not set on sholat_client — cannot send reminder")
                return

            channel = bot.get_channel(channel_id)
            if not channel:
                logger.warning(f"Sholat reminder channel {channel_id} not found")
                return

            await channel.send(message)
            logger.info(f"Sholat reminder sent: {prayer_name} to #{channel.name}")

        except Exception as e:
            logger.error(f"Failed to send sholat reminder: {e}")

    def get_status(self):
        return {
            "running": self.running,
            "last_prune": self.last_prune_time.isoformat() if self.last_prune_time else None,
            "next_prune": self._get_next_prune_time()
        }

    def _get_next_prune_time(self):
        now = datetime.now(WIB)
        next_prune = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if next_prune <= now:
            next_prune += timedelta(days=1)
        return next_prune.isoformat()
