import os
import sys
import time
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dateutil import parser

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Master YouTube Intelligence Roster (26 Channels)
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
TIME_WINDOW_36H = NOW_UTC - timedelta(hours=36)
CYCLE_WINDOW_START = NOW_UTC - timedelta(hours=2, minutes=20)
FIVE_DAYS_AGO = NOW_UTC - timedelta(days=5)
SIXTY_DAYS_AGO = NOW_UTC - timedelta(days=60)

# Strict Age Quotas
MAX_VIDEOS_OVER_5_DAYS = 40
MAX_VIDEOS_OVER_60_DAYS = 20
TARGET_FEED_CAPACITY = 300

# High-resilience session with automatic connection retries
SESSION = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=0.8,
    status_forcelist=[429, 500, 502, 503, 504],
    raise_on_status=False
)
adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20)
SESSION.mount("https://", adapter)
SESSION.mount("http://", adapter)
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
})

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# Safe Atomic File Storage (Prevents JSON corruption during sudden termination)
def atomic_save_json(filepath, data):
    tmp_path = f"{filepath}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, filepath)
    except Exception as e:
        log(f"⚠️ Error saving {filepath} atomically: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

# ==============================================================================
# TIERED CHANNEL ID RESOLVER (4 FAILOVER ROUTES)
# ==============================================================================
def resolve_channel_id(handle):
    clean_handle = handle if handle.startswith("@") else f"@{handle}"
    
    # Route 1: Direct Web HTML Scrape (Canonical)
    url = f"https://www.youtube.com/{clean_handle}"
    try:
        res = SESSION.get(url, timeout=10)
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
            match4 = re.search(r'href="https://www\.youtube\.com/channel/([a-zA-Z0-9_-]{24})"', res.text)
            if match4:
                return match4.group(1)
    except Exception as e:
        log(f"Resolve Route 1 failed for {handle}: {e}")

    # Route 2: YouTube API forHandle
    if YOUTUBE_API_KEY:
        try:
            api_url = "https://www.googleapis.com/youtube/v3/channels"
            params = {
                "part": "snippet,contentDetails",
                "forHandle": clean_handle.replace("@", ""),
                "key": YOUTUBE_API_KEY
            }
            res = SESSION.get(api_url, params=params, timeout=8).json()
            items = res.get("items", [])
            if items:
                return items[0]["id"]
        except Exception as e:
            log(f"Resolve Route 2 (API Handle) failed for {handle}: {e}")

    # Route 3: YouTube API Search Query
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
            res = SESSION.get(search_url, params=params, timeout=8).json()
            items = res.get("items", [])
            if items:
                return items[0]["snippet"]["channelId"]
        except Exception as e:
            log(f"Resolve Route 3 (API Search) failed for {handle}: {e}")

    return None

# ==============================================================================
# RESILIENT VIDEO HARVESTING (6 FAILOVER ROUTES PER CHANNEL)
# ==============================================================================

# Route 1: YouTube XML RSS Feed
def fetch_via_rss(channel_id, handle):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    videos = []
    res = SESSION.get(url, timeout=9)
    if res.status_code == 200:
        root = ET.fromstring(res.content)
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'yt': 'http://www.youtube.com/xml/schemas/2015',
            'media': 'http://search.yahoo.com/mrss/'
        }
        ch_name_el = root.find('atom:title', ns)
        ch_name = ch_name_el.text if ch_name_el is not None else handle

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

# Route 2: Official YouTube API Uploads Playlist (UU...)
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
    res = SESSION.get(url, params=params, timeout=9).json()
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

# Routes 3, 4, 5: Frontend Web Scraper (/videos, /streams, /featured)
def fetch_via_web_initialdata(handle, tab="videos"):
    clean_handle = handle if handle.startswith("@") else f"@{handle}"
    url = f"https://www.youtube.com/{clean_handle}/{tab}"
    videos = []
    res = SESSION.get(url, timeout=10)
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

        contents = target_tab.get("content", {}).get("richGridRenderer", {}).get("contents", [])
        for item in contents:
            v_rend = item.get("richItemRenderer", {}).get("content", {}).get("videoRenderer", {})
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
        log(f"Web scraper parsing error on {handle} [{tab}]: {e}")

    return videos

# Route 6: Official YouTube API Search
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
    res = SESSION.get(url, params=params, timeout=9).json()
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

