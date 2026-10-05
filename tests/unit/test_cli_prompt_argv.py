"""Check the CLI process boundary and its installed option names."""

import asyncio
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from claudable_helper.cli.adapters.antigravity_cli import AntigravityCLI, DEFAULT_MODEL, PRINT_TIMEOUT
from claudable_helper.cli.adapters.grok_cli import GrokCLI
from claudable_helper.models.messages import MessageType


class _Output:
    def __init__(self, lines):
        self.lines = iter(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.lines)
        except StopIteration:
            raise StopAsyncIteration


class _Process:
    def __init__(self, lines=(b"OK\n",)):
        self.returncode = 0
        self.stdout = _Output(lines)
        self.stderr = None
        self.stdin = None

    async def wait(self):
        return self.returncode


class PromptArgvTests(unittest.IsolatedAsyncioTestCase):
    async def _invoke(self, adapter, instruction, lines=(b"OK\n",), model=None):
        calls = []

        async def fake_exec(*args, **kwargs):
            calls.append((list(args), kwargs))
            return _Process(lines)

        with patch("asyncio.create_subprocess_exec", fake_exec):
            messages = [m async for m in adapter.execute_with_streaming(instruction, ".", model=model)]
        return messages, calls

    async def test_grok_full_argv_cwd_and_no_stdin(self):
        instruction = "Reply with the single word OK."
        messages, calls = await self._invoke(GrokCLI(), instruction, model="chosen-model")
        self.assertEqual([(m.message_type, m.content) for m in messages], [(MessageType.ASSISTANT, "OK")])
        self.assertEqual(len(calls), 1)
        argv, kwargs = calls[0]
        project_path = str(Path(".").absolute())
        self.assertEqual(argv, ["grok", "--single", instruction, "--cwd", project_path, "--model", "chosen-model"])
        self.assertEqual(kwargs["cwd"], project_path)
        self.assertEqual(kwargs["stdout"], asyncio.subprocess.PIPE)
        self.assertEqual(kwargs["stderr"], asyncio.subprocess.PIPE)
        self.assertNotIn("stdin", kwargs)

    async def test_antigravity_full_argv_cwd_and_no_stdin(self):
        instruction = "Reply with the single word OK."
        messages, calls = await self._invoke(AntigravityCLI(), instruction)
        self.assertEqual([(m.message_type, m.content) for m in messages], [(MessageType.ASSISTANT, "OK")])
        self.assertEqual(len(calls), 1)
        argv, kwargs = calls[0]
        project_path = str(Path(".").absolute())
        self.assertEqual(argv, ["agy", "-p", instruction, "--print-timeout", PRINT_TIMEOUT, "--model", DEFAULT_MODEL])
        self.assertEqual(kwargs["cwd"], project_path)
        self.assertEqual(kwargs["stdout"], asyncio.subprocess.PIPE)
        self.assertEqual(kwargs["stderr"], asyncio.subprocess.PIPE)
        self.assertNotIn("stdin", kwargs)

    async def test_grok_leading_hyphen_is_prompt_value(self):
        instruction = "-start Reply with the single word OK."
        _, calls = await self._invoke(GrokCLI(), instruction)
        self.assertEqual(calls[0][0], ["grok", f"--single={instruction}", "--cwd", str(Path(".").absolute())])

    async def test_empty_instructions_start_no_process(self):
        for adapter in (GrokCLI(), AntigravityCLI()):
            for instruction in ("", " \t\n"):
                with self.subTest(adapter=type(adapter).__name__, instruction=repr(instruction)):
                    messages, calls = await self._invoke(adapter, instruction)
                    self.assertEqual(calls, [])
                    self.assertEqual([(m.message_type, m.content) for m in messages],
                                     [(MessageType.ERROR, "Instruction must not be empty or whitespace-only.")])

    async def test_exit_zero_without_text_is_error(self):
        for adapter in (GrokCLI(), AntigravityCLI()):
            with self.subTest(adapter=type(adapter).__name__):
                messages, calls = await self._invoke(adapter, "Reply with the single word OK.", lines=(b" \n",))
                self.assertEqual(len(calls), 1)
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0].message_type, MessageType.ERROR)
                self.assertIn("exited 0 with no text", messages[0].content)

    def test_installed_help_lists_adapter_options(self):
        cases = (("grok", ("--single", "--cwd", "--model")),
                 ("agy", ("-p", "--print-timeout", "--model")))
        for binary, options in cases:
            with self.subTest(binary=binary):
                if not shutil.which(binary):
                    print(f"SKIP {binary} --help: binary absent")
                    continue
                result = subprocess.run([binary, "--help"], capture_output=True, text=True, check=True)
                help_text = result.stdout + result.stderr
                for option in options:
                    self.assertRegex(help_text, rf"(?<!\w){re.escape(option)}(?=\s|,|$)")
