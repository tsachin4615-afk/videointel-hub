from google import genai
from google.genai import types
import json
import logging
from config import settings

logger = logging.getLogger(__name__)

class GeminiIntelligenceService:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

    async def analyze_video_content(self, title: str, channel: str, transcript: str | None, description: str = "") -> dict:
        """
        Analyzes video transcript (or description if transcript is absent) using Gemini.
        Returns structured synthesis covering summary, key points, UPSC relevance, and entities.
        """
        if not self.client:
            logger.warning("Gemini API key not configured. Returning fallback skeleton.")
            return self._build_empty_response(title, "API key not configured.")

        # If transcript is missing, clearly state it in the analysis
        content_source = "Transcript" if transcript else "Video Description (Transcript Unavailable)"
        input_body = transcript[:15000] if transcript else description[:3000]

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
                    temperature=0.2
                )
            )
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"Gemini analysis failure: {e}")
            return self._build_empty_response(title, f"Analysis failed: {str(e)}")

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
                "mains_pointers": []
            },
            "deep_dossier_markdown": f"### {title}\n\n*Notice: {reason}*"
        }
