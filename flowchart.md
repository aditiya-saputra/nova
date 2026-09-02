# Nova Discord Bot - Full Flowchart

## System Architecture

```mermaid
flowchart TB
    subgraph External["External Services"]
        DiscordAPI["Discord API"]
        GeminiAPI["Google Gemini API"]
        GroqAPI["Groq API"]
        TavilyAPI["Tavily API"]
        BrowserlessAPI["Browserless API"]
        GitHubAPI["GitHub API"]
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
        BrowserlessClient["services/browserless_client.py"]
        ToolExecutor["services/tool_executor.py"]
    end

    subgraph Memory["Memory Layer"]
        SessionManager["memory/session_manager.py"]
        HistoryStore["memory/history_store.py"]
        RagStore["memory/rag_store.py"]
        CompactionEngine["memory/compaction_engine.py"]
        AuditLogger["memory/audit_logger.py"]
        GitHubBackup["memory/github_backup.py"]
        ScheduledJobs["memory/scheduled_jobs.py"]
    end

    subgraph Cogs["Cogs (Discord Commands)"]
        AICogs["cogs/ai_commands.py"]
        AdminCogs["cogs/admin_commands.py"]
        DynamicPresence["cogs/dynamic_presence.py"]
        SlashCommands["cogs/slash_commands.py"]
    end

    subgraph Config["Configuration"]
        Settings["config/settings.py"]
        Personality["config/prompts/personality.txt"]
        Prefixes["config/prefixes.json"]
    end

    Main --> Bot
    Main --> Services
    Main --> Memory
    Main --> Cogs
    Main --> Config

    Bot --> DiscordAPI
    Bot --> EventHandler
    Bot --> MessageRouter

    GeminiClient --> GeminiAPI
    GroqClient --> GroqAPI
    TavilyClient --> TavilyAPI
    BrowserlessClient --> BrowserlessAPI
    GitHubBackup --> GitHubAPI

    ToolExecutor --> GeminiClient
    ToolExecutor --> GroqClient
    ToolExecutor --> TavilyClient
    ToolExecutor --> BrowserlessClient

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
    
    CleanPrefix --> ExtractContent
    CleanMention --> ExtractContent
    CleanReply --> ExtractContent
    
    ExtractContent["Extract Content"] --> LogAudit["Log to Audit"]
    LogAudit --> DetectURL{"Detect URLs?"}
    
    DetectURL -->|"Yes"| StoreURLs["Store URLs in Metadata"]
    DetectURL -->|"No"| ContinueProcess
    StoreURLs --> ContinueProcess
    
    ContinueProcess --> LoadRAG["Load RAG Nuggets"]
    LoadRAG --> RetrieveRelevant["Retrieve Relevant Facts"]
    RetrieveRelevant --> CompactCheck{"Check Compaction"}
    
    CompactCheck -->|"Above Threshold"| RunCompaction["Run Compaction"]
    CompactCheck -->|"Below Threshold"| SkipCompaction
    RunCompaction --> SkipCompaction
    
    SkipCompaction --> AddUserMsg["Add User Message to Session"]
    AddUserMsg --> BuildSystem["Build System Prompt"]
    BuildSystem --> CallGemini["Call Gemini with Tools"]
    
    CallGemini --> GeminiDecision{"Gemini Response"}
    
    GeminiDecision -->|"Text Response"| DirectResponse
    GeminiDecision -->|"Tool Call"| ExecuteTool["Execute Tool"]
    
    ExecuteTool --> ToolType{"Tool Type"}
    
    ToolType -->|"web_search"| WebSearch["Tavily Search"]
    ToolType -->|"recall_memory"| RecallMemory["RAG Recall"]
    ToolType -->|"get_history"| GetHistory["Session History"]
    ToolType -->|"get_channel_info"| ChannelInfo["Discord Channel"]
    ToolType -->|"get_user_info"| UserInfo["Discord User"]
    ToolType -->|"get_audit_logs"| AuditLogs["Audit Logger"]
    ToolType -->|"fetch_webpage"| FetchPage["Browserless Fetch"]
    ToolType -->|"get_online_users"| OnlineUsers["Discord Presence"]
    
    WebSearch --> Synthesize["Synthesize with Tool Result"]
    RecallMemory --> Synthesize
    GetHistory --> Synthesize
    ChannelInfo --> Synthesize
    UserInfo --> Synthesize
    AuditLogs --> Synthesize
    FetchPage --> Synthesize
    OnlineUsers --> Synthesize
    
    Synthesize --> DirectResponse["Get Final Response"]
    
    DirectResponse --> AddBotMsg["Add Bot Message to Session"]
    AddBotMsg --> AppendHistory["Append to History"]
    AppendHistory --> SendResponse["Send Response to Discord"]
    SendResponse --> LogResponse["Log Response Audit"]
    LogResponse --> ExtractFacts["Extract Facts for RAG"]
    ExtractFacts --> SaveNugget["Save Nugget to RAG"]
    SaveNugget --> IncrementCounter["Increment Backup Counter"]
    IncrementCounter --> CheckBackup{"Should Backup?"}
    
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
        History["/history"]
        Deleted["/deleted"]
        Audit["/audit"]
        Send["/send"]
        Welcome["/welcome"]
    end

    Ask --> Defer1["Defer Response"]
    Recall --> Defer2["Defer Response"]
    History --> Defer3["Defer Response"]
    Deleted --> Defer4["Defer Response"]
    Audit --> Defer5["Defer Response"]
    Send --> Defer6["Defer Response"]
    Welcome --> Defer7["Defer Response"]

    Defer1 --> AskProcess["Process Question"]
    Defer2 --> RecallProcess["Query RAG"]
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
    ToolSwitch -->|"get_audit_logs"| AuditQuery["AuditLogger.get_logs()"]
    ToolSwitch -->|"fetch_webpage"| BrowserlessFetch["BrowserlessClient.fetch()"]
    ToolSwitch -->|"get_online_users"| PresenceQuery["Guild.members loop"]
    
    TavilySearch --> FormatResult["Format Result"]
    RAGQuery --> GroqRetrieve["Groq Retrieve Relevant"]
    GroqRetrieve --> FormatResult
    SessionQuery --> FormatResult
    BotGetChannel --> FormatResult
    BotFetchUser --> FormatResult
    AuditQuery --> FormatResult
    BrowserlessFetch --> Sanitize["Sanitize Content"]
    Sanitize --> FormatResult
    PresenceQuery --> FormatResult
    
    FormatResult --> ReturnResult["Return to Gemini"]
```

