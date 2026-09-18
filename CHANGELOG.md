# Changelog - Nova Discord AI Bot

All notable changes to this project will be documented in this file.

---

## [1.15.0] - 2026-09-18

### 🐛 Fixed (20 bugs — Context7 audit)

#### Critical (5)
- **Audit log auth bypass** (`services/tool_executor.py:390`): `get_audit_logs` tool only checked permissions when both `channel_id` AND `user_id` were provided. If either was missing, audit logs (including deleted messages, tool args, errors) were returned without authorization. Now requires both and validates moderator/admin permission. **Security: high.**
- **Gemini no-keys crash** (`services/gemini_client.py:147`): `_run_with_fallback()` looped `range(len(self.keys))` — with zero keys, no API call occurred, `last_error` remained `None`, and `raise last_error` produced unhelpful `TypeError`. Now raises `ValueError("No Gemini API keys configured")` early.
- **File attachment limit bypass** (`handlers/message_handler.py:541`): `_build_final_prompt` appended file contents directly without calling `format_for_prompt()`, bypassing `MAX_TOTAL_CHARS=20000`. Up to ~40K chars could be injected. Now uses `FileProcessor.format_for_prompt()` which enforces the limit.
- **`/welcome` no permission check** (`cogs/slash_commands.py:405`): Any user could invoke `/welcome` to send bot-generated mentions to arbitrary channels. Added `@app_commands.checks.has_permissions(manage_messages=True)`.
- **Hyperbrowser screenshot unbounded download** (`services/hyperbrowser_client.py:152`): `_coerce_image_bytes` followed screenshot URLs and read entire response into memory without size limit or content-type check. Added 20MB limit, content-type validation, and streaming chunked read.

#### Medium (8)
- **Settings crash on invalid env** (`config/settings.py:39-40,58-59`): `GEMINI_CONTEXT_LIMIT`, `GEMINI_OUTPUT_LIMIT`, `NUGGETS_TTL_DAYS`, `NUGGETS_TOP_K` used direct `int()` conversion, crashing at import on invalid values. Now uses `_safe_int`/`_safe_float` helpers. **CHANGELOG 1.11.0 claim was incomplete.**
- **TTL prune mismatch** (`memory/scheduled_jobs.py:87`): `TTL_PRUNE_DAYS` defaulted to 30 days, while RAG nuggets use `NUGGETS_TTL_DAYS` (default 3 days). Expired nuggets persisted up to 30 days. Now defaults to `NUGGETS_TTL_DAYS` value.
- **RAG lock eviction race** (`memory/rag_store.py:32`): LRU eviction deleted locks without checking if they were actively held (`locked()`). A new lock for the same channel could be created while the old operation was still running, allowing concurrent writes. Now skips locked entries.
- **Audit timestamp naive** (`memory/audit_logger.py:30`): `log()` used `datetime.now()` (host timezone) instead of `datetime.now(timezone.utc)`. Inconsistent with documented UTC storage contract. Now uses UTC.
- **`get_logs_by_type` returns oldest** (`memory/audit_logger.py:123`): Scanned file from beginning, returning oldest matching entries while UIs described "recent/last". Now reads from end (most recent first) and reverses for chronological order.
- **Sholat config relative path** (`memory/scheduled_jobs.py:11`): Used literal `data/sholat_config.json` instead of `Settings.DATA_DIR`. Running from different working directory caused config to disappear. Now uses `Path(Settings.DATA_DIR) / "sholat_config.json"`.
- **Sholat role ID env ignored** (`memory/scheduled_jobs.py:283`): Reminder used only JSON config's `role_id`, ignoring `SHOLAT_ROLE_ID` from `.env`. Now falls back to env setting when JSON is empty.
- **Gemini VLM Part constructor** (`services/gemini_client.py:469`): Image parts used `types.Part(inline_data=...)` instead of `types.Part.from_blob(...)`. Could produce incorrect Part objects. Now uses factory method. **CHANGELOG 1.14.0 claim was incomplete.**

