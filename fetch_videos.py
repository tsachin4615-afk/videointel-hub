import os
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

CHANNELS = [
    {"name": "StudyIQ IAS", "id": "UCrDxqG5pZ2H6jP5_F4e9QvA"},
    {"name": "World Affairs", "id": "UCCBs6hV2e9P_u_Dcx2hV25A"},
    {"name": "WION", "id": "UC_gUM8rL-Lrg6O3adPW9K1g"},
    {"name": "DEF Talks by Aadi", "id": "UC7uH7o5JcKeqHqjFjXbF9vA"}
]

def analyze_with_gemini(client, title, description, channel):
    if not client:
        return {
            "summary": description[:250] + "..." if description else "No summary available.",
            "takeaways": ["Analysis engine waiting for API key."],
            "dossier": f"### {title}\n\n{description}"
        }

    prompt = f"""
    You are an expert news analyst and competitive exam (UPSC/Current Affairs) tutor.
    Analyze this video update:
    Channel: {channel}
    Title: {title}
    Description/Transcript Context: {description[:2000]}

    Respond in valid JSON format with exactly these keys:
    {{
      "summary": "2-3 concise sentences summarizing core developments.",
      "takeaways": ["High-yield pointer 1", "High-yield pointer 2", "High-yield pointer 3"],
      "dossier": "A comprehensive markdown analysis covering Background, Key Entities, Exam/Policy Relevance, and Strategic Implications."
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
        print(f"Gemini processing error for {title}: {e}")
        return {
            "summary": description[:250] + "..." if description else "No summary available.",
            "takeaways": ["Analysis temporarily unavailable."],
            "dossier": f"### {title}\n\n{description}"
        }

def fetch_rss_videos():
    client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    all_videos = []

    for ch in CHANNELS:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['id']}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)
            ns = {'atom': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015', 'media': 'http://search.yahoo.com/mrss/'}

            # Fetch top 2 most recent videos per channel to stay fast and within free quota
            entries = root.findall('atom:entry', ns)[:2]
            for entry in entries:
                v_id = entry.find('yt:videoId', ns).text
                v_title = entry.find('atom:title', ns).text
                published = entry.find('atom:published', ns).text
                
                desc_elem = entry.find('.//media:description', ns)
                v_desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""
                
                print(f"Synthesizing intelligence for: {v_title}")
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
            print(f"Error fetching channel {ch['name']}: {e}")

    with open("videos.json", "w", encoding="utf-8") as f:
        json.dump(all_videos, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(all_videos)} dossiers into videos.json")

if __name__ == "__main__":
    fetch_rss_videos()
