
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs


# ==========================================
# VIDEOINTEL HUB - YOUTUBE DISCOVERY ENGINE
# ==========================================

CHANNELS = [
    {"name": "StudyIQ IAS", "id": "UCrC8mOqJQpoB7NuIMKIS6rQ"},
    {"name": "DEF Talks by Aadi", "id": "UCMDWKjf52UP55TF4a5sxmQg"},
    {"name": "World Affairs", "id": "UCCJsQKOKArvDksacfT2ryQw"},
    {"name": "Coffee With Sumeet Jain", "id": "UCcnwa6E4BwDJKeATB6tqmsQ"},
    {"name": "Firstpost Vantage", "id": "UCz8QaiQxApLq8sLNcszYyJw"},
    {"name": "WION", "id": "UC_gUM8rL-Lrg6O3adPW9K1g"},
    {"name": "Finology Legal", "id": "UCItJsxqZNWUyxFn-A2tzizQ"},
    {"name": "Pranjal Kamra", "id": "UCwAdQUuPT6laN-AQR17fe1g"},
    {"name": "Bankers Adda247", "id": "UC7DgZZeZD2HKc7JUAsIwe-w"}
]

MAX_VIDEOS_PER_CHANNEL = 15
MAX_TOTAL_VIDEOS = 250
REQUEST_TIMEOUT = 20

OUTPUT_FILE = Path("videos.json")

ATOM = "{http://www.w3.org/2005/Atom}"
YT = "{http://www.youtube.com/xml/schemas/2015}"
MEDIA = "{http://search.yahoo.com/mrss/}"


def utc_now():
    return datetime.now(timezone.utc)


def parse_date(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def get_video_id(link):
    try:
        parsed = urlparse(link)

        if parsed.hostname in ("youtu.be", "www.youtu.be"):
            return parsed.path.strip("/").split("/")[0]

        if parsed.hostname and "youtube.com" in parsed.hostname:
            query_id = parse_qs(parsed.query).get("v")
            if query_id:
                return query_id[0]

            match = re.search(
                r"/(?:shorts|live|embed)/([^/?]+)",
                parsed.path
            )
            if match:
                return match.group(1)

    except Exception:
        pass

    return ""


def load_existing_videos():
    if not OUTPUT_FILE.exists():
        return []

    try:
        with OUTPUT_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        videos = data.get("videos", [])

        if isinstance(videos, list):
            return videos

    except (OSError, json.JSONDecodeError) as error:
        print(f"WARNING: Could not read old videos.json: {error}")

    return []


def fetch_channel(channel):
    channel_id = channel["id"]

    feed_url = (
        "https://www.youtube.com/feeds/videos.xml"
        f"?channel_id={channel_id}"
    )

    request = urllib.request.Request(
        feed_url,
        headers={
            "User-Agent": "VideoIntelHub/1.0",
            "Accept": "application/atom+xml, application/xml"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=REQUEST_TIMEOUT
    ) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)

    entries = root.findall(f"{ATOM}entry")
    videos = []

    for entry in entries[:MAX_VIDEOS_PER_CHANNEL]:

        title_element = entry.find(f"{ATOM}title")
        link_element = entry.find(f"{ATOM}link")
        published_element = entry.find(f"{ATOM}published")
        id_element = entry.find(f"{YT}videoId")

        title = (
            title_element.text.strip()
            if title_element is not None and title_element.text
            else "Untitled video"
        )

        link = ""

        if link_element is not None:
            link = link_element.attrib.get("href", "")

        video_id = (
            id_element.text.strip()
            if id_element is not None and id_element.text
            else get_video_id(link)
        )

        if not video_id:
            video_id = get_video_id(link)

        if not video_id:
            continue

        published = (
            published_element.text.strip()
            if published_element is not None
            and published_element.text
            else ""
        )

        # Extract optional video description.
        description = ""
        media_group = entry.find(f"{MEDIA}group")

        if media_group is not None:
            description_element = media_group.find(
                f"{MEDIA}description"
            )

            if description_element is not None:
                description = description_element.text or ""

        videos.append({
            "video_id": video_id,
            "channel": channel["name"],
            "channel_id": channel_id,
            "title": title,
            "link": link or (
                f"https://www.youtube.com/watch?v={video_id}"
            ),
            "published": published,
            "thumbnail": (
                f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            ),
            "description": description
        })

    return videos


def main():

    old_videos = load_existing_videos()

    successful_channels = set()
    failed_channels = []

    discovered = []

    print("Starting VideoIntel Hub discovery...")
    print(f"Monitoring {len(CHANNELS)} channels.")

    for channel in CHANNELS:

        try:
            videos = fetch_channel(channel)

            discovered.extend(videos)
            successful_channels.add(channel["id"])

            print(
                f"SUCCESS: {channel['name']} "
                f"- {len(videos)} videos"
            )

        except Exception as error:

            failed_channels.append({
                "channel": channel["name"],
                "error": str(error)
            })

            print(
                f"ERROR: {channel['name']} - {error}"
            )

    # If every feed fails, preserve the existing file.
    if not successful_channels:

        print(
            "All channel feeds failed. "
            "Existing videos.json was not changed."
        )

        sys.exit(1)

    # Preserve previously collected data for channels
    # that could not be reached during this run.
    preserved = []

    failed_ids = {
        channel["id"]
        for channel in CHANNELS
        if channel["id"] not in successful_channels
    }

    failed_names = {
        channel["name"]
        for channel in CHANNELS
        if channel["id"] not in successful_channels
    }

    for video in old_videos:

        channel_id = video.get("channel_id", "")
        channel_name = video.get("channel", "")

        if channel_id in failed_ids or (
            not channel_id and channel_name in failed_names
        ):
            preserved.append(video)

    # Combine newly discovered and preserved videos.
    combined = discovered + preserved

    # Remove duplicate videos using their YouTube video ID.
    unique = {}
    for video in combined:

        video_id = video.get("video_id") or get_video_id(
            video.get("link", "")
        )

        if not video_id:
            continue

        video["video_id"] = video_id

        if video_id not in unique:
            unique[video_id] = video

    all_videos = list(unique.values())

    # Sort newest first.
    all_videos.sort(
        key=lambda video: parse_date(video.get("published")),
        reverse=True
    )

    all_videos = all_videos[:MAX_TOTAL_VIDEOS]

    output = {
        "last_updated": utc_now().strftime(
            "%Y-%m-%d %H:%M UTC"
        ),
        "total_videos": len(all_videos),
        "successful_channels": len(successful_channels),
        "failed_channels": failed_channels,
        "videos": all_videos
    }

    # Write safely using a temporary file.
    temporary_file = OUTPUT_FILE.with_suffix(".tmp")

    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False
        )

    temporary_file.replace(OUTPUT_FILE)

    print("--------------------------------")
    print("VIDEOINTEL HUB DISCOVERY COMPLETE")
    print(f"Videos available: {len(all_videos)}")
    print(f"Channels successful: {len(successful_channels)}")
    print(f"Channels failed: {len(failed_channels)}")
    print("Saved videos.json")
    print("--------------------------------")


if __name__ == "__main__":
    main()
