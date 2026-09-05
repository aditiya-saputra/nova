# Changelog - Nova Discord AI Bot

All notable changes to this project will be documented in this file.

---

## [1.7.4] - 2026-09-05

### ✨ Added (command hapus ingatan)
- **Slash command `/forget`** (admin, `manage_messages`): hapus semua memori RAG channel + riwayat percakapan/session + reset tracker anti-repeat. `memory/rag_store.py` mendapat method `delete_channel()`.

### 🌐 Changed (timezone WIB)
- **`utils/time_utils.py`**: helper baru `to_wib()` / `to_wib_iso()` / `format_wib()` berbasis `pytz` (Asia/Jakarta, UTC+7). Penyimpanan internal tetap UTC — konversi hanya di sisi tampilan, jadi logika TTL/expired tidak berubah.
- **Display WIB**: `/recall`, `/deleted`, `/audit`, `/mystatus`, serta "Time:" di system prompt (pesan & `/ask`) kini menampilkan waktu WIB.
- **Fix `/recall`**: timestamp memori dulu selalu "N/A" (membaca field `created_at` yang tidak ada) — kini membaca field `timestamp`.
- **Dependency**: `pytz` ditambahkan ke `requirements.txt`.

### 🔧 Changed (default model Gemini)
- `config/settings.py`: default `GEMINI_MODEL` diubah `gemini-3.6-flash` → `gemini-3-flash-preview`; default `GEMINI_FALLBACK_MODELS` kini `gemini-flash-latest,gemini-flash-lite-latest` (config kosong tidak lagi memakai model thinking-only / nonaktif).

### ⚠️ Migration Notes
- Jalankan `pip install -r requirements.txt` (menambah `pytz`).
- Restart Nova.

---

## [1.7.3] - 2026-09-05

### 🐛 Fixed (bot mengulang jawaban yang sama persis untuk prompt berbeda)
- **Root cause**: tool `get_online_users` di-panggil ulang pada follow-up singkat (mis. "dih ada aku ternyata", "oke cukup 2M sih"), lalu `synthesize_with_tool_result` yang stateless menyusun ulang laporan dari data tool yang sama → output byte-for-byte identik.
- **Anti-repeat gate (`handlers/message_handler.py`)**: jika Gemini memilih tool yang **sama + args sama** dengan tool pada turn sebelumnya DAN pesan user singkat (≤ `SHORT_REACTION_MAX`), tool TIDAK dieksekusi ulang — diganti balasan singkat via `_build_reaction_prompt`.
- **Stateful synthesize (`services/gemini_client.py`)**: `synthesize_with_tool_result` kini menerima `last_assistant` (jawaban sebelumnya) dan instruksi tegas untuk menjawab pesan terbaru, tidak menyalin ulang laporan/format lama, dan tidak mengulang verbatim.
- **Prompt guard (`config/prompts/personality.txt`)**: aturan baru — reaksi singkat tidak boleh memicu tool/format penuh; jangan pernah mengulang pesan persis sama.
- Pelacak `_last_response_text[channel]/_last_tool_calls[channel]` per channel untuk anti-repeat dan grounding synth.

### ⚠️ Migration Notes
- Tidak ada perubahan env. Restart Nova untuk memuat perbaikan.

---

## [1.7.2] - 2026-09-05

### 🐛 Fixed (latensi Gemini & fallback invalid)
- **`gemini-3.6-flash` lambat ~25-28s bahkan untuk prompt pendek** karena model ini **thinking-only** (`thinking: true` di metadata API; `thinking_budget=0` ditolak API dengan 400, budget kecil 32/64 tetap ~27s) — thinking-nya tidak bisa dimatikan. Model utama diganti ke **`gemini-3-flash-preview`** (terverifikasi 1.3-1.8s di probe latensi dengan config bot).
- **Fallback `gemini-3.0-flash` invalid (404 NOT_FOUND)** — bukan model yang tersedia. Rantai fallback diganti ke `gemini-flash-latest,gemini-flash-lite-latest` (terverifikasi tersedia & cepat di probe latensi).

