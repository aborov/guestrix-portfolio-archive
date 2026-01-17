#!/usr/bin/env python3
"""
Diagnostic script to identify Chrome driver issues on staging
"""
import os
import sys
import subprocess
import time

def check_chrome_installation():
    print("🔍 Checking Chrome/Chromium installation...")
    
    # Check if Chrome is installed
    chrome_paths = [
        '/usr/bin/google-chrome',
        '/usr/bin/chromium-browser',
        '/snap/bin/chromium',
        '/usr/bin/chromium'
    ]
    
    chrome_found = False
    for path in chrome_paths:
        if os.path.exists(path):
            print(f"✅ Chrome found at: {path}")
            chrome_found = True
            break
    
    if not chrome_found:
        print("❌ Chrome/Chromium not found in common locations")
        return False
    
    # Check Chrome version
    try:
        result = subprocess.run([chrome_paths[0], '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✅ Chrome version: {result.stdout.strip()}")
        else:
            print(f"⚠️  Chrome version check failed: {result.stderr}")
    except Exception as e:
        print(f"⚠️  Chrome version check error: {e}")
    
    return True

def check_chromedriver():
    print("\n🔍 Checking ChromeDriver...")
    
    # Check if chromedriver is in PATH
    try:
        result = subprocess.run(['which', 'chromedriver'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            chromedriver_path = result.stdout.strip()
            print(f"✅ ChromeDriver found at: {chromedriver_path}")
            
            # Check ChromeDriver version
            try:
                version_result = subprocess.run(['chromedriver', '--version'], 
                                             capture_output=True, text=True, timeout=10)
                if version_result.returncode == 0:
                    print(f"✅ ChromeDriver version: {version_result.stdout.strip()}")
                else:
                    print(f"⚠️  ChromeDriver version check failed: {version_result.stderr}")
            except Exception as e:
                print(f"⚠️  ChromeDriver version check error: {e}")
                
        else:
            print("❌ ChromeDriver not found in PATH")
            return False
    except Exception as e:
        print(f"❌ ChromeDriver check error: {e}")
        return False
    
    return True

def test_selenium_import():
    print("\n🔍 Testing Selenium imports...")
    
    try:
        from selenium import webdriver
        print("✅ Selenium imported successfully")
        
        from selenium.webdriver.chrome.options import Options
        print("✅ Chrome options imported successfully")
        
        return True
    except ImportError as e:
        print(f"❌ Selenium import failed: {e}")
        return False

def test_chrome_driver_creation():
    print("\n🔍 Testing Chrome driver creation...")
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        print("Creating Chrome options...")
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1024,768')
        
        print("Creating Chrome driver...")
        start_time = time.time()
        
        driver = webdriver.Chrome(options=options)
        
        creation_time = time.time() - start_time
        print(f"✅ Chrome driver created successfully in {creation_time:.2f} seconds")
        
        # Test basic functionality
        print("Testing driver functionality...")
        driver.get('https://example.com')
        title = driver.title
        print(f"✅ Page loaded: {title}")
        
        driver.quit()
        print("✅ Driver closed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Chrome driver creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 Chrome/ChromeDriver Diagnostic Tool")
    print("=" * 50)
    
    chrome_ok = check_chrome_installation()
    driver_ok = check_chromedriver()
    selenium_ok = test_selenium_import()
    
    if not all([chrome_ok, driver_ok, selenium_ok]):
        print("\n❌ Prerequisites not met. Cannot test driver creation.")
        return
    
    print("\n🧪 Testing Chrome driver creation...")
    driver_creation_ok = test_chrome_driver_creation()
    
    print("\n📊 Summary:")
    print(f"   Chrome installation: {'✅' if chrome_ok else '❌'}")
    print(f"   ChromeDriver: {'✅' if driver_ok else '❌'}")
    print(f"   Selenium imports: {'✅' if selenium_ok else '❌'}")
    print(f"   Driver creation: {'✅' if driver_creation_ok else '❌'}")
    
    if driver_creation_ok:
        print("\n🎉 Chrome setup is working correctly!")
    else:
        print("\n⚠️  Chrome setup has issues that need to be resolved.")

if __name__ == "__main__":
    main()
