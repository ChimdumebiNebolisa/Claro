"""POST /api/write tests with mocked GCS and Gemini (no real API calls)."""
import pytest
from fastapi.testclient import TestClient

import main as main_module

_FIXED_TITLE = "Mock Assignment"
_FIXED_QUESTIONS = [
    {"id": 1, "text": "First?"},
    {"id": 3, "text": "Second?"},
    {"id": 7, "text": "Third?"},
]


def _fake_load_assignment(_assignment_id: str):
    return _FIXED_TITLE, list(_FIXED_QUESTIONS)


@pytest.fixture
def write_client(monkeypatch):
    monkeypatch.setattr(main_module, "load_assignment_from_gcs", _fake_load_assignment)
    monkeypatch.setattr(main_module, "get_api_key", lambda: "test-api-key-not-used")

    class FakeChunk:
        __slots__ = ("text",)

        def __init__(self, text: str):
            self.text = text

    class FakeModels:
        async def generate_content_stream(self, model, contents):
            async def _stream():
                yield FakeChunk("stub-")
                yield FakeChunk("answer")

            return _stream()

    class FakeAio:
        def __init__(self):
            self.models = FakeModels()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.aio = FakeAio()

    import types as std_types

    monkeypatch.setattr(main_module, "genai", std_types.SimpleNamespace(Client=FakeClient))
    return TestClient(main_module.app)


def test_write_unknown_question_id_returns_400(write_client: TestClient):
    response = write_client.post(
        "/api/write/mock-assignment-id",
        json={
            "question_id": 99,
            "conversation": [],
            "answer_candidate": "",
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert "detail" in body
    assert "Unknown question id" in body["detail"]


def test_write_valid_question_id_streams_stub_text(write_client: TestClient):
    response = write_client.post(
        "/api/write/mock-assignment-id",
        json={
            "question_id": 7,
            "conversation": [{"speaker": "user", "text": "My answer is seven."}],
            "answer_candidate": "7",
        },
    )
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert response.text == "stub-answer"
