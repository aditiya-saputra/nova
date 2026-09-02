import json
import os
import time
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)

RATE_LIMITS = {
    "10m": 600,
    "1h": 3600,
    "1d": 86400,
    "off": 0,
}


class MentionStore:
    def __init__(self, settings):
        self.settings = settings
        self.data_dir = settings.DATA_DIR
        self.mentions_dir = self.data_dir / "mentions"
        self.mentions_dir.mkdir(parents=True, exist_ok=True)
        self.preferences_file = self.mentions_dir / "preferences.json"
        self.preferences = self._load_preferences()

    def _load_preferences(self):
        if self.preferences_file.exists():
            try:
                with open(self.preferences_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load mention preferences: {e}")
        return {}

    def _save_preferences(self):
        try:
            with open(self.preferences_file, "w", encoding="utf-8") as f:
                json.dump(self.preferences, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save mention preferences: {e}")

    def get_user_pref(self, user_id):
        user_id = str(user_id)
        if user_id not in self.preferences:
            self.preferences[user_id] = {
                "opt_in": False,
                "rate_limit": "1h",
                "last_mention": 0,
            }
        return self.preferences[user_id]

    def opt_in(self, user_id, rate_limit="1h"):
        user_id = str(user_id)
        pref = self.get_user_pref(user_id)
        pref["opt_in"] = True
        if rate_limit in RATE_LIMITS:
            pref["rate_limit"] = rate_limit
        self._save_preferences()
        return pref

    def opt_out(self, user_id):
        user_id = str(user_id)
        pref = self.get_user_pref(user_id)
        pref["opt_in"] = False
        self._save_preferences()
        return pref

    def set_rate_limit(self, user_id, rate_limit):
        user_id = str(user_id)
        if rate_limit not in RATE_LIMITS:
            return None
        pref = self.get_user_pref(user_id)
        pref["rate_limit"] = rate_limit
        self._save_preferences()
        return pref

    def can_mention(self, user_id):
        user_id = str(user_id)
        pref = self.get_user_pref(user_id)

        if not pref["opt_in"]:
            return False

        rate_limit = RATE_LIMITS.get(pref["rate_limit"], 0)
        if rate_limit == 0:
            return False

        last = pref.get("last_mention", 0)
        if time.time() - last < rate_limit:
            return False

        return True

    def record_mention(self, user_id):
        user_id = str(user_id)
        pref = self.get_user_pref(user_id)
        pref["last_mention"] = time.time()
        self._save_preferences()

    def get_all_opted_in(self):
        return [
            int(uid)
            for uid, pref in self.preferences.items()
            if pref.get("opt_in", False)
        ]

    def get_stats(self):
        total = len(self.preferences)
        opted_in = sum(1 for p in self.preferences.values() if p.get("opt_in", False))
        return {
            "total_users": total,
            "opted_in": opted_in,
            "opted_out": total - opted_in,
        }
