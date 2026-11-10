import os
import json
import urllib.request
import xml.etree.ElementTree as ET
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Reliable, verified Indian & global current affairs RSS feeds
FEEDS = [
    {"name": "WION", "id": "UC_gUM8rL-Lrg6O3adPW9K1g"},
    {"name": "Firstpost", "id": "UCz8QaiQxApLq8sLNcszYyJw"},
    {"name": "DD India", "id": "UChLtXXcbWyF4b93b8L5g6CA"},
    {"name": "India Today", "id": "UCYPvAwZP8pZhSMW8qs7cVCw"},
    {"name": "NDTV", "id": "UCZFMm1mMw0F81Z37aaSuT_Q"},
    {"name": "Sansad TV", "id": "UC4L4WwF2j1zM1S6w27p1Qpg"}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def analyze_with_gemini(client, title, description, channel):
    if not client:
        return {
            "summary": description[:240] + "..." if description else "Summary pending.",
            "takeaways": ["GEMINI_API_KEY environment variable missing in workflow."],
            "dossier": f"### {title}\n\n{description}"
        }

    prompt = f"""
    You are a senior geopolitical intelligence analyst and competitive exam mentor.
    Synthesize an intelligence dossier for this report:
    Channel: {channel}
    Title: {title}
    Context: {description[:2000]}

    Respond strictly in valid JSON format:
    {{
      "summary": "2-3 concise sentences explaining the strategic development.",
      "takeaways": [
        "Core policy or factual update",
        "Strategic / geopolitical implication",
        "Key exam / governance relevance"
      ],
      "dossier": "### Strategic Overview\\nDetailed background.\\n\\n### Key Developments\\nPoint-by-point breakdown.\\n\\n### Exam & Policy Takeaways\\nRelevant insights for competitive exams and policy analysis."
    }}
    """

    # Try gemini-2.0-flash first, fallback to gemini-1.5-flash
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
        "summary": description[:240] + "..." if description else "Analysis unavailable.",
        "takeaways": ["Gemini API quota or authentication check required."],
        "dossier": f"### {title}\n\n{description}"
    }

def fetch_all():
    client = None
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            print("[Init] Gemini client initialized successfully.")
        except Exception as e:
            print(f"[Init Error] Could not initialize Gemini client: {e}")
    else:
        print("[Warning] GEMINI_API_KEY secret is not detected!")

    all_videos = []

    for item in FEEDS:
        name = item["name"]
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={item['id']}"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as res:
                xml_data = res.read()

            root = ET.fromstring(xml_data)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "yt": "http://www.youtube.com/xml/schemas/2015",
                "media": "http://search.yahoo.com/mrss/"
            }

            # Pull 4 videos per channel (4 x 4-6 channels = 16-24 dossiers)
            entries = root.findall("atom:entry", ns)[:4]
            print(f"[Channel] {name}: Retrieved {len(entries)} updates")

            for entry in entries:
                v_id = entry.find("yt:videoId", ns).text
                v_title = entry.find("atom:title", ns).text
                published = entry.find("atom:published", ns).text

                desc_elem = entry.find(".//media:description", ns)
                v_desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""

                print(f" -> Analyzing: {v_title[:40]}...")
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

    if all_videos:
        with open("videos.json", "w", encoding="utf-8") as f:
            json.dump(all_videos, f, indent=2, ensure_ascii=False)
        print(f"\n[Done] Successfully saved {len(all_videos)} dossiers into videos.json")
    else:
        print("\n[Error] No videos retrieved. videos.json unchanged.")

if __name__ == "__main__":
    fetch_all()