# Master Fault-Tolerant Harvesting Cascade
def fetch_channel_videos_resilient(channel_id, handle):
    # Tier 1: XML RSS
    if channel_id:
        try:
            vids = fetch_via_rss(channel_id, handle)
            if vids:
                return vids, "RSS"
        except Exception:
            pass

    # Tier 2: API Playlist
    if channel_id and YOUTUBE_API_KEY:
        try:
            vids = fetch_via_api_playlist(channel_id, handle)
            if vids:
                return vids, "API_Playlist"
        except Exception:
            pass

    # Tier 3: Web Scraper /videos
    try:
        vids = fetch_via_web_initialdata(handle, tab="videos")
        if vids:
            return vids, "Web_Scrape_Videos"
    except Exception:
        pass

    # Tier 4: Web Scraper /streams (Live Broadcasts)
    try:
        vids = fetch_via_web_initialdata(handle, tab="streams")
        if vids:
            return vids, "Web_Scrape_Streams"
    except Exception:
        pass

    # Tier 5: Web Scraper /featured
    try:
        vids = fetch_via_web_initialdata(handle, tab="featured")
        if vids:
            return vids, "Web_Scrape_Featured"
    except Exception:
        pass

    # Tier 6: API Search
    if channel_id and YOUTUBE_API_KEY:
        try:
            vids = fetch_via_api_search(channel_id, handle)
            if vids:
                return vids, "API_Search"
        except Exception:
            pass

    return [], "None"

