# Nova Discord Bot - Full Flowchart

## System Architecture

```mermaid
flowchart TB
    subgraph External["External Services"]
        DiscordAPI["Discord API"]
        GeminiAPI["Google Gemini API"]
        GroqAPI["Groq API"]
        TavilyAPI["Tavily API"]
        HyperbrowserAPI["Hyperbrowser API"]
        BrowserlessAPI["Browserless API"]
        GitHubAPI["GitHub API"]
        myQuranAPI["myQuran API"]
        AlAdhanAPI["AlAdhan API"]
    end

    subgraph BotCore["Bot Core"]
        Main["main.py"]
        Bot["core/bot.py"]
        EventHandler["core/event_handler.py"]
        MessageRouter["core/message_router.py"]
        ContextBuilder["core/context_builder.py"]
    end

    subgraph Services["Services Layer"]
        GeminiClient["services/gemini_client.py"]
        GroqClient["services/groq_client.py"]
        TavilyClient["services/tavily_client.py"]
        HyperbrowserClient["services/hyperbrowser_client.py"]
        BrowserlessClient["services/browserless_client.py"]
        SholatClient["services/sholat_client.py"]
        ToolExecutor["services/tool_executor.py"]
        TokenCounter["services/token_counter.py"]
    end

    subgraph Memory["Memory Layer"]
        SessionManager["memory/session_manager.py"]
        HistoryStore["memory/history_store.py"]
        RagStore["memory/rag_store.py"]
        CompactionEngine["memory/compaction_engine.py"]
        AuditLogger["memory/audit_logger.py"]
        MentionStore["memory/mention_store.py"]
        GitHubBackup["memory/github_backup.py"]
        ScheduledJobs["memory/scheduled_jobs.py"]
    end

    subgraph Handlers["Message Handlers"]
        MessageHandler["handlers/message_handler.py"]
        MessageCache["handlers/message_cache.py"]
        AttachmentProcessor["handlers/attachment_processor.py"]
        FileProcessor["handlers/file_processor.py"]
        FactExtractor["handlers/fact_extractor.py"]
    end

    subgraph Cogs["Cogs (Discord Commands)"]
        AICogs["cogs/ai_commands.py"]
        AdminCogs["cogs/admin_commands.py"]
        DynamicPresence["cogs/dynamic_presence.py"]
        SlashCommands["cogs/slash_commands.py"]
        VoiceCog["cogs/voice.py"]
        SholatCog["cogs/sholat.py"]
    end

    subgraph Config["Configuration"]
        Settings["config/settings.py"]
        Personality["config/prompts/personality.txt"]
        Prefixes["config/prefixes.json"]
    end

    Main --> Bot
    Main --> Services
    Main --> Memory
    Main --> Handlers
    Main --> Cogs
    Main --> Config

    Bot --> DiscordAPI
    Bot --> EventHandler
    Bot --> MessageRouter

    GeminiClient --> GeminiAPI
    GroqClient --> GroqAPI
    TavilyClient --> TavilyAPI
    HyperbrowserClient --> HyperbrowserAPI
    BrowserlessClient --> BrowserlessAPI
    GitHubBackup --> GitHubAPI
    SholatClient --> myQuranAPI
    SholatClient --> AlAdhanAPI

    ToolExecutor --> GeminiClient
    ToolExecutor --> GroqClient
    ToolExecutor --> TavilyClient
    ToolExecutor --> HyperbrowserClient
    ToolExecutor --> BrowserlessClient

    MessageHandler --> AttachmentProcessor
    MessageHandler --> FileProcessor
    MessageHandler --> FactExtractor
    MessageHandler --> ToolExecutor

    SlashCommands --> ToolExecutor
    SlashCommands --> AuditLogger
```

## Message Processing Flow

