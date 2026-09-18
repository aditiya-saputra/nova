import json
import re
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)

# Skills directory — scan semua .md file
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _clamp_int(val, default, min_val=1, max_val=50):
    try:
        v = int(val)
        return max(min_val, min(v, max_val))
    except (TypeError, ValueError):
        return default


class ToolExecutor:
    def __init__(self, bot):
        self.bot = bot
        self.tools = self._define_tools()

    def _define_tools(self):
        return [
            {
                "name": "web_search",
                "description": "Search the web for real-time information using Tavily API",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "recall_memory",
                "description": "Recall stored memories and facts from this channel's Micro-RAG",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query to find relevant memories"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of memories to return (default: 5)"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "get_history",
                "description": "Get conversation history for the current channel",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Number of messages to retrieve (default: 10)"
                        }
                    }
                }
            },
            {
                "name": "get_channel_info",
                "description": "Get information about the current Discord channel",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_user_info",
                "description": "Get information about a specific user",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "The user ID to look up"
                        }
                    },
                    "required": ["user_id"]
                }
            },
            {
                "name": "get_audit_logs",
                "description": "Get audit logs from Discord server. Use this when user asks about deleted messages, edited messages, tool calling history, or bot activity logs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_type": {
                            "type": "string",
                            "description": "Event type filter: message_deleted, message_edited, tool_call, tool_result, error, all (default: all)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of logs to retrieve (default: 10)"
                        }
                    }
                }
            },
            {
                "name": "fetch_webpage",
                "description": "Fetch and extract content from a URL. Use this when user shares a link and asks about its content, or asks questions about a specific webpage. Content is sanitized for safety.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to fetch (must be http or https)"
                        }
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "get_online_users",
                "description": "Get list of online/offline users in the server. Use when user asks who's online, who's offline, or about user status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status_filter": {
                            "type": "string",
                            "description": "Filter by status: online, idle, dnd, offline, all (default: all)"
                        }
                    }
                }
            },
            {
                "name": "analyze_image",
                "description": "Analyze an image from a URL. Use this when user shares an image URL and asks to analyze, describe, or explain it. Returns detailed analysis of the image content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The image URL to analyze (must be http or https)"
                        },
                        "question": {
                            "type": "string",
                            "description": "Optional specific question about the image"
                        }
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "screenshot_page",
                "description": "Take a screenshot of a webpage and analyze it visually. Use this when user asks to see or analyze how a webpage looks. Returns visual analysis of the page.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to screenshot and analyze"
                        },
                        "question": {
                            "type": "string",
                            "description": "Optional specific question about the screenshot"
                        }
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "use_skill",
                "description": (
                    "Gunakan skill/specialist untuk menjawab pertanyaan user. "
                    "Skill berisi pengetahuan khusus (EYD, translate, code review, dll). "
                    "Pilih skill yang paling relevan dengan pertanyaan user."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": (
                                "Nama skill yang akan digunakan. "
                                "Gunakan list_skills untuk melihat semua skill yang tersedia."
                            )
                        },
                        "query": {
                            "type": "string",
                            "description": "Pertanyaan atau instruksi yang akan diproses dengan skill ini"
                        }
                    },
                    "required": ["skill_name", "query"]
                }
            },
            {
                "name": "list_skills",
                "description": (
                    "Lihat semua skill/specialist yang tersedia di sistem. "
                    "Gunakan sebelum use_skill untuk mengetahui skill apa saja yang ada."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "read_attachment",
                "description": (
                    "Baca isi file attachment yang di-upload user di pesan ini. "
                    "Gunakan saat user upload file dan minta dibaca, direview, atau dianalisis. "
                    "Mendukung file code (.py, .js, .ts, dll), data (.json, .yaml, .csv), "
                    "dan text (.txt, .md). Tidak mendukung gambar (gunakan VLM)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": (
                                "Nama file attachment yang ingin dibaca. "
                                "Gunakan filename yang persis sama dengan yang terlihat di pesan."
                            )
                        }
                    },
                    "required": ["filename"]
                }
            }
        ]

    def get_tools_for_gemini(self):
        return self.tools

    async def execute(self, tool_name, parameters, channel_id=None, user_id=None):
        try:
            if not isinstance(parameters, dict):
                parameters = {}

            if tool_name == "web_search":
                return await self._web_search(parameters.get("query", ""))
            elif tool_name == "recall_memory":
                limit = _clamp_int(parameters.get("limit", 5), 5, 1, 20)
                return await self._recall_memory(
                    parameters.get("query", ""),
                    channel_id,
                    limit
                )
            elif tool_name == "get_history":
                limit = _clamp_int(parameters.get("limit", 10), 10, 1, 30)
                return await self._get_history(
                    channel_id,
                    limit
                )
            elif tool_name == "get_channel_info":
                return await self._get_channel_info(channel_id)
            elif tool_name == "get_user_info":
                return await self._get_user_info(parameters.get("user_id", ""))
            elif tool_name == "get_audit_logs":
                limit = _clamp_int(parameters.get("limit", 10), 10, 1, 20)
                return await self._get_audit_logs(
                    parameters.get("event_type", "all"),
                    limit,
                    channel_id=channel_id,
                    user_id=user_id,
                )
            elif tool_name == "fetch_webpage":
                return await self._fetch_webpage(parameters.get("url", ""))
            elif tool_name == "get_online_users":
                return await self._get_online_users(
                    parameters.get("status_filter", "all"),
                    channel_id=channel_id,
                )
            elif tool_name == "analyze_image":
                return await self._analyze_image(
                    parameters.get("url", ""),
                    parameters.get("question", "Deskripsikan gambar ini secara detail.")
                )
            elif tool_name == "screenshot_page":
                return await self._screenshot_page(
                    parameters.get("url", ""),
                    parameters.get("question", "Analisis tampilan halaman ini.")
                )
            elif tool_name == "use_skill":
                return await self._use_skill(
                    parameters.get("skill_name", ""),
                    parameters.get("query", "")
                )
            elif tool_name == "list_skills":
                return await self._list_skills()
            elif tool_name == "read_attachment":
                return await self._read_attachment(
                    parameters.get("filename", ""),
                    channel_id=channel_id,
                )
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Tool execution error: {tool_name} - {e}")
            return {"error": "Tool execution failed"}

    async def _web_search(self, query):
        tavily = self.bot.tavily
        if not tavily:
            return {"error": "Tavily not configured"}

        result = await tavily.search(query)
        if result:
            return {
                "answer": result.get("answer", ""),
                "results": result.get("results", [])[:3]
            }
        return {"error": "Search failed"}

    async def _recall_memory(self, query, channel_id, limit=5):
        rag_store = self.bot.rag_store
        if not channel_id:
            return {"error": "No channel ID"}

        nuggets = await rag_store.aget_all(channel_id)
        if not nuggets:
            return {"memories": [], "count": 0}

        if query:
            groq = self.bot.groq
            nuggets_text = "\n".join(
                f"- {n.get('fact', '')} (by user {n.get('user_id', 'N/A')})"
                for n in nuggets
            )
            retrieve_prompt = f"Query: {query}\n\nMemories:\n{nuggets_text}\n\nSelect the {limit} most relevant. Output JSON array of facts."
            try:
                response_text = await groq.retrieve_relevant(retrieve_prompt)
                relevant = json.loads(response_text.strip().strip("```json").strip("```"))
                if isinstance(relevant, list):
                    return {"memories": relevant[:limit], "count": len(relevant)}
            except Exception:
                pass

        return {
            "memories": [n.get("fact", "") for n in nuggets[:limit]],
            "count": len(nuggets)
        }

    async def _get_history(self, channel_id, limit=10):
        session_manager = self.bot.session_manager
        if not channel_id:
            return {"error": "No channel ID"}

        channel_key = f"channel_{channel_id}"
        history = session_manager.get_history(channel_key)

        return {
            "messages": history[-limit:],
            "count": len(history)
        }

    async def _get_channel_info(self, channel_id):
        if not channel_id:
            return {"error": "No channel ID"}

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return {"error": "Channel not found"}

        return {
            "name": channel.name,
            "id": channel.id,
            "type": str(channel.type),
            "guild": channel.guild.name if channel.guild else "DM",
            "member_count": getattr(channel.guild, "member_count", None) if channel.guild else None
        }

    async def _get_user_info(self, user_id):
        try:
            if not str(user_id).isdigit():
                return {"error": "Invalid user ID"}
            user = await self.bot.fetch_user(int(user_id))
            return {
                "name": user.name,
                "display_name": user.display_name,
                "id": user.id,
                "bot": user.bot,
                "created_at": user.created_at.isoformat()
            }
        except Exception:
            return {"error": "User not found"}

    async def _get_audit_logs(self, event_type="all", limit=10, channel_id=None, user_id=None):
        audit_logger = self.bot.audit_logger
        if not audit_logger:
            return {"error": "Audit logger not configured"}

        # Otorisasi: WAJIB ada channel_id DAN user_id, dan harus moderator/admin
        if not channel_id or not user_id:
            return {"error": "Akses ditolak: channel_id dan user_id diperlukan untuk otorisasi."}

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return {"error": "Channel not found"}

        if not getattr(channel, "guild", None):
            return {"error": "Akses ditolak: hanya di server Discord."}

        member = channel.guild.get_member(user_id)
        if not member or not (member.guild_permissions.manage_messages or member.guild_permissions.administrator):
            return {"error": "Akses ditolak: hanya moderator atau admin yang dapat membaca audit logs."}

        allowed_events = {"all", "message_deleted", "message_edited", "tool_call", "tool_result", "error"}
        if event_type not in allowed_events:
            event_type = "all"

        if event_type == "all":
            logs = await audit_logger.aget_recent_logs(limit=limit)
        else:
            logs = await audit_logger.aget_logs_by_type(event_type, limit=limit)

        if not logs:
            return {"logs": [], "count": 0, "message": "No audit logs found"}

        formatted = []
        for log in logs:
            event = log.get("event", "unknown")
            timestamp = log.get("timestamp", "")[:19]
            data = log.get("data", {})

            if event == "message_deleted":
                formatted.append({
                    "event": event,
                    "timestamp": timestamp,
                    "user": data.get("user_name", "N/A"),
                    "channel": data.get("channel_name", "N/A"),
                    "content": data.get("content", "")[:200],
                })
            elif event == "message_edited":
                formatted.append({
                    "event": event,
                    "timestamp": timestamp,
                    "user": data.get("user_name", "N/A"),
                    "old": data.get("old_content", "")[:100],
                    "new": data.get("new_content", "")[:100],
                })
            elif event == "tool_call":
                formatted.append({
                    "event": event,
                    "timestamp": timestamp,
                    "user": data.get("user_name", "N/A"),
                    "tool": data.get("tool_name", "N/A"),
                    "args": data.get("tool_args", {}),
                })
            elif event == "tool_result":
                formatted.append({
                    "event": event,
                    "timestamp": timestamp,
                    "tool": data.get("tool_name", "N/A"),
                    "success": data.get("success", "N/A"),
                    "result_length": data.get("result_length", 0),
                })
            elif event == "error":
                formatted.append({
                    "event": event,
                    "timestamp": timestamp,
                    "type": data.get("error_type", "N/A"),
                    "message": data.get("error_message", "")[:150],
                })
            else:
                formatted.append({
                    "event": event,
                    "timestamp": timestamp,
                    "data": data,
                })

        return {"logs": formatted, "count": len(formatted)}

    def _fetch_providers(self):
        """Urutan provider fetch/screenshot berdasar FETCH_PROVIDER.

        auto (default): hyperbrowser dulu, fallback browserless.
        """
        mode = (getattr(getattr(self.bot, "settings", None), "FETCH_PROVIDER", "auto") or "auto").lower()
        hb = getattr(self.bot, "hyperbrowser", None)
        bl = getattr(self.bot, "browserless", None)
        hb_ok = bool(hb and getattr(hb, "enabled", False))
        bl_ok = bool(bl and getattr(bl, "enabled", False))
        if mode == "hyperbrowser":
            return [p for p in (hb,) if hb_ok]
        if mode == "browserless":
            return [p for p in (bl,) if bl_ok]
        ordered = []
        if hb_ok:
            ordered.append(hb)
        if bl_ok:
            ordered.append(bl)
        return ordered

    async def _fetch_webpage(self, url):
        if not url:
            return {"error": "No URL provided"}

        providers = self._fetch_providers()
        if not providers:
            return {"error": "No fetch provider configured (Hyperbrowser/Browserless)"}

        last = None
        for provider in providers:
            result = await provider.fetch_with_retry(url)
            if result.get("success"):
                return result
            last = result
            logger.warning(f"Fetch via {type(provider).__name__} failed, trying next: {result.get('error')}")
        return last or {"error": "All fetch providers failed"}

    async def _get_online_users(self, status_filter="all", channel_id=None):
        status_map = {
            "online": "online",
            "idle": "idle",
            "dnd": "dnd",
            "offline": "offline",
        }

        users_by_status = {
            "online": [],
            "idle": [],
            "dnd": [],
            "offline": [],
        }

        guilds = []
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel and getattr(channel, "guild", None):
                guilds = [channel.guild]
        if not guilds:
            guilds = list(self.bot.guilds)[:1]

        MAX_PER_STATUS = 25
        for guild in guilds:
            for member in guild.members:
                if member.bot:
                    continue

                status = str(member.status)
                if status in users_by_status and len(users_by_status[status]) < MAX_PER_STATUS:
                    users_by_status[status].append({
                        "name": member.display_name,
                        "id": member.id,
                        "status": status,
                        "activity": str(member.activity.name) if member.activity else None,
                    })

        if status_filter != "all" and status_filter in users_by_status:
            filtered = users_by_status[status_filter]
            return {
                "users": filtered,
                "count": len(filtered),
                "filter": status_filter
            }

        total = sum(len(v) for v in users_by_status.values())
        return {
            "users": {k: v for k, v in users_by_status.items() if v},
            "total": total,
            "summary": {k: len(v) for k, v in users_by_status.items()}
        }

    async def _analyze_image(self, url, question="Deskripsikan gambar ini secara detail."):
        browserless = self.bot.browserless
        gemini = self.bot.gemini

        if not browserless:
            return {"error": "Browserless not configured"}
        if not gemini:
            return {"error": "Gemini not configured"}
        if not url:
            return {"error": "No URL provided"}

        result = await browserless.fetch_image(url)
        if not result.get("success"):
            return {"error": result.get("error", "Failed to fetch image")}

        try:
            response = await gemini.generate_with_images(
                prompt=question,
                images=[{
                    "mime_type": result["mime_type"],
                    "data": result["data"]
                }]
            )
            return {"analysis": response, "url": url, "size": result.get("size", 0)}
        except Exception as e:
            logger.error(f"VLM analyze_image error: {e}")
            return {"error": f"Analysis failed: {str(e)}"}

    async def _screenshot_page(self, url, question="Analisis tampilan halaman ini."):
        gemini = self.bot.gemini

        if not gemini:
            return {"error": "Gemini not configured"}
        if not url:
            return {"error": "No URL provided"}

        providers = self._fetch_providers()
        if not providers:
            return {"error": "No screenshot provider configured (Hyperbrowser/Browserless)"}

        last = None
        for provider in providers:
            result = await provider.screenshot_page(url)
            if result.get("success"):
                break
            last = result
            logger.warning(f"Screenshot via {type(provider).__name__} failed, trying next: {result.get('error')}")
        else:
            return last or {"error": "All screenshot providers failed"}
        if not result.get("success"):
            return {"error": result.get("error", "Failed to take screenshot")}

        try:
            response = await gemini.generate_with_images(
                prompt=question,
                images=[{
                    "mime_type": "image/png",
                    "data": result["data"]
                }]
            )
            return {"analysis": response, "url": url}
        except Exception as e:
            logger.error(f"VLM screenshot_page error: {e}")
            return {"error": f"Analysis failed: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════
    # SKILL TOOLS
    # ═══════════════════════════════════════════════════════════════

    async def _list_skills(self):
        """List semua skill (.md files) yang tersedia di skills/ directory."""
        if not SKILLS_DIR.exists():
            return {"skills": [], "count": 0, "message": "Skills directory not found"}

        skills = []
        for f in sorted(SKILLS_DIR.glob("*.md")):
            # Extract name from filename: eyd_helper.md → eyd_helper
            name = f.stem
            # Try to extract display name from first heading
            try:
                content = f.read_text(encoding="utf-8")
                for line in content.splitlines():
                    if line.startswith("# "):
                        # "# Skill: EYD Helper — ..." → "EYD Helper"
                        display = line.lstrip("# ").strip()
                        if display.startswith("Skill:"):
                            display = display[len("Skill:"):].strip()
                        # Cut at " —" if present
                        if " —" in display:
                            display = display.split(" —")[0].strip()
                        break
                else:
                    display = name.replace("_", " ").title()
            except Exception:
                display = name.replace("_", " ").title()

            skills.append({
                "name": name,
                "display_name": display,
                "file": f.name,
            })

        return {
            "skills": skills,
            "count": len(skills),
            "message": f"{len(skills)} skill(s) available"
        }

    async def _read_attachment(self, filename, channel_id=None):
        """Baca isi file attachment dari cache yang di-populate FileProcessor.

        File content di-cache per-message oleh MessageHandler saat pesan diterima.
        Tool ini memungkinkan Gemini request file spesifik dari attachment yang sama.
        """
        if not filename:
            return {"error": "No filename provided"}

        # Cari di file cache (di-populate oleh MessageHandler)
        file_cache = getattr(self.bot, "_file_attachment_cache", {})
        if not file_cache:
            return {"error": "No file attachments available. Upload a file and ask me to read it."}

        # Filter cache berdasarkan channel_id untuk mencegah kebocoran file lintas channel/server
        target_cache = {}
        if channel_id:
            channel_prefix = f"{channel_id}_"
            for k, v in file_cache.items():
                if str(k).startswith(channel_prefix):
                    target_cache[k] = v
        else:
            target_cache = file_cache

        # Cache dict mempertahankan insertion order; entry terakhir adalah message terbaru.
        found_in = None
        found_fc = None
        for key, files in reversed(list(target_cache.items())):
            for fc in files:
                if fc.get("filename") == filename:
                    found_in = key
                    found_fc = fc
                    break
            if found_fc:
                break

        if found_fc:
            content = found_fc.get("content", "")
            truncated = found_fc.get("truncated", False)
            result = {
                "filename": filename,
                "content": content,
                "size": found_fc.get("size", 0),
            }
            if truncated:
                result["note"] = "File content was truncated due to size limit."
            return result

        available = []
        for files in target_cache.values():
            for fc in files:
                available.append(fc.get("filename", ""))
        return {
            "error": f"File '{filename}' not found",
            "available_files": list(set(available)),
        }

    async def _use_skill(self, skill_name, query):
        """Load skill .md file dan proses query dengan Gemini menggunakan skill sebagai context."""
        if not skill_name:
            return {"error": "No skill name provided"}

        if not query:
            return {"error": "No query provided"}

        if not re.match(r'^[a-zA-Z0-9_\-]+$', skill_name):
            return {"error": "Invalid skill name"}

        # Load skill file
        skill_path = SKILLS_DIR / f"{skill_name}.md"
        if not skill_path.resolve().is_relative_to(SKILLS_DIR.resolve()):
            return {"error": "Invalid skill name"}
        if not skill_path.exists():
            # List available skills for error message
            available = [f.stem for f in SKILLS_DIR.glob("*.md")] if SKILLS_DIR.exists() else []
            return {
                "error": f"Skill '{skill_name}' not found",
                "available_skills": available
            }

        try:
            skill_content = skill_path.read_text(encoding="utf-8")
        except Exception as e:
            return {"error": f"Failed to read skill file: {str(e)}"}

        # Process with Gemini
        gemini = self.bot.gemini
        if not gemini:
            return {"error": "Gemini not configured"}

        prompt = f"""Kamu adalah assistant yang menggunakan skill/specialist berikut untuk menjawab.

=== SKILL CONTENT ===
{skill_content}
=== END SKILL ===

Pertanyaan/instruksi user:
{query}

Instruksi:
1. Gunakan pengetahuan dari skill di atas untuk menjawab pertanyaan user.
2. Berikan jawaban yang lengkap, akurat, dan terstruktur.
3. Gunakan format markdown untuk tabel, bold, dan code block.
4. Jika pertanyaan di luar cakupan skill, tetap jawab dengan pengetahuan umummu."""

        try:
            response = await gemini.generate(
                prompt,
                system_instruction="Kamu adalah assistant yang ahli dalam bidangnya. Jawab dalam Bahasa Indonesia yang baku."
            )
            return {
                "success": True,
                "skill_used": skill_name,
                "query": query,
                "response": response
            }
        except Exception as e:
            return {"error": f"Gemini processing failed: {str(e)}"}
