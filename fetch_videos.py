import os
import sys
import time
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import requests
from dateutil import parser

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Master YouTube Intelligence & Monitoring Roster (Includes @deftalksbyaadi & @IndiaDecodedAA)
CHANNELS = [
    "@deftalksbyaadi",
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
CYCLES_FILE = "cycles.json"
NOW_UTC = datetime.now(timezone.utc)
TIME_WINDOW_START = NOW_UTC - timedelta(hours=36)
CYCLE_WINDOW_START = NOW_UTC - timedelta(hours=2, minutes=20)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
})

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ==============================================================================
# TIERED CHANNEL ID RESOLVER (3 CASCADE LEVELS)
# ==============================================================================
def resolve_channel_id(handle):
    clean_handle = handle if handle.startswith("@") else f"@{handle}"
    
    # Cascade 1: Direct Web HTML Scrape
    url = f"https://www.youtube.com/{clean_handle}"
    try:
        res = SESSION.get(url, timeout=12)
        if res.status_code == 200:
            match = re.search(r'itemprop="channelId"\s+content="([a-zA-Z0-9_-]{24})"', res.text)
            if match:
                return match.group(1)
            match2 = re.search(r'"channelId":"([a-zA-Z0-9_-]{24})"', res.text)
            if match2:
                return match2.group(1)
            match3 = re.search(r'"externalId":"([a-zA-Z0-9_-]{24})"', res.text)
            if match3:
                return match3.group(1)
    except Exception as e:
        log(f"Resolve Tier 1 (HTML Scrape) error for {handle}: {e}")

    # Cascade 2: YouTube Data API by Handle
    if YOUTUBE_API_KEY:
        try:
            api_url = "https://www.googleapis.com/youtube/v3/channels"
            params = {
                "part": "snippet,contentDetails",
                "forHandle": clean_handle.replace("@", ""),
                "key": YOUTUBE_API_KEY
            }
            res = SESSION.get(api_url, params=params, timeout=10).json()
            items = res.get("items", [])
            if items:
                return items[0]["id"]
        except Exception as e:
            log(f"Resolve Tier 2 (API Handle) error for {handle}: {e}")

    # Cascade 3: YouTube Data API Search Query Fallback
    if YOUTUBE_API_KEY:
        try:
            search_url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "snippet",
                "q": clean_handle,
                "type": "channel",
                "maxResults": 1,
                "key": YOUTUBE_API_KEY
            }
            res = SESSION.get(search_url, params=params, timeout=10).json()
            items = res.get("items", [])
            if items:
                return items[0]["snippet"]["channelId"]
        except Exception as e:
            log(f"Resolve Tier 3 (API Search) error for {handle}: {e}")

    return None

# ==============================================================================
# MULTI-METHOD VIDEO FETCHING ENGINES
# ==============================================================================

# Method 1: YouTube XML RSS Feed
def fetch_via_rss(channel_id, handle):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    videos = []
    res = SESSION.get(url, timeout=10)
    if res.status_code == 200:
        root = ET.fromstring(res.content)
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'yt': 'http://www.youtube.com/xml/schemas/2015',
            'media': 'http://search.yahoo.com/mrss/'
        }
        channel_title_el = root.find('atom:title', ns)
        ch_name = channel_title_el.text if channel_title_el is not None else handle

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
                    "title": title.text.strip(),
                    "channel_title": ch_name,
                    "handle": handle,
                    "published_at": pub_dt.isoformat(),
                    "description": desc.strip(),
                    "thumbnail_url": thumb or f"https://i.ytimg.com/vi/{v_id.text}/hqdefault.jpg"
                })
    return videos

# Method 2: YouTube API Uploads Playlist (UU...)
def fetch_via_api_playlist(channel_id, handle):
    if not YOUTUBE_API_KEY:
        return []
    uploads_id = "UU" + channel_id[2:] if channel_id.startswith("UC") else channel_id
    url = "https://www.googleapis.com/youtube/v3/playlistItems"
    params = {
        "part": "snippet,contentDetails",
        "playlistId": uploads_id,
        "maxResults": 20,
        "key": YOUTUBE_API_KEY
    }
    videos = []
    res = SESSION.get(url, params=params, timeout=10).json()
    for item in res.get("items", []):
        snip = item.get("snippet", {})
        v_id = snip.get("resourceId", {}).get("videoId")
        if not v_id:
            continue
        videos.append({
            "id": v_id,
            "title": snip.get("title", "").strip(),
            "channel_title": snip.get("channelTitle", handle),
            "handle": handle,
            "published_at": snip.get("publishedAt"),
            "description": snip.get("description", "").strip(),
            "thumbnail_url": snip.get("thumbnails", {}).get("high", {}).get("url") or f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg"
        })
    return videos

