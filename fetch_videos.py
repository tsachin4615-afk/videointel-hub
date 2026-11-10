import os
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Verified channel IDs for current affairs & exam preparation
CHANNELS = [
    {"name": "StudyIQ IAS", "id": "UCrDxqG5pZ2H6jP5_F4e9QvA"},
    {"name": "World Affairs", "id": "UC_wP3Y4zN7n3g5-wGq-5Q0A"},
    {"name": "WION", "id": "UC_gUM8rL-Lrg6O3adPW9K1g"},
    {"name": "DEF Talks by Aadi", "id": "UCu2P8V98w_VqP_g0E5q1z1g"},
    {"name": "Firstpost Vantage", "id": "UCz8QaiQxApLq8sLNcszYyJw"}
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

def fetch_rss_videos():
    client = None
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            print("[Init] Gemini client initialized successfully.")
        except Exception as e:
            print(f"[Init Error] Could not initialize Gemini client: {e}")
    else:
        print("[Warning] GEMINI_API_KEY secret is missing or empty.")

    all_videos = []

    for ch in CHANNELS:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['id']}"
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'yt': 'http://www.youtube.com/xml/schemas/2015',
                'media': 'http://search.yahoo.com/mrss/'
            }

            # Fetch top 3 videos per channel (3 videos x 5 channels = 15 total dossiers)
            entries = root.findall('atom:entry', ns)[:3]
            print(f"[Channel] {ch['name']}: Found {len(entries)} updates")

            for entry in entries:
                v_id = entry.find('yt:videoId', ns).text
                v_title = entry.find('atom:title', ns).text
                published = entry.find('atom:published', ns).text
                
                desc_elem = entry.find('.//media:description', ns)
                v_desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""
                
                print(f" -> Analyzing: {v_title[:45]}...")
                ai_intel = analyze_with_gemini(client, v_title, v_desc, ch['name'])

                all_videos.append({
                    "id": v_id,
                    "channel_title": ch['name'],
                    "title": v_title,
                    "published_at": published,
                    "thumbnail_url": f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg",
                    "executive_summary": ai_intel.get("summary", ""),
                    "key_takeaways": ai_intel.get("takeaways", []),
                    "deep_dossier_markdown": ai_intel.get("dossier", "")
                })
        except Exception as e:
            print(f"[Fetch Error] Channel '{ch['name']}': {e}")

    with open("videos.json", "w", encoding="utf-8") as f:
        json.dump(all_videos, f, indent=2, ensure_ascii=False)
    print(f"\n[Complete] Successfully generated {len(all_videos)} dossiers into videos.json")

if __name__ == "__main__":
    fetch_rss_videos()
