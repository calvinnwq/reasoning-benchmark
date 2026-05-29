#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib import error, request

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from benchmark_contract import build_model_prompt

SUPPORTED_MODELS: tuple[str, ...] = (
    "gpt-5.4",
    "gpt-5.5-xhigh",
    "sonnet-4.6",
    "opus-4.7-max",
    "opus-4.8-max",
    "qwen3.5-9b",
)


@dataclass(frozen=True)
class AdapterResult:
    answer: str
    reasoning: str
    notes: str | None = None
    usage: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "answer": self.answer,
            "reasoning": self.reasoning,
        }
        if self.notes:
            payload["notes"] = self.notes
        if self.usage:
            payload["usage"] = self.usage
        return payload


class AdapterError(RuntimeError):
    pass


def normalize_result_payload(payload: Any) -> AdapterResult:
    if not isinstance(payload, dict):
        raise AdapterError("adapter payload must be a JSON object")

    answer = payload.get("answer", "")
    reasoning = payload.get("reasoning", "")
    notes = payload.get("notes")
    usage = normalize_usage_payload(payload.get("usage"))

    if not isinstance(answer, str):
        answer = str(answer)
    if not isinstance(reasoning, str):
        reasoning = str(reasoning)
    if notes is not None and not isinstance(notes, str):
        notes = str(notes)

    return AdapterResult(answer=answer.strip(), reasoning=reasoning.strip(), notes=notes, usage=usage)


def json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value


def int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def compact_usage(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None and value != {}}


def first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def normalize_usage_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    usage = compact_usage(
        {
            "input_tokens": int_or_none(value.get("input_tokens")),
            "output_tokens": int_or_none(value.get("output_tokens")),
            "reasoning_output_tokens": int_or_none(value.get("reasoning_output_tokens")),
            "cache_read_input_tokens": int_or_none(value.get("cache_read_input_tokens")),
            "cache_creation_input_tokens": int_or_none(value.get("cache_creation_input_tokens")),
            "duration_ms": int_or_none(value.get("duration_ms")),
            "provider_reported_cost_usd": float_or_none(value.get("provider_reported_cost_usd")),
        }
    )
    for key in ("provider", "provider_usage", "provider_model_usage"):
        if key in value:
            usage[key] = json_safe(value[key])
    return usage or None


def codex_usage_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    usage = event.get("usage")
    if not isinstance(usage, dict):
        return None
    return compact_usage(
        {
            "provider": "codex",
            "input_tokens": int_or_none(usage.get("input_tokens")),
            "output_tokens": int_or_none(usage.get("output_tokens")),
            "reasoning_output_tokens": int_or_none(usage.get("reasoning_output_tokens")),
            "cache_read_input_tokens": int_or_none(usage.get("cached_input_tokens")),
            "provider_usage": json_safe(usage),
        }
    )


def claude_usage_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    return compact_usage(
        {
            "provider": "claude",
            "input_tokens": int_or_none(usage.get("input_tokens")),
            "output_tokens": int_or_none(usage.get("output_tokens")),
            "cache_read_input_tokens": int_or_none(usage.get("cache_read_input_tokens")),
            "cache_creation_input_tokens": int_or_none(usage.get("cache_creation_input_tokens")),
            "duration_ms": int_or_none(payload.get("duration_ms")),
            "provider_reported_cost_usd": float_or_none(payload.get("total_cost_usd")),
            "provider_usage": json_safe(usage),
            "provider_model_usage": json_safe(payload.get("modelUsage")) if payload.get("modelUsage") is not None else None,
        }
    )


def opencode_usage_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    usage = event.get("usage")
    if not isinstance(usage, dict):
        return None
    return compact_usage(
        {
            "provider": "opencode",
            "input_tokens": int_or_none(first_present(usage, "input_tokens", "inputTokens")),
            "output_tokens": int_or_none(first_present(usage, "output_tokens", "outputTokens")),
            "reasoning_output_tokens": int_or_none(
                first_present(usage, "reasoning_output_tokens", "reasoningOutputTokens")
            ),
            "cache_read_input_tokens": int_or_none(
                first_present(usage, "cache_read_input_tokens", "cacheReadInputTokens")
            ),
            "cache_creation_input_tokens": int_or_none(
                first_present(usage, "cache_creation_input_tokens", "cacheCreationInputTokens")
            ),
            "provider_reported_cost_usd": float_or_none(first_present(usage, "cost_usd", "costUSD")),
            "provider_usage": json_safe(usage),
        }
    )


