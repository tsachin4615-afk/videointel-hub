from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from google import genai
from google.genai import types
from database import get_db
from models import VideoAnalysis, Video
from config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assistant", tags=["Assistant"])

class QuestionRequest(BaseModel):
    question: str
    video_id: str | None = None

@router.post("/ask")
async def ask_assistant(req: QuestionRequest, db: AsyncSession = Depends(get_db)):
    """
    RAG-powered intelligence assistant answering questions grounded in collected reports.
    """
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Gemini API key is not configured.")

    context_snippets = []

    # If asking about a specific video
    if req.video_id:
        video = await db.get(Video, req.video_id)
        analysis = await db.get(VideoAnalysis, req.video_id)
        if video and analysis:
            context_snippets.append(
                f"Title: {video.title}\nChannel: {video.channel_title}\nSummary: {analysis.executive_summary}\nDossier: {analysis.deep_dossier_markdown[:3000]}"
            )
    else:
        # Ground question in recent analyses
        stmt = (
            select(Video.title, VideoAnalysis.executive_summary)
            .join(VideoAnalysis, Video.id == VideoAnalysis.video_id)
            .order_by(VideoAnalysis.processed_at.desc())
            .limit(5)
        )
        result = await db.execute(stmt)
        for title, summary in result.all():
            context_snippets.append(f"Video: {title}\nSummary: {summary}\n")

    grounding_context = "\n---\n".join(context_snippets) if context_snippets else "No local intelligence records found."

    prompt = f"""
    You are VideoIntel Assistant, an objective news and current affairs tutor.
    Answer the user's question accurately using the provided verified intelligence context.
    If the context does not contain enough information to answer definitively, state that clearly without guessing.

    Context:
    {grounding_context}

    Question:
    {req.question}
    """

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3)
        )
        return {"answer": response.text, "grounded_in_video": req.video_id}
    except Exception as e:
        logger.error(f"Assistant generation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate assistant response.")