```mermaid
flowchart TD
    Start["User Message"] --> Detect{"Detect Trigger"}

    Detect -->|"Prefix Command<br/>!ask, ?, .ai"| CleanPrefix["Clean Prefix"]
    Detect -->|"Direct Mention<br/>@Nova"| CleanMention["Clean Mention"]
    Detect -->|"Reply to Bot"| CheckReply{"Should Process?"}
    Detect -->|"No Trigger"| Ignore["Ignore Message"]

    CheckReply -->|"Yes"| CleanReply["Clean Reply"]
    CheckReply -->|"No"| Ignore

    CleanPrefix --> FilterMention
    CleanMention --> FilterMention
    CleanReply --> FilterMention

    FilterMention{"Role/Everyone Only?"}
    FilterMention -->|"Yes (only mention)"| Ignore
    FilterMention -->|"No"| ExtractContent

    ExtractContent["Extract Content"] --> LogAudit["Log to Audit"]
    LogAudit --> GatherIOParallel

    GatherIOParallel["Parallel I/O via asyncio.gather"]
    GatherIOParallel --> VLM["Analyze Images<br/>(AttachmentProcessor)"]
    GatherIOParallel --> RAG["Retrieve Facts<br/>(FactExtractor via Groq)"]
    GatherIOParallel --> Compact["Check Compaction<br/>(CompactionEngine)"]
    GatherIOParallel --> URLFetch["Fetch URLs<br/>(Hyperbrowser → Browserless)"]
    GatherIOParallel --> FileRead["Read Files<br/>(FileProcessor)"]

    VLM --> Merge["Merge Results"]
    RAG --> Merge
    Compact --> Merge
    URLFetch --> Merge
    FileRead --> Merge

    Merge --> AddUserMsg["Add User Message to Session"]
    AddUserMsg --> BuildSystem["Build System Prompt<br/>(ContextBuilder)"]
    BuildSystem --> CallGemini["Call Gemini with Tools<br/>(timeout 45s)"]

    CallGemini --> GeminiDecision{"Gemini Response"}

    GeminiDecision -->|"Text Response"| DirectResponse
    GeminiDecision -->|"Tool Call(s)"| ExecuteTools["Execute Tools<br/>(parallel asyncio.gather)"]

    ExecuteTools --> ToolType{"Tool Type"}

    ToolType -->|"web_search"| WebSearch["Tavily Search"]
    ToolType -->|"recall_memory"| RecallMemory["RAG Recall"]
    ToolType -->|"get_history"| GetHistory["Session History"]
    ToolType -->|"get_channel_info"| ChannelInfo["Discord Channel"]
    ToolType -->|"get_user_info"| UserInfo["Discord User"]
    ToolType -->|"get_audit_logs"| AuditLogs["Audit Logger<br/>(auth required)"]
    ToolType -->|"fetch_webpage"| FetchPage["Hyperbrowser/Browserless"]
    ToolType -->|"screenshot_page"| Screenshot["Screenshot + VLM"]
    ToolType -->|"analyze_image"| AnalyzeImage["Image VLM"]
    ToolType -->|"get_online_users"| OnlineUsers["Discord Presence"]
    ToolType -->|"read_attachment"| ReadAttachment["Read Cached File"]
    ToolType -->|"use_skill"| UseSkill["Load Skill .md → Gemini"]
    ToolType -->|"list_skills"| ListSkills["Scan skills/ dir"]

    WebSearch --> ComposeLoop{"More Tool<br/>Rounds?"}
    RecallMemory --> ComposeLoop
    GetHistory --> ComposeLoop
    ChannelInfo --> ComposeLoop
    UserInfo --> ComposeLoop
    AuditLogs --> ComposeLoop
    FetchPage --> ComposeLoop
    Screenshot --> ComposeLoop
    AnalyzeImage --> ComposeLoop
    OnlineUsers --> ComposeLoop
    ReadAttachment --> ComposeLoop
    UseSkill --> ComposeLoop
    ListSkills --> ComposeLoop

    ComposeLoop -->|"Yes (< 5 rounds)"| CallGemini
    ComposeLoop -->|"No / Text"| DirectResponse["Get Final Response"]

    DirectResponse --> AddBotMsg["Add Bot Message to Session"]
    AddBotMsg --> AppendHistory["Append to History<br/>(HistoryStore)"]
    AppendHistory --> SendResponse["Send Response to Discord"]
    SendResponse --> LogResponse["Log Response Audit"]
    LogResponse --> ExtractFacts["Extract Facts for RAG<br/>(FactExtractor via Groq)"]
    ExtractFacts --> IncrementCounter["Increment Backup Counter"]

    IncrementCounter --> CheckBackup{"Should Backup?<br/>(every 10 msgs or 1hr)"}
    CheckBackup -->|"Yes"| RunBackup["GitHub Backup"]
    CheckBackup -->|"No"| End["Done"]
    RunBackup --> End
```