# Method 3, 4 & 5: Web Scraping ytInitialData (/videos, /streams, /featured)
def fetch_via_web_initialdata(handle, tab="videos"):
    clean_handle = handle if handle.startswith("@") else f"@{handle}"
    url = f"https://www.youtube.com/{clean_handle}/{tab}"
    videos = []
    res = SESSION.get(url, timeout=12)
    if res.status_code != 200:
        return []

    match = re.search(r'var ytInitialData\s*=\s*({.+?});</script>', res.text)
    if not match:
        match = re.search(r'window\["ytInitialData"\]\s*=\s*({.+?});', res.text)
    if not match:
        return []

    try:
        data = json.loads(match.group(1))
        tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
        
        target_tab = None
        for t in tabs:
            tab_renderer = t.get("tabRenderer", {})
            if tab_renderer.get("selected"):
                target_tab = tab_renderer
                break
        
        if not target_tab and tabs:
            target_tab = tabs[0].get("tabRenderer", {})

        contents = (
            target_tab.get("content", {})
            .get("richGridRenderer", {})
            .get("contents", [])
        )

        for item in contents:
            rich_item = item.get("richItemRenderer", {}).get("content", {})
            v_rend = rich_item.get("videoRenderer", {})
            if not v_rend:
                continue

            v_id = v_rend.get("videoId")
            title_obj = v_rend.get("title", {})
            title = ""
            if "runs" in title_obj and title_obj["runs"]:
                title = title_obj["runs"][0].get("text", "")
            elif "simpleText" in title_obj:
                title = title_obj["simpleText"]

            if not v_id or not title:
                continue

            ch_name = handle
            owner = v_rend.get("ownerText", {}).get("runs", [])
            if owner:
                ch_name = owner[0].get("text", handle)

            desc = ""
            desc_snip = v_rend.get("descriptionSnippet", {}).get("runs", [])
            if desc_snip:
                desc = "".join(r.get("text", "") for r in desc_snip)

            videos.append({
                "id": v_id,
                "title": title.strip(),
                "channel_title": ch_name,
                "handle": handle,
                "published_at": NOW_UTC.isoformat(),
                "description": desc.strip(),
                "thumbnail_url": f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg"
            })
    except Exception as e:
        log(f"Web initialData error for {handle} tab [{tab}]: {e}")

    return videos

# Method 6: YouTube API Search
def fetch_via_api_search(channel_id, handle):
    if not YOUTUBE_API_KEY:
        return []
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "maxResults": 15,
        "order": "date",
        "type": "video",
        "key": YOUTUBE_API_KEY
    }
    videos = []
    res = SESSION.get(url, params=params, timeout=10).json()
    for item in res.get("items", []):
        v_id = item.get("id", {}).get("videoId")
        if not v_id:
            continue
        snip = item.get("snippet", {})
        videos.append({
            "id": v_id,
            "title": snip.get("title", "").strip(),
            "channel_title": snip.get("channelTitle", handle),
            "handle": handle,
            "published_at": snip.get("publishedAt"),
            "description": snip.get("description", "").strip(),
            "thumbnail_url": snip.get("thumbnails", {}).get("high", {}).get("url") or f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg"
        })
    return videos

