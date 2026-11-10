import os
import json
import urllib.request
import urllib.parse
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

# Target channels for current affairs & exam prep
CHANNELS = [
    {"name": "StudyIQ IAS", "query": "StudyIQ IAS"},
    {"name": "World Affairs", "query": "World Affairs Unacademy"},
    {"name": "WION", "query": "WION news"},
    {"name": "Firstpost Vantage", "query": "Firstpost Vantage"},
    {"name": "India Decoded", "query": "India Decoded AA"},
    {"name": "Times Axis", "query": "Times Axis"},
    {"name": "Parcham Classes", "query": "Parcham Classes"},
    {"name": "Coffee With Sumeet Jain", "query": "Coffee With Sumeet Jain"}
]

def analyze_with_gemini(client, title, description, channel):
    if not client:
        return {
            "summary": description[:200] + "..." if description else "Analysis summary pending.",
            "takeaways": ["GEMINI_API_KEY secret not detected."],
            "dossier": f"### {title}\n\n{description[:600]}"
        }

    prompt = f"""
    You are an expert geopolitical intelligence and competitive exam current affairs analyst.
    Analyze this report:
    Channel: {channel}
    Title: {title}
    Context: {description[:2000]}

    Provide your assessment strictly in valid JSON format:
    {{
      "summary": "2 concise sentences summarizing the core strategic points.",
      "takeaways": [
        "Core policy or factual takeaway",
        "Geopolitical or strategic implication",
        "High-yield competitive exam pointer"
      ],
      "dossier": "### Strategic Background\\nDetailed context.\\n\\n### Key Developments\\nPoint-by-point breakdown.\\n\\n### Strategic & Exam Implications\\nRelevance to international relations, policy, and exams."
    }}
    """

    for model_name in ["gemini-2.0-flash", "gemini-1.5-flash"]:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"[Gemini Error on {model_name}] {title[:30]}: {e}")
            continue

    return {
        "summary": description[:200] + "..." if description else "Summary unavailable.",
        "takeaways": ["Analysis temporarily unavailable."],
        "dossier": f"### {title}\n\n{description[:600]}"
    }

def fetch_all():
    if not YOUTUBE_API_KEY:
        print("[Fatal Error] YOUTUBE_API_KEY is missing from environment variables!")
        return

    client = None
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            print("[Init] Gemini client initialized.")
        except Exception as e:
            print(f"[Init Error] Gemini: {e}")

    all_videos = []

    for ch in CHANNELS:
        name = ch["name"]
        print(f"\n[Channel] Fetching {name} via YouTube API...")

        params = {
            "part": "snippet",
            "q": ch["query"],
            "type": "video",
            "order": "date",
            "maxResults": 2,
            "key": YOUTUBE_API_KEY
        }
        url = f"https://www.googleapis.com/youtube/v3/search?{urllib.parse.urlencode(params)}"

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=12) as res:
                data = json.loads(res.read().decode('utf-8'))

            items = data.get("items", [])
            print(f" -> Found {len(items)} videos for {name}")

            for item in items:
                v_id = item["id"]["videoId"]
                snippet = item["snippet"]
                v_title = snippet.get("title", "")
                v_desc = snippet.get("description", "")
                published = snippet.get("publishedAt", "")
                thumb = snippet.get("thumbnails", {}).get("high", {}).get("url", f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg")

                print(f"    Synthesizing: {v_title[:45]}...")
                ai_intel = analyze_with_gemini(client, v_title, v_desc, name)

                all_videos.append({
                    "id": v_id,
                    "channel_title": name,
                    "title": v_title,
                    "published_at": published,
                    "thumbnail_url": thumb,
                    "executive_summary": ai_intel.get("summary", ""),
                    "key_takeaways": ai_intel.get("takeaways", []),
                    "deep_dossier_markdown": ai_intel.get("dossier", "")
                })

        except Exception as e:
            print(f"[API Error] Failed fetching {name}: {e}")

    if all_videos:
        with open("videos.json", "w", encoding="utf-8") as f:
            json.dump(all_videos, f, indent=2, ensure_ascii=False)
        print(f"\n[Complete] Successfully generated {len(all_videos)} dossiers across all channels into videos.json")
    else:
        print("\n[Warning] No videos collected; keeping existing videos.json")

if __name__ == "__main__":
    fetch_all()