## Slash Commands Flow

```mermaid
flowchart TD
    subgraph Commands["Slash Commands"]
        Ask["/ask"]
        Recall["/recall"]
        History["/history<br/>(manage_messages)"]
        Forget["/forget<br/>(manage_messages)"]
        Deleted["/deleted<br/>(manage_messages)"]
        Audit["/audit<br/>(manage_messages)"]
        Send["/send<br/>(manage_messages)"]
        Welcome["/welcome<br/>(manage_messages)"]
        OptIn["/optin"]
        OptOut["/optout"]
        MyStatus["/mystatus"]
        Analyze["/analyze"]
        Screenshot["/screenshot"]
        Read["/read"]
        Afk["/afk"]
        Unafk["/unafk"]
        Sholat["/sholat"]
        SholatKiblat["/sholat-kiblat"]
        SholatStatus["/sholat-status<br/>(admin)"]
        SholatSetChannel["/sholat-set-channel<br/>(admin)"]
        SholatSetRole["/sholat-set-role<br/>(admin)"]
        SholatSetCity["/sholat-set-city<br/>(admin)"]
    end

    Ask --> Defer1["Defer Response"]
    Recall --> Defer2["Defer Response"]
    History --> Defer3["Defer Response"]
    Deleted --> Defer4["Defer Response"]
    Audit --> Defer5["Defer Response"]
    Send --> Defer6["Defer Response"]
    Welcome --> Defer7["Defer Response"]

    Defer1 --> AskProcess["Process Question<br/>(Gemini + RAG + Tools)"]
    Defer2 --> RecallProcess["Query RAG + Groq"]
    Defer3 --> HistoryProcess["Get Session History"]
    Defer4 --> DeletedProcess["Get Deleted Logs"]
    Defer5 --> AuditProcess["Get Audit Logs"]
    Defer6 --> SendProcess["Send to Channel"]
    Defer7 --> WelcomeProcess["Send Welcome"]

    AskProcess --> AskResponse["Send Embed Response"]
    RecallProcess --> AskResponse
    HistoryProcess --> AskResponse
    DeletedProcess --> AskResponse
    AuditProcess --> AskResponse
    SendProcess --> Confirm["Send Confirmation"]
    WelcomeProcess --> Confirm
```

## Tool Execution Flow

