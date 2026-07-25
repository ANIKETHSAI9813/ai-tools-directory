import json
import urllib.request
import xml.etree.ElementTree as ET

# Fetching real product launches from Product Hunt's AI Feed
FEED_URL = "https://www.producthunt.com/feed?category=artificial-intelligence"

def fetch_latest():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        req = urllib.request.Request(FEED_URL, headers=headers)
        xml_data = urllib.request.urlopen(req).read()
        root = ET.fromstring(xml_data)

        # Load existing tools to prevent deleting manual/curated entries
        try:
            with open('data.json', 'r') as f:
                existing_tools = json.load(f)
        except Exception:
            existing_tools = []

        existing_names = {tool['name'].lower() for tool in existing_tools}
        new_tools = []

        # Parse Atom/RSS feed items
        namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
        entries = root.findall('atom:entry', namespaces) if root.tag.endswith('feed') else root.findall('.//item')

        for entry in entries[:10]:
            title_node = entry.find('atom:title', namespaces) if root.tag.endswith('feed') else entry.find('title')
            link_node = entry.find('atom:link', namespaces) if root.tag.endswith('feed') else entry.find('link')
            
            title = title_node.text.strip() if title_node is not None else "AI Tool"
            
            if root.tag.endswith('feed'):
                link = link_node.attrib.get('href', '') if link_node is not None else ''
            else:
                link = link_node.text.strip() if link_node is not None else ''

            if title.lower() not in existing_names and link:
                new_tools.append({
                    "id": str(len(existing_tools) + len(new_tools) + 1),
                    "name": title,
                    "description": f"Newly launched AI product: {title}",
                    "category": "AI & Tech",
                    "affiliate_link": link,
                    "featured": False
                })

        # Prepend new tools so latest appear first
        combined_tools = new_tools + existing_tools

        with open('data.json', 'w') as f:
            json.dump(combined_tools, f, indent=2)

        print(f"Successfully added {len(new_tools)} real new AI tools.")

    except Exception as e:
        print(f"Error fetching feed: {e}")

if __name__ == "__main__":
    fetch_latest()
