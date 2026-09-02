import asyncio
import json
import time
import re
import discord
from utils.logger import get_logger
from utils.rich_presenter import rich
from handlers.message_cache import MessageCache
from handlers.attachment_processor import AttachmentProcessor
from handlers.fact_extractor import FactExtractor

logger = get_logger(__name__)

URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
HISTORY_BUDGET = 20


def _to_gemini_history(session_history):
    out = []
    for msg in session_history[-HISTORY_BUDGET:]:
        role = msg.get("role")
        content = msg.get("content", "")
        if role not in ("user", "model", "system"):
            continue
        out.append({"role": role, "parts": [{"text": content}]})
    return out


class MessageHandler:
    def __init__(
        self,
        bot,
        settings,
        gemini,
        groq,
        rag_store,
        history_store,
        session_manager,
        context_builder,
        tool_executor,
        compaction_engine,
        audit_logger,
        github_backup,
        mention_store,
    ):
        self.bot = bot
        self.settings = settings
        self.gemini = gemini
        self.groq = groq
        self.rag_store = rag_store
        self.history_store = history_store
        self.session_manager = session_manager
        self.context_builder = context_builder
        self.tool_executor = tool_executor
        self.compaction_engine = compaction_engine
        self.audit_logger = audit_logger
        self.github_backup = github_backup
        self.mention_store = mention_store
        self.cache = MessageCache()
        self.attachments = AttachmentProcessor(gemini)
        self.fact_extractor = FactExtractor(groq, rag_store, audit_logger)

    def cache_message(self, message):
        if message.author.bot:
            return
        self.cache.put(message.id, {
            "user_id": message.author.id,
            "user_name": message.author.display_name,
            "channel_id": message.channel.id,
            "channel_name": getattr(message.channel, "name", "DM"),
            "content": message.content,
            "created_at": message.created_at.isoformat(),
            "attachments": [a.url for a in message.attachments],
        })

    async def handle(self, message):
        trigger_type = self.bot.router.detect_trigger(message)
        if not trigger_type:
            return

        if trigger_type == "reply_to_bot" and not self.bot.router.should_process_reply(message):
            return

        content = self.bot.router.clean_content(message, trigger_type)
        if not content and not message.attachments:
            return

        urls = URL_PATTERN.findall(content) if content else []
        image_attachments = self.attachments.extract_image_attachments(message)

        metadata = self.bot.router.extract_metadata(message, trigger_type)
        if urls:
            metadata["urls"] = urls
            metadata["has_urls"] = True
        if image_attachments:
            metadata["has_images"] = True
            metadata["image_count"] = len(image_attachments)

        channel_key = f"channel_{message.channel.id}"
        user_id = message.author.id

        await self.audit_logger.log_message(
            user_id, message.author.display_name,
            message.channel.id, trigger_type, content
        )

        rich.process_trigger(trigger_type, message.author.display_name, getattr(message.channel, "name", "DM"))

        start_time = time.time()
        response = ""

        async with message.channel.typing():
            image_analyses = await self.attachments.analyze(
                image_attachments, content or "Deskripsikan gambar ini secara detail."
            )

            relevant_facts = await self._retrieve_facts(content, message.channel.id)
            await self.compaction_engine.check_and_compact(channel_key, user_id)

            self.session_manager.add_message(channel_key, "user", content)
            self.history_store.append_message(channel_key, user_id, "user", content)

            try:
                system_prompt = self.context_builder.build_system_prompt(metadata, relevant_facts)
                final_prompt = self._build_final_prompt(content, image_analyses)
                tools = self.tool_executor.get_tools_for_gemini()
                history = _to_gemini_history(self.session_manager.get_history(channel_key)[:-1])

                gemini_response = await self.gemini.generate_with_tools(
                    final_prompt, tools,
                    system_instruction=system_prompt,
                    history=history or None,
                )

                if gemini_response.get("type") == "tool_call":
                    tool_name = gemini_response.get("tool")
                    tool_args = gemini_response.get("args", {})
                    logger.info(f"Gemini selected tool: {tool_name}")

                    await self.audit_logger.log("tool_call", {
                        "user_id": user_id,
                        "user_name": message.author.display_name,
                        "channel_id": message.channel.id,
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                    })

                    tool_result = await self.tool_executor.execute(
                        tool_name, tool_args,
                        channel_id=message.channel.id,
                        user_id=user_id,
                    )

                    await self.audit_logger.log("tool_result", {
                        "user_id": user_id,
                        "channel_id": message.channel.id,
                        "tool_name": tool_name,
                        "result_length": len(str(tool_result)),
                        "success": not str(tool_result).startswith("Error"),
                    })

                    response = await self.gemini.synthesize_with_tool_result(
                        final_prompt, tool_result, system_instruction=system_prompt
                    )
                else:
                    response = gemini_response.get("text", "")

                self.session_manager.add_message(channel_key, "assistant", response)
                self.history_store.append_message(channel_key, user_id, "assistant", response)

            except Exception as e:
                logger.error(f"Error processing message: {e}")
                response = f"Error: {str(e)}"
                await self.audit_logger.log_error("message_processing", str(e), {"channel_id": message.channel.id})

        latency = time.time() - start_time
        rich.response_stats(len(response.split()), latency)

        await self.audit_logger.log_response(
            message.channel.id, len(response), latency, len(response.split())
        )

        if self.settings.BOT_REPLY_MENTION:
            await message.reply(response, mention_author=True)
        else:
            await message.channel.send(response)

        presence = self.bot.get_cog("DynamicPresence") if hasattr(self.bot, "get_cog") else None
        if presence:
            presence.add_message()
            presence.add_tokens(len(response.split()))

        if response and not response.startswith("Error:"):
            extract_prompt = self.context_builder.build_rag_extract_prompt(content, response, metadata)
            await self.fact_extractor.extract_and_save(
                extract_prompt, message.channel.id, user_id, message.id
            )

        if self.github_backup.increment_counter():
            await self.audit_logger.log_backup("success", "Auto backup triggered")

        await self.bot.process_commands(message)

    async def _retrieve_facts(self, query, channel_id):
        nuggets = await self.rag_store.clean_expired(channel_id)
        if not nuggets:
            return []
        prompt_template = self.context_builder.load_prompt_template("rag_retrieve_prompt.txt")
        nuggets_text = "\n".join(
            f"- [{n.get('channel_id', 'N/A')}] {n.get('fact', '')} (by user {n.get('user_id', 'N/A')})"
            for n in nuggets
        )
        retrieve_prompt = prompt_template.format(
            query=query,
            top_k=self.settings.NUGGETS_TOP_K,
            nuggets_text=nuggets_text,
        )
        try:
            response_text = await asyncio.to_thread(self.groq.retrieve_relevant, retrieve_prompt)
            relevant_facts = json.loads(response_text.strip().strip("```json").strip("```"))
            if not isinstance(relevant_facts, list):
                return []
            return [f for f in relevant_facts if isinstance(f, str)][:self.settings.NUGGETS_TOP_K]
        except Exception:
            return []

    @staticmethod
    def _build_final_prompt(content, image_analyses):
        if not image_analyses:
            return content
        img_context = "\n\n[Image Attachments Analyzed by Nova VLM]:\n"
        for i, img in enumerate(image_analyses, 1):
            img_context += f"\n--- Image {i}: {img['filename']} ---\n{img['analysis']}\n"
        if content:
            return content + img_context
        return f"User mengirim gambar tanpa teks.{img_context}"

    async def handle_delete(self, message):
        if message.author.bot:
            return
        cached = self.cache.pop(message.id)
        data = cached or {
            "user_id": message.author.id,
            "user_name": message.author.display_name,
            "channel_id": message.channel.id,
            "channel_name": getattr(message.channel, "name", "DM"),
            "content": message.content,
            "created_at": message.created_at.isoformat(),
            "attachments": [a.url for a in message.attachments],
        }
        if not cached:
            data["cached"] = False
        data["deleted_at"] = discord.utils.utcnow().isoformat()
        await self.audit_logger.log("message_deleted", data)
        if cached:
            logger.info(f"Deleted message logged: {cached['user_name']} in #{cached['channel_name']}")

    async def handle_edit(self, before, after):
        if before.author.bot:
            return
        if before.content == after.content:
            return
        await self.audit_logger.log("message_edited", {
            "user_id": before.author.id,
            "user_name": before.author.display_name,
            "channel_id": before.channel.id,
            "old_content": before.content,
            "new_content": after.content,
            "edited_at": discord.utils.utcnow().isoformat(),
        })

    async def handle_presence(self, before, after):
        if before.bot:
            return
        if before.status == after.status:
            return

        status_map = {
            "online": "🟢 Online",
            "idle": "🟡 Idle",
            "dnd": "🔴 DND",
            "offline": "⚫ Offline",
        }
        old_status = status_map.get(str(before.status), str(before.status))
        new_status = status_map.get(str(after.status), str(after.status))

        await self.audit_logger.log("presence_update", {
            "user_id": after.id,
            "user_name": after.display_name,
            "old_status": old_status,
            "new_status": new_status,
            "timestamp": discord.utils.utcnow().isoformat(),
        })
        logger.info(f"Presence update: {after.display_name} {old_status} → {new_status}")

        if str(before.status) != "offline" or str(after.status) != "online":
            return

        await self.audit_logger.log("user_online", {
            "user_id": after.id,
            "user_name": after.display_name,
            "timestamp": discord.utils.utcnow().isoformat(),
        })

        if not (self.settings.WELCOME_ENABLED and self.settings.WELCOME_CHANNEL_ID):
            return
        if not self.mention_store.can_mention(after.id):
            return

        try:
            channel = self.bot.get_channel(self.settings.WELCOME_CHANNEL_ID)
            if not channel:
                return
            welcome_prompt = (
                f"Kamu adalah Nova, asisten AI Discord dengan karakter tsundere. "
                f"Buat pesan selamat datang singkat (1-2 kalimat) untuk user bernama "
                f"'{after.display_name}' yang baru online lagi. "
                f"Gunakan gaya tsundere: cuek di luar tapi peduli di dalam. "
                f"Jangan pakai emoji. Output hanya teks pesan saja."
            )
            response = await self.gemini.generate(welcome_prompt)
            if response and not response.startswith("Error:"):
                await channel.send(f"{after.mention} {response}")
                self.mention_store.record_mention(after.id)
                await self.audit_logger.log("auto_mention", {
                    "user_id": after.id,
                    "user_name": after.display_name,
                    "channel_id": channel.id,
                    "message": response,
                })
        except Exception as e:
            logger.error(f"Auto-mention error: {e}")