## Memory & Storage Flow

```mermaid
flowchart TD
    subgraph InMemory["In-Memory Storage"]
        SessionCache["Session Cache<br/>(channel_id → messages)"]
        MessageCache["Message Cache<br/>(message_id → data)"]
    end

    subgraph Persistent["Persistent Storage"]
        HistoryJSONL["data/history/*.jsonl"]
        MemoriesJSONL["data/memories/*.jsonl"]
        AuditJSONL["data/audit/audit.jsonl"]
        GitRepo["data/.git (GitHub Backup)"]
    end

    subgraph Processes["Background Processes"]
        TTLPrune["TTL Prune<br/>(Daily at 3AM)"]
        HistoryCleanup["History Cleanup<br/>(Optional)"]
        BackupTrigger["Backup Trigger<br/>(Every 10 msgs / 1hr)"]
    end

    MessageIn["New Message"] --> SessionCache
    MessageIn --> HistoryJSONL
    MessageIn --> AuditJSONL
    
    RAGExtract["RAG Extraction"] --> MemoriesJSONL
    
    TTLPrune --> MemoriesJSONL
    HistoryCleanup --> HistoryJSONL
    
    BackupTrigger --> GitRepo
    TTLPrune --> GitRepo
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
    end

    Events --> AuditFile["data/audit/audit.jsonl"]
    
    AuditFile --> DeletedCmd["/deleted Command"]
    AuditFile --> AuditCmd["/audit Command"]
    AuditFile --> GetAuditLogs["get_audit_logs Tool"]
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
    InitialCommit --> SetMain["git branch -M main"]
    SetMain --> InitialPush["git push -u origin main"]
    
    CheckGit -->|"Yes"| UpdateRemote["git remote set-url origin"]
    UpdateRemote --> CheckCommits{"Has commits?"}
    
    CheckCommits -->|"No"| CreateCommit["Create initial commit"]
    CreateCommit --> SetMain
    CheckCommits -->|"Yes"| CheckBranch{"Branch = main?"}
    
    CheckBranch -->|"No"| RenameBranch["git branch -M main"]
    RenameBranch --> PushBranch["git push -u origin main"]
    CheckBranch -->|"Yes"| Ready["Ready for backup"]
    
    Backup["backup()"] --> GitAdd["git add -A"]
    GitAdd --> GitStatus{"Changes?"}
    
    GitStatus -->|"No"| NoChange["No changes to backup"]
    GitStatus -->|"Yes"| GitCommit["git commit"]
    GitCommit --> GitPush["git push origin main"]
    GitPush --> LogSuccess["Log backup success"]
```

## Prompt Injection Protection (Browserless)

```mermaid
flowchart TD
    FetchRequest["Fetch URL Request"] --> URLCheck{"URL Validation"}
    
    URLCheck -->|"Invalid Protocol"| BlockURL["Block: Only HTTP/HTTPS"]
    URLCheck -->|"Private IP"| BlockIP["Block: Private IP"]
    URLCheck -->|"Invalid Hostname"| BlockHost["Block: Invalid Host"]
    URLCheck -->|"Valid URL"| FetchContent["Fetch via Browserless"]
    
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

## Presence Tracking Flow

```mermaid
flowchart TD
    StatusChange["User Status Change"] --> PresenceEvent["on_presence_update"]
    
    PresenceEvent --> LogPresence["Log to Audit"]
    LogPresence --> CheckOnline{"Status = Online?"}
    
    CheckOnline -->|"Yes"| LogUserOnline["Log user_online event"]
    CheckOnline -->|"No"| LogUserOffline["Log user_offline event"]
    
    LogUserOnline --> UseWelcomeCmd["Use /welcome command"]
    LogUserOffline --> End["Done"]
```

## Gemini API Key Rotation

```mermaid
flowchart TD
    Request["API Request"] --> KeyIndex["Current Key Index"]
    
    KeyIndex --> TryKey["Try Current Key"]
    TryKey --> Success{"Success?"}
    
    Success -->|"Yes"| ReturnResponse["Return Response"]
    Success -->|"Rate Limited/503"| NextKey["Increment Key Index"]
    NextKey --> WaitForRetry["Wait 1.5s"]
    WaitForRetry --> RetryCount{"Retries < 5?"}
    
    RetryCount -->|"Yes"| TryKey
    RetryCount -->|"No"| ReturnError["Return Error"]
```
