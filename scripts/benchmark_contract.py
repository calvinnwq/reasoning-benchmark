#!/usr/bin/env python3
from __future__ import annotations

from typing import Any, Dict

PROMPT_CONTRACT: Dict[str, Any] = {
    "version": "1.0.0",
    "instruction": (
        "Answer the question with a concise final answer.\n"
        "Use this exact JSON shape in the model-facing response:\n"
        '{"answer": "<short final answer>", "reasoning": "<brief reason>"}\n'
        "If unsure, provide your best short answer and reasoning."
    ),
}


def build_prompt_contract() -> Dict[str, Any]:
    return dict(PROMPT_CONTRACT)


def build_model_prompt(question_prompt: str) -> str:
    question_prompt = question_prompt.strip()
    return (
        "You are answering a short natural-language reasoning benchmark question.\n"
        "Do not use tools, files, web search, or external context.\n"
        "Return JSON only. No markdown fences. No extra commentary.\n\n"
        f"{PROMPT_CONTRACT['instruction']}\n\n"
        f"Question:\n{question_prompt}\n"
    )
