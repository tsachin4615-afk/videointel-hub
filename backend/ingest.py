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
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"Synthesis error: {str(e)}"

async def run_pipeline():
    print("[Ingest] Initializing database...")
    await init_db()

    if not settings.YOUTUBE_API_KEY:
        print("[Error] YOUTUBE_API_KEY is not set.")
        return

    youtube = build("youtube", "v3", developerKey=settings.YOUTUBE_API_KEY)

    async with AsyncSessionLocal() as session:
        for ch in CHANNELS:
            print(f"[Ingest] Checking channel: {ch['name']}...")
            videos = fetch_channel_videos(youtube, ch)

            for v in videos:
                existing = await session.execute(select(Video).where(Video.id == v["id"]))
                if existing.scalar_one_or_none():
                    continue

                print(f"[Ingest] Processing new video: {v['title'][:40]}...")
                transcript, has_transcript = get_transcript(v["id"])
                analysis = synthesize_with_gemini(v["title"], transcript, v["description"])

                video_entry = Video(
                    id=v["id"],
                    channel_id=v["channel_id"],
                    channel_title=v["channel_title"],
                    title=v["title"],
                    description=v["description"],
                    published_at=v["published_at"],
                    thumbnail_url=v["thumbnail_url"],
                    category=v["category"],
                    raw_transcript=transcript,
                    has_transcript=1 if has_transcript else 0,
                    analysis=analysis,
                    created_at=datetime.utcnow()
                )
                session.add(video_entry)
                await session.commit()
                print(f"[Ingest] Saved: {v['title'][:30]}")

    print("[Ingest] Pipeline execution cycle finished.")

if __name__ == "__main__":
    asyncio.run(run_pipeline())