# Resilient Cascade Orchestrator
def fetch_channel_videos_resilient(channel_id, handle):
    # 1. XML RSS
    if channel_id:
        try:
            vids = fetch_via_rss(channel_id, handle)
            if vids:
                return vids, "RSS"
        except Exception as e:
            log(f"Method 1 (RSS) failed for {handle}: {e}")

    # 2. API Playlist
    if channel_id and YOUTUBE_API_KEY:
        try:
            vids = fetch_via_api_playlist(channel_id, handle)
            if vids:
                return vids, "API_Playlist"
        except Exception as e:
            log(f"Method 2 (API Playlist) failed for {handle}: {e}")

    # 3. Web Scrape /videos
    try:
        vids = fetch_via_web_initialdata(handle, tab="videos")
        if vids:
            return vids, "Web_Scrape_Videos"
    except Exception as e:
        log(f"Method 3 (Web Videos) failed for {handle}: {e}")

    # 4. Web Scrape /streams (Live Streams)
    try:
        vids = fetch_via_web_initialdata(handle, tab="streams")
        if vids:
            return vids, "Web_Scrape_Streams"
    except Exception as e:
        log(f"Method 4 (Web Streams) failed for {handle}: {e}")

    # 5. Web Scrape /featured
    try:
        vids = fetch_via_web_initialdata(handle, tab="featured")
        if vids:
            return vids, "Web_Scrape_Featured"
    except Exception as e:
        log(f"Method 5 (Web Featured) failed for {handle}: {e}")

    # 6. API Search
    if channel_id and YOUTUBE_API_KEY:
        try:
            vids = fetch_via_api_search(channel_id, handle)
            if vids:
                return vids, "API_Search"
        except Exception as e:
            log(f"Method 6 (API Search) failed for {handle}: {e}")

    return [], "None"

