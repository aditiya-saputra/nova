import asyncio
import os
import json
import time
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)


class ScheduledJobs:
    def __init__(self, settings, audit_logger=None, github_backup=None):
        self.settings = settings
        self.audit_logger = audit_logger
        self.github_backup = github_backup
        self.running = False
        self.last_prune_time = None

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

            cutoff_days = int(os.getenv("TTL_PRUNE_DAYS", "30"))
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
                                    ts = datetime.fromisoformat(ts).timestamp()
                                if ts >= cutoff_time:
                                    kept_records.append(record)
                                else:
                                    deleted_count += 1
                            except (json.JSONDecodeError, KeyError, ValueError):
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
        try:
            return datetime.fromisoformat(ts).timestamp()
        except (ValueError, TypeError):
            return None

    def get_status(self):
        return {
            "running": self.running,
            "last_prune": self.last_prune_time.isoformat() if self.last_prune_time else None,
            "next_prune": self._get_next_prune_time()
        }

    def _get_next_prune_time(self):
        now = datetime.now()
        next_prune = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if next_prune <= now:
            next_prune += timedelta(days=1)
        return next_prune.isoformat()
