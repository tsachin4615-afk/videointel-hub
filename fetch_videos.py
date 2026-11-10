import os
import sys
import time
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import requests
from dateutil import parser

API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()

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
# Capture everything from past 36 hours to ensure zero gap across rolling cycles
TIME_WINDOW_START = NOW_UTC - timedelta(hours=36)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# METHOD 1: Resolve Handle to Channel ID via Direct HTML Scraping (0 Quota Units)
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
            match3 = re.search(r'https://www.youtube.com/channel/([a-zA-Z0-9_-]{24})', res.text)
            if match3:
                return match3.group(1)
    except Exception as e:
        log(f"Scrape resolve failed for {handle}: {e}")
    return None

# METHOD 2: Resolve Handle via Official YouTube Data API (1 Quota Unit)
def resolve_channel_id_api(handle):
    if not API_KEY:
        return None
    clean_handle = handle.replace("@", "")
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {
        "part": "snippet,contentDetails",
        "forHandle": clean_handle,
        "key": API_KEY
    }
    try:
        res = SESSION.get(url, params=params, timeout=10).json()
        items = res.get("items", [])
        if items:
            return items[0]["id"]
    except Exception as e:
        log(f"API resolve failed for {handle}: {e}")
    return None

# METHOD 3: Fetch Channel Videos via RSS XML Endpoint (0 Quota Units)
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

# METHOD 4: Fetch Channel Videos via Playlist API (Uploads Playlist: UU...) (1 Quota Unit)
def fetch_videos_api_playlist(channel_id, handle):
    if not API_KEY:
        return []
    uploads_id = "UU" + channel_id[2:] if channel_id.startswith("UC") else channel_id
    url = "https://www.googleapis.com/youtube/v3/playlistItems"
    params = {
        "part": "snippet,contentDetails",
        "playlistId": uploads_id,
        "maxResults": 25,
        "key": API_KEY
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
        log(f"API playlist fetch error for {uploads_id}: {e}")
    return videos

def main():
    existing_videos = []
    if os.path.exists(FEED_FILE):
        try:
            with open(FEED_FILE, "r", encoding="utf-8") as f:
                existing_videos = json.load(f)
        except Exception:
            existing_videos = []

    feed_map = {v["id"]: v for v in existing_videos}
    log(f"Starting Intelligence Harvest. {len(feed_map)} existing records loaded.")

    for index, handle in enumerate(CHANNELS, start=1):
        log(f"[{index}/{len(CHANNELS)}] Processing {handle}...")
        
        # 1. Resolve Channel ID
        channel_id = resolve_channel_id_scraping(handle)
        if not channel_id:
            channel_id = resolve_channel_id_api(handle)

        if not channel_id:
            log(f"⚠️ Could not resolve channel ID for {handle}. Skipping gracefully.")
            continue

        # 2. Extract Videos (Try Free RSS first, then fallback to API)
        videos = fetch_videos_rss(channel_id, handle)
        if not videos and API_KEY:
            log(f"RSS empty or throttled for {handle}. Falling back to API playlist extraction.")
            videos = fetch_videos_api_playlist(channel_id, handle)

        # 3. Filter & Merge
        added_count = 0
        for vid in videos:
            try:
                dt = parser.parse(vid["published_at"])
                if dt >= TIME_WINDOW_START or vid["id"] not in feed_map:
                    feed_map[vid["id"]] = vid
                    added_count += 1
            except Exception:
                feed_map[vid["id"]] = vid

        log(f"Extracted {len(videos)} videos from {handle}. (Merged {added_count} records).")
        
        # Rate-limit safety spacing: 0.8s pause prevents IP/per-second API bursts
        time.sleep(0.8)

    sorted_feed = sorted(
        feed_map.values(),
        key=lambda x: parser.parse(x.get("published_at", "1970-01-01T00:00:00Z")),
        reverse=True
    )

    final_feed = sorted_feed[:300]

    with open(FEED_FILE, "w", encoding="utf-8") as f:
        json.dump(final_feed, f, indent=2, ensure_ascii=False)

    log(f"Feed updated successfully. Total active items in videos.json: {len(final_feed)}")

if __name__ == "__main__":
    main()
