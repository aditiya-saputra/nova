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
# #fix-stale: auto-fetch URL di pesan agar URL baru selalu segar (tidak dari RAG lama).
MAX_AUTO_URLS = 2
URL_CONTEXT_CHARS = 4000
# Timeout Gemini: percobaan penuh 45s, retry 60s dengan history dipangkas.
GEMINI_TIMEOUT = 45
GEMINI_RETRY_TIMEOUT = 60
HISTORY_RETRY_BUDGET = 8
# #repeat: follow-up singkat yang kemungkinan besar reaksi/konfirmasi.
SHORT_REACTION_MAX = 24


async def _bg_await(coro, label="bg"):
    """Fire-and-forget dengan log error — untuk audit/fact-extract/backup."""
    try:
        await coro
    except Exception as e:
        logger.error(f"Background {label} error: {e}")


def _spawn(coro, label="bg"):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_bg_await(coro, label))
    except RuntimeError:
        # Tidak ada loop berjalan (mis. saat shutdown/test) — skip aman.
        logger.error(f"No running loop for background {label}")


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
        self._last_tool_calls = {}
        self._last_response_text = {}

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
        # Guard: bila ini prefix-command terdaftar (!clear, !stats, !ask, ...),
        # biarkan process_commands yang menangani — AI skip agar tidak double-reply.
        try:
            if self.bot.router.is_bot_command(message):
                return
        except Exception:
            pass
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
            # #1: Paralelkan I/O independen (VLM + RAG + compaction + URL fetch) via gather.
            image_analyses, relevant_facts, _, url_contexts = await asyncio.gather(
                self.attachments.analyze(
                    image_attachments, content or "Deskripsikan gambar ini secara detail."
                ),
                self._retrieve_facts(content, message.channel.id),
                self.compaction_engine.check_and_compact(channel_key, user_id),
                self._fetch_url_contexts(urls),
            )

            self.session_manager.add_message(channel_key, "user", content)
            await self.history_store.aappend_message(channel_key, user_id, "user", content)

            try:
                system_prompt = self.context_builder.build_system_prompt(metadata, relevant_facts)
                final_prompt = self._build_final_prompt(content, image_analyses, url_contexts)
                tools = self.tool_executor.get_tools_for_gemini()
                history = _to_gemini_history(self.session_manager.get_history(channel_key)[:-1])

                # Timeout berlapis: coba penuh dulu; bila timeout, retry sekali
                # dengan history dipangkas (prompt panjang = penyebab umum lambat).
                try:
                    gemini_response = await asyncio.wait_for(self.gemini.generate_with_tools(
                        final_prompt, tools,
                        system_instruction=system_prompt,
                        history=history or None,
                    ), timeout=GEMINI_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.warning(f"Gemini tools timeout ({GEMINI_TIMEOUT}s), retrying with trimmed history")
                    try:
                        gemini_response = await asyncio.wait_for(self.gemini.generate_with_tools(
                            final_prompt, tools,
                            system_instruction=system_prompt,
                            history=history[-HISTORY_RETRY_BUDGET:] if history else None,
                        ), timeout=GEMINI_RETRY_TIMEOUT)
                    except asyncio.TimeoutError:
                        raise TimeoutError(f"Gemini generate_with_tools timeout ({GEMINI_TIMEOUT}s+{GEMINI_RETRY_TIMEOUT}s)")

                if gemini_response.get("type") == "tool_call":
                    tool_name = gemini_response.get("tool")
                    tool_args = gemini_response.get("args", {})
                    logger.info(f"Gemini selected tool: {tool_name}")

                    # #2: audit tool_call jangan block eksekusi tool.
                    _spawn(self.audit_logger.log("tool_call", {
                        "user_id": user_id,
                        "user_name": message.author.display_name,
                        "channel_id": message.channel.id,
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                    }), "tool_call")

                    last_assistant = self._last_response_text.get(channel_key, "")

                    if self._should_skip_repeated_tool(channel_key, tool_name, tool_args, content):
                        logger.info(
                            f"Skipping repeated {tool_name} call (short follow-up), "
                            "answering conversationally"
                        )
                        response = await asyncio.wait_for(self.gemini.generate(
                            self._build_reaction_prompt(content, last_assistant),
                            system_instruction=system_prompt,
                        ), timeout=GEMINI_TIMEOUT)
                    else:
                        self._last_tool_calls[channel_key] = {
                            "tool": tool_name, "args": tool_args,
                        }
                        tool_result = await self.tool_executor.execute(
                            tool_name, tool_args,
                            channel_id=message.channel.id,
                            user_id=user_id,
                        )

                        # #2: audit tool_result jangan block synthesize.
                        _spawn(self.audit_logger.log("tool_result", {
                            "user_id": user_id,
                            "channel_id": message.channel.id,
                            "tool_name": tool_name,
                            "result_length": len(str(tool_result)),
                            "success": not str(tool_result).startswith("Error"),
                        }), "tool_result")

                        try:
                            response = await asyncio.wait_for(self.gemini.synthesize_with_tool_result(
                                final_prompt, tool_result, system_instruction=system_prompt,
                                last_assistant=last_assistant,
                            ), timeout=GEMINI_TIMEOUT)
                        except asyncio.TimeoutError:
                            raise TimeoutError(f"Gemini synthesize timeout ({GEMINI_TIMEOUT}s)")
                else:
                    response = gemini_response.get("text", "")

                # Retry sekali via generate polos bila kosong (thinking-only) —
                # baru fallback bila tetap kosong (guard di bawah).
                if not (response or "").strip():
                    logger.warning("Gemini empty on first pass, retrying once without tools")
                    try:
                        response = await asyncio.wait_for(self.gemini.generate(
                            final_prompt,
                            system_instruction=system_prompt,
                            history=history or None,
                        ), timeout=GEMINI_TIMEOUT)
                    except Exception as retry_e:
                        logger.error(f"Gemini retry error: {retry_e}")

                self.session_manager.add_message(channel_key, "assistant", response)
                await self.history_store.aappend_message(channel_key, user_id, "assistant", response)

            except Exception as e:
                logger.error(f"Error processing message: {e}")
                response = f"Error: {str(e)}"
                await self.audit_logger.log_error("message_processing", str(e), {"channel_id": message.channel.id})

            # Guard: Gemini thinking-only (text kosong + thoughtsignature) → jangan
            # kirim string kosong / repr internal ke Discord (400 empty message).
            if not (response or "").strip():
                logger.warning("Gemini returned empty text (thinking-only?), using fallback")
                response = "Hmph! Aku sempat blank... coba tanya lagi dengan lebih jelas, baka! (￣ω￣;)"

        latency = time.time() - start_time
        rich.response_stats(len(response.split()), latency)

        if response and not response.startswith("Error:"):
            self._last_response_text[channel_key] = response

        # Reply dulu agar user tidak nunggu audit/RAG/backup.
        if self.settings.BOT_REPLY_MENTION:
            await message.reply(response, mention_author=True)
        else:
            await message.channel.send(response)

        # #2: non-kritis jadi background (tidak block return handle).
        _spawn(self.audit_logger.log_response(
            message.channel.id, len(response), latency, len(response.split())
        ), "log_response")

        try:
            presence = self.bot.get_cog("DynamicPresence") if hasattr(self.bot, "get_cog") else None
            if presence:
                presence.add_message()
                presence.add_tokens(len(response.split()))
        except Exception:
            pass

        if response and not response.startswith("Error:"):
            try:
                extract_prompt = self.context_builder.build_rag_extract_prompt(content, response, metadata)
                _spawn(self.fact_extractor.extract_and_save(
                    extract_prompt, message.channel.id, user_id, message.id
                ), "rag_extract")
            except Exception as e:
                logger.error(f"RAG extract spawn error: {e}")

        try:
            if self.github_backup.increment_counter():
                _spawn(self._backup_and_log(), "github_backup")
        except Exception as e:
            logger.error(f"Backup spawn error: {e}")

        # NOTE: process_commands dipanggil di main.py on_message (finally),
        # bukan di sini, agar pesan command tetap diproses walau AI skip.

    async def _backup_and_log(self):
        ok = await self.github_backup.backup("message_threshold")
        if ok:
            await self.audit_logger.log_backup("success", "Auto backup triggered")

    async def _retrieve_facts(self, query, channel_id):
        # Single source of truth via FactExtractor helper (hindari 3x duplikasi).
        try:
            top_k = getattr(self.settings, "NUGGETS_TOP_K", 5)
            return await self.fact_extractor.retrieve_relevant_facts(query, channel_id, top_k=top_k)
        except Exception:
            return []

    async def _fetch_url_contexts(self, urls):
        """Auto-fetch URL di pesan (max MAX_AUTO_URLS) via ToolExecutor fallback.

        Hasil segar di-injeksi ke prompt agar jawaban tidak basi dari RAG lama.
        Return list[{url, title, content}]; [] bila tidak ada/gagal.
        """
        if not urls:
            return []
        contexts = []
        for url in urls[:MAX_AUTO_URLS]:
            try:
                result = await self.tool_executor._fetch_webpage(url)
                if result.get("success") and (result.get("content") or "").strip():
                    text = result["content"][:URL_CONTEXT_CHARS]
                    contexts.append({
                        "url": url,
                        "title": result.get("title", ""),
                        "content": text,
                    })
                else:
                    logger.warning(f"Auto-fetch empty/failed for {url}: {result.get('error')}")
            except Exception as e:
                logger.error(f"Auto-fetch error for {url}: {e}")
        return contexts

    @staticmethod
    def _build_final_prompt(content, image_analyses, url_contexts=None):
        out = content or "User mengirim gambar/link tanpa teks."
        if image_analyses:
            out += "\n\n[Image Attachments Analyzed by Nova VLM]:\n"
            for i, img in enumerate(image_analyses, 1):
                out += f"\n--- Image {i}: {img['filename']} ---\n{img['analysis']}\n"
        if url_contexts:
            out += "\n\n[Webpage Content Auto-Fetched — GUNAKAN INI sebagai sumber utama untuk URL di bawah, jangan jawab dari memori lama]:\n"
            for ctx in url_contexts:
                out += f"\n--- URL: {ctx['url']} ---\nTitle: {ctx.get('title', '')}\n{ctx['content']}\n"
        return out

    @staticmethod
    def _normalize_args(args):
        try:
            return json.dumps(args, sort_keys=True, ensure_ascii=False)
        except Exception:
            return str(args)

    def _should_skip_repeated_tool(self, channel_key, tool_name, tool_args, content):
        """Anti-repeat: tool yang sama + args sama + follow-up singkat → jangan re-run.

        Follow-up pendek biasanya reaksi/konfirmasi ("dih ada aku ternyata",
        "oke cukup 2M sih"), bukan pertanyaan baru — re-run tool cuma melahirkan
        laporan yang sama persis.
        """
        prev = self._last_tool_calls.get(channel_key)
        if not prev:
            return False
        if tool_name != prev.get("tool"):
            return False
        if self._normalize_args(tool_args) != self._normalize_args(prev.get("args", {})):
            return False
        return len((content or "").strip()) <= SHORT_REACTION_MAX

    @staticmethod
    def _build_reaction_prompt(content, last_assistant):
        return (
            f"User menanggapi jawabanmu sebelumnya dengan singkat:\n"
            f"\"{content}\"\n\n"
            f"Jawabanmu sebelumnya:\n\"{last_assistant[:2000]}\"\n\n"
            f"Balas reaksi itu dengan singkat (1-2 kalimat, gaya tsundere) sesuai isi pesan user. "
            f"JANGAN memanggil tool, JANGAN mengulang laporan/format penuh dari jawaban sebelumnya."
        )

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