### ⚠️ Migration Notes
- Update `.env` server: `GEMINI_MODEL=gemini-3-flash-preview`, `GEMINI_FALLBACK_MODELS=gemini-flash-latest,gemini-flash-lite-latest`, lalu restart Nova. Cek log startup `Gemini model chain: [...]` untuk konfirmasi rantai model baru.

---

## [1.7.1] - 2026-09-05

### 🔄 Changed (migrasi model Gemini)
- **`gemini-2.5-flash` deprecated** oleh Google (404 NOT_FOUND "no longer available to new users"). Konfigurasi dimigrasi ke `gemini-3.6-flash`:
  - `config/settings.py`: default `GEMINI_MODEL` = `gemini-3.6-flash`; error 404 muncul karena proses lama masih memakai `.env` yang berisi `gemini-2.5-flash`.
  - `.env`: `GEMINI_MODEL=gemini-3.6-flash`, `GEMINI_FALLBACK_MODELS=gemini-3.0-flash` — model deprecated tidak lagi ada di rantai fallback.
  - `.env.example`: `GEMINI_FALLBACK_MODELS=gemini-3.0-flash` (hapus `gemini-2.5-flash`) agar `.env` baru yang disalin dari contoh tidak mengulang bug yang sama.
- **Log rantai model saat startup (`services/gemini_client.py`)**: `GeminiClient.__init__` kini mencatat `Gemini model chain: [...]` sekali saat init — drift config model (mis. model deprecated) langsung terlihat di log, bukan hanya saat API menolak request.

### ⚠️ Migration Notes
- Bot yang sedang berjalan WAJIB di-restart agar memuat `.env` terkini; proses lama yang masih memakai `gemini-2.5-flash` tetap kena 404 sampai restart. Jika deploy di server/salinan lain, samakan nilai `GEMINI_MODEL` dan `GEMINI_FALLBACK_MODELS` di sana juga.

---

## [1.7.0] - 2026-09-04

### ✨ Added (Hyperbrowser provider)
- **`services/hyperbrowser_client.py` baru**: wrapper `AsyncHyperbrowser` (SDK 1.4.1) dengan return-shape sama persis seperti Browserless, reuse SSRF guard + sanitizer, screenshot parser defensif (base64/data-URL/URL/bytes). Terverifikasi live: key valid, fetch README 200 + 2803 char.
- **Fallback provider**: `ToolExecutor._fetch_webpage/_screenshot_page` + slash `/screenshot` coba berurutan via `FETCH_PROVIDER` (`auto` default: hyperbrowser → browserless). `analyze_image` tetap Browserless.
- **Config**: `HYPERBROWSER_API_KEY`, `FETCH_PROVIDER` (`config/settings.py`, `.env.example`, `requirements.txt: hyperbrowser>=1.4.0`).

### 🐛 Fixed (jawaban basi/kosong)
- **Auto-fetch URL (`handlers/message_handler.py`)**: URL di pesan di-fetch paralel (max 2, 4000 char/URL) dalam `gather` dan di-injeksi ke prompt sebagai sumber utama — URL baru tidak lagi dijawab dari RAG lama.
- **Retry kosong**: hasil thinking-only dicoba sekali `generate` polos sebelum fallback; fallback tsundere hanya bila tetap kosong.
- **Scraper JS**: Hyperbrowser `wait_for 5000` + `wait_until networkidle`, Browserless `waitFor 5000` (halaman `0 Total Staff` karena belum render).

