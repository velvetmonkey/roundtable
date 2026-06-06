"""Antigravity CLI (agy) adapter for Roundtable AI MCP Server.

Rewritten 2026-06-06 against the real Antigravity CLI (binary `agy`, v1.0.6) —
the previous stub invoked a nonexistent `antigravity` binary. Google replaces
Gemini CLI with Antigravity on 2026-06-18; this adapter is the gemini seat's
successor. Prompt goes via STDIN (`agy -p ""` non-interactive mode) so large
council briefs never hit argv limits. Default model is the max-thinking pro
tier; agy model ids are display strings (see `agy models`), e.g.
"Gemini 3.1 Pro (High)", "Gemini 3.5 Flash (High)", "Claude Opus 4.6 (Thinking)".
"""

import asyncio
import os
import pwd
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from claudable_helper.cli.base import BaseCLI
from claudable_helper.models.messages import Message, MessageType

# Max-thinking pro tier — "use agy in max thinking mode going forward" (operator,
# 2026-06-06). agy's own default is Gemini 3.5 Flash (Medium), too light for
# council/verdict work.
DEFAULT_MODEL = "Gemini 3.1 Pro (High)"
# agy's --print-timeout defaults to 5m; max-thinking runs can exceed it.
PRINT_TIMEOUT = "10m"


class AntigravityCLI(BaseCLI):
    def __init__(self):
        super().__init__(cli_type="antigravity")
        self._session_store: Dict[str, str] = {}  # in-memory, per gemini adapter pattern

    def _get_env(self) -> dict:
        # Engine sessions run with an ISOLATED HOME (tmp path); agy's Google
        # credentials live in the REAL home. Same fix as codex/gemini/grok
        # (2d060c5) — without it agy demands OAuth and times out (field-tested
        # in Monkey's council 2026-06-06 21:59).
        real_home = pwd.getpwuid(os.getuid()).pw_dir
        env = os.environ.copy()
        env["HOME"] = real_home
        return env

    async def get_session_id(self, project_id: str) -> Optional[str]:
        return self._session_store.get(project_id)

    async def set_session_id(self, project_id: str, session_id: str) -> None:
        self._session_store[project_id] = session_id

    async def check_availability(self) -> Dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_shell(
                "agy --version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._get_env(),
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                version = stdout.decode().strip()
                return {
                    "available": True,
                    "status": f"✅ **Antigravity CLI Available** (agy {version})\n📋 **Default Model:** {DEFAULT_MODEL}",
                }
            return {"available": False, "status": "❌ Antigravity CLI (agy) failed — run `agy` once to sign in"}
        except Exception as e:
            return {"available": False, "status": f"❌ Antigravity CLI error: {str(e)}"}

    async def execute_with_streaming(
        self,
        instruction: str,
        project_path: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        is_initial_prompt: bool = False,
    ) -> AsyncIterator[Message]:
        project_path = str(Path(project_path).absolute())
        cmd = [
            "agy",
            "-p", "",
            "--print-timeout", PRINT_TIMEOUT,
            "--model", model or DEFAULT_MODEL,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_path,
                env=self._get_env(),
            )
            # Prompt via stdin — argv-safe for multi-hundred-KB council briefs.
            if proc.stdin:
                proc.stdin.write(instruction.encode())
                await proc.stdin.drain()
                proc.stdin.close()
            if proc.stdout:
                async for line in proc.stdout:
                    line_text = line.decode().strip()
                    if line_text:
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
                stderr_tail = b""
                if proc.stderr:
                    stderr_tail = await proc.stderr.read()
                yield Message(
                    project_id=project_path,
                    role="assistant",
                    message_type=MessageType.ERROR,
                    content=f"agy exited {proc.returncode}: {stderr_tail.decode()[-500:]}",
                    session_id=session_id or "default",
                    created_at=datetime.utcnow(),
                )
        except Exception as e:
            yield Message(
                project_id=project_path,
                role="assistant",
                message_type=MessageType.ERROR,
                content=f"Error: {str(e)}",
                session_id=session_id or "default",
                created_at=datetime.utcnow(),
            )
