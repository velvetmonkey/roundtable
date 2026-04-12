from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _load_compat_module():
    terminal_ui = types.ModuleType("claudable_helper.core.terminal_ui")

    class _UI:
        def debug(self, message: str, category: str = "DEBUG") -> None:
            return None

    terminal_ui.ui = _UI()

    core = types.ModuleType("claudable_helper.core")
    claudable_helper = types.ModuleType("claudable_helper")
    claudable_helper.core = core
    core.terminal_ui = terminal_ui

    sys.modules["claudable_helper"] = claudable_helper
    sys.modules["claudable_helper.core"] = core
    sys.modules["claudable_helper.core.terminal_ui"] = terminal_ui

    module_path = (
        Path(__file__).resolve().parents[2]
        / "claudable_helper"
        / "cli"
        / "adapters"
        / "claude_sdk_compat.py"
    )
    spec = importlib.util.spec_from_file_location("claude_sdk_compat_under_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rate_limit_event_is_skipped_without_raising() -> None:
    compat = _load_compat_module()
    compat.ensure_compatible_claude_sdk()

    from claude_code_sdk._internal import client as internal_client
    from claude_code_sdk._internal import message_parser

    event = {
        "type": "rate_limit_event",
        "rate_limit_info": {
            "status": "allowed",
            "resetsAt": 1776013200,
            "rateLimitType": "five_hour",
            "isUsingOverage": False,
        },
        "uuid": "abc",
        "session_id": "sid",
    }

    assert message_parser.parse_message(event) is None
    assert internal_client.parse_message(event) is None


def test_unknown_top_level_event_is_skipped_without_raising() -> None:
    compat = _load_compat_module()
    compat.ensure_compatible_claude_sdk()

    from claude_code_sdk._internal import client as internal_client
    from claude_code_sdk._internal import message_parser

    event = {"type": "future_event", "payload": {"x": 1}}

    assert message_parser.parse_message(event) is None
    assert internal_client.parse_message(event) is None


def test_known_messages_still_parse() -> None:
    compat = _load_compat_module()
    compat.ensure_compatible_claude_sdk()

    from claude_code_sdk._internal import message_parser

    assistant = {
        "type": "assistant",
        "message": {
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "OK"}],
        },
    }

    parsed = message_parser.parse_message(assistant)

    assert parsed is not None
    assert getattr(parsed, "model", None) == "claude-sonnet-4-6"
    assert getattr(parsed.content[0], "text", None) == "OK"