```mermaid
flowchart TD
    ToolCall["Tool Call from Gemini"] --> ParseTool["Parse Tool Name & Args"]

    ParseTool --> ToolSwitch{"Tool Name"}

    ToolSwitch -->|"web_search"| TavilySearch["Tavily.search(query)"]
    ToolSwitch -->|"recall_memory"| RAGQuery["RagStore.get_all(channel_id)"]
    ToolSwitch -->|"get_history"| SessionQuery["SessionManager.get_history()"]
    ToolSwitch -->|"get_channel_info"| BotGetChannel["bot.get_channel(id)"]
    ToolSwitch -->|"get_user_info"| BotFetchUser["bot.fetch_user(id)"]
    ToolSwitch -->|"get_audit_logs"| AuthCheck{"Auth Check<br/>(channel+user required)"}
    ToolSwitch -->|"fetch_webpage"| FetchProviders{"Provider Order"}
    ToolSwitch -->|"screenshot_page"| ScreenshotProviders{"Provider Order"}
    ToolSwitch -->|"analyze_image"| VLMImage["Gemini VLM"]
    ToolSwitch -->|"get_online_users"| PresenceQuery["Guild.members loop"]
    ToolSwitch -->|"read_attachment"| ReadFile["File Cache Lookup"]
    ToolSwitch -->|"use_skill"| LoadSkill["Load .md → Gemini"]
    ToolSwitch -->|"list_skills"| ScanSkills["Scan skills/ dir"]

    AuthCheck -->|"OK"| AuditQuery["AuditLogger.get_logs()"]
    AuthCheck -->|"Denied"| AuthError["Return Error"]

    FetchProviders -->|"auto"| HBFirst["Hyperbrowser → Browserless"]
    FetchProviders -->|"hyperbrowser"| HBOnly["Hyperbrowser only"]
    FetchProviders -->|"browserless"| BLOnly["Browserless only"]

    HBFirst --> FetchContent["Fetch + Sanitize"]
    FetchContent --> FormatResult["Format Result"]

    ScreenshotProviders --> ScrHBFirst["Hyperbrowser → Browserless"]
    ScrHBFirst --> ScrScreenshot["Screenshot Page"]
    ScrScreenshot --> ScrVLM["VLM Analysis"]
    ScrVLM --> FormatResult

    TavilySearch --> FormatResult
    RAGQuery --> GroqRetrieve["Groq Retrieve Relevant"]
    GroqRetrieve --> FormatResult
    SessionQuery --> FormatResult
    BotGetChannel --> FormatResult
    BotFetchUser --> FormatResult
    AuditQuery --> FormatResult
    PresenceQuery --> FormatResult
    ReadFile --> FormatResult
    LoadSkill --> FormatResult
    ScanSkills --> FormatResult

    FormatResult --> ReturnResult["Return to Gemini"]
```

## Memory & Storage Flow

```mermaid
flowchart TD
    subgraph InMemory["In-Memory Storage"]
        SessionCache["Session Cache<br/>(channel_id → messages)"]
        MessageCache["Message Cache<br/>(message_id → data, LRU 500)"]
        FileCache["File Attachment Cache<br/>(channel_msg → contents, 100 max)"]
        TrackerCache["Tracker Dicts<br/>(channel → tool/response/fp, 200 max)"]
    end

    subgraph Persistent["Persistent Storage"]
        HistoryJSONL["data/history/*.jsonl<br/>(SHA1-hashed keys)"]
        MemoriesJSONL["data/memories/*.jsonl<br/>(with dedup + TTL)"]
        AuditJSONL["data/audit/audit.jsonl<br/>(UTC timestamps)"]
        SholatConfig["data/sholat_config.json"]
        PreferencesJSON["data/mentions/preferences.json"]
        GitRepo["data/.git (GitHub Backup)"]
    end

    subgraph Processes["Background Processes"]
        TTLPrune["TTL Prune<br/>(Daily at 3AM WIB)"]
        HistoryCleanup["History Cleanup<br/>(Weekly Sunday 4AM)"]
        BackupTrigger["Backup Trigger<br/>(Every 10 msgs / 1hr)"]
        SholatReminder["Sholat Reminder<br/>(Every 60s check)"]
    end

    MessageIn["New Message"] --> SessionCache
    MessageIn --> HistoryJSONL
    MessageIn --> AuditJSONL

    RAGExtract["RAG Extraction"] --> MemoriesJSONL

    TTLPrune --> MemoriesJSONL
    HistoryCleanup --> HistoryJSONL

    BackupTrigger --> GitRepo
    TTLPrune --> GitRepo

    SholatReminder --> SholatConfig
```

