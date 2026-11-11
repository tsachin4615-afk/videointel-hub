from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app
from backend.security import sanitize_input, verify_token
from backend.services.gemini_service import GeminiIntelligenceService


def test_gemini_parser_handles_fenced_json():
    raw = """```json
{
  "executive_summary": "ok",
  "key_takeaways": [],
  "topics_covered": [],
  "entities": {"people": [], "organizations": [], "locations": []},
  "fact_check_notes": [],
  "upsc_relevance": {
    "syllabus_mapping": "GS",
    "prelims_pointers": [],
    "mains_pointers": []
  },
  "deep_dossier_markdown": "hello"
}
```"""
    parsed = GeminiIntelligenceService._parse_json_response(raw)
    assert parsed["executive_summary"] == "ok"


def test_gemini_parser_rejects_list_response():
    try:
        GeminiIntelligenceService._parse_json_response("[1, 2, 3]")
        assert False, "Expected list response to be rejected"
    except TypeError:
        pass


def test_app_rejects_empty_assistant_question():
    client = TestClient(app)
    response = client.post("/api/assistant/ask", json={"question": ""})
    assert response.status_code == 400


def test_sanitize_input_handles_none_and_control_chars():
    assert sanitize_input(None) == ""
    assert sanitize_input("hello\x00world") == "helloworld"


def test_verify_token_requires_match():
    assert verify_token(None) is False
    assert verify_token("abc") is False
