# Changelog - Nova Discord AI Bot

All notable changes to this project will be documented in this file.

---

## [1.4.0] - 2026-09-02

### ✨ Added
- **Refactored Architecture**: Extracted `MessageHandler` + helpers into `handlers/` package (`message_handler.py`, `message_cache.py`, `attachment_processor.py`, `fact_extractor.py`). `main.py` shrunk from 439 → 124 lines.
- **Real Chat History → Gemini**: `MessageHandler` and `/ask` slash now pass actual session history (last 20 messages) to Gemini chat-mode. Previously `history=None` always.
- **Audit Logger Lock**: `AuditLogger` now async with `asyncio.Lock` + `asyncio.to_thread` for writes. 22 call sites updated to `await`. Race-free concurrent appends.
- **RAG Nugget Dedup**: `RagStore.save()` now SHA1-hashes normalized fact, scans last 1000 lines, skips duplicates. Returns bool. Stored nuggets include `fact_hash` field.
- **Weekly History Cleanup**: `scheduled_jobs.prune_loop` now triggers `run_cleanup_history` on Sundays at 04:00 (was defined but never scheduled).
- **Prefix SoT**: `BOT_PREFIX` env var added to `.env` / `.env.example` / `config/settings.py`. `core/bot.py` reads env first, falls back to `config/prefixes.json`. README updated.

### 🔒 Security
- **`.env` Rotated**: Old secrets (Discord, 5× Gemini, Groq, Tavily, GitHub, Browserless) archived to `secrets/.env.archive`. Live `.env` replaced with placeholders. **Treat old values as compromised** — rotate immediately at each provider dashboard.
- **`.gitignore` Hardened**: Added `.env.*` (with `!.env.example` exception), `secrets/`. Defense-in-depth in case secrets/ dir is ever created in-tree.

### 🐛 Fixed
- `audit_logger.log()` was synchronous with no lock — race condition under concurrent writes from `on_message` + `on_presence_update`. Now async + locked.
- `compaction_engine` audit logging moved from inline main.py call to inside the engine itself (was orphan after refactor).
- `github_backup.backup()` audit logging now uses `loop.create_task()` to schedule async log without blocking sync git subprocess.

### ⚠️ Migration Notes
- All `audit_logger.log_*()` callers must now `await`. Existing callers in `cogs/slash_commands.py`, `memory/scheduled_jobs.py`, `core/event_handler.py`, `handlers/message_handler.py`, `main.py` updated.
- `rag_store.save()` now returns `True/False` (was always implicit `None`). Callers don't check return — idempotent, safe.
- `.env` is invalid until user fills rotated values. Bot will fail at startup with placeholder `ROTATE_AND_PASTE_HERE`.

---

## [1.3.0] - 2026-09-01

### ✨ Added
- **VLM (Vision Language Model) Support**:
  - Direct image attachment analysis in Discord chat.
  - Added `generate_with_images()` method in `GeminiClient` supporting inline multimodal data.
  - Added `fetch_image()` and `screenshot_page()` methods in `BrowserlessClient`.
  - Added `analyze_image` and `screenshot_page` tools in `ToolExecutor`.
  - Added `/analyze` slash command for analyzing image URLs.
  - Added `/screenshot` slash command for webpage visual analysis.
  - Updated `personality.txt` with VLM handling instructions.

- **Auto-Mention System**:
  - Presence tracking integration via `on_presence_update`.
  - Created `MentionStore` to manage user opt-in preferences and rate limits (10m, 1h, 1d).
  - Added slash commands `/optin`, `/optout`, `/mystatus`.
  - AI-generated welcome messages via Gemini when users come online.
  - `WELCOME_CHANNEL_ID` and `WELCOME_ENABLED` settings.

- **Documentation**:
  - Added comprehensive `README.md`.
  - Added `CHANGELOG.md`.
  - Added `flowchart.md` with 10 detailed Mermaid diagrams.

### 🐛 Fixed
- Fixed `github_backup.py` repo initialization handling 3 edge cases (missing `.git`, empty repository, incorrect branch name).
- Fixed `discord.Color.cyan()` deprecation warning by changing to `discord.Color.teal()`.
- Fixed missing `await` on `rag_store.clean_expired()`.

---

## [1.2.0] - 2026-08-31

### ✨ Added
- **Browserless Integration**:
  - `BrowserlessClient` for webpage content extraction.
  - `fetch_webpage` tool in `ToolExecutor`.
  - Security protections: HTML sanitization, injection pattern filtering, IP safety validation.
  - Automatic URL detection in incoming messages.

- **Audit & Monitoring**:
  - `AuditLogger` writing structured logs to `data/audit/audit.jsonl`.
  - Deleted & edited message caching and audit logging.
  - Tool call execution and result logging.
  - Slash commands `/deleted` and `/audit`.
  - `get_audit_logs` tool for Nova to read her own logs.

- **Presence & Presence Tracking**:
  - Added `get_online_users` tool.
  - Added `intents.members` and `intents.presences` in `core/bot.py`.
  - Added `/send` and `/welcome` slash commands.

---

## [1.1.0] - 2026-08-30

### ✨ Added
- **Personality Enhancements**:
  - Expanded `config/prompts/personality.txt`.
  - Dynamic cat ear emoticons generation guide.
  - Improved tsundere response consistency.

- **Micro-RAG Memory System**:
  - Nugget storage per channel with configurable TTL.
  - Groq-based fast fact extraction and retrieval.
  - Scheduled TTL pruning jobs.

---

## [1.0.0] - Initial Release

### ✨ Added
- Initial release of Nova Discord AI Bot.
- Gemini API integration with key rotation.
- Groq API integration for fast processing.
- Tavily web search tool.
- Session compaction & conversation history management.
- Dynamic rotating presence statuses.
- Basic GitHub automated backup system.