#### Low (7)
- **`/history` no permission check** (`cogs/slash_commands.py:221`): Any user could view channel conversation history. Added `manage_messages` permission requirement.
- **Voice raw exception leak** (`cogs/voice.py:89,171`): Voice join errors sent raw `str(e)` to users, leaking internal details. Now sends generic message.
- **`read_attachment` filename collision** (`services/tool_executor.py:692`): Cache lookup matched first filename found in insertion order. When multiple messages had same filename, stale content could be returned. Now searches newest message first (sorted keys, reverse).
- **Tracker eviction inconsistency** (`handlers/message_handler.py:595`): Three tracker dictionaries were evicted independently, causing keys to exist in one but not others. Now collects all keys, sorts, and evicts consistently across all three dicts.
- **HistoryStore key collision** (`memory/history_store.py:18`): Sanitized keys by removing invalid chars — `a/b` and `ab` mapped to same file. Now uses SHA1 hash of key for unique filenames.
- **`get_all_opted_in` crash** (`memory/mention_store.py:109`): Blindly converted all opted-in keys to `int()`. Malformed `preferences.json` caused `ValueError`. Now wraps in try/except per key.
- **`/sholat` validation mismatch** (`cogs/sholat.py:93`): Error said "1-30" but `days=0` was intentionally handled as "today". Updated message to "0-30".

### 📁 File Changes
```
services/tool_executor.py       # Auth required for get_audit_logs, read_attachment newest-first
services/gemini_client.py       # No-keys ValueError, Part.from_blob for VLM
services/hyperbrowser_client.py # Bounded screenshot download (20MB, content-type, streaming)
handlers/message_handler.py     # format_for_prompt for file limits, consistent tracker eviction
cogs/slash_commands.py          # /welcome + /history permission checks
cogs/voice.py                   # Generic voice error messages
cogs/sholat.py                  # Validation message 0-30
config/settings.py              # _safe_int for GEMINI_CONTEXT/OUTPUT_LIMIT, NUGGETS_*
memory/audit_logger.py          # UTC timestamps, get_logs_by_type newest-first
memory/rag_store.py             # Skip locked entries during LRU eviction
memory/scheduled_jobs.py        # Absolute config path, TTL default, role ID fallback
memory/history_store.py         # SHA1-hashed keys to prevent collision
memory/mention_store.py         # Graceful handling of malformed preference keys
```

---

## [1.14.0] - 2026-09-17

### 🐛 Fixed (17 bugs — deep scan)

#### Critical (6)
- **Gemini history always empty** (`handlers/message_handler.py:45`): `_to_gemini_history` filtered messages with `role not in ("user", "model")`, but `SessionManager` stores role as `"assistant"`. All assistant messages were silently dropped — Gemini received zero conversation history. Now maps `"assistant"` → `"model"`.
- **Event loop blocked during compaction** (`memory/session_manager.py:88`): `replace_history()` called sync `HistoryStore` file I/O directly from async context, blocking the entire event loop during history compaction. Now wraps file I/O in `asyncio.to_thread`.
- **Race condition in Gemini key rotation** (`services/gemini_client.py:144`): `_get_next_key()` mutated `current_index` without lock. Concurrent Gemini calls (e.g., multiple slash commands) could use the same API key, accelerating rate limits. Added `asyncio.Lock` guard.
- **Sholat reminder timezone mismatch** (`memory/scheduled_jobs.py:203`): `_check_sholat_reminder` received `datetime.now()` (server local time) but prayer times from API are in WIB. If server runs in UTC, all reminders fired at wrong times. Now uses `datetime.now(WIB)` for comparison.
- **RagStore unbounded lock memory leak** (`memory/rag_store.py:28`): `_channel_locks` dict grew forever — one `asyncio.Lock` per channel ID across all guilds. Added LRU eviction at `MAX_LOCKS=500`.
- **SessionManager eviction crash** (`memory/session_manager.py:119`): `_evict_if_needed` sorted `self.last_activity` keys, but some sessions might not have entries in `last_activity`, causing `KeyError`. Now sorts from `self.sessions.keys()` instead.

