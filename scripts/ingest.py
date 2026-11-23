def fetch_via_yt_html(channel_id, handle, fallback_title):
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        import scrapetube

        videos = []

        if channel_id and str(channel_id).startswith("UC"):
            items = scrapetube.get_channel(
                channel_id=str(channel_id),
                limit=MAX_VIDEOS_PER_CHANNEL
            )

        else:
            clean_handle = str(handle).replace("@", "").strip()

            items = scrapetube.get_channel(
                channel_url=f"https://www.youtube.com/@{clean\_handle}",
                limit=MAX_VIDEOS_PER_CHANNEL
            )

        for item in items:
            vid = item.get("videoId")

            if not vid:
                continue

            title = ""

            title_obj = item.get("title", {})

            if isinstance(title_obj, dict):
                runs = title_obj.get("runs", [])

                if runs:
                    title = "".join(
                        r.get("text", "")
                        for r in runs
                        if isinstance(r, dict)
                    )

                else:
                    title = title_obj.get("simpleText", "")

            if not title:
                continue

            videos.append({
                "id": vid,
                "title": title.strip(),
                "channel_title": fallback_title,
                "handle": handle,
                "published_at": now_iso,
                "description": "",
                "thumbnail_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            })

            if len(videos) >= MAX_VIDEOS_PER_CHANNEL:
                break

        return videos

    except Exception:
        return []