# ==============================================================================
# AI SUMMARIZATION (PRIORITIZING GEMINI 4 ARGON)
# ==============================================================================
def generate_layman_summary(title, description, channel_title):
    if not GEMINI_API_KEY:
        return None

    prompt = f"""Rewrite this video event as a simple, engaging news story for a regular person:
Format exactly like this:
## [Catchy Clear News Headline]
**The Story in Brief:** 2-3 short, clear sentences explaining what just happened in simple everyday words.
**Why It Matters to You:** 1-2 simple sentences explaining the real-world impact on everyday citizens.

Video Title: "{title}"
Channel: "{channel_title}"
Context / Description: {description[:1800]}"""

    # Argon model prioritised first
    models = ["gemini-4-argon", "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
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
        except Exception:
            continue
    return None

def normalize_keywords(text):
    stop = {"the", "a", "an", "in", "to", "for", "of", "and", "on", "with", "by", "is", "at", 
            "from", "video", "news", "breaking", "update", "explained", "full", "analysis", 
            "why", "how", "what", "watch", "live", "about", "this", "that", "over", "into"}
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', text.lower())
    return set(w for w in cleaned.split() if len(w) > 2 and w not in stop)

# ==============================================================================
# SMART DYNAMIC FEED ALLOCATOR (300 CAP WITH TOPIC PURGE)
# ==============================================================================
def build_smart_deduplicated_feed(feed_map):
    """
    If enough fresh and unique topics exist, prunes duplicate coverage from other channels
    to keep only unique stories. If fresh topics are insufficient to reach 300 items,
    retains secondary coverage at the bottom so the dashboard stays full.
    """
    all_vids = list(feed_map.values())
    all_vids.sort(key=lambda x: parser.parse(x.get("published_at", "1970-01-01T00:00:00Z")), reverse=True)

    topic_clusters = []
    
    for vid in all_vids:
        words = normalize_keywords(vid.get("title", ""))
        matched_cluster = None

        for cluster in topic_clusters:
            overlap = len(words.intersection(cluster["words"]))
            if overlap >= 3 or (overlap >= 2 and len(words) <= 4):
                matched_cluster = cluster
                break

        if matched_cluster:
            matched_cluster["videos"].append(vid)
        else:
            topic_clusters.append({
                "words": words,
                "videos": [vid]
            })

    unique_primary_videos = []
    secondary_duplicate_videos = []

    for cluster in topic_clusters:
        # Sort cluster videos by presence of Layman news, description length, and freshness
        sorted_cluster = sorted(
            cluster["videos"],
            key=lambda v: (
                1 if v.get("layman_news") else 0,
                len(v.get("description", "")),
                v.get("published_at", "")
            ),
            reverse=True
        )
        unique_primary_videos.append(sorted_cluster[0])
        for extra in sorted_cluster[1:]:
            extra["is_duplicate_topic"] = True
            secondary_duplicate_videos.append(extra)

    # If unique stories alone fill up to 300, discard duplicates entirely
    if len(unique_primary_videos) >= 300:
        return unique_primary_videos[:300]

    # Otherwise, fill the remainder with secondary coverage so dashboard has 300 news
    remaining_slots = 300 - len(unique_primary_videos)
    combined = unique_primary_videos + secondary_duplicate_videos[:remaining_slots]
    return combined

def save_feed(feed_list):
    sorted_feed = sorted(
        feed_list,
        key=lambda x: parser.parse(x.get("published_at", "1970-01-01T00:00:00Z")),
        reverse=True
    )
    with open(FEED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted_feed[:300], f, indent=2, ensure_ascii=False)

def log_cycle_data(cycle_channels_data, total_new_in_cycle):
    cycles_history = []
    if os.path.exists(CYCLES_FILE):
        try:
            with open(CYCLES_FILE, "r", encoding="utf-8") as f:
                cycles_history = json.load(f)
        except Exception:
            cycles_history = []

    current_cycle_record = {
        "timestamp": NOW_UTC.isoformat(),
        "total_new_videos": total_new_in_cycle,
        "active_channels_count": len(cycle_channels_data),
        "channels": cycle_channels_data
    }

    updated_history = [current_cycle_record] + cycles_history[:5]
    with open(CYCLES_FILE, "w", encoding="utf-8") as f:
        json.dump(updated_history, f, indent=2, ensure_ascii=False)
    log(f"Cycle recorded. Channels active: {len(cycle_channels_data)}")

# ==============================================================================
# MAIN ISOLATED EXECUTION CONTROLLER
# ==============================================================================
def main():
    existing_videos = []
    if os.path.exists(FEED_FILE):
        try:
            with open(FEED_FILE, "r", encoding="utf-8") as f:
                existing_videos = json.load(f)
        except Exception:
            existing_videos = []

    feed_map = {v["id"]: v for v in existing_videos}
    log(f"Existing records loaded: {len(feed_map)}")

    cycle_channel_map = {}
    total_cycle_videos = 0

    for index, handle in enumerate(CHANNELS, start=1):
        # ISOLATION BARRIER: One channel's network error will never stop others
        try:
            log(f"[{index}/{len(CHANNELS)}] Inspecting {handle}...")
            channel_id = resolve_channel_id(handle)
            
            videos, method_used = fetch_channel_videos_resilient(channel_id, handle)
            log(f"--> {handle}: Fetched {len(videos)} videos via [{method_used}]")

            for vid in videos:
                v_id = vid["id"]
                try:
                    dt = parser.parse(vid["published_at"])
                    is_fresh_36h = dt >= TIME_WINDOW_START
                    is_in_current_2h_cycle = dt >= CYCLE_WINDOW_START or (v_id not in feed_map)
                except Exception:
                    is_fresh_36h = True
                    is_in_current_2h_cycle = False

                if is_in_current_2h_cycle:
                    ch_title = vid.get("channel_title", handle)
                    if ch_title not in cycle_channel_map:
                        cycle_channel_map[ch_title] = {
                            "channel_name": ch_title,
                            "handle": handle,
                            "video_count": 0,
                            "topics": []
                        }
                    if vid["title"] not in cycle_channel_map[ch_title]["topics"]:
                        cycle_channel_map[ch_title]["video_count"] += 1
                        cycle_channel_map[ch_title]["topics"].append(vid["title"])
                        total_cycle_videos += 1

                if v_id not in feed_map:
                    feed_map[v_id] = vid
                else:
                    for k in ["title", "description", "thumbnail_url"]:
                        if k in vid and vid[k]:
                            feed_map[v_id][k] = vid[k]

                # Layman Summary Generation via Gemini 4 Argon
                if is_fresh_36h and not feed_map[v_id].get("layman_news"):
                    log(f"--> Summarizing with Argon: {vid['title'][:40]}...")
                    summary = generate_layman_summary(vid["title"], vid.get("description", ""), vid.get("channel_title", ""))
                    if summary:
                        feed_map[v_id]["layman_news"] = summary
                        time.sleep(3.5)

            time.sleep(0.8)

        except Exception as channel_err:
            log(f"⚠️ Channel {handle} bypassed due to exception: {channel_err}. Proceeding.")
            continue

    smart_feed = build_smart_deduplicated_feed(feed_map)
    save_feed(smart_feed)
    log_cycle_data(list(cycle_channel_map.values()), total_cycle_videos)
    log(f"Run completed. Active items in feed: {len(smart_feed)}")

if __name__ == "__main__":
    main()