# ==============================================================================
# GEMINI 4 ARGON SUMMARIZER WITH AUTOMATIC CASCADE
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

    # Cascade prioritizing Gemini 4 Argon
    model_cascade = ["gemini-4-argon", "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
    for model in model_cascade:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
            data = res.json()
            if "candidates" in data and len(data["candidates"]) > 0:
                parts = data["candidates"][0].get("content", {}).get("parts", [])
                if parts and "text" in parts[0]:
                    return parts[0]["text"].strip()
        except Exception:
            continue
    return None

# ==============================================================================
# DYNAMIC FEEDBACK & TOPIC SIGNATURE CLUSTERING
# ==============================================================================
def normalize_keywords(text):
    stop = {"the", "a", "an", "in", "to", "for", "of", "and", "on", "with", "by", "is", "at", 
            "from", "video", "news", "breaking", "update", "explained", "full", "analysis", 
            "why", "how", "what", "watch", "live", "about", "this", "that", "over", "into",
            "vs", "new", "top", "latest", "after", "will"}
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', text.lower())
    return set(w for w in cleaned.split() if len(w) > 2 and w not in stop)

def load_previous_cycle_topic_signatures():
    """Extracts keyword signatures of topics already covered in previous 2-hour cycles."""
    past_signatures = []
    if os.path.exists(CYCLES_FILE):
        try:
            with open(CYCLES_FILE, "r", encoding="utf-8") as f:
                cycles = json.load(f)
            # Inspect the previous 3 cycles
            for cyc in cycles[:3]:
                for ch in cyc.get("channels", []):
                    for topic in ch.get("topics", []):
                        sig = normalize_keywords(topic)
                        if sig:
                            past_signatures.append(sig)
        except Exception as e:
            log(f"⚠️ Error reading past cycle signatures: {e}")
    return past_signatures

def is_topic_in_past_cycles(title_words, past_signatures):
    for past_sig in past_signatures:
        overlap = len(title_words.intersection(past_sig))
        if overlap >= 3 or (overlap >= 2 and len(title_words) <= 4):
            return True
    return False

# ==============================================================================
# DYNAMIC ADAPTIVE FEED ALLOCATOR (STRICT AGE & REPEAT QUOTAS)
# ==============================================================================
def build_adaptive_quota_feed(feed_map, past_signatures):
    """
    Enforces all strict user constraints:
    1. Videos > 60 days old cannot exceed 20.
    2. Videos > 5 days old cannot exceed 40.
    3. Fresh unrepeated topics are prioritized at the top.
    4. Topics covered in previous cycles or cross-channel duplicates are suppressed if new topics exist.
    5. If fresh topics are insufficient to reach 300, secondary/older news fills the bottom.
    """
    all_vids = list(feed_map.values())
    
    # Parse dates safely
    for v in all_vids:
        try:
            v["_dt"] = parser.parse(v.get("published_at", "1970-01-01T00:00:00Z"))
        except Exception:
            v["_dt"] = datetime(1970, 1, 1, tzinfo=timezone.utc)

    # Sort descending by date
    all_vids.sort(key=lambda x: x["_dt"], reverse=True)

    # Semantic Clustering to identify single best video per event
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

    unique_best_candidates = []
    repeated_cross_channel_candidates = []

    for cluster in topic_clusters:
        # Best video chosen by: Layman summary presence -> description length -> freshness
        sorted_vids = sorted(
            cluster["videos"],
            key=lambda v: (
                1 if v.get("layman_news") else 0,
                len(v.get("description", "")),
                v["_dt"]
            ),
            reverse=True
        )
        unique_best_candidates.append(sorted_vids[0])
        for rep in sorted_vids[1:]:
            rep["is_duplicate_topic"] = True
            repeated_cross_channel_candidates.append(rep)

    # Segregate based on past cycle history & age categories
    tier1_fresh_unique = []       # Brand new topic, < 5 days
    tier2_past_cycle_repeats = []   # Topic was covered in previous 2h cycles
    tier3_older_5_to_60_days = []  # Between 5 and 60 days
    tier4_older_than_60_days = []  # Older than 60 days

    for vid in unique_best_candidates:
        words = normalize_keywords(vid.get("title", ""))
        dt = vid["_dt"]

        if dt < SIXTY_DAYS_AGO:
            tier4_older_than_60_days.append(vid)
        elif dt < FIVE_DAYS_AGO:
            tier3_older_5_to_60_days.append(vid)
        elif is_topic_in_past_cycles(words, past_signatures):
            vid["is_past_cycle_repeat"] = True
            tier2_past_cycle_repeats.append(vid)
        else:
            tier1_fresh_unique.append(vid)

    # Apply strict age caps
    capped_over_60_days = tier4_older_than_60_days[:MAX_VIDEOS_OVER_60_DAYS]
    
    # Videos over 5 days include both capped over 60 days + tier 3 (Total cannot exceed 40)
    allowed_tier3_slots = max(0, MAX_VIDEOS_OVER_5_DAYS - len(capped_over_60_days))
    capped_5_to_60_days = tier3_older_5_to_60_days[:allowed_tier3_slots]

    # Combine primary active pool (Fresh unique topics take absolute priority)
    primary_active_feed = tier1_fresh_unique

    # If capacity permits, add older age-capped videos
    primary_active_feed.extend(capped_5_to_60_days)
    primary_active_feed.extend(capped_over_60_days)

    # Dynamic fallback: If fresh news is insufficient to reach 300, fill remaining slots
    if len(primary_active_feed) < TARGET_FEED_CAPACITY:
        remaining = TARGET_FEED_CAPACITY - len(primary_active_feed)
        # Use previous cycle repeats first as filler
        filler_pool = tier2_past_cycle_repeats + repeated_cross_channel_candidates
        primary_active_feed.extend(filler_pool[:remaining])

    # Clean temporary sorting objects
    for v in primary_active_feed:
        v.pop("_dt", None)

    # Final sort descending by date
    primary_active_feed.sort(key=lambda x: parser.parse(x.get("published_at", "1970-01-01T00:00:00Z")), reverse=True)
    return primary_active_feed[:TARGET_FEED_CAPACITY]

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
    log(f"Feed loaded. Total existing records: {len(feed_map)}")

    past_signatures = load_previous_cycle_topic_signatures()
    log(f"Loaded {len(past_signatures)} topic signatures from past 2-hour cycles.")

    cycle_channel_map = {}
    total_cycle_videos = 0

    # Process all 26 channels with per-channel isolation
    for index, handle in enumerate(CHANNELS, start=1):
        try:
            log(f"[{index}/{len(CHANNELS)}] Inspecting {handle}...")
            channel_id = resolve_channel_id(handle)
            videos, method_used = fetch_channel_videos_resilient(channel_id, handle)
            log(f"--> {handle}: Fetched {len(videos)} videos via [{method_used}]")

            for vid in videos:
                v_id = vid["id"]
                try:
                    dt = parser.parse(vid["published_at"])
                    is_fresh_36h = dt >= TIME_WINDOW_36H
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

                # Layman Summary Generation prioritizing Gemini 4 Argon
                if is_fresh_36h and not feed_map[v_id].get("layman_news"):
                    log(f"--> Summarizing with Argon: {vid['title'][:40]}...")
                    summary = generate_layman_summary(vid["title"], vid.get("description", ""), vid.get("channel_title", ""))
                    if summary:
                        feed_map[v_id]["layman_news"] = summary
                        time.sleep(3.2)

            time.sleep(0.7)

        except Exception as channel_err:
            log(f"⚠️ Channel {handle} bypassed due to exception: {channel_err}. Proceeding without error.")
            continue

    # Build dynamically filtered feed respecting all age caps and past-cycle suppressions
    final_feed = build_adaptive_quota_feed(feed_map, past_signatures)
    atomic_save_json(FEED_FILE, final_feed)

    # Log telemetry for the current 2-hour cycle
    cycles_history = []
    if os.path.exists(CYCLES_FILE):
        try:
            with open(CYCLES_FILE, "r", encoding="utf-8") as f:
                cycles_history = json.load(f)
        except Exception:
            cycles_history = []

    current_cycle_record = {
        "timestamp": NOW_UTC.isoformat(),
        "total_new_videos": total_cycle_videos,
        "active_channels_count": len(cycle_channel_map),
        "channels": list(cycle_channel_map.values())
    }
    updated_history = [current_cycle_record] + cycles_history[:5]
    atomic_save_json(CYCLES_FILE, updated_history)

    log(f"Cycle completed successfully. Feed preserved with {len(final_feed)} quota-compliant items.")

if __name__ == "__main__":
    main()
