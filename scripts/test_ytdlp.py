
import json
import re
import subprocess
import sys
import time

CHANNELS_FILE = "data/channels.json"
VIDEO_LIMIT = 3
TIMEOUT = 60


def load_channels():
    with open(CHANNELS_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("channels.json must contain a list")

    return data


def get_channel_urls(channel):
    urls = []

    channel_id = str(channel.get("channel_id") or "").strip()
    handle = str(channel.get("handle") or "").strip()

    if channel_id.startswith("UC"):
        urls.append(
            f"https://www.youtube.com/channel/{channel_id}/videos"
        )

    if handle:
        if not handle.startswith("@"):
            handle = "@" + handle

        urls.append(
            f"https://www.youtube.com/{handle}/videos"
        )

    return list(dict.fromkeys(urls))


def test_channel(channel):
    urls = get_channel_urls(channel)

    if not urls:
        return False, [], "No channel ID or handle"

    errors = []

    for url in urls:
        command = [
            sys.executable,
            "-m", "yt_dlp",
            "--ignore-config",
            "--flat-playlist",
            "--playlist-end", str(VIDEO_LIMIT),
            "--dump-single-json",
            "--no-warnings",
            "--socket-timeout", "30",
            "--extractor-retries", "2",
            "--retries", "2",
            url
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=TIMEOUT
            )

            output = result.stdout.strip()

            if not output:
                errors.append(
                    "Empty response: " +
                    (result.stderr.strip()[-300:] or
                     f"Exit code {result.returncode}")
                )
                continue

            try:
                data = json.loads(output)
            except json.JSONDecodeError:
                errors.append("Invalid JSON response")
                continue

            if not isinstance(data, dict):
                errors.append("Invalid YouTube response")
                continue

            entries = data.get("entries") or []

            videos = []

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                video_id = str(entry.get("id") or "").strip()
                title = str(entry.get("title") or "").strip()

                if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                    videos.append({
                        "video_id": video_id,
                        "title": title
                    })

            if videos:
                return True, videos[:VIDEO_LIMIT], None

            errors.append("Channel resolved but no videos returned")

        except subprocess.TimeoutExpired:
            errors.append("Request timed out")

        except Exception as error:
            errors.append(str(error))

    return False, [], " | ".join(errors)


def main():
    channels = load_channels()

    passed = 0
    failed = 0
    skipped = 0

    print("=" * 65)
    print("YT-DLP CHANNEL RESOLUTION TEST")
    print("=" * 65)
    print(f"Total channels: {len(channels)}\n")

    for index, channel in enumerate(channels, 1):

        if channel.get("paused", False):
            skipped += 1
            print(f"[{index}/{len(channels)}] [SKIP] "
                  f"{channel.get('handle')}")
            continue

        handle = channel.get("handle", "Unknown")

        success, videos, error = test_channel(channel)

        if success:
            passed += 1

            print(f"\n[{index}/{len(channels)}] [PASS] {handle}")

            for video in videos:
                print(f"  ID: {video['video_id']}")
                print(f"  Title: {video['title']}")

        else:
            failed += 1

            print(f"\n[{index}/{len(channels)}] [FAIL] {handle}")
            print(f"  Reason: {error}")

        time.sleep(0.5)

    print("\n" + "=" * 65)
    print("FINAL TEST RESULTS")
    print("=" * 65)
    print(f"Total:   {len(channels)}")
    print(f"Passed:  {passed}")
    print(f"Failed:  {failed}")
    print(f"Skipped: {skipped}")
    print("=" * 65)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