## Audit Logging Flow

```mermaid
flowchart TD
    subgraph Events["Logged Events"]
        MsgReceived["message_received"]
        MsgSent["response_sent"]
        MsgDeleted["message_deleted"]
        MsgEdited["message_edited"]
        PresenceUpdate["presence_update"]
        ToolCall["tool_call"]
        ToolResult["tool_result"]
        RAGExtract["rag_extract"]
        RAGRetrieve["rag_retrieve"]
        Compaction["compaction"]
        Backup["github_backup"]
        Error["error"]
        Startup["bot_startup"]
        Shutdown["bot_shutdown"]
        WelcomeSent["welcome_sent"]
        MemoryCleared["memory_cleared"]
        TTlPrune["ttl_prune"]
    end

    Events --> AuditFile["data/audit/audit.jsonl<br/>(thread-safe write, UTC timestamps)"]

    AuditFile --> DeletedCmd["/deleted Command<br/>(manage_messages)"]
    AuditFile --> AuditCmd["/audit Command<br/>(manage_messages)"]
    AuditFile --> GetAuditLogs["get_audit_logs Tool<br/>(auth required)"]
```

## GitHub Backup Flow

```mermaid
flowchart TD
    Init["init_repo()"] --> CheckGit{".git exists?"}

    CheckGit -->|"No"| GitInit["git init"]
    GitInit --> AddRemote["git remote add origin"]
    AddRemote --> GitConfig["git config user.name/email"]
    GitConfig --> CreateGitignore["Create .gitignore"]
    CreateGitignore --> InitialCommit["git add -A && commit"]
    InitialCommit --> SetMain["git branch -m main"]
    SetMain --> InitialPush["git push -u origin main"]

    CheckGit -->|"Yes"| UpdateRemote["git remote set-url origin"]
    UpdateRemote --> CheckCommits{"Has commits?"}

    CheckCommits -->|"No"| CreateCommit["Create initial commit"]
    CreateCommit --> SetMain
    CheckCommits -->|"Yes"| CheckBranch{"Branch = main?"}

    CheckBranch -->|"No"| RenameBranch["git branch -m main"]
    RenameBranch --> PushBranch["git push -u origin main"]
    CheckBranch -->|"Yes"| Ready["Ready for backup"]

    Backup["backup()"] --> ThreadGuard["threading.Lock guard"]
    ThreadGuard --> GitAdd["git add -A"]
    GitAdd --> GitStatus{"Changes?"}

    GitStatus -->|"No"| NoChange["No changes to backup"]
    GitStatus -->|"Yes"| GitCommit["git commit"]
    GitCommit --> GitPush["git push origin main"]
    GitPush --> LogSuccess["Log backup success"]
```

## Prompt Injection Protection (Browserless / Hyperbrowser)

```mermaid
flowchart TD
    FetchRequest["Fetch URL Request"] --> URLCheck{"URL Validation"}

    URLCheck -->|"Invalid Protocol"| BlockURL["Block: Only HTTP/HTTPS"]
    URLCheck -->|"Private/Reserved IP"| BlockIP["Block: Private IP<br/>(ipaddress stdlib)"]
    URLCheck -->|"IPv6 mapped"| StripBrackets["Strip brackets + check mapped IPv4"]
    URLCheck -->|"Single-label host"| BlockHost["Block: Invalid Host"]
    URLCheck -->|"Valid URL"| DNSCheck{"DNS Rebinding<br/>Check"}

    DNSCheck -->|"Unsafe resolve"| BlockDNS["Block: DNS resolved to private IP"]
    DNSCheck -->|"Safe resolve"| FetchContent["Fetch via Provider"]

    FetchContent --> RemoveScript["Remove <script> tags"]
    RemoveScript --> RemoveStyle["Remove <style> tags"]
    RemoveStyle --> RemoveIframe["Remove <iframe> tags"]
    RemoveIframe --> RemoveHTML["Remove HTML tags"]
    RemoveHTML --> DecodeEntities["Decode HTML entities"]
    DecodeEntities --> CheckInjection{"Injection Patterns?"}

    CheckInjection -->|"Detected"| FilterContent["Filter Suspicious Content"]
    CheckInjection -->|"Clean"| LimitLength["Limit to 15K chars"]
    FilterContent --> LimitLength

    LimitLength --> ReturnSafe["Return Sanitized Content"]
```

