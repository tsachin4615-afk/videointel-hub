import os
import sys
import asyncio
from datetime import datetime
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import settings
from database import init_db, AsyncSessionLocal
from models import Video
from sqlalchemy import select
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai

# Target channels to track
CHANNELS = [
    {"name": "StudyIQ IAS", "id": "UCrDxGhvy9x2m2MskR1Wc2qg", "category": "Current Affairs & UPSC"},
    {"name": "World Affairs by Unacademy", "id": "UCCJsQKOKArvDksacfT2rgQw", "category": "International Relations & Geopolitics"},
    {"name": "Parcham Classes", "id": "UC_QmsC24w74_s3nF3s3h5yw", "category": "Current Affairs & Static GK"},
    {"name": "AffairsCloud", "id": "UCiG8_6Z6dKkY9oT7G7X2j9w", "category": "Banking & Economy"},
    {"name": "India Decoded", "id": "UC0yN6_h7A5sZ0X7L7R3G8tw", "category": "National Analysis"},
]

def fetch_channel_videos(youtube, channel_info):
    """Fetch latest videos for a channel using YouTube Data API."""
    channel_id = channel_info.get("id") or channel_info.get("channel_id")
    channel_title = channel_info.get("name", "Unknown Channel")
    category = channel_info.get("category", "General Current Affairs")

    try:
        res = youtube.channels().list(
            part="contentDetails,snippet",
            id=channel_id
        ).execute()

        items = res.get("items", [])
        if not items:
            return []

        uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        actual_title = items[0]["snippet"].get("title", channel_title)

        playlist_res = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_id,
            maxResults=5
        ).execute()

        videos = []
        for item in playlist_res.get("items", []):
            snip = item.get("snippet", {})
            v_id = item.get("contentDetails", {}).get("videoId") or snip.get("resourceId", {}).get("videoId")
            if not v_id:
                continue

            item_channel_id = snip.get("channelId") or channel_id or "unknown_channel"

            pub_raw = snip.get("publishedAt")
            try:
                published_at = datetime.fromisoformat(pub_raw.replace("Z", "+00:00")) if pub_raw else datetime.utcnow()
            except Exception:
                published_at = datetime.utcnow()

            thumbnails = snip.get("thumbnails", {})
            thumb_url = (
                thumbnails.get("high", {}).get("url")
                or thumbnails.get("medium", {}).get("url")
                or f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg"
            )

            videos.append({
                "id": v_id,
                "channel_id": item_channel_id,
                "channel_title": snip.get("channelTitle") or actual_title,
                "title": snip.get("title", "Untitled Video"),
                "description": snip.get("description", ""),
                "published_at": published_at,
                "thumbnail_url": thumb_url,
                "category": category
            })
        return videos
    except Exception as e:
        print(f"[Warning] Failed fetching {channel_title}: {e}")
        return []

def get_transcript(video_id):
    """Fetch transcript with 0 YouTube quota cost."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'hi', 'en-IN'])
        return " ".join([t['text'] for t in transcript_list]), True
    except Exception:
        return None, False

def synthesize_with_gemini(title, transcript, description):
    """Synthesize dossier using Gemini."""
    if not settings.GEMINI_API_KEY:
        return "Gemini API key missing. Summary unavailable."

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    content = transcript if transcript else description
    if not content:
        return "No transcript or content available for analysis."

    prompt = f"""
Analyze this educational/current affairs video content:
Title: {title}
Content: {content[:10000]}

Provide an exam-ready intelligence brief structured as:
1. Executive Summary (2-3 concise sentences)
2. High-Yield Key Points (3-5 bullet points)
3. Strategic / Exam Relevance (UPSC, Banking, State PSC relevance)
"""
    try:
        response = client.models.generate_content