### ⚡ Performance (timeout + I/O)
- **Timeout berlapis**: `generate_with_tools` 45s → retry 60s dengan history 20→8; `synthesize`/retry/`/ask` 45s (`handlers/message_handler.py`, `cogs/slash_commands.py`).
- **File I/O non-blocking**: `AuditLogger.aget_recent_logs/aget_logs_by_type`, `RagStore` save/clean/read + `aget_all` via `to_thread`; caller tool + `/deleted`/`/audit`/`/recall` diupdate.

---

## [1.6.2] - 2026-09-04

### 🐛 Fixed (Browserless auth)
- **500 semua request (`services/browserless_client.py`)**: instance `chrome.browserless.io` (openresty, API v1) tidak kenal auth header `Bearer` saja — dibalas 500 untuk URL/token apapun. Endpoint kini sertakan `?token=` (header Bearer tetap dikirim). Terverifikasi: `?token=` → 200 + konten asli (README 8221 bytes).

---

## [1.6.1] - 2026-09-04

### 🐛 Fixed (Discord + Gemini warnings dari server log)
- **DeprecationWarning `message.interaction` (`core/message_router.py`)**: hapus cek `hasattr(message,'interaction')` yang memicu warning tiap pesan di discord.py 2.7 — tersisa `getattr(message,"interaction_metadata",None)` saja.
- **AFC warning (`services/gemini_client.py:generate_with_tools`)**: selalu via `chats.create(history or [])` + `send_message`, tidak lagi `models.generate_content` saat tanpa history (sesuai anjuran SDK).
- **Non-text warning (`_extract_response_text`)**: inspeksi `parts` dulu sebelum sentuh `response.text`; teks digabung hanya bila tidak ada `function_call`.
- **Balasan repr internal (`faa: baca readme` → `parts=[Part(text='', thoughtsignature=...)]`)**: thinking-only (teks kosong + thoughtsignature) kini return `""`, bukan `str(content)`. Guard di `handlers/message_handler.py`: respon kosong → fallback tsundere agar tidak 400 empty message Discord.

---

## [1.6.0] - 2026-09-04

### ⚡ Performance (asyncio fast-response)
- **#1 Paralel I/O (`handlers/message_handler.py`)**: `attachments.analyze` + `_retrieve_facts` + `check_and_compact` kini `asyncio.gather` dalam 1x `typing()` — hemat 1x RTT.
- **#2 Background non-kritis**: helper `_spawn`/`_bg_await` fire-and-forget dengan log error. `log tool_call/tool_result` tidak block `execute`/`synthesize`. Urutan dibalik: reply dulu, baru `_spawn(log_response)`, `_spawn(rag_extract)`, `_spawn(_backup_and_log)`. `handle()` return tanpa nunggu Groq extract / git push.
- **#3 Reuse koneksi**: `GeminiClient._clients` cache `genai.Client` per API key (`services/gemini_client.py`); `BrowserlessClient._get_session/aclose` shared `ClientSession` (`limit=20`, DNS cache 300s) untuk `fetch_content`/`fetch_image`; `AttachmentProcessor` shared session (`limit=10`) + `aclose`. Semua ditutup di `main.py` finally.
- **#4 Non-blocking CPU/IO**: `TokenCounter._encode_cached` `@lru_cache(2048)` (`services/token_counter.py`); `HistoryStore.aappend/aappend_message` via `asyncio.to_thread` (`memory/history_store.py`) dipakai di `message_handler` + `/ask`.
- **#5 Timeout + paralel gambar**: Gemini `generate_with_tools`/`synthesize`/`generate` dibungkus `asyncio.wait_for(timeout=30)` (`handlers/message_handler.py`, `cogs/slash_commands.py`); `AttachmentProcessor.analyze` batasi `MAX_IMAGES_PER_MESSAGE=3` + `gather` download+VLM paralel.
- **Token-count restart fix**: `SessionManager.get_token_count/get_token_usage` kini `hydrate_from_disk` dulu (`memory/session_manager.py`) — cek compaction pertama setelah restart akurat.