#### Medium (7)
- **Audit log race on read** (`memory/audit_logger.py:104`): `get_recent_logs` read the audit file without acquiring `_file_lock`, potentially reading partial writes from concurrent threads. Now reads under lock.
- **SSRF bypass via IPv6 URL** (`services/browserless_client.py:132`): IPv6 check only matched exact `::1`. URLs like `http://[::ffff:127.0.0.1]` or `http://[0:0:0:0:0:ffff:127.0.0.1]` bypassed the block. Now strips brackets and checks mapped IPv4 addresses.
- **FactExtractor silent failure** (`handlers/fact_extractor.py:32`): `extract_and_save` swallowed all exceptions without logging, making Groq extraction failures invisible. Now logs the error.
- **Background tasks GC'd before completion** (`handlers/message_handler.py:36`): `_spawn` created tasks via `create_task` but never stored the reference. Tasks could be garbage-collected before finishing. Added `task_set` tracking with `done_callback` cleanup.
- **SholatClient cache data race** (`services/sholat_client.py:258`): `get_today_prayer_times` returned a direct reference to the cached dict, which could be mutated by concurrent async writes. Now returns a copy.
- **Compaction sync file I/O** (`memory/compaction_engine.py:39`): `check_and_compact` called sync `session_manager.replace_history` which blocked the event loop. Updated to `await` the now-async method.
- **HistoryStore `__import__` anti-pattern** (`memory/history_store.py:52`): `__import__("time").time()` called on every message append. Moved `time` to module-level import.

#### Low (4)
- **MentionStore `NameError` on save failure** (`memory/mention_store.py:36`): If `tempfile.mkstemp()` failed, the `tmp` variable was undefined, causing `NameError` in the exception handler. Now initializes `tmp = None` before try block.
- **SlashCommands inline imports** (`cogs/slash_commands.py:76,412,653`): `import asyncio`, `import random`, `import io` inside methods on every invocation. Moved to module-level imports.
- **Gemini Part constructor** (`services/gemini_client.py:464`): `types.Part(text=prompt)` used direct constructor instead of `types.Part.from_text(text=prompt)`. Could produce incorrect Part objects depending on SDK version.
- **File attachment cache FIFO cleanup** (`handlers/message_handler.py:179`): `list(cache.keys())[:50]` did not guarantee FIFO order after deletions. Now uses `list(cache.keys())[:-50:-1]` for correct oldest-first eviction.

### 📁 File Changes
```
handlers/message_handler.py     # role mapping, task tracking, cache FIFO
memory/session_manager.py       # async replace_history, eviction fix, asyncio import
memory/compaction_engine.py     # await replace_history
memory/history_store.py         # time import, remove __import__
memory/rag_store.py             # LRU lock eviction
memory/audit_logger.py          # read with lock
memory/mention_store.py         # NameError guard
memory/scheduled_jobs.py        # WIB timezone for sholat
services/gemini_client.py       # key rotation lock, Part.from_text
services/browserless_client.py  # IPv6 SSRF bypass fix
services/sholat_client.py       # cache copy
handlers/fact_extractor.py      # error logging
cogs/slash_commands.py          # module-level imports
```

---

## [1.13.0] - 2026-09-17

### ✨ Added (Jadwal Sholat & Auto-Reminder)
- **`services/sholat_client.py`** (NEW): API client untuk jadwal sholat — myQuran v3 (primary, data Kementerian Agama RI) + AlAdhan (fallback global, no API key).
  - `get_today()` / `get_date()` / `get_range()` — jadwal sholat hari ini, tanggal tertentu, atau N hari ke depan
  - `get_qibla()` — arah kiblat dari koordinat kota
  - `search_city()` — cari kota di myQuran (517 kota Indonesia)
  - `generate_reminder()` — pesan reminder tsundere via Gemini (system instruction pakai `personality.txt`); fallback template statis jika Gemini down
  - In-memory cache per hari untuk mengurangi API calls
- **`cogs/sholat.py`** (NEW): 7 slash commands:
  - `/sholat [days]` — jadwal sholat hari ini atau N hari ke depan (max 30)
  - `/sholat-kiblat` — arah kiblat dalam derajat + kompas
  - `/sholat-status` — cek konfigurasi (kota, method, channel, role, status)
  - `/sholat-set-channel #channel` — set channel untuk auto-reminder (admin)
  - `/sholat-set-role @Role` — set role untuk mention di reminder (admin)
  - `/sholat-set-city Jakarta` — cari dan set kota via myQuran API (admin)
