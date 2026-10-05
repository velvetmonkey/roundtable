"""Check error messages at the Grok and Antigravity MCP tool boundary."""

import pytest

from claudable_helper.models.messages import Message, MessageType
from roundtable_mcp_server import server as server_module


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,adapter_name,tool_name",
    [
        ("grok", "GrokCLI", "grok_subagent"),
        ("antigravity", "AntigravityCLI", "antigravity_subagent"),
    ],
)
@pytest.mark.parametrize(
    "instruction,contents,expected",
    [
        (
            " \t\n",
            [(MessageType.ERROR, "Instruction must not be empty or whitespace-only.")],
            "❌ Instruction must not be empty or whitespace-only. (agent=unknown)",
        ),
        (
            "normal",
            [(MessageType.ASSISTANT, "Answer  Ω")],
            "**{label}:**\nAnswer  Ω",
        ),
        (
            "partial",
            [
                (MessageType.ASSISTANT, "partial answer"),
                (MessageType.ERROR, "CLI failed after partial output"),
            ],
            "❌ CLI failed after partial output (agent=unknown)",
        ),
    ],
)
async def test_tool_propagates_adapter_messages(
    monkeypatch, tmp_path, name, adapter_name, tool_name, instruction, contents, expected
):
    class FakeAdapter:
        async def check_availability(self):
            return {"available": True}

        async def execute_with_streaming(self, **kwargs):
            assert kwargs["instruction"] == instruction
            for message_type, content in contents:
                yield Message(role="assistant", message_type=message_type, content=content)

    monkeypatch.setattr(server_module, adapter_name, FakeAdapter)
    monkeypatch.setattr(server_module, "enabled_subagents", {name})
    monkeypatch.setattr(server_module, "ERROR_HANDLING_AVAILABLE", True)

    result = await getattr(server_module, tool_name)(instruction, str(tmp_path))
    label = "Grok" if name == "grok" else "Antigravity"
    assert result == expected.format(label=label)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,adapter_name,tool_name",
    [
        ("grok", "GrokCLI", "grok_subagent"),
        ("antigravity", "AntigravityCLI", "antigravity_subagent"),
    ],
)
async def test_tool_reports_absent_cli(monkeypatch, tmp_path, name, adapter_name, tool_name):
    class FakeAdapter:
        async def check_availability(self):
            return {"available": False}

    monkeypatch.setattr(server_module, adapter_name, FakeAdapter)
    monkeypatch.setattr(server_module, "enabled_subagents", {name})
    monkeypatch.setattr(server_module, "ERROR_HANDLING_AVAILABLE", True)

    result = await getattr(server_module, tool_name)("normal", str(tmp_path))
    assert result.startswith(f"❌ {name.capitalize()} CLI not available:")
