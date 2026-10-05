"""Grok CLI adapter for Roundtable AI MCP Server."""

import asyncio
import os
import pwd
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from claudable_helper.cli.base import BaseCLI
from claudable_helper.core.terminal_ui import ui
from claudable_helper.models.messages import Message, MessageType


class GrokCLI(BaseCLI):
    """Adapter for Grok CLI."""

    def __init__(self):
        super().__init__(cli_type="grok")
        self.session_mapping: Dict[str, str] = {}

    async def check_availability(self) -> Dict[str, Any]:
        """Check if Grok CLI is available."""
        try:
            proc = await asyncio.create_subprocess_shell(
                "grok --help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._get_env(),
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                return {"available": True, "status": "✅ Grok CLI Available"}
            else:
                return {"available": False, "status": f"❌ Grok CLI failed: {stderr.decode()}"}
        except Exception as e:
            return {"available": False, "status": f"❌ Grok CLI error: {str(e)}"}

    def _get_env(self) -> dict:
        real_home = pwd.getpwuid(os.getuid()).pw_dir
        env = os.environ.copy()
        env["HOME"] = real_home
        return env

    async def execute_with_streaming(
        self,
        instruction: str,
        project_path: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        is_initial_prompt: bool = False,
    ) -> AsyncIterator[Message]:
        """Execute Grok CLI with streaming output."""
        project_path = str(Path(project_path).absolute())
        if not instruction or not instruction.strip():
            yield Message(
                project_id=project_path,
                role="assistant",
                message_type=MessageType.ERROR,
                content="Instruction must not be empty or whitespace-only.",
                session_id=session_id or "default",
                created_at=datetime.utcnow(),
            )
            return
        # Clap treats a leading hyphen in a separate value as another option.
        prompt_args = [f"--single={instruction}"] if instruction.startswith("-") else ["--single", instruction]
        cmd = ["grok", *prompt_args, "--cwd", project_path]
        if model:
            cmd += ["--model", model]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_path,
                env=self._get_env(),
            )

            has_text = False
            if proc.stdout:
                async for line in proc.stdout:
                    line_text = line.decode().strip()
                    if line_text:
                        has_text = True
                        yield Message(
                            project_id=project_path,
                            role="assistant",
                            message_type=MessageType.ASSISTANT,
                            content=line_text,
                            session_id=session_id or "default",
                            created_at=datetime.utcnow(),
                        )

            await proc.wait()

            if proc.returncode != 0:
                stderr = await proc.stderr.read() if proc.stderr else b""
                yield Message(
                    project_id=project_path,
                    role="assistant",
                    message_type=MessageType.ERROR,
                    content=f"Grok CLI exited {proc.returncode}: {stderr.decode().strip()}",
                    session_id=session_id or "default",
                    created_at=datetime.utcnow(),
                )
            elif not has_text:
                yield Message(
                    project_id=project_path,
                    role="assistant",
                    message_type=MessageType.ERROR,
                    content="Grok CLI exited 0 with no text.",
                    session_id=session_id or "default",
                    created_at=datetime.utcnow(),
                )

        except Exception as e:
            yield Message(
                project_id=project_path,
                role="assistant",
                message_type=MessageType.ERROR,
                content=f"Execution error: {str(e)}",
                session_id=session_id or "default",
                created_at=datetime.utcnow(),
            )

    async def get_session_id(self, project_id: str) -> Optional[str]:
        """Get current session ID for project"""
        return self.session_mapping.get(project_id)

    async def set_session_id(self, project_id: str, session_id: str) -> None:
        """Set session ID for project in memory"""
        self.session_mapping[project_id] = session_id
