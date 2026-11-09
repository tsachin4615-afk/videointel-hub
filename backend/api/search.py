from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from database import get_db
from models import Video, VideoAnalysis

router = APIRouter(prefix="/search", tags=["Search"])

@router.get("/")
async def search_intelligence(
    q: str = Query(..., min_length=2, description="Search query string"),
    limit: int = 25,
    db: AsyncSession = Depends(get_db)
):
    """
    Searches across video titles, descriptions, summaries, and topics.
    """
    search_pattern = f"%{q.strip()}%"
    
    stmt = (
        select(Video, VideoAnalysis)
        .outerjoin(VideoAnalysis, Video.id == VideoAnalysis.video_id)
        .where(
            or_(
                Video.title.ilike(search_pattern),
                Video.description.ilike(search_pattern),
                VideoAnalysis.executive_summary.ilike(search_pattern)
            )
        )
        .order_by(Video.published_at.desc())
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    records = result.all()

    matches = []
    for video, analysis in records:
        matches.append({
            "video_id": video.id,
            "title": video.title,
            "channel_title": video.channel_title,
            "published_at": video.published_at,
            "category": video.category,
            "summary": analysis.executive_summary if analysis else None,
            "topics": analysis.topics_covered if analysis else []
        })

    return {"query": q, "count": len(matches), "results": matches}