def ollama_usage_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    total_duration = int_or_none(payload.get("total_duration"))
    load_duration = int_or_none(payload.get("load_duration"))
    prompt_eval_duration = int_or_none(payload.get("prompt_eval_duration"))
    eval_duration = int_or_none(payload.get("eval_duration"))
    provider_usage = {
        key: payload[key]
        for key in (
            "total_duration",
            "load_duration",
            "prompt_eval_count",
            "prompt_eval_duration",
            "eval_count",
            "eval_duration",
        )
        if key in payload
    }
    return compact_usage(
        {
            "provider": "ollama",
            "input_tokens": int_or_none(payload.get("prompt_eval_count")),
            "output_tokens": int_or_none(payload.get("eval_count")),
            "duration_ms": round(total_duration / 1_000_000) if total_duration is not None else None,
            "provider_usage": compact_usage(
                {
                    **provider_usage,
                    "total_duration_ms": round(total_duration / 1_000_000) if total_duration is not None else None,
                    "load_duration_ms": round(load_duration / 1_000_000) if load_duration is not None else None,
                    "prompt_eval_duration_ms": round(prompt_eval_duration / 1_000_000) if prompt_eval_duration is not None else None,
                    "eval_duration_ms": round(eval_duration / 1_000_000) if eval_duration is not None else None,
                }
            ),
        }
    )


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise AdapterError("empty adapter output")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AdapterError("adapter output did not contain JSON object")

    snippet = text[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError as exc:
        raise AdapterError(f"failed to parse adapter JSON: {exc}") from exc


def run_subprocess(
    command: Sequence[str],
    *,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
) -> str:
    process = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip() or f"exit {process.returncode}"
        raise AdapterError(detail)
    return process.stdout


def resolve_codex_auth_path() -> Path:
    override_home = os.environ.get("REASONING_BENCHMARK_CODEX_HOME")
    candidate_homes = []
    if override_home:
        candidate_homes.append(Path(override_home).expanduser())
    candidate_homes.append(Path.home() / ".codex")

    for codex_home in candidate_homes:
        auth_path = codex_home / "auth.json"
        if auth_path.is_file():
            return auth_path
    raise AdapterError("codex auth.json not found; log in with Codex before running benchmark")


def run_codex_subprocess(command: Sequence[str], *, timeout: float | None = None) -> str:
    auth_path = resolve_codex_auth_path()
    temp_home_path = Path(tempfile.mkdtemp(prefix="reasoning-benchmark-codex-"))
    try:
        shutil.copy2(auth_path, temp_home_path / "auth.json")
        env = os.environ.copy()
        env["CODEX_HOME"] = str(temp_home_path)
        return run_subprocess(command, timeout=timeout, env=env)
    finally:
        # Codex can leave late-written plugin/cache files under CODEX_HOME after
        # the subprocess exits. Never let best-effort cleanup mask a completed answer.
        (temp_home_path / "auth.json").unlink(missing_ok=True)
        try:
            shutil.rmtree(temp_home_path, ignore_errors=True)
        except OSError:
            pass


def run_codex_cli(
    model: str,
    question_prompt: str,
    *,
    reasoning_effort: str | None = None,
    timeout: float = 120.0,
) -> AdapterResult:
    prompt = build_model_prompt(question_prompt)
    command = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "read-only",
        "--json",
        "--model",
        model,
    ]
    if reasoning_effort is not None:
        command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    command.append(prompt)
    stdout = run_codex_subprocess(command, timeout=timeout)

    last_message = None
    usage = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_usage = codex_usage_from_event(event)
        if event_usage:
            usage = event_usage

        msg = event.get("msg")
        if isinstance(msg, dict) and msg.get("type") == "assistant":
            content = msg.get("content")
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "output_text":
                        text_val = item.get("text", "")
                        if text_val:
                            text_parts.append(str(text_val))
                if text_parts:
                    last_message = "".join(text_parts)

        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            text_val = item.get("text")
            if isinstance(text_val, str) and text_val.strip():
                last_message = text_val
    if not last_message:
        raise AdapterError("codex did not return assistant output")
    result = normalize_result_payload(extract_json_object(last_message))
    return AdapterResult(answer=result.answer, reasoning=result.reasoning, notes=result.notes, usage=usage or result.usage)


def run_claude_cli(
    model: str,
    question_prompt: str,
    *,
    effort: str | None = None,
    timeout: float = 120.0,
) -> AdapterResult:
    prompt = build_model_prompt(question_prompt)
    command = [
        "claude",
        "--print",
        "--output-format",
        "json",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--tools",
        "",
        "--permission-mode",
        "bypassPermissions",
        "--no-session-persistence",
        "--model",
        model,
    ]
    if effort is not None:
        command.extend(["--effort", effort])
    command.append(prompt)
    stdout = run_subprocess(command, timeout=timeout)
    payload = extract_json_object(stdout)

    result_text = payload.get("result")
    if not isinstance(result_text, str):
        raise AdapterError("claude output missing string result field")
    result = normalize_result_payload(extract_json_object(result_text))
    usage = claude_usage_from_payload(payload)
    return AdapterResult(answer=result.answer, reasoning=result.reasoning, notes=result.notes, usage=usage or result.usage)


