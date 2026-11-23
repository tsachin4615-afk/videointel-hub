import json
import os
import sys
import time

# Import the exact 4 tier functions directly from scripts/ingest.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest

CHANNELS_FILE = "data/channels.json"
VALID_MODES = {"rss", "yt_dlp", "yt_html", "mirrors"}


def load_channels():
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    mode = sys.argv[1].strip().lower() if len(sys.argv) > 1 else "yt_html"
    if mode not in VALID_MODES:
        print("Usage: python scripts/test_tiers.py [rss|yt_dlp|yt_html|mirrors]")
        sys.exit(1)

    channels = load_channels()
    total = len(channels)
    passed = 0
    failed = []

    print("=" * 60)
    print(f"TESTING TIER: {mode.upper()} ACROSS {total} CHANNELS")
    print("=" * 60)

    for idx, ch in enumerate(channels, start=1):
        handle = ch.get("handle") or f"channel_{idx}"
        cid = ch.get("channel_id")
        title = ch.get("title") or handle

        try:
            if mode == "rss":
                vids = ingest.fetch_via_rss(cid, handle, title, ch=ch)
            elif mode == "yt_dlp":
                vids = ingest.fetch_via_ytdlp(cid, handle, title, ch=ch)
            elif mode == "yt_html":
                vids = ingest.fetch_via_yt_html(cid, handle, title)
            else:
                vids = ingest.fetch_via_mirrors(cid, handle, title)

            if vids:
                passed += 1
                sample = vids[0]["title"][:50]
                print(f"[{idx:02d}/{total}] [PASS] {handle} -> {len(vids)} videos (e.g., {sample})")
            else:
                failed.append((handle, "Returned 0 videos"))
                print(f"[{idx:02d}/{total}] [FAIL] {handle} -> Returned 0 videos")

        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:80]}"
            failed.append((handle, err))
            print(f"[{idx:02d}/{total}] [FAIL] {handle} -> {err}")

        time.sleep(0.4)

    print("\n" + "=" * 60)
    print(f"{mode.upper()} RESULTS: {passed}/{total} PASSED | {len(failed)}/{total} FAILED")
    print("=" * 60)

    if failed:
        print("\nFailed channels:")
        for handle, err in failed:
            print(f" - {handle}: {err}")


if __name__ == "__main__":
    main()
