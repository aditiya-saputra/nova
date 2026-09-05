# Nova - Tsundere AI Discord Bot

Nova adalah bot Discord AI dengan kepribadian tsundere feminim yang didukung oleh Google Gemini, Groq, Tavily, dan Browserless. Bot ini memiliki berbagai fitur canggih seperti VLM (Vision Language Model), Micro-RAG memory, auto-mention, audit logging, dan automatic GitHub backup.

---

## 🌟 Fitur Utama

### 🧠 AI & Memory
- **Google Gemini API** - Response generation dengan support model rotation & VLM
- **Groq API** - Fact extraction & memory retrieval yang sangat cepat
- **Micro-RAG System** - Menyimpan memori/fakta penting per channel dengan TTL
- **Session Compaction** - Otomatis meringkas percakapan panjang

### 👁️ VLM (Vision Language Model)
- **Direct Image Analysis** - Analisis gambar yang dikirim langsung di chat
- **Image URL Analysis** - Analisis gambar dari URL menggunakan tool `analyze_image`
- **Webpage Screenshot** - Screenshot webpage dan analisis visual menggunakan Browserless

### 🌐 Web Fetching & Search
- **Tavily Web Search** - Search real-time data di internet
- **Browserless Integration** - Fetch & sanitize webpage content dengan prompt injection protection

### 🔔 Auto-Mention System
- **Presence Tracking** - Otomatis deteksi saat user online
- **Opt-in / Opt-out** - User bisa memilih untuk di-mention atau tidak
- **Custom Rate Limits** - Option: 10 menit, 1 jam, atau 1 hari sekali
- **AI Welcome Messages** - Pesan menyapa tsundere di-generate via Gemini

### 📝 Audit & Monitoring
- **Deleted Message Tracking** - Log pesan yang dihapus (dengan cache 500 pesan)
- **Edited Message Tracking** - Log pesan yang diedit
- **Tool Call Audit** - Log semua pemanggilan tool dan hasilnya
- **Presence Log** - Audit log perpindahan status user

### 💾 Automatic Backup
- **GitHub Auto-Backup** - Backup data memori & audit logs ke GitHub private repository secara berkala

---

## ⚙️ Configuration

### Source of Truth
Prefix bot ditentukan oleh `BOT_PREFIX` di `.env` (comma-separated). Jika kosong, fallback ke `config/prefixes.json`. Default: `n!,.,?`.

```env
BOT_PREFIX=n!,.,?
```

### Rotating Secrets
Untuk mengganti API key:
1. Rotate di dashboard masing-masing provider.
2. Update `.env` (yang sekarang berisi placeholder).
3. **JANGAN** commit `.env` ke git (sudah di-ignore).

Old values yang pernah bocor ada di `secrets/.env.archive` — anggap compromised, rotate segera.

### Waktu (Timezone)
Semua timestamp yang ditampilkan ke user (audit logs, memory recall, status, dll.) memakai **WIB (Asia/Jakarta, UTC+7)** via `pytz`. Penyimpanan internal tetap UTC agar logika TTL & expired konsisten.

### Gemini Model & Fallback
Nova memakai rantai model Gemini: `GEMINI_MODEL` sebagai model utama, lalu `GEMINI_FALLBACK_MODELS` (comma-separated) sebagai cadangan. Saat model yang sedang dipakai mengembalikan error 404 NOT_FOUND (mis. model sudah deprecated / tidak tersedia untuk key baru), client otomatis mencoba model berikutnya di rantai secara berurutan. (Error rate-limit 429/503 justru memicu retry dengan rotasi API key, bukan ganti model.)

`gemini-3.6-flash` ternyata **model thinking-only** (`thinking: true` di metadata API; `thinking_budget=0` ditolak, budget kecil tetap ~27s) — lambatnya tidak bisa dihilangkan, jadi model utama memakai **`gemini-3-flash-preview`** yang terverifikasi cepat (~1.3-1.8s di probe latensi).

```env
GEMINI_MODEL=gemini-3-flash-preview
GEMINI_FALLBACK_MODELS=gemini-flash-latest,gemini-flash-lite-latest
```

Catatan:
- Urutan fallback mengikuti urutan penulisan — model pertama yang berhasil yang dipakai.
- Jangan masukkan model yang sudah deprecated (mis. `gemini-2.5-flash`) ke dalam rantai; Gemini menolaknya dengan 404 untuk key baru.
- Saat startup, Nova memverifikasi rantai model ke API Gemini dan mencatatnya di log (`Gemini model chain: [...]`). Bila seluruh rantai tidak tersedia, startup dibatalkan (fail-fast) sebelum bot online — cek log `Startup aborted` bila bot tidak menyala.

## ⚡ Slash Commands

| Command | Description |
|---------|-------------|
| `/ask` | Tanya sesuatu ke Nova |
| `/recall` | Cari fakta/memori tersimpan di channel |
| `/forget` | Hapus semua ingatan Nova di channel (memori RAG + riwayat) — admin |
| `/history` | Lihat riwayat percakapan |
| `/deleted` | Lihat log pesan yang dihapus |
| `/audit` | Lihat audit log bot (deleted, edited, tool calls, errors) |
| `/send` | Kirim pesan ke channel tertentu (admin) |
| `/welcome` | Sambut user back secara manual |
| `/optin` | Aktifkan auto-mention saat online |
| `/optout` | Nonaktifkan auto-mention |
| `/mystatus` | Cek status auto-mention kamu |
| `/analyze` | Analisis gambar dari URL menggunakan VLM |
| `/screenshot` | Screenshot webpage dan analisis tampilan visualnya |