- **Auto-Reminder** (`memory/scheduled_jobs.py`): reminder check di `prune_loop` setiap 60 detik, kirim pesan 10 menit sebelum waktu sholat ke channel yang dikonfigurasi. Role mention `<@&ROLE_ID>` untuk notifikasi user yang sudah assign role.
- **Config** (`config/settings.py`): 9 env vars baru — `SHOLAT_ENABLED`, `SHOLAT_CITY_ID`, `SHOLAT_CITY_NAME`, `SHOLAT_LAT`, `SHOLAT_LNG`, `SHOLAT_METHOD`, `SHOLAT_TIMEZONE`, `SHOLAT_ROLE_ID`, `SHOLAT_REMINDER_MINUTES`.

### 📁 File Changes
```
services/sholat_client.py      # NEW: myQuran + AlAdhan API client + AI reminder
cogs/sholat.py                 # NEW: 7 slash commands for jadwal sholat
memory/scheduled_jobs.py       # +sholat reminder check in prune_loop, load/save_sholat_config
config/settings.py             # +9 SHOLAT_* env vars
main.py                        # +SholatClient wiring + load cogs.sholat
.env.example                   # +sholat settings documentation
```

---

## [1.12.0] - 2026-09-15

### ✨ Added (Voice AFK)
- **`cogs/voice.py`**: New cog — Nova bisa masuk voice channel dan AFK di sana.
  - `/afk` / `!afk` — Join voice channel, self-deafen, duduk manis
  - `/unafk` / `!unafk` — Leave voice channel
  - Activity status berubah otomatis: "AFK di #channel_name"
- **`discord.py[voice]`** (includes PyNaCl) + opus library auto-load check — voice commands gracefully disable when `libopus` is missing
- **Voice intent** (`voice_states=True`) ditambahkan di `core/bot.py`

### 🐛 Fixed
- **`thought_signature` lost** (`services/gemini_client.py`): Compositional function calling gagal dengan `400 INVALID_ARGUMENT` karena `_rebuild_content_with_signatures` membuat Part baru yang tidak preserve thought_signature. Sekarang pass original content langsung.

### 📁 File Changes
```
cogs/voice.py                  # NEW: Voice AFK cog
requirements.txt               # +PyNaCl
core/bot.py                    # +voice_states intent
main.py                        # +load cogs.voice
config/prompts/personality.txt # +voice AFK docs
services/gemini_client.py      # thought_signature fix (hapus _rebuild_content)
```

---

## [1.11.0] - 2026-09-15

### 🐛 Fixed (18 bugs — deep scan)

#### Critical (4)
- **`UnboundLocalError` in TTL prune** (`memory/scheduled_jobs.py:86-87`): Exception handler referenced `record` variable that was never assigned when `json.loads` failed. Split exception handling: `JSONDecodeError` keeps raw line, other errors keep parsed record.
- **`AttributeError` on null content** (`services/gemini_client.py:317`): `_parse_tool_response` accessed `response.candidates[0].content.parts` without null-checking `content`. Gemini API can return `content=None` on safety filter blocks.
- **Path traversal via `channel_id`** (`memory/rag_store.py:36`): `_get_file_path` interpolated `channel_id` directly into filename. Malicious values like `../../` could escape the `memories/` directory. Now sanitized with regex.
- **Path traversal via `skill_name`** (`services/tool_executor.py:672`): `_use_skill` constructed file path from unsanitized user/LLM input. Added regex whitelist (`^[a-zA-Z0-9_-]+$`) and `is_relative_to()` check.

#### Medium (10)
- **`last_assistant` param ignored** (`services/gemini_client.py:415`): `synthesize_with_tool_result` (singular) accepted `last_assistant` but didn't pass it to `_synthesize_multi`.
- **Extension whitelist bypass** (`handlers/file_processor.py:56`): Files without extensions (e.g., `malware`) bypassed the whitelist filter. Now requires `text/*` MIME type when no extension is present.
- **`latin-1` decodes binary data** (`handlers/file_processor.py:119`): `latin-1` fallback always succeeds, allowing binary files to be decoded as garbled text. Added null-byte heuristic before fallback.
- **Compaction prompt unreadable** (`core/context_builder.py:58`): History list rendered as raw Python dict repr. Now formatted as `[role]: content` per message.
- **`tree.sync()` rate limit** (`core/event_handler.py:112`): Called on every `on_ready` reconnect, hitting Discord's ~1/hour rate limit. Added `_tree_synced` flag.
- **`on_command_error` leaks errors** (`core/event_handler.py:119`): Raw exception sent to channel and could crash on deleted channel. Now sends generic message with `HTTPException` guard.
- **System prompt not as `system_instruction`** (`cogs/slash_commands.py:69`, `cogs/ai_commands.py:41`): `/ask` and `!ask` embedded system prompt in user message instead of passing as `system_instruction` parameter.
- **Error details leaked to users** (`cogs/slash_commands.py`): Multiple slash commands sent raw `str(e)` to users. Now sends generic error message.
- **Invalid env vars crash at import** (`config/settings.py:41-55`): `COMPACTION_THRESHOLD=abc` caused `ValueError` at import time. Added `_safe_int`/`_safe_float` helpers.
- **Audit file loaded into memory** (`memory/audit_logger.py:104`): `get_recent_logs` used `f.readlines()` loading entire file. Now uses `deque(maxlen=limit)`.

