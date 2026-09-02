import json
from utils.logger import get_logger

logger = get_logger(__name__)


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
            }
        ]

    def get_tools_for_gemini(self):
        return self.tools

    async def execute(self, tool_name, parameters, channel_id=None, user_id=None):
        try:
            if tool_name == "web_search":
                return await self._web_search(parameters.get("query", ""))
            elif tool_name == "recall_memory":
                return await self._recall_memory(
                    parameters.get("query", ""),
                    channel_id,
                    parameters.get("limit", 5)
                )
            elif tool_name == "get_history":
                return await self._get_history(
                    channel_id,
                    parameters.get("limit", 10)
                )
            elif tool_name == "get_channel_info":
                return await self._get_channel_info(channel_id)
            elif tool_name == "get_user_info":
                return await self._get_user_info(parameters.get("user_id", ""))
            elif tool_name == "get_audit_logs":
                return await self._get_audit_logs(
                    parameters.get("event_type", "all"),
                    parameters.get("limit", 10)
                )
            elif tool_name == "fetch_webpage":
                return await self._fetch_webpage(parameters.get("url", ""))
            elif tool_name == "get_online_users":
                return await self._get_online_users(
                    parameters.get("status_filter", "all")
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
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Tool execution error: {tool_name} - {e}")
            return {"error": str(e)}

    async def _web_search(self, query):
        tavily = self.bot.tavily
        if not tavily:
            return {"error": "Tavily not configured"}

        result = tavily.search(query)
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

        nuggets = rag_store.get_all(channel_id)
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
                response_text = groq.retrieve_relevant(retrieve_prompt)
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

    async def _get_audit_logs(self, event_type="all", limit=10):
        audit_logger = self.bot.audit_logger
        if not audit_logger:
            return {"error": "Audit logger not configured"}

        if event_type == "all":
            logs = audit_logger.get_recent_logs(limit=limit)
        else:
            logs = audit_logger.get_logs_by_type(event_type, limit=limit)

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

    async def _fetch_webpage(self, url):
        browserless = self.bot.browserless
        if not browserless:
            return {"error": "Browserless not configured"}

        if not url:
            return {"error": "No URL provided"}

        result = await browserless.fetch_with_retry(url)
        return result

    async def _get_online_users(self, status_filter="all"):
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

        for guild in self.bot.guilds:
            for member in guild.members:
                if member.bot:
                    continue

                status = str(member.status)
                if status in users_by_status:
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
        browserless = self.bot.browserless
        gemini = self.bot.gemini

        if not browserless:
            return {"error": "Browserless not configured"}
        if not gemini:
            return {"error": "Gemini not configured"}
        if not url:
            return {"error": "No URL provided"}

        result = await browserless.screenshot_page(url)
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
