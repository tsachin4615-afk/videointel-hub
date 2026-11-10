import os
import json
import urllib.request
import urllib.parse

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

CHANNELS = [
    {"name": "StudyIQ IAS", "query": "StudyIQ IAS"},
    {"name": "World Affairs", "query": "World Affairs Unacademy"},
    {"name": "WION", "query": "WION news"},
    {"name": "Firstpost Vantage", "query": "Firstpost Vantage"},
    {"name": "India Decoded", "query": "India Decoded AA"},
    {"name": "Times Axis", "query": "Times Axis"},
    {"name": "Parcham Classes", "query": "Parcham Classes"},
    {"name": "Coffee With Sumeet Jain", "query": "Coffee With Sumeet Jain"}
]

def fetch_feed():
    if not YOUTUBE_API_KEY:
        print("[Fatal Error] YOUTUBE_API_KEY is missing from environment variables!")
        return

    all_videos = []

    for ch in CHANNELS:
        name = ch["name"]
        print(f"[Channel] Fetching updates for {name}...")

        params = {
            "part": "snippet",
            "q": ch["query"],
            "type": "video",
            "order": "date",
            "maxResults": 2,
            "key": YOUTUBE_API_KEY
        }
        url = f"https://www.googleapis.com/youtube/v3/search?{urllib.parse.urlencode(params)}"

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=12) as res:
                data = json.loads(res.read().decode('utf-8'))

            items = data.get("items", [])
            print(f" -> Found {len(items)} items for {name}")

            for item in items:
                v_id = item["id"]["videoId"]
                snippet = item["snippet"]
                all_videos.append({
                    "id": v_id,
                    "channel_title": name,
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "thumbnail_url": snippet.get("thumbnails", {}).get("high", {}).get("url", f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg")
                })
        except Exception as e:
            print(f"[API Error] Failed fetching {name}: {e}")

    if all_videos:
        with open("videos.json", "w", encoding="utf-8") as f:
            json.dump(all_videos, f, indent=2, ensure_ascii=False)
        print(f"\n[Success] Saved {len(all_videos)} videos across all channels into videos.json")
    else:
        print("\n[Warning] No videos retrieved. Existing videos.json kept.")

if __name__ == "__main__":
    fetch_feed()
