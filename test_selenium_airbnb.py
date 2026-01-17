#!/usr/bin/env python3
"""
Test Selenium scraping with Airbnb
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def test_selenium_scrape():
    """Test Selenium scraping"""
    
    listing_url = "https://www.airbnb.com/rooms/1376252243023110567"
    
    print(f"Testing Selenium scraping of: {listing_url}")
    
    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # Remove this to see browser
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        print("Chrome driver initialized successfully")
        
        # Navigate to the page
        print("Loading page...")
        driver.get(listing_url)
        
        # Wait for page to load
        print("Waiting for page to load...")
        time.sleep(5)
        
        # Try to find title elements
        print("Looking for title elements...")
        
        # Common title selectors for Airbnb
        title_selectors = [
            'h1[data-testid="listing-title"]',
            'h1',
            '[data-testid="listing-title"]',
            'h1._1199f3l8',  # Common Airbnb class
            '._1199f3l8'
        ]
        
        title_found = None
        for selector in title_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"Found {len(elements)} elements with selector '{selector}':")
                    for i, elem in enumerate(elements[:3]):  # Show first 3
                        text = elem.text.strip()
                        if text:
                            print(f"  {i+1}: {text}")
                            if not title_found and len(text) > 5:
                                title_found = text
            except Exception as e:
                print(f"Error with selector '{selector}': {e}")
        
        # Look for any h1, h2, h3 tags with content
        print("\nLooking for any heading tags...")
        for tag in ['h1', 'h2', 'h3']:
            elements = driver.find_elements(By.TAG_NAME, tag)
            if elements:
                print(f"Found {len(elements)} {tag} tags:")
                for i, elem in enumerate(elements[:5]):
                    text = elem.text.strip()
                    if text:
                        print(f"  {i+1}: {text}")
        
        # Look for elements with common Airbnb data attributes
        print("\nLooking for elements with data-testid...")
        data_elements = driver.find_elements(By.CSS_SELECTOR, '[data-testid]')
        print(f"Found {len(data_elements)} elements with data-testid")
        
        # Get page title
        page_title = driver.title
        print(f"\nPage title: {page_title}")
        
        # Check if we're getting blocked or redirected
        current_url = driver.current_url
        print(f"Current URL: {current_url}")
        
        # Get page source length
        page_source = driver.page_source
        print(f"Page source length: {len(page_source)}")
        
        # Look for any text that might indicate content is loading
        if "loading" in page_source.lower() or "spinner" in page_source.lower():
            print("Page seems to still be loading, waiting longer...")
            time.sleep(10)
            
            # Try again after longer wait
            print("Trying to find content again...")
            for tag in ['h1', 'h2', 'h3']:
                elements = driver.find_elements(By.TAG_NAME, tag)
                if elements:
                    print(f"After waiting - Found {len(elements)} {tag} tags:")
                    for i, elem in enumerate(elements[:3]):
                        text = elem.text.strip()
                        if text:
                            print(f"  {i+1}: {text}")
        
        # Save screenshot for debugging
        try:
            driver.save_screenshot('airbnb_selenium_screenshot.png')
            print("Screenshot saved as: airbnb_selenium_screenshot.png")
        except Exception as e:
            print(f"Could not save screenshot: {e}")
        
        # Save page source
        with open('airbnb_selenium_source.html', 'w', encoding='utf-8') as f:
            f.write(page_source)
        print("Page source saved as: airbnb_selenium_source.html")
        
        if title_found:
            print(f"\n✅ Successfully found title: {title_found}")
        else:
            print("\n❌ No title found - page might be blocked or require additional waiting")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()

if __name__ == '__main__':
    test_selenium_scrape() 