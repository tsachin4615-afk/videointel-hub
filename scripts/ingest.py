import os
import re
import sys
import json
import time
import random
import subprocess
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

DATA_CHANNELS_FILE = "data/channels.json"
ROOT_CHANNELS_FILE = "channels.json"
VIDEOS_FILE = "videos.json"
MAX_VIDEOS_PER_CHANNEL = 6
MAX_TOTAL_VIDEOS = 250
REQUEST_TIMEOUT = 12
YTDLP_TIMEOUT = 60

DEFAULT_HIGH_QUOTA_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemma-4-31b-it"
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

YT_CONSENT_COOKIE = "CONSENT=YES+cb; SOCS=CAESEwgDEgk0ODE3Nzk3MQaAmgVuBg"

PIPED_MIRRORS = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.tokhmi.xyz",
    "https://pipedapi.moomoo.me",
]

INVIDIOUS_MIRRORS = [
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://yt.artemislena.eu",
]


def http_get_text(url, timeout=REQUEST_TIMEOUT, extra_headers=None):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "*/*",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def http_post_json(url, payload, timeout=15):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8", errors="ignore"))


def load_json_safe(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json_safe(path, data):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_channel_paused(ch):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    paused_until = ch.get("paused_until")
    if paused_until:
        if paused_until >= today:
            return True
        ch["paused"] = False
        ch["paused_until"] = None
        return False
    return bool(ch.get("paused", False))


def extract_uc_from_text(text):
    if not text:
        return None
    patterns = [
        r'"externalId"\s*:\s*"(UC[a-zA-Z0-9_-]{22})"',
        r'"channelId"\s*:\s*"(UC[a-zA-Z0-9_-]{22})"',
        r'"browseId"\s*:\s*"(UC[a-zA-Z0-9_-]{22})"',
        r'youtube\.com/channel/(UC[a-zA-Z0-9_-]{22})',
        r'urn:youtube:channel:(UC[a-zA-Z0-9_-]{22})',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def resolve_channel_id(ch):
    existing = str(ch.get("channel_id") or "").strip()
    if existing.startswith("UC") and len(existing) == 24:
        return existing

    raw_handle = str(ch.get("handle") or "").strip()
    if raw_handle.startswith("UC") and len(raw_handle) == 24:
        ch["channel_id"] = raw_handle
        return raw_handle

    clean_handle = raw_handle.lstrip("@")
    if not clean_handle:
        return None

    # RSS Method 1A: YouTube oEmbed endpoint for @handle (lighter than full channel HTML)
    try:
        watch_or_handle = urllib.parse.quote(f"https://www.youtube.com/@{clean_handle}", safe=":/")
        oembed_raw = http_get_text(
            f"https://www.youtube.com/oembed?url={watch_or_handle}&format=json",
            timeout=8,
        )
        oembed_data = json.loads(oembed_raw)
        author_url = oembed_data.get("author_url", "")
        cid = extract_uc_from_text(author_url)
        if cid:
            ch["channel_id"] = cid
            if oembed_data.get("author_name"):
                ch["title"] = oembed_data["author_name"]
            return cid
    except Exception:
        pass

    # RSS Method 1B: Direct handle page UC extraction
    for candidate_url in [
        f"https://www.youtube.com/@{clean_handle}/about",
        f"https://www.youtube.com/@{clean_handle}",
    ]:
        try:
            html = http_get_text(candidate_url, timeout=9)
            cid = extract_uc_from_text(html)
            if cid:
                ch["channel_id"] = cid
                t = re.search(r'<meta property="og:title" content="([^"]+)">', html)
                if t and t.group(1):
                    ch["title"] = t.group(1)
                return cid
        except Exception:
            continue

    # RSS Method 1C: Invidious channel lookup fallback
    for mirror in INVIDIOUS_MIRRORS:
        try:
            raw = http_get_text(
                f"{mirror}/api/v1/search?q={urllib.parse.quote(clean_handle)}&type=channel",
                timeout=8,
            )
            results = json.loads(raw)
            if isinstance(results, list) and results:
                cid = results[0].get("authorId")
                if cid and cid.startswith("UC"):
                    ch["channel_id"] = cid
                    if results[0].get("author"):
                        ch["title"] = results[0]["author"]
                    return cid
        except Exception:
            continue

    return None


def parse_rss_xml(xml_text, handle, fallback_title, ch=None):
    root = ET.fromstring(xml_text)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }
    if ch is not None and not ch.get("channel_id"):
        ch_id_el = root.find("yt:channelId", ns)
        if ch_id_el is not None and ch_id_el.text and ch_id_el.text.strip().startswith("UC"):
            ch["channel_id"] = ch_id_el.text.strip()

    feed_title_el = root.find("atom:title", ns)
    ch_title = feed_title_el.text.strip() if feed_title_el is not None and feed_title_el.text else fallback_title

    videos = []
    for entry in root.findall("atom:entry", ns)[:MAX_VIDEOS_PER_CHANNEL]:
        vid_el = entry.find("yt:videoId", ns)
        title_el = entry.find("atom:title", ns)
        pub_el = entry.find("atom:published", ns)
        desc_el = entry.find("media:group/media:description", ns)
        if vid_el is None or not vid_el.text:
            continue
        vid = vid_el.text.strip()
        videos.append({
            "id": vid,
            "title": (title_el.text or "").strip() if title_el is not None else "",
            "channel_title": ch_title,
            "handle": handle,
            "published_at": (pub_el.text or datetime.now(timezone.utc).isoformat()).strip() if pub_el is not None else datetime.now(timezone.utc).isoformat(),
            "description": (desc_el.text or "").strip()[:1500] if desc_el is not None else "",
            "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        })
    return videos


def fetch_via_rss(channel_id, handle, fallback_title, ch=None):
    rss_urls = []
    if channel_id and str(channel_id).startswith("UC"):
        rss_urls.append(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")

    clean_handle = str(handle or "").lstrip("@").strip()
    if clean_handle:
        rss_urls.append(f"https://www.youtube.com/feeds/videos.xml?user={urllib.parse.quote(clean_handle)}")

    for url in rss_urls:
        try:
            xml_text = http_get_text(url, timeout=9)
            videos = parse_rss_xml(xml_text, handle, fallback_title, ch=ch)
            if videos:
                return videos
        except Exception:
            continue
    return []


def fetch_via_ytdlp(channel_id, handle, fallback_title, ch=None):
    urls = []
    cid_str = str(channel_id or "").strip()
    handle_str = str(handle or "").strip()

    if cid_str.startswith("UC"):
        urls.append(f"https://www.youtube.com/channel/{cid_str}/videos")
    if handle_str:
        clean_handle = handle_str if handle_str.startswith("@") else f"@{handle_str}"
        urls.append(f"https://www.youtube.com/{clean_handle}/videos")

    urls = list(dict.fromkeys(urls))
    if not urls:
        return []

    now_iso = datetime.now(timezone.utc).isoformat()

    for url in urls:
        command = [
            sys.executable,
            "-m", "yt_dlp",
            "--ignore-config",
            "--flat-playlist",
            "--playlist-end", str(MAX_VIDEOS_PER_CHANNEL),
            "--dump-single-json",
            "--no-warnings",
            "--socket-timeout", "30",
            "--extractor-retries", "2",
            "--retries", "2",
            url,
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=YTDLP_TIMEOUT,
            )
            output = result.stdout.strip()
            if not output:
                continue

            try:
                data = json.loads(output)
            except json.JSONDecodeError:
                continue

            if not isinstance(data, dict):
                continue

            if ch is not None and not ch.get("channel_id"):
                detected_cid = str(data.get("channel_id") or "").strip()
                if detected_cid.startswith("UC"):
                    ch["channel_id"] = detected_cid

            ch_title = (
                data.get("channel")
                or data.get("uploader")
                or data.get("title")
                or fallback_title
            )
            entries = data.get("entries") or []
            videos = []
            seen_ids = set()

            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                vid = str(entry.get("id") or "").strip()
                title = str(entry.get("title") or "").strip()
                if (
                    not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid)
                    or vid in seen_ids
                    or not title
                    or title.lower() in {"[private video]", "[deleted video]"}
                ):
                    continue
                seen_ids.add(vid)
                ts = entry.get("timestamp") or entry.get("release_timestamp")
                pub = (
                    datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    if isinstance(ts, (int, float)) and ts > 0
                    else now_iso
                )
                desc = str(entry.get("description") or "").strip()[:1500]
                videos.append({
                    "id": vid,
                    "title": title,
                    "channel_title": ch_title,
                    "handle": handle,
                    "published_at": pub,
                    "description": desc,
                    "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                })
                if len(videos) >= MAX_VIDEOS_PER_CHANNEL:
                    break

            if videos:
                return videos
        except (subprocess.TimeoutExpired, OSError):
            continue
        except Exception:
            continue

    return []


def _extract_yt_initial_data(html):
    if not html:
        return None
    low = html.lower()
    if "consent.youtube.com" in low or "sorry/index" in low:
        return None

    m = re.search(
        r"(?:var\s+ytInitialData|window\[\s*['\"]ytInitialData['\"]\s*\])\s*=\s*",
        html,
        re.IGNORECASE,
    )
    if not m:
        return None

    start = html.find("{", m.end() - 1)
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for idx in range(start, len(html)):
        ch = html[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[start : idx + 1])
                    except json.JSONDecodeError:
                        return None
    return None


def _extract_videos_recursive(data, ch_title, handle, now_iso, limit):
    found = []
    seen = set()
    stack = [data]

    while stack and len(found) < limit:
        node = stack.pop()
        if isinstance(node, list):
            for item in reversed(node):
                stack.append(item)
        elif isinstance(node, dict):
            vid = node.get("videoId")
            if isinstance(vid, str) and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid) and vid not in seen:
                title = ""
                title_field = node.get("title")
                if isinstance(title_field, dict):
                    if isinstance(title_field.get("simpleText"), str):
                        title = title_field["simpleText"]
                    elif isinstance(title_field.get("runs"), list):
                        title = "".join(
                            p.get("text", "") for p in title_field["runs"] if isinstance(p, dict)
                        )
                elif isinstance(title_field, str):
                    title = title_field
                title = title.strip()
                if title:
                    desc_runs = node.get("descriptionSnippet", {}).get("runs", []) if isinstance(node.get("descriptionSnippet"), dict) else []
                    desc = "".join(r.get("text", "") for r in desc_runs if isinstance(r, dict))
                    seen.add(vid)
                    found.append({
                        "id": vid,
                        "title": title,
                        "channel_title": ch_title,
                        "handle": handle,
                        "published_at": now_iso,
                        "description": desc.strip()[:1500],
                        "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    })
            for val in reversed(list(node.values())):
                if isinstance(val, (dict, list)):
                    stack.append(val)

    return found


def fetch_via_yt_html(channel_id, handle, fallback_title):
    now_iso = datetime.now(timezone.utc).isoformat()
    cid_str = str(channel_id or "").strip()

    # Primary: YouTube InnerTube JSON API (fast, bypasses HTML bot/consent stripping)
    if cid_str.startswith("UC"):
        try:
            payload = {
                "context": {
                    "client": {
                        "clientName": "WEB",
                        "clientVersion": "2.20241120.01.00",
                        "hl": "en",
                        "gl": "US",
                    }
                },
                "browseId": cid_str,
                "params": "EgZ2aWRlb3PyBgQKAjoA",
            }
            status, data = http_post_json(
                "https://www.youtube.com/youtubei/v1/browse?prettyPrint=false",
                payload,
                timeout=REQUEST_TIMEOUT,
            )
            if status == 200 and isinstance(data, dict):
                ch_title = (
                    data.get("metadata", {})
                    .get("channelMetadataRenderer", {})
                    .get("title")
                    or fallback_title
                )
                videos = _extract_videos_recursive(
                    data, ch_title, handle, now_iso, MAX_VIDEOS_PER_CHANNEL
                )
                if videos:
                    return videos
        except Exception:
            pass

    # Fallback: Raw HTML page scraping
    targets = []
    if cid_str.startswith("UC"):
        targets.append(f"https://www.youtube.com/channel/{cid_str}/videos")
        targets.append(f"https://www.youtube.com/channel/{cid_str}/streams")
    if handle:
        clean_handle = handle if str(handle).startswith("@") else f"@{handle}"
        targets.append(f"https://www.youtube.com/{clean_handle}/videos")
        targets.append(f"https://www.youtube.com/{clean_handle}/streams")

    for target in targets:
        try:
            time.sleep(random.uniform(0.2, 0.5))
            html = http_get_text(
                target,
                timeout=REQUEST_TIMEOUT,
                extra_headers={"Cookie": YT_CONSENT_COOKIE},
            )
            data = _extract_yt_initial_data(html)
            if not data:
                continue

            ch_title = (
                data.get("metadata", {})
                .get("channelMetadataRenderer", {})
                .get("title")
                or fallback_title
            )
            tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
            items = []
            for t in tabs:
                grid = t.get("tabRenderer", {}).get("content", {}).get("richGridRenderer", {}).get("contents", [])
                if grid:
                    items = grid
                    break

            videos = []
            for item in items[:MAX_VIDEOS_PER_CHANNEL]:
                vr = item.get("richItemRenderer", {}).get("content", {}).get("videoRenderer")
                if not vr or not vr.get("videoId"):
                    continue
                vid = vr["videoId"]
                runs = vr.get("title", {}).get("runs", [])
                title = runs[0].get("text", "") if runs else vr.get("title", {}).get("simpleText", "")
                desc_runs = vr.get("descriptionSnippet", {}).get("runs", [])
                desc = "".join(r.get("text", "") for r in desc_runs)
                videos.append({
                    "id": vid,
                    "title": title.strip(),
                    "channel_title": ch_title,
                    "handle": handle,
                    "published_at": now_iso,
                    "description": desc.strip()[:1500],
                    "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                })

            if not videos:
                videos = _extract_videos_recursive(data, ch_title, handle, now_iso, MAX_VIDEOS_PER_CHANNEL)

            if videos:
                return videos
        except Exception:
            continue

    return []


def fetch_via_mirrors(channel_id, handle, fallback_title):
    if not channel_id:
        return []
    now_iso = datetime.now(timezone.utc).isoformat()

    for mirror in PIPED_MIRRORS:
        try:
            data = json.loads(http_get_text(f"{mirror}/channel/{channel_id}", timeout=8))
            ch_title = data.get("name") or fallback_title
            streams = data.get("relatedStreams", [])[:MAX_VIDEOS_PER_CHANNEL]
            videos = []
            for s in streams:
                m = re.search(r"v=([a-zA-Z0-9_-]{11})", s.get("url", ""))
                if not m:
                    continue
                vid = m.group(1)
                ts = s.get("uploaded")
                pub = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat() if isinstance(ts, (int, float)) and ts > 0 else now_iso
                videos.append({
                    "id": vid,
                    "title": (s.get("title") or "").strip(),
                    "channel_title": ch_title,
                    "handle": handle,
                    "published_at": pub,
                    "description": (s.get("shortDescription") or "").strip()[:1500],
                    "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                })
            if videos:
                return videos
        except Exception:
            continue

    for mirror in INVIDIOUS_MIRRORS:
        try:
            data = json.loads(http_get_text(f"{mirror}/api/v1/channels/{channel_id}/videos", timeout=8))
            items = data.get("videos", data) if isinstance(data, dict) else data
            if not isinstance(items, list):
                continue
            videos = []
            for s in items[:MAX_VIDEOS_PER_CHANNEL]:
                vid = s.get("videoId")
                if not vid:
                    continue
                ts = s.get("published")
                pub = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if isinstance(ts, (int, float)) and ts > 0 else now_iso
                videos.append({
                    "id": vid,
                    "title": (s.get("title") or "").strip(),
                    "channel_title": s.get("author") or fallback_title,
                    "handle": handle,
                    "published_at": pub,
                    "description": (s.get("description") or "").strip()[:1500],
                    "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                })
            if videos:
                return videos
        except Exception:
            continue

    return []


def fetch_channel_videos_bulletproof(ch):
    handle = ch.get("handle", "")
    fallback_title = ch.get("title") or handle
    cid = resolve_channel_id(ch)

    tiers = [
        ("RSS", lambda: fetch_via_rss(cid, handle, fallback_title, ch=ch)),
        ("YT_DLP", lambda: fetch_via_ytdlp(cid, handle, fallback_title, ch=ch)),
        ("YT_HTML", lambda: fetch_via_yt_html(cid, handle, fallback_title)),
        ("MIRRORS", lambda: fetch_via_mirrors(cid, handle, fallback_title)),
    ]

    for tier_name, fn in tiers:
        try:
            vids = fn()
            if vids:
                ch["title"] = vids[0]["channel_title"] or fallback_title
                print(f"[OK] {handle} -> {len(vids)} videos via {tier_name}")
                return vids
        except Exception as e:
            print(f"[FAILOVER] {handle} failed on {tier_name}: {type(e).__name__}")
            continue

    print(f"[SKIP] {handle} unreachable on all tiers this run (non-fatal).")
    return []


def get_gemini_keys():
    keys = []
    for idx, env_name in enumerate(["GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"], start=1):
        val = (os.environ.get(env_name) or "").strip()
        if len(val) > 10:
            keys.append({"id": f"key{idx}", "label": f"Key {idx}", "key": val})
    if not keys:
        fallback = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if len(fallback) > 10:
            keys.append({"id": "key1", "label": "Key 1", "key": fallback})
    return keys


def discover_active_free_models(keys):
    models = list(DEFAULT_HIGH_QUOTA_MODELS)
    if not keys:
        return models
    try:
        raw = http_get_text(f"https://generativelanguage.googleapis.com/v1beta/models?key={keys[0]['key']}", timeout=10)
        catalog = json.loads(raw).get("models", [])
        banned = ("tts", "image", "audio", "live", "transcribe", "embedding", "aqa", "vision", "robotics", "omni", "nano", "pro", "carbon", "argon", "neon", "1.5", "2.0", "2.5", "exp", "thinking")
        for m in catalog:
            mid = (m.get("name") or "").replace("models/", "")
            if "generateContent" not in (m.get("supportedGenerationMethods") or []):
                continue
            low = mid.lower()
            if any(b in low for b in banned):
                continue
            if (("flash-lite" in low and "preview" not in low) or re.match(r"^gemma-(4|5|6).*-it$", low)) and mid not in models:
                models.append(mid)
    except Exception:
        pass
    return models


def build_layman_prompt(video):
    return (
        "Rewrite this news report as a clear, concrete briefing with exact names, numbers, and dates:\n"
        "## [Sharp Headline]\n"
        "**The Story in Brief:** 3 clear sentences on exact events and actors.\n"
        "**Key Facts:**\n"
        "* **[Fact 1]:** Concrete data, policy, or location.\n"
        "* **[Fact 2]:** Key institution, agreement, or timeline.\n"
        "**Why It Matters:** 2 sentences on real-world impact.\n\n"
        f"Title: \"{video['title']}\" ({video['channel_title']})\n"
        f"Context: {(video.get('description') or '')[:950]}"
    )


def generate_layman_with_failover(video, batch_index, keys, models, cooldown_map):
    if not keys or not models:
        return None

    num_keys = len(keys)
    num_models = len(models)
    start_key_idx = batch_index % num_keys
    per_key_turn = batch_index // num_keys
    start_model_idx = per_key_turn % num_models

    ordered_keys = keys[start_key_idx:] + keys[:start_key_idx]
    ordered_models = models[start_model_idx:] + models[:start_model_idx]

    chain = []
    for k in ordered_keys:
        for m in ordered_models:
            chain.append((k, m, f"{k['id']}::{m}"))

    now = time.time()
    ready = [step for step in chain if cooldown_map.get(step[2], 0) <= now]
    cooling = [step for step in chain if cooldown_map.get(step[2], 0) > now]

    prompt = build_layman_prompt(video)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.35, "maxOutputTokens": 550},
    }

    for key_obj, model, path_id in ready + cooling:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key_obj['key']}"
        try:
            status, data = http_post_json(url, payload, timeout=14)
            txt = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if status == 200 and txt and len(txt.strip()) > 15:
                cooldown_map.pop(path_id, None)
                return txt.strip(), key_obj["label"], model
        except urllib.error.HTTPError as he:
            if he.code == 429:
                cooldown_map[path_id] = time.time() + 45
            continue
        except Exception:
            continue

    return None


def main():
    source_file = DATA_CHANNELS_FILE if os.path.exists(DATA_CHANNELS_FILE) else ROOT_CHANNELS_FILE
    raw_channels = load_json_safe(source_file, [])
    channels = [
        {"handle": c, "title": c, "channel_id": None, "paused": False, "paused_until": None}
        if isinstance(c, str)
        else c
        for c in raw_channels
    ]

    existing_videos = load_json_safe(VIDEOS_FILE, [])
    video_map = {v["id"]: v for v in existing_videos if isinstance(v, dict) and v.get("id")}

    for ch in channels:
        if is_channel_paused(ch):
            continue
        fetched = fetch_channel_videos_bulletproof(ch)
        for v in fetched:
            vid = v["id"]
            if vid in video_map and video_map[vid].get("layman_news"):
                v["layman_news"] = video_map[vid]["layman_news"]
                v["layman_engine"] = video_map[vid].get("layman_engine", "Pre-Generated")
                v["layman_model"] = video_map[vid].get("layman_model", DEFAULT_HIGH_QUOTA_MODELS[0])
            video_map[vid] = v
        time.sleep(0.4)

    save_json_safe(DATA_CHANNELS_FILE, channels)
    save_json_safe(ROOT_CHANNELS_FILE, channels)

    all_videos = sorted(
        video_map.values(),
        key=lambda x: x.get("published_at", ""),
        reverse=True,
    )[:MAX_TOTAL_VIDEOS]

    keys = get_gemini_keys()
    models = discover_active_free_models(keys)
    pending = [v for v in all_videos if not v.get("layman_news")][:45]
    cooldown_map = {}

    if keys and pending:
        print(f"Generating Layman summaries for {len(pending)} new videos across {len(keys)} keys × {len(models)} models...")
        for idx, vid in enumerate(pending):
            res = generate_layman_with_failover(vid, idx, keys, models, cooldown_map)
            if res:
                text, eng, mod = res
                vid["layman_news"] = text
                vid["layman_engine"] = f"{eng} (Backend)"
                vid["layman_model"] = mod
                print(f"[LAYMAN OK] {vid['id']} via {eng} / {mod}")
            time.sleep(0.8)

    save_json_safe(VIDEOS_FILE, all_videos)
    print(f"Done! Saved {len(all_videos)} videos to {VIDEOS_FILE}.")


if __name__ == "__main__":
    main()
