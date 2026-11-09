from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import Video, VideoAnalysis
from services.report_builder import ReportBuilder

router = APIRouter(prefix="/articles", tags=["Articles"])

@router.get("/")
async def list_articles(limit: int = 30, db: AsyncSession = Depends(get_db)):
    """Fetches completed intelligence reports with associated video metadata."""
    stmt = (
        select(VideoAnalysis, Video)
        .join(Video, VideoAnalysis.video_id == Video.id)
        .order_by(VideoAnalysis.processed_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    records = result.all()

    articles = []
    for analysis, video in records:
        articles.append({
            "video_id": video.id,
            "title": video.title,
            "channel_title": video.channel_title,
            "published_at": video.published_at,
            "category": video.category,
            "thumbnail_url": video.thumbnail_url,
            "executive_summary": analysis.executive_summary,
            "key_takeaways": analysis.key_takeaways,
            "topics_covered": analysis.topics_covered,
            "upsc_relevance": analysis.upsc_relevance,
            "processed_at": analysis.processed_at
        })
    return articles

@router.get("/{video_id}/markdown")
async def get_article_markdown(video_id: str, db: AsyncSession = Depends(get_db)):
    """Exports structured dossier in full Markdown format."""
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video record not found")

    analysis = await db.get(VideoAnalysis, video_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Intelligence report not found")

    analysis_dict = {
        "executive_summary": analysis.executive_summary,
        "key_takeaways": analysis.key_takeaways,
        "topics_covered": analysis.topics_covered,
        "entities": analysis.entities,
        "fact_check_notes": analysis.fact_check_notes,
        "upsc_relevance": analysis.upsc_relevance,
        "deep_dossier_markdown": analysis.deep_dossier_markdown
    }

    markdown_text = ReportBuilder.build_markdown_article(
        title=video.title,
        channel=video.channel_title,
        video_url=f"https://www.youtube.com/watch?v={video.id}",
        analysis=analysis_dict
    )
    return {"video_id": video_id, "markdown": markdown_text}
