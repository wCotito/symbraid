from __future__ import annotations

import io
import json
import unittest
from unittest import mock

from symbraid import cli, mcp_server
from symbraid.redaction import REDACTED, redact_for_output, redact_text


class RedactionTests(unittest.TestCase):
    def test_recursive_redaction_preserves_public_shape_without_mutation(self):
        source = {
            "status": "ok",
            "api_key_configured": True,
            "nested": [
                {
                    "API-Key": "test-first",
                    "password": "test-second",
                    "accessToken": "test-camel",
                    "authorization_header": "test-header",
                },
                {"message": "ordinary diagnostic"},
            ],
            "query": "ordinary semantic search",
        }

        redacted = redact_for_output(source)

        self.assertEqual(redacted["nested"][0]["API-Key"], REDACTED)
        self.assertEqual(redacted["nested"][0]["password"], REDACTED)
        self.assertEqual(redacted["nested"][0]["accessToken"], REDACTED)
        self.assertEqual(redacted["nested"][0]["authorization_header"], REDACTED)
        self.assertTrue(redacted["api_key_configured"])
        self.assertEqual(redacted["query"], source["query"])
        self.assertEqual(source["nested"][0]["API-Key"], "test-first")

    def test_success_output_preserves_search_text_query_and_watcher_path(self):
        source = {
            "query": "find token = parse_header(value)",
            "results": [{"text": "token = parse_header(value)"}],
            "event": {"path": "src/token=parser.py"},
        }
        self.assertEqual(redact_for_output(source), source)

    def test_text_redaction_covers_headers_url_and_labeled_forms(self):
        values = (
            "https://user:test-url@example.test",
            "Authorization: Bearer test-bearer",
            "Authorization: Basic test-basic",
            "{'Authorization': 'Basic test-repr'}",
            "{'X-Api-Key': 'test-key'}",
            "access_token=test-query; password='test-quoted'",
        )
        redacted = "\n".join(redact_text(value) for value in values)
        for secret in (
            "test-url",
            "test-bearer",
            "test-basic",
            "test-repr",
            "test-key",
            "test-query",
            "test-quoted",
        ):
            self.assertNotIn(secret, redacted)

    def test_emit_filters_nested_watcher_payload(self):
        output = io.StringIO()
        with mock.patch("symbraid.redaction.sys.stdout", output):
            cli.emit({"event": "reconcile", "result": {"credentials": ["test-sentinel"]}})
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["result"]["credentials"], REDACTED)
        self.assertNotIn("test-sentinel", output.getvalue())

    def test_cli_error_is_redacted_and_keeps_contract(self):
        for message in (
            "api" + "_key=" + "test-sentinel",
            "Authorization: Basic test-sentinel",
            "{'Authorization': 'Basic test-sentinel'}",
        ):
            with self.subTest(message=message):
                stderr = io.StringIO()
                with mock.patch("symbraid.cli.build_parser") as parser, mock.patch(
                    "symbraid.cli.run", side_effect=RuntimeError(message)
                ), mock.patch("symbraid.cli.sys.stderr", stderr):
                    parser.return_value.parse_args.return_value = mock.Mock(command="paths")
                    result = cli.main()
                payload = json.loads(stderr.getvalue())
                self.assertEqual(result, 1)
                self.assertEqual(payload["status"], "error")
                self.assertNotIn("test-sentinel", payload["error"])

    def test_standalone_mcp_error_uses_same_boundary(self):
        stderr = io.StringIO()
        with mock.patch("symbraid.mcp_server.build_parser") as parser, mock.patch(
            "symbraid.mcp_server.run_mcp",
            side_effect=RuntimeError("Authorization: Bearer test-sentinel"),
        ), mock.patch("symbraid.mcp_server.sys.stderr", stderr):
            parser.return_value.parse_args.return_value = mock.Mock(
                transport="stdio", project=None, host="127.0.0.1", port=8765, token_env=None
            )
            result = mcp_server.main()
        self.assertEqual(result, 1)
        self.assertNotIn("test-sentinel", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
