"""Codex CLI provider implementation.

Uses `codex exec --json` (codex-cli >= 0.118.0).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple

from claudable_helper.core.terminal_ui import ui
from claudable_helper.models.messages import Message

from ..base import BaseCLI, CLIType

logger = logging.getLogger(__name__)


class CodexCLI(BaseCLI):
    """Codex CLI implementation using `codex exec --json`"""

    _BENIGN_STDERR_LINES = (
        "Reading prompt from stdin...",
        "failed to record rollout items: thread ",
    )

    def __init__(self):
        super().__init__(CLIType.CODEX)
        self._session_store = {}

    async def check_availability(self) -> Dict[str, Any]:
        """Check if Codex CLI is available"""
        try:
            result = await asyncio.create_subprocess_shell(
                "codex --version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                error_msg = (
                    f"Codex CLI not installed or not working "
                    f"(returncode: {result.returncode}). "
                    f"stderr: {stderr.decode().strip()}"
                )
                return {"available": False, "configured": False, "error": error_msg}

            return {
                "available": True,
                "configured": True,
                "models": self.get_supported_models(),
                "default_models": ["gpt-5-codex"],
            }
        except Exception as e:
            return {
                "available": False,
                "configured": False,
                "error": f"Failed to check Codex CLI: {e}",
            }

    async def execute_with_streaming(
        self,
        instruction: str,
        project_path: str,
        session_id: Optional[str] = None,
        log_callback: Optional[Callable[[str], Any]] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        is_initial_prompt: bool = False,
    ) -> AsyncGenerator[Message, None]:
        """Execute Codex CLI using `codex exec --json`.

        The old `codex proto` interactive protocol was removed in codex-cli
        v0.118.  This adapter uses the non-interactive `codex exec` subcommand
        with ``--json`` to get JSONL event output.
        """
        # Only pass -m when the caller explicitly requested a model.  The
        # hardcoded "gpt-5" default breaks on ChatGPT-account codex installs
        # (which only allow gpt-5-codex); letting codex use its configured
        # default is the safest behavior.
        cli_model = self._get_cli_model_name(model) if model else None
        ui.info(
            f"Starting Codex execution with model: {cli_model or '(codex default)'}",
            "Codex",
        )

        workdir_abs = os.path.abspath(project_path)

        # Build command — subcommand-specific flags must come after `exec`
        cmd = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--cd", workdir_abs,
            "--json",
            "--dangerously-bypass-approvals-and-sandbox",
        ]
        if cli_model:
            cmd.extend(["-m", cli_model])

        # Attach images if provided
        if images:
            for image_data in images:
                path = image_data.get("path") if isinstance(image_data, dict) else None
                if path:
                    cmd.extend(["-i", str(path)])

        # Prompt routes via stdin, NOT argv — codex >= 0.118 with exec --json
        # reads the prompt from stdin and hangs waiting for EOF even when a
        # prompt is given as argv. Passing it on argv with stdin=DEVNULL made
        # codex error "Reading additional input from stdin..." and exit
        # non-zero. Per the characterization in flywheel-ideas'
        # docs/cli-quirks.md (pinned to codex-cli 0.121.0), the discipline is:
        #   - don't append the prompt to argv
        #   - open stdin=PIPE (so codex doesn't inherit our JSON-RPC stdin)
        #   - write the prompt then explicitly close stdin so codex sees EOF

        logger.info(f"[Codex] Running: {' '.join(cmd[:6])} ...")

        try:
            # stdin=PIPE so we can write the prompt then close — prevents
            # inheriting the MCP server's JSON-RPC transport stdin (the
            # original DEVNULL concern) while giving codex the prompt bytes
            # it needs.
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir_abs,
            )

            # Write prompt to stdin then close so codex sees EOF.
            if process.stdin is not None:
                process.stdin.write(instruction.encode("utf-8"))
                await process.stdin.drain()
                process.stdin.close()

            # Wait for the process to complete and collect all output.
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(),
                timeout=300,  # 5 minute hard timeout
            )

            stderr_text = stderr_data.decode("utf-8", errors="replace").strip()
            if stderr_text:
                logger.debug(f"[Codex] stderr: {stderr_text[:500]}")

            parsed_messages, saw_turn_completed, saw_turn_failed, failure_text = (
                self._parse_stdout_events(
                    stdout_data.decode("utf-8", errors="replace"),
                    project_path,
                    session_id,
                )
            )
            has_agent_output = any(m.message_type.value == "chat" for m in parsed_messages)

            # Codex can emit a full successful JSONL turn and then exit non-zero
            # while failing to persist rollout bookkeeping. Trust the JSONL turn
            # outcome first; only promote the exit code to a user-facing failure
            # when the stream itself failed or no usable answer was produced.
            if process.returncode != 0:
                if (
                    has_agent_output
                    and saw_turn_completed
                    and not saw_turn_failed
                    and self._stderr_is_benign(stderr_text)
                ):
                    logger.warning(
                        "[Codex] ignoring non-zero exit after completed turn: %s",
                        stderr_text[:500],
                    )
                    for message in parsed_messages:
                        yield message
                    return

                error_text = failure_text or stderr_text or f"exit code {process.returncode}"
                yield Message(
                    id=str(uuid.uuid4()),
                    project_id=project_path,
                    role="assistant",
                    message_type="error",
                    content=f"Codex failed: {error_text}",
                    metadata_json={"error": "execution_failed", "cli_type": "codex"},
                    session_id=session_id,
                    created_at=datetime.utcnow(),
                )
                return

            for message in parsed_messages:
                yield message

            if saw_turn_failed:
                yield Message(
                    id=str(uuid.uuid4()),
                    project_id=project_path,
                    role="assistant",
                    message_type="error",
                    content=f"Codex failed: {failure_text or 'turn.failed'}",
                    metadata_json={"error": "execution_failed", "cli_type": "codex"},
                    session_id=session_id,
                    created_at=datetime.utcnow(),
                )
                return

        except asyncio.TimeoutError:
            yield Message(
                id=str(uuid.uuid4()),
                project_id=project_path,
                role="assistant",
                message_type="error",
                content="Codex execution timed out after 5 minutes",
                metadata_json={"error": "timeout", "cli_type": "codex"},
                session_id=session_id,
                created_at=datetime.utcnow(),
            )
        except FileNotFoundError:
            yield Message(
                id=str(uuid.uuid4()),
                project_id=project_path,
                role="assistant",
                message_type="error",
                content="Codex CLI not found. Please install Codex CLI first.",
                metadata_json={"error": "cli_not_found", "cli_type": "codex"},
                session_id=session_id,
                created_at=datetime.utcnow(),
            )
        except Exception as e:
            logger.error(f"[Codex] Exception: {e}", exc_info=True)
            yield Message(
                id=str(uuid.uuid4()),
                project_id=project_path,
                role="assistant",
                message_type="error",
                content=f"Codex execution failed: {str(e)}",
                metadata_json={"error": "execution_failed", "cli_type": "codex"},
                session_id=session_id,
                created_at=datetime.utcnow(),
            )

    async def get_session_id(self, project_id: str) -> Optional[str]:
        """Get stored session ID for project"""
        return self._session_store.get(project_id)

    async def set_session_id(self, project_id: str, session_id: str) -> None:
        """Store session ID for project in memory"""
        self._session_store[project_id] = session_id

    async def get_rollout_path(self, project_id: str) -> Optional[str]:
        return None

    def _parse_stdout_events(
        self,
        stdout_text: str,
        project_path: str,
        session_id: Optional[str],
    ) -> Tuple[List[Message], bool, bool, Optional[str]]:
        """Parse codex JSONL stdout into message objects and turn state."""
        messages: List[Message] = []
        saw_turn_completed = False
        saw_turn_failed = False
        failure_text: Optional[str] = None

        for raw_line in stdout_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")

            if event_type == "turn.completed":
                saw_turn_completed = True
                continue

            if event_type in {"turn.failed", "error"}:
                saw_turn_failed = True
                failure_text = self._extract_error_text(
                    event.get("error") if event_type == "turn.failed" else event
                )
                continue

            if event_type != "item.completed":
                continue

            item = event.get("item", {})
            item_type = item.get("type", "")

            if item_type == "agent_message":
                text = item.get("text", "")
                if text.strip():
                    messages.append(
                        Message(
                            id=str(uuid.uuid4()),
                            project_id=project_path,
                            role="assistant",
                            message_type="chat",
                            content=text.strip(),
                            metadata_json={"cli_type": self.cli_type.value},
                            session_id=session_id,
                            created_at=datetime.utcnow(),
                        )
                    )
                continue

            if item_type == "tool_call":
                tool_name = item.get("name", "unknown")
                summary = self._create_tool_summary(
                    tool_name, {"args": item.get("arguments", "")}
                )
                messages.append(
                    Message(
                        id=str(uuid.uuid4()),
                        project_id=project_path,
                        role="assistant",
                        message_type="tool_use",
                        content=summary,
                        metadata_json={
                            "cli_type": self.cli_type.value,
                            "tool_name": tool_name,
                        },
                        session_id=session_id,
                        created_at=datetime.utcnow(),
                    )
                )

        return messages, saw_turn_completed, saw_turn_failed, failure_text

    def _extract_error_text(self, payload: Any) -> Optional[str]:
        """Extract the most useful error string from a codex JSON event."""
        if payload is None:
            return None
        if isinstance(payload, str):
            text = payload.strip()
            if not text:
                return None
            try:
                return self._extract_error_text(json.loads(text))
            except json.JSONDecodeError:
                return text
        if isinstance(payload, dict):
            for key in ("message", "error", "details"):
                value = payload.get(key)
                extracted = self._extract_error_text(value)
                if extracted:
                    return extracted
            try:
                return json.dumps(payload)
            except Exception:
                return str(payload)
        return str(payload)

    def _stderr_is_benign(self, stderr_text: str) -> bool:
        """Return true when stderr contains only known codex exec noise."""
        lines = [line.strip() for line in stderr_text.splitlines() if line.strip()]
        if not lines:
            return True

        for line in lines:
            if line == self._BENIGN_STDERR_LINES[0]:
                continue
            if (
                self._BENIGN_STDERR_LINES[1] in line
                and line.endswith(" not found")
            ):
                continue
            return False

        return True

    async def set_rollout_path(self, project_id: str, rollout_path: str) -> None:
        pass


__all__ = ["CodexCLI"]