---

## ⚙️ Requirements & Installation

### 1. Prerequisites
- Python 3.10+
- Discord Bot Token (dengan Intent: Server Members, Presences, Message Content)
- Google Gemini API Key
- Groq API Key (opsional, untuk RAG)
- Tavily API Key (opsional, untuk web search)
- Browserless Token (opsional, untuk web fetch & screenshot)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup Environment Variables (`.env`)
Salin `.env.example` ke `.env` dan isi variabel yang dibutuhkan:

```env
# Discord
DISCORD_TOKEN=your_discord_token

# Bot Behavior
BOT_PREFIX=n!,.,?

# Gemini API
GEMINI_API_KEYS=key1,key2,key3
GEMINI_MODEL=gemini-3-flash-preview
GEMINI_FALLBACK_MODELS=gemini-flash-latest,gemini-flash-lite-latest

# Groq API
GROQ_API_KEY=your_groq_api_key

# Tavily API
TAVILY_API_KEY=your_tavily_api_key

# Browserless
BROWSERLESS_URL=https://chrome.browserless.io
BROWSERLESS_TOKEN=your_browserless_token

# GitHub Backup
GITHUB_TOKEN=your_github_token
GITHUB_REPO=username/repo-name

# Auto-Mention
WELCOME_ENABLED=true
WELCOME_CHANNEL_ID=your_channel_id_here
```

### 4. Run the Bot
```bash
python main.py
```

---

## 🛠️ Project Structure

```
discord-ai-bot/
├── main.py                  # Entry point + thin event wrappers
├── cogs/                    # Discord command cogs
│   ├── ai_commands.py       # Prefix AI commands
│   ├── admin_commands.py    # Admin management
│   ├── dynamic_presence.py  # Rotating bot status
│   └── slash_commands.py    # All slash commands
├── core/                    # Bot core logic
│   ├── bot.py               # Bot setup & intents
│   ├── context_builder.py   # System prompt builder
│   ├── event_handler.py     # on_ready, on_error, slash sync
│   └── message_router.py    # Message trigger detection
├── handlers/                # Message orchestration
│   ├── message_handler.py   # Main orchestrator (handle/handle_delete/handle_edit/handle_presence)
│   ├── message_cache.py     # LRU cache for deleted-message tracking
│   ├── attachment_processor.py # VLM inline image analysis
│   └── fact_extractor.py    # Post-response RAG nugget extraction
├── services/                # External API integrations
│   ├── gemini_client.py     # Gemini API & VLM client
│   ├── groq_client.py       # Groq API client
│   ├── tavily_client.py     # Tavily search client
│   ├── browserless_client.py# Browserless web fetch & screenshot
│   ├── tool_executor.py     # Tool definition & execution
│   └── token_counter.py     # tiktoken wrapper
├── memory/                  # Memory & storage management
│   ├── session_manager.py   # In-memory session history
│   ├── history_store.py     # Persistent history storage
│   ├── rag_store.py         # Micro-RAG nugget storage (with dedup)
│   ├── compaction_engine.py # History summarization
│   ├── audit_logger.py      # Async-locked event audit logging
│   ├── mention_store.py     # User auto-mention preferences
│   ├── github_backup.py     # Automatic Git backup
│   └── scheduled_jobs.py    # TTL prune + history cleanup
├── config/                  # Configuration & prompts
│   ├── settings.py          # Environment settings (BOT_PREFIX, etc.)
│   ├── prefixes.json        # Fallback prefix config
│   └── prompts/             # System prompts
│       ├── personality.txt  # Nova tsundere personality prompt
│       ├── compaction_prompt.txt
│       ├── rag_extract_prompt.txt
│       └── rag_retrieve_prompt.txt
├── utils/                   # Logging, validation, time helpers
│   ├── logger.py
│   ├── rich_presenter.py
│   ├── validators.py
│   └── time_utils.py
├── secrets/                 # OUT-OF-TREE: archive of rotated secrets (.env.archive)
└── data/                    # Dynamic storage (JSON/JSONL)
```

---

## 🛡️ Safety & Security

- **Prompt Injection Protection** - Content dari Browserless di-sanitize (strip HTML, script, iframe, injection patterns).
- **Private IP Blocking** - Browserless memblokir request ke localhost / IP privat.
- **Audit Logging** - Semua aktivitas sensitif di-log ke `data/audit/audit.jsonl` dengan `asyncio.Lock` (race-free).
- **Sensitive Data Filtering** - Token dan API keys disembunyikan dalam log.
- **`.env` Hardening** - `.env` masuk `.gitignore` (override `.env.*` kecuali `.env.example`). Old secrets diarsipkan ke `secrets/.env.archive` (out-of-tree).
- **RAG Nugget Dedup** - Fact baru di-hash (SHA1 normalized) sebelum disimpan; duplikat di skip.
- **SSRF Guard** - URL validation di Browserless: scheme whitelist + private IP blocklist + injection regex.

---

## 📜 License

MIT License. Feel free to use and modify for your own Discord servers.
