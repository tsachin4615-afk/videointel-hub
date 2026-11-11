from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import Video, VideoAnalysis

router = APIRouter(prefix="/assistant", tags=["Assistant"])


class QuestionRequest(BaseModel):
    question: str
    video_id: str | None = None


@router.post("/ask")
async def ask_assistant(req: QuestionRequest, db: AsyncSession = Depends(get_db)):
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Gemini API key is not configured.")

    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    video_id = (req.video_id or "").strip()
    context_snippets: list[str] = []

    if video_id:
        video = await db.get(Video, video_id)
        analysis = await db.get(VideoAnalysis, video_id)
        if video and analysis:
            context_snippets.append(
                f"Title: {video.title}\nChannel: {video.channel_title}\nSummary: {analysis.executive_summary}\nDossier: {analysis.deep_dossier_markdown[:3000]}"
            )
    else:
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
    {question}
    """

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3),
        )
        return {"answer": response.text, "grounded_in_video": video_id or None}
    except Exception as exc:  # pragma: no cover - depends on external service
        raise HTTPException(status_code=500, detail=f"Failed to generate assistant response: {exc}") from exc
