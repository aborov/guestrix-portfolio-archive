#!/usr/bin/env python3
"""
Test script to verify Chrome scraper functionality on staging
"""
from concierge.utils.airbnb_scraper import AirbnbScraper

def test_chrome_scraper():
    print("🧪 Testing Chrome scraper functionality...")
    
    try:
        # Create scraper with Selenium enabled
        scraper = AirbnbScraper(use_selenium=True)
        print(f"✅ Scraper created successfully")
        print(f"   Selenium enabled: {scraper.use_selenium}")
        print(f"   Driver type: {type(scraper.driver).__name__}")
        
        # Test basic page loading
        print("\n🌐 Testing basic page loading...")
        test_url = "https://example.com"
        content = scraper._get_page_content(test_url)
        
        if content:
            print(f"✅ Page loaded successfully: {len(content)} characters")
            # Show first 200 characters
            preview = content[:200].replace('\n', ' ').strip()
            print(f"   Preview: {preview}...")
        else:
            print("❌ Failed to load page content")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        if 'scraper' in locals() and scraper.driver:
            scraper.driver.quit()
            print("🧹 Driver cleaned up")

if __name__ == "__main__":
    test_chrome_scraper()
