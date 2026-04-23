#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib import error, request

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from benchmark_contract import build_model_prompt

SUPPORTED_MODELS: tuple[str, ...] = ("gpt-5.4", "sonnet-4.6", "qwen3.5-9b")


@dataclass(frozen=True)
class AdapterResult:
    answer: str
    reasoning: str
    notes: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "answer": self.answer,
            "reasoning": self.reasoning,
        }
        if self.notes:
            payload["notes"] = self.notes
        return payload


class AdapterError(RuntimeError):
    pass


def normalize_result_payload(payload: Any) -> AdapterResult:
    if not isinstance(payload, dict):
        raise AdapterError("adapter payload must be a JSON object")

    answer = payload.get("answer", "")
    reasoning = payload.get("reasoning", "")
    notes = payload.get("notes")

    if not isinstance(answer, str):
        answer = str(answer)
    if not isinstance(reasoning, str):
        reasoning = str(reasoning)
    if notes is not None and not isinstance(notes, str):
        notes = str(notes)

    return AdapterResult(answer=answer.strip(), reasoning=reasoning.strip(), notes=notes)


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


def run_subprocess(command: Sequence[str], *, timeout: float | None = None) -> str:
    process = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip() or f"exit {process.returncode}"
        raise AdapterError(detail)
    return process.stdout


def run_codex_cli(model: str, question_prompt: str, *, timeout: float = 120.0) -> AdapterResult:
    prompt = build_model_prompt(question_prompt)
    command = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--json",
        "--model",
        model,
        prompt,
    ]
    stdout = run_subprocess(command, timeout=timeout)

    last_message = None
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
    return normalize_result_payload(extract_json_object(last_message))


def run_claude_cli(model: str, question_prompt: str, *, timeout: float = 120.0) -> AdapterResult:
    prompt = build_model_prompt(question_prompt)
    command = [
        "claude",
        "--print",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
        "--no-session-persistence",
        "--model",
        model,
        prompt,
    ]
    stdout = run_subprocess(command, timeout=timeout)
    payload = extract_json_object(stdout)

    result_text = payload.get("result")
    if not isinstance(result_text, str):
        raise AdapterError("claude output missing string result field")
    return normalize_result_payload(extract_json_object(result_text))


def run_opencode_cli(model: str, question_prompt: str, *, timeout: float = 120.0) -> AdapterResult:
    prompt = build_model_prompt(question_prompt)
    command = [
        "opencode",
        "run",
        "--format",
        "json",
        "--model",
        model,
        prompt,
    ]
    stdout = run_subprocess(command, timeout=timeout)

    last_text = None
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
    return normalize_result_payload(extract_json_object(last_text))


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

    if isinstance(response_text, str) and response_text.strip():
        return normalize_result_payload(extract_json_object(response_text))
    if isinstance(thinking_text, str) and thinking_text.strip():
        result = normalize_result_payload(extract_json_object(thinking_text))
        notes = result.notes or "ollama_used_thinking_fallback"
        return AdapterResult(answer=result.answer, reasoning=result.reasoning, notes=notes)
    raise AdapterError("ollama response missing text body")


def run_api_adapter(model: str, question_prompt: str) -> AdapterResult:
    if model == "gpt-5.4":
        raise AdapterError("direct API adapter for gpt-5.4 is not wired yet; use CLI adapter or implement API transport")
    if model == "sonnet-4.6":
        raise AdapterError("direct API adapter for sonnet-4.6 is not wired yet; use CLI adapter or implement API transport")
    if model == "qwen3.5-9b":
        return run_ollama("qwen3.5:9b", question_prompt)
    raise AdapterError(f"unsupported model: {model}")


def run_cli_adapter(model: str, question_prompt: str, *, prefer: str = "subscription") -> AdapterResult:
    if model == "gpt-5.4":
        if prefer == "opencode":
            return run_opencode_cli("openai/gpt-5.4", question_prompt)
        return run_codex_cli("gpt-5.4", question_prompt)
    if model == "sonnet-4.6":
        if prefer == "opencode":
            return run_opencode_cli("anthropic/claude-sonnet-4.6", question_prompt)
        return run_claude_cli("claude-sonnet-4-6", question_prompt)
    if model == "qwen3.5-9b":
        return run_api_adapter(model, question_prompt)
    raise AdapterError(f"unsupported model: {model}")
