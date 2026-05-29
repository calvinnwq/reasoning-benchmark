from __future__ import annotations

import json
import os
import sys
import tempfile
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

    def test_adapter_result_payload_includes_usage_when_present(self) -> None:
        result = benchmark_adapters.AdapterResult(
            answer="A",
            reasoning="B",
            usage={"input_tokens": 12, "output_tokens": 3, "provider": "unit"},
        )
        self.assertEqual(
            result.to_payload(),
            {
                "answer": "A",
                "reasoning": "B",
                "usage": {"input_tokens": 12, "output_tokens": 3, "provider": "unit"},
            },
        )

    def test_run_api_adapter_qwen_uses_ollama(self) -> None:
        with patch.object(benchmark_adapters, "run_ollama", return_value=benchmark_adapters.AdapterResult("A", "B")) as mock_run:
            result = benchmark_adapters.run_api_adapter("qwen3.5-9b", "Prompt")
        self.assertEqual(result.answer, "A")
        mock_run.assert_called_once_with("qwen3.5:9b", "Prompt")

    def test_run_api_adapter_reports_unwired_direct_models(self) -> None:
        with self.assertRaises(benchmark_adapters.AdapterError):
            benchmark_adapters.run_api_adapter("gpt-5.4", "Prompt")
        with self.assertRaises(benchmark_adapters.AdapterError):
            benchmark_adapters.run_api_adapter("gpt-5.5-xhigh", "Prompt")
        with self.assertRaises(benchmark_adapters.AdapterError):
            benchmark_adapters.run_api_adapter("opus-4.8-max", "Prompt")
        with self.assertRaises(benchmark_adapters.AdapterError):
            benchmark_adapters.run_api_adapter("opus-4.7-max", "Prompt")

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

    def test_run_cli_adapter_routes_new_reasoning_models(self) -> None:
        with patch.object(benchmark_adapters, "run_codex_cli", return_value=benchmark_adapters.AdapterResult("A", "B")) as mock_codex, patch.object(
            benchmark_adapters,
            "run_claude_cli",
            return_value=benchmark_adapters.AdapterResult("C", "D"),
        ) as mock_claude:
            gpt = benchmark_adapters.run_cli_adapter("gpt-5.5-xhigh", "Prompt one")
            opus = benchmark_adapters.run_cli_adapter("opus-4.8-max", "Prompt two")
            opus47 = benchmark_adapters.run_cli_adapter("opus-4.7-max", "Prompt three")

        self.assertEqual(gpt.answer, "A")
        self.assertEqual(opus.answer, "C")
        self.assertEqual(opus47.answer, "C")
        mock_codex.assert_called_once_with("gpt-5.5", "Prompt one", reasoning_effort="xhigh")
        self.assertEqual(
            [call.args for call in mock_claude.call_args_list],
            [("claude-opus-4-8", "Prompt two"), ("claude-opus-4-7", "Prompt three")],
        )
        self.assertEqual(
            [call.kwargs for call in mock_claude.call_args_list],
            [{"effort": "max"}, {"effort": "max"}],
        )

    def test_run_codex_cli_passes_reasoning_effort(self) -> None:
        output = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": '{"answer":"Drive there.","reasoning":"The car must reach the wash"}',
                },
            }
        ) + "\n" + json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 100,
                    "cached_input_tokens": 25,
                    "output_tokens": 10,
                    "reasoning_output_tokens": 7,
                },
            }
        )
        with patch.object(benchmark_adapters, "run_codex_subprocess", return_value=output) as mock_run:
            result = benchmark_adapters.run_codex_cli("gpt-5.5", "Prompt", reasoning_effort="xhigh")

        self.assertEqual(result.answer, "Drive there.")
        self.assertEqual(result.usage["provider"], "codex")
        self.assertEqual(result.usage["input_tokens"], 100)
        self.assertEqual(result.usage["cache_read_input_tokens"], 25)
        self.assertEqual(result.usage["reasoning_output_tokens"], 7)
        self.assertIn('model_reasoning_effort="xhigh"', mock_run.call_args.args[0])
        self.assertIn("--ignore-user-config", mock_run.call_args.args[0])
        self.assertIn("--ignore-rules", mock_run.call_args.args[0])

    def test_run_codex_subprocess_uses_temporary_auth_home_and_cleans_up(self) -> None:
        seen_home: Path | None = None

        with tempfile.TemporaryDirectory() as source_home:
            auth_path = Path(source_home) / "auth.json"
            auth_path.write_text('{"auth_mode":"chatgpt"}', encoding="utf-8")

            def fake_run(command, *, timeout=None, env=None):
                nonlocal seen_home
                self.assertIsNotNone(env)
                seen_home = Path(env["CODEX_HOME"])
                self.assertTrue((seen_home / "auth.json").is_file())
                self.assertFalse((seen_home / "config.toml").exists())
                return "{}"

            with patch.dict(os.environ, {"REASONING_BENCHMARK_CODEX_HOME": source_home}), patch.object(
                benchmark_adapters, "run_subprocess", side_effect=fake_run
            ):
                benchmark_adapters.run_codex_subprocess(["codex"], timeout=1)

        self.assertIsNotNone(seen_home)
        self.assertFalse(seen_home.exists())

    def test_run_codex_subprocess_cleanup_does_not_mask_completed_output(self) -> None:
        seen_home: Path | None = None

        with tempfile.TemporaryDirectory() as source_home:
            auth_path = Path(source_home) / "auth.json"
            auth_path.write_text('{"auth_mode":"chatgpt"}', encoding="utf-8")

            def fake_run(command, *, timeout=None, env=None):
                nonlocal seen_home
                self.assertIsNotNone(env)
                seen_home = Path(env["CODEX_HOME"])
                (seen_home / "plugins" / "late-write").mkdir(parents=True)
                return '{"answer":"A","reasoning":"B"}'

            with patch.dict(os.environ, {"REASONING_BENCHMARK_CODEX_HOME": source_home}), patch.object(
                benchmark_adapters,
                "run_subprocess",
                side_effect=fake_run,
            ), patch.object(
                benchmark_adapters.shutil,
                "rmtree",
                side_effect=OSError("Directory not empty: 'plugins'"),
            ):
                output = benchmark_adapters.run_codex_subprocess(["codex"], timeout=1)

        self.assertEqual(output, '{"answer":"A","reasoning":"B"}')
        self.assertIsNotNone(seen_home)
        self.assertFalse((seen_home / "auth.json").exists())

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
        outer = json.dumps(
            {
                "result": '{"answer":"Open the window","reasoning":"They are making a polite request"}',
                "duration_ms": 1234,
                "total_cost_usd": 0.5,
                "usage": {
                    "input_tokens": 11,
                    "output_tokens": 22,
                    "cache_read_input_tokens": 33,
                    "cache_creation_input_tokens": 44,
                },
                "modelUsage": {
                    "claude-sonnet-4-6": {
                        "inputTokens": 11,
                        "outputTokens": 22,
                    }
                },
            }
        )
        with patch.object(benchmark_adapters, "run_subprocess", return_value=outer) as mock_run:
            result = benchmark_adapters.run_claude_cli("claude-sonnet-4-6", "Prompt")
        self.assertEqual(result.answer, "Open the window")
        self.assertEqual(result.usage["provider"], "claude")
        self.assertEqual(result.usage["input_tokens"], 11)
        self.assertEqual(result.usage["output_tokens"], 22)
        self.assertEqual(result.usage["cache_creation_input_tokens"], 44)
        self.assertEqual(result.usage["duration_ms"], 1234)
        self.assertEqual(result.usage["provider_reported_cost_usd"], 0.5)
        command = mock_run.call_args.args[0]
        self.assertIn("--disable-slash-commands", command)
        self.assertIn("--strict-mcp-config", command)
        self.assertIn("--tools", command)
        self.assertIn('{"mcpServers":{}}', command)

    def test_run_opencode_cli_parses_event_text(self) -> None:
        output = "\n".join(
            [
                json.dumps(
                    {
                        "usage": {
                            "inputTokens": 13,
                            "outputTokens": 5,
                            "reasoningOutputTokens": 4,
                            "costUSD": 0.02,
                        }
                    }
                ),
                json.dumps({"text": '{"answer":"No","reasoning":"Use the umbrella in rain to test it"}'}),
            ]
        )
        with patch.object(benchmark_adapters, "run_subprocess", return_value=output):
            result = benchmark_adapters.run_opencode_cli("openai/gpt-5.4", "Prompt")
        self.assertEqual(result.answer, "No")
        self.assertEqual(result.usage["provider"], "opencode")
        self.assertEqual(result.usage["input_tokens"], 13)
        self.assertEqual(result.usage["output_tokens"], 5)
        self.assertEqual(result.usage["reasoning_output_tokens"], 4)
        self.assertEqual(result.usage["provider_reported_cost_usd"], 0.02)

    def test_run_ollama_uses_thinking_fallback(self) -> None:
        outer = json.dumps(
            {
                "response": "",
                "thinking": '{"answer":"Drive there","reasoning":"The car must be there"}',
                "prompt_eval_count": 8,
                "eval_count": 9,
                "total_duration": 12_500_000,
            }
        )

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
        self.assertEqual(result.usage["provider"], "ollama")
        self.assertEqual(result.usage["input_tokens"], 8)
        self.assertEqual(result.usage["output_tokens"], 9)
        self.assertEqual(result.usage["duration_ms"], 12)


if __name__ == "__main__":
    unittest.main()
