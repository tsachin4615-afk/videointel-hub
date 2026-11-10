import os
import sys
import time
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import requests
from dateutil import parser

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Master YouTube Intelligence & Monitoring Roster (25 Channels)
CHANNELS = [
    "@IndiaDecodedAA",
    "@WorldAffairsUnacademy",
    "@StudyIQIAS",
    "@coffeewithsumeetjain",
    "@IndiaGlobalReview",
    "@TimesAxis",
    "@LetsCrackUPSCCSE",
    "@Adda247Bankers",
    "@ParchamClasses",
    "@AffairsCloud",
    "@alpha_defense",
    "@DefenceDecode",
    "@GareebScientist",
    "@NEXTIAS",
    "@DrishtiIASEnglish",
    "@SleepyClassesIAS",
    "@amitsengupta01",
    "@TheChanakyaDialoguesHindi",
    "@StratNewsGlobal",
    "@ThirdEyekannada",
    "@rajshamani",
    "@inconnectnews",
    "@NarendraModi",
    "@ReVIEWbySoukhyaGaonkar",
    "@MasthMagaa"
]

FEED_FILE = "videos.json"
NOW_UTC = datetime.now(timezone.utc)
TIME_WINDOW_START = NOW_UTC - timedelta(hours=36)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def resolve_channel_id_scraping(handle):
    clean_handle = handle if handle.startswith("@") else f"@{handle}"
    url = f"https://www.youtube.com/{clean_handle}"
    try:
        res = SESSION.get(url, timeout=10)
        if res.status_code == 200:
            import re
            match = re.search(r'itemprop="channelId"\s+content="([a-zA-Z0-9_-]{24})"', res.text)
            if match:
                return match.group(1)
            match2 = re.search(r'"channelId":"([a-zA-Z0-9_-]{24})"', res.text)
            if match2:
                return match2.group(1)
    except Exception as e:
        log(f"Scrape resolve failed for {handle}: {e}")
    return None

def resolve_channel_id_api(handle):
    if not YOUTUBE_API_KEY:
        return None
    clean_handle = handle.replace("@", "")
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {
        "part": "snippet,contentDetails",
        "forHandle": clean_handle,
        "key": YOUTUBE_API_KEY
    }
    try:
        res = SESSION.get(url, params=params, timeout=10).json()
        items = res.get("items", [])
        if items:
            return items[0]["id"]
    except Exception as e:
        log(f"API resolve failed for {handle}: {e}")
    return None

def fetch_videos_rss(channel_id, handle):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    videos = []
    try:
        res = SESSION.get(url, timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'yt': 'http://www.youtube.com/xml/schemas/2015',
                'media': 'http://search.yahoo.com/mrss/'
            }
            channel_title = root.find('atom:title', ns)
            ch_name = channel_title.text if channel_title is not None else handle

            for entry in root.findall('atom:entry', ns):
                v_id = entry.find('yt:videoId', ns)
                title = entry.find('atom:title', ns)
                pub = entry.find('atom:published', ns)
                media_group = entry.find('media:group', ns)
                desc = ""
                thumb = ""
                if media_group is not None:
                    desc_el = media_group.find('media:description', ns)
                    if desc_el is not None:
                        desc = desc_el.text or ""
                    thumb_el = media_group.find('media:thumbnail', ns)
                    if thumb_el is not None:
                        thumb = thumb_el.attrib.get('url', '')

                if v_id is not None and title is not None and pub is not None:
                    pub_dt = parser.parse(pub.text)
                    videos.append({
                        "id": v_id.text,
                        "title": title.text,
                        "channel_title": ch_name,
                        "handle": handle,
                        "published_at": pub_dt.isoformat(),
                        "description": desc.strip(),
                        "thumbnail_url": thumb or f"https://i.ytimg.com/vi/{v_id.text}/hqdefault.jpg"
                    })
    except Exception as e:
        log(f"RSS fetch error for {channel_id}: {e}")
    return videos

