"""Forward-compatible hook contract for tool-use and multi-agent extensions.

The reasoning benchmark stays focused on short natural-language reasoning
prompts. M4-02 reserves a small data-first hook so future expansion packs
(for example tool-use or multi-agent benchmarks) can attach metadata to a
``RunConfig`` without dragging those assumptions into the current core.

The contract is intentionally narrow:

* ``RESERVED_EXTENSION_NAMESPACES`` lists the namespaces the framework
  recognises today. Any other key is a configuration error so a typo cannot
  silently disable forward-compatibility checks.
* Each namespace payload must declare an explicit ``enabled`` boolean.
  Until the corresponding milestone ships, ``enabled`` must be ``False`` so
  configs can record planned extensions without activating code paths that
  do not exist yet.
* Everything else inside a namespace payload is opaque to the validator;
  individual expansion packs own their own schema in their own milestone.
"""

from __future__ import annotations

from typing import Any

RESERVED_EXTENSION_NAMESPACES: tuple[str, ...] = ("tool_use", "multi_agent")


def validate_extensions_block(extensions: Any) -> None:
    """Validate a RunConfig (or future case-level) ``extensions`` block.

    ``None`` and ``{}`` are both treated as the no-extension default. Anything
    else must be a JSON object whose top-level keys come from
    :data:`RESERVED_EXTENSION_NAMESPACES`, with a boolean ``enabled`` flag.
    Reserved namespaces with ``enabled=True`` are rejected until the
    corresponding milestone wires their runner support.
    """

    if extensions is None:
        return
    if not isinstance(extensions, dict):
        raise ValueError("extensions must be a JSON object when supplied")

    for namespace, payload in extensions.items():
        if not isinstance(namespace, str) or not namespace:
            raise ValueError("extension namespace must be a non-empty string")
        if namespace != namespace.strip():
            raise ValueError(
                f"extension namespace must not have surrounding whitespace: {namespace!r}"
            )
        if namespace not in RESERVED_EXTENSION_NAMESPACES:
            raise ValueError(
                f"unknown extension namespace: {namespace!r}; "
                f"reserved namespaces: {', '.join(RESERVED_EXTENSION_NAMESPACES)}"
            )
        if not isinstance(payload, dict):
            raise ValueError(
                f"extension namespace {namespace!r} payload must be a JSON object"
            )
        if "enabled" not in payload:
            raise ValueError(
                f"extension namespace {namespace!r} requires explicit 'enabled' boolean"
            )
        enabled = payload["enabled"]
        if not isinstance(enabled, bool):
            raise ValueError(
                f"extension namespace {namespace!r} 'enabled' must be a boolean"
            )
        if enabled:
            raise ValueError(
                f"extension namespace {namespace!r} is reserved but has no "
                "implementation yet; set 'enabled' to false until the "
                "corresponding milestone ships"
            )
