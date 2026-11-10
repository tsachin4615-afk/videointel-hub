import os
import json
import urllib.request
import urllib.parse
from datetime import datetime
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

# Target current affairs & exam intelligence channels by handle / query
CHANNELS = [
    {"name": "StudyIQ IAS", "query": "StudyIQ IAS"},
    {"name": "World Affairs", "query": "World Affairs Unacademy"},
    {"name": "WION", "query": "WION news"},
    {"name": "DEF Talks by Aadi", "query": "DEF Talks by Aadi"},
    {"name": "Firstpost Vantage", "query": "Firstpost Vantage"}
]

def analyze_with_gemini(client, title, description, channel):
    if not client:
        return {
            "summary": description[:280] + "..." if description else "Analysis summary pending.",
            "takeaways": ["API key environment variable not detected."],
            "dossier": f"### {title}\n\n{description}"
        }

    prompt = f"""
    You are an expert geopolitical intelligence and competitive exam current affairs analyst.
    Analyze this report:
    Channel: {channel}
    Title: {title}
    Context: {description[:2500]}

    Provide your assessment strictly in valid JSON format:
    {{
      "summary": "Concise 2-sentence executive summary of core strategic points.",
      "takeaways": [
        "Key takeaway 1 (factual / policy focus)",
        "Key takeaway 2 (strategic / global implication)",
        "Key takeaway 3 (high-yield exam pointer)"
      ],
      "dossier": "### Strategic Background\\nDetailed background.\\n\\n### Key Developments\\nPoints covered.\\n\\n### Strategic & Exam Relevance\\nRelevance to international relations, policy, and exams."
    }}
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"[Gemini Error] {title}: {e}")
        return {
            "summary": description[:280] + "..." if description else "Summary unavailable.",
            "takeaways": [
                "Detailed synthesis pending API rate reset.",
                "Review raw update directly via Watch link."
            ],
            "dossier": f"### {title}\n\n{description}"
        }

def fetch_videos_via_api():
    client = None
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            print("[Init] Gemini client ready.")
        except Exception as e:
            print(f"[Init Error] Gemini: {e}")

    all_videos = []

    for ch in CHANNELS:
        try:
            # Query the YouTube Data API v3 Search endpoint
            params = {
                "part": "snippet",
                "q": ch["query"],
                "type": "video",
                "order": "date",
                "maxResults": 2,
                "key": YOUTUBE_API_KEY
            }
            url = f"https://www.googleapis.com/youtube/v3/search?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode('utf-8'))

            items = data.get("items", [])
            print(f"[Channel] {ch['name']}: Retrieved {len(items)} videos via API")

            for item in items:
                v_id = item["id"]["videoId"]
                snippet = item["snippet"]
                v_title = snippet["title"]
                v_desc = snippet["description"]
                published = snippet["publishedAt"]
                thumb = snippet["thumbnails"].get("high", {}).get("url", f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg")

                print(f" -> Analyzing: {v_title[:40]}...")
                ai_intel = analyze_with_gemini(client, v_title, v_desc, ch['name'])

                all_videos.append({
                    "id": v_id,
                    "channel_title": ch['name'],
                    "title": v_title,
                    "published_at": published,
                    "thumbnail_url": thumb,
                    "executive_summary": ai_intel.get("summary", ""),
                    "key_takeaways": ai_intel.get("takeaways", []),
                    "deep_dossier_markdown": ai_intel.get("dossier", "")
                })

        except Exception as e:
            print(f"[API Error] Failed fetching {ch['name']}: {e}")

    with open("videos.json", "w", encoding="utf-8") as f:
        json.dump(all_videos, f, indent=2, ensure_ascii=False)
    print(f"\n[Done] Successfully saved {len(all_videos)} dossiers into videos.json")

if __name__ == "__main__":
    fetch_videos_via_api()