def fetch_videos_api_playlist(channel_id, handle):
    if not YOUTUBE_API_KEY:
        return []
    uploads_id = "UU" + channel_id[2:] if channel_id.startswith("UC") else channel_id
    url = "https://www.googleapis.com/youtube/v3/playlistItems"
    params = {
        "part": "snippet,contentDetails",
        "playlistId": uploads_id,
        "maxResults": 25,
        "key": YOUTUBE_API_KEY
    }
    videos = []
    try:
        res = SESSION.get(url, params=params, timeout=10).json()
        for item in res.get("items", []):
            snip = item.get("snippet", {})
            v_id = snip.get("resourceId", {}).get("videoId")
            if not v_id:
                continue
            pub_str = snip.get("publishedAt")
            videos.append({
                "id": v_id,
                "title": snip.get("title", ""),
                "channel_title": snip.get("channelTitle", handle),
                "handle": handle,
                "published_at": pub_str,
                "description": snip.get("description", ""),
                "thumbnail_url": snip.get("thumbnails", {}).get("high", {}).get("url") or f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg"
            })
    except Exception as e:
        log(f"API playlist error for {uploads_id}: {e}")
    return videos

# BACKEND GEMINI SUMMARIZER WITH CASCADE
def generate_layman_summary(title, description, channel_title):
    if not GEMINI_API_KEY:
        return None

    prompt = f"""Rewrite this video event as a simple, engaging news story for a regular person:
Format exactly like this:
## [Catchy Clear News Headline]
**The Story in Brief:** 2-3 short, clear sentences explaining what just happened in simple everyday words (no complex political or technical jargon).
**Why It Matters to You:** 1-2 simple sentences explaining the real-world impact on everyday citizens or the general public.

Video Title: "{title}"
Channel: "{channel_title}"
Context / Description: {description[:1800]}"""

    models = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
            data = res.json()
            if "candidates" in data and len(data["candidates"]) > 0:
                parts = data["candidates"][0].get("content", {}).get("parts", [])
                if parts and "text" in parts[0]:
                    return parts[0]["text"].strip()
        except Exception as e:
            continue
    return None

def save_feed(feed_map):
    sorted_feed = sorted(
        feed_map.values(),
        key=lambda x: parser.parse(x.get("published_at", "1970-01-01T00:00:00Z")),
        reverse=True
    )
    with open(FEED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted_feed[:300], f, indent=2, ensure_ascii=False)

def main():
    existing_videos = []
    if os.path.exists(FEED_FILE):
        try:
            with open(FEED_FILE, "r", encoding="utf-8") as f:
                existing_videos = json.load(f)
        except Exception:
            existing_videos = []

    feed_map = {v["id"]: v for v in existing_videos}
    log(f"Feed loaded. Total existing records: {len(feed_map)}")

    newly_added_count = 0
    summarized_count = 0

    for index, handle in enumerate(CHANNELS, start=1):
        log(f"[{index}/{len(CHANNELS)}] Inspecting {handle}...")
        
        channel_id = resolve_channel_id_scraping(handle)
        if not channel_id:
            channel_id = resolve_channel_id_api(handle)

        if not channel_id:
            log(f"⚠️ Channel ID not resolved for {handle}. Skipping.")
            continue

        videos = fetch_videos_rss(channel_id, handle)
        if not videos and YOUTUBE_API_KEY:
            videos = fetch_videos_api_playlist(channel_id, handle)

        for vid in videos:
            v_id = vid["id"]
            try:
                dt = parser.parse(vid["published_at"])
                is_fresh = dt >= TIME_WINDOW_START
            except Exception:
                is_fresh = True

            # If brand new video or missing layman news in existing video
            if v_id not in feed_map:
                feed_map[v_id] = vid
                newly_added_count += 1
            else:
                # Update basic info but preserve existing summary
                for k in ["title", "description", "thumbnail_url"]:
                    if k in vid:
                        feed_map[v_id][k] = vid[k]

            # PREPARE LAYMAN SUMMARY ONE-BY-ONE IF MISSING
            if is_fresh and not feed_map[v_id].get("layman_news"):
                log(f"--> Generating Layman summary for: {vid['title'][:45]}...")
                summary = generate_layman_summary(vid["title"], vid.get("description", ""), vid.get("channel_title", ""))
                if summary:
                    feed_map[v_id]["layman_news"] = summary
                    summarized_count += 1
                    # Save immediately so progress is preserved
                    save_feed(feed_map)
                    # Safe spacing between Gemini AI calls to stay under rate limits
                    time.sleep(3.5)

        time.sleep(0.8)

    save_feed(feed_map)
    log(f"Complete. New videos added: {newly_added_count}, Summaries pre-compiled: {summarized_count}")

if __name__ == "__main__":
    main()
