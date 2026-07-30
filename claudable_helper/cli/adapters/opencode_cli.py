"""OpenCode CLI adapter for Roundtable AI MCP Server.

Invocation notes, verified against opencode 1.18.4 on 2026-07-30:

  * The non-interactive entry point is `opencode run [message..]`. Bare
    `opencode <text>` treats the text as the PROJECT positional and starts the
    TUI, which under a piped stdout just prints the usage banner and exits 0.
  * There is no `--path` flag. The working directory is `--dir`, and `cwd` on
    the spawn is what actually matters.
  * `--format json` emits one JSON event per line. The assistant's answer is
    carried on `type == "text"` events; `type == "step_finish"` carries the
    per-run token counts and USD cost, which is the only per-dispatch cost
    meter any of our seats expose.
"""

import asyncio
import json
import os
import pwd
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from claudable_helper.cli.base import BaseCLI
from claudable_helper.models.messages import Message, MessageType


class OpenCodeCLI(BaseCLI):
    def __init__(self):
        super().__init__(cli_type="opencode")
        self.session_mapping: Dict[str, str] = {}
        self.last_usage: Dict[str, Any] = {}

    def _get_env(self) -> dict:
        # Engine sessions run with an ISOLATED HOME (tmp path); opencode's
        # provider credentials live in the REAL home under
        # ~/.local/share/opencode/auth.json. Same fix as codex/gemini/grok
        # (2d060c5) and antigravity (8f64588).
        #
        # PATH also needs widening: the official installer drops the binary in
        # ~/.opencode/bin, which is not on a non-login shell's PATH, so both
        # the availability probe and the spawn used to fail with "not found".
        real_home = pwd.getpwuid(os.getuid()).pw_dir
        env = os.environ.copy()
        env["HOME"] = real_home
        extra = [f"{real_home}/.local/bin", f"{real_home}/.opencode/bin"]
        path = env.get("PATH", "")
        env["PATH"] = ":".join([p for p in extra if p not in path.split(":")] + [path])
        return env

    async def check_availability(self) -> Dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_shell(
                "opencode --version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._get_env(),
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                version = stdout.decode().strip().splitlines()[-1] if stdout else "unknown"
                return {"available": True, "status": f"✅ OpenCode CLI Available ({version})", "version": version}
            err = (stderr.decode().strip() or stdout.decode().strip())[:200]
            return {"available": False, "status": f"❌ OpenCode CLI failed: {err}"}
        except Exception as e:
            return {"available": False, "status": f"❌ OpenCode CLI error: {str(e)}"}

    async def execute_with_streaming(self, instruction: str, project_path: str, session_id: Optional[str] = None, model: Optional[str] = None, images: Optional[List[Dict[str, Any]]] = None, is_initial_prompt: bool = False) -> AsyncIterator[Message]:
        project_path = str(Path(project_path).absolute())
        cmd = ["opencode", "run", "--format", "json", "--dir", project_path]
        if model:
            cmd += ["--model", model]
        if session_id and not is_initial_prompt:
            cmd += ["--session", session_id]
        cmd.append(instruction)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_path,
                env=self._get_env(),
            )
            emitted = False
            if proc.stdout:
                async for line in proc.stdout:
                    line_text = line.decode(errors="replace").strip()
                    if not line_text:
                        continue
                    try:
                        event = json.loads(line_text)
                    except json.JSONDecodeError:
                        # Not a JSON event line; pass it through rather than
                        # dropping output we do not recognise.
                        yield Message(project_id=project_path, role="assistant", message_type=MessageType.ASSISTANT, content=line_text, session_id=session_id or "default", created_at=datetime.utcnow())
                        emitted = True
                        continue

                    kind = event.get("type")
                    part = event.get("part") or {}
                    sid = event.get("sessionID") or session_id or "default"
                    if sid and sid != session_id:
                        self.session_mapping[project_path] = sid

                    if kind == "text":
                        text = part.get("text", "")
                        if text:
                            yield Message(project_id=project_path, role="assistant", message_type=MessageType.ASSISTANT, content=text, session_id=sid, created_at=datetime.utcnow())
                            emitted = True
                    elif kind == "step_finish":
                        self.last_usage = {
                            "tokens": part.get("tokens", {}),
                            "cost": part.get("cost"),
                            "sessionID": sid,
                            "model": model,
                        }

            await proc.wait()
            stderr_text = ""
            if proc.stderr:
                stderr_text = (await proc.stderr.read()).decode(errors="replace").strip()

            if proc.returncode != 0:
                yield Message(project_id=project_path, role="assistant", message_type=MessageType.ERROR, content=f"opencode exited {proc.returncode}: {stderr_text[:500]}", session_id=session_id or "default", created_at=datetime.utcnow())
            elif not emitted:
                # Exit 0 with no assistant text is the old silent-failure shape
                # (usage banner on stdout). Surface it rather than returning
                # an empty success.
                yield Message(project_id=project_path, role="assistant", message_type=MessageType.ERROR, content=f"opencode produced no assistant output (exit 0). stderr: {stderr_text[:500]}", session_id=session_id or "default", created_at=datetime.utcnow())
        except Exception as e:
            yield Message(project_id=project_path, role="assistant", message_type=MessageType.ERROR, content=f"Error: {str(e)}", session_id=session_id or "default", created_at=datetime.utcnow())

    async def get_session_id(self, project_id: str) -> Optional[str]:
        """Get current session ID for project"""
        return self.session_mapping.get(project_id)

    async def set_session_id(self, project_id: str, session_id: str) -> None:
        """Set session ID for project in memory"""
        self.session_mapping[project_id] = session_id