#### Low (4)
- **Unbounded session caches** (`memory/session_manager.py`): `sessions`, `last_activity`, `token_counts` grew without bound. Added `MAX_SESSIONS=500` with LRU eviction.
- **Unbounded tracker dicts** (`handlers/message_handler.py:91`): `_last_tool_calls`, `_last_response_text`, `_last_tool_result_fp` grew without bound. Added `MAX_CHANNEL_TRACKERS=200` with eviction.
- **Non-atomic preferences write** (`memory/mention_store.py:35`): `_save_preferences` wrote directly to file. Crash mid-write corrupted data. Now uses temp file + `os.replace()`.
- **Relative path for prefixes** (`core/bot.py:21`): Used relative `config/prefixes.json`. Now uses `Path(__file__).resolve()` for absolute path.

### 📁 File Changes
```
memory/scheduled_jobs.py       # Split exception handler in TTL prune
services/gemini_client.py      # Null-check content, pass last_assistant
memory/rag_store.py            # Sanitize channel_id in file path
services/tool_executor.py      # Whitelist + is_relative_to for skill_name
handlers/file_processor.py     # No-ext MIME check, null-byte binary detection
core/context_builder.py        # Format history as [role]: content
cogs/slash_commands.py         # system_instruction param, generic errors
cogs/ai_commands.py            # system_instruction param, generic error
core/event_handler.py          # tree.sync flag, on_command_error guard
config/settings.py             # _safe_int/_safe_float helpers
memory/audit_logger.py         # deque for recent logs
memory/session_manager.py      # MAX_SESSIONS + LRU eviction
handlers/message_handler.py    # MAX_CHANNEL_TRACKERS + eviction
memory/mention_store.py        # Atomic write via temp file
core/bot.py                    # Absolute path for prefixes.json
```

---

## [1.10.0] - 2026-09-15

### ✨ Added (File Reading Module)
- **`handlers/file_processor.py`**: New module for reading non-image file attachments (code, JSON, text, config). Supports 40+ extensions (.py, .js, .ts, .json, .yaml, .md, etc.) with 500KB/file and 8000 chars content limit.
- **Tool `read_attachment`** (`services/tool_executor.py`): New tool for Gemini to read uploaded file contents on-demand. Use when user asks to review, analyze, or discuss uploaded files.
- **Auto-detection** (`handlers/message_handler.py`): Non-image file attachments are automatically detected, downloaded, and injected into prompt context. File contents are also cached for the `read_attachment` tool.
- **Parallel I/O**: File download runs in parallel with VLM, RAG, compaction, and URL fetch via `asyncio.gather`.

### 🐛 Fixed
- **`thought_signatures` overwrite** (`handlers/message_handler.py:383`): Compositional function calling loop was resetting `thought_signatures = []`, discarding initial signatures from Gemini response. This could cause `400 INVALID_ARGUMENT` errors on subsequent tool rounds.
- **Sequential URL fetch** (`handlers/message_handler.py:_fetch_url_contexts`): URLs were fetched sequentially. Now parallelized via `asyncio.gather` for faster response (2 URLs = ~2x faster).
- **Duplicate `import json`** (`cogs/slash_commands.py`): Removed redundant inline `import json` in `/ask` and `/recall` commands (already imported at module level).

