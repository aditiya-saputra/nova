import json
import os
import asyncio
import time
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)


class AuditLogger:
    def __init__(self, settings):
        self.settings = settings
        self.audit_dir = os.path.join(settings.DATA_DIR, "audit")
        os.makedirs(self.audit_dir, exist_ok=True)
        self.audit_file = os.path.join(self.audit_dir, "audit.jsonl")
        self._lock = asyncio.Lock()

    def _write_entry(self, entry):
        try:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Audit log error: {e}")

    async def log(self, event_type, data):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "data": data
        }
        async with self._lock:
            await asyncio.to_thread(self._write_entry, entry)

    async def log_message(self, user_id, user_name, channel_id, trigger_type, content):
        await self.log("message_received", {
            "user_id": user_id,
            "user_name": user_name,
            "channel_id": channel_id,
            "trigger_type": trigger_type,
            "content_length": len(content)
        })

    async def log_response(self, channel_id, response_length, latency, tokens):
        await self.log("response_sent", {
            "channel_id": channel_id,
            "response_length": response_length,
            "latency": round(latency, 2),
            "tokens": tokens
        })

    async def log_compaction(self, channel_key, usage_before, usage_after):
        await self.log("compaction", {
            "channel_key": channel_key,
            "usage_before": round(usage_before, 4),
            "usage_after": round(usage_after, 4)
        })

    async def log_rag_extract(self, channel_id, facts_count):
        await self.log("rag_extract", {
            "channel_id": channel_id,
            "facts_count": facts_count
        })

    async def log_rag_retrieve(self, channel_id, nuggets_loaded, nuggets_selected):
        await self.log("rag_retrieve", {
            "channel_id": channel_id,
            "nuggets_loaded": nuggets_loaded,
            "nuggets_selected": nuggets_selected
        })

    async def log_backup(self, status, message):
        await self.log("github_backup", {
            "status": status,
            "message": message
        })

    async def log_ttl_prune(self, files_scanned, records_deleted):
        await self.log("ttl_prune", {
            "files_scanned": files_scanned,
            "records_deleted": records_deleted
        })

    async def log_error(self, error_type, error_message, context=None):
        await self.log("error", {
            "error_type": error_type,
            "error_message": str(error_message),
            "context": context
        })

    async def log_startup(self, bot_name, guilds, gemini_keys):
        await self.log("bot_startup", {
            "bot_name": bot_name,
            "guilds": guilds,
            "gemini_keys": gemini_keys
        })

    async def log_shutdown(self, reason="normal"):
        await self.log("bot_shutdown", {
            "reason": reason
        })

    def get_recent_logs(self, limit=50):
        logs = []
        try:
            if os.path.exists(self.audit_file):
                with open(self.audit_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    for line in lines[-limit:]:
                        try:
                            logs.append(json.loads(line.strip()))
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"Error reading audit logs: {e}")
        return logs

    def get_logs_by_type(self, event_type, limit=50):
        logs = []
        try:
            if os.path.exists(self.audit_file):
                with open(self.audit_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            if entry.get("event") == event_type:
                                logs.append(entry)
                                if len(logs) >= limit:
                                    break
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"Error reading audit logs: {e}")
        return logs

    async def aget_recent_logs(self, limit=50):
        # File read bisa besar (seluruh audit.jsonl) — jangan block event loop.
        return await asyncio.to_thread(self.get_recent_logs, limit)

    async def aget_logs_by_type(self, event_type, limit=50):
        return await asyncio.to_thread(self.get_logs_by_type, event_type, limit)

    def clear_old_logs(self, days=30):
        cutoff = time.time() - (days * 86400)
        cleared = 0
        try:
            if os.path.exists(self.audit_file):
                temp_file = self.audit_file + ".tmp"
                with open(self.audit_file, "r", encoding="utf-8") as f, \
                     open(temp_file, "w", encoding="utf-8") as temp:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
                            if ts >= cutoff:
                                temp.write(line)
                            else:
                                cleared += 1
                        except (json.JSONDecodeError, KeyError):
                            temp.write(line)
                os.replace(temp_file, self.audit_file)
        except Exception as e:
            logger.error(f"Error clearing old logs: {e}")
        return cleared
