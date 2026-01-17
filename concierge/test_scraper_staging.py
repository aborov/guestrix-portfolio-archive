#!/usr/bin/env python3
"""
Test script to verify Selenium + Firefox headless scraping on staging server
"""

import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def test_selenium_firefox_headless():
    """Test Selenium with Firefox in headless mode"""
    print("🧪 Testing Selenium + Firefox headless scraping...")
    
    # Set up Firefox options for headless mode
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    # Set up geckodriver service
    geckodriver_path = '/snap/bin/geckodriver'
    if not os.path.exists(geckodriver_path):
        print(f"❌ Geckodriver not found at {geckodriver_path}")
        return False
    
    service = Service(geckodriver_path)
    
    try:
        print("🚀 Creating Firefox driver...")
        driver = webdriver.Firefox(service=service, options=options)
        print("✅ Firefox driver created successfully")
        
        # Test basic functionality
        print("🌐 Loading test page...")
        driver.get('https://www.google.com')
        
        # Wait for page to load
        wait = WebDriverWait(driver, 10)
        search_box = wait.until(EC.presence_of_element_located((By.NAME, "q")))
        
        print(f"✅ Page loaded: {driver.title}")
        print(f"✅ Search box found: {search_box.get_attribute('placeholder')}")
        
        # Test search functionality
        search_box.send_keys("Selenium test")
        search_box.submit()
        
        # Wait for results
        time.sleep(2)
        print(f"✅ Search results page loaded: {driver.title}")
        
        # Close driver
        driver.quit()
        print("✅ Driver closed successfully")
        print("🎉 Selenium + Firefox headless test PASSED!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_airbnb_scraper_imports():
    """Test if Airbnb scraper modules can be imported"""
    print("\n🧪 Testing Airbnb scraper imports...")
    
    try:
        # Test basic imports
        from selenium import webdriver
        print("✅ Selenium imported successfully")
        
        # Test if we can access the scraper modules
        import sys
        sys.path.append('/app/dashboard')
        
        from concierge.utils.airbnb_scraper import AirbnbScraper
        print("✅ AirbnbScraper imported successfully")
        
        # Test basic scraper functionality
        scraper = AirbnbScraper()
        print("✅ AirbnbScraper instance created successfully")
        
        print("🎉 Airbnb scraper imports test PASSED!")
        return True
        
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 STAGING SCRAPER FUNCTIONALITY TEST")
    print("=" * 60)
    
    # Test 1: Basic Selenium + Firefox
    test1_passed = test_selenium_firefox_headless()
    
    # Test 2: Airbnb scraper imports
    test2_passed = test_airbnb_scraper_imports()
    
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)
    print(f"✅ Selenium + Firefox headless: {'PASSED' if test1_passed else 'FAILED'}")
    print(f"✅ Airbnb scraper imports: {'PASSED' if test2_passed else 'FAILED'}")
    
    if test1_passed and test2_passed:
        print("\n🎉 ALL TESTS PASSED! Scraper is ready for use.")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED. Check the output above for details.")
        sys.exit(1)