### 📁 File Changes
```
handlers/file_processor.py      # NEW: File attachment reader
services/tool_executor.py       # +1 tool def (read_attachment), +1 method, +1 dispatch
handlers/message_handler.py     # +FileProcessor integration, parallel URL fetch, thought_signature fix
main.py                         # +FileProcessor wiring + aclose
config/prompts/personality.txt  # +tool docs for read_attachment
```

---

## [1.9.1] - 2026-09-13

### 🐛 Fixed (thought_signature — Gemini API Requirement)
- **Root Cause**: Gemini API now **requires** `thought_signature` on every `functionCall` part in conversation history. When Nova sent function calls back to Gemini via `models.generate_content`, the `thought_signature` bytes were missing from `Part` objects, causing `400 INVALID_ARGUMENT: Function call is missing a thought_signature in functionCall parts`.
- **Fix** (`services/gemini_client.py`):
  - Added `_extract_thought_signatures()` — extract `thought_signature` bytes from each Part in a Content object.
  - Added `_rebuild_content_with_signatures()` — rebuild Content with `thought_signature` properly attached to each Part.
  - Added `_build_contents_with_signatures()` — build contents array with proper thought_signature handling.
  - Updated `_parse_tool_response()` — now also extracts `thought_signatures` alongside tool_calls.
  - Updated `generate_with_tools()` — stores `thought_signatures` from response for compositional loop.
  - Updated `generate_with_tool_results()` — accepts `thought_signatures` parameter and passes it to `_build_contents_with_signatures()`.
- **Fix** (`handlers/message_handler.py`):
  - `_handle_tool_calls()` now accepts `thought_signatures` parameter.
  - `initial_thought_signatures` extracted from `generate_with_tools` response and passed through compositional loop.
  - Each round accumulates `thought_signatures` from previous response and passes them to next `generate_with_tool_results` call.

### ✨ Added (Anti-Slop-Writing Skill)
- **`skills/anti_slop_writing.md`** — New skill for detecting AI-generated/slop writing. Based on Wikipedia's ["Signs of AI writing"](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) guide. Covers 30+ indicators including content clues, language patterns, style tells, model-specific artifacts (ChatGPT, Gemini, Grok, DeepSeek, Perplexity fingerprints), citation issues, and more.
- Skills directory now contains **2 skills**: `eyd_helper` (EYD & grammar) and `anti_slop_writing` (AI/slop detection).

### 📁 File Changes
```
skills/
├── eyd_helper.md          # Built-in skill: EYD Helper
└── anti_slop_writing.md   # New: Anti-Slop-Writing AI detection skill
```

---

## [1.9.0] - 2026-09-11

### ✨ Added (Skills System — Tool Calling Based)
- **Skills System** (`skills/` directory): Nova kini mendukung skills yang disimpan sebagai file `.md` di direktori `skills/`. Setiap skill berisi pengetahuan khusus yang bisa digunakan via tool calling.
- **Tool `use_skill`** (`services/tool_executor.py`): Tool baru untuk memanggil skill. Gemini akan memilih skill yang relevan dan memproses query dengan context dari skill file.
- **Tool `list_skills`** (`services/tool_executor.py`): Tool untuk melihat semua skill yang tersedia.
- **EYD Helper Skill** (`skills/eyd_helper.md`): Skill contoh pertama — ahli Ejaan Yang Disempurnakan (EYD) dan tata bahasa Indonesia dengan knowledge base lengkap.

### 🐛 Fixed (Compositional Function Calling 400 Error)
- **Root Cause**: `generate_with_tool_results()` menggunakan `models.generate_content` (stateless) tanpa menyertakan function call sebelumnya di conversation history. Gemini API membutuhkan function response datang **langsung setelah** function call turn.
- **Fix** (`services/gemini_client.py`):
  - `generate_with_tools()` kini mengembalikan `chat` object di result dict untuk dipertahankan di compositional loop.
  - `generate_with_tool_results()` menerima parameter `chat` — jika ada, menggunakan `chat.send_message()` (stateful) bukan `models.generate_content()`.
  - Function response kini di-wrap dalam `types.Content(role="tool", parts=[...])` sesuai dokumentasi Gemini API.
- **Fix** (`handlers/message_handler.py`): `_handle_tool_calls()` menerima dan meneruskan `chat` object melalui compositional loop.