def run_opencode_cli(
    model: str,
    question_prompt: str,
    *,
    variant: str | None = None,
    timeout: float = 120.0,
) -> AdapterResult:
    prompt = build_model_prompt(question_prompt)
    command = [
        "opencode",
        "run",
        "--format",
        "json",
        "--model",
        model,
    ]
    if variant is not None:
        command.extend(["--variant", variant])
    command.append(prompt)
    stdout = run_subprocess(command, timeout=timeout)

    last_text = None
    usage = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_usage = opencode_usage_from_event(event)
        if event_usage:
            usage = event_usage
        message = event.get("message")
        if isinstance(message, dict):
            parts = message.get("parts")
            if isinstance(parts, list):
                text_parts = []
                for part in parts:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        text_parts.append(part["text"])
                if text_parts:
                    last_text = "".join(text_parts)
        if isinstance(event.get("text"), str):
            last_text = event["text"]
    if not last_text:
        raise AdapterError("opencode did not return assistant output")
    result = normalize_result_payload(extract_json_object(last_text))
    return AdapterResult(answer=result.answer, reasoning=result.reasoning, notes=result.notes, usage=usage or result.usage)


def run_ollama(model_name: str, question_prompt: str, *, timeout: float = 120.0) -> AdapterResult:
    prompt = build_model_prompt(question_prompt)
    url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except error.URLError as exc:
        raise AdapterError(f"ollama request failed: {exc}") from exc
    outer = extract_json_object(raw)
    response_text = outer.get("response", "")
    thinking_text = outer.get("thinking", "")
    usage = ollama_usage_from_payload(outer)

    if isinstance(response_text, str) and response_text.strip():
        result = normalize_result_payload(extract_json_object(response_text))
        return AdapterResult(answer=result.answer, reasoning=result.reasoning, notes=result.notes, usage=usage or result.usage)
    if isinstance(thinking_text, str) and thinking_text.strip():
        result = normalize_result_payload(extract_json_object(thinking_text))
        notes = result.notes or "ollama_used_thinking_fallback"
        return AdapterResult(answer=result.answer, reasoning=result.reasoning, notes=notes, usage=usage or result.usage)
    raise AdapterError("ollama response missing text body")


def run_api_adapter(model: str, question_prompt: str) -> AdapterResult:
    if model == "gpt-5.4":
        raise AdapterError("direct API adapter for gpt-5.4 is not wired yet; use CLI adapter or implement API transport")
    if model == "gpt-5.5-xhigh":
        raise AdapterError("direct API adapter for gpt-5.5-xhigh is not wired yet; use CLI adapter or implement API transport")
    if model == "sonnet-4.6":
        raise AdapterError("direct API adapter for sonnet-4.6 is not wired yet; use CLI adapter or implement API transport")
    if model == "opus-4.8-max":
        raise AdapterError("direct API adapter for opus-4.8-max is not wired yet; use CLI adapter or implement API transport")
    if model == "opus-4.7-max":
        raise AdapterError("direct API adapter for opus-4.7-max is not wired yet; use CLI adapter or implement API transport")
    if model == "qwen3.5-9b":
        return run_ollama("qwen3.5:9b", question_prompt)
    raise AdapterError(f"unsupported model: {model}")


def run_cli_adapter(model: str, question_prompt: str, *, prefer: str = "subscription") -> AdapterResult:
    if model == "gpt-5.4":
        if prefer == "opencode":
            return run_opencode_cli("openai/gpt-5.4", question_prompt)
        return run_codex_cli("gpt-5.4", question_prompt)
    if model == "gpt-5.5-xhigh":
        return run_codex_cli("gpt-5.5", question_prompt, reasoning_effort="xhigh")
    if model == "sonnet-4.6":
        if prefer == "opencode":
            return run_opencode_cli("anthropic/claude-sonnet-4.6", question_prompt)
        return run_claude_cli("claude-sonnet-4-6", question_prompt)
    if model == "opus-4.8-max":
        return run_claude_cli("claude-opus-4-8", question_prompt, effort="max")
    if model == "opus-4.7-max":
        return run_claude_cli("claude-opus-4-7", question_prompt, effort="max")
    if model == "qwen3.5-9b":
        return run_api_adapter(model, question_prompt)
    raise AdapterError(f"unsupported model: {model}")
