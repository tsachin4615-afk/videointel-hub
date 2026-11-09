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
headers = {'User-Agent': 'Mozilla/5.0'}

for ch in CHANNELS:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['id']}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            ns = {'atom': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
            
            for entry in root.findall('atom:entry', ns)[:3]:
                title = entry.find('atom:title', ns).text
                link = entry.find('atom:link', ns).attrib['href']
                published = entry.find('atom:published', ns).text
                video_id = entry.find('yt:videoId', ns).text
                
                all_videos.append({
                    "channel": ch['name'],
                    "title": title,
                    "link": link,
                    "published": published,
                    "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
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
