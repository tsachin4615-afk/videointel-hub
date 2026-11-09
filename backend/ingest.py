import asyncio
import json
import os
from datetime import datetime
from sqlalchemy import select
from database import init_db, AsyncSessionLocal
from models import Video, VideoAnalysis
from services.youtube_service import YouTubeService
from services.transcript_service import TranscriptService
from services.gemini_service import GeminiIntelligenceService

async def run_pipeline():
    print("[Ingest] Initializing database...")
    await init_db()

    channels_file = os.path.join(os.path.dirname(__file__), "..", "data", "channels.json")
    if not os.path.exists(channels_file):
        print(f"[Ingest] Channels configuration not found at {channels_file}")
        return

    with open(channels_file, "r", encoding="utf-8") as f:
        channels_data = json.load(f)

    yt = YouTubeService()
    gemini = GeminiIntelligenceService()

    async with AsyncSessionLocal() as session:
        for channel in channels_data:
            c_id = channel.get("channel_id")
            c_name = channel.get("name")
            category = channel.get("category", "General")

            print(f"[Ingest] Checking channel: {c_name} ({c_id})")
            recent_videos = yt.fetch_channel_recent_videos(channel_id=c_id, max_results=3)

            for v in recent_videos:
                v_id = v["id"]
                existing = await session.get(Video, v_id)
                if existing:
                    continue  # Video already indexed

                print(f"[Ingest] New video discovered: {v['title']} ({v_id})")
                transcript = TranscriptService.get_transcript(v_id)

                video_entry = Video(
                    id=v_id,
                    channel_id=c_id,
                    channel_title=c_name,
                    title=v["title"],
                    description=v["description"],
                    published_at=v["published_at"],
                    thumbnail_url=v["thumbnail_url"],
                    category=category,
                    raw_transcript=transcript,
                    has_transcript=bool(transcript)
                )
                session.add(video_entry)
                await session.flush()

                # Run synthesis through Gemini
                print(f"[Ingest] Synthesizing intelligence dossier for {v_id}...")
                analysis_data = await gemini.analyze_video_content(
                    title=v["title"],
                    channel=c_name,
                    transcript=transcript,
                    description=v["description"]
                )

                analysis_entry = VideoAnalysis(
                    video_id=v_id,
                    executive_summary=analysis_data.get("executive_summary", ""),
                    key_takeaways=analysis_data.get("key_takeaways", []),
                    topics_covered=analysis_data.get("topics_covered", []),
                    entities=analysis_data.get("entities", {}),
                    fact_check_notes=analysis_data.get("fact_check_notes", []),
                    upsc_relevance=analysis_data.get("upsc_relevance", {}),
                    deep_dossier_markdown=analysis_data.get("deep_dossier_markdown", "")
                )
                session.add(analysis_entry)
                await session.commit()
                print(f"[Ingest] Successfully processed and stored: {v_id}")

    print("[Ingest] Pipeline execution cycle finished.")

if __name__ == "__main__":
    asyncio.run(run_pipeline())
