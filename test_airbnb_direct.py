#!/usr/bin/env python3
"""
Simple test script to debug Airbnb listing scraping
"""

import requests
from bs4 import BeautifulSoup
import json

def test_listing_scrape():
    """Test scraping a specific Airbnb listing"""
    
    # The listing URL we found
    listing_url = "https://www.airbnb.com/rooms/1376252243023110567"
    
    print(f"Testing direct scraping of: {listing_url}")
    
    # Set up session with headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    
    try:
        # Fetch the page
        print("Fetching page...")
        response = session.get(listing_url, timeout=30)
        response.raise_for_status()
        print(f"Page fetched successfully. Status: {response.status_code}")
        print(f"Content length: {len(response.text)}")
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Debug: Look for common elements
        print(f"\nFound {len(soup.find_all('h1'))} h1 tags")
        print(f"Found {len(soup.find_all('h2'))} h2 tags")
        print(f"Found {len(soup.find_all('h3'))} h3 tags")
        
        # Try to find title
        h1_tags = soup.find_all('h1')
        if h1_tags:
            print(f"\nH1 tags found:")
            for i, h1 in enumerate(h1_tags[:3]):  # Show first 3
                print(f"  {i+1}: {h1.get_text(strip=True)}")
        
        # Look for any text that might be a title
        title_candidates = []
        for h_tag in soup.find_all(['h1', 'h2', 'h3']):
            text = h_tag.get_text(strip=True)
            if text and len(text) > 5 and len(text) < 100:
                title_candidates.append(text)
        
        if title_candidates:
            print(f"\nPotential titles:")
            for i, candidate in enumerate(title_candidates[:5]):
                print(f"  {i+1}: {candidate}")
        
        # Look for script tags with JSON data
        script_tags = soup.find_all('script')
        json_scripts = []
        for script in script_tags:
            if script.string:
                text = script.string.strip()
                if text.startswith('{') or 'window.' in text:
                    json_scripts.append(text[:100] + "..." if len(text) > 100 else text)
        
        print(f"\nFound {len(json_scripts)} potentially interesting script tags")
        if json_scripts:
            print("First few script contents:")
            for i, script in enumerate(json_scripts[:3]):
                print(f"  {i+1}: {script}")
        
        # Look for data attributes
        elements_with_data = soup.find_all(attrs={"data-testid": True})
        print(f"\nFound {len(elements_with_data)} elements with data-testid")
        
        testids = set()
        for elem in elements_with_data:
            testid = elem.get('data-testid')
            if testid:
                testids.add(testid)
        
        if testids:
            print("Data-testid values found:")
            for testid in sorted(list(testids))[:10]:  # Show first 10
                print(f"  - {testid}")
        
        # Check if we can find any listing-related content
        listing_keywords = ['bedroom', 'bathroom', 'guest', 'bed', 'amenity', 'wifi', 'kitchen']
        page_text = soup.get_text().lower()
        
        found_keywords = []
        for keyword in listing_keywords:
            if keyword in page_text:
                found_keywords.append(keyword)
        
        print(f"\nFound listing-related keywords: {found_keywords}")
        
        # Save the HTML for inspection
        with open('listing_page_debug.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"\nSaved full HTML to: listing_page_debug.html")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_listing_scrape() 