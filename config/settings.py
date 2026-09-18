import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _safe_int(val, default):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _safe_float(val, default):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


class Settings:
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "data"
    HISTORY_DIR = DATA_DIR / "history"
    MEMORIES_DIR = DATA_DIR / "memories"
    ARCHIVES_DIR = DATA_DIR / "archives"
    PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    MEMORIES_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)

    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

    GEMINI_API_KEYS = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
    GEMINI_FALLBACK_MODELS = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-flash-latest,gemini-flash-lite-latest").split(",") if m.strip()]
    GEMINI_CONTEXT_LIMIT = _safe_int(os.getenv("GEMINI_CONTEXT_LIMIT"), 1048576)
    GEMINI_OUTPUT_LIMIT = _safe_int(os.getenv("GEMINI_OUTPUT_LIMIT"), 65536)

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL_HEAVY = os.getenv("GROQ_MODEL_HEAVY", "openai/gpt-oss-120b")
    GROQ_MODEL_FAST = os.getenv("GROQ_MODEL_FAST", "openai/gpt-oss-20b")

    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

    BROWSERLESS_URL = os.getenv("BROWSERLESS_URL", "")
    BROWSERLESS_TOKEN = os.getenv("BROWSERLESS_TOKEN", "")

    HYPERBROWSER_API_KEY = os.getenv("HYPERBROWSER_API_KEY", "")
    # hyperbrowser | browserless | auto (default: hyperbrowser dulu, fallback browserless)
    FETCH_PROVIDER = os.getenv("FETCH_PROVIDER", "auto").lower()

    COMPACTION_THRESHOLD = _safe_float(os.getenv("COMPACTION_THRESHOLD"), 0.80)
    COMPACTION_TARGET = _safe_float(os.getenv("COMPACTION_TARGET"), 0.20)

    NUGGETS_TTL_DAYS = _safe_int(os.getenv("NUGGETS_TTL_DAYS"), 3)
    NUGGETS_TOP_K = _safe_int(os.getenv("NUGGETS_TOP_K"), 5)

    BOT_PREFIXES = [p.strip() for p in os.getenv("BOT_PREFIX", "").split(",") if p.strip() and p.strip() not in (",",)]

    BOT_REPLY_MENTION = os.getenv("BOT_REPLY_MENTION", "true").lower() == "true"
    PROCESS_REPLY_WITHOUT_MENTION = os.getenv("PROCESS_REPLY_WITHOUT_MENTION", "false").lower() == "true"

    SESSION_TIMEOUT = _safe_int(os.getenv("SESSION_TIMEOUT"), 3600)

    WELCOME_ENABLED = os.getenv("WELCOME_ENABLED", "false").lower() == "true"
    WELCOME_CHANNEL_ID = _safe_int(os.getenv("WELCOME_CHANNEL_ID"), 0)

    BACKUP_ENABLED = os.getenv("BACKUP_ENABLED", "false").lower() == "true"
    # Kanonis: GITHUB_BACKUP_REPO. Terima alias lama GITHUB_REPO agar tidak breaking.
    GITHUB_BACKUP_REPO = os.getenv("GITHUB_BACKUP_REPO", "") or os.getenv("GITHUB_REPO", "")
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

    # Sholat (Jadwal Sholat Auto-Reminder)
    SHOLAT_ENABLED = os.getenv("SHOLAT_ENABLED", "false").lower() == "true"
    SHOLAT_CITY_ID = os.getenv("SHOLAT_CITY_ID", "")
    SHOLAT_CITY_NAME = os.getenv("SHOLAT_CITY_NAME", "")
    SHOLAT_LAT = _safe_float(os.getenv("SHOLAT_LAT"), 0.0)
    SHOLAT_LNG = _safe_float(os.getenv("SHOLAT_LNG"), 0.0)
    SHOLAT_METHOD = _safe_int(os.getenv("SHOLAT_METHOD"), 8)
    SHOLAT_TIMEZONE = os.getenv("SHOLAT_TIMEZONE", "Asia/Jakarta")
    SHOLAT_ROLE_ID = _safe_int(os.getenv("SHOLAT_ROLE_ID"), 0)
    SHOLAT_REMINDER_MINUTES = _safe_int(os.getenv("SHOLAT_REMINDER_MINUTES"), 10)
