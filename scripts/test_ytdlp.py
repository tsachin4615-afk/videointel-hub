import json
import os
import re
import subprocess
import sys
import time

DATA_CHANNELS_FILE = "data/channels.json"
ROOT_CHANNELS_FILE = "channels.json"
TEST_LIMIT = 3
TIMEOUT_SECONDS = 25


def load_channels():
    path = DATA_CHANNELS_FILE if os.path.exists(DATA_CHANNELS_FILE) else ROOT_CHANNELS_FILE
    if not os.path.exists(path):
        print(f"[ERROR] Channels file not found at {path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [
        {"handle": c, "title": c, "channel_id": None}
        if isinstance(c, str)
        else c
        for c in raw
    ]


def test_channel_ytdlp(ch):
    channel_id = str(ch.get("channel_id") or "").strip()
    handle = str(ch.get("handle") or "").strip()

    targets = []
    if channel_id.startswith("UC"):
        targets.append(f"https://www.youtube.com/channel/{channel_id}/videos")
        targets.append(f"https://www.youtube.com/channel/{channel_id}/streams")
    elif handle:
        clean_handle = handle if handle.startswith("@") else f"@{handle}"
        targets.append(f"https://www.youtube.com/{clean_handle}/videos")
        targets.append(f"https://www.youtube.com/{clean_handle}/streams")

    if not targets:
        return [], "No channel_id or handle"

    found = []
    seen = set()
    last_error = "No videos returned"

    for tab_url in targets:
        if len(found) >= TEST_LIMIT:
            break
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--flat-playlist",
            "--playlist-end",
            str(TEST_LIMIT),
            "--dump-single-json",
            "--no-warnings",
            "--ignore-errors",
            "--extractor-args",
            "youtube:player_client=android,web",
            tab_url,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
            if not proc.stdout:
                err_msg = (proc.stderr or "").strip().splitlines()
                if err_msg:
                    last_error = err_msg[-1][:120]
                continue
            payload = json.loads(proc.stdout)
            entries = payload.get("entries") or []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                vid = (entry.get("id") or "").strip()
                title = (entry.get("title") or "").strip()
                if (
                    vid
                    and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid)
                    and vid not in seen
                    and title
                    and title.lower() not in {"[private video]", "[deleted video]"}
                ):
                    seen.add(vid)
                    found.append((vid, title))
                    if len(found) >= TEST_LIMIT:
                        break
        except subprocess.TimeoutExpired:
            last_error = f"Timeout ({TIMEOUT_SECONDS}s)"
        except Exception as e:
            last_error = type(e).__name__

    return found, last_error


def main():
    channels = load_channels()
    total = len(channels)
    passed = []
    failed = []

    print(f"Starting yt-dlp test across {total} channels...\n")

    for idx, ch in enumerate(channels, start=1):
        handle = ch.get("handle") or ch.get("title") or ch.get("channel_id") or f"channel_{idx}"
        videos, err = test_channel_ytdlp(ch)
        if videos:
            passed.append(handle)
            sample_title = videos[0][1][:55]
            print(f"[{idx:02d}/{total}] [OK]   {handle} -> {len(videos)} videos (e.g., {sample_title})")
        else:
            failed.append((handle, err))
            print(f"[{idx:02d}/{total}] [FAIL] {handle} -> {err}")
        time.sleep(0.5)

    print("\n" + "=" * 60)
    print(f"TEST COMPLETE: {len(passed)}/{total} PASSED | {len(failed)}/{total} FAILED")
    print("=" * 60)
    if failed:
        print("\nFailed channels:")
        for handle, err in failed:
            print(f" - {handle}: {err}")


if __name__ == "__main__":
    main()