### 🏗️ Architecture
- **Simple File-Based**: Skills = file `.md` di folder `skills/`. Tidak perlu framework kompleks.
- **Tool Calling Integration**: Gemini secara otomatis memanggil `use_skill` saat user meminta sesuatu yang relevan dengan skill.
- **Auto-Discovery**: `list_skills` otomatis scan semua `.md` file di `skills/`.

### 📁 File Structure
```
skills/
└── eyd_helper.md    # Skill EYD Helper (contoh)
```

### 🔧 Cara Membuat Skill Baru
1. Buat file `.md` di folder `skills/` (mis. `translator.md`)
2. Isi dengan pengetahuan/instruksi skill
3. Restart bot (atau Gemini akan mendeteksi skill baru secara otomatis)
4. User bisa langsung gunakan — Gemini akan memanggil tool `use_skill` secara otomatis

---

## [1.8.1] - 2026-09-11

### ✨ Added (Ignore Role & @everyone Mentions)
- **Role & @everyone Mention Filtering**: Nova kini mengabaikan pesan yang hanya berisi mention role (`<@&ROLE_ID>`) atau `@everyone`/`@here` tanpa konten bermakna lainnya. Pesan seperti `@everyone` atau `@Admin` saja tidak akan memicu response dari Nova.
- **Smart Content Stripping (`core/message_router.py`)**:
  - `_strip_all_mentions()`: Method helper untuk menghapus semua jenis mention Discord (bot, role, @everyone, @here) dari konten pesan.
  - `_is_only_mention_content()`: Cek apakah pesan hanya berisi mention tanpa konten bermakna.
- **Clean Content Updated**: `clean_content()` kini juga menghapus role mention dan @everyone/@here dari konten yang diproses, sehingga pesan seperti `@Nova @everyone halo` hanya akan memproses `halo`.

### 🐛 Fixed
- **False Trigger on Role Mentions**: Pesan yang hanya berisi role mention atau @everyone tidak lagi memicu Nova untuk merespon.

---

## [1.8.0] - 2026-09-11

### ✨ Added (Parallel & Compositional Function Calling)
- **Parallel Tool Execution**: Gemini kini dapat memicu beberapa tool sekaligus dalam satu turn. Nova mengeksekusi semua tool tersebut secara konkuren (`asyncio.gather`) untuk respons yang lebih cepat.
- **Compositional Loop**: Implementasi "chaining" tool call hingga 5 ronde. Hasil tool dikirim balik ke Gemini, memungkinkan model untuk meminta tool tambahan berdasarkan data sebelumnya sebelum memberikan jawaban akhir.
- **New Methods (`services/gemini_client.py`)**: 
  - `generate_with_tool_results()`: Mengirim balik hasil eksekusi tool ke model dalam format `function_response`.
  - `synthesize_with_tool_results()`: Mendukung sintesis jawaban dari banyak hasil tool sekaligus.
  - `_parse_tool_response()`: Parser terpusat untuk menangani N tool calls atau teks biasa.

### 🐛 Fixed (Repetitive Output & Prompt Focus)
- **Tool Result Fingerprinting**: Nova kini melacak hash/fingerprint hasil tool terakhir per channel (`_last_tool_result_fp`). Jika tool+args sama dan data belum berubah, Nova menggunakan cache.
- **Staleness Guard**: Cache tool result otomatis expired setelah 5 menit untuk memastikan data tetap aktual.
- **Prompt Best Practices**: 
  - **Reordering**: Mengikuti panduan resmi Gemini, query user kini diletakkan di **akhir prompt** agar model lebih fokus pada instruksi terbaru.
  - **Contextual Reference**: Re-implementasi `last_assistant` sebagai referensi konteks saja. Model dilarang keras mengulang jawaban sebelumnya secara verbatim, tapi diizinkan memakainya untuk menjaga alur percakapan tetap nyambung.
- **Anti-Repeat Extended**: Logic anti-repeat kini mencakup deteksi argumen tool yang identik, bukan hanya panjang pesan user.

### 🛠 Refactored
- **`handlers/message_handler.py`**: Logika penanganan tool dipisahkan ke method `_handle_tool_calls` untuk modularitas dan keterbacaan.
- **`services/gemini_client.py`**: Refaktor struktur prompt sintesis untuk efisiensi token dan akurasi respons.

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
