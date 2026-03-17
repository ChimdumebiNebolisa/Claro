"""Integration tests for main FastAPI app (static and HTML routes only; no GCS/Gemini)."""
import pytest

from fastapi.testclient import TestClient

# Import app only when running tests that don't need GCS/Gemini (we only hit GET / and GET /test)
from main import app

client = TestClient(app)


def test_index_returns_html():
    """GET / returns HTML (Claros frontend or fallback)."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert b"<" in response.content and b"html" in response.content.lower()


def test_test_page_returns_html():
    """GET /test returns HTML (voice test page or 404 if file missing)."""
    response = client.get("/test")
    # 200 if test_voice.html exists, 404 otherwise
    assert response.status_code in (200, 404)
    if response.status_code == 200:
        assert "text/html" in response.headers.get("content-type", "")
