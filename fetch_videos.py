import os
import re
import json
import urllib.request
import xml.etree.ElementTree as ET
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# The 10 requested intelligence & exam preparation channels
TARGET_CHANNELS = [
    {"name": "India Decoded", "handle": "@IndiaDecodedAA"},
    {"name": "World Affairs", "handle": "@WorldAffairsUnacademy"},
    {"name": "StudyIQ IAS", "handle": "@StudyIQEducationLtd"},
    {"name": "Coffee With Sumeet Jain", "handle": "@coffeewithsumeetjain"},
    {"name": "India Global Review", "handle": "@IndiaGlobalReview"},
    {"name": "Times Axis", "handle": "@TimesAxis"},
    {"name": "Parcham Classes", "handle": "@ParchamClasses"},
    {"name": "Unacademy UPSC Prep", "handle": "@unacademyupscprep"},
    {"name": "Adda247", "handle": "@adda247"},
    {"name": "AffairsCloud", "handle": "@AffairsCloud-Com"}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def resolve_channel_id(handle: str) -> str:
    """Dynamically resolves any @handle into its canonical UC... channel ID."""
    try:
        url = f"https://www.youtube.com/{handle}"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
        # Match channelId in meta tags or initial data
        match = re.search(r'itemprop="channelId"\s+content="([^"]+)"', html)
        if match:
            return match.group(1)
        match_alt = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"', html)
        if match_alt:
            return match_alt.group(1)
    except Exception as e:
        print(f"[Resolver Warning] Could not resolve ID for {handle}: {e}")
    return None

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

def fetch_all_channels():
    client = None
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            print("[Init] Gemini client initialized.")
        except Exception as e:
            print(f"[Init Error] Gemini: {e}")

    all_videos = []

    for target in TARGET_CHANNELS:
        name = target["name"]
        handle = target["handle"]
        print(f"\n[Channel] Resolving {name} ({handle})...")
        channel_id = resolve_channel_id(handle)

        if not channel_id:
            print(f"[Fetch Error] Skipping {name}: channel ID could not be resolved.")
            continue

        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            req = urllib.request.Request(rss_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "yt": "http://www.youtube.com/xml/schemas/2015",
                "media": "http://search.yahoo.com/mrss/"
            }

            # Fetch top 2 updates per channel to compile up to 20 dossiers per run
            entries = root.findall("atom:entry", ns)[:2]
            print(f" -> Found {len(entries)} updates for {name}")

            for entry in entries:
                v_id = entry.find("yt:videoId", ns).text
                v_title = entry.find("atom:title", ns).text
                published = entry.find("atom:published", ns).text

                desc_elem = entry.find(".//media:description", ns)
                v_desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""

                print(f"    Synthesizing: {v_title[:45]}...")
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
    print(f"\n[Done] Successfully saved {len(all_videos)} dossiers across all channels into videos.json")

if __name__ == "__main__":
    fetch_all_channels()
