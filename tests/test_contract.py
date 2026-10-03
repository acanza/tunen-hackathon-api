"""Contract regression tests for the frozen soil layers POC."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import unittest

from fastapi.testclient import TestClient

from soil_api.app import app


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_REQUEST_PATH = REPOSITORY_ROOT / "docs" / "poc" / "samples" / "request.json"
SAMPLE_RESPONSE_PATH = REPOSITORY_ROOT / "docs" / "poc" / "samples" / "response.json"


class SampleContractTest(unittest.TestCase):
    """Verify the public route against the frozen request/response contract."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.request_body = json.loads(SAMPLE_REQUEST_PATH.read_text())
        cls.expected_response = json.loads(SAMPLE_RESPONSE_PATH.read_text())

    def test_sample_request_returns_exact_response(self) -> None:
        response = self.client.post("/soil/layers", json=self.request_body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.expected_response)

    def test_sample_artifact_urls_are_retrievable(self) -> None:
        response = self.client.post("/soil/layers", json=self.request_body)
        self.assertEqual(response.status_code, 200)

        urls = self._artifact_urls(response.json())
        self.assertTrue(urls)
        for url in urls:
            artifact_response = self.client.get(url)
            self.assertEqual(artifact_response.status_code, 200, url)

    @staticmethod
    def _artifact_urls(response_body: dict[str, Any]) -> set[str]:
        urls: set[str] = set()
        for field in response_body["fields"]:
            for layer in field["layers"]:
                for key in ("png_url", "geotiff_url"):
                    url = layer.get(key)
                    if url:
                        urls.add(url.split("#", 1)[0])
        return urls
