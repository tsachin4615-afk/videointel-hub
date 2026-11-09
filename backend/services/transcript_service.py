from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import logging

logger = logging.getLogger(__name__)

class TranscriptService:
    @staticmethod
    def get_transcript(video_id: str, languages: list[str] = ["en", "hi"]) -> str | None:
        """
        Attempts to fetch video subtitles/transcripts in preferred languages.
        Returns combined text if found, or None if transcripts are unavailable or disabled.
        """
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
            full_text = " ".join([entry.get("text", "").strip() for entry in transcript_list])
            return full_text if full_text.strip() else None
        except (TranscriptsDisabled, NoTranscriptFound):
            logger.info(f"Transcript disabled or not found for video: {video_id}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching transcript for video {video_id}: {e}")
            return None