### 🧹 Housekeeping
- Hapus `__pycache__`/`*.pyc` + 3 log 0-byte (`data/logs/bot_2026_08_30.log`, `bot_2026_09_02.log`, `bot_2026_09_04.log`). `secrets/*` dipertahankan sesuai pilihan user.

---

## [1.5.0] - 2026-09-04

### ✨ Added
- **Shared RAG helper**: `FactExtractor.retrieve_relevant_facts()` (`handlers/fact_extractor.py`) jadi single source of truth untuk `MessageHandler`, `/ask`, dan `ToolExecutor`. Hapus 3x duplikasi prompt-build + JSON-parse.
- **Double-command guard**: `MessageRouter.is_bot_command()` (`core/message_router.py`) — pesan prefix-command terdaftar (`!clear`, `!ask`, ...) di-skip dari AI handler agar tidak double-reply.
- **Backup env kanonis**: `Settings.BACKUP_ENABLED` / `GITHUB_BACKUP_REPO` (alias lama `GITHUB_REPO` tetap didukung) + `GITHUB_TOKEN` (`config/settings.py`, `memory/github_backup.py`). `.env.example` didokumentasikan.
- **Groq cleanup**: `GroqClient.aclose()` + dipanggil di `main.py` finally.

### 🐛 Fixed (Reliability)
- **Event-loop blocking (`groq`, `tavily`)**: `GroqClient` migrasi `groq.Groq` sync → `AsyncGroq(DefaultAioHttpClient)` (`services/groq_client.py`, per Context7 `/groq/groq-python`). Semua method (`compact`, `extract_facts`, `retrieve_relevant`, `process_search_results`, `synthesize`) kini `async` + `await`. Caller diupdate: `memory/compaction_engine.py`, `handlers/fact_extractor.py`, `handlers/message_handler.py`, `services/tool_executor.py`, `cogs/slash_commands.py`. `TavilyClient.search()` jadi `async` via `asyncio.to_thread` (`services/tavily_client.py`).
- **Dead fallback log (`gemini_client._run_with_fallback`)**: bandingkan ke `primary_model` (`model_chain[0]`) bukan `self.model_name` yang selalu sama — log `Switched to model (fallback)` kini muncul benar (`services/gemini_client.py`).
- **Stub prefix commands (`cogs/ai_commands.py`)**: `!ask`/`!ai` yang tadinya echo kini panggil Gemini + session + RAG + split 1900 char.
- **Command routing (`main.py` + `handlers/message_handler.py`)**: `process_commands` pindah ke `main.py on_message finally` (discord.py best practice per Context7), dihapus dari akhir `MessageHandler.handle`. Pesan command tetap diproses walau AI skip.
- **History race (`memory/history_store.py`)**: tambah `threading.Lock` untuk `append`/`clear`.
- **Naive datetime (`memory/rag_store.py`)**: `utcnow()` → `now(timezone.utc)`, compare aware-vs-aware di `clean_expired`.
- **Timestamp parse (`memory/scheduled_jobs.py`)**: terima ISO `Z`-suffix, `TypeError` → keep (fail-closed) di TTL prune + history cleanup.

### 🐛 Fixed (Security)
- **SSRF DNS-rebinding (`browserless_client`)**: tambah `_is_safe_url_async()` — sync literal check + `loop.getaddrinfo` dan tolak bila ada IP resolve yang `is_private/loopback/link_local/reserved/multicast/unspecified`. `fetch_content`/`fetch_image`/redirect hop kini pakai versi async.
- **`octet` rule mati**: `BLOCKED_RULES` tipe `octet` kini dicek dot-bounded (`10` cocok `10.x` tapi tidak `10evil.com`); tolak userinfo (`user:pass@host`) dan single-label hostname.
- **Redirect handling (`fetch_image`)**: satu `ClientSession` reuse (per Context7 `/aio-libs/aiohttp`), `urljoin` untuk `Location` relatif, dukung `Location`/`URI` header, tidak lagi kirim `Authorization: Bearer` ke host arbitrary + strip saat cross-origin. Hapus pembuatan session baru per hop.
- **Missing dep (`requirements.txt`)**: tambah `aiohttp>=3.9.0` yang diimport `browserless_client` + `attachment_processor` tapi belum terdaftar.

