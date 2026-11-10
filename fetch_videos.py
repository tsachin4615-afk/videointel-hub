import os
import json
import urllib.request
import xml.etree.ElementTree as ET
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Verified feeds for current affairs, exam prep, and geopolitical intelligence
FEEDS = [
    {
        "name": "WION",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC_gUM8rL-Lrg6O3adPW9K1g"
    },
    {
        "name": "StudyIQ IAS",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCrDxqG5pZ2H6jP5_F4e9QvA"
    },
    {
        "name": "World Affairs",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCP4W9sL5Kvd4Gv9a9qWJ4lg"
    },
    {
        "name": "Firstpost",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCz8QaiQxApLq8sLNcszYyJw"
    },
    {
        "name": "Sansad TV",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCV0UqW3hV9W2jB5b6zQ_YgA"
    }
]

def analyze_with_gemini(client, title, description, channel):
    if not client:
        return {
            "summary": description[:280] + "..." if description else "Analysis summary pending.",
            "takeaways": ["GEMINI_API_KEY not configured."],
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
      "summary": "2-3 concise sentences summarizing core strategic points.",
      "takeaways": [
        "Core policy or factual takeaway",
        "Geopolitical or strategic implication",
        "Exam-relevant pointer"
      ],
      "dossier": "### Strategic Background\\nDetailed context.\\n\\n### Key Developments\\nMajor points.\\n\\n### Strategic & Exam Implications\\nRelevance to policy and international relations."
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
            "takeaways": ["Analysis temporarily unavailable."],
            "dossier": f"### {title}\n\n{description}"
        }

def fetch_rss_videos():
    client = None
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            print("[Init] Gemini client initialized.")
        except Exception as e:
            print(f"[Init Error] {e}")

    all_videos = []

    for item in FEEDS:
        name = item["name"]
        url = item["url"]
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "yt": "http://www.youtube.com/xml/schemas/2015",
                "media": "http://search.yahoo.com/mrss/"
            }

            # Fetch top 2 updates per channel
            entries = root.findall("atom:entry", ns)[:2]
            print(f"[Channel] {name}: Successfully pulled {len(entries)} updates")

            for entry in entries:
                v_id = entry.find("yt:videoId", ns).text
                v_title = entry.find("atom:title", ns).text
                published = entry.find("atom:published", ns).text

                desc_elem = entry.find(".//media:description", ns)
                v_desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""

                print(f" -> Analyzing: {v_title[:45]}...")
                ai_intel = analyze_with_gemini(client, v_title, v_desc, name)

                all_videos.append({
                    "id": v_id,
                    "channel_title": name,
                    "title": v_title,
                    "published_at": published,
                    "thumbnail_url": f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg",
                    "executive_summary": ai_intel.get("summary", ""),
                    "key_takeaways": ai_intel.get("takeaways", []),
                    "deep_dossier_markdown": ai_intel.get("dossier", "")
                })
        except Exception as e:
            print(f"[Fetch Error] Channel '{name}': {e}")

    with open("videos.json", "w", encoding="utf-8") as f:
        json.dump(all_videos, f, indent=2, ensure_ascii=False)
    print(f"\n[Done] Successfully compiled {len(all_videos)} dossiers across channels into videos.json")

if __name__ == "__main__":
    fetch_rss_videos()
