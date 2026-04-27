import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.agent import _safe_parse_json_args, Model, Agent


class TestSafeParseJsonArgs(unittest.TestCase):
    def test_valid_json(self):
        self.assertEqual(_safe_parse_json_args('{"a": 1}'), {"a": 1})

    def test_empty_string(self):
        self.assertEqual(_safe_parse_json_args(""), {})
        self.assertEqual(_safe_parse_json_args(None), {})

    def test_js_bool_conversion(self):
        self.assertEqual(_safe_parse_json_args('{"ok": true}'), {"ok": True})
        self.assertEqual(_safe_parse_json_args('{"ok": false}'), {"ok": False})
        self.assertEqual(_safe_parse_json_args('{"val": null}'), {"val": None})

    def test_ast_fallback(self):
        self.assertEqual(_safe_parse_json_args("{'name': 'test'}"), {"name": "test"})

    def test_malformed_string(self):
        self.assertEqual(_safe_parse_json_args("not json at all"), {})

    def test_nested_object(self):
        result = _safe_parse_json_args('{"user": {"name": "alice", "age": 30}}')
        self.assertEqual(result, {"user": {"name": "alice", "age": 30}})

    def test_array_args(self):
        result = _safe_parse_json_args('["a", "b", "c"]')
        self.assertEqual(result, ["a", "b", "c"])


class TestExtractReasoningContent(unittest.TestCase):
    def test_chunk_with_direct_attr(self):
        chunk = MagicMock()
        chunk.reasoning_content = "thinking step 1"
        result = Agent._extract_reasoning_content(chunk)
        self.assertEqual(result, "thinking step 1")

    def test_chunk_with_additional_kwargs(self):
        chunk = MagicMock()
        chunk.reasoning_content = None
        chunk.additional_kwargs = {"reasoning_content": "thinking in kwargs"}
        chunk.response_metadata = {}
        result = Agent._extract_reasoning_content(chunk)
        self.assertEqual(result, "thinking in kwargs")

    def test_chunk_with_response_metadata(self):
        chunk = MagicMock()
        chunk.reasoning_content = None
        chunk.additional_kwargs = {}
        chunk.response_metadata = {"reasoning_content": "thinking in meta"}
        result = Agent._extract_reasoning_content(chunk)
        self.assertEqual(result, "thinking in meta")

    def test_chunk_with_reasoning_key(self):
        chunk = MagicMock()
        chunk.reasoning_content = None
        chunk.additional_kwargs = {"reasoning": "other model reasoning"}
        result = Agent._extract_reasoning_content(chunk)
        self.assertEqual(result, "other model reasoning")

    def test_chunk_with_thinking_attr(self):
        chunk = MagicMock()
        chunk.reasoning_content = None
        chunk.additional_kwargs = {}
        chunk.response_metadata = {}
        chunk.thinking = "think content"
        result = Agent._extract_reasoning_content(chunk)
        self.assertEqual(result, "think content")

    def test_no_reasoning(self):
        chunk = MagicMock()
        chunk.reasoning_content = None
        chunk.additional_kwargs = {}
        chunk.response_metadata = {}
        chunk.thinking = None
        result = Agent._extract_reasoning_content(chunk)
        self.assertIsNone(result)

    def test_direct_attr_priority(self):
        chunk = MagicMock()
        chunk.reasoning_content = "direct"
        chunk.additional_kwargs = {"reasoning_content": "kwargs"}
        result = Agent._extract_reasoning_content(chunk)
        self.assertEqual(result, "direct")


