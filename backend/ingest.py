import json
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CHANNELS_FILE = DATA_DIR / "channels.json"
FEED_FILE = DATA_DIR / "feed.json"

RSS_URL_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cookie": "CONSENT=YES+cb; SOCS=CAESEwgDEgk0ODE3Nzk3MQaAmgVuBg",
}

PIPED_INSTANCES = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://pipedapi.leptons.xyz",
]

ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def load_channels() -> list[dict]:
    if not CHANNELS_FILE.exists():
        return []
    with CHANNELS_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def load_existing_feed() -> dict:
    if not FEED_FILE.exists():
        return {"updated_at": None, "videos": []}
    try:
        with FEED_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("videos"), list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"updated_at": None, "videos": []}


def fetch_via_rss(channel_id: str, limit: int = 6, timeout: int = 12) -> list[dict]:
    if not channel_id or not channel_id.startswith("UC"):
        return []
    url = RSS_URL_TEMPLATE.format(channel_id=quote(channel_id.strip()))
    resp = requests.get(
        url,
        headers={"User-Agent": BROWSER_HEADERS["User-Agent"]},
        timeout=timeout,
    )
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    entries = root.findall("atom:entry", ATOM_NS)
    videos = []

    for entry in entries[:limit]:
        vid_el = entry.find("yt:videoId", ATOM_NS)
        title_el = entry.find("atom:title", ATOM_NS)
        pub_el = entry.find("atom:published", ATOM_NS)
        desc_el = entry.find("media:group/media:description", ATOM_NS)

        video_id = (vid_el.text or "").strip() if vid_el is not None else ""
        title = (title_el.text or "").strip() if title_el is not None else ""
        published = (pub_el.text or "").strip() if pub_el is not None else ""
        description = (desc_el.text or "").strip() if desc_el is not None else ""

        if video_id and title:
            videos.append({
                "video_id": video_id,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "published_at": published,
                "description": description[:500],
                "source_tier": "RSS",
            })

    return videos


def _extract_yt_initial_data(html: str) -> dict | None:
    if not html:
        return None
    lowered = html.lower()
    if "consent.youtube.com" in lowered or "sorry/index" in lowered:
        return None

    pattern = re.compile(
        r"(?:var\s+ytInitialData|window\[\s*['\"]ytInitialData['\"]\s*\])\s*=\s*",
        re.IGNORECASE,
    )
    match = pattern.search(html)
    if not match:
        return None

    start = html.find("{", match.end() - 1)
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
                    raw_json = html[start : idx + 1]
                    try:
                        return json.loads(raw_json)
                    except json.JSONDecodeError:
                        return None
    return None


def _extract_videos_from_data(data: dict, limit: int = 6) -> list[dict]:
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
                            part.get("text", "")
                            for part in title_field["runs"]
                            if isinstance(part, dict)
                        )
                elif isinstance(title_field, str):
                    title = title_field

                title = title.strip()
                if title:
                    seen.add(vid)
                    found.append({
                        "video_id": vid,
                        "title": title,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "published_at": "",
                        "description": "",
                        "source_tier": "YT_HTML",
                    })

            for val in reversed(list(node.values())):
                if isinstance(val, (dict, list)):
                    stack.append(val)

    return found


def fetch_via_yt_html(channel: dict, limit: int = 6, timeout: int = 12) -> list[dict]:
    handle = (channel.get("handle") or "").strip()
    channel_id = (channel.get("channel_id") or "").strip()

    urls = []
    if handle:
        clean_handle = handle if handle.startswith("@") else f"@{handle}"
        urls.append(f"https://www.youtube.com/{quote(clean_handle)}/videos")
        urls.append(f"https://www.youtube.com/{quote(clean_handle)}/streams")
    if channel_id and channel_id.startswith("UC"):
        urls.append(f"https://www.youtube.com/channel/{quote(channel_id)}/videos")

    last_err = None
    for page_url in urls:
        try:
            time.sleep(random.uniform(0.35, 0.9))
            resp = requests.get(page_url, headers=BROWSER_HEADERS, timeout=timeout)
            resp.raise_for_status()
            yt_data = _extract_yt_initial_data(resp.text)
            if not yt_data:
                continue
            videos = _extract_videos_from_data(yt_data, limit=limit)
            if videos:
                return videos
        except requests.HTTPError as exc:
            last_err = exc
            continue
        except requests.RequestException as exc:
            last_err = exc
            continue

    if last_err is not None:
        raise last_err
    return []


