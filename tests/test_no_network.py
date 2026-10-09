"""Regression test proving request handling performs no outbound networking."""

from __future__ import annotations

import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from soil_api.app import app


REQUEST_PATH = Path(__file__).resolve().parents[1] / "docs" / "poc" / "samples" / "request.json"


class NoNetworkRegressionTest(unittest.TestCase):
    """Requests must be served entirely from the frozen local store."""

    def test_sample_request_succeeds_with_outbound_connections_blocked(self) -> None:
        request_body = json.loads(REQUEST_PATH.read_text())
        client = TestClient(app)

        with patch(
            "socket.socket.connect",
            side_effect=AssertionError("outbound socket connection attempted"),
        ), patch(
            "socket.socket.connect_ex",
            side_effect=AssertionError("outbound socket connection attempted"),
        ), patch(
            "socket.create_connection",
            side_effect=AssertionError("outbound socket connection attempted"),
        ):
            response = client.post("/soil/layers", json=request_body)

        self.assertEqual(response.status_code, 200)
