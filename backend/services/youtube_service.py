from googleapiclient.discovery import build
from datetime import datetime
from config import settings
import logging

logger = logging.getLogger(__name__)

class YouTubeService:
    def __init__(self):
        self.api_key = settings.YOUTUBE_API_KEY
        self.client = build("youtube", "v3", developerKey=self.api_key) if self.api_key else None

    def fetch_channel_recent_videos(self, channel_id: str, max_results: int = 5) -> list[dict]:
        if not self.client:
            logger.warning("YouTube API key not configured. Skipping live discovery.")
            return []
        
        try:
            response = self.client.search().list(
                part="snippet",
                channelId=channel_id,
                maxResults=max_results,
                order="date",
                type="video"
            ).execute()

            videos = []
            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                video_id = item.get("id", {}).get("videoId")
                if not video_id:
                    continue

                published_str = snippet.get("publishedAt", "")
                published_dt = datetime.fromisoformat(published_str.replace("Z", "+00:00")) if published_str else datetime.utcnow()

                videos.append({
                    "id": video_id,
                    "channel_id": channel_id,
                    "channel_title": snippet.get("channelTitle", "Unknown Channel"),
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "published_at": published_dt,
                    "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url", "")
                })
            return videos
        except Exception as e:
            logger.error(f"Error fetching videos for channel {channel_id}: {e}")
            return []
