from google import genai
from google.genai import types
import json
import logging
from config import settings

logger = logging.getLogger(__name__)

class FactCheckerService:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

    async def verify_claims(self, claims: list[str], external_evidence: list[dict] = None) -> list[dict]:
        """
        Cross-examines stated claims against known facts and supplementary evidence.
        Categorizes claims into 'Verified', 'Disputed', or 'Unverified' with explanations.
        """
        if not claims:
            return []

        if not self.client:
            return [
                {
                    "claim": claim,
                    "status": "Unverified",
                    "details": "Verification engine requires Gemini API key."
                }
                for claim in claims
            ]

        evidence_str = "\n".join([f"- {e.get('snippet', '')}" for e in (external_evidence or [])])

        prompt = f"""
        You are an objective news fact-verification engine.
        Evaluate the following claims for accuracy against verified general knowledge and the supplementary context provided.

        Supplementary Context:
        {evidence_str}

        Claims to verify:
        {json.dumps(claims, indent=2)}

        Return a single valid JSON list of objects matching this schema:
        [
            {{
                "claim": "Stated claim",
                "status": "Verified" | "Disputed" | "Unverified",
                "details": "Clear reasoning citing facts, dates, or context. Never invent evidence."
            }}
        ]
        """

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"Fact checking failed: {e}")
            return [
                {
                    "claim": claim,
                    "status": "Unverified",
                    "details": f"Verification encountered an error: {str(e)}"
                }
                for claim in claims
            ]
