import urllib.request
import xml.etree.ElementTree as ET
import json
from datetime import datetime

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

all_videos = []
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

for ch in CHANNELS:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['id']}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            # YouTube XML uses Atom namespace
            entries = root.findall('{http://www.w3.org/2005/Atom}entry')
            for entry in entries[:3]:
                title_elem = entry.find('{http://www.w3.org/2005/Atom}title')
                link_elem = entry.find('{http://www.w3.org/2005/Atom}link')
                published_elem = entry.find('{http://www.w3.org/2005/Atom}published')
                video_id_elem = entry.find('{http://www.youtube.com/xml/schemas/2015}videoId')
                
                title = title_elem.text if title_elem is not None else "No Title"
                link = link_elem.attrib.get('href', '#') if link_elem is not None else "#"
                published = published_elem.text if published_elem is not None else datetime.utcnow().isoformat()
                v_id = video_id_elem.text if video_id_elem is not None else ""
                
                all_videos.append({
                    "channel": ch['name'],
                    "title": title,
                    "link": link,
                    "published": published,
                    "thumbnail": f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg" if v_id else ""
                })
    except Exception as e:
        print(f"Error fetching {ch['name']}: {e}")

all_videos.sort(key=lambda x: x['published'], reverse=True)

output = {
    "last_updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    "videos": all_videos
}

with open("videos.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"Saved videos.json with {len(all_videos)} items.")