class TestExtractTokenUsage(unittest.TestCase):
    def test_usage_metadata_priority(self):
        chunk = MagicMock()
        chunk.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
        result = Agent._extract_token_usage(chunk)
        self.assertEqual(result, {"input_tokens": 100, "output_tokens": 50})

    def test_response_metadata_token_usage(self):
        chunk = MagicMock()
        chunk.usage_metadata = None
        chunk.response_metadata = {"token_usage": {"prompt_tokens": 200, "completion_tokens": 80}}
        result = Agent._extract_token_usage(chunk)
        self.assertEqual(result, {"input_tokens": 200, "output_tokens": 80})

    def test_response_metadata_usage(self):
        chunk = MagicMock()
        chunk.usage_metadata = None
        chunk.response_metadata = {"usage": {"input_tokens": 300, "output_tokens": 150}}
        result = Agent._extract_token_usage(chunk)
        self.assertEqual(result, {"input_tokens": 300, "output_tokens": 150})

    def test_no_usage_data(self):
        chunk = MagicMock()
        chunk.usage_metadata = None
        chunk.response_metadata = {}
        result = Agent._extract_token_usage(chunk)
        self.assertEqual(result, {"input_tokens": 0, "output_tokens": 0})

    def test_zero_tokens_ignored(self):
        chunk = MagicMock()
        chunk.usage_metadata = {"input_tokens": 0, "output_tokens": 0}
        chunk.response_metadata = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        result = Agent._extract_token_usage(chunk)
        self.assertEqual(result, {"input_tokens": 10, "output_tokens": 5})


class TestEstimateTokens(unittest.TestCase):
    def test_empty_text(self):
        self.assertEqual(Agent._estimate_tokens(""), 0)
        self.assertEqual(Agent._estimate_tokens(None), 0)

    def test_chinese_only(self):
        tokens = Agent._estimate_tokens("你好世界")
        self.assertEqual(tokens, int(4 * 1.5))

    def test_english_only(self):
        tokens = Agent._estimate_tokens("hello world")
        self.assertEqual(tokens, int(11 * 0.25))

    def test_mixed_text(self):
        tokens = Agent._estimate_tokens("你好hello")
        self.assertEqual(tokens, int(2 * 1.5 + 5 * 0.25))


class TestParseToolCallChunks(unittest.TestCase):
    def test_single_tool_call(self):
        chunk = MagicMock()
        chunk.tool_call_chunks = [{"index": 0, "id": "call_1", "name": "search", "args": '{"q":"test"}'}]
        result = Agent._parse_tool_call_chunks([chunk])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "search")
        self.assertEqual(result[0]["args"], '{"q":"test"}')

    def test_multi_chunk_tool_call(self):
        ch1 = MagicMock()
        ch1.tool_call_chunks = [{"index": 0, "id": "call_1", "name": "calc", "args": '{"exp":'}]
        ch2 = MagicMock()
        ch2.tool_call_chunks = [{"index": 0, "id": "call_1", "name": "", "args": '"2+2"}'}]
        result = Agent._parse_tool_call_chunks([ch1, ch2])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["args"], '{"exp":"2+2"}')

    def test_multiple_tool_calls(self):
        ch1 = MagicMock()
        ch1.tool_call_chunks = [{"index": 0, "id": "a", "name": "t1", "args": "{}"}]
        ch2 = MagicMock()
        ch2.tool_call_chunks = [{"index": 1, "id": "b", "name": "t2", "args": "{}"}]
        result = Agent._parse_tool_call_chunks([ch1, ch2])
        self.assertEqual(len(result), 2)


class TestBuildAiMessage(unittest.TestCase):
    def test_no_tool_calls(self):
        msg = Agent._build_ai_message("hello", {})
        self.assertEqual(msg.content, "hello")

    def test_with_tool_calls(self):
        tcd = {0: {"id": "c1", "name": "search", "args": '{"q":"test"}'}}
        msg = Agent._build_ai_message("", tcd)
        self.assertEqual(msg.content, "")
        self.assertTrue(hasattr(msg, "tool_calls"))
        self.assertEqual(msg.tool_calls[0]["name"], "search")
        self.assertEqual(msg.tool_calls[0]["args"], {"q": "test"})


if __name__ == "__main__":
    unittest.main()