## VLM (Vision Language Model) Flow

```mermaid
flowchart TD
    ImgAttach["Image Attachment"] --> ExtractImages["Extract Image Attachments<br/>(max 3 per message)"]
    ExtractImages --> Download["Download in Parallel<br/>(aiohttp)"]
    Download --> Analyze["Gemini VLM Analysis<br/>(parallel via gather)"]
    Analyze --> Inject["Inject into Prompt"]

    URLImg["Image URL"] --> FetchURL["/analyze or /screenshot"]
    FetchURL --> Screenshot["Browserless/Hyperbrowser<br/>Screenshot"]
    Screenshot --> VLMAnalysis["Gemini VLM Analysis"]
    VLMAnalysis --> SendResponse["Send Response"]
```

## Sholat Auto-Reminder Flow

```mermaid
flowchart TD
    PruneLoop["prune_loop (every 60s)"] --> CheckReminder["_check_sholat_reminder(now_wib)"]

    CheckReminder --> LoadConfig{"Sholat enabled?"}
    LoadConfig -->|"No"| Skip["Skip"]
    LoadConfig -->|"Yes"| CheckDate{"Date changed?"}

    CheckDate -->|"Yes"| ResetState["Reset reminded set"]
    CheckDate -->|"No"| FetchSchedule
    ResetState --> FetchSchedule

    FetchSchedule{"Schedule cached?"}
    FetchSchedule -->|"No"| APICall["Fetch from myQuran/AlAdhan"]
    FetchSchedule -->|"Yes"| CompareTimes
    APICall --> CompareTimes

    CompareTimes["Compare prayer times (WIB)"] --> WindowCheck{"In reminder window?<br/>(N min before)"}

    WindowCheck -->|"Yes"| GenerateMsg["Generate Gemini reminder<br/>(tsundere style)"]
    GenerateMsg --> AddRoleMention{"Role configured?"}
    AddRoleMention -->|"Yes"| MentionRole["Add <@&ROLE_ID>"]
    AddRoleMention -->|"No"| SendMsg
    MentionRole --> SendMsg

    SendMsg["Send to channel"] --> LogReminder["Log to audit"]

    WindowCheck -->|"No"| NextPrayer["Check next prayer"]
    NextPrayer --> CompareTimes
```

## Gemini API Key Rotation & Model Fallback

```mermaid
flowchart TD
    Request["API Request"] --> CheckKeys{"Keys configured?"}
    CheckKeys -->|"No"| RaiseError["Raise ValueError"]

    CheckKeys -->|"Yes"| ModelLoop["For each model in chain"]
    ModelLoop --> PrimaryModel["Primary Model"]
    PrimaryModel --> KeyLoop["For each API key"]

    KeyLoop --> TryKey["Try Current Key"]
    TryKey --> Success{"Success?"}

    Success -->|"Yes"| ReturnResponse["Return Response"]
    Success -->|"404 NOT_FOUND"| NextModel["Try Next Model"]
    Success -->|"429/503 Rate Limit"| WaitRetry["Wait exponential backoff"]
    Success -->|"Other Error"| Raise["Raise Error"]

    WaitRetry --> RetryKey{"More keys?"}
    RetryKey -->|"Yes"| KeyLoop
    RetryKey -->|"No"| NextModel

    NextModel --> MoreModels{"More models?"}
    MoreModels -->|"Yes"| ModelLoop
    MoreModels -->|"No"| AllFailed["Raise Last Error"]
```
