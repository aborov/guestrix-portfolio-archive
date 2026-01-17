#!/usr/bin/env python3
"""
Test the fixed Airbnb scraper with Selenium
"""

import sys
sys.path.append('concierge')

def test_fixed_scraper():
    """Test the fixed scraper with Selenium"""
    
    # Import with path modification to avoid websocket conflict
    original_path = sys.path.copy()
    if '.' in sys.path:
        sys.path.remove('.')
    if '' in sys.path:
        sys.path.remove('')
    
    try:
        from concierge.utils.airbnb_scraper import AirbnbScraper
        sys.path = original_path
        
        print("Creating scraper with Selenium enabled...")
        scraper = AirbnbScraper(use_selenium=True)
        
        user_url = "https://www.airbnb.com/users/show/13734172"
        print(f"Testing scraper with: {user_url}")
        
        result = scraper.scrape_user_properties(user_url)
        
        print(f"\nResults:")
        print(f"  User URL: {result.get('user_url', 'N/A')}")
        print(f"  Listings found: {result.get('listings_count', 0)}")
        print(f"  Knowledge items generated: {result.get('knowledge_items_count', 0)}")
        
        # Show listing details
        listings = result.get('listings', [])
        if listings:
            print(f"\nListing Details:")
            for i, listing in enumerate(listings, 1):
                print(f"  {i}. Title: {listing.get('title', 'Unknown')}")
                print(f"     Location: {listing.get('location', 'Unknown')}")
                print(f"     Amenities: {len(listing.get('amenities', []))}")
                print(f"     Images: {len(listing.get('images', []))}")
                print(f"     Rating: {listing.get('reviews', {}).get('rating', 'N/A')}")
                print(f"     URL: {listing.get('url', 'N/A')}")
        
        # Save results
        import json
        from datetime import datetime
        filename = f"fixed_scraper_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {filename}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.path = original_path

if __name__ == '__main__':
    test_fixed_scraper() 