### 📦 Dependencies
- Naikkan pin minimum: `google-genai>=2.22.0` (was `>=2.20.0`), `groq>=1.7.0` (tetap, tapi install lokal masih 1.5.0 — wajib `pip install -U`), `tavily-python>=0.8.1` (was `>=0.8.0`), `python-dotenv>=1.2.3` (was unpinned). Terinstall terverifikasi: `groq 1.7.0`, `google-genai 2.22.0`, `tavily 0.8.1`, `dotenv 1.2.3`, `aiohttp 3.14.3`, `discord.py 2.7.1`, `tiktoken 0.14.0`, `rich 15.0.0`. `AsyncGroq` + `DefaultAioHttpClient` + `genai.Client` + `TavilyClient` import check OK.
- **Docs**: `services/token_counter.py` ditandai aproksimasi tiktoken→Gemini (bukan presisi billing).

### ⚠️ Migration Notes
- Semua pemanggil Groq harus `await` (sync wrapper dihapus). `asyncio.to_thread(groq...)` lama tidak berlaku.
- `HistoryStore.append/clear` kini thread-safe tapi tetap sync — panggil langsung seperti biasa.
- Env backup: pakai `GITHUB_BACKUP_REPO`; `GITHUB_REPO` lama masih dibaca sebagai fallback.
- Struktur file tidak berubah (21 file modified, 0 tambah/hapus/pindah).

---

## [1.4.2] - 2026-09-04

### ✨ Added
- **Model Fallback Routing**: `GeminiClient` now supports automatic model fallback via `GEMINI_FALLBACK_MODELS` config. When the primary model returns a 404 NOT_FOUND error, the client automatically rotates through the fallback list (`model_chain`). All generation methods (`generate`, `chat`, `generate_with_tools`, `synthesize_with_tool_result`, `generate_with_images`) use the shared `_run_with_fallback()` helper.
- **`config/settings.py`**: Added `GEMINI_FALLBACK_MODELS` setting (comma-separated model IDs). Empty by default — no fallback unless configured.

### 🛠 Changed
- **`services/gemini_client.py`**: Refactored error handling into `_is_not_found_error()` and `_run_with_fallback()` helpers. All public methods now delegate to `_run_with_fallback()` instead of duplicating key-rotation + error-handling loops.
- **`.env`**: Added `GEMINI_FALLBACK_MODELS=gemini-3.0-flash,gemini-3.6-flash`. Primary model still `gemini-2.5-flash` (stale; will trigger fallback on next run).
- **`.env.example`**: Added `GEMINI_FALLBACK_MODELS` example line.

---

## [1.4.1] - 2026-09-03

### 🐛 Fixed (Security)
- **SSRF via redirect (`browserless_client.fetch_image`)**: Replaced `allow_redirects=True` with manual hop loop (max 5), validating each `Location` header through `_is_safe_url`. Attacker can no longer pivot public URL → internal IP via 302.
- **SSRF prefix bypass (`browserless_client._is_safe_url`)**: Replaced string-prefix matching (`hostname.startswith('10.')` — `10evil.com` slipped through) with `ipaddress` stdlib checks (`is_private`/`is_loopback`/`is_linkage_local`/`is_reserved`/`is_multicast`/`is_unspecified`) for IP literals + dot-bounded suffix matching for hostnames. Covers IPv4 and IPv6 (RFC1918, ULA, link-local, loopback).
- **Token leak in git remote URL (`github_backup._get_auth_url`)**: Removed inline-credential URL pattern (`https://token@github.com/...`). Token now applied via repo-local `git config http.<host>/.extraheader` + `http.<host>/.token` and redacted from all `subprocess` stdout/stderr via `_safe_run` wrapper. Token no longer exposed in `git remote -v`, error logs, or process listings.

