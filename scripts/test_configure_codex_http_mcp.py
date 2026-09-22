from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == "nt", "Codex HTTP helper is Windows-only")
class ConfigureCodexHttpMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="symbraid-helper-test-"))
        self.bin = self.root / "bin"
        self.codex = self.root / "codex"
        self.state = self.root / "state"
        self.bin.mkdir()
        self.codex.mkdir()
        self.fake = self.bin / "symbraid.cmd"
        self.fake.write_text(
            "@echo off\r\n"
            'if "%1"=="--version" echo symbraid 0.3.0\r\n'
            'if "%1"=="mcp" if "%2"=="--help" echo streamable-http --allow-all-projects --auth-token-env\r\n'
            "exit /b 0\r\n",
            encoding="utf-8",
        )
        self.config = self.codex / "config.toml"
        self.config.write_text(
            '[plugins."symbraid-search@symbraid"]\n'
            "enabled = true\n\n"
            '[plugins."hybrid-code-search@semantic-code-index-kit"]\n'
            "enabled = true\n",
            encoding="utf-8",
        )
        self.script = Path(__file__).with_name("configure-codex-http-mcp.ps1")
        self.powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not self.powershell:
            self.skipTest("PowerShell is not available")
        self.environment = os.environ.copy()
        self.environment["PATH"] = str(self.bin) + os.pathsep + self.environment.get("PATH", "")
        self.environment["SYMBRAID_CODEX_MCP_TOKEN"] = "test-token-not-secret"

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def run_helper(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                self.powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.script),
                *arguments,
            ],
            env=self.environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def base_arguments(self) -> tuple[str, ...]:
        return (
            "-CodexHome",
            str(self.codex),
            "-StateDirectory",
            str(self.state),
            "-NoStart",
        )

    def test_configure_is_idempotent_and_disables_all_symbraid_plugins(self) -> None:
        first = self.run_helper("-Action", "Configure", *self.base_arguments())
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        first_text = self.config.read_text(encoding="utf-8")
        second = self.run_helper("-Action", "Configure", *self.base_arguments())
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(first_text, self.config.read_text(encoding="utf-8"))
        self.assertIn("symbraid-search@symbraid", first_text)
        self.assertIn("hybrid-code-search@semantic-code-index-kit", first_text)
        self.assertEqual(first_text.count("enabled = false"), 2)
        self.assertIn('bearer_token_env_var = "SYMBRAID_CODEX_MCP_TOKEN"', first_text)
        state = json.loads((self.state / "codex-http-mcp.json").read_text(encoding="utf-8"))
        self.assertNotIn("test-token-not-secret", json.dumps(state))
        self.assertNotIn("test-token-not-secret", first.stdout + first.stderr)

    def test_configure_without_plugins_still_adds_standalone_server(self) -> None:
        self.config.write_text("# user config only\n", encoding="utf-8")
        result = self.run_helper("-Action", "Configure", *self.base_arguments())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = self.config.read_text(encoding="utf-8")
        self.assertIn('[mcp_servers."io.github.wcotito/symbraid"]', text)
        self.assertNotIn('[plugins.', text)
    def test_remove_only_removes_managed_block_and_keeps_external_token(self) -> None:
        configured = self.run_helper("-Action", "Configure", *self.base_arguments())
        self.assertEqual(configured.returncode, 0, configured.stdout + configured.stderr)
        removed = self.run_helper(
            "-Action",
            "Remove",
            "-CodexHome",
            str(self.codex),
            "-StateDirectory",
            str(self.state),
        )
        self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
        remaining = self.config.read_text(encoding="utf-8")
        self.assertIn('[plugins."symbraid-search@symbraid"]', remaining)
        self.assertNotIn("BEGIN SYMBRAID", remaining)
        self.assertEqual(self.environment["SYMBRAID_CODEX_MCP_TOKEN"], "test-token-not-secret")
        self.assertFalse((self.state / "codex-http-mcp.json").exists())

    def test_what_if_does_not_write_config_or_state(self) -> None:
        original = self.config.read_text(encoding="utf-8")
        result = self.run_helper("-Action", "Configure", "-WhatIf", *self.base_arguments())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(original, self.config.read_text(encoding="utf-8"))
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
