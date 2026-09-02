from config.settings import Settings
from pathlib import Path


class ContextBuilder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._personality_cache = None

    def load_personality(self):
        if self._personality_cache:
            return self._personality_cache

        prompt_file = self.settings.PROMPTS_DIR / "personality.txt"
        if prompt_file.exists():
            self._personality_cache = prompt_file.read_text(encoding="utf-8")
        else:
            self._personality_cache = "You are a helpful Discord bot assistant."

        return self._personality_cache

    def load_prompt_template(self, filename):
        prompt_file = self.settings.PROMPTS_DIR / filename
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8")
        return ""

    def build_system_prompt(self, metadata, nuggets=None):
        personality = self.load_personality()

        context_parts = [
            f"User: {metadata['user_name']} (ID: {metadata['user_id']})",
            f"Channel: #{metadata['channel_name']}",
            f"Time: {metadata['timestamp']}",
            f"Trigger: {metadata['trigger_type']}",
        ]

        if metadata.get("guild_name"):
            context_parts.append(f"Server: {metadata['guild_name']}")

        if metadata.get("thread_name"):
            context_parts.append(f"Thread: {metadata['thread_name']}")

        if metadata.get("parent_message"):
            parent = metadata["parent_message"]
            context_parts.append(f"Replying to {parent['author']}: {parent['content']}")

        context = "\n".join(context_parts)

        prompt = f"{personality}\n\n---\nContext:\n{context}"

        if nuggets:
            nuggets_text = "\n".join(f"- {n}" for n in nuggets)
            prompt += f"\n\nRelevant memory nuggets:\n{nuggets_text}"

        return prompt

    def build_compaction_prompt(self, history):
        template = self.load_prompt_template("compaction_prompt.txt")
        return f"{template}\n\nConversation:\n{history}"

    def build_rag_extract_prompt(self, user_message, bot_response, metadata):
        template = self.load_prompt_template("rag_extract_prompt.txt")
        return f"{template}\n\nUser ({metadata.get('user_name', 'Unknown')}): {user_message}\nBot: {bot_response}"

    def build_rag_retrieve_prompt(self, query, nuggets, top_k=5):
        template = self.load_prompt_template("rag_retrieve_prompt.txt")
        nuggets_text = "\n".join(
            f"- [{n.get('channel_id', 'N/A')}] {n.get('fact', '')} (by user {n.get('user_id', 'N/A')})"
            for n in nuggets
        )
        return template.format(query=query, top_k=top_k, nuggets_text=nuggets_text)
