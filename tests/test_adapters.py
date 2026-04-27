from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch
import unittest

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
sys.path.append(str(REPO_ROOT / "scripts"))

import benchmark_adapters
import benchmark_contract


class ContractTests(unittest.TestCase):
    def test_prompt_contract_is_shared(self) -> None:
        prompt = benchmark_contract.build_model_prompt("Should I walk my flat-tyre bike to the shop?")
        self.assertIn("Return JSON only", prompt)
        self.assertIn("Question:", prompt)
        self.assertIn("flat-tyre bike", prompt)

    def test_prompt_contract_exposes_v2_response_shape_metadata(self) -> None:
        contract = benchmark_contract.build_prompt_contract()
        self.assertEqual(contract["response_format"], "json_object")
        self.assertEqual(contract["required_fields"], ["answer", "reasoning"])


class AdapterParsingTests(unittest.TestCase):
    def test_extract_json_object_from_wrapped_text(self) -> None:
        payload = benchmark_adapters.extract_json_object(
            "noise before\n{\"answer\":\"Drive there\",\"reasoning\":\"The car must reach the wash\"}\nnoise after"
        )
        self.assertEqual(payload["answer"], "Drive there")

    def test_normalize_result_payload_coerces_values(self) -> None:
        result = benchmark_adapters.normalize_result_payload({"answer": 42, "reasoning": True, "notes": ["x"]})
        self.assertEqual(result.answer, "42")
        self.assertEqual(result.reasoning, "True")
        self.assertEqual(result.notes, "['x']")

    def test_run_api_adapter_qwen_uses_ollama(self) -> None:
        with patch.object(benchmark_adapters, "run_ollama", return_value=benchmark_adapters.AdapterResult("A", "B")) as mock_run:
            result = benchmark_adapters.run_api_adapter("qwen3.5-9b", "Prompt")
        self.assertEqual(result.answer, "A")
        mock_run.assert_called_once_with("qwen3.5:9b", "Prompt")

    def test_run_api_adapter_reports_unwired_direct_models(self) -> None:
        with self.assertRaises(benchmark_adapters.AdapterError):
            benchmark_adapters.run_api_adapter("gpt-5.4", "Prompt")

    def test_run_cli_adapter_subscription_routes_expected_harnesses(self) -> None:
        with patch.object(benchmark_adapters, "run_codex_cli", return_value=benchmark_adapters.AdapterResult("A", "B")) as mock_codex, patch.object(
            benchmark_adapters,
            "run_claude_cli",
            return_value=benchmark_adapters.AdapterResult("C", "D"),
        ) as mock_claude:
            gpt = benchmark_adapters.run_cli_adapter("gpt-5.4", "Prompt one")
            sonnet = benchmark_adapters.run_cli_adapter("sonnet-4.6", "Prompt two")
        self.assertEqual(gpt.answer, "A")
        self.assertEqual(sonnet.answer, "C")
        mock_codex.assert_called_once_with("gpt-5.4", "Prompt one")
        mock_claude.assert_called_once_with("claude-sonnet-4-6", "Prompt two")

    def test_run_cli_adapter_opencode_preference_routes_expected_models(self) -> None:
        with patch.object(benchmark_adapters, "run_opencode_cli", return_value=benchmark_adapters.AdapterResult("A", "B")) as mock_open:
            benchmark_adapters.run_cli_adapter("gpt-5.4", "Prompt one", prefer="opencode")
            benchmark_adapters.run_cli_adapter("sonnet-4.6", "Prompt two", prefer="opencode")
        calls = [call.args for call in mock_open.call_args_list]
        self.assertEqual(calls, [("openai/gpt-5.4", "Prompt one"), ("anthropic/claude-sonnet-4.6", "Prompt two")])

    def test_run_codex_cli_parses_jsonl_output(self) -> None:
        output = "\n".join(
            [
                json.dumps({"msg": {"type": "assistant", "content": [{"type": "output_text", "text": '{\"answer\":\"Drive there\",\"reasoning\":\"The car needs washing\"}'}]}})
            ]
        )
        with patch.object(benchmark_adapters, "run_subprocess", return_value=output):
            result = benchmark_adapters.run_codex_cli("gpt-5.4", "Prompt")
        self.assertEqual(result.answer, "Drive there")

    def test_run_codex_cli_parses_agent_message_event_shape(self) -> None:
        output = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "abc"}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": '{\"answer\":\"Drive there.\",\"reasoning\":\"The car must reach the wash\"}'}}),
            ]
        )
        with patch.object(benchmark_adapters, "run_subprocess", return_value=output):
            result = benchmark_adapters.run_codex_cli("gpt-5.4", "Prompt")
        self.assertEqual(result.answer, "Drive there.")

    def test_run_claude_cli_parses_result_field_json(self) -> None:
        outer = json.dumps({"result": '{"answer":"Open the window","reasoning":"They are making a polite request"}'})
        with patch.object(benchmark_adapters, "run_subprocess", return_value=outer):
            result = benchmark_adapters.run_claude_cli("claude-sonnet-4-6", "Prompt")
        self.assertEqual(result.answer, "Open the window")

    def test_run_opencode_cli_parses_event_text(self) -> None:
        output = json.dumps({"text": '{"answer":"No","reasoning":"Use the umbrella in rain to test it"}'})
        with patch.object(benchmark_adapters, "run_subprocess", return_value=output):
            result = benchmark_adapters.run_opencode_cli("openai/gpt-5.4", "Prompt")
        self.assertEqual(result.answer, "No")

    def test_run_ollama_uses_thinking_fallback(self) -> None:
        outer = json.dumps({"response": "", "thinking": '{"answer":"Drive there","reasoning":"The car must be there"}'})

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return outer.encode("utf-8")

        with patch.object(benchmark_adapters.request, "urlopen", return_value=_Response()):
            result = benchmark_adapters.run_ollama("qwen3.5:9b", "Prompt")
        self.assertEqual(result.answer, "Drive there")
        self.assertEqual(result.notes, "ollama_used_thinking_fallback")


if __name__ == "__main__":
    unittest.main()
