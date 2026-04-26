"""Unit tests for the Codex CLI adapter."""
import pytest
from unittest.mock import AsyncMock, patch

from claudable_helper.cli.adapters.codex_cli import CodexCLI


class _FakeStdin:
    def __init__(self):
        self.buffer = b""
        self.closed = False

    def write(self, data: bytes) -> None:
        self.buffer += data

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, stdout: bytes, stderr: bytes, returncode: int):
        self.stdin = _FakeStdin()
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr


async def _collect_messages(cli: CodexCLI, instruction: str = "Reply with exactly OK"):
    return [
        message
        async for message in cli.execute_with_streaming(
            instruction=instruction,
            project_path="/tmp/project",
        )
    ]


@pytest.mark.unit
@pytest.mark.asyncio
class TestCodexCLI:
    async def test_nonzero_exit_after_completed_turn_is_treated_as_success(self):
        cli = CodexCLI()
        process = _FakeProcess(
            stdout=(
                b'{"type":"thread.started","thread_id":"thr-1"}\n'
                b'{"type":"turn.started"}\n'
                b'{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"OK"}}\n'
                b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n'
            ),
            stderr=(
                b"Reading prompt from stdin...\n"
                b"2026-04-26T12:14:02.638016Z ERROR codex_core::session: "
                b"failed to record rollout items: thread 019dc9b5 not found\n"
            ),
            returncode=1,
        )

        with patch(
            "claudable_helper.cli.adapters.codex_cli.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ):
            messages = await _collect_messages(cli)

        assert [message.content for message in messages] == ["OK"]
        assert all(message.message_type.value != "error" for message in messages)
        assert process.stdin.buffer == b"Reply with exactly OK"
        assert process.stdin.closed is True

    async def test_turn_failed_event_is_reported_as_error(self):
        cli = CodexCLI()
        process = _FakeProcess(
            stdout=(
                b'{"type":"thread.started","thread_id":"thr-2"}\n'
                b'{"type":"turn.started"}\n'
                b'{"type":"turn.failed","error":{"message":"bad model"}}\n'
            ),
            stderr=b"",
            returncode=1,
        )

        with patch(
            "claudable_helper.cli.adapters.codex_cli.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ):
            messages = await _collect_messages(cli)

        assert len(messages) == 1
        assert messages[0].message_type.value == "error"
        assert "bad model" in messages[0].content
