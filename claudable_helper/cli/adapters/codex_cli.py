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
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from claudable_helper.core.terminal_ui import ui
from claudable_helper.models.messages import Message

from ..base import BaseCLI, CLIType

logger = logging.getLogger(__name__)


class CodexCLI(BaseCLI):
    """Codex CLI implementation using `codex exec --json`"""

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
                "default_models": ["gpt-5"],
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
        cli_model = self._get_cli_model_name(model) or "gpt-5"
        ui.info(f"Starting Codex execution with model: {cli_model}", "Codex")

        workdir_abs = os.path.abspath(project_path)

        # Build command — subcommand-specific flags must come after `exec`
        cmd = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--cd", workdir_abs,
            "--json",
            "--dangerously-bypass-approvals-and-sandbox",
            "-m", cli_model,
        ]

        # Attach images if provided
        if images:
            for image_data in images:
                path = image_data.get("path") if isinstance(image_data, dict) else None
                if path:
                    cmd.extend(["-i", str(path)])

        # Prompt goes last
        cmd.append(instruction)

        logger.info(f"[Codex] Running: {' '.join(cmd[:6])} ...")

        try:
            # stdin=DEVNULL is critical — without it codex inherits the MCP
            # server's stdin (the JSON-RPC transport) and hangs reading it.
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir_abs,
            )

            # Wait for the process to complete and collect all output.
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(),
                timeout=300,  # 5 minute hard timeout
            )

            if stderr_data:
                logger.debug(f"[Codex] stderr: {stderr_data.decode()[:500]}")

            if process.returncode != 0:
                error_text = (
                    stderr_data.decode().strip()
                    if stderr_data
                    else f"exit code {process.returncode}"
                )
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

            # Parse JSONL events from stdout
            for line in stdout_data.decode().splitlines():
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                if event_type == "item.completed":
                    item = event.get("item", {})
                    item_type = item.get("type", "")

                    if item_type == "agent_message":
                        text = item.get("text", "")
                        if text.strip():
                            yield Message(
                                id=str(uuid.uuid4()),
                                project_id=project_path,
                                role="assistant",
                                message_type="chat",
                                content=text.strip(),
                                metadata_json={"cli_type": self.cli_type.value},
                                session_id=session_id,
                                created_at=datetime.utcnow(),
                            )

                    elif item_type == "tool_call":
                        tool_name = item.get("name", "unknown")
                        summary = self._create_tool_summary(
                            tool_name, {"args": item.get("arguments", "")}
                        )
                        yield Message(
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

    async def set_rollout_path(self, project_id: str, rollout_path: str) -> None:
        pass


__all__ = ["CodexCLI"]
