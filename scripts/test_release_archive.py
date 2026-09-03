"""Self-test the release archive scanner without embedding real-looking secrets."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

try:
    from scan_release_archive import check_member, find_secret_kinds, scan_archive
except ModuleNotFoundError:  # pragma: no cover - package-style invocation
    from scripts.scan_release_archive import check_member, find_secret_kinds, scan_archive


class ReleaseArchiveScannerTests(unittest.TestCase):
    def test_common_token_shapes_are_detected(self) -> None:
        bearer = "Authorization: " + "Bearer " + "A1b2C3d4E5f6G7h8I9j0K1l2"
        jwt = ".".join(
            (
                "eyJ" + "A" * 12,
                "e30" + "B" * 12,
                "sig" + "C" * 12,
            )
        )
        npm = "npm" + "_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
        gitlab = "glpat" + "-" + "A1b2C3d4E5f6G7h8I9j0K1l2"
        private_key = (
            "-----BEGIN " + "RSA PRIVATE KEY-----\n"
            + "base64-payload\n"
            + "-----END RSA PRIVATE KEY-----"
        )
        text = "\n".join((bearer, jwt, npm, gitlab, private_key))
        findings = find_secret_kinds(text)
        self.assertIn("bearer token", findings)
        self.assertIn("JWT", findings)
        self.assertIn("npm token", findings)
        self.assertIn("GitLab token", findings)
        self.assertIn("private-key PEM", findings)

    def test_credential_assignments_are_detected_without_echoing_values(self) -> None:
        values = (
            "Qd7x-9kLm-2pQr-8sT",
            "xY7z-1aBc-3dEf-5gHi",
            "S3cure-Pass-7xY",
        )
        text = "\n".join(
            (
                "qdrant" + "_api_key = " + repr(values[0]),
                "api" + "-key: " + repr(values[1]),
                "pass" + "word = " + repr(values[2]),
            )
        )
        violations: list[str] = []
        check_member("config.txt", text.encode("utf-8"), violations)
        self.assertEqual(len(violations), 1)
        self.assertIn("credential assignment", violations[0])
        for value in values:
            self.assertNotIn(value, violations[0])

    def test_documentation_references_are_not_findings(self) -> None:
        text = "\n".join(
            (
                "Authorization: " + "Bearer " + "$" + "{SYMBRAID_MCP_TOKEN}",
                "api" + "_key: env:SYMBRAID_API_KEY",
                "pass" + "word: <password>",
                "qdrant" + "_api_key = QDRANT_API_KEY",
                "npm" + "_token = " + "$" + "{NPM_TOKEN}",
                "The token is supplied by the environment.",
            )
        )
        self.assertEqual(find_secret_kinds(text), [])

    def test_archive_dispatch_scans_benign_zip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "release.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "docs/example.md",
                    "Use Authorization: " + "Bearer <token>.\n"
                    "Configure api_key with env:SYMBRAID_API_KEY.\n",
                )
            violations: list[str] = []
            scan_archive(archive_path, violations)
            self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
