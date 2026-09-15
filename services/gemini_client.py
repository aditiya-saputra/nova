import asyncio
import random
import json
import httpx
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
        # #10: shared transport async (httpx) untuk semua client. Ini menghindari
        # resolver DNS aiodns/aiohttp yang rusak di sebagian environment Windows
        # ("Could not contact DNS servers") — httpx memakai resolver OS yang normal.
        self._async_http = httpx.AsyncClient(timeout=120)

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
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    httpx_async_client=self._async_http,
                ),
            )
            self._clients[api_key] = client
        return client

    async def aclose(self):
        """Tutup transport HTTP bersama saat shutdown (hindari warning unclosed)."""
        try:
            await self._async_http.aclose()
        except Exception:
            pass

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
            logger.info(f"Trying model: {model}")
            for attempt in range(len(self.keys)):
                api_key = self._get_next_key()
                try:
                    result = await fn(api_key, model)
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
        async def _call(api_key, model):
            client = self._get_client(api_key)
            config = self._build_config(system_instruction)
            logger.info(f"Generating with model: {model}")
            if history:
                chat = client.aio.chats.create(
                    model=model,
                    history=history,
                    config=config
                )
                response = await chat.send_message(prompt)
            else:
                response = await client.aio.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )
            return self._extract_response_text(response)

        return await self._run_with_fallback(_call, "generate")

    async def chat(self, messages, system_instruction=None):
        async def _call(api_key, model):
            client = self._get_client(api_key)
            config = self._build_config(system_instruction)
            chat = client.aio.chats.create(
                model=model,
                config=config
            )
            return chat

        return await self._run_with_fallback(_call, "chat")

    async def generate_with_tools(self, prompt, tools, system_instruction=None, history=None):
        """Generate with tool declarations. Returns tool_calls list or text response.

        Supports parallel function calling: Gemini can return multiple tool calls
        in a single response. Returns:
            {"type": "tool_calls", "calls": [...], "function_call_content": Content, "user_content": Content}
            {"type": "text", "text": "..."}

        The "function_call_content" and "user_content" keys preserve conversation state
        for compositional function calling.
        """
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
            tools=[tool_declarations],
            # Disable thinking untuk tool calling — thinking models butuh
            # thought_signature yang tidak tersedia via models.generate_content.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        if system_instruction:
            config.system_instruction = system_instruction

        # Build user content for conversation history
        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)]
        )

        async def _call(api_key, model):
            client = self._get_client(api_key)
            logger.info(f"Generating with tools: {model}")
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
            result = self._parse_tool_response(response)

            # Preserve conversation state for compositional loop
            result["user_content"] = user_content
            if response.candidates and response.candidates[0].content:
                content_obj = response.candidates[0].content
                result["function_call_content"] = content_obj
                # Extract thought_signatures from function call parts for Gemini API v1
                if result["type"] == "tool_calls":
                    result["thought_signatures"] = self._extract_thought_signatures(content_obj)

            return result

        return await self._run_with_fallback(_call, "generate_with_tools")

    def _extract_thought_signatures(self, content):
        """Extract thought_signature bytes from each Part in a Content object."""
        signatures = []
        if content and getattr(content, 'parts', None):
            for part in content.parts:
                ts = getattr(part, 'thought_signature', None)
                signatures.append(ts if ts is not None else b'')
        return signatures

    def _rebuild_content_with_signatures(self, content, thought_signatures):
        """Rebuild Content object with thought_signature attached to each Part."""
        if not content or not getattr(content, 'parts', None):
            return content
        new_parts = []
        for i, part in enumerate(content.parts):
            ts = thought_signatures[i] if i < len(thought_signatures) else b''
            if ts:
                new_part = types.Part(
                    text=part.text,
                    function_call=part.function_call,
                    thought_signature=ts,
                )
                new_parts.append(new_part)
            else:
                new_parts.append(part)
        return types.Content(role=content.role, parts=new_parts)

    def _build_contents_with_signatures(self, user_content, function_call_content, function_response_content, thought_signatures=None):
        """Build contents array with proper thought_signature handling."""
        contents = []
        if user_content:
            contents.append(user_content)
        if function_call_content:
            if thought_signatures:
                rebuilt = self._rebuild_content_with_signatures(function_call_content, thought_signatures)
                contents.append(rebuilt)
            else:
                contents.append(function_call_content)
        if function_response_content:
            contents.append(function_response_content)
        return contents

    def _parse_tool_response(self, response):
        """Parse Gemini response into structured tool_calls or text.

        Handles parallel function calling: returns ALL tool calls from a single
        response as a list. Also extracts thought_signature from function call parts.
        """
        response_text = self._extract_response_text(response)
        tool_calls = []
        thought_signatures = []

        if (response.candidates
                and response.candidates[0].content
                and response.candidates[0].content.parts):
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    tool_calls.append({
                        "tool": part.function_call.name,
                        "args": dict(part.function_call.args),
                    })
                    ts = getattr(part, 'thought_signature', None)
                    thought_signatures.append(ts if ts is not None else b'')

        result = {"type": "text", "text": response_text}
        if tool_calls:
            result = {"type": "tool_calls", "calls": tool_calls, "thought_signatures": thought_signatures}
        return result

    async def generate_with_tool_results(self, tool_results, tools, system_instruction=None,
                                          user_content=None, function_call_content=None,
                                          thought_signatures=None):
        """Compositional function calling: send tool results back, get next response.

        After executing tool(s), send results back to Gemini.
        Gemini may return more tool calls (chain) or a final text response.

        Format: [user_content, function_call_content, function_response_content]
        (required by Gemini API — function call must follow user turn)

        Args:
            tool_results: list of {"tool": name, "args": {...}, "result": {...}}
            tools: tool declarations for Gemini
            system_instruction: system prompt
            user_content: the original user Content from initial prompt
            function_call_content: the function call Content from previous response
            thought_signatures: list of thought_signature bytes for each function call part

        Returns: same format as generate_with_tools
        """
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
            tools=[tool_declarations],
            # Disable thinking untuk tool calling — thinking models butuh
            # thought_signature yang tidak tersedia via models.generate_content.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        if system_instruction:
            config.system_instruction = system_instruction

        # Build function response content
        function_response_parts = []
        for tr in tool_results:
            result_data = json.dumps(tr["result"], ensure_ascii=False) if isinstance(tr["result"], dict) else str(tr["result"])
            function_response_parts.append(types.Part.from_function_response(
                name=tr["tool"],
                response=tr["result"] if isinstance(tr["result"], dict) else {"text": result_data},
            ))

        function_response_content = types.Content(
            role="tool",
            parts=function_response_parts
        )

        # Build full contents: user + function_call + function_response
        # with proper thought_signature handling for Gemini API v1
        contents = self._build_contents_with_signatures(
            user_content, function_call_content, function_response_content,
            thought_signatures or []
        )

        async def _call(api_key, model):
            client = self._get_client(api_key)
            logger.info(f"Compositional round: {model} ({len(tool_results)} results)")
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
            result = self._parse_tool_response(response)
            # Preserve conversation state for next round
            result["user_content"] = user_content
            result["thought_signatures"] = []
            if response.candidates and response.candidates[0].content:
                content_obj = response.candidates[0].content
                result["function_call_content"] = content_obj
                if result["type"] == "tool_calls":
                    result["thought_signatures"] = self._extract_thought_signatures(content_obj)
            return result

        return await self._run_with_fallback(_call, "generate_with_tool_results")

    async def synthesize_with_tool_result(self, original_prompt, tool_result, system_instruction=None, last_assistant=None):
        """Synthesize final answer from tool result (single tool).

        Prompt ordering follows Gemini best practices:
        - Tool result as context (main data source)
        - User query at the END (docs: "query at end performs better")
        - No last_assistant injection (causes model to fixate on previous output)
        """
        return await self._synthesize_multi(
            original_prompt, [tool_result], system_instruction, last_assistant
        )

    async def synthesize_with_tool_results(self, original_prompt, tool_results, system_instruction=None, last_assistant=None):
        """Synthesize final answer from multiple parallel tool results."""
        results = [tr["result"] for tr in tool_results]
        return await self._synthesize_multi(
            original_prompt, results, system_instruction, last_assistant
        )

    async def _synthesize_multi(self, original_prompt, results, system_instruction=None, last_assistant=None):
        """Shared synthesis logic with explicit anti-verbatim reference."""
        config = self._build_config(system_instruction)

        parts = []
        for i, result in enumerate(results):
            data = json.dumps(result, indent=2, ensure_ascii=False) if isinstance(result, dict) else str(result)
            if len(results) > 1:
                parts.append(f"Tool result {i+1}:\n{data}")
            else:
                parts.append(f"Tool execution result:\n{data}")

        tool_data = "\n\n".join(parts)

        # Build prompt with reference context
        prompt = f"""[CONTEXTUAL DATA]
{tool_data}
"""
        if last_assistant:
            prompt += f"""
[REFERENCE ONLY - PREVIOUS ANSWER]
{last_assistant[:1500]}
(Use the above ONLY for context/flow. DO NOT REPEAT IT.)
"""
        
        prompt += f"""
---

User request: {original_prompt}

RULES:
1. NEVER repeat your previous answer verbatim. 
2. Use the [REFERENCE] only to understand what was already discussed.
3. Generate a fresh, NEW response based on the current tool results.
4. If the user is asking a follow-up, ensure your new answer connects logically to the previous context without echoing it.
5. Keep response concise and in tsundere character."""

        async def _call(api_key, model):
            client = self._get_client(api_key)
            response = await client.aio.models.generate_content(
                model=model,
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

        async def _call(api_key, model):
            client = self._get_client(api_key)
            logger.info(f"Generating VLM with model: {model}, images: {len(images)}")
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
            return self._extract_response_text(response)

        return await self._run_with_fallback(_call, "generate_with_images")