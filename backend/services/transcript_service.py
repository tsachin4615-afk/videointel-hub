from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TranscriptService:
    @staticmethod
    def get_transcript(video_id: str, languages: list[str] | None = None) -> str | None:
        try:
            from youtube_transcript_api import (
                NoTranscriptFound,
                TranscriptsDisabled,
                YouTubeTranscriptApi,
            )
        except Exception as exc:  # pragma: no cover - dependency guard
            logger.warning("Transcript dependencies unavailable: %s", exc)
            return None

        selected_languages = languages or ["en", "hi"]
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=selected_languages)
            full_text = " ".join([entry.get("text", "").strip() for entry in transcript_list])
            return full_text.strip() or None
        except (TranscriptsDisabled, NoTranscriptFound):
            logger.info("Transcript disabled or not found for video: %s", video_id)
            return None
        except Exception as exc:
            logger.warning("Error fetching transcript for video %s: %s", video_id, exc)
            return None