def fetch_via_piped(channel_id: str, limit: int = 6, timeout: int = 10) -> list[dict]:
    if not channel_id or not channel_id.startswith("UC"):
        return []

    for base_url in PIPED_INSTANCES:
        try:
            resp = requests.get(
                f"{base_url}/channel/{quote(channel_id.strip())}",
                headers={"User-Agent": BROWSER_HEADERS["User-Agent"]},
                timeout=timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
            streams = payload.get("relatedStreams") or []
            videos = []
            for item in streams[:limit]:
                raw_url = item.get("url") or ""
                vid = raw_url.split("v=")[-1].split("&")[0] if "v=" in raw_url else ""
                title = (item.get("title") or "").strip()
                if vid and title:
                    videos.append({
                        "video_id": vid,
                        "title": title,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "published_at": "",
                        "description": "",
                        "source_tier": "PIPED",
                    })
            if videos:
                return videos
        except (requests.RequestException, ValueError):
            continue

    return []


def fetch_channel_videos(channel: dict, limit: int = 6) -> tuple[list[dict], str]:
    handle = (channel.get("handle") or channel.get("title") or "unknown").strip()
    channel_id = (channel.get("channel_id") or "").strip()

    # Tier 1: Official RSS using UC... channel_id
    if channel_id:
        try:
            videos = fetch_via_rss(channel_id, limit=limit)
            if videos:
                return videos, "RSS"
        except Exception:
            pass

    # Tier 2: Hardened YT_HTML fallback (handles HTTPError gracefully)
    try:
        videos = fetch_via_yt_html(channel, limit=limit)
        if videos:
            return videos, "YT_HTML"
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        print(f"[FAILOVER] {handle} failed on YT_HTML: HTTPError ({status})")
    except Exception as exc:
        print(f"[FAILOVER] {handle} failed on YT_HTML: {type(exc).__name__}")

    # Tier 3: Piped mirror fallback
    if channel_id:
        videos = fetch_via_piped(channel_id, limit=limit)
        if videos:
            return videos, "PIPED"

    return [], "NONE"


def run_ingest() -> None:
    channels = load_channels()
    existing_feed = load_existing_feed()
    existing_videos = existing_feed.get("videos", [])

    by_id = {}
    for item in existing_videos:
        if isinstance(item, dict) and item.get("video_id"):
            by_id[item["video_id"]] = item

    new_count = 0

    for ch in channels:
        if not isinstance(ch, dict):
            continue
        if ch.get("paused") is True:
            continue

        handle = (ch.get("handle") or ch.get("title") or "unknown").strip()
        channel_id = (ch.get("channel_id") or "").strip()

        videos, tier = fetch_channel_videos(ch, limit=6)
        if not videos:
            print(f"[SKIP] {handle} unreachable on all tiers this run (non-fatal).")
            continue

        print(f"[OK] {handle} -> {len(videos)} videos via {tier}")
        for v in videos:
            vid = v["video_id"]
            if vid not in by_id:
                new_count += 1
            by_id[vid] = {
                **by_id.get(vid, {}),
                **v,
                "channel_handle": handle,
                "channel_title": ch.get("title") or handle,
                "channel_id": channel_id,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

    merged_videos = list(by_id.values())
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_videos": len(merged_videos),
        "new_videos_this_run": new_count,
        "videos": merged_videos,
    }

    with FEED_FILE.open("w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2, ensure_ascii=False)

    print(f"Ingest complete. New videos discovered: {new_count}, Total cached: {len(merged_videos)}")


if __name__ == "__main__":
    # Keep GEMINI_API_KEY check non-blocking if invoked standalone
    if not os.environ.get("GEMINI_API_KEY"):
        print("[INFO] GEMINI_API_KEY not set in environment; skipping summary step if handled elsewhere.")
    run_ingest()
