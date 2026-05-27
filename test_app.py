"""
Basic tests for the web-keyword-scanner Flask app.
Run: .venv/bin/pytest test_app.py -v
"""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from app import _evict_old_scans, _normalise_url, _snippets, app, scans


# ---------------------------------------------------------------------------
# Unit tests — pure functions
# ---------------------------------------------------------------------------


class TestNormaliseUrl:
    def test_adds_https_to_bare_domain(self):
        assert _normalise_url("example.com") == "https://example.com"

    def test_leaves_https_url_alone(self):
        assert _normalise_url("https://example.com") == "https://example.com"

    def test_leaves_http_url_alone(self):
        assert _normalise_url("http://example.com") == "http://example.com"

    def test_strips_whitespace(self):
        assert _normalise_url("  example.com  ") == "https://example.com"

    def test_empty_string_stays_empty(self):
        assert _normalise_url("") == ""


class TestSnippets:
    def test_returns_snippet_around_keyword(self):
        text = "a" * 100 + "crypto" + "b" * 100
        result = _snippets(text, "crypto")
        assert "crypto" in result
        assert result.startswith("…")
        assert result.endswith("…")

    def test_returns_empty_when_keyword_not_found(self):
        assert _snippets("hello world", "bitcoin") == ""

    def test_clamps_start_at_zero(self):
        result = _snippets("crypto is great", "crypto")
        assert "crypto" in result

    def test_clamps_end_at_text_length(self):
        result = _snippets("great crypto", "crypto")
        assert "crypto" in result


class TestEvictOldScans:
    def test_evicts_old_finished_scans(self):
        scans.clear()
        scans["old"] = {"done": True, "ts": time.time() - 7200, "queue": MagicMock()}
        scans["new"] = {"done": True, "ts": time.time(), "queue": MagicMock()}
        scans["active"] = {"done": False, "ts": time.time() - 7200, "queue": MagicMock()}

        _evict_old_scans()

        assert "old" not in scans       # evicted: done + stale
        assert "new" in scans           # kept: done but fresh
        assert "active" in scans        # kept: not done
        scans.clear()


# ---------------------------------------------------------------------------
# Integration tests — Flask test client
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    app.config["TESTING"] = True
    scans.clear()
    with app.test_client() as c:
        yield c
    scans.clear()


class TestIndexRoute:
    def test_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_returns_html(self, client):
        resp = client.get("/")
        assert b"<!DOCTYPE html>" in resp.data or b"<html" in resp.data


class TestStartScan:
    def _post(self, client, payload):
        return client.post(
            "/scan",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_missing_keywords_returns_400(self, client):
        resp = self._post(client, {"start_url": "https://example.com", "keywords": ""})
        assert resp.status_code == 400
        assert b"keyword" in resp.data.lower()

    def test_missing_url_returns_400(self, client):
        resp = self._post(client, {"start_url": "", "url_list": "", "keywords": "bitcoin"})
        assert resp.status_code == 400
        assert b"url" in resp.data.lower()

    def test_valid_request_returns_scan_id(self, client):
        with patch("app.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            resp = self._post(
                client,
                {
                    "start_url": "https://example.com",
                    "keywords": "bitcoin",
                    "max_depth": "1",
                    "max_pages": "5",
                },
            )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "scan_id" in data
        assert len(data["scan_id"]) == 36  # UUID format

    def test_invalid_max_depth_returns_400(self, client):
        resp = self._post(
            client,
            {
                "start_url": "https://example.com",
                "keywords": "bitcoin",
                "max_depth": "not-a-number",
            },
        )
        assert resp.status_code == 400
        assert b"integer" in resp.data.lower()

    def test_max_depth_clamped_to_5(self, client):
        with patch("app.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            resp = self._post(
                client,
                {
                    "start_url": "https://example.com",
                    "keywords": "bitcoin",
                    "max_depth": "999",
                    "max_pages": "5",
                },
            )
        assert resp.status_code == 200

    def test_concurrent_scan_limit(self, client):
        # Fill the active scan slots
        scans.clear()
        import queue as q_mod
        for i in range(10):
            scans[f"scan-{i}"] = {"done": False, "ts": time.time(), "queue": q_mod.Queue()}

        resp = self._post(
            client,
            {"start_url": "https://example.com", "keywords": "bitcoin"},
        )
        assert resp.status_code == 429
        scans.clear()


class TestStreamRoute:
    def test_unknown_scan_id_returns_404(self, client):
        resp = client.get("/stream/nonexistent-id")
        assert resp.status_code == 404
