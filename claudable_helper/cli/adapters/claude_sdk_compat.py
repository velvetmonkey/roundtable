"""Compatibility helpers for the deprecated Claude Code Python SDK.

Roundtable still uses ``claude_code_sdk`` today. Newer Claude Code CLI versions
emit top-level transport events such as ``rate_limit_event`` that older SDK
releases do not understand. The maintained ``claude-agent-sdk`` handles unknown
events gracefully; this shim mirrors that behavior until Roundtable migrates.
"""

from __future__ import annotations

from typing import Any

from claudable_helper.core.terminal_ui import ui

_PATCHED = False


def ensure_compatible_claude_sdk() -> None:
    """Patch the deprecated SDK to skip unknown transport event types.

    The deprecated ``claude_code_sdk`` raises ``MessageParseError`` for any
    top-level message type it does not recognize. That is fatal for callers
    using either ``query()`` or ``ClaudeSDKClient.receive_messages()``. We
    instead return ``None`` for unknown events so callers can ignore them.
    """

    global _PATCHED
    if _PATCHED:
        return

    try:
        from claude_code_sdk._internal import client as internal_client
        from claude_code_sdk._internal import message_parser
        from claude_code_sdk._errors import MessageParseError
    except ImportError:
        return

    original_parse_message = message_parser.parse_message

    def _compatible_parse_message(data: dict[str, Any]) -> Any:
        try:
            return original_parse_message(data)
        except MessageParseError as exc:
            message_type = data.get("type") if isinstance(data, dict) else None
            if message_type == "rate_limit_event":
                ui.debug(
                    "Skipping Claude SDK rate_limit_event transport message",
                    "Claude SDK",
                )
                return None

            if message_type:
                ui.debug(
                    f"Skipping unsupported Claude SDK transport message: {message_type}",
                    "Claude SDK",
                )
                return None

            raise exc

    message_parser.parse_message = _compatible_parse_message
    internal_client.parse_message = _compatible_parse_message
    _PATCHED = True
