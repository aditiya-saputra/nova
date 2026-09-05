import asyncio
import random
import json
from google import genai
from google.genai import types
from config.settings import Settings
from utils.logger import get_logger

logger = get_logger(__name__)

NOT_FOUND_CODES = [404, "404", "NOT_FOUND"]


class GeminiClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.keys = settings.GEMINI_API_KEYS
        self.current_index = 0
        self.model_name = settings.GEMINI_MODEL
        self.fallback_models = settings.GEMINI_FALLBACK_MODELS
        self.model_chain = [self.model_name] + self.fallback_models
        # Log rantai model sekali saat startup agar drift config (mis. model deprecated)
        # langsung terlihat di log, bukan hanya saat API menolak.
        logger.info(f"Gemini model chain: {self.model_chain}")
        # #3: cache genai.Client per API key — jangan bikin baru tiap call.
        self._clients: dict[str, object] = {}

    def _is_not_found_error(self, e):
        code = getattr(e, "code", None) or getattr(e, "status_code", None)
        msg = str(e)
        return code in NOT_FOUND_CODES or "NOT_FOUND" in msg or "no longer available" in msg.lower()

    async def verify_model_chain(self):
        """Cek ketersediaan rantai model ke API Gemini saat startup (fail-fast).

        - Model yang 404 (deprecated/typo) → log error keras per model.
        - Seluruh rantai tidak tersedia → raise RuntimeError agar bot tidak start
          (lebih baik abort di sini daripada error 404 muncul di chat).
        - Error non-404 (auth/network, mis. key placeholder) → hanya warning dan
          verifikasi dihentikan: bukan indikasi model mati, jadi tidak fatal.
        """
        if not self.keys:
            logger.error("No Gemini API keys configured — cannot verify model chain.")
            return
        client = self._get_client(self.keys[0])
        available, missing = [], []
        for model in self.model_chain:
            try:
                await client.aio.models.get(model=model)
                available.append(model)
            except Exception as e:
                if self._is_not_found_error(e):
                    logger.error(
                        f"Gemini model '{model}' NOT AVAILABLE at startup ({e}). "
                        "Perbaiki GEMINI_MODEL/GEMINI_FALLBACK_MODELS di .env ke model yang masih didukung."
                    )
                    missing.append(model)
                else:
                    logger.warning(
                        f"Gemini model check for '{model}' skipped (bukan 404: {e}) "
                        "— verifikasi tidak bisa jalan, lanjut startup."
                    )
                    return
        if missing and not available:
            raise RuntimeError(
                f"Semua model Gemini tidak tersedia: {missing}. "
                "Perbaiki GEMINI_MODEL/GEMINI_FALLBACK_MODELS di .env sebelum start."
            )
        logger.info(f"Gemini model chain check OK: available={available}"
                    + (f", missing={missing}" if missing else ""))

    def _get_next_key(self):
        if not self.keys:
            raise ValueError("No Gemini API keys configured")
        key = self.keys[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.keys)
        return key

    def _get_client(self, api_key):
        # #3: reuse client per key (genai.Client menyimpan httpx connection pool).
        client = self._clients.get(api_key)
        if client is None:
            client = genai.Client(api_key=api_key)
            self._clients[api_key] = client
        return client

    def _build_config(self, system_instruction=None):
        config = types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=self.settings.GEMINI_OUTPUT_LIMIT,
        )
        if system_instruction:
            config.system_instruction = system_instruction
        return config

    def _extract_response_text(self, response):
        # Jangan akses response.text bila ada function_call (SDK warning:
        # "non-text parts in the response"). Inspeksi parts dulu.
        # Jangan pernah return repr internal (Part(...)/thoughtsignature) ke user.
        try:
            candidates = getattr(response, "candidates", None)
            if candidates:
                parts = getattr(getattr(candidates[0], "content", None), "parts", None) or []
                texts = [p.text for p in parts if getattr(p, "text", None)]
                # Buang string kosong / whitespace-only (kasus thoughtsignature saja).
                texts = [t for t in texts if t and t.strip()]
                has_func = any(getattr(p, "function_call", None) for p in parts)
                if texts and not has_func:
                    return str(texts[0])
                if texts:
                    return str("\n".join(texts))
                if has_func:
                    return ""
                # Tidak ada teks & bukan tool call (mis. thinking-only) → string kosong,
                # JANGAN str(content) karena itu repr internal Part(thoughtsignature=...).
                return ""
            try:
                txt = getattr(response, "text", None)
            except Exception:
                txt = None
            if txt:
                return str(txt)
        except Exception as e:
            logger.error(f"Error extracting response text: {e}")
        return ""

    async def _run_with_fallback(self, fn, label_prefix=""):
        last_error = None
        primary_model = self.model_chain[0] if self.model_chain else self.model_name
        for model in self.model_chain:
            self.model_name = model
            logger.info(f"Trying model: {model}")
            for attempt in range(len(self.keys)):
                api_key = self._get_next_key()
                try:
                    result = await fn(api_key)
                    if model != primary_model:
                        logger.info(f"Switched to model: {model} (fallback from {primary_model})")
                    return result
                except Exception as e:
                    last_error = e
                    if self._is_not_found_error(e):
                        logger.warning(f"Model {model} not available ({e}), trying next model...")
                        break
                    code = getattr(e, "code", None) or getattr(e, "status_code", None)
                    if code in [503, 429] or "429" in str(e) or "503" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(f"Gemini rate limited/unavailable ({e}), retrying key {attempt+1}/{len(self.keys)} in {wait_time:.1f}s")
                        await asyncio.sleep(wait_time)
                        continue
                    raise
        logger.error(f"All models failed. Last error: {last_error}")
        raise last_error

    async def generate(self, prompt, system_instruction=None, history=None):
        async def _call(api_key):
            client = self._get_client(api_key)
            config = self._build_config(system_instruction)
            logger.info(f"Generating with model: {self.model_name}")
            if history:
                chat = client.aio.chats.create(
                    model=self.model_name,
                    history=history,
                    config=config
                )
                response = await chat.send_message(prompt)
            else:
                response = await client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )
            return self._extract_response_text(response)

        return await self._run_with_fallback(_call, "generate")

    async def chat(self, messages, system_instruction=None):
        async def _call(api_key):
            client = self._get_client(api_key)
            config = self._build_config(system_instruction)
            chat = client.aio.chats.create(
                model=self.model_name,
                config=config
            )
            return chat

        return await self._run_with_fallback(_call, "chat")

    async def generate_with_tools(self, prompt, tools, system_instruction=None, history=None):
        flat_tools = []
        for t in tools:
            flat_tools.append(types.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters_json_schema=t.get("parameters", {})
            ))
        tool_declarations = types.Tool(function_declarations=flat_tools)

        config = types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=self.settings.GEMINI_OUTPUT_LIMIT,
            tools=[tool_declarations]
        )
        if system_instruction:
            config.system_instruction = system_instruction

        async def _call(api_key):
            client = self._get_client(api_key)
            logger.info(f"Generating with tools: {self.model_name}")
            # SDK anjurkan AFC via Chat.send_message, bukan Models.generate_content.
            # Selalu pakai chat (history kosong bila tidak ada) agar tidak warning.
            chat = client.aio.chats.create(
                model=self.model_name,
                history=history or [],
                config=config
            )
            response = await chat.send_message(prompt)
            response_text = self._extract_response_text(response)
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'function_call') and part.function_call:
                        return {
                            "type": "tool_call",
                            "tool": part.function_call.name,
                            "args": dict(part.function_call.args)
                        }
            return {"type": "text", "text": response_text}

        return await self._run_with_fallback(_call, "generate_with_tools")

    async def synthesize_with_tool_result(self, original_prompt, tool_result, system_instruction=None):
        config = self._build_config(system_instruction)
        prompt = f"""Original request: {original_prompt}

Tool execution result:
{json.dumps(tool_result, indent=2) if isinstance(tool_result, dict) else str(tool_result)}

Based on the tool result above, provide a helpful response to the user."""

        async def _call(api_key):
            client = self._get_client(api_key)
            response = await client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            return self._extract_response_text(response)

        return await self._run_with_fallback(_call, "synthesize_with_tool_result")

    async def generate_with_images(self, prompt, images, system_instruction=None):
        config = self._build_config(system_instruction)
        contents = []
        contents.append(types.Part(text=prompt))
        for img in images:
            contents.append(types.Part(inline_data=types.Blob(
                mime_type=img["mime_type"],
                data=img["data"]
            )))

        async def _call(api_key):
            client = self._get_client(api_key)
            logger.info(f"Generating VLM with model: {self.model_name}, images: {len(images)}")
            response = await client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )
            return self._extract_response_text(response)

        return await self._run_with_fallback(_call, "generate_with_images")