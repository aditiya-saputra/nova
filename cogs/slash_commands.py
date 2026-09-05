import json
import discord
from discord import app_commands
from discord.ext import commands
from utils.logger import get_logger
from utils.rich_presenter import rich
from utils.time_utils import format_wib, to_wib_iso

logger = get_logger(__name__)


class SlashCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ask", description="Ask Nova a question")
    @app_commands.describe(question="Your question for Nova")
    async def ask_slash(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer(thinking=True)

        try:
            settings = self.bot.settings
            session_manager = self.bot.session_manager
            history_store = self.bot.history_store
            rag_store = self.bot.rag_store
            context_builder = self.bot.context_builder
            groq = self.bot.groq
            gemini = self.bot.gemini

            channel_key = f"channel_{interaction.channel_id}"
            user_id = interaction.user.id

            nuggets = await rag_store.clean_expired(interaction.channel_id)
            prompt_template = context_builder.load_prompt_template("rag_retrieve_prompt.txt")
            nuggets_text = "\n".join(
                f"- [{n.get('channel_id', 'N/A')}] {n.get('fact', '')} (by user {n.get('user_id', 'N/A')})"
                for n in nuggets
            )
            retrieve_prompt = prompt_template.format(
                query=question,
                top_k=settings.NUGGETS_TOP_K,
                nuggets_text=nuggets_text
            )

            try:
                import json
                response_text = await groq.retrieve_relevant(retrieve_prompt)
                relevant_facts = json.loads(response_text.strip().strip("```json").strip("```"))
                if not isinstance(relevant_facts, list):
                    relevant_facts = []
                relevant_facts = [f for f in relevant_facts if isinstance(f, str)][:settings.NUGGETS_TOP_K]
            except Exception:
                relevant_facts = []

            metadata = {
                "user_id": user_id,
                "user_name": interaction.user.display_name,
                "channel_id": interaction.channel_id,
                "channel_name": getattr(interaction.channel, "name", "DM"),
                "timestamp": to_wib_iso(discord.utils.utcnow()),
                "trigger_type": "slash_command",
                "guild_id": interaction.guild_id,
                "guild_name": interaction.guild.name if interaction.guild else None,
            }

            system_prompt = context_builder.build_system_prompt(metadata, relevant_facts)
            session_manager.add_message(channel_key, "user", question)
            await history_store.aappend_message(channel_key, user_id, "user", question)

            prompt = f"{system_prompt}\n\nUser: {question}"
            history = session_manager.get_history(channel_key)[:-1]
            history_payload = [
                {"role": m["role"], "parts": [{"text": m["content"]}]}
                for m in history[-20:]
                if m["role"] in ("user", "model", "system")
            ]
            import asyncio as _asyncio
            if history_payload:
                response = await _asyncio.wait_for(gemini.generate(prompt, history=history_payload), timeout=45)
            else:
                response = await _asyncio.wait_for(gemini.generate(prompt), timeout=45)

            session_manager.add_message(channel_key, "assistant", response)
            await history_store.aappend_message(channel_key, user_id, "assistant", response)

            await interaction.followup.send(response)

            if response and not response.startswith("Error:"):
                extract_prompt = context_builder.build_rag_extract_prompt(question, response, metadata)
                try:
                    facts_response = await groq.extract_facts(extract_prompt)
                    facts = json.loads(facts_response.strip().strip("```json").strip("```"))
                    if isinstance(facts, list):
                        for fact in facts:
                            if isinstance(fact, str) and fact.strip():
                                nugget = rag_store.create_nugget(
                                    interaction.channel_id,
                                    user_id,
                                    interaction.id,
                                    fact
                                )
                                await rag_store.save(interaction.channel_id, nugget)
                except Exception:
                    pass

            if hasattr(self.bot, 'get_cog') and self.bot.get_cog('DynamicPresence'):
                presence = self.bot.get_cog('DynamicPresence')
                presence.add_message()
                presence.add_tokens(len(response.split()))

        except Exception as e:
            logger.error(f"Slash /ask error: {e}")
            await interaction.followup.send(f"Error: {str(e)}")

    @app_commands.command(name="recall", description="Recall memories from this channel")
    @app_commands.describe(query="Search query for memories")
    async def recall_slash(self, interaction: discord.Interaction, query: str = ""):
        await interaction.response.defer(thinking=True)

        try:
            rag_store = self.bot.rag_store
            nuggets = await rag_store.aget_all(interaction.channel_id)

            if not nuggets:
                await interaction.followup.send("No memories found for this channel.")
                return

            if query:
                import json
                groq = self.bot.groq
                nuggets_text = "\n".join(
                    f"- [{n.get('channel_id', 'N/A')}] {n.get('fact', '')} (by user {n.get('user_id', 'N/A')})"
                    for n in nuggets
                )
                retrieve_prompt = f"Query: {query}\n\nAvailable nuggets:\n{nuggets_text}\n\nSelect the 5 most relevant nuggets. Output as JSON array."
                response_text = await groq.retrieve_relevant(retrieve_prompt)
                relevant = json.loads(response_text.strip().strip("```json").strip("```"))
                if isinstance(relevant, list):
                    nuggets = [n for n in nuggets if n.get('fact', '') in relevant][:5]

            embed = discord.Embed(
                title="Nova Memory Recall",
                description=f"Found **{len(nuggets)}** memories",
                color=discord.Color.teal()
            )

            for i, nugget in enumerate(nuggets[:10]):
                fact = nugget.get("fact", "N/A")
                user_id = nugget.get("user_id", "N/A")
                created = nugget.get("timestamp") or nugget.get("created_at") or "N/A"
                if created != "N/A":
                    created = format_wib(created)
                embed.add_field(
                    name=f"Memory {i+1}",
                    value=f"{fact}\n*by {user_id} - {created}*",
                    inline=False
                )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Slash /recall error: {e}")
            await interaction.followup.send(f"Error: {str(e)}")

    @app_commands.command(name="forget", description="Hapus semua ingatan Nova di channel ini (memori RAG + riwayat percakapan)")
    @app_commands.default_permissions(manage_messages=True)
    async def forget_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            channel_key = f"channel_{interaction.channel_id}"
            rag_store = self.bot.rag_store
            session_manager = self.bot.session_manager
            lines = []

            if rag_store:
                count = len(await rag_store.aget_all(interaction.channel_id))
                await rag_store.delete_channel(interaction.channel_id)
                lines.append(f"🧠 Memori (RAG): {count} fakta dihapus")

            if session_manager:
                session_manager.clear(channel_key)
                lines.append("💬 Riwayat percakapan (session): dibersihkan")

            # Reset tracker anti-repeat channel ini agar tidak carry-over.
            mh = getattr(self.bot, "message_handler", None)
            if mh is not None:
                for tracker in (getattr(mh, "_last_tool_calls", None), getattr(mh, "_last_response_text", None)):
                    if isinstance(tracker, dict):
                        tracker.pop(channel_key, None)

            audit_logger = self.bot.audit_logger
            if audit_logger:
                await audit_logger.log("memory_cleared", {
                    "user_id": interaction.user.id,
                    "user_name": interaction.user.display_name,
                    "channel_id": interaction.channel_id,
                    "channel_name": getattr(interaction.channel, "name", "DM"),
                })

            await interaction.followup.send(
                "🗑️ Udah diapus semua ingatan Nova di channel ini.\n\n" + "\n".join(lines),
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Slash /forget error: {e}")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="history", description="View conversation history")
    @app_commands.describe(limit="Number of messages to show (default: 10)")
    async def history_slash(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer(thinking=True)

        try:
            session_manager = self.bot.session_manager
            channel_key = f"channel_{interaction.channel_id}"
            history = session_manager.get_history(channel_key)

            if not history:
                await interaction.followup.send("No conversation history found.")
                return

            embed = discord.Embed(
                title="Nova Conversation History",
                description=f"Showing last **{min(limit, len(history))}** messages",
                color=discord.Color.green()
            )

            for msg in history[-limit:]:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if len(content) > 100:
                    content = content[:100] + "..."
                embed.add_field(
                    name=f"{role.upper()}",
                    value=content,
                    inline=False
                )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Slash /history error: {e}")
            await interaction.followup.send(f"Error: {str(e)}")

    @app_commands.command(name="deleted", description="View recently deleted messages")
    @app_commands.describe(limit="Number of deleted messages to show (default: 10)")
    async def deleted_slash(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer(thinking=True)

        try:
            audit_logger = self.bot.audit_logger
            logs = await audit_logger.aget_logs_by_type("message_deleted", limit=limit)

            if not logs:
                await interaction.followup.send("No deleted messages logged.")
                return

            embed = discord.Embed(
                title="Nova Deleted Messages",
                description=f"Showing last **{len(logs)}** deleted messages",
                color=discord.Color.red()
            )

            for log in logs:
                data = log.get("data", {})
                user_name = data.get("user_name", "Unknown")
                channel_name = data.get("channel_name", "Unknown")
                content = data.get("content", "")
                created_at = data.get("created_at", "")
                deleted_at = data.get("deleted_at", "")

                if len(content) > 150:
                    content = content[:150] + "..."

                embed.add_field(
                    name=f"{user_name} in #{channel_name}",
                    value=f"**Content:** {content}\n*Created: {format_wib(created_at)}*\n*Deleted: {format_wib(deleted_at)}*",
                    inline=False
                )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Slash /deleted error: {e}")
            await interaction.followup.send(f"Error: {str(e)}")

    @app_commands.command(name="audit", description="View audit logs")
    @app_commands.describe(event_type="Event type: message_deleted, message_edited, tool_call, tool_result, error, all (default: all)", limit="Number of logs to show (default: 15)")
    async def audit_slash(self, interaction: discord.Interaction, event_type: str = "all", limit: int = 15):
        await interaction.response.defer(thinking=True)

        try:
            audit_logger = self.bot.audit_logger

            if event_type == "all":
                logs = await audit_logger.aget_recent_logs(limit=limit)
            else:
                logs = await audit_logger.aget_logs_by_type(event_type, limit=limit)

            if not logs:
                await interaction.followup.send("No audit logs found.")
                return

            embed = discord.Embed(
                title="Nova Audit Logs",
                description=f"Showing last **{len(logs)}** logs `{event_type}`",
                color=discord.Color.blue()
            )

            for log in logs:
                event = log.get("event", "unknown")
                timestamp = format_wib(log.get("timestamp", ""))
                data = log.get("data", {})

                if event == "message_deleted":
                    value = f"**User:** {data.get('user_name', 'N/A')} in #{data.get('channel_name', 'N/A')}\n**Content:** {data.get('content', '')[:100]}"
                elif event == "message_edited":
                    value = f"**User:** {data.get('user_name', 'N/A')}\n**Old:** {data.get('old_content', '')[:80]}\n**New:** {data.get('new_content', '')[:80]}"
                elif event == "tool_call":
                    value = f"**User:** {data.get('user_name', 'N/A')}\n**Tool:** `{data.get('tool_name', 'N/A')}`\n**Args:** `{json.dumps(data.get('tool_args', {}))[:100]}`"
                elif event == "tool_result":
                    value = f"**Tool:** `{data.get('tool_name', 'N/A')}`\n**Success:** {data.get('success', 'N/A')}\n**Result length:** {data.get('result_length', 0)}"
                elif event == "error":
                    value = f"**Type:** {data.get('error_type', 'N/A')}\n**Error:** {data.get('error_message', '')[:100]}"
                else:
                    value = json.dumps(data, ensure_ascii=False)[:200]

                embed.add_field(
                    name=f"[{event}] {timestamp}",
                    value=value,
                    inline=False
                )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Slash /audit error: {e}")
            await interaction.followup.send(f"Error: {str(e)}")

    @app_commands.command(name="send", description="Send a message to a channel with optional mention")
    @app_commands.describe(
        channel="Target channel to send message",
        message="Message to send",
        mention="User to mention (optional)"
    )
    async def send_slash(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str,
        mention: discord.Member = None
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            if mention:
                content = f"{mention.mention} {message}"
            else:
                content = message

            await channel.send(content)
            await interaction.followup.send(
                f"✅ Pesan terkirim ke {channel.mention}" +
                (f" dengan mention {mention.mention}" if mention else ""),
                ephemeral=True
            )

            audit_logger = self.bot.audit_logger
            await audit_logger.log("message_sent", {
                "user_id": interaction.user.id,
                "user_name": interaction.user.display_name,
                "channel_id": channel.id,
                "channel_name": channel.name,
                "message": message,
                "mention_user_id": mention.id if mention else None,
                "mention_user_name": mention.display_name if mention else None,
            })

        except Exception as e:
            logger.error(f"Slash /send error: {e}")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="welcome", description="Send welcome back message to a user in a channel")
    @app_commands.describe(
        channel="Target channel",
        user="User to welcome back"
    )
    async def welcome_slash(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        user: discord.Member
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            messages = [
                f"Hmph! {user.mention} udah online lagi... bukan karena aku peduli ya! (￣ω￣;)",
                f"Dasar {user.mention}, lama banget offline-nya. Tapi ya udah lah... (￣▽￣*)ゞ",
                f"{user.mention} balik juga akhirnya. Jangan dikira aku nungguin ya! (｡•̀ᴗ-)✧",
                f"Yah, {user.mention} udah muncul lagi. Repot deh... (~˘▾˘)~",
                f"{user.mention} kok baru online sih? Aku gak kangen lho! ...jangan salah paham. (；一_一)"
            ]

            import random
            chosen = random.choice(messages)

            await channel.send(chosen)
            await interaction.followup.send(
                f"✅ Welcome message terkirim ke {channel.mention} untuk {user.mention}",
                ephemeral=True
            )

            audit_logger = self.bot.audit_logger
            await audit_logger.log("welcome_sent", {
                "user_id": interaction.user.id,
                "user_name": interaction.user.display_name,
                "target_user_id": user.id,
                "target_user_name": user.display_name,
                "channel_id": channel.id,
                "channel_name": channel.name,
                "message": chosen,
            })

        except Exception as e:
            logger.error(f"Slash /welcome error: {e}")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="optin", description="Opt-in for auto-mention when you come online")
    @app_commands.describe(rate_limit="How often you want to be mentioned: 10m, 1h, 1d")
    @app_commands.choices(rate_limit=[
        app_commands.Choice(name="Every 10 minutes", value="10m"),
        app_commands.Choice(name="Every 1 hour", value="1h"),
        app_commands.Choice(name="Once per day", value="1d"),
    ])
    async def optin_slash(
        self,
        interaction: discord.Interaction,
        rate_limit: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            mention_store = self.bot.mention_store
            rl = rate_limit.value if rate_limit else "1h"
            pref = mention_store.opt_in(interaction.user.id, rl)

            rl_text = {"10m": "10 menit", "1h": "1 jam", "1d": "1 hari"}
            await interaction.followup.send(
                f"✅ Auto-mention diaktifkan!\n"
                f"Rate limit: {rl_text.get(rl, rl)} sekali\n"
                f"Nanti kalau kamu online, Nova bakal kirim pesan ke <#{self.bot.settings.WELCOME_CHANNEL_ID}>.",
                ephemeral=True
            )

            audit_logger = self.bot.audit_logger
            await audit_logger.log("mention_optin", {
                "user_id": interaction.user.id,
                "user_name": interaction.user.display_name,
                "rate_limit": rl,
            })

        except Exception as e:
            logger.error(f"Slash /optin error: {e}")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="optout", description="Opt-out from auto-mention")
    async def optout_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            mention_store = self.bot.mention_store
            mention_store.opt_out(interaction.user.id)

            await interaction.followup.send(
                "✅ Auto-mention dinonaktifkan.\n"
                "Kalau kamu online lagi, Nova gak bakal kirim pesan.",
                ephemeral=True
            )

            audit_logger = self.bot.audit_logger
            await audit_logger.log("mention_optout", {
                "user_id": interaction.user.id,
                "user_name": interaction.user.display_name,
            })

        except Exception as e:
            logger.error(f"Slash /optout error: {e}")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="mystatus", description="Check your mention settings")
    async def mystatus_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            mention_store = self.bot.mention_store
            pref = mention_store.get_user_pref(interaction.user.id)

            status = "✅ Aktif" if pref["opt_in"] else "❌ Nonaktif"
            rl_text = {"10m": "10 menit", "1h": "1 jam", "1d": "1 hari", "off": "Nonaktif"}
            rate_limit = rl_text.get(pref.get("rate_limit", "off"), "Nonaktif")

            last_mention = pref.get("last_mention", 0)
            if last_mention > 0:
                last_text = f"\nTerakhir di-mention: {format_wib(last_mention)}"
            else:
                last_text = "\nBelum pernah di-mention"

            await interaction.followup.send(
                f"**Status Auto-Mention kamu:**\n"
                f"Status: {status}\n"
                f"Rate limit: {rate_limit}{last_text}",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Slash /mystatus error: {e}")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="analyze", description="Analyze an image from URL using VLM")
    @app_commands.describe(
        url="Image URL to analyze",
        question="Specific question about the image (optional)"
    )
    async def analyze_slash(
        self,
        interaction: discord.Interaction,
        url: str,
        question: str = None
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            gemini = self.bot.gemini
            browserless = self.bot.browserless

            if not gemini or not browserless:
                await interaction.followup.send("VLM service not configured.", ephemeral=True)
                return

            result = await browserless.fetch_image(url)
            if not result.get("success"):
                await interaction.followup.send(
                    f"Failed to fetch image: {result.get('error', 'Unknown error')}",
                    ephemeral=True
                )
                return

            q = question if question else "Deskripsikan gambar ini secara detail."
            response = await gemini.generate_with_images(
                prompt=q,
                images=[{
                    "mime_type": result["mime_type"],
                    "data": result["data"]
                }]
            )

            embed = discord.Embed(
                title="VLM Image Analysis",
                description=response[:4000],
                color=discord.Color.teal()
            )
            embed.set_image(url=url)
            embed.set_footer(text=f"Analyzed by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed, ephemeral=False)

            audit_logger = self.bot.audit_logger
            await audit_logger.log("vlm_analyze", {
                "user_id": interaction.user.id,
                "user_name": interaction.user.display_name,
                "channel_id": interaction.channel.id,
                "url": url,
                "question": q,
            })

        except Exception as e:
            logger.error(f"Slash /analyze error: {e}")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

    @app_commands.command(name="screenshot", description="Take screenshot of a webpage and analyze it")
    @app_commands.describe(
        url="URL to screenshot",
        question="Specific question about the screenshot (optional)"
    )
    async def screenshot_slash(
        self,
        interaction: discord.Interaction,
        url: str,
        question: str = None
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            gemini = self.bot.gemini

            if not gemini:
                await interaction.followup.send("Screenshot service not configured.", ephemeral=True)
                return

            # Provider order sama seperti ToolExecutor (hyperbrowser → browserless).
            mode = (getattr(getattr(self.bot, "settings", None), "FETCH_PROVIDER", "auto") or "auto").lower()
            hb = getattr(self.bot, "hyperbrowser", None)
            bl = getattr(self.bot, "browserless", None)
            providers = []
            if mode == "hyperbrowser":
                providers = [p for p in (hb,) if p and getattr(p, "enabled", False)]
            elif mode == "browserless":
                providers = [p for p in (bl,) if p and getattr(p, "enabled", False)]
            else:
                if hb and getattr(hb, "enabled", False):
                    providers.append(hb)
                if bl and getattr(bl, "enabled", False):
                    providers.append(bl)
            if not providers:
                await interaction.followup.send("Screenshot service not configured.", ephemeral=True)
                return

            result = None
            for provider in providers:
                result = await provider.screenshot_page(url)
                if result.get("success"):
                    break
            if not result or not result.get("success"):
                await interaction.followup.send(
                    f"Failed to take screenshot: {result.get('error', 'Unknown error')}",
                    ephemeral=True
                )
                return

            q = question if question else "Analisis tampilan halaman ini."
            response = await gemini.generate_with_images(
                prompt=q,
                images=[{
                    "mime_type": "image/png",
                    "data": result["data"]
                }]
            )

            embed = discord.Embed(
                title=f"Screenshot Analysis: {url[:100]}",
                description=response[:4000],
                color=discord.Color.teal()
            )

            import io
            file = discord.File(io.BytesIO(result["data"]), filename="screenshot.png")
            embed.set_image(url="attachment://screenshot.png")
            embed.set_footer(text=f"Analyzed by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed, file=file, ephemeral=False)

            audit_logger = self.bot.audit_logger
            await audit_logger.log("vlm_screenshot", {
                "user_id": interaction.user.id,
                "user_name": interaction.user.display_name,
                "channel_id": interaction.channel.id,
                "url": url,
                "question": q,
            })

        except Exception as e:
            logger.error(f"Slash /screenshot error: {e}")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(SlashCommands(bot))
