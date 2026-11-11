from __future__ import annotations

import json
import logging
import re

from google import genai
from google.genai import types

from config import settings

logger = logging.getLogger(__name__)

_REQUIRED_ANALYSIS_KEYS = {
    "executive_summary",
    "key_takeaways",
    "topics_covered",
    "entities",
    "fact_check_notes",
    "upsc_relevance",
    "deep_dossier_markdown",
}


class GeminiIntelligenceService:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

    async def analyze_video_content(self, title: str, channel: str, transcript: str | None, description: str = "") -> dict:
        if not self.client:
            logger.warning("Gemini API key not configured. Returning fallback skeleton.")
            return self._build_empty_response(title, "API key not configured.")

        content_source = "Transcript" if transcript else "Video Description (Transcript Unavailable)"
        input_body = (transcript or description or "")[:15000]

        if not input_body.strip():
            return self._build_empty_response(title, "No text or transcript available for analysis.")

        prompt = f"""
        You are a current affairs intelligence and analytical engine.
        Analyze the following video content thoroughly for competitive exams (UPSC/civil services) and serious news intelligence.

        Video Title: {title}
        Source Channel: {channel}
        Source Content Type: {content_source}
        Content:
        {input_body}

        Return a single strictly valid JSON object matching this schema:
        {{
            "executive_summary": "Comprehensive 3-4 sentence overview of the news or event.",
            "key_takeaways": [
                "Detailed takeaway point 1",
                "Detailed takeaway point 2",
                "Detailed takeaway point 3"
            ],
            "topics_covered": ["Topic 1", "Topic 2", "Topic 3"],
            "entities": {{
                "people": ["Name 1"],
                "organizations": ["Org 1"],
                "locations": ["Country/City 1"]
            }},
            "fact_check_notes": [
                {{
                    "claim": "Specific factual claim made in video",
                    "verification": "Assessment against known facts",
                    "status": "Verified"
                }}
            ],
            "upsc_relevance": {{
                "syllabus_mapping": "e.g., GS Paper II: Bilateral Relations",
                "prelims_pointers": ["Factual note 1", "Factual note 2"],
                "mains_pointers": ["Analytical question or theme 1", "Analytical question or theme 2"]
            }},
            "deep_dossier_markdown": "Multi-paragraph markdown report detailing background, timeline, strategic implications, and conclusion."
        }}
        """

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            parsed = self._parse_json_response(response.text)
            if not isinstance(parsed, dict):
                raise TypeError("Gemini response was not a JSON object.")
            missing = sorted(key for key in _REQUIRED_ANALYSIS_KEYS if key not in parsed)
            if missing:
                raise ValueError(f"Gemini response missing keys: {missing}")
            return parsed
        except Exception as exc:
            logger.error(f"Gemini analysis failure: {exc}")
            return self._build_empty_response(title, f"Analysis failed: {exc}")

    @staticmethod
    def _parse_json_response(raw_text: str | None) -> dict:
        if not raw_text:
            raise ValueError("Empty Gemini response")

        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)

        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(0)

        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            raise TypeError("Gemini returned a JSON list instead of an object")
        return parsed

    def _build_empty_response(self, title: str, reason: str) -> dict:
        return {
            "executive_summary": f"Could not generate full intelligence: {reason}",
            "key_takeaways": ["Analysis pending or transcript unavailable."],
            "topics_covered": ["Current Affairs"],
            "entities": {"people": [], "organizations": [], "locations": []},
            "fact_check_notes": [],
            "upsc_relevance": {
                "syllabus_mapping": "General Studies",
                "prelims_pointers": [],
                "mains_pointers": [],
            },
            "deep_dossier_markdown": f"### {title}\n\n*Notice: {reason}*",
        }