### 🐛 Fixed (Data Integrity)
- **Git branch force-rename clobber (`github_backup.init_repo`)**: Replaced `git branch -M main` (force rename, overwrites remote `main`) with `git branch -m main` (only if current branch differs). Existing remote history no longer destroyed on re-init.
- **Concurrent backup race (`github_backup._backup_sync`)**: Added `threading.Lock` guard. Multiple callers (TTL prune job + message-threshold trigger + scheduled tick) no longer collide on `.git/index.lock` or interleave `git add`/`commit`/`push` operations.
- **Sync method in async loop (`github_backup.increment_counter` + `backup`)**: `backup()` now `async` wrapper around `asyncio.to_thread(self._backup_sync)`. `increment_counter()` returns pure decision bool. Callers in `message_handler.py:200` and `scheduled_jobs.py:105` updated to `await`. Event loop no longer blocked by subprocess sync calls.
- **Audit log fire-and-forget loss (`github_backup._schedule_audit`)**: `asyncio.create_task` calls now guarded by `loop.create_task` inside `try/except RuntimeError`. Best-effort audit persists, no exception swallowed silently when no loop is running.

### 🐛 Fixed (Reliability)
- **Dead retry code (`browserless_client.fetch_with_retry`)**: Original logic returned on every error because `fetch_content` set `safe: False` for all errors (including transient 5xx). Added `transient` flag (HTTP 429/500/502/503/504 + exceptions), `fetch_with_retry` now respects it with exponential backoff (1s, 2s). Real transient failures retry; permanent failures (4xx, unsafe URL) still bail immediately.

### 🐛 Fixed (Prompt Injection)
- **False-positive injection filter (`browserless_client.INJECTION_PATTERNS`)**: Removed overly broad patterns (`IMPORTANT:`, `CRITICAL:`, `URGENT:`, `you must`, `do not`, `never`, `always respond`) that blocked legitimate news/text content. Retained specific injection phrasings (`ignore previous instructions`, `you are now a/an`, `disregard all`, `system prompt:`, `jailbreak`, `DAN mode`, etc.) with stricter anchoring.

### 🐛 Fixed (Amnesia)
- **Session amnesia on restart (`session_manager.SessionManager`)**: `SessionManager` now accepts `history_store` and lazy-hydrates from disk on first access per channel key (`hydrate_from_disk`). In-memory `defaultdict(list)` no longer starts empty on bot startup — restart preserves all prior conversation.
- **Idle timeout amnesia**: Removed auto-clear on `SESSION_TIMEOUT` in `_cleanup_expired`. Sessions persist indefinitely on disk; pruning handled by weekly disk cleanup (7-day TTL via `HISTORY_CLEANUP_DAYS`).
- **Compaction wiped in-memory only (`session_manager.replace_history`)**: Now also persists summary + last 4 tail messages to `HistoryStore`. Compaction result survives restart. CompactionEngine `append_compaction` call removed (now handled inside `replace_history`).
- **TTL cleanup crash on float timestamps (`scheduled_jobs.run_cleanup_history`)**: `datetime.fromisoformat(time.time())` raised uncaught `ValueError` per entry (history was stored as float epoch). Added `_entry_timestamp` helper handling float/int/ISO/missing formats. Cleanup count now accurate (`cleaned` counter incremented per entry removed).

### 🛠 Changed
- **`session_manager.replace_history` signature**: New optional kwarg `tail_keep=4` controls how many recent messages survive compaction alongside the summary.
- **`compaction_engine.check_and_compact`**: Dropped redundant `history_store.append_compaction` call (now done inside `replace_history`).
- **`main.py`**: `SessionManager(settings, history_store)` wiring — history_store must be instantiated first.

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
