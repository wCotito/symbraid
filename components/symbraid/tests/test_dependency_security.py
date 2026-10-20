"""Exercise the dependency security boundaries used by the MCP server."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import unittest
from unittest import mock

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from symbraid.mcp_server import _HttpSecurity, build_server


class DependencySecurityTests(unittest.TestCase):
    def test_mutated_public_pem_cannot_verify_hmac_forgery(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        claims = {"sub": "security-regression"}
        legitimate = jwt.encode(claims, key, algorithm="RS256")
        self.assertEqual(jwt.decode(legitimate, pem, algorithms=["RS256"]), claims)

        def encoded(value):
            return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")

        for mutated in (
            pem.replace(b"\n", b"\r"),
            pem.replace(b"-----END", b"\t-----END"),
        ):
            with self.subTest(pem=mutated):
                # Both variants still represent a valid asymmetric public key.
                serialization.load_pem_public_key(mutated)
                signing_input = encoded({"alg": "HS256"}) + b"." + encoded(claims)
                signature = hmac.new(mutated, signing_input, hashlib.sha256).digest()
                forged = signing_input + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")
                with self.assertRaises(jwt.InvalidKeyError):
                    jwt.decode(forged.decode(), mutated, algorithms=["RS256", "HS256"])

    def test_http_session_limit_and_delete_reclaim_capacity(self):
        # Exercise the real product app with small SDK limits, without adding
        # public configuration or changing production session semantics.
        with mock.patch("symbraid.mcp_server.FastMCP", side_effect=lambda *args, **kwargs: FastMCP(
            *args, **kwargs, max_sessions=2, max_request_body_size=1024
        )):
            server = build_server(port=8765)
        app = _HttpSecurity(server.streamable_http_app(), "fixture-token", 8765)
        headers = {
            "Authorization": "Bearer fixture-token",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        initialize = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "security-regression", "version": "1"},
            },
        }
        with TestClient(app, base_url="http://127.0.0.1:8765") as client:
            first = client.post("/mcp", json=initialize, headers=headers)
            self.assertEqual(first.status_code, 200)
            session_id = first.headers["mcp-session-id"]
            session_headers = {**headers, "Mcp-Session-Id": session_id}
            tools_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
            self.assertEqual(client.post(
                "/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers=session_headers,
            ).status_code, 202)
            tools = client.post("/mcp", json=tools_request, headers=session_headers)
            self.assertEqual(tools.status_code, 200)
            self.assertIn("semantic_search", tools.text)

            # A valid session ID never substitutes for the bearer or origin checks.
            for changes, expected in (
                ({"Authorization": "Bearer wrong"}, 401),
                ({"Origin": "https://attacker.invalid"}, 403),
            ):
                with self.subTest(headers=changes):
                    self.assertEqual(client.post(
                        "/mcp", json=tools_request, headers={**session_headers, **changes}
                    ).status_code, expected)
            self.assertEqual(client.post("/mcp", json=initialize, headers=headers).status_code, 200)
            self.assertEqual(client.post("/mcp", json=initialize, headers=headers).status_code, 503)
            self.assertEqual(client.delete("/mcp", headers=session_headers).status_code, 200)
            self.assertEqual(client.post("/mcp", json=tools_request, headers=session_headers).status_code, 404)
            self.assertEqual(client.post("/mcp", json=initialize, headers=headers).status_code, 200)
            self.assertEqual(client.post(
                "/mcp", content=b" " * 1025,
                headers={**headers, "Content-Type": "application/json"},
            ).status_code, 413)


if __name__ == "__main__":
    unittest.main()
