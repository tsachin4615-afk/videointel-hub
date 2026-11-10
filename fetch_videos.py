import os
import json
import time
import re
import urllib.request
import urllib.parse
from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

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

def clean_json_response(text):
    text = text.strip()
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        return match.group(1)
    return text

def analyze_with_gemini(client, title, description, channel):
    if not client:
        return {
            "summary": description[:200] + "..." if description else "Summary pending.",
            "takeaways": ["GEMINI_API_KEY not found in environment."],
            "dossier": f"### {title}\n\n{description[:600]}"
        }

    prompt = f"""
You are a senior geopolitical intelligence and competitive exam current affairs analyst.
Analyze this video briefing:
Channel: {channel}
Title: {title}
Context / Description: {description[:1800]}

Provide your structured output strictly in valid JSON format with this exact structure:
{{
  "summary": "2 concise sentences explaining the central strategic or policy development.",
  "takeaways": [
    "Core policy, factual, or geopolitical takeaway",
    "Strategic, regional, or international implication",
    "High-yield competitive exam or governance pointer"
  ],
  "dossier": "### Strategic Overview\\nDetailed background context.\\n\\n### Key Developments\\nPoint-by-point breakdown.\\n\\n### Exam & Policy Takeaways\\nRelevant points for competitive examinations and policy analysis."
}}
Return only valid JSON. Do not include markdown code block quotes around it.
"""

    for model_name in ["gemini-2.0-flash", "gemini-1.5-flash"]:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                raw_text = clean_json_response(response.text)
                return json.loads(raw_text)
            except Exception as e:
                err_str = str(e)
                print(f"[Gemini Error on {model_name} (Attempt {attempt+1})] {title[:25]}: {err_str}")
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    time.sleep(6)
                else:
                    break

    return {
        "summary": description[:200] + "..." if description else "Analysis summary pending.",
        "takeaways": ["AI synthesis temporarily queued. Please check back."],
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
            print("[Init] Gemini client initialized successfully.")
        except Exception as e:
            print(f"[Init Error] Gemini: {e}")

    all_videos = []

    for ch in CHANNELS:
        name = ch["name"]
        print(f"\n[Channel] Querying {name} via YouTube API...")

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
            print(f" -> Found {len(items)} items for {name}")

            for item in items:
                v_id = item["id"]["videoId"]
                snippet = item["snippet"]
                v_title = snippet.get("title", "")
                v_desc = snippet.get("description", "")
                published = snippet.get("publishedAt", "")
                thumb = snippet.get("thumbnails", {}).get("high", {}).get("url", f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg")

                print(f"    Synthesizing intelligence: {v_title[:40]}...")
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

                # Pause 3.5 seconds between videos to stay safely below the Gemini RPM rate limit
                time.sleep(3.5)

        except Exception as e:
            print(f"[API Error] Failed fetching {name}: {e}")

    if all_videos:
        with open("videos.json", "w", encoding="utf-8") as f:
            json.dump(all_videos, f, indent=2, ensure_ascii=False)
        print(f"\n[Complete] Successfully generated {len(all_videos)} dossiers into videos.json")
    else:
        print("\n[Warning] No videos collected; keeping existing videos.json")

if __name__ == "__main__":
    fetch_all()
