from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Video, VideoAnalysis
from services.gemini_service import GeminiIntelligenceService
from services.transcript_service import TranscriptService

router = APIRouter(prefix="/videos", tags=["Videos"])
gemini_service = GeminiIntelligenceService()


@router.get("/")
async def list_videos(category: str | None = None, limit: int = 50, db: AsyncSession = Depends(get_db)):
    stmt = select(Video).order_by(Video.published_at.desc()).limit(limit)
    if category:
        stmt = stmt.where(Video.category == category)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{video_id}")
async def get_video(video_id: str, db: AsyncSession = Depends(get_db)):
    cleaned_video_id = (video_id or "").strip()
    if not cleaned_video_id:
        raise HTTPException(status_code=400, detail="video_id is required")

    video = await db.get(Video, cleaned_video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.get("/{video_id}/analysis")
async def get_or_create_analysis(video_id: str, db: AsyncSession = Depends(get_db)):
    cleaned_video_id = (video_id or "").strip()
    if not cleaned_video_id:
        raise HTTPException(status_code=400, detail="video_id is required")

    stmt = select(VideoAnalysis).where(VideoAnalysis.video_id == cleaned_video_id)
    result = await db.execute(stmt)
    analysis = result.scalar_one_or_none()
    if analysis:
        return analysis

    video = await db.get(Video, cleaned_video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    transcript = video.raw_transcript
    if not transcript:
        transcript = TranscriptService.get_transcript(cleaned_video_id)
        if transcript:
            video.raw_transcript = transcript
            video.has_transcript = True
            await db.commit()

    data = await gemini_service.analyze_video_content(
        title=video.title,
        channel=video.channel_title,
        transcript=transcript,
        description=video.description,
    )

    new_analysis = VideoAnalysis(
        video_id=cleaned_video_id,
        executive_summary=data.get("executive_summary", ""),
        key_takeaways=data.get("key_takeaways", []),
        topics_covered=data.get("topics_covered", []),
        entities=data.get("entities", {}),
        fact_check_notes=data.get("fact_check_notes", []),
        upsc_relevance=data.get("upsc_relevance", {}),
        deep_dossier_markdown=data.get("deep_dossier_markdown", ""),
    )
    db.add(new_analysis)
    await db.commit()
    await db.refresh(new_analysis)
    return new_analysis
