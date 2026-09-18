import asyncio
import base64
import importlib
import json
import os
import sys
import tempfile
import types as py_types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class TempSettings:
    def __init__(self, root):
        self.DATA_DIR = Path(root)
        self.HISTORY_DIR = self.DATA_DIR / "history"
        self.MEMORIES_DIR = self.DATA_DIR / "memories"
        self.NUGGETS_TTL_DAYS = 3
        self.NUGGETS_TOP_K = 5
        self.GEMINI_CONTEXT_LIMIT = 100


class TestStorageRegressions(unittest.TestCase):
    def test_history_keys_do_not_collide(self):
        from memory.history_store import HistoryStore

        with tempfile.TemporaryDirectory() as root:
            settings = TempSettings(root)
            settings.HISTORY_DIR.mkdir()
            store = HistoryStore(settings)
            self.assertNotEqual(store._get_file_path("a/b"), store._get_file_path("ab"))

    def test_malformed_opted_in_key_is_skipped(self):
        from memory.mention_store import MentionStore

        with tempfile.TemporaryDirectory() as root:
            settings = TempSettings(root)
            store = MentionStore(settings)
            store.preferences = {"123": {"opt_in": True}, "bad-id": {"opt_in": True}}
            self.assertEqual(store.get_all_opted_in(), [123])

    def test_audit_log_uses_utc_and_filtered_logs_are_recent(self):
        from memory.audit_logger import AuditLogger

        with tempfile.TemporaryDirectory() as root:
            settings = TempSettings(root)
            logger = AuditLogger(settings)
            for value in range(3):
                logger._write_entry({"timestamp": str(value), "event": "x", "data": {"value": value}})
            logger._write_entry({"timestamp": "3", "event": "other", "data": {}})
            logger._write_entry({"timestamp": "4", "event": "x", "data": {"value": 4}})
            self.assertEqual([x["data"]["value"] for x in logger.get_logs_by_type("x", 2)], [2, 4])

            asyncio.run(logger.log("utc", {}))
            entry = json.loads(Path(logger.audit_file).read_text().splitlines()[-1])
            self.assertTrue(entry["timestamp"].endswith("+00:00"))

    def test_file_prompt_enforces_total_limit(self):
        from handlers.file_processor import FileProcessor

        files = [
            {"filename": f"file{i}.txt", "size": 100, "content": "x" * 8000}
            for i in range(5)
        ]
        formatted = FileProcessor().format_for_prompt(files)
        self.assertLessEqual(len(formatted), 20050)
        self.assertIn("total limit reached", formatted)


class TestMessageHandlerRegressions(unittest.TestCase):
    def test_assistant_history_maps_to_model(self):
        from handlers.message_handler import _to_gemini_history

        result = _to_gemini_history([{"role": "assistant", "content": "hello"}])
        self.assertEqual(result[0]["role"], "model")

    def test_tracker_eviction_removes_keys_consistently(self):
        from handlers.message_handler import MessageHandler

        handler = object.__new__(MessageHandler)
        handler._MAX_CHANNEL_TRACKERS = 2
        handler._last_tool_calls = {"a": {}, "b": {}, "c": {}}
        handler._last_response_text = {"a": "", "b": "", "c": ""}
        handler._last_tool_result_fp = {"a": {}, "b": {}, "c": {}}
        handler._evict_trackers_if_needed()
        self.assertEqual(set(handler._last_tool_calls), set(handler._last_response_text))
        self.assertEqual(set(handler._last_tool_calls), set(handler._last_tool_result_fp))


class TestToolExecutorRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_audit_logs_require_identity_and_moderator(self):
        from services.tool_executor import ToolExecutor

        audit = SimpleNamespace(aget_recent_logs=AsyncMock(return_value=[]))
        bot = SimpleNamespace(audit_logger=audit)
        executor = ToolExecutor(bot)
        self.assertIn("Akses ditolak", (await executor._get_audit_logs())["error"])

        guild = SimpleNamespace(get_member=lambda _: SimpleNamespace(
            guild_permissions=SimpleNamespace(manage_messages=False, administrator=False)
        ))
        bot.get_channel = lambda _: SimpleNamespace(guild=guild)
        self.assertIn("Akses ditolak", (await executor._get_audit_logs(channel_id=1, user_id=2))["error"])

    async def test_attachment_lookup_prefers_newest_cache_entry(self):
        from services.tool_executor import ToolExecutor

        bot = SimpleNamespace(
            audit_logger=None,
            _file_attachment_cache={
                "1_old": [{"filename": "same.txt", "content": "old", "size": 3}],
                "1_new": [{"filename": "same.txt", "content": "new", "size": 3}],
            },
        )
        result = await ToolExecutor(bot)._read_attachment("same.txt", channel_id=1)
        self.assertEqual(result["content"], "new")


class TestRagLockRegressions(unittest.TestCase):
    def test_locked_rag_lock_is_not_evicted(self):
        from memory.rag_store import RagStore

        settings = TempSettings(tempfile.mkdtemp())
        store = RagStore(settings)
        store.MAX_LOCKS = 2
        first = store._get_lock("first")
        second = store._get_lock("second")
        asyncio.run(first.acquire())
        store._get_lock("third")
        self.assertIs(store._channel_locks["first"], first)
        first.release()
        self.assertIn("third", store._channel_locks)


class TestHyperbrowserRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_data_image_is_decoded(self):
        from services.hyperbrowser_client import HyperbrowserClient

        client = object.__new__(HyperbrowserClient)
        raw = b"image-bytes"
        result = await client._coerce_image_bytes(
            "data:image/png;base64," + base64.b64encode(raw).decode()
        )
        self.assertEqual(result, raw)

    async def test_remote_non_image_is_rejected(self):
        from services.hyperbrowser_client import HyperbrowserClient

        class Response:
            status = 200
            headers = {"Content-Type": "text/html"}

            class Content:
                async def iter_chunked(self, _):
                    yield b"not image"

            content = Content()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

        client = object.__new__(HyperbrowserClient)
        client._guard = SimpleNamespace(
            _is_safe_url_async=AsyncMock(return_value=(True, "")),
            _get_session=AsyncMock(return_value=SimpleNamespace(get=lambda *a, **k: Response())),
        )
        self.assertIsNone(await client._coerce_image_bytes("https://example.com/image"))


class TestGeminiRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_no_keys_has_actionable_error(self):
        # google-genai is optional in the local test environment; stub only imports.
        if "google.genai" not in sys.modules:
            google = py_types.ModuleType("google")
            genai = py_types.ModuleType("google.genai")
            sdk_types = py_types.SimpleNamespace()
            genai.Client = object
            genai.types = sdk_types
            google.genai = genai
            sys.modules.setdefault("google", google)
            sys.modules.setdefault("google.genai", genai)
            sys.modules.setdefault("google.genai.types", sdk_types)

        module = importlib.import_module("services.gemini_client")

        class Settings:
            GEMINI_API_KEYS = []
            GEMINI_MODEL = "model"
            GEMINI_FALLBACK_MODELS = []
            GEMINI_OUTPUT_LIMIT = 10

        client = module.GeminiClient.__new__(module.GeminiClient)
        client.keys = []
        client.model_chain = ["model"]
        client.model_name = "model"
        with self.assertRaisesRegex(ValueError, "No Gemini API keys"):
            await client._run_with_fallback(AsyncMock())
