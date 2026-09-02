import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


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
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    GEMINI_CONTEXT_LIMIT = int(os.getenv("GEMINI_CONTEXT_LIMIT", "1048576"))
    GEMINI_OUTPUT_LIMIT = int(os.getenv("GEMINI_OUTPUT_LIMIT", "65536"))

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL_HEAVY = os.getenv("GROQ_MODEL_HEAVY", "openai/gpt-oss-120b")
    GROQ_MODEL_FAST = os.getenv("GROQ_MODEL_FAST", "openai/gpt-oss-20b")

    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

    BROWSERLESS_URL = os.getenv("BROWSERLESS_URL", "")
    BROWSERLESS_TOKEN = os.getenv("BROWSERLESS_TOKEN", "")

    COMPACTION_THRESHOLD = float(os.getenv("COMPACTION_THRESHOLD", "0.80"))
    COMPACTION_TARGET = float(os.getenv("COMPACTION_TARGET", "0.20"))

    NUGGETS_TTL_DAYS = int(os.getenv("NUGGETS_TTL_DAYS", "3"))
    NUGGETS_TOP_K = int(os.getenv("NUGGETS_TOP_K", "5"))

    BOT_PREFIXES = [p.strip() for p in os.getenv("BOT_PREFIX", "").split(",") if p.strip()]

    BOT_REPLY_MENTION = os.getenv("BOT_REPLY_MENTION", "true").lower() == "true"
    PROCESS_REPLY_WITHOUT_MENTION = os.getenv("PROCESS_REPLY_WITHOUT_MENTION", "false").lower() == "true"

    SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "3600"))

    WELCOME_ENABLED = os.getenv("WELCOME_ENABLED", "false").lower() == "true"
    WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "0"))
