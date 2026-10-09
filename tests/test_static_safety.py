"""Regression tests for static safety and read-only store behavior."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import unittest

from fastapi.testclient import TestClient

from soil_api.app import app
from soil_api.database import open_read_only_connection
from soil_api.settings import get_settings


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RESPONSE_PATH = REPOSITORY_ROOT / "docs" / "poc" / "samples" / "response.json"


class StaticSafetyTest(unittest.TestCase):
    """Ensure static delivery cannot escape or mutate the frozen store."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        response_body = json.loads(SAMPLE_RESPONSE_PATH.read_text())
        cls.png_url = next(
            layer["png_url"]
            for field in response_body["fields"]
            for layer in field["layers"]
            if layer.get("png_url")
        )
        cls.artifact_url = cls.png_url.split("#", 1)[0]
        settings = get_settings()
        cls.database_path = settings.database_path
        cls.artifact_path = settings.store_root / cls.artifact_url.removeprefix("/static/")

    def test_static_response_has_immutable_cache_and_mime_type(self) -> None:
        response = self.client.get(self.artifact_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(
            response.headers["cache-control"],
            "public, max-age=31536000, immutable",
        )

    def test_invalid_static_paths_return_not_found(self) -> None:
        for path in (
            "/static/%2e%2e/soil.sqlite",
            "/static/soil.sqlite",
            "/static/runs/missing.png",
            "/static/runs/not-an-artifact.txt",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_read_only_connection_rejects_writes(self) -> None:
        connection = open_read_only_connection()
        try:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("CREATE TABLE should_not_exist (value TEXT)")
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'should_not_exist'"
            ).fetchall()
            self.assertEqual(tables, [])
        finally:
            connection.close()

    def test_static_request_does_not_mutate_store_or_artifact(self) -> None:
        database_digest_before = self._digest(self.database_path)
        artifact_digest_before = self._digest(self.artifact_path)

        response = self.client.get(self.artifact_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._digest(self.database_path), database_digest_before)
        self.assertEqual(self._digest(self.artifact_path), artifact_digest_before)

    @staticmethod
    def _digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
