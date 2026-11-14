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

# Default 26 Seed Channels (Automatically migrated into permanent channels.json)
DEFAULT_CHANNELS = [
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

CHANNELS_FILE = "channels.json"
FEED_FILE = "videos.json"
CYCLES_FILE = "cycles.json"

NOW_UTC = datetime.now(timezone.utc)
TIME_WINDOW_36H = NOW_UTC - timedelta(hours=36)
CYCLE_WINDOW_START = NOW_UTC - timedelta(hours=2, minutes=20)
FIVE_DAYS_AGO = NOW_UTC - timedelta(days=5)
SIXTY_DAYS_AGO = NOW_UTC - timedelta(days=60)

MAX_VIDEOS_OVER_5_DAYS = 40
MAX_VIDEOS_OVER_60_DAYS = 20
TARGET_FEED_CAPACITY = 300

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

def atomic_save_json(filepath, data):
    tmp_path = f"{filepath}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, filepath)
    except Exception as e:
        log(f"⚠️ Error saving {filepath}: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

# ==============================================================================
# VIDEO LINK & CHANNEL LINK AUTO-DETECTION (4 FAILOVER ROUTES)
# ==============================================================================
def extract_video_id_from_input(raw_input):
    """Detects if input is a YouTube video link (watch, live, shorts, youtu.be) and returns the 11-char videoId."""
    text = raw_input.strip()
    patterns = [
        r'(?:v=|\/live\/|\/shorts\/|\/embed\/|youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None

def resolve_video_to_parent_channel(video_id):
    """Given a single video ID, detects the original parent channel ID, handle, and title via 4 routes."""
    # Route 1: oEmbed API + Channel URL scrape
    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        res = SESSION.get(oembed_url, timeout=8)
        if res.status_code == 200:
            data = res.json()
            author_name = data.get("author_name", "")
            author_url = data.get("author_url", "")
            handle = None
            channel_id = None
            if "/@" in author_url:
                handle = "@" + author_url.split("/@")[1].split("/")[0].strip()
            elif "/channel/" in author_url:
                channel_id = author_url.split("/channel/")[1].split("/")[0].strip()
            if handle and not channel_id:
                channel_id = resolve_channel_id(handle)
            if channel_id or handle:
                return {
                    "handle": handle or f"@{re.sub(r'[^a-zA-Z0-9]', '', author_name) or channel_id}",
                    "channel_id": channel_id,
                    "title": author_name or handle
                }
    except Exception as e:
        log(f"Video-to-Channel Route 1 (oEmbed) failed for {video_id}: {e}")

    # Route 2: Direct Watch Page HTML Scrape
    try:
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        res = SESSION.get(watch_url, timeout=10)
        if res.status_code == 200:
            html = res.text
            ch_id_match = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"', html) or re.search(r'itemprop="channelId"\s+content="(UC[a-zA-Z0-9_-]{22})"', html)
            owner_match = re.search(r'"ownerProfileUrl":"https://www\.youtube\.com/@([^"/]+)"', html)
            author_match = re.search(r'"author":"([^"]+)"', html)

            c_id = ch_id_match.group(1) if ch_id_match else None
            h_str = f"@{owner_match.group(1)}" if owner_match else None
            t_str = author_match.group(1) if author_match else (h_str or c_id)

            if c_id or h_str:
                return {
                    "handle": h_str or c_id,
                    "channel_id": c_id,
                    "title": t_str
                }
    except Exception as e:
        log(f"Video-to-Channel Route 2 (Watch HTML) failed for {video_id}: {e}")

    # Route 3: YouTube Data API v3 Videos Endpoint
    if YOUTUBE_API_KEY:
        try:
            api_url = "https://www.googleapis.com/youtube/v3/videos"
            params = {"part": "snippet", "id": video_id, "key": YOUTUBE_API_KEY}
            res = SESSION.get(api_url, params=params, timeout=8).json()
            items = res.get("items", [])
            if items:
                snip = items[0].get("snippet", {})
                c_id = snip.get("channelId")
                c_title = snip.get("channelTitle", c_id)
                return {
                    "handle": f"@{re.sub(r'[^a-zA-Z0-9]', '', c_title)}" if c_title else c_id,
                    "channel_id": c_id,
                    "title": c_title
                }
        except Exception as e:
            log(f"Video-to-Channel Route 3 (API) failed for {video_id}: {e}")

    return None

# ==============================================================================
# TIERED CHANNEL ID RESOLVER (4 FAILOVER ROUTES)
# ==============================================================================
def resolve_channel_id(handle_or_input):
    raw = handle_or_input.strip()

    # Check if already a 24-char UC channel ID
    if re.match(r'^UC[a-zA-Z0-9_-]{22}$', raw):
        return raw

    # Check if URL contains /channel/UC...
    m_ch = re.search(r'youtube\.com/channel/(UC[a-zA-Z0-9_-]{22})', raw)
    if m_ch:
        return m_ch.group(1)

    # Extract @handle if full URL was passed
    m_h = re.search(r'youtube\.com/@([a-zA-Z0-9_.-]+)', raw)
    if m_h:
        clean_handle = f"@{m_h.group(1)}"
    else:
        clean_handle = raw if raw.startswith("@") else f"@{raw}"

    # Route 1: Direct Web HTML Scrape
    url = f"https://www.youtube.com/{clean_handle}"
    try:
        res = SESSION.get(url, timeout=10)
        if res.status_code == 200:
            for pat in [
                r'itemprop="channelId"\s+content="([a-zA-Z0-9_-]{24})"',
                r'"channelId":"([a-zA-Z0-9_-]{24})"',
                r'"externalId":"([a-zA-Z0-9_-]{24})"',
                r'href="https://www\.youtube\.com/channel/([a-zA-Z0-9_-]{24})"'
            ]:
                match = re.search(pat, res.text)
                if match:
                    return match.group(1)
    except Exception as e:
        log(f"Resolve Route 1 failed for {clean_handle}: {e}")

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
            log(f"Resolve Route 2 failed for {clean_handle}: {e}")

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
            log(f"Resolve Route 3 failed for {clean_handle}: {e}")

    return None

# ==============================================================================
# PERMANENT CHANNEL ROSTER MANAGER & PAUSE CHECKER
# ==============================================================================
def load_and_sync_channels():
    """
    Loads channels.json, merges any new entries or raw video/channel links added from the dashboard,
    resolves parent channels permanently, and saves back to channels.json.
    """
    roster = []
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    roster = loaded
        except Exception as e:
            log(f"⚠️ Could not parse {CHANNELS_FILE}, rebuilding: {e}")

    # Normalize existing entries and ensure seed channels exist
    normalized_map = {}
    for entry in roster:
        if isinstance(entry, str):
            entry = {"handle": entry, "title": entry, "paused": False, "paused_until": None}
        raw_key = (entry.get("handle") or entry.get("raw_input") or "").strip()
        if not raw_key:
            continue

        # Check if user pasted a video link or raw URL into the entry
        vid_id = extract_video_id_from_input(raw_key)
        if vid_id and not entry.get("channel_id"):
            log(f"🔍 Detecting parent channel from shared video link [{vid_id}]...")
            detected = resolve_video_to_parent_channel(vid_id)
            if detected:
                entry["handle"] = detected["handle"]
                entry["channel_id"] = detected["channel_id"]
                entry["title"] = detected["title"]
                log(f"✅ Permanently resolved video {vid_id} -> {entry['title']} ({entry['handle']})")

        # Clean handle if full channel URL was pasted
        m_h = re.search(r'youtube\.com/@([a-zA-Z0-9_.-]+)', entry.get("handle", ""))
        if m_h:
            entry["handle"] = f"@{m_h.group(1)}"

        handle_key = entry.get("handle", raw_key)
        if not handle_key.startswith("@") and not handle_key.startswith("UC"):
            handle_key = f"@{handle_key}"
        entry["handle"] = handle_key
        entry.setdefault("title", handle_key)
        entry.setdefault("channel_id", None)
        entry.setdefault("paused", False)
        entry.setdefault("paused_until", None)
        entry.setdefault("added_at", NOW_UTC.isoformat())

        normalized_map[handle_key.lower()] = entry

    # Ensure all 26 default channels are present unless explicitly deleted
    if not roster:
        for ch in DEFAULT_CHANNELS:
            k = ch.lower()
            if k not in normalized_map:
                normalized_map[k] = {
                    "handle": ch,
                    "title": ch,
                    "channel_id": None,
                    "paused": False,
                    "paused_until": None,
                    "added_at": NOW_UTC.isoformat()
                }

    final_roster = list(normalized_map.values())
    atomic_save_json(CHANNELS_FILE, final_roster)
    return final_roster

def is_channel_currently_paused(ch_obj):
    """Checks if a channel is paused indefinitely or until a future date."""
    paused_until = ch_obj.get("paused_until")
    if paused_until:
        try:
            until_dt = parser.parse(paused_until)
            if until_dt.tzinfo is None:
                until_dt = until_dt.replace(tzinfo=timezone.utc)
            if NOW_UTC < until_dt:
                return True, f"Paused until {paused_until[:10]}"
            else:
                # Pause date has expired -> auto-unpause!
                ch_obj["paused"] = False
                ch_obj["paused_until"] = None
                return False, None
        except Exception:
            pass

    if ch_obj.get("paused") is True:
        return True, "Paused indefinitely"

    return False, None

# ==============================================================================
# RESILIENT VIDEO HARVESTING (6 FAILOVER ROUTES PER CHANNEL)
# ==============================================================================
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

def fetch_via_web_initialdata(handle, tab="videos"):
    clean_handle = handle if handle.startswith("@") or handle.startswith("UC") else f"@{handle}"
    path_prefix = f"channel/{clean_handle}" if clean_handle.startswith("UC") else clean_handle
    url = f"https://www.youtube.com/{path_prefix}/{tab}"
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
        log(f"Web scraper error on {handle} [{tab}]: {e}")

    return videos

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

    # Tier 4: Web Scraper /streams
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
# FAST CASCADE SUMMARIZER
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

    model_cascade = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-4-argon", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
    for model in model_cascade:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=18)
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
    past_signatures = []
    if os.path.exists(CYCLES_FILE):
        try:
            with open(CYCLES_FILE, "r", encoding="utf-8") as f:
                cycles = json.load(f)
            for cyc in cycles[:3]:
                for ch in cyc.get("channels", []):
                    for topic in ch.get("topics", []):
                        sig = normalize_keywords(topic)
                        if sig:
                            past_signatures.append(sig)
        except Exception:
            pass
    return past_signatures

def is_topic_in_past_cycles(title_words, past_signatures):
    for past_sig in past_signatures:
        overlap = len(title_words.intersection(past_sig))
        if overlap >= 3 or (overlap >= 2 and len(title_words) <= 4):
            return True
    return False

def build_adaptive_quota_feed(feed_map, past_signatures):
    all_vids = list(feed_map.values())
    for v in all_vids:
        try:
            v["_dt"] = parser.parse(v.get("published_at", "1970-01-01T00:00:00Z"))
        except Exception:
            v["_dt"] = datetime(1970, 1, 1, tzinfo=timezone.utc)

    all_vids.sort(key=lambda x: x["_dt"], reverse=True)

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
            topic_clusters.append({"words": words, "videos": [vid]})

    unique_best_candidates = []
    repeated_cross_channel_candidates = []

    for cluster in topic_clusters:
        sorted_vids = sorted(
            cluster["videos"],
            key=lambda v: (1 if v.get("layman_news") else 0, len(v.get("description", "")), v["_dt"]),
            reverse=True
        )
        unique_best_candidates.append(sorted_vids[0])
        for rep in sorted_vids[1:]:
            rep["is_duplicate_topic"] = True
            repeated_cross_channel_candidates.append(rep)

    tier1_fresh_unique = []
    tier2_past_cycle_repeats = []
    tier3_older_5_to_60_days = []
    tier4_older_than_60_days = []

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

    capped_over_60_days = tier4_older_than_60_days[:MAX_VIDEOS_OVER_60_DAYS]
    allowed_tier3_slots = max(0, MAX_VIDEOS_OVER_5_DAYS - len(capped_over_60_days))
    capped_5_to_60_days = tier3_older_5_to_60_days[:allowed_tier3_slots]

    primary_active_feed = tier1_fresh_unique + capped_5_to_60_days + capped_over_60_days

    if len(primary_active_feed) < TARGET_FEED_CAPACITY:
        remaining = TARGET_FEED_CAPACITY - len(primary_active_feed)
        filler_pool = tier2_past_cycle_repeats + repeated_cross_channel_candidates
        primary_active_feed.extend(filler_pool[:remaining])

    for v in primary_active_feed:
        v.pop("_dt", None)

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
    log(f"Feed loaded: {len(feed_map)} existing items.")

    # Load permanent channel roster (includes any newly added channels from dashboard)
    channel_roster = load_and_sync_channels()
    log(f"Active permanent channel roster size: {len(channel_roster)}")

    past_signatures = load_previous_cycle_topic_signatures()
    cycle_channel_map = {}
    total_cycle_videos = 0

    for index, ch_obj in enumerate(channel_roster, start=1):
        handle = ch_obj.get("handle", "")
        try:
            # Check Pause Status / Pause Date
            is_paused, reason = is_channel_currently_paused(ch_obj)
            if is_paused:
                log(f"[{index}/{len(channel_roster)}] ⏸️ Skipping {handle} ({reason})")
                continue

            log(f"[{index}/{len(channel_roster)}] Inspecting {handle}...")
            channel_id = ch_obj.get("channel_id") or resolve_channel_id(handle)
            if channel_id:
                ch_obj["channel_id"] = channel_id

            videos, method_used = fetch_channel_videos_resilient(channel_id, handle)
            log(f"--> {handle}: Fetched {len(videos)} videos via [{method_used}]")

            if videos and videos[0].get("channel_title"):
                ch_obj["title"] = videos[0]["channel_title"]

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

                if is_fresh_36h and not feed_map[v_id].get("layman_news"):
                    log(f"--> Summarizing: {vid['title'][:40]}...")
                    summary = generate_layman_summary(vid["title"], vid.get("description", ""), vid.get("channel_title", ""))
                    if summary:
                        feed_map[v_id]["layman_news"] = summary
                        time.sleep(3.0)

            time.sleep(0.6)

        except Exception as channel_err:
            log(f"⚠️ Channel {handle} isolated error: {channel_err}. Continuing.")
            continue

    # Save updated channel metadata (resolved channel_ids, titles, auto-expired pause dates)
    atomic_save_json(CHANNELS_FILE, channel_roster)

    final_feed = build_adaptive_quota_feed(feed_map, past_signatures)
    atomic_save_json(FEED_FILE, final_feed)

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
    atomic_save_json(CYCLES_FILE, [current_cycle_record] + cycles_history[:5])
    log(f"Run completed. Active feed items: {len(final_feed)}")

if __name__ == "__main__":
    main()
