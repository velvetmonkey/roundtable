"""Check that the CLI adapters pass their instructions to the installed CLIs."""

import unittest
from unittest.mock import patch

from claudable_helper.cli.adapters.antigravity_cli import AntigravityCLI
from claudable_helper.cli.adapters.grok_cli import GrokCLI


class _Output:
    def __aiter__(self):
        self._lines = iter([b"OK\n"])
        return self

    async def __anext__(self):
        try:
            return next(self._lines)
        except StopIteration:
            raise StopAsyncIteration


class _Process:
    returncode = 0
    stdout = _Output()
    stderr = None
    stdin = None

    async def wait(self):
        return 0


class PromptArgvTests(unittest.IsolatedAsyncioTestCase):
    async def test_grok_prompt_and_supported_flags(self):
        instruction = "Reply with the single word OK."
        calls = []

        async def fake_exec(*args, **kwargs):
            calls.append((args, kwargs))
            return _Process()

        with patch("asyncio.create_subprocess_exec", fake_exec):
            messages = [message async for message in GrokCLI().execute_with_streaming(instruction, ".")]

        self.assertEqual([message.content for message in messages], ["OK"])
        argv, _ = calls[0]
        self.assertEqual(argv[0], "grok")
        self.assertNotIn("--prompt", argv)
        self.assertNotIn("--directory", argv)
        self.assertEqual(argv[argv.index("--single") + 1], instruction)
        self.assertIn("--cwd", argv)

    async def test_antigravity_print_prompt_is_instruction(self):
        instruction = "Reply with the single word OK."
        calls = []

        async def fake_exec(*args, **kwargs):
            calls.append((args, kwargs))
            return _Process()

        with patch("asyncio.create_subprocess_exec", fake_exec):
            messages = [message async for message in AntigravityCLI().execute_with_streaming(instruction, ".")]

        self.assertEqual([message.content for message in messages], ["OK"])
        argv, kwargs = calls[0]
        self.assertEqual(argv[0], "agy")
        self.assertNotIn("", argv)
        self.assertEqual(argv[argv.index("-p") + 1], instruction)
        self.assertNotIn("stdin", kwargs)
