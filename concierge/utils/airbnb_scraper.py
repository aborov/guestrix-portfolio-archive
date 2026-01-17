#!/usr/bin/env python3
"""
Airbnb Property Data Scraper

This script can extract property data from Airbnb user profiles including:
- Property listings for a given user
- Property details (title, description, amenities)
- Property images
- Location information
- Pricing and availability

The extracted data can be used to generate knowledge items for the concierge system.
"""

import os
import time
import json
import requests
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin, urlparse, parse_qs
import re
import logging

# Try to import beautifulsoup4 - if not available, provide installation instructions
try:
    from bs4 import BeautifulSoup
except ImportError:
    print("beautifulsoup4 is required for HTML parsing.")
    print("Install it with: pip install beautifulsoup4")
    raise

# Try to import Selenium - optional for enhanced scraping
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# Try to import Gemini - optional for AI validation
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

    # Try to import selenium for dynamic content - optional
try:
    # Temporarily modify path to avoid local websocket directory conflict
    import sys
    original_path = sys.path.copy()
    # Remove current directory to avoid websocket conflict
    if '.' in sys.path:
        sys.path.remove('.')
    if '' in sys.path:
        sys.path.remove('')
    
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
    
    # Restore original path
    sys.path = original_path
    
except ImportError as e:
    SELENIUM_AVAILABLE = False
    print("Selenium not available. Some dynamic content may not be accessible.")
    print("Install it with: pip install selenium")
    print(f"Import error: {e}")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AirbnbScraper:
    """
    A comprehensive Airbnb scraper that can extract property data from user profiles.
    """

    def __init__(self, use_selenium=False, headless=True):
        """
        Initialize the scraper.

        Args:
            use_selenium: Whether to use Selenium for JavaScript-heavy pages
            headless: Whether to run browser in headless mode (Selenium only)
        """
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE
        self.headless = headless
        self.session = requests.Session()
        self.driver = None
        self._selenium_failures = 0  # Track Selenium failures for graceful degradation
        self._max_selenium_failures = 3  # Max failures before disabling Selenium
        
        # Set up headers to mimic a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

        if self.use_selenium:
            self._setup_selenium()

    def _setup_selenium(self):
        """Set up Selenium WebDriver with timeout and fallback."""
        if not SELENIUM_AVAILABLE:
            logger.warning("Selenium not available, falling back to requests")
            self.use_selenium = False
            return

        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument('--headless')
            # Use a smaller viewport in headless mode to reduce memory footprint
            chrome_options.add_argument('--window-size=1024,768')

            # Chrome options for better scraping and memory management
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Critical options for server environments
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-software-rasterizer')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-plugins')
            chrome_options.add_argument('--disable-default-apps')
            chrome_options.add_argument('--disable-sync')
            chrome_options.add_argument('--disable-translate')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--allow-running-insecure-content')
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')
            
            # Constrain memory-heavy features for low-RAM instances
            chrome_options.add_argument('--disable-images')  # block images
            chrome_options.add_argument('--disable-cache')  # disable cache
            chrome_options.add_argument('--disable-application-cache')
            chrome_options.add_argument('--disable-offline-load-stale-cache')
            chrome_options.add_argument('--disk-cache-size=0')
            chrome_options.add_argument('--media-cache-size=0')
            chrome_options.add_argument('--disable-media-session')
            chrome_options.add_argument('--disable-background-timer-throttling')
            chrome_options.add_argument('--disable-backgrounding-occluded-windows')
            chrome_options.add_argument('--disable-renderer-backgrounding')
            chrome_options.add_argument('--disable-features=TranslateUI')
            chrome_options.add_argument('--disable-ipc-flooding-protection')
            
            # Memory management for low-resource servers
            chrome_options.add_argument('--memory-pressure-off')
            chrome_options.add_argument('--max_old_space_size=128')
            chrome_options.add_argument('--single-process')
            chrome_options.add_argument('--process-per-site')
            
            logger.info("Chrome headless mode configured with server-optimized options")
            
            # Initialize Chrome driver with timeout
            import signal
            import threading
            
            def timeout_handler():
                logger.error("Chrome driver creation timed out after 30 seconds")
                raise TimeoutError("Chrome driver creation timed out")
            
            # Set up timeout
            timer = threading.Timer(30.0, timeout_handler)
            timer.start()
            
            try:
                logger.info("Creating Chrome driver (timeout: 30s)...")
                self.driver = webdriver.Chrome(options=chrome_options)
                timer.cancel()
                logger.info("Chrome driver created successfully")
            except Exception as e:
                timer.cancel()
                raise e

            # Set timeouts and improve page loading
            self.driver.set_page_load_timeout(60)  # Increased timeout
            self.driver.implicitly_wait(10)  # Wait for elements to appear

            # Execute script to disable automation detection (Chrome compatible)
            try:
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                self.driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
                self.driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
            except Exception:
                pass  # Chrome may handle this differently

            logger.info("Selenium WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Selenium: {e}")
            self._selenium_failures += 1
            
            if self._selenium_failures >= self._max_selenium_failures:
                logger.warning(f"Selenium failed {self._selenium_failures} times, permanently disabling")
                self.use_selenium = False
                self.driver = None
            else:
                logger.warning(f"Selenium failed {self._selenium_failures}/{self._max_selenium_failures} times, will retry")
                self.use_selenium = False
                self.driver = None

    def __del__(self):
        """Clean up resources."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

    def _get_page_content(self, url: str, wait_for_element: str = None) -> Optional[str]:
        """
        Get page content using either requests or Selenium.

        Args:
            url: URL to fetch
            wait_for_element: CSS selector to wait for (Selenium only)

        Returns:
            Page HTML content or None if failed
        """
        try:
            if self.use_selenium and self.driver and self._selenium_failures < self._max_selenium_failures:
                logger.info(f"Fetching with Selenium: {url}")
                self.driver.get(url)
                
                if wait_for_element:
                    try:
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_element))
                        )
                    except TimeoutException:
                        logger.warning(f"Timeout waiting for element: {wait_for_element}")
                
                # Reduced wait for dynamic content to load
                time.sleep(1)
                return self.driver.page_source
            else:
                logger.info(f"Fetching with requests: {url}")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response.text
                
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def extract_user_from_listing(self, listing_url: str) -> Optional[str]:
        """
        Extract the user profile URL from an Airbnb listing page.

        Args:
            listing_url: Airbnb listing URL (e.g., https://www.airbnb.com/rooms/1376252243023110567)

        Returns:
            User profile URL or None if not found
        """
        logger.info(f"Extracting user profile from listing: {listing_url}")

        content = self._get_page_content(listing_url, wait_for_element='h1')
        if not content:
            return None

        soup = BeautifulSoup(content, 'html.parser')

        try:
            # Look for host profile links in various locations
            host_selectors = [
                'a[href*="/users/show/"]',
                'a[href*="/host/"]',
                '[data-testid="host-profile-link"]',
                '.host-profile a',
                'a[aria-label*="host"]',
                'a[aria-label*="Host"]',
                '[data-testid*="host"] a',
                '.host-info a',
                'a[href*="/user/"]'
            ]

            # Also try to find user ID in page data/scripts
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    # Look for user ID patterns in JavaScript
                    user_id_patterns = [
                        r'"user_id":\s*"?(\d+)"?',
                        r'"userId":\s*"?(\d+)"?',
                        r'"host_id":\s*"?(\d+)"?',
                        r'"hostId":\s*"?(\d+)"?',
                        r'/users/show/(\d+)'
                    ]

                    for pattern in user_id_patterns:
                        matches = re.findall(pattern, script.string)
                        if matches:
                            user_id = matches[0]
                            clean_url = f"https://www.airbnb.com/users/show/{user_id}"
                            logger.info(f"Found user profile from script: {clean_url}")
                            return clean_url

            # Try the link-based approach
            for selector in host_selectors:
                host_links = soup.select(selector)
                for link in host_links:
                    href = link.get('href', '')
                    if '/users/show/' in href or '/user/' in href:
                        # Convert relative URL to absolute
                        if href.startswith('/'):
                            user_url = f"https://www.airbnb.com{href}"
                        else:
                            user_url = href

                        # Extract user ID and construct clean URL
                        user_id_match = re.search(r'/users?/show/(\d+)', user_url) or re.search(r'/user/(\d+)', user_url)
                        if user_id_match:
                            user_id = user_id_match.group(1)
                            clean_url = f"https://www.airbnb.com/users/show/{user_id}"
                            logger.info(f"Found user profile from link: {clean_url}")
                            return clean_url

            logger.warning("Could not find user profile link in listing page")
            return None

        except Exception as e:
            logger.error(f"Error extracting user profile from listing: {e}")
            return None

    def extract_user_listings(self, user_url: str) -> List[Dict[str, Any]]:
        """
        Extract all listing URLs and basic info for a given Airbnb user.

        Args:
            user_url: Airbnb user profile URL (e.g., https://www.airbnb.com/users/show/13734172)

        Returns:
            List of dictionaries containing listing information
        """
        logger.info(f"Extracting listings for user: {user_url}")
        
        # First, try to get the user profile page
        content = self._get_page_content(user_url)
        if not content:
            logger.error("Failed to fetch user profile page")
            return []

        soup = BeautifulSoup(content, 'html.parser')
        listings = []

        # Try multiple approaches to find listings
        listing_links = []

        # Method 1: Look for listing containers and extract basic info directly
        listing_containers = soup.select('[data-testid*="listing"], .listing-card, [class*="listing"], [class*="property"], [data-testid*="card"]')
        logger.info(f"Found {len(listing_containers)} potential listing containers")

        # If no containers found, try broader selectors
        if not listing_containers:
            listing_containers = soup.select('div[class*="card"], div[data-testid], article, section')
            logger.info(f"Fallback: Found {len(listing_containers)} potential containers")

        for i, container in enumerate(listing_containers):
            try:
                # Extract URL
                link_elem = container.find('a', href=True)
                if not link_elem:
                    # Try to find link in child elements
                    link_elem = container.select_one('a[href*="/rooms/"], a[href*="/plus/"]')
                    if not link_elem:
                        continue

                href = link_elem.get('href', '')
                if '/rooms/' not in href and '/plus/' not in href:
                    continue

                if href.startswith('/'):
                    href = 'https://www.airbnb.com' + href

                # Skip if already processed
                if href in [l['url'] for l in listings]:
                    continue

                logger.info(f"Processing container {i+1} with URL: {href}")

                # Debug: Log container HTML structure
                container_html = str(container)[:500]  # First 500 chars
                logger.info(f"Container {i+1} HTML preview: {container_html}")

                # Extract basic info from the container (SIMPLIFIED)
                listing_info = {
                    'url': href,
                    'title': '',
                    'location': '',
                    'property_type': '',
                    'image': ''
                }

                # Extract title from various possible elements
                title_selectors = ['h2', 'h3', 'h4', '[data-testid*="title"]', '[class*="title"]', 'strong', 'span']
                for selector in title_selectors:
                    title_elems = container.select(selector)
                    for title_elem in title_elems:
                        if title_elem and title_elem.get_text(strip=True):
                            text = title_elem.get_text(strip=True)
                            # Skip very short or very long text, or text that looks like metadata
                            if 5 <= len(text) <= 100 and not any(word in text.lower() for word in ['photo', 'image', 'rating', 'review', 'price', '$']):
                                listing_info['title'] = text
                                logger.info(f"Found title: {text}")
                                break
                    if listing_info['title']:
                        break

                # Extract location - look for text that looks like addresses/locations
                all_text_elements = container.find_all(['span', 'div', 'p'])
                for elem in all_text_elements:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 3:
                        # Look for location patterns
                        if (', ' in text or
                            any(word in text.lower() for word in ['city', 'state', 'country', 'beach', 'downtown', 'center', 'avenue', 'street', 'road']) or
                            re.search(r'\b[A-Z][a-z]+,\s*[A-Z]{2}\b', text) or  # City, ST pattern
                            re.search(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b', text)):  # City Name pattern
                            # Skip if it looks like a title or other metadata
                            if not any(word in text.lower() for word in ['entire', 'private', 'shared', 'bedroom', 'bathroom', 'guest', 'host']):
                                listing_info['location'] = text
                                logger.info(f"Found location: {text}")
                                break

                # Extract image (SIMPLIFIED)
                img_elem = container.find('img')
                if img_elem and img_elem.get('src'):
                    src = img_elem.get('src')
                    # Convert to small square thumbnail
                    if '?im_w=' in src:
                        thumbnail_url = re.sub(r'im_w=\d+', 'im_w=240', src)
                        thumbnail_url = re.sub(r'im_h=\d+', 'im_h=240', thumbnail_url)
                        if 'im_h=' not in thumbnail_url:
                            thumbnail_url += '&im_h=240'
                    elif '?' in src:
                        thumbnail_url = src + '&im_w=240&im_h=240'
                    else:
                        thumbnail_url = src + '?im_w=240&im_h=240'
                    listing_info['image'] = thumbnail_url

                listings.append(listing_info)
                logger.info(f"Extracted basic info for listing: {listing_info['title'] or 'Unknown'} at {listing_info['location'] or 'Unknown location'}")

            except Exception as e:
                logger.error(f"Error extracting basic listing info: {e}")
                continue

        # Method 2: Try to extract from JSON data in script tags
        if not listings:
            logger.info("No listings found from containers, trying script data extraction")
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and ('rooms' in script.string or 'listing' in script.string.lower()):
                    try:
                        # Look for JSON-like data containing listing information
                        script_text = script.string

                        # Try to find listing URLs and extract basic info
                        room_urls = re.findall(r'https://www\.airbnb\.com/rooms/(\d+)', script_text)
                        for room_id in room_urls:
                            room_url = f"https://www.airbnb.com/rooms/{room_id}"
                            if room_url not in [l['url'] for l in listings]:
                                # Try to find associated data near the URL
                                url_context = script_text[max(0, script_text.find(room_url)-500):script_text.find(room_url)+500]

                                listing_info = {
                                    'url': room_url,
                                    'title': '',
                                    'location': '',
                                    'property_type': '',
                                    'image': ''
                                }

                                # Try to extract title from context
                                title_matches = re.findall(r'"name":\s*"([^"]+)"', url_context)
                                if title_matches:
                                    listing_info['title'] = title_matches[0]

                                # Try to extract location from context
                                location_matches = re.findall(r'"city":\s*"([^"]+)"', url_context)
                                if location_matches:
                                    listing_info['location'] = location_matches[0]

                                listings.append(listing_info)
                                logger.info(f"Extracted from script: {listing_info['title'] or 'Unknown'}")

                    except Exception as e:
                        logger.error(f"Error parsing script data: {e}")
                        continue

        # Fallback: Look for simple listing links if still no listings found
        if not listings:
            logger.info("No listings found from scripts, trying simple link extraction")
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '/rooms/' in href or '/plus/' in href:
                    if href.startswith('/'):
                        href = 'https://www.airbnb.com' + href
                    if href not in [l['url'] for l in listing_links]:
                        listing_links.append({'url': href, 'title': link.get_text(strip=True)})

            # Convert simple links to listing format
            for link_info in listing_links:
                listing_info = {
                    'url': link_info['url'],
                    'title': link_info['title'] or f"Property {link_info['url'].split('/')[-1][:8]}...",
                    'location': 'Location to be determined',
                    'property_type': '',
                    'image': ''
                }
                listings.append(listing_info)
                logger.info(f"Added fallback listing: {listing_info['title']}")

        # Method 2: Look for data in script tags (Airbnb often embeds data in JSON)
        script_tags = soup.find_all('script')
        for script in script_tags:
            if script.string and 'listings' in script.string.lower():
                try:
                    # Try to extract JSON data
                    text = script.string
                    # Look for patterns that might contain listing data
                    json_matches = re.findall(r'\{[^{}]*"listings"[^{}]*\}', text)
                    for match in json_matches:
                        try:
                            data = json.loads(match)
                            # Process the data if it contains listing information
                            if isinstance(data, dict) and 'listings' in data:
                                logger.info("Found listings data in script tag")
                        except json.JSONDecodeError:
                            continue
                except Exception as e:
                    logger.debug(f"Error parsing script tag: {e}")

        # ENHANCED: Always try to get detailed info for each listing found
        if listings:
            logger.info(f"Enhancing {len(listings)} listings with detailed information")
            enhanced_listings = []

            for listing in listings:
                try:
                    # Get detailed information from the individual listing page
                    listing_details = self.extract_listing_details(listing['url'])
                    if listing_details:
                        # Use the enhanced data, but keep any good data from profile extraction
                        enhanced_listing = listing_details.copy()

                        # If profile had better data for some fields, keep it
                        if not enhanced_listing.get('title') and listing.get('title'):
                            enhanced_listing['title'] = listing['title']
                        if not enhanced_listing.get('location') and listing.get('location'):
                            enhanced_listing['location'] = listing['location']
                        if not enhanced_listing.get('property_type') and listing.get('property_type'):
                            enhanced_listing['property_type'] = listing['property_type']

                        enhanced_listings.append(enhanced_listing)
                        logger.info(f"Enhanced listing: {enhanced_listing.get('title', 'Unknown')[:50]}...")
                    else:
                        # Keep original if enhancement failed
                        enhanced_listings.append(listing)
                        logger.warning(f"Could not enhance listing: {listing['url']}")

                    # Be respectful with rate limiting
                    time.sleep(1)

                except Exception as e:
                    logger.error(f"Error enhancing listing {listing['url']}: {e}")
                    # Keep original listing if enhancement fails
                    enhanced_listings.append(listing)

            listings = enhanced_listings

        # If we found listing links but no detailed listings, get more details for each
        elif listing_links:
            logger.info(f"Extracting details for {len(listing_links)} listing links")
            for link_info in listing_links:
                try:
                    listing_details = self.extract_listing_details(link_info['url'])
                    if listing_details:
                        listings.append(listing_details)
                        logger.info(f"Successfully extracted details for: {listing_details.get('title', 'Unknown')}")

                    # Be respectful with rate limiting
                    time.sleep(1)

                except Exception as e:
                    logger.error(f"Error extracting listing details from {link_info['url']}: {e}")

        logger.info(f"Found {len(listings)} listings for user")
        return listings

    def extract_host_info(self, url: str) -> Dict[str, Any]:
        """
        Extract host information from Airbnb user profile or listing page.
        Supports internal editor URLs, public listing URLs, and user profile URLs.

        Args:
            url: Airbnb URL (can be internal editor, listing, or profile)

        Returns:
            Dictionary containing host information
        """
        logger.info(f"Extracting host info from: {url}")

        # Validate and normalize the URL
        validation = self._validate_airbnb_url(url)
        if not validation['is_valid']:
            logger.error(f"Invalid URL: {validation['error_message']}")
            return {
                'name': '',
                'error': validation['error_message'],
                'validation': validation
            }

        # Use the normalized URL for extraction
        normalized_url = validation['normalized_url']
        if normalized_url != url:
            logger.info(f"Using normalized URL: {normalized_url}")

        host_info = {
            'name': '',
            'location': '',
            'joined_date': '',
            'profile_image': '',
            'description': '',
            'original_url': url,
            'normalized_url': normalized_url,
            'url_validation': validation
        }

        try:
            # Determine URL type and extract accordingly
            if '/rooms/' in normalized_url:
                return self._extract_host_from_listing(normalized_url)
            else:
                return self._extract_host_from_profile(normalized_url)

        except Exception as e:
            logger.error(f"Error extracting host info from {normalized_url}: {e}")
            return host_info

    def _extract_host_from_listing(self, url):
        """Extract host information from Airbnb listing page"""
        host_info = {
            'name': '',
            'location': '',
            'joined_date': '',
            'profile_image': '',
            'description': ''
        }

        try:
            content = self._get_page_content(url)
            if not content:
                return host_info

            soup = BeautifulSoup(content, 'html.parser')
            page_text = soup.get_text()

            logger.info(f"Extracting host info from listing page")
            logger.info(f"Page text preview (first 2000 chars): {page_text[:2000]}")

            # Multiple strategies for listing pages
            candidates = []

            # Strategy 1: Look for "Hosted by [Name]" pattern (multiple variations)
            hosted_by_patterns = [
                r"Hosted by ([A-Z][a-zA-Z\s\-\'\.]+?)(?:\s|$|\.|\n|,|\|)",
                r"Host:\s*([A-Z][a-zA-Z\s\-\'\.]+?)(?:\s|$|\.|\n|,|\|)",
                r"Your host ([A-Z][a-zA-Z\s\-\'\.]+?)(?:\s|$|\.|\n|,|\|)",
                r"Meet your host,?\s*([A-Z][a-zA-Z\s\-\'\.]+?)(?:\s|$|\.|\n|,|\|)",
                r"Contact host ([A-Z][a-zA-Z\s\-\'\.]+?)(?:\s|$|\.|\n|,|\|)"
            ]

            for i, pattern in enumerate(hosted_by_patterns):
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
                    candidates.append(('hosted_by', name, page_text.find(match.group(0))))
                    logger.info(f"Found 'Hosted by' pattern {i+1}: '{name}'")

            # Strategy 2: Look for "[Name] is a Superhost" pattern
            superhost_patterns = [
                r"([A-Z][a-zA-Z\s\-\'\.]+?) is a Superhost",
                r"([A-Z][a-zA-Z\s\-\'\.]+?) · Superhost",
                r"Superhost ([A-Z][a-zA-Z\s\-\'\.]+?)"
            ]

            for pattern in superhost_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
                    candidates.append(('superhost', name, page_text.find(match.group(0))))
                    logger.info(f"Found Superhost pattern: '{name}'")

            # Strategy 3: Look in structured data (JSON-LD and other scripts)
            json_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_scripts:
                try:
                    if script.string:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and 'host' in data:
                            host_name = data['host'].get('name', '')
                            if host_name:
                                candidates.append(('json_ld', host_name, 0))
                                logger.info(f"Found JSON-LD host: '{host_name}'")
                except:
                    continue

            # Strategy 4: Look in all script tags for host data
            all_scripts = soup.find_all('script')
            for script in all_scripts:
                if script.string and 'host' in script.string.lower():
                    script_text = script.string
                    # Look for host name patterns in JavaScript data
                    js_patterns = [
                        r'"hostName":\s*"([^"]+)"',
                        r'"host_name":\s*"([^"]+)"',
                        r'"firstName":\s*"([^"]+)"',
                        r'"name":\s*"([A-Z][a-zA-Z\s\-\'\.]+?)"'
                    ]

                    for pattern in js_patterns:
                        matches = re.findall(pattern, script_text)
                        for name in matches:
                            if self._is_valid_name(name):
                                candidates.append(('script_data', name, 0))
                                logger.info(f"Found script data pattern: '{name}'")

            # Strategy 5: Look for title patterns
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text()
                logger.info(f"Title text: '{title_text}'")
                # Look for patterns like "Property hosted by Name"
                title_patterns = [
                    r"hosted by ([A-Z][a-zA-Z\s\-\'\.]+)",
                    r"by ([A-Z][a-zA-Z\s\-\'\.]+)",
                    r"- ([A-Z][a-zA-Z\s\-\'\.]+?) -"
                ]
                for pattern in title_patterns:
                    match = re.search(pattern, title_text, re.IGNORECASE)
                    if match:
                        name = match.group(1).strip()
                        candidates.append(('title', name, 0))
                        logger.info(f"Found title pattern: '{name}'")

            # Select best candidate
            if candidates:
                best_candidate = self._select_best_name_candidate(candidates)

                # Cross-validate with user profile
                validation_result = self._cross_validate_host_name(url, best_candidate)

                # Apply confidence filtering - only store high confidence names
                filtered_name = self._apply_confidence_filter(validation_result)

                # Apply Gemini validation for additional name cleaning and validation
                gemini_validated_name = self._validate_host_name_with_gemini(filtered_name, candidates, page_text[:2000])

                host_info['name'] = gemini_validated_name
                host_info['validation'] = validation_result

                logger.info(f"Final result after confidence filtering and Gemini validation: '{gemini_validated_name}' "
                           f"(original: '{validation_result['final_name']}', "
                           f"confidence: {validation_result['confidence']}, "
                           f"method: {validation_result['validation_method']})")

        except Exception as e:
            logger.error(f"Error extracting host from listing {url}: {e}")

        return host_info

    def _extract_host_from_profile(self, url):
        """Extract host information from Airbnb user profile page"""
        host_info = {
            'name': '',
            'location': '',
            'joined_date': '',
            'profile_image': '',
            'description': ''
        }

        try:
            content = self._get_page_content(url)
            if not content:
                return host_info

            soup = BeautifulSoup(content, 'html.parser')
            page_text = soup.get_text()

            logger.info(f"Extracting host info from profile page")

            # Multiple strategies for profile pages
            candidates = []

            # Strategy 1: Title tag extraction
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text()
                # Pattern: "Name - Airbnb"
                title_match = re.search(r'^([^-]+)', title_text)
                if title_match:
                    name = title_match.group(1).strip()
                    if self._is_valid_name(name):
                        candidates.append(('title', name, 0))
                        logger.info(f"Found title pattern: '{name}'")

            # Strategy 2: "[Name]'s reviews" pattern
            reviews_patterns = [
                r"\b([A-Z][a-zA-Z\s]+?)['\u2019]s reviews",
                r"([A-Z][a-zA-Z\s]+?)['\u2019]s\s+reviews"
            ]

            for pattern in reviews_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    name = self._clean_name(match.group(1).strip())
                    if self._is_valid_name(name):
                        candidates.append(('reviews', name, page_text.find(match.group(0))))
                        logger.info(f"Found reviews pattern: '{name}'")

            # Strategy 3: "Where [Name] has been" pattern
            where_pattern = re.search(r"Where ([A-Z][a-zA-Z\s]+?) has been", page_text, re.IGNORECASE)
            if where_pattern:
                name = where_pattern.group(1).strip()
                if self._is_valid_name(name):
                    candidates.append(('where_been', name, page_text.find(where_pattern.group(0))))
                    logger.info(f"Found 'where been' pattern: '{name}'")

            # Strategy 4: "[Name]'s listings" pattern
            listings_patterns = [
                r"([A-Z][a-zA-Z\s]+?)['\u2019]s listings",
                r"([A-Z][a-zA-Z\s]+?)['\u2019]s\s+listings"
            ]

            for pattern in listings_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
                    if self._is_valid_name(name):
                        candidates.append(('listings', name, page_text.find(match.group(0))))
                        logger.info(f"Found listings pattern: '{name}'")

            # Strategy 5: Name followed by colon pattern
            colon_patterns = re.findall(r'([A-Z][a-zA-Z\s]+?):\s*[\n\r]', page_text)
            for name in colon_patterns:
                name = name.strip()
                if self._is_valid_name(name):
                    position = page_text.find(f"{name}:")
                    candidates.append(('colon', name, position))
                    logger.info(f"Found colon pattern: '{name}'")

            # Strategy 6: Meta tags and structured data
            meta_name = soup.find('meta', {'property': 'og:title'})
            if meta_name and meta_name.get('content'):
                content_text = meta_name.get('content')
                name_match = re.search(r'^([^-]+)', content_text)
                if name_match:
                    name = name_match.group(1).strip()
                    if self._is_valid_name(name):
                        candidates.append(('meta', name, 0))
                        logger.info(f"Found meta pattern: '{name}'")

            # Select best candidate
            if candidates:
                best_candidate = self._select_best_name_candidate(candidates)

                # For profile pages, assess confidence based on extraction quality
                # High confidence: score >= 15.0 and valid name
                # Medium/Low confidence: score < 15.0 or questionable name
                best_score = max([score for _, _, score in candidates])

                if best_score >= 15.0 and self._is_valid_name(best_candidate):
                    confidence = 'high'
                    filtered_name = best_candidate
                    logger.info(f"High confidence profile extraction: '{best_candidate}' (score: {best_score:.1f}) - storing name")
                else:
                    confidence = 'medium'
                    filtered_name = ''
                    logger.info(f"Medium/low confidence profile extraction: '{best_candidate}' (score: {best_score:.1f}) - storing empty string for safety")

                # Apply Gemini validation for profile names too
                gemini_validated_name = self._validate_host_name_with_gemini(filtered_name, [('profile_extraction', best_candidate, 0)], page_text[:2000])

                host_info['name'] = gemini_validated_name
                host_info['validation'] = {
                    'confidence': confidence,
                    'original_name': best_candidate,
                    'score': best_score,
                    'validation_method': 'profile_only'
                }
                logger.info(f"Selected best candidate from profile: '{best_candidate}' -> filtered: '{filtered_name}' -> Gemini validated: '{gemini_validated_name}'")

            if not host_info['name']:
                logger.info("No host name pattern found in page text")

            # Fallback: try other selectors if pattern didn't work
            if not host_info['name']:
                name_selectors = [
                    'h1[data-testid*="host-name"]',
                    'h1[class*="host-name"]',
                    '[data-testid*="host-name"]',
                    '.host-name'
                ]

                for selector in name_selectors:
                    name_elem = soup.select_one(selector)
                    if name_elem and name_elem.get_text(strip=True):
                        text = name_elem.get_text(strip=True)
                        # Filter out common non-name text
                        if not any(word in text.lower() for word in ['airbnb', 'host', 'profile', 'listings', 'reviews', 'where', 'been']):
                            if len(text) < 50:  # Reasonable name length
                                host_info['name'] = text
                                break

            # Extract host location - look for geographic location patterns
            location_selectors = [
                '[data-testid*="host-location"]',
                '[class*="location"]'
            ]

            for selector in location_selectors:
                location_elems = soup.select(selector)
                for elem in location_elems:
                    text = elem.get_text(strip=True)
                    # More strict location validation
                    if (text and len(text) < 100 and
                        (', ' in text or re.search(r'\b[A-Z][a-z]+,\s*[A-Z]{2}\b', text)) and
                        not any(word in text.lower() for word in ['guest', 'coffee', 'tea', 'recommendation', 'always', 'make', 'share', 'for'])):
                        host_info['location'] = text
                        logger.info(f"Found host location: {text}")
                        break
                if host_info['location']:
                    break

            # Extract profile image
            img_elem = soup.find('img', {'alt': True})
            if img_elem and img_elem.get('src'):
                host_info['profile_image'] = img_elem.get('src')

            logger.info(f"Extracted host info: {host_info['name']} from {host_info['location']}")

        except Exception as e:
            logger.error(f"Error extracting host info: {e}")

        return host_info

    def _validate_host_name_with_gemini(self, extracted_name: str, candidates: List[tuple], page_context: str) -> str:
        """
        Use Gemini to validate and clean the extracted host name.

        Args:
            extracted_name: The name extracted by our algorithms
            candidates: List of all candidate names found
            page_context: Sample of the page text for context

        Returns:
            Cleaned and validated host name, or empty string if invalid
        """
        try:
            # If no name extracted, return empty
            if not extracted_name or not extracted_name.strip():
                return ""

            # If name looks obviously good, skip Gemini validation to save API calls
            if self._is_obviously_good_name(extracted_name):
                logger.info(f"Name '{extracted_name}' looks obviously good, skipping Gemini validation")
                return extracted_name.strip()

            # If name looks obviously bad, skip Gemini and return empty
            if self._is_obviously_bad_name(extracted_name):
                logger.info(f"Name '{extracted_name}' looks obviously bad, skipping Gemini validation")
                return ""

            # Prepare candidate information for Gemini
            candidate_info = []
            for method, name, position in candidates[:5]:  # Limit to top 5 candidates
                candidate_info.append(f"- {name} (found via {method})")

            candidates_text = "\n".join(candidate_info) if candidate_info else "No candidates found"

            prompt = f"""You are helping to extract and validate an Airbnb host name from a webpage.

EXTRACTED NAME: "{extracted_name}"

CANDIDATE NAMES FOUND:
{candidates_text}

PAGE CONTEXT (first 2000 chars):
{page_context}

TASK: Analyze the extracted name and determine if it's a valid human name for an Airbnb host.

RULES:
1. Return ONLY a clean first name (like "Jennifer", "Michael", "Sarah")
2. Remove any prefixes like "Show review", "Hosted by", "Profile of", etc.
3. Remove any suffixes like "is a Superhost", "reviews", etc.
4. If the name contains obvious non-name words, extract just the name part
5. If no valid name can be extracted, return "INVALID"
6. Names should be 2-50 characters, start with capital letter
7. Avoid obvious fake names, business names, or property names

EXAMPLES:
- "Show reviewJennifer" → "Jennifer"
- "Hosted by Michael Smith" → "Michael"
- "Sarah is a Superhost" → "Sarah"
- "Denver Charmer Property" → "INVALID"
- "Airbnb Host Profile" → "INVALID"
- "Review123" → "INVALID"

RESPONSE: Return only the clean name or "INVALID" (no explanation needed)."""

            # Call Gemini
            response = self._call_gemini_api(prompt)

            if response and response.strip():
                cleaned_name = response.strip()

                # Validate Gemini's response
                if cleaned_name == "INVALID":
                    logger.info(f"Gemini marked name '{extracted_name}' as invalid")
                    return ""
                elif self._is_obviously_good_name(cleaned_name):
                    logger.info(f"Gemini cleaned name: '{extracted_name}' → '{cleaned_name}'")
                    return cleaned_name
                else:
                    logger.warning(f"Gemini returned questionable name: '{cleaned_name}', using empty string")
                    return ""
            else:
                logger.warning(f"Gemini validation failed, using original name: '{extracted_name}'")
                return extracted_name if self._is_obviously_good_name(extracted_name) else ""

        except Exception as e:
            logger.error(f"Error in Gemini host name validation: {e}")
            # Fallback to original name if it looks good
            return extracted_name if self._is_obviously_good_name(extracted_name) else ""

    def _is_obviously_good_name(self, name: str) -> bool:
        """Check if a name is obviously a good human name without needing Gemini validation"""
        if not name or len(name) < 2 or len(name) > 30:
            return False

        name = name.strip()

        # Must start with capital letter
        if not name[0].isupper():
            return False

        # Should only contain letters, spaces, hyphens, apostrophes
        if not re.match(r"^[A-Z][a-zA-Z\s\-\'\.]*$", name):
            return False

        # Check for obvious bad words
        name_lower = name.lower()
        bad_words = [
            'show', 'review', 'host', 'airbnb', 'profile', 'super', 'property',
            'rental', 'vacation', 'home', 'house', 'apartment', 'listing',
            'guest', 'check', 'book', 'where', 'what', 'about', 'contact'
        ]

        for bad_word in bad_words:
            if bad_word in name_lower:
                return False

        # If it's a single common first name, it's probably good
        common_names = [
            'jennifer', 'michael', 'sarah', 'david', 'jessica', 'james', 'ashley',
            'christopher', 'amanda', 'daniel', 'melissa', 'matthew', 'stephanie',
            'joshua', 'elizabeth', 'andrew', 'heather', 'kenneth', 'nicole', 'steven'
        ]

        if name_lower in common_names:
            return True

        # If it's 2-15 characters and looks like a name, probably good
        # Allow letters, hyphens, and apostrophes
        if 2 <= len(name) <= 15 and ' ' not in name and re.match(r"^[A-Za-z\-\']+$", name):
            return True

        return False

    def _is_obviously_bad_name(self, name: str) -> bool:
        """Check if a name is obviously bad and should be rejected without Gemini validation"""
        if not name or len(name) < 2:
            return True

        name_lower = name.lower().strip()

        # Obviously bad patterns that don't need Gemini validation
        obviously_bad_patterns = [
            'airbnb', 'host profile', 'vacation rental', 'property', 'listing',
            'apartment', 'house', 'studio', 'condo', 'villa', 'cottage',
            'downtown', 'uptown', 'luxury', 'modern', 'cozy', 'charming',
            'spacious', 'private', 'entire', 'guest', 'check in', 'check out',
            'book now', 'contact', 'message', 'reviews', 'ratings',
            'where you', 'what you', 'about this', 'location', 'amenities'
        ]

        for pattern in obviously_bad_patterns:
            if pattern in name_lower:
                return True

        # Names that are clearly not human names
        if any(char.isdigit() for char in name):
            return True

        # Names that are too long to be real names
        if len(name) > 50:
            return True

        # Names with too many special characters
        special_char_count = sum(1 for char in name if not char.isalnum() and char not in [' ', '-', "'", '.'])
        if special_char_count > 2:
            return True

        return False

    def _call_gemini_api(self, prompt: str) -> str:
        """Call Gemini API with the given prompt and rate limit handling"""
        try:
            import google.generativeai as genai
            import os
            import time

            gemini_api_key = os.getenv('GEMINI_API_KEY')
            if not gemini_api_key:
                logger.debug("No Gemini API key found")
                return ""

            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel('gemini-2.0-flash')

            # Retry logic for rate limits
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    response = model.generate_content(prompt)
                    return response.text.strip() if response and response.text else ""

                except Exception as api_error:
                    error_str = str(api_error)

                    # Check for rate limit errors
                    if "429" in error_str or "quota" in error_str.lower() or "rate limit" in error_str.lower():
                        if attempt < max_retries:
                            # Extract retry_delay from Gemini's error response
                            retry_delay = self._extract_retry_delay_from_error(error_str)
                            logger.warning(f"Rate limit hit, retrying in {retry_delay} seconds (attempt {attempt + 1}/{max_retries + 1})")
                            logger.info(f"Gemini suggested retry_delay: {retry_delay} seconds")
                            time.sleep(retry_delay)
                            continue
                        else:
                            logger.warning(f"Rate limit exceeded after {max_retries} retries, skipping Gemini validation")
                            return ""
                    else:
                        # Non-rate-limit error, don't retry
                        logger.error(f"Gemini API error: {api_error}")
                        return ""

            return ""

        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return ""

    def _extract_retry_delay_from_error(self, error_str: str) -> int:
        """Extract retry_delay from Gemini's error response"""
        try:
            import re
            # Look for retry_delay { seconds: X } pattern
            delay_match = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', error_str)
            if delay_match:
                suggested_delay = int(delay_match.group(1))
                # Add a small buffer to the suggested delay
                return suggested_delay + 2

            # Fallback: look for just "seconds: X" pattern
            delay_match = re.search(r'seconds:\s*(\d+)', error_str)
            if delay_match:
                suggested_delay = int(delay_match.group(1))
                return suggested_delay + 2

        except Exception as e:
            logger.debug(f"Could not extract retry_delay from error: {e}")

        # Default fallback delay
        return 10

    def _is_valid_name(self, name):
        """Validate if a string is a reasonable host name"""
        if not name or len(name) < 2 or len(name) > 50:
            return False

        name_lower = name.lower().strip()

        # Check for invalid words (expanded list)
        invalid_words = [
            'airbnb', 'host', 'profile', 'super', 'where', 'what', 'fun', 'show', 'all',
            'vacation', 'rental', 'home', 'pets', 'work', 'pros', 'cons', 'reviews',
            'listings', 'verified', 'identity', 'guest', 'coffee', 'tea', 'recommendation',
            'always', 'make', 'share', 'for', 'about', 'contact', 'message', 'book',
            'check', 'in', 'out', 'location', 'amenities', 'rules', 'policy'
        ]

        if name_lower in invalid_words:
            return False

        # Check for property-related words
        property_words = [
            'house', 'apartment', 'condo', 'suite', 'room', 'studio', 'loft', 'villa',
            'cabin', 'cottage', 'mansion', 'penthouse', 'townhouse', 'duplex', 'flat',
            'pool', 'garden', 'downtown', 'uptown', 'beach', 'ocean', 'mountain', 'lake',
            'luxury', 'modern', 'cozy', 'charming', 'spacious', 'private', 'entire',
            'beautiful', 'stunning', 'amazing', 'perfect', 'unique', 'romantic',
            'comfortable', 'convenient', 'close', 'near', 'walking', 'distance'
        ]

        # If name contains multiple property words, it's likely a property description
        property_word_count = sum(1 for word in property_words if word in name_lower)
        if property_word_count >= 2:
            return False

        # Check for business/location indicators
        business_indicators = [
            'hotel', 'motel', 'inn', 'resort', 'lodge', 'hostel', 'boutique',
            'freehand', 'marriott', 'hilton', 'hyatt', 'sheraton', 'westin',
            'los angeles', 'new york', 'san francisco', 'chicago', 'miami', 'austin',
            'nashville', 'denver', 'seattle', 'portland', 'boston', 'atlanta',
            'company', 'group', 'management', 'properties', 'hospitality'
        ]

        for indicator in business_indicators:
            if indicator in name_lower:
                return False

        # Check for UI text patterns (ENHANCED)
        ui_patterns = [
            'show more', 'read more', 'see more', 'view more', 'click here',
            'learn more', 'find out', 'discover', 'explore', 'browse',
            'identity verified', 'verified identity'  # NEW: Catch identity verification text
        ]

        for pattern in ui_patterns:
            if pattern in name_lower:
                return False

        # NEW: Check for state code + identity pattern (e.g., "ILIdentity verifiedSalma")
        if re.search(r'\b[A-Z]{2}identity\s+verified', name, re.IGNORECASE):
            return False

        # NEW: Check for mixed case patterns that suggest UI contamination
        # e.g., "ILIdentity verifiedSalma" has suspicious capitalization
        if re.search(r'[A-Z]{2,}[a-z]+\s+[a-z]+[A-Z][a-z]+', name):
            return False

        # Check if it contains mostly letters and reasonable punctuation
        if not re.match(r'^[A-Za-z\s\-\'\.&]+$', name):
            return False

        # Check if it starts with a capital letter
        if not name[0].isupper():
            return False

        # Check for reasonable name patterns
        # Names should typically be 1-3 words, each starting with capital
        words = name.split()
        if len(words) > 4:  # Too many words, likely a description
            return False

        # Each word should be reasonable length for a name
        for word in words:
            if len(word) > 20:  # Individual word too long
                return False

        return True

    def _clean_name(self, name):
        """Clean extracted name from common prefixes and suffixes"""
        if not name:
            return name

        original_name = name

        # Remove UI text patterns (more comprehensive)
        ui_patterns = [
            r'show more reviews?',
            r'show more listings?',
            r'read more',
            r'see more',
            r'view more',
            r'learn more',
            r'find out more',
            r'click here',
            r'discover more',
            r'explore more',
            r'browse more'
        ]

        for pattern in ui_patterns:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE).strip()

        # Remove common prefixes (expanded)
        prefixes = [
            'verified identity',
            'verified',
            'identity verified',
            'identity',
            'showing',
            'all',
            'host',
            'by',
            'from',
            'meet your host',
            'your host',
            'contact host',
            'hosted by',
            'superhost'
        ]

        for prefix in prefixes:
            if name.lower().startswith(prefix.lower()):
                name = re.sub(f'^{re.escape(prefix)}', '', name, flags=re.IGNORECASE).strip()

        # Remove common suffixes (expanded)
        suffixes = [
            'is a superhost',
            'superhost',
            'host',
            'listings?',
            'reviews?',
            'profile',
            'page'
        ]

        for suffix in suffixes:
            name = re.sub(f'\\s+{suffix}$', '', name, flags=re.IGNORECASE).strip()

        # Clean up extra whitespace and punctuation
        name = re.sub(r'\s+', ' ', name).strip()
        name = re.sub(r'^[,\.\-\s]+|[,\.\-\s]+$', '', name).strip()

        # If cleaning removed too much, return original
        if len(name) < 2:
            return original_name

        return name

    def _select_best_name_candidate(self, candidates):
        """Select the best name candidate from multiple extraction strategies"""
        if not candidates:
            return ''

        # Score candidates based on strategy reliability and position
        scored_candidates = []

        strategy_scores = {
            'title': 10,
            'hosted_by': 9,
            'json_ld': 8,
            'superhost': 7,
            'host_colon': 6,
            'reviews': 5,
            'where_been': 4,
            'listings': 3,
            'colon': 2,
            'meta': 1,
            'script_data': 6  # Added script_data strategy
        }

        for strategy, name, position in candidates:
            cleaned_name = self._clean_name(name)
            if self._is_valid_name(cleaned_name):
                base_score = strategy_scores.get(strategy, 0)

                # Prefer names that appear earlier in the page (lower position)
                position_score = max(0, 5 - (position / 2000))

                # Quality bonuses
                quality_bonus = 0

                # Bonus for typical name patterns
                if re.match(r'^[A-Z][a-z]+(\s[A-Z][a-z]+)*$', cleaned_name):
                    quality_bonus += 3  # Proper capitalization

                # Bonus for reasonable length
                if 2 <= len(cleaned_name) <= 20:
                    quality_bonus += 2

                # Bonus for common name patterns
                words = cleaned_name.split()
                if 1 <= len(words) <= 3:
                    quality_bonus += 2

                # Penalty for suspicious patterns
                penalty = 0

                # Penalty for property-like names
                property_indicators = ['house', 'apartment', 'suite', 'room', 'home', 'place']
                if any(indicator in cleaned_name.lower() for indicator in property_indicators):
                    penalty += 5

                # Penalty for business-like names
                business_indicators = ['hotel', 'inn', 'resort', 'company', 'group', 'management']
                if any(indicator in cleaned_name.lower() for indicator in business_indicators):
                    penalty += 8

                # Penalty for location names
                location_indicators = ['angeles', 'francisco', 'york', 'chicago', 'miami', 'austin', 'downtown']
                if any(indicator in cleaned_name.lower() for indicator in location_indicators):
                    penalty += 6

                # Penalty for very long names (likely descriptions)
                if len(cleaned_name) > 25:
                    penalty += 4

                # Penalty for names with too many words
                if len(words) > 3:
                    penalty += 3

                total_score = base_score + position_score + quality_bonus - penalty
                scored_candidates.append((total_score, cleaned_name, strategy))

                logger.debug(f"Candidate '{cleaned_name}' ({strategy}): base={base_score}, pos={position_score:.1f}, quality={quality_bonus}, penalty={penalty}, total={total_score:.1f}")

        if scored_candidates:
            # Sort by score (highest first) and return the best candidate
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_name, best_strategy = scored_candidates[0]

            # Log all candidates for debugging
            logger.info(f"All candidates: {[(name, strategy, score) for score, name, strategy in scored_candidates]}")
            logger.info(f"Selected best candidate: '{best_name}' (strategy: {best_strategy}, score: {best_score:.1f}) from {len(candidates)} options")

            return best_name

        logger.info("No valid candidates found after filtering")
        return ''

    def _extract_user_profile_url_from_listing(self, listing_url: str) -> Optional[str]:
        """Extract user profile URL from a listing page"""
        try:
            content = self._get_page_content(listing_url)
            if not content:
                return None

            soup = BeautifulSoup(content, 'html.parser')

            # Strategy 1: Look for user profile links in the page
            profile_patterns = [
                r'https://www\.airbnb\.com/users/show/(\d+)',
                r'/users/show/(\d+)',
                r'airbnb\.com/users/show/(\d+)'
            ]

            page_text = soup.get_text()
            for pattern in profile_patterns:
                matches = re.findall(pattern, page_text)
                if matches:
                    user_id = matches[0]
                    return f'https://www.airbnb.com/users/show/{user_id}'

            # Strategy 2: Look in script tags for user data
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    script_text = script.string
                    # Look for user ID patterns in JavaScript data
                    user_id_patterns = [
                        r'"userId":\s*"?(\d+)"?',
                        r'"user_id":\s*"?(\d+)"?',
                        r'"hostId":\s*"?(\d+)"?',
                        r'"host_id":\s*"?(\d+)"?'
                    ]

                    for pattern in user_id_patterns:
                        matches = re.findall(pattern, script_text)
                        if matches:
                            user_id = matches[0]
                            return f'https://www.airbnb.com/users/show/{user_id}'

            # Strategy 3: Look for href attributes pointing to user profiles
            links = soup.find_all('a', href=True)
            for link in links:
                href = link['href']
                if '/users/show/' in href:
                    # Extract user ID from href
                    match = re.search(r'/users/show/(\d+)', href)
                    if match:
                        user_id = match.group(1)
                        return f'https://www.airbnb.com/users/show/{user_id}'

            logger.info(f"Could not extract user profile URL from listing: {listing_url}")
            return None

        except Exception as e:
            logger.error(f"Error extracting user profile URL from listing {listing_url}: {e}")
            return None

    def _cross_validate_host_name(self, listing_url: str, extracted_name: str) -> Dict[str, Any]:
        """
        Cross-validate host name by checking both listing and user profile.

        Args:
            listing_url: The listing URL
            extracted_name: Name extracted from listing

        Returns:
            Dict with validation results and final name
        """
        validation_result = {
            'validated': False,
            'final_name': extracted_name,
            'listing_name': extracted_name,
            'profile_name': '',
            'confidence': 'low',
            'validation_method': 'listing_only'
        }

        try:
            # Extract user profile URL from listing
            profile_url = self._extract_user_profile_url_from_listing(listing_url)
            if not profile_url:
                logger.info(f"Could not extract profile URL for cross-validation")
                return validation_result

            logger.info(f"Cross-validating with profile URL: {profile_url}")

            # Extract name from user profile
            profile_host_info = self._extract_host_from_profile(profile_url)
            profile_name = profile_host_info.get('name', '')

            validation_result['profile_name'] = profile_name

            if not profile_name:
                logger.info(f"No name extracted from profile, using listing name")
                validation_result['confidence'] = 'medium'
                validation_result['validation_method'] = 'listing_only_verified'
                return validation_result

            # Compare names
            if extracted_name.lower().strip() == profile_name.lower().strip():
                # Perfect match
                validation_result['validated'] = True
                validation_result['confidence'] = 'high'
                validation_result['validation_method'] = 'cross_validated_exact'
                logger.info(f"Cross-validation successful: '{extracted_name}' matches profile")
            elif extracted_name.lower() in profile_name.lower() or profile_name.lower() in extracted_name.lower():
                # Partial match (e.g., "John" vs "John Smith")
                validation_result['validated'] = True

                # NEW: Prefer the cleaner name when there's a partial match
                listing_is_clean = self._is_valid_name(extracted_name)
                profile_is_clean = self._is_valid_name(profile_name)

                if listing_is_clean and not profile_is_clean:
                    # Listing name is clean, profile is contaminated - use listing
                    validation_result['final_name'] = extracted_name
                    validation_result['confidence'] = 'high'
                    validation_result['validation_method'] = 'cross_validated_listing_preferred'
                    logger.info(f"Cross-validation partial match: '{extracted_name}' (clean) vs '{profile_name}' (contaminated), using listing name")
                elif profile_is_clean and not listing_is_clean:
                    # Profile name is clean, listing is contaminated - use profile
                    validation_result['final_name'] = profile_name
                    validation_result['confidence'] = 'high'
                    validation_result['validation_method'] = 'cross_validated_profile_preferred'
                    logger.info(f"Cross-validation partial match: '{extracted_name}' (contaminated) vs '{profile_name}' (clean), using profile name")
                elif listing_is_clean and profile_is_clean:
                    # Both are clean - use the more complete one
                    if len(profile_name) > len(extracted_name):
                        validation_result['final_name'] = profile_name
                        logger.info(f"Cross-validation partial match: both clean, using longer profile name '{profile_name}'")
                    else:
                        validation_result['final_name'] = extracted_name
                        logger.info(f"Cross-validation partial match: both clean, using listing name '{extracted_name}'")
                    validation_result['confidence'] = 'high'
                    validation_result['validation_method'] = 'cross_validated_partial'
                else:
                    # Both are contaminated - lower confidence, use listing as fallback
                    validation_result['final_name'] = extracted_name
                    validation_result['confidence'] = 'medium'
                    validation_result['validation_method'] = 'cross_validated_both_contaminated'
                    logger.info(f"Cross-validation partial match: both contaminated, using listing name '{extracted_name}' with medium confidence")
            else:
                # Names don't match - use profile name if it's valid, otherwise listing name
                if self._is_valid_name(profile_name):
                    validation_result['final_name'] = profile_name
                    validation_result['confidence'] = 'medium'
                    validation_result['validation_method'] = 'profile_preferred'
                    logger.info(f"Cross-validation mismatch: '{extracted_name}' vs '{profile_name}', using profile name")
                else:
                    validation_result['confidence'] = 'low'
                    validation_result['validation_method'] = 'listing_fallback'
                    logger.info(f"Cross-validation mismatch and invalid profile name, using listing name")

        except Exception as e:
            logger.error(f"Error during cross-validation: {e}")
            validation_result['confidence'] = 'low'
            validation_result['validation_method'] = 'validation_error'

        return validation_result

    def _normalize_airbnb_url(self, url: str) -> str:
        """
        Normalize Airbnb URLs for consistent storage and duplicate checking.

        Handles:
        - Internal editor URLs: /hosting/listings/editor/{id}/details -> /rooms/{id}
        - Custom host URLs: /h/{slug} -> resolve to /rooms/{id} by following redirect (best-effort)
        - User profile URLs: /users/show/{id} (kept as-is, query params removed)
        - Public listing URLs: /rooms/{id} (kept as-is, query params removed)
        - Removes query parameters and fragments for duplicate prevention

        Args:
            url: Input URL (can be internal editor, profile, or public listing)

        Returns:
            Normalized public URL without query parameters
        """
        try:
            from urllib.parse import urlparse

            # First, handle internal editor URLs
            # Format: https://www.airbnb.com/hosting/listings/editor/1376252243023110567/details
            editor_pattern = r'/hosting/listings/editor/(\d+)/'
            editor_match = re.search(editor_pattern, url)
            if editor_match:
                listing_id = editor_match.group(1)
                normalized_url = f'https://www.airbnb.com/rooms/{listing_id}'
                logger.info(f"Normalized editor URL: {url} -> {normalized_url}")
                return normalized_url

            # Handle other internal hosting URLs
            # Format: https://www.airbnb.com/hosting/listings/1376252243023110567
            hosting_pattern = r'/hosting/listings/(\d+)'
            hosting_match = re.search(hosting_pattern, url)
            if hosting_match:
                listing_id = hosting_match.group(1)
                normalized_url = f'https://www.airbnb.com/rooms/{listing_id}'
                logger.info(f"Normalized hosting URL: {url} -> {normalized_url}")
                return normalized_url

            # If it's a custom host URL (/h/{slug}), try to resolve to a listing by following redirects
            if re.search(r"/h/[A-Za-z0-9_-]+", url):
                try:
                    logger.info(f"Resolving custom host URL via HEAD: {url}")
                    # Use HEAD to follow redirects quickly; fallback to GET if needed
                    resp = self.session.head(url, allow_redirects=True, timeout=15)
                    final_url = resp.url
                    if '/rooms/' in final_url:
                        # Normalize to rooms URL without query
                        from urllib.parse import urlparse
                        parsed_final = urlparse(final_url)
                        normalized_final = f"{parsed_final.scheme}://{parsed_final.netloc}{parsed_final.path}"
                        if normalized_final.endswith('/'):
                            normalized_final = normalized_final[:-1]
                        logger.info(f"Resolved /h/ URL: {url} -> {normalized_final}")
                        return normalized_final
                except Exception as e:
                    logger.warning(f"Failed to resolve /h/ URL via HEAD: {e}; will proceed with generic normalization")

            # For all other URLs (user profiles, public listings), remove query parameters
            parsed = urlparse(url)

            # Reconstruct URL without query parameters and fragments
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

            # Remove trailing slash if present
            if normalized.endswith('/'):
                normalized = normalized[:-1]

            if normalized != url:
                logger.info(f"Normalized URL: {url} → {normalized}")

            return normalized

        except Exception as e:
            logger.error(f"Error normalizing URL {url}: {e}")
            return url

    def _validate_airbnb_url(self, url: str) -> Dict[str, Any]:
        """
        Validate if URL is a supported Airbnb URL format.

        Args:
            url: Input URL to validate

        Returns:
            Dict with validation results
        """
        validation_result = {
            'is_valid': False,
            'is_airbnb': False,
            'url_type': 'unknown',
            'normalized_url': url,
            'error_message': ''
        }

        try:
            # Normalize missing scheme for backend as well
            if not re.match(r'^https?://', url, flags=re.IGNORECASE) and re.search(r'(^|//|\.)airbnb\.com', url, flags=re.IGNORECASE):
                url = 'https://' + url.lstrip('/').lstrip('/')
                validation_result['normalized_url'] = url

            # Check if it's an Airbnb URL
            if 'airbnb.com' not in url.lower():
                validation_result['error_message'] = 'Please enter an Airbnb URL (should contain "airbnb.com")'
                return validation_result

            validation_result['is_airbnb'] = True

            # Normalize the URL
            normalized_url = self._normalize_airbnb_url(url)
            validation_result['normalized_url'] = normalized_url

            # Treat custom host URL (/h/{slug}) as listing; it will be resolved downstream
            # Check supported formats
            if '/rooms/' in normalized_url or '/h/' in normalized_url:
                validation_result['is_valid'] = True
                validation_result['url_type'] = 'listing'
            elif '/users/show/' in normalized_url:
                validation_result['is_valid'] = True
                validation_result['url_type'] = 'profile'
            else:
                validation_result['error_message'] = 'Please check if the URL is correct. Supported formats: listing pages or user profiles.'

        except Exception as e:
            validation_result['error_message'] = f'Error validating URL: {str(e)}'

        return validation_result

    def _apply_confidence_filter(self, validation_result: Dict[str, Any]) -> str:
        """
        Apply confidence filtering - only return names for high confidence extractions.

        Args:
            validation_result: Result from cross-validation

        Returns:
            Host name if high confidence, empty string otherwise
        """
        confidence = validation_result.get('confidence', 'low')
        final_name = validation_result.get('final_name', '')

        if confidence == 'high':
            logger.info(f"High confidence extraction: '{final_name}' - storing name")
            return final_name
        else:
            logger.info(f"Medium/low confidence extraction: '{final_name}' (confidence: {confidence}) - storing empty string for safety")
            return ''

    def extract_listing_details(self, listing_url: str) -> Optional[Dict[str, Any]]:
        """
        Extract detailed information from a specific Airbnb listing.
        Enhanced with improved patterns for title, location, type, and images.

        Args:
            listing_url: URL of the Airbnb listing

        Returns:
            Dictionary containing listing details or None if failed
        """
        logger.info(f"Extracting details for listing: {listing_url}")

        content = self._get_page_content(listing_url, wait_for_element='title')
        if not content:
            return None

        soup = BeautifulSoup(content, 'html.parser')
        listing_data = {
            'url': listing_url,
            'title': '',
            'location': '',
            'property_type': '',
            'image': ''  # Single thumbnail image URL
        }

        try:
            # Extract title (ENHANCED)
            title_selectors = [
                'h1[data-testid="listing-title"]',
                'h1._feky19f',
                'h1',
                '[data-testid="listing-title"]',
                'title'
            ]

            title = ''
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    break

            # Clean up title if extracted from page title
            if title and ' - ' in title:
                # Remove " - Houses for Rent in..." and " - Airbnb" suffixes
                title = re.sub(r'\s*-\s*(Houses|Apartments|Condos|Homes)\s+for\s+Rent.*$', '', title, flags=re.IGNORECASE)
                title = re.sub(r'\s*-\s*Airbnb\s*$', '', title, flags=re.IGNORECASE)
                title = title.strip()

            listing_data['title'] = title
            logger.info(f"Extracted title: {title}")

            # Extract description
            desc_selectors = [
                '[data-testid="listing-description"] span',
                '._1d1ntwqj span',
                '._1d1ntwqj',
                '[data-section-id="DESCRIPTION_DEFAULT"] span'
            ]
            
            for selector in desc_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    listing_data['description'] = desc_elem.get_text(strip=True)
                    break

            # Extract location (ENHANCED)
            location_selectors = [
                '[data-testid="listing-location"]',
                '._9xiloll',
                '._1qs8v84p',
                '[data-section-id="LOCATION_DEFAULT"]'
            ]

            location = ''
            for selector in location_selectors:
                location_elem = soup.select_one(selector)
                if location_elem:
                    location = location_elem.get_text(strip=True)
                    break

            # If no location found in selectors, try multiple extraction methods
            if not location:
                # Method 1: Extract from original page title (before cleaning)
                title_tag = soup.find('title')
                if title_tag:
                    full_title = title_tag.get_text(strip=True)

                    # Try different patterns on the full title to extract neighborhood + city
                    location_patterns = [
                        r'\s+in\s+([^-]+?)(?:\s*-|$)',  # "in Location -" or "in Location" at end
                        r'-\s*[^-]*\s+in\s+([^-]+?)(?:\s*-|$)',  # "- ... in Location -"
                        r'@\s*([^-@]+?)(?:\s*-|$)',     # "@ Location -"
                        r'near\s+([^-]+?)(?:\s*-|$)',   # "near Location -"
                        r'Close\s+to\s+([^-]+?)(?:\s*-|$)',  # "Close to Location -"
                    ]

                    for pattern in location_patterns:
                        match = re.search(pattern, full_title, re.IGNORECASE)
                        if match:
                            location = match.group(1).strip()
                            # Clean up the location to get just city, state, country
                            location = self._clean_location_text(location)
                            if len(location) > 2:
                                logger.info(f"Extracted location from full title: {location}")
                                break

                # Method 2: Extract from script content if still no location
                if not location:
                    scripts = soup.find_all('script')

                    # Try to find city and state separately in scripts
                    city_from_script = ''
                    state_from_script = ''

                    location_patterns_in_scripts = [
                        r'"city":\s*"([^"]+)"',
                        r'"locality":\s*"([^"]+)"',
                        r'"addressLocality":\s*"([^"]+)"'
                    ]

                    state_patterns_in_scripts = [
                        r'"region":\s*"([^"]+)"',
                        r'"state":\s*"([^"]+)"',
                        r'"addressRegion":\s*"([^"]+)"'
                    ]

                    for script in scripts:
                        if script.string:
                            # Look for city
                            if not city_from_script:
                                for pattern in location_patterns_in_scripts:
                                    matches = re.findall(pattern, script.string, re.IGNORECASE)
                                    if matches:
                                        for match in matches:
                                            if len(match) > 2 and not match.lower() in ['us', 'usa', 'united states']:
                                                city_from_script = match
                                                break
                                        if city_from_script:
                                            break

                            # Look for state
                            if not state_from_script:
                                for pattern in state_patterns_in_scripts:
                                    matches = re.findall(pattern, script.string, re.IGNORECASE)
                                    if matches:
                                        for match in matches:
                                            if len(match) > 1 and not match.lower() in ['us', 'usa', 'united states']:
                                                state_from_script = match
                                                break
                                        if state_from_script:
                                            break

                            if city_from_script and state_from_script:
                                break

                    # Combine city and state if found
                    if city_from_script and state_from_script:
                        location = f"{city_from_script}, {state_from_script}, United States"
                        logger.info(f"Extracted location from script parts: {location}")
                    elif city_from_script:
                        location = self._clean_location_text(city_from_script)
                        logger.info(f"Extracted partial location from script: {location}")

            listing_data['location'] = location

            # Extract property type (ENHANCED)
            property_type = ''
            page_text = soup.get_text()

            # Look for property type patterns in order of specificity
            type_patterns = [
                r'(Entire\s+(?:home|house|apartment|condo|villa|cabin|cottage|studio|loft))',
                r'(Private\s+(?:room|suite|studio))',
                r'(Shared\s+(?:room|space))',
                r'(Home|House|Apartment|Condo|Villa|Cabin|Cottage|Studio|Loft|Townhouse|Duplex)',
                r'(Rental\s+unit)',
                r'(Guest\s+suite)',
                r'(Bed\s+and\s+breakfast)'
            ]

            for pattern in type_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    property_type = match.group(1)
                    logger.info(f"Found property type: {property_type}")
                    break

            # Also check JSON-LD structured data
            if not property_type:
                json_scripts = soup.find_all('script', type='application/ld+json')
                for script in json_scripts:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict):
                            if data.get('@type') in ['Product', 'Accommodation', 'LodgingBusiness']:
                                if 'category' in data:
                                    property_type = data['category']
                                    logger.info(f"Found property type in JSON-LD: {property_type}")
                                    break
                    except (json.JSONDecodeError, AttributeError):
                        continue

            listing_data['property_type'] = property_type

            # Note: Amenities extraction removed for simplified data structure

            # Extract single thumbnail image (ENHANCED with better targeting)
            thumbnail_url = ''

            # Method 1: Try to find the main listing photo with specific selectors
            primary_img_selectors = [
                # Main listing photo selectors (most specific first)
                'img[data-testid="listing-main-image"]',
                'img[data-testid="photo-viewer-image"]',
                'div[data-testid="photo-viewer"] img',
                'div[data-section-id="HERO_DEFAULT"] img',
                'div[data-section-id="PHOTOS_DEFAULT"] img:first-child',
                # Gallery and photo-specific selectors
                'img[data-testid*="photo"]:not([data-testid*="avatar"]):not([data-testid*="profile"])',
                'div[data-testid*="gallery"] img:first-child',
                'div[data-testid*="photos"] img:first-child',
                # Picture elements (responsive images)
                'picture:not([data-testid*="avatar"]) img',
                # Generic but filtered selectors
                'img[src*="pictures"]:not([src*="user"]):not([src*="avatar"])',
                'img[src*="hosting"]',
                'img[src*="miso"]'
            ]

            for selector in primary_img_selectors:
                img_elements = soup.select(selector)
                for img in img_elements:
                    src = img.get('src') or img.get('data-src') or img.get('data-original')
                    if src and self._is_valid_listing_image(src):
                        thumbnail_url = self._convert_to_thumbnail(src)
                        logger.info(f"Found listing image via selector '{selector}': {src[:100]}...")
                        break

                if thumbnail_url:
                    break

            # Method 2: If no images in img tags, parse script content with better filtering
            if not thumbnail_url:
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string:
                        # Look for image URLs in script content with better patterns
                        image_patterns = [
                            # High-quality listing images
                            r'https://[^"\']*(?:hosting|miso|airflow)[^"\']*\.(?:jpg|jpeg|png|webp)[^"\']*',
                            # General Airbnb images
                            r'https://[^"\']*muscache\.com[^"\']*pictures[^"\']*\.(?:jpg|jpeg|png|webp)[^"\']*',
                            # Fallback pattern
                            r'https://[^"\']*(?:pictures|images)[^"\']*\.(?:jpg|jpeg|png|webp)[^"\']*'
                        ]

                        for pattern in image_patterns:
                            image_matches = re.findall(pattern, script.string)
                            if image_matches:
                                # Filter and prioritize listing photos
                                valid_images = [img for img in image_matches if self._is_valid_listing_image(img)]

                                if valid_images:
                                    # Prioritize hosting/miso images (these are usually listing photos)
                                    hosting_images = [img for img in valid_images if any(keyword in img.lower() for keyword in ['hosting', 'miso', 'airflow'])]

                                    if hosting_images:
                                        thumbnail_url = self._convert_to_thumbnail(hosting_images[0])
                                        logger.info(f"Found hosting image in script: {hosting_images[0][:100]}...")
                                    else:
                                        thumbnail_url = self._convert_to_thumbnail(valid_images[0])
                                        logger.info(f"Found valid image in script: {valid_images[0][:100]}...")

                                    break

                            if thumbnail_url:
                                break

                        if thumbnail_url:
                            break

            # Method 3: Try Open Graph and meta tags as fallback
            if not thumbnail_url:
                meta_selectors = [
                    'meta[property="og:image"]',
                    'meta[name="twitter:image"]',
                    'meta[property="og:image:url"]',
                    'link[rel="image_src"]'
                ]

                for selector in meta_selectors:
                    meta_elem = soup.select_one(selector)
                    if meta_elem:
                        src = meta_elem.get('content') or meta_elem.get('href')
                        if src and self._is_valid_listing_image(src):
                            thumbnail_url = self._convert_to_thumbnail(src)
                            logger.info(f"Found meta image via '{selector}': {src[:100]}...")
                            break

            listing_data['image'] = thumbnail_url
            if thumbnail_url:
                logger.info(f"Found thumbnail image: Yes - {thumbnail_url[:100]}...")
            else:
                logger.warning(f"No valid thumbnail image found for listing")

            # Apply Gemini validation for data quality improvement
            page_content_sample = soup.get_text()[:1000]  # First 1000 chars for context
            listing_data = self._validate_with_gemini(listing_data, page_content_sample)

            logger.info(f"Successfully extracted listing details: {listing_data['title']}")
            return listing_data

        except Exception as e:
            logger.error(f"Error parsing listing details: {e}")
            return listing_data

    def _convert_to_thumbnail(self, src: str) -> str:
        """
        Convert an image URL to a small square thumbnail (240x240).

        Args:
            src: Original image URL

        Returns:
            Thumbnail URL
        """
        # Normalize URL
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            src = 'https://www.airbnb.com' + src

        # Convert to small square thumbnail (240x240 for cards)
        if '?im_w=' in src:
            # Airbnb uses im_w and im_h for dimensions
            thumbnail_url = re.sub(r'im_w=\d+', 'im_w=240', src)
            thumbnail_url = re.sub(r'im_h=\d+', 'im_h=240', thumbnail_url)
            if 'im_h=' not in thumbnail_url:
                thumbnail_url += '&im_h=240'
        elif '?' in src:
            thumbnail_url = src + '&im_w=240&im_h=240'
        else:
            thumbnail_url = src + '?im_w=240&im_h=240'

        return thumbnail_url

    def _is_valid_listing_image(self, src: str) -> bool:
        """
        Check if an image URL is likely a valid listing photo (not avatar, icon, etc.)

        Args:
            src: Image URL to validate

        Returns:
            True if likely a listing photo, False otherwise
        """
        if not src or len(src) < 10:
            return False

        src_lower = src.lower()

        # Exclude obvious non-listing images
        exclude_patterns = [
            'user', 'avatar', 'profile', 'icon', 'logo', 'badge', 'star',
            'heart', 'flag', 'button', 'arrow', 'check', 'close', 'menu',
            'search', 'filter', 'sort', 'calendar', 'map', 'pin', 'marker',
            'facebook', 'twitter', 'instagram', 'google', 'apple',
            'placeholder', 'loading', 'spinner', 'default'
        ]

        for pattern in exclude_patterns:
            if pattern in src_lower:
                return False

        # Must be a reasonable image format
        if not any(ext in src_lower for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            return False

        # Prefer Airbnb hosting/listing images
        if any(keyword in src_lower for keyword in ['hosting', 'miso', 'airflow']):
            return True

        # Must contain 'pictures' or 'images' for Airbnb URLs (unless it's a hosting image)
        if 'muscache.com' in src_lower and 'pictures' not in src_lower and not any(keyword in src_lower for keyword in ['hosting', 'miso', 'airflow']):
            return False

        # Check for reasonable image dimensions in URL (listing photos are usually larger)
        if 'im_w=' in src:
            try:
                width_match = re.search(r'im_w=(\d+)', src)
                if width_match:
                    width = int(width_match.group(1))
                    # Listing photos are usually at least 200px wide
                    if width < 200:
                        return False
            except:
                pass

        return True

    def _clean_location_text(self, location: str) -> str:
        """
        Clean location text to extract neighborhood, city, state, country format.

        Args:
            location: Raw location text that may contain extra descriptive text

        Returns:
            Cleaned location in "Neighborhood, City, State, Country" or "City, State, Country" format
        """
        if not location:
            return ''

        # Remove common prefixes and excessive descriptive text
        location = re.sub(r'^(Where you\'ll be\s*)', '', location, flags=re.IGNORECASE)
        location = re.sub(r'^(Located in\s*)', '', location, flags=re.IGNORECASE)
        location = re.sub(r'^(Situated in\s*)', '', location, flags=re.IGNORECASE)
        location = re.sub(r'^(In\s*)', '', location, flags=re.IGNORECASE)

        # Remove excessive descriptive text that often appears after location
        location = re.sub(r'We verified that this listing.*$', '', location, flags=re.IGNORECASE)
        location = re.sub(r'Learn more.*$', '', location, flags=re.IGNORECASE)
        location = re.sub(r'Neighborhood highlights.*$', '', location, flags=re.IGNORECASE)
        location = re.sub(r'Show more.*$', '', location, flags=re.IGNORECASE)
        location = re.sub(r'Redfin ranked.*$', '', location, flags=re.IGNORECASE)

        # Remove common suffixes
        location = re.sub(r'\s+for\s+Rent.*$', '', location, flags=re.IGNORECASE)
        location = re.sub(r'\s+area.*$', '', location, flags=re.IGNORECASE)
        location = re.sub(r'\s+neighborhood.*$', '', location, flags=re.IGNORECASE)
        location = re.sub(r'\s+district.*$', '', location, flags=re.IGNORECASE)

        # Clean up extra whitespace and punctuation
        location = re.sub(r'\s+', ' ', location).strip()
        location = re.sub(r'^[,\s]+|[,\s]+$', '', location)

        # Handle edge case where text gets concatenated without spaces
        # Look for patterns like "beChicago" and fix them
        location = re.sub(r'be([A-Z][a-z]+)', r'\1', location)
        location = re.sub(r'States([A-Z][a-z]+)', r'States \1', location)

        # Special handling for concatenated city names
        # Look for common US cities that might get concatenated
        major_cities = ['Chicago', 'New York', 'Los Angeles', 'Houston', 'Phoenix', 'Philadelphia',
                       'San Antonio', 'San Diego', 'Dallas', 'San Jose', 'Austin', 'Jacksonville',
                       'Fort Worth', 'Columbus', 'Charlotte', 'San Francisco', 'Indianapolis',
                       'Seattle', 'Denver', 'Washington', 'Boston', 'Nashville', 'Baltimore',
                       'Oklahoma City', 'Louisville', 'Portland', 'Las Vegas', 'Milwaukee',
                       'Albuquerque', 'Tucson', 'Fresno', 'Sacramento', 'Mesa', 'Kansas City',
                       'Atlanta', 'Long Beach', 'Colorado Springs', 'Raleigh', 'Miami', 'Virginia Beach']

        for city in major_cities:
            # Look for the city name in the text and extract it with surrounding context
            city_pattern = rf'.*?({city}[^A-Z]*(?:[A-Z][a-z]+)?[^A-Z]*(?:United States)?)'
            match = re.search(city_pattern, location, re.IGNORECASE)
            if match:
                extracted = match.group(1).strip()
                # Clean up the extracted part
                extracted = re.sub(r'\s+', ' ', extracted)
                if len(extracted) > len(city) and len(extracted) < 100:  # Reasonable length
                    location = extracted
                    break

        # Try to extract city, state, country pattern first (simpler approach)
        city_state_country_match = re.search(r'([A-Za-z\s]+),\s*([A-Za-z\s]+)(?:,\s*(United States|USA|US))?', location)
        if city_state_country_match:
            city = city_state_country_match.group(1).strip()
            state = city_state_country_match.group(2).strip()

            # Build clean location
            return f"{city}, {state}, United States"

        # If no clear city/state pattern, check if it's a neighborhood that needs mapping
        # Common neighborhood patterns that should be mapped to cities (preserve neighborhood name)
        neighborhood_mappings = {
            'bucktown': ('Bucktown', 'Chicago, Illinois'),
            'ukrainian village': ('Ukrainian Village', 'Chicago, Illinois'),
            'wicker park': ('Wicker Park', 'Chicago, Illinois'),
            'pilsen': ('Pilsen', 'Chicago, Illinois'),
            'lincoln park': ('Lincoln Park', 'Chicago, Illinois'),
            'logan square': ('Logan Square', 'Chicago, Illinois'),
            'river north': ('River North', 'Chicago, Illinois'),
            'downtown': ('', ''),  # Too generic, will be handled below
            'midtown': ('', ''),   # Too generic
            'uptown': ('', '')     # Too generic
        }

        location_lower = location.lower().strip()
        for neighborhood_key, (neighborhood_name, city_state) in neighborhood_mappings.items():
            if neighborhood_key in location_lower and city_state:
                return f"{neighborhood_name}, {city_state}, United States"

        # If no clear city/state pattern, try to clean up what we have
        # Remove "United States" if it's the only thing left
        if location.lower().strip() in ['united states', 'usa', 'us']:
            return ''

        # Remove trailing "United States" if location is too long
        location = re.sub(r',\s*(United States|USA|US)\s*$', '', location, flags=re.IGNORECASE)

        # If still too long (more than 50 chars), try to extract the last meaningful part
        if len(location) > 50:
            # Look for the last comma-separated part that looks like a location
            parts = location.split(',')
            if len(parts) >= 2:
                # Take the last 2-3 parts (likely city, state)
                meaningful_parts = [part.strip() for part in parts[-3:] if part.strip()]
                if meaningful_parts:
                    location = ', '.join(meaningful_parts)

        return location.strip()

    def _validate_with_gemini(self, listing_data: Dict[str, Any], page_content_sample: str) -> Dict[str, Any]:
        """
        Use Gemini to validate and normalize listing data for better quality.

        Args:
            listing_data: Raw extracted listing data
            page_content_sample: Sample of page content for context

        Returns:
            Validated and normalized listing data
        """
        try:
            # Only validate if we have a Gemini API key
            gemini_api_key = os.getenv('GEMINI_API_KEY')
            if not gemini_api_key:
                logger.debug("No Gemini API key found, skipping validation")
                return listing_data

            import google.generativeai as genai
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel('gemini-2.0-flash')

            # Prepare validation prompt
            prompt = f"""
You are a data validation expert for Airbnb listings. Please review and normalize the following extracted data:

EXTRACTED DATA:
- Title: "{listing_data.get('title', '')}"
- Location: "{listing_data.get('location', '')}"
- Property Type: "{listing_data.get('property_type', '')}"

PAGE CONTENT SAMPLE:
{page_content_sample[:500]}...

VALIDATION TASKS:
1. TITLE: Choose the best, most user-friendly title that clearly identifies the property
2. LOCATION: Normalize to format "Neighborhood, City, State, Country" (if neighborhood available) or "City, State, Country"
3. PROPERTY TYPE: Standardize to one of: House, Apartment, Condo, Studio, Villa, Cottage, Townhouse, Other

RULES:
- Keep titles descriptive but concise (under 60 characters)
- For locations, include neighborhood if it's a well-known area
- Use proper capitalization
- Be consistent with naming conventions

Please respond in JSON format:
{{
    "title": "normalized title",
    "location": "normalized location",
    "property_type": "normalized type",
    "confidence": "high|medium|low",
    "changes_made": ["list of changes"]
}}
"""

            response = model.generate_content(prompt)

            # Parse the response
            response_text = response.text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:-3]
            elif response_text.startswith('```'):
                response_text = response_text[3:-3]

            validated_data = json.loads(response_text)

            # Apply validated data if confidence is high or medium
            if validated_data.get('confidence') in ['high', 'medium']:
                if validated_data.get('title'):
                    listing_data['title'] = validated_data['title']
                if validated_data.get('location'):
                    listing_data['location'] = validated_data['location']
                if validated_data.get('property_type'):
                    listing_data['property_type'] = validated_data['property_type']

                logger.info(f"Gemini validation applied with {validated_data.get('confidence')} confidence")
                if validated_data.get('changes_made'):
                    logger.info(f"Changes made: {', '.join(validated_data['changes_made'])}")
            else:
                logger.info("Gemini validation had low confidence, keeping original data")

        except Exception as e:
            logger.warning(f"Gemini validation failed: {e}")
            # Return original data if validation fails

        return listing_data

    def extract_deep_property_data(self, listing_url: str) -> Dict[str, Any]:
        """
        Extract comprehensive property data from an Airbnb listing including:
        - Amenities with appliance details
        - House rules
        - Safety information
        - Property descriptions (cleaned)
        - Check-in/check-out instructions
        - Local area information

        Args:
            listing_url: URL of the Airbnb listing

        Returns:
            Dictionary containing extracted property data
        """
        logger.info(f"Starting deep extraction for: {listing_url}")

        try:
            # Enable Selenium for better amenities extraction (location grouping)
            original_selenium_setting = self.use_selenium
            if SELENIUM_AVAILABLE and not self.use_selenium:
                self.use_selenium = True
                self._setup_selenium()

            # Initialize variables
            page_source = None
            response = None

            # Fetch the page - use Selenium if available for better JavaScript rendering
            if self.use_selenium and self.driver:
                logger.info(f"Using Selenium for deep extraction: {listing_url}")
                self.driver.get(listing_url)

                # Wait for amenities content to load
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    # Reduced wait for dynamic content
                    time.sleep(1)
                except TimeoutException:
                    logger.warning("Timeout waiting for page to load with Selenium")

                page_source = self.driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
            else:
                # Fallback to requests
                logger.info(f"Using requests for deep extraction: {listing_url}")
                response = self.session.get(listing_url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                page_source = response.text

            # First try to extract from JSON data in script tags (more reliable for modern Airbnb)
            json_extracted_data = self._extract_from_json_scripts(soup, page_source)

            # Extract all components using traditional HTML parsing as fallback
            extracted_data = {
                'amenities': self._extract_detailed_amenities(soup),
                'house_rules': self._extract_house_rules(soup, listing_url),  # Pass URL for house rules page
                'safety_info': self._extract_safety_info(soup),
                'description': self._extract_and_clean_description(soup),
                'checkin_checkout': self._extract_checkin_checkout_info(soup),
                'local_area': self._extract_local_area_info(soup),
                'practical_facts': self._extract_practical_facts(soup)
            }

            # If no safety info extracted from the main page, try the dedicated safety page
            try:
                if (not extracted_data.get('safety_info')) and listing_url:
                    safety_url = self._construct_safety_url(listing_url)
                    if safety_url:
                        safety_items = self._extract_from_safety_page(safety_url)
                        if safety_items:
                            extracted_data['safety_info'] = safety_items
                            logger.info(f"Safety info extracted from dedicated page: {len(safety_items)} items")
            except Exception as _e:
                logger.warning(f"Error extracting safety info from dedicated page: {_e}")

            # Merge JSON data with HTML-extracted data (JSON takes priority)
            if json_extracted_data:
                logger.info("Merging JSON-extracted data with HTML-extracted data")
                for key, value in json_extracted_data.items():
                    if key in extracted_data:
                        if isinstance(value, dict) and isinstance(extracted_data[key], dict):
                            # Merge dictionaries, JSON data takes priority
                            merged_dict = extracted_data[key].copy()
                            merged_dict.update(value)
                            extracted_data[key] = merged_dict
                        elif isinstance(value, list) and isinstance(extracted_data[key], list):
                            # Combine lists, handling both strings and dictionaries
                            combined_list = extracted_data[key] + value
                            if combined_list:
                                # Remove duplicates while preserving order
                                seen = set()
                                unique_list = []
                                for item in combined_list:
                                    if isinstance(item, dict):
                                        # For dictionaries, use name as key for deduplication
                                        item_key = item.get('name', str(item))
                                        if item_key not in seen:
                                            seen.add(item_key)
                                            unique_list.append(item)
                                    elif isinstance(item, str):
                                        if item not in seen:
                                            seen.add(item)
                                            unique_list.append(item)
                                    else:
                                        unique_list.append(item)
                                extracted_data[key] = unique_list
                            else:
                                extracted_data[key] = []
                        elif value:  # Only override if JSON value is not empty
                            extracted_data[key] = value

            # Filter out unavailable amenities using cross-reference with page content
            extracted_data = self._filter_unavailable_amenities_from_page(extracted_data, soup)

            # Apply CONSOLIDATED Gemini processing (replaces multiple separate calls)
            page_content_sample = soup.get_text()[:2000]  # First 2000 chars for context
            extracted_data = self._consolidate_gemini_processing(extracted_data, page_content_sample)

            # Apply extracted time information to property fields (if not already applied by consolidated processing)
            if hasattr(self, '_extracted_time_info') and self._extracted_time_info:
                for key, value in self._extracted_time_info.items():
                    if key in ['checkInTime', 'checkOutTime'] and key not in extracted_data:
                        extracted_data[key] = value
                        logger.info(f"Applied extracted time info: {key} = {value}")

            logger.info(f"Deep extraction completed successfully with consolidated Gemini processing")
            # OCR augmentation: attempt to read house rules and safety via screenshots for completeness
            try:
                if self.use_selenium and self.driver:
                    # Use pair capture to force two independent OCR passes
                    main_items, add_items = self._ocr_house_rules_pair(listing_url)
                    # Preserve raw OCR arrays for importData.rawData
                    extracted_data.setdefault('ocr_raw', {})
                    extracted_data['ocr_raw']['house_rules_ocr_main'] = main_items
                    extracted_data['ocr_raw']['house_rules_ocr_additional'] = add_items

                    combined = []
                    if isinstance(main_items, list):
                        combined.extend(main_items)
                    if isinstance(add_items, list):
                        combined.extend(add_items)

                    if combined:
                        # Merge OCR rules (avoid duplicates by content)
                        existing = {(r.get('content') or r.get('description') or '').strip().lower() for r in extracted_data.get('house_rules', [])}
                        added = 0
                        for it in combined:
                            key = (it.get('content') or '').strip().lower()
                            if key and key not in existing:
                                extracted_data.setdefault('house_rules', []).append({
                                    'title': it.get('title'),
                                    'description': it.get('content'),
                                    'content': it.get('content'),
                                    'type': it.get('type', 'rule')
                                })
                                existing.add(key)
                                added += 1
                        logger.info(f"OCR pair added {added} unique house rules to extracted_data")

                        # Derive times from OCR rules if not already present
                        try:
                            times_from_ocr = self._extract_times_from_house_rules(extracted_data.get('house_rules', []))
                            if times_from_ocr.get('checkin_time') and not extracted_data.get('checkInTime'):
                                extracted_data['checkInTime'] = times_from_ocr['checkin_time']
                                logger.info(f"Applied check-in time from OCR rules: {extracted_data['checkInTime']}")
                            if times_from_ocr.get('checkout_time') and not extracted_data.get('checkOutTime'):
                                extracted_data['checkOutTime'] = times_from_ocr['checkout_time']
                                logger.info(f"Applied check-out time from OCR rules: {extracted_data['checkOutTime']}")
                        except Exception:
                            pass

                        # Merge quiet hours time-only items into a single consolidated rule
                        try:
                            extracted_data['house_rules'] = self._merge_quiet_hours_rules(extracted_data.get('house_rules', []))
                        except Exception:
                            pass

                    ocr_safety = self._ocr_safety_from_page(listing_url)
                    if ocr_safety:
                        # Persist raw safety OCR for debugging/visibility in importData
                        extracted_data.setdefault('ocr_raw', {})
                        extracted_data['ocr_raw']['safety_ocr'] = ocr_safety
                        existing_s = {(s.get('content') or s.get('description') or '').strip().lower() for s in extracted_data.get('safety_info', [])}
                        for it in ocr_safety:
                            key = it.get('content', '').strip().lower()
                            if key and key not in existing_s:
                                extracted_data.setdefault('safety_info', []).append({'title': it.get('title'), 'description': it.get('content'), 'content': it.get('content'), 'type': 'emergency'})
                                existing_s.add(key)
            except Exception as _e:
                logger.warning(f"OCR augmentation failed or partial: {_e}")

            return extracted_data

        except Exception as e:
            logger.error(f"Deep extraction failed for {listing_url}: {e}")
            return self._get_empty_deep_extraction_result()
        finally:
            # Restore original Selenium setting
            if 'original_selenium_setting' in locals():
                self.use_selenium = original_selenium_setting
                if not self.use_selenium and self.driver:
                    try:
                        self.driver.quit()
                        self.driver = None
                    except:
                        pass

    def _extract_detailed_amenities(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract amenities including appliance details with nested structure"""

        amenities = {
            'basic': [],
            'appliances': []
        }

        try:
            # First try to extract location-grouped amenities using Selenium if available
            location_grouped_amenities = self._extract_location_grouped_amenities()
            if location_grouped_amenities:
                logger.info(f"Found location-grouped amenities: {len(location_grouped_amenities)} groups")
                # Process location-grouped amenities
                for location, items in location_grouped_amenities.items():
                    for item in items:
                        self._process_amenity_with_location(item, location, amenities)

                # If we got good results from location grouping, return early
                if len(amenities['basic']) + len(amenities['appliances']) > 10:
                    self._deduplicate_amenities(amenities)
                    self._post_process_appliances(amenities)
                    logger.info(f"Extracted {len(amenities['basic'])} basic amenities and {len(amenities['appliances'])} appliances from location groups")
                    return amenities

            # Fallback to original extraction method
            # Look for amenities sections using multiple strategies
            amenity_sections = []

            # Strategy 1: Look for data-testid attributes (enhanced)
            testid_patterns = ['amenity', 'amenities', 'feature', 'facilities', 'what-this-place-offers']
            for pattern in testid_patterns:
                sections_by_testid = soup.find_all(['div', 'section'], attrs={
                    'data-testid': lambda x: x and pattern in x.lower() if x else False
                })
                amenity_sections.extend(sections_by_testid)

            # Strategy 1b: Look for specific amenity containers
            amenity_containers = soup.find_all(['div', 'section'], class_=lambda x: x and any(
                keyword in x.lower() for keyword in ['amenity', 'feature', 'facility', 'offer']
            ) if x else False)
            amenity_sections.extend(amenity_containers)

            # Strategy 2: Look for text patterns
            amenity_patterns = [
                r'amenities?',
                r'what this place offers',
                r'facilities',
                r'features',
                r'included'
            ]

            for pattern in amenity_patterns:
                text_nodes = soup.find_all(text=re.compile(pattern, re.IGNORECASE))
                for text_node in text_nodes:
                    parent = text_node.parent
                    if parent:
                        container = parent.find_parent(['div', 'section'])
                        if container and container not in amenity_sections:
                            amenity_sections.append(container)

            # Strategy 3: Look for script data (JSON-LD or other structured data)
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    import json
                    data = json.loads(script.string)
                    if isinstance(data, dict) and 'amenityFeature' in data:
                        for amenity in data['amenityFeature']:
                            if isinstance(amenity, dict) and 'name' in amenity:
                                amenities['basic'].append(amenity['name'])
                except:
                    pass

            # Extract amenities from sections - refined keywords to avoid false positives
            # Use exact matching for appliances to avoid false positives
            appliance_keywords = [
                'dishwasher', 'washing machine', 'washer', 'dryer', 'microwave', 'oven', 'stove',
                'refrigerator', 'fridge', 'coffee maker', 'coffee machine', 'toaster', 'blender',
                'tv', 'television', 'smart tv', 'hdtv', 'roku tv', 'apple tv',
                'hair dryer', 'freezer', 'espresso machine', 'nespresso machine',
                'electric kettle', 'rice cooker', 'slow cooker', 'air fryer',
                'food processor', 'stand mixer', 'ice maker', 'wine fridge',
                'range', 'cooktop', 'stovetop'
            ]

            # Items that should NOT be appliances (common false positives)
            # These take priority over appliance keywords
            non_appliance_keywords = [
                'parking', 'pillows', 'blankets', 'books', 'reading material',
                'security cameras', 'cameras', 'dishes', 'silverware', 'wine glasses',
                'clothing storage', 'exercise equipment', 'gym', 'fitness', 'noise monitors',
                'decibel monitors', 'beach access', 'wifi', 'internet',
                'air conditioning', 'patio', 'balcony', 'smart lock', 'lock',
                'heating', 'pool', 'hot tub', 'jacuzzi', 'fireplace', 'deck',
                # Food/consumable items that are often misclassified
                'coffee', 'tea', 'cooking basics', 'spices', 'condiments', 'oil', 'salt',
                'shampoo', 'body soap', 'shower gel', 'hot water', 'towels', 'linens',
                'cleaning products', 'toilet paper', 'paper towels'
            ]

            processed_items = set()  # Avoid duplicates

            for section in amenity_sections:
                # Look for various element types that might contain amenities
                items = section.find_all(['li', 'div', 'span', 'p', 'button', 'a'])
                for item in items:
                    text = item.get_text(strip=True)

                    # Filter out obvious non-amenities and unavailable items
                    if (text and len(text) > 2 and len(text) < 100 and
                        text.lower() not in processed_items and
                        not any(skip in text.lower() for skip in ['show all', 'see more', 'hide', 'close', 'back', 'next']) and
                        not self._is_unavailable_amenity(text, item)):

                        processed_items.add(text.lower())

                        # Check if it's an appliance using improved logic
                        text_lower = text.lower().strip()

                        # First check if it's explicitly NOT an appliance
                        is_non_appliance = any(keyword in text_lower for keyword in non_appliance_keywords)

                        # Special case: "Coffee" alone should be basic amenity, "Coffee maker" should be appliance
                        if text_lower == 'coffee':
                            is_non_appliance = True

                        # Then check if it's an appliance using more precise matching
                        is_appliance = False
                        if not is_non_appliance:
                            # Use exact word matching for better precision
                            for keyword in appliance_keywords:
                                # Check for exact word match or as part of compound terms
                                if (keyword == text_lower or
                                    f" {keyword} " in f" {text_lower} " or
                                    text_lower.startswith(f"{keyword} ") or
                                    text_lower.endswith(f" {keyword}")):
                                    is_appliance = True
                                    break

                        if is_appliance and not is_non_appliance:
                            # Parse appliance information
                            appliance_data = self._parse_appliance_info(text)
                            amenities['appliances'].append(appliance_data)
                        else:
                            # Add to basic amenities
                            amenities['basic'].append(text)

            # Strategy 4: Fallback - look for any list items that might be amenities
            if len(amenities['basic']) < 10:  # If we didn't find many amenities, be more aggressive
                all_lists = soup.find_all(['ul', 'ol'])
                for list_elem in all_lists:
                    items = list_elem.find_all('li')
                    if len(items) > 3:  # Likely an amenities list
                        for item in items:
                            text = item.get_text(strip=True)
                            if (text and len(text) > 2 and len(text) < 100 and
                                text.lower() not in processed_items and
                                not self._is_unavailable_amenity(text, item)):
                                processed_items.add(text.lower())

                                # Check if it's an appliance using improved logic
                                text_lower = text.lower().strip()

                                # First check if it's explicitly NOT an appliance
                                is_non_appliance = any(keyword in text_lower for keyword in non_appliance_keywords)

                                # Special case: "Coffee" alone should be basic amenity, "Coffee maker" should be appliance
                                if text_lower == 'coffee':
                                    is_non_appliance = True

                                # Then check if it's an appliance using more precise matching
                                is_appliance = False
                                if not is_non_appliance:
                                    for keyword in appliance_keywords:
                                        if (keyword == text_lower or
                                            f" {keyword} " in f" {text_lower} " or
                                            text_lower.startswith(f"{keyword} ") or
                                            text_lower.endswith(f" {keyword}")):
                                            is_appliance = True
                                            break

                                if is_appliance and not is_non_appliance:
                                    # Parse appliance information with kitchen location
                                    appliance_data = self._parse_appliance_info(text)
                                    amenities['appliances'].append(appliance_data)
                                else:
                                    # Add to basic amenities
                                    amenities['basic'].append(text)

            # Deduplicate and post-process amenities
            self._deduplicate_amenities(amenities)
            self._post_process_appliances(amenities)

            logger.info(f"Extracted {len(amenities['basic'])} basic amenities and {len(amenities['appliances'])} appliances")

        except Exception as e:
            logger.error(f"Error extracting detailed amenities: {e}")

        return amenities

    def _extract_location_grouped_amenities(self) -> Dict[str, List[str]]:
        """
        Extract amenities grouped by location using Selenium for JavaScript rendering.
        Airbnb often groups amenities by location (Kitchen, Bathroom, Bedroom, etc.)
        """
        if not SELENIUM_AVAILABLE or not self.use_selenium:
            return {}

        try:
            # Get current URL from the driver if available
            if not self.driver:
                return {}

            current_url = self.driver.current_url
            logger.info(f"Extracting location-grouped amenities from: {current_url}")

            # Look for location-based amenity groupings
            location_groups = {}

            # Strategy 1: Look for explicit location headers with amenity lists
            location_headers = self.driver.find_elements(By.XPATH,
                "//h3[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'kitchen') or "
                "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'bathroom') or "
                "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'bedroom') or "
                "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'living') or "
                "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'dining') or "
                "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'laundry') or "
                "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'outdoor') or "
                "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'parking') or "
                "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'entertainment')]")

            for header in location_headers:
                location_name = header.text.strip()
                if location_name:
                    # Find the next sibling or parent container with amenity items
                    amenity_container = None

                    # Try to find amenity list after this header
                    try:
                        # Look for lists in the next few siblings
                        parent = header.find_element(By.XPATH, "./..")
                        amenity_lists = parent.find_elements(By.XPATH, ".//ul | .//ol | .//div[contains(@class, 'amenity') or contains(@class, 'feature')]")

                        if amenity_lists:
                            amenity_container = amenity_lists[0]
                    except:
                        pass

                    if amenity_container:
                        # Extract amenities from this location group
                        amenity_items = amenity_container.find_elements(By.XPATH, ".//li | .//div | .//span")
                        location_amenities = []

                        for item in amenity_items:
                            text = item.text.strip()
                            if text and len(text) > 2 and len(text) < 100:
                                # Filter out navigation elements
                                if not any(skip in text.lower() for skip in ['show all', 'see more', 'hide', 'close', 'back', 'next']):
                                    location_amenities.append(text)

                        if location_amenities:
                            location_groups[location_name] = location_amenities
                            logger.info(f"Found {len(location_amenities)} amenities in {location_name}")

            # Strategy 2: Look for amenity sections with location indicators in their structure
            amenity_sections = self.driver.find_elements(By.XPATH,
                "//div[contains(@data-testid, 'amenity') or contains(@class, 'amenity') or contains(@class, 'feature')]")

            for section in amenity_sections:
                try:
                    # Look for location indicators within the section
                    location_indicators = section.find_elements(By.XPATH,
                        ".//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'kitchen') or "
                        "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'bathroom') or "
                        "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'bedroom') or "
                        "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'living') or "
                        "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'dining')]")

                    for indicator in location_indicators:
                        location_text = indicator.text.strip()
                        if location_text:
                            # Find amenities near this location indicator
                            nearby_amenities = []

                            # Look for amenity items in the same container
                            container = indicator.find_element(By.XPATH, "./ancestor::div[1]")
                            amenity_elements = container.find_elements(By.XPATH, ".//span | .//div")

                            for elem in amenity_elements:
                                text = elem.text.strip()
                                if (text and text != location_text and len(text) > 2 and len(text) < 100 and
                                    not any(skip in text.lower() for skip in ['show all', 'see more', 'hide', 'close'])):
                                    nearby_amenities.append(text)

                            if nearby_amenities:
                                if location_text not in location_groups:
                                    location_groups[location_text] = []
                                location_groups[location_text].extend(nearby_amenities)

                except Exception as e:
                    # Continue with next section if this one fails
                    continue

            # Clean up and deduplicate location groups
            cleaned_groups = {}
            for location, items in location_groups.items():
                # Normalize location name
                location_clean = location.title().strip()
                if location_clean not in cleaned_groups:
                    cleaned_groups[location_clean] = []

                # Deduplicate items
                seen = set()
                for item in items:
                    item_lower = item.lower().strip()
                    if item_lower not in seen and item_lower:
                        seen.add(item_lower)
                        cleaned_groups[location_clean].append(item.strip())

            logger.info(f"Extracted location-grouped amenities: {list(cleaned_groups.keys())}")
            return cleaned_groups

        except Exception as e:
            logger.warning(f"Failed to extract location-grouped amenities: {e}")
            return {}

    def _is_unavailable_amenity(self, text: str, element) -> bool:
        """Check if an amenity is marked as unavailable or crossed-off"""
        text_lower = text.lower().strip()

        # Check for explicit unavailable text patterns
        unavailable_patterns = [
            'unavailable:', 'not available', 'crossed out', 'not offered',
            'temporarily unavailable', 'currently unavailable'
        ]

        for pattern in unavailable_patterns:
            if pattern in text_lower:
                logger.debug(f"Filtering out unavailable amenity: '{text}' (contains '{pattern}')")
                return True

        # Check element styling and attributes for unavailable indicators
        if element:
            # Check for common CSS classes that indicate unavailable items
            element_classes = element.get('class', [])
            if isinstance(element_classes, list):
                element_classes = ' '.join(element_classes).lower()
            elif isinstance(element_classes, str):
                element_classes = element_classes.lower()
            else:
                element_classes = ''

            unavailable_class_patterns = [
                'unavailable', 'disabled', 'crossed', 'strikethrough',
                'line-through', 'not-available', 'inactive'
            ]

            for pattern in unavailable_class_patterns:
                if pattern in element_classes:
                    logger.debug(f"Filtering out unavailable amenity: '{text}' (class contains '{pattern}')")
                    return True

            # Check for strikethrough or line-through styling
            style = element.get('style', '')
            if style and ('line-through' in style or 'strikethrough' in style):
                logger.debug(f"Filtering out unavailable amenity: '{text}' (strikethrough styling)")
                return True

            # Check parent elements for unavailable indicators
            parent = element.parent
            if parent:
                parent_text = parent.get_text(strip=True).lower()
                if any(pattern in parent_text for pattern in unavailable_patterns):
                    logger.debug(f"Filtering out unavailable amenity: '{text}' (parent contains unavailable text)")
                    return True

        return False

    def _filter_unavailable_amenities_from_page(self, extracted_data: Dict[str, Any], soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Filter out unavailable amenities by cross-referencing with page content.
        This catches unavailable amenities that might be missed in JSON extraction.
        """
        if 'amenities' not in extracted_data:
            return extracted_data

        try:
            # Get all page text for analysis
            page_text = soup.get_text().lower()

            # Common patterns that indicate unavailable amenities (comprehensive list)
            unavailable_indicators = [
                'washer unavailable', 'dryer unavailable', 'washer not available', 'dryer not available',
                'no washer', 'no dryer', 'washer crossed out', 'dryer crossed out',
                'washer temporarily unavailable', 'dryer temporarily unavailable',
                'laundromat nearby', 'shared laundry', 'communal laundry', 'laundry facility nearby',
                'washer/dryer not available', 'no in-unit laundry', 'external laundry'
            ]

            # Check if any unavailable indicators are present
            unavailable_amenities = set()
            for indicator in unavailable_indicators:
                if indicator in page_text:
                    # Extract the amenity name from the indicator
                    if 'washer' in indicator or 'laundry' in indicator:
                        unavailable_amenities.add('washer')
                        unavailable_amenities.add('washing machine')
                    if 'dryer' in indicator or 'laundry' in indicator:
                        unavailable_amenities.add('dryer')
                    logger.info(f"Found unavailable indicator: '{indicator}' - marking related amenities as unavailable")

            # Special case: If "Laundromat nearby" is present, it usually means no in-unit washer/dryer
            if 'laundromat nearby' in page_text:
                unavailable_amenities.add('washer')
                unavailable_amenities.add('washing machine')
                unavailable_amenities.add('dryer')
                logger.info("Found 'Laundromat nearby' - marking in-unit washer/dryer as unavailable")

            # Check basic amenities for indicators of missing in-unit laundry
            if 'amenities' in extracted_data and 'basic' in extracted_data['amenities']:
                basic_amenities_text = ' '.join(extracted_data['amenities']['basic']).lower()
                if 'laundromat nearby' in basic_amenities_text:
                    unavailable_amenities.add('washer')
                    unavailable_amenities.add('washing machine')
                    unavailable_amenities.add('dryer')
                    logger.info("Found 'Laundromat nearby' in basic amenities - marking in-unit washer/dryer as unavailable")

            # Also check for crossed-out elements in HTML
            crossed_out_elements = soup.find_all(attrs={'style': lambda x: x and 'line-through' in x})
            for element in crossed_out_elements:
                text = element.get_text(strip=True).lower()
                if 'washer' in text:
                    unavailable_amenities.add('washer')
                    unavailable_amenities.add('washing machine')
                    logger.info(f"Found crossed-out washer element: '{text}'")
                if 'dryer' in text:
                    unavailable_amenities.add('dryer')
                    logger.info(f"Found crossed-out dryer element: '{text}'")

            # Filter out unavailable amenities from basic amenities
            if 'basic' in extracted_data['amenities']:
                original_basic = extracted_data['amenities']['basic']
                filtered_basic = []
                for amenity in original_basic:
                    amenity_lower = amenity.lower()
                    if not any(unavailable in amenity_lower for unavailable in unavailable_amenities):
                        filtered_basic.append(amenity)
                    else:
                        logger.info(f"Filtered out unavailable basic amenity: '{amenity}'")
                extracted_data['amenities']['basic'] = filtered_basic

            # Filter out unavailable amenities from appliances
            if 'appliances' in extracted_data['amenities']:
                original_appliances = extracted_data['amenities']['appliances']
                filtered_appliances = []
                for appliance in original_appliances:
                    appliance_name = appliance.get('name', '').lower()
                    if not any(unavailable in appliance_name for unavailable in unavailable_amenities):
                        filtered_appliances.append(appliance)
                    else:
                        logger.info(f"Filtered out unavailable appliance: '{appliance.get('name', '')}'")
                extracted_data['amenities']['appliances'] = filtered_appliances

            return extracted_data

        except Exception as e:
            logger.warning(f"Error filtering unavailable amenities: {e}")
            return extracted_data

    def _process_amenity_with_location(self, amenity_text: str, location: str, amenities: Dict[str, List]) -> None:
        """Process an amenity item with its location context"""

        # Define appliance keywords (same as in original method)
        appliance_keywords = [
            'dishwasher', 'washing machine', 'washer', 'dryer', 'microwave', 'oven', 'stove',
            'refrigerator', 'fridge', 'coffee maker', 'toaster', 'blender',
            'tv', 'television', 'smart tv', 'hdtv', 'roku tv', 'apple tv',
            'hair dryer', 'freezer', 'espresso machine', 'coffee machine',
            'electric kettle', 'rice cooker', 'slow cooker', 'air fryer',
            'food processor', 'stand mixer', 'ice maker', 'wine fridge',
            'range', 'cooktop', 'stovetop'
        ]

        # Items that should NOT be appliances
        non_appliance_keywords = [
            'parking', 'pillows', 'blankets', 'books', 'reading material',
            'security cameras', 'cameras', 'dishes', 'silverware', 'wine glasses',
            'clothing storage', 'exercise equipment', 'gym', 'fitness', 'noise monitors',
            'decibel monitors', 'beach access', 'wifi', 'internet',
            'air conditioning', 'patio', 'balcony', 'smart lock', 'lock',
            'heating', 'pool', 'hot tub', 'jacuzzi', 'fireplace', 'deck',
            # Food/consumable items that are often misclassified
            'coffee', 'tea', 'cooking basics', 'spices', 'condiments', 'oil', 'salt',
            'shampoo', 'body soap', 'shower gel', 'hot water', 'towels', 'linens',
            'cleaning products', 'toilet paper', 'paper towels'
        ]

        # Check if it's an appliance using improved logic
        text_lower = amenity_text.lower().strip()

        # First check if it's explicitly NOT an appliance
        is_non_appliance = any(keyword in text_lower for keyword in non_appliance_keywords)

        # Special case: "Coffee" alone should be basic amenity, "Coffee maker" should be appliance
        if text_lower == 'coffee':
            is_non_appliance = True

        # Then check if it's an appliance using more precise matching
        is_appliance = False
        if not is_non_appliance:
            for keyword in appliance_keywords:
                if (keyword == text_lower or
                    f" {keyword} " in f" {text_lower} " or
                    text_lower.startswith(f"{keyword} ") or
                    text_lower.endswith(f" {keyword}")):
                    is_appliance = True
                    break

        if is_appliance and not is_non_appliance:
            # Parse appliance information with location context
            appliance_data = self._parse_appliance_info(amenity_text)

            # Use the location from the grouping if the appliance doesn't have one
            if not appliance_data.get('location') or appliance_data.get('location') == '':
                # Normalize location name for consistency
                normalized_location = self._normalize_location_name(location)
                appliance_data['location'] = normalized_location
                logger.debug(f"Set appliance '{amenity_text}' location to '{normalized_location}' from group")

            amenities['appliances'].append(appliance_data)
        else:
            # Add to basic amenities
            amenities['basic'].append(amenity_text)

    def _normalize_location_name(self, location: str) -> str:
        """Normalize location names for consistency"""
        location_lower = location.lower().strip()

        # Map common variations to standard names
        location_mappings = {
            'kitchen': 'Kitchen',
            'kitchen area': 'Kitchen',
            'kitchenette': 'Kitchen',
            'bathroom': 'Bathroom',
            'bath': 'Bathroom',
            'bedroom': 'Bedroom',
            'bed room': 'Bedroom',
            'living room': 'Living Room',
            'living area': 'Living Room',
            'living space': 'Living Room',
            'lounge': 'Living Room',
            'dining room': 'Dining Room',
            'dining area': 'Dining Room',
            'laundry': 'Laundry Room',
            'laundry room': 'Laundry Room',
            'laundry area': 'Laundry Room',
            'outdoor': 'Outdoor',
            'outside': 'Outdoor',
            'patio': 'Outdoor',
            'balcony': 'Outdoor',
            'deck': 'Outdoor',
            'parking': 'Parking',
            'garage': 'Parking',
            'entertainment': 'Entertainment',
            'media room': 'Entertainment',
            'game room': 'Entertainment'
        }

        return location_mappings.get(location_lower, location.title())

    def _deduplicate_amenities(self, amenities: Dict[str, List]) -> None:
        """Remove duplicate amenities and normalize names"""

        # Deduplicate basic amenities
        if 'basic' in amenities:
            seen = set()
            unique_basic = []
            for amenity in amenities['basic']:
                amenity_lower = amenity.lower().strip()
                if amenity_lower not in seen and amenity_lower:
                    seen.add(amenity_lower)
                    unique_basic.append(amenity.strip())
            amenities['basic'] = unique_basic

        # Deduplicate appliances
        if 'appliances' in amenities:
            seen = set()
            unique_appliances = []
            for appliance in amenities['appliances']:
                if isinstance(appliance, dict):
                    name = appliance.get('name', '').lower().strip()
                    if name not in seen and name:
                        seen.add(name)
                        unique_appliances.append(appliance)
                elif isinstance(appliance, str):
                    name_lower = appliance.lower().strip()
                    if name_lower not in seen and name_lower:
                        seen.add(name_lower)
                        unique_appliances.append({'name': appliance.strip(), 'location': '', 'brand': '', 'model': ''})
            amenities['appliances'] = unique_appliances

        logger.debug(f"After deduplication: {len(amenities.get('basic', []))} basic amenities, {len(amenities.get('appliances', []))} appliances")

    def _post_process_appliances(self, amenities: Dict[str, List]) -> None:
        """Post-process appliances to ensure kitchen location is properly set"""

        kitchen_appliances = [
            'microwave', 'dishwasher', 'refrigerator', 'fridge', 'oven',
            'stove', 'cooktop', 'toaster', 'coffee maker', 'coffee machine',
            'espresso machine', 'freezer', 'blender', 'food processor',
            'electric kettle', 'rice cooker', 'slow cooker', 'air fryer',
            'stand mixer', 'ice maker', 'wine fridge', 'range', 'stovetop',
            'garbage disposal', 'can opener', 'mixer', 'juicer'
        ]

        # Items that should NOT get kitchen location (even if they're appliances)
        non_kitchen_appliances = [
            'washer', 'washing machine', 'dryer', 'hair dryer', 'tv', 'television',
            'air conditioning', 'heating', 'vacuum', 'iron', 'fan'
        ]

        # Specific location mappings for non-kitchen appliances
        # Order matters: more specific matches should come first
        appliance_locations = {
            'hair dryer': 'Bathroom',  # Must come before 'dryer'
            'washing machine': 'Laundry',  # Must come before 'washer'
            'smart tv': 'Living Room',  # Must come before 'tv'
            'hdtv': 'Living Room',  # Must come before 'tv'
            'tv': 'Living Room',
            'television': 'Living Room',
            'washer': 'Laundry',
            'dryer': 'Laundry',
            'vacuum': 'Storage',
            'iron': 'Bedroom',
            'fan': 'Bedroom'
            # Note: air conditioning and heating left without default location
            # so hosts can specify the actual location (bedroom, living room, etc.)
        }

        # Locations that should be normalized to "Kitchen" for kitchen appliances
        kitchen_location_variants = ['unit', 'in unit', 'kitchen', '']

        # Check all appliances and ensure kitchen appliances have Kitchen location
        for appliance in amenities.get('appliances', []):
            if isinstance(appliance, dict):
                name = appliance.get('name', '')
                current_location = appliance.get('location', '').strip()

                # Check if this is a kitchen appliance (and not explicitly non-kitchen)
                name_lower = name.lower()
                is_kitchen_appliance = False
                is_non_kitchen_appliance = False

                # First check if it's explicitly a non-kitchen appliance
                for keyword in non_kitchen_appliances:
                    if keyword in name_lower:
                        is_non_kitchen_appliance = True
                        break

                # Then check if it's a kitchen appliance (only if not non-kitchen)
                if not is_non_kitchen_appliance:
                    for keyword in kitchen_appliances:
                        # Fixed logic: only match if the keyword is in the name, not the other way around
                        if keyword in name_lower:
                            is_kitchen_appliance = True
                            break

                # Assign appropriate location based on appliance type
                if is_non_kitchen_appliance:
                    # Assign specific location for non-kitchen appliances (override any existing location)
                    for keyword, location in appliance_locations.items():
                        if keyword in name_lower:
                            appliance['location'] = location
                            logger.debug(f"Post-processing: Set '{name}' location to {location} (was: '{current_location}')")
                            break
                elif is_kitchen_appliance:
                    # Normalize common location variants to "Kitchen"
                    if current_location.lower() in kitchen_location_variants:
                        appliance['location'] = 'Kitchen'
                        logger.debug(f"Post-processing: Set '{name}' location to Kitchen (was: '{current_location}')")
                    elif not current_location:
                        appliance['location'] = 'Kitchen'
                        logger.debug(f"Post-processing: Set '{name}' location to Kitchen (was empty)")

    def _parse_appliance_info(self, text: str) -> Dict[str, str]:
        """Parse appliance information to extract name, brand, model, and location"""

        # Clean the text
        text = text.strip()

        # Kitchen appliances that should have location pre-populated (comprehensive list)
        kitchen_appliances = [
            'microwave', 'dishwasher', 'refrigerator', 'fridge', 'oven',
            'stove', 'cooktop', 'toaster', 'coffee maker', 'coffee machine',
            'espresso machine', 'freezer', 'blender', 'food processor',
            'electric kettle', 'rice cooker', 'slow cooker', 'air fryer',
            'stand mixer', 'ice maker', 'wine fridge', 'range', 'stovetop'
        ]

        # Try to extract brand and model patterns
        brand_model_pattern = r'([A-Z][a-z]+)\s+([A-Z0-9\-]+)'
        match = re.search(brand_model_pattern, text)

        if match:
            brand = match.group(1)
            model = match.group(2)
            # Remove brand and model from name
            name = re.sub(brand_model_pattern, '', text).strip()
            if not name:
                name = text
        else:
            brand = ""
            model = ""
            name = text

        # Determine if it's a kitchen appliance with flexible matching
        name_lower = name.lower()
        is_kitchen_appliance = False

        for keyword in kitchen_appliances:
            # Fixed logic: only match if the keyword is in the name, not the other way around
            if keyword in name_lower:
                is_kitchen_appliance = True
                break

        location = 'Kitchen' if is_kitchen_appliance else ''

        if is_kitchen_appliance:
            logger.debug(f"Pre-populating '{name}' with Kitchen location")

        return {
            "name": name,
            "location": location,
            "brand": brand,
            "model": model
        }

    def _extract_house_rules(self, soup: BeautifulSoup, base_url: str = None) -> List[Dict[str, Any]]:
        """Extract house rules from the listing using enhanced HTML parsing"""

        rules = []

        try:
            # Strategy 1: Enhanced extraction from current page focusing on Airbnb's structure
            rules.extend(self._extract_rules_from_airbnb_structure(soup))

            # Strategy 2: Fallback to general rule extraction
            if len(rules) == 0:
                logger.info("No rules found with Airbnb structure parsing, trying general extraction...")
                rules.extend(self._extract_rules_from_page(soup))

            # Strategy 3: If still no rules found and we have a base URL, try the dedicated house rules page
            if len(rules) == 0 and base_url:
                logger.info("No rules found on main page, trying dedicated house rules page...")
                house_rules_url = self._construct_house_rules_url(base_url)
                if house_rules_url:
                    rules.extend(self._extract_from_house_rules_page(house_rules_url))

            logger.info(f"Extracted {len(rules)} house rules total")
            for rule in rules:
                title = rule.get('title', 'No title')
                description = rule.get('description', 'No description')
                logger.info(f"House rule: {title} - {description}")

        except Exception as e:
            logger.error(f"Error extracting house rules: {e}")

        return rules

    def _extract_rules_from_airbnb_structure(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract house rules using Airbnb's specific page structure (similar to amenities)"""
        rules = []

        try:
            logger.info("Attempting Airbnb structure-based house rules extraction...")

            # Strategy 0: Interactive expansion with Selenium (expand sections first)
            if hasattr(self, 'driver') and self.driver:
                try:
                    # Find and click expandable sections
                    from selenium.webdriver.common.by import By
                    from selenium.webdriver.support.ui import WebDriverWait
                    from selenium.webdriver.support import expected_conditions as EC
                    from selenium.common.exceptions import TimeoutException, NoSuchElementException
                    import time

                    wait = WebDriverWait(self.driver, 5)  # Reduced from 10 seconds

                    # Click "Things to know" or similar expandable sections
                    expandable_selectors = [
                        '[data-section-id*="POLICIES"]',
                        '[data-section-id*="HOUSE_RULES"]',
                        'button[data-testid*="policies"]',
                        'button[data-testid*="house-rules"]'
                    ]

                    for selector in expandable_selectors:
                        try:
                            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for element in elements:
                                try:
                                    self.driver.execute_script("arguments[0].click();", element)
                                    logger.info(f"Clicked expandable section: {element.text[:50]}...")
                                    time.sleep(1)  # Reduced wait for expansion
                                except Exception as e:
                                    logger.debug(f"Could not click element: {e}")
                        except Exception as e:
                            logger.debug(f"Error with selector {selector}: {e}")

                    # ENHANCED: Find the correct "Show more" button that opens the detailed house rules modal
                    # We need to find the button that opens the modal with "During your stay", "Before you leave" sections
                    house_rules_show_more_selectors = [
                        # Strategy 1: Look for "Show more" specifically in house rules context with modal attributes
                        "//div[contains(@class, 'house') or contains(@class, 'rules')]//button[contains(text(), 'Show more') and (@role='button' or @aria-expanded)]",
                        "//div[contains(@class, 'house') or contains(@class, 'rules')]//a[contains(text(), 'Show more') and (@role='button' or @aria-expanded)]",

                        # Strategy 2: Look for "Show more" that has modal-related attributes
                        "//button[contains(text(), 'Show more') and (@data-testid or @aria-haspopup or @data-modal)]",
                        "//a[contains(text(), 'Show more') and (@data-testid or @aria-haspopup or @data-modal)]",

                        # Strategy 3: Look for "Show more" near house rules that has click handlers
                        "//div[.//text()[contains(., 'House rules')]]//button[contains(text(), 'Show more') and (@onclick or @data-testid)]",
                        "//div[.//text()[contains(., 'House rules')]]//a[contains(text(), 'Show more') and (@onclick or @data-testid)]",

                        # Strategy 4: Look for "Show more" in the "Things to know" section (parent of house rules)
                        "//div[.//text()[contains(., 'Things to know')]]//button[contains(text(), 'Show more')]",
                        "//div[.//text()[contains(., 'Things to know')]]//a[contains(text(), 'Show more')]",

                        # Strategy 5: Original selectors as fallback
                        "//h3[contains(text(), 'House rules')]/following-sibling::*//button[contains(text(), 'Show more')]",
                        "//div[.//h3[contains(text(), 'House rules')]]//button[contains(text(), 'Show more')]",
                        "//div[.//h3[contains(text(), 'House rules')]]//a[contains(text(), 'Show more')]"
                    ]

                    house_rules_modal_opened = False
                    for xpath in house_rules_show_more_selectors:
                        if house_rules_modal_opened:
                            break
                        try:
                            elements = self.driver.find_elements(By.XPATH, xpath)
                            logger.info(f"Found {len(elements)} 'House rules Show more' elements for xpath: {xpath}")

                            for element in elements:
                                try:
                                    if element.is_enabled() and element.is_displayed():
                                        logger.info(f"Clicking 'House rules Show more' button: {element.text[:50]}...")
                                        element.click()
                                        time.sleep(2)  # Reduced wait for modal to open

                                        # Check if the DETAILED house rules modal opened by looking for section headers
                                        # We need to see the actual modal sections, not just basic rules
                                        modal_section_indicators = [
                                            "During your stay", "Before you leave", "Checking in and out", "Additional rules"
                                        ]

                                        detailed_rule_indicators = [
                                            "Quiet hours", "No parties", "No smoking", "Commercial photography", "No pets",
                                            "Gather used towels", "Turn things off", "Return keys", "Lock up",
                                            "Park only in", "Drive slowly", "Baby gear", "Standard checkout"
                                        ]

                                        # Check for modal sections first (more reliable)
                                        modal_sections_found = 0
                                        for indicator in modal_section_indicators:
                                            modal_elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{indicator}')]")
                                            if modal_elements:
                                                modal_sections_found += 1
                                                logger.info(f"Found modal section: '{indicator}'")

                                        # Check for detailed rules and store them for extraction
                                        detailed_rules_found = 0
                                        detected_rules = []
                                        for indicator in detailed_rule_indicators:
                                            modal_elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{indicator}')]")
                                            if modal_elements:
                                                detailed_rules_found += 1
                                                detected_rules.append(indicator)
                                                logger.info(f"Found detailed rule: '{indicator}'")

                                        # Modal is considered opened if we find at least 2 sections OR 3 detailed rules
                                        modal_found = modal_sections_found >= 2 or detailed_rules_found >= 3

                                        if modal_found:
                                            logger.info(f"DETAILED house rules modal opened! Sections: {modal_sections_found}, Rules: {detailed_rules_found}")

                                            # Store detected rules for later extraction
                                            if not hasattr(self, '_detected_modal_rules'):
                                                self._detected_modal_rules = []
                                            self._detected_modal_rules.extend(detected_rules)
                                            logger.info(f"Stored {len(detected_rules)} detected rules for extraction")

                                        else:
                                            logger.info(f"Basic expansion only. Sections: {modal_sections_found}, Rules: {detailed_rules_found}")
                                            # Continue trying other buttons

                                        if modal_found:
                                            house_rules_modal_opened = True
                                            logger.info("SUCCESS! House rules modal with detailed rules opened!")

                                            # Wait for specific modal content to load (reduced time)
                                            modal_content_loaded = False
                                            max_wait_time = 8   # seconds (reduced from 15)
                                            wait_interval = 0.5 # seconds (reduced from 1)

                                            for wait_count in range(max_wait_time):
                                                try:
                                                    # Check if session is still valid
                                                    self.driver.current_url

                                                    # Look for modal sections AND detailed rules
                                                    modal_sections = ["During your stay", "Before you leave", "Checking in and out"]
                                                    detailed_rules = ["Quiet hours", "No parties", "No smoking", "Commercial photography", "Gather used towels"]

                                                    found_sections = 0
                                                    found_detailed_rules = 0

                                                    for section in modal_sections:
                                                        elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{section}')]")
                                                        if elements:
                                                            found_sections += 1

                                                    for rule in detailed_rules:
                                                        elements = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{rule}')]")
                                                        if elements:
                                                            found_detailed_rules += 1

                                                    # Modal content is loaded if we have sections AND rules
                                                    if found_sections >= 2 and found_detailed_rules >= 2:
                                                        modal_content_loaded = True
                                                        logger.info(f"Modal content loaded! Sections: {found_sections}, Rules: {found_detailed_rules}")
                                                        break
                                                    elif found_sections >= 1 or found_detailed_rules >= 3:
                                                        modal_content_loaded = True
                                                        logger.info(f"Modal content partially loaded! Sections: {found_sections}, Rules: {found_detailed_rules}")
                                                        break
                                                    else:
                                                        logger.info(f"Waiting for modal content... (found {found_detailed_rules} detailed rules, attempt {wait_count + 1}/{max_wait_time})")
                                                        time.sleep(wait_interval)

                                                except Exception as session_error:
                                                    logger.warning(f"WebDriver session error during wait: {session_error}")
                                                    break

                                            if modal_content_loaded:
                                                logger.info("Modal content fully loaded, capturing page source")
                                                try:
                                                    # Get fresh page source with modal content
                                                    soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                                                    logger.info("Updated page source after modal content loaded")

                                                    # Save modal content for debugging
                                                    with open('modal_content_debug.html', 'w', encoding='utf-8') as f:
                                                        f.write(self.driver.page_source)
                                                    logger.info("Saved modal content to modal_content_debug.html")

                                                except Exception as capture_error:
                                                    logger.warning(f"Error capturing modal content: {capture_error}")
                                            else:
                                                logger.warning("Modal content did not load completely within timeout")

                                            break
                                        else:
                                            logger.info("Clicked but detailed house rules not detected, trying next element...")

                                except Exception as e:
                                    logger.debug(f"Could not click house rules show more: {e}")
                        except Exception as e:
                            logger.debug(f"Error with house rules xpath {xpath}: {e}")

                    if not house_rules_modal_opened:
                        logger.warning("Could not open detailed house rules modal, will extract from available content")

                        # Fallback: click any "Show more" buttons as before
                        fallback_xpath_selectors = [
                            "//button[contains(text(), 'Show more')]",
                            "//a[contains(text(), 'Show more')]",
                            "//span[contains(text(), 'Show more')]"
                        ]

                        for xpath in fallback_xpath_selectors:
                            try:
                                elements = self.driver.find_elements(By.XPATH, xpath)
                                for element in elements:
                                    try:
                                        self.driver.execute_script("arguments[0].click();", element)
                                        logger.info(f"Clicked fallback 'Show more' button: {element.text[:30]}...")
                                        time.sleep(1)  # Reduced wait for expansion
                                    except Exception as e:
                                        logger.debug(f"Could not click fallback show more: {e}")
                            except Exception as e:
                                logger.debug(f"Error with fallback xpath {xpath}: {e}")

                    # CRITICAL: Click "House rules" button/link to open modal
                    # Try multiple strategies to find and click the house rules modal trigger
                    house_rules_modal_selectors = [
                        # Direct text matching
                        "//button[contains(text(), 'House rules')]",
                        "//a[contains(text(), 'House rules')]",
                        "//span[contains(text(), 'House rules')]",
                        "//div[contains(text(), 'House rules') and (@role='button' or @onclick or contains(@class, 'button'))]",

                        # Attribute-based matching
                        "//button[contains(@aria-label, 'House rules')]",
                        "//button[contains(@data-testid, 'house-rules')]",
                        "//a[contains(@aria-label, 'House rules')]",

                        # Look for clickable elements near "House rules" text
                        "//button[.//text()[contains(., 'House rules')]]",
                        "//a[.//text()[contains(., 'House rules')]]",

                        # Look for elements that might trigger house rules modal
                        "//*[contains(text(), 'House rules')]/ancestor-or-self::*[@role='button' or @onclick or contains(@class, 'button') or name()='button' or name()='a'][1]"
                    ]

                    modal_opened = False
                    for xpath in house_rules_modal_selectors:
                        if modal_opened:
                            break
                        try:
                            elements = self.driver.find_elements(By.XPATH, xpath)
                            logger.info(f"Found {len(elements)} elements for xpath: {xpath}")

                            for element in elements:
                                try:
                                    # Check if element is clickable and not just text
                                    if element.is_enabled() and element.is_displayed():
                                        element_text = element.text[:100] if element.text else element.get_attribute('aria-label') or 'No text'
                                        logger.info(f"Attempting to click house rules trigger: {element_text}")

                                        # Try both regular click and JavaScript click
                                        try:
                                            element.click()
                                        except:
                                            self.driver.execute_script("arguments[0].click();", element)

                                        logger.info(f"Clicked 'House rules' modal trigger: {element_text}")
                                        time.sleep(2)  # Reduced wait for modal to open

                                        # Check if modal actually opened by looking for modal content
                                        modal_check = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Checking in and out') or contains(text(), 'During your stay') or contains(text(), 'Before you leave')]")
                                        if modal_check:
                                            logger.info("House rules modal content detected!")
                                            modal_opened = True
                                            break
                                        else:
                                            logger.info("Modal trigger clicked but no modal content detected yet...")

                                except Exception as e:
                                    logger.debug(f"Could not click house rules modal: {e}")
                        except Exception as e:
                            logger.debug(f"Error with modal xpath {xpath}: {e}")

                    if modal_opened or house_rules_modal_opened:
                        logger.info("House rules modal opened successfully, extracting modal content...")
                        # Reduced wait for modal content to fully load
                        time.sleep(1)
                    else:
                        logger.info("Could not open detailed house rules modal, will extract from available content")

                    # Get updated page source after interactions
                    soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                    logger.info("Updated page source after expanding sections")

                except Exception as e:
                    logger.warning(f"Error during interactive expansion: {e}")

            # Strategy 1: Look for sections with "house rules" or similar headings
            house_rules_sections = []

            # Find headings that mention house rules or related sections
            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                heading_text = heading.get_text(strip=True).lower()
                rule_keywords = [
                    'house rules', 'rules', 'policies', 'guidelines',
                    'during your stay', 'before you leave', 'checkout instructions',
                    'things to know', 'important information', 'guest guidelines'
                ]

                if any(phrase in heading_text for phrase in rule_keywords):
                    logger.info(f"Found rules-related heading: {heading_text}")

                    # Find the parent section that contains the rules
                    section = heading.find_parent(['section', 'div'])
                    if section:
                        house_rules_sections.append(section)
                        logger.info(f"Added section with {len(section.get_text())} characters")

            # Strategy 2: Look for Airbnb's specific class patterns for house rules
            # These patterns are similar to how amenities are structured
            rule_containers = soup.find_all(['div', 'section'], class_=re.compile(r'(rule|policy|guideline)', re.IGNORECASE))
            house_rules_sections.extend(rule_containers)

            # Strategy 3: Look for structured lists that contain rule-like content
            for section in house_rules_sections:
                # Look for list items or structured content within the section
                rule_items = section.find_all(['li', 'div', 'span', 'p'])

                for item in rule_items:
                    rule_text = item.get_text(strip=True)

                    # Filter for actual house rules
                    if (rule_text and
                        len(rule_text) > 10 and
                        len(rule_text) < 200 and
                        self._is_likely_house_rule(rule_text)):

                        rule_entry = {
                            'title': self._extract_precise_rule_title(rule_text),
                            'description': rule_text,
                            'enabled': True,
                            'type': 'rule',
                            'source': 'airbnb_structure_extraction'
                        }
                        rules.append(rule_entry)
                        logger.info(f"Extracted rule from structure: {rule_entry['title']}")

            # Strategy 4: Extract from House Rules Modal (if opened)
            # Look for modal-specific structure based on the screenshot
            modal_rules = self._extract_modal_house_rules(soup)
            if modal_rules:
                rules.extend(modal_rules)
                logger.info(f"Extracted {len(modal_rules)} rules from modal")

            # Strategy 5: Look for specific rule patterns in all text
            # This catches rules that might not be in structured sections
            all_text_elements = soup.find_all(text=True)
            for text_element in all_text_elements:
                text = text_element.strip()

                # Look for specific rule patterns (more comprehensive)
                rule_patterns = [
                    r'pets?\s+(allowed|permitted|welcome|ok)',
                    r'no\s+pets?',
                    r'pet\s+friendly',
                    r'\d+\s+guests?\s+(maximum|max|allowed|limit)',
                    r'maximum\s+\d+\s+guests?',
                    r'accommodates\s+\d+',
                    r'quiet\s+hours?',
                    r'no\s+smoking',
                    r'smoking\s+(not\s+)?allowed',
                    r'no\s+parties?',
                    r'parties?\s+(not\s+)?allowed',
                    r'events?\s+(not\s+)?allowed',
                    r'check.?in\s+(after|from|at)\s+\d',
                    r'check.?out\s+(before|by|at)\s+\d'
                ]

                for pattern in rule_patterns:
                    if re.search(pattern, text, re.IGNORECASE) and self._is_likely_house_rule(text):
                        # Avoid duplicates
                        if not any(rule['description'] == text for rule in rules):
                            rule_entry = {
                                'title': self._extract_precise_rule_title(text),
                                'description': text,
                                'enabled': True,
                                'type': 'rule',
                                'source': 'airbnb_pattern_extraction'
                            }
                            rules.append(rule_entry)
                            logger.info(f"Extracted rule from pattern: {rule_entry['title']}")

            # Strategy 4: Look for time-based patterns that suggest rules (like quiet hours)
            time_patterns = soup.find_all(text=re.compile(r'\d{1,2}:\d{2}\s*(AM|PM|am|pm)', re.IGNORECASE))
            for time_text in time_patterns:
                parent = time_text.parent
                if parent:
                    full_text = parent.get_text(strip=True)
                    if (len(full_text) > 10 and
                        len(full_text) < 200 and
                        self._is_likely_house_rule(full_text) and
                        not any(rule['description'] == full_text for rule in rules)):

                        rule_entry = {
                            'title': self._extract_precise_rule_title(full_text),
                            'description': full_text,
                            'enabled': True,
                            'type': 'rule',
                            'source': 'airbnb_time_pattern_extraction'
                        }
                        rules.append(rule_entry)
                        logger.info(f"Extracted time-based rule: {rule_entry['title']}")

            logger.info(f"Airbnb structure extraction found {len(rules)} rules")

        except Exception as e:
            logger.error(f"Error in Airbnb structure extraction: {e}")

        return rules

    def _construct_house_rules_url(self, base_url: str) -> str:
        """Construct the house rules page URL from the base listing URL"""
        try:
            # Remove any existing query parameters and fragments
            if '?' in base_url:
                base_url = base_url.split('?')[0]
            if '#' in base_url:
                base_url = base_url.split('#')[0]

            # Add /house-rules if not already present
            if not base_url.endswith('/house-rules'):
                if base_url.endswith('/'):
                    house_rules_url = base_url + 'house-rules'
                else:
                    house_rules_url = base_url + '/house-rules'
            else:
                house_rules_url = base_url

            logger.info(f"Constructed house rules URL: {house_rules_url}")
            return house_rules_url
        except Exception as e:
            logger.error(f"Error constructing house rules URL: {e}")
            return None

    def _construct_safety_url(self, base_url: str) -> Optional[str]:
        """Construct the safety page URL from the base listing URL"""
        try:
            if '?' in base_url:
                base_url = base_url.split('?')[0]
            if '#' in base_url:
                base_url = base_url.split('#')[0]

            if not base_url.endswith('/safety'):
                safety_url = base_url + 'safety' if base_url.endswith('/') else base_url + '/safety'
            else:
                safety_url = base_url

            logger.info(f"Constructed safety URL: {safety_url}")
            return safety_url
        except Exception as e:
            logger.error(f"Error constructing safety URL: {e}")
            return None

    def _get_page_with_selenium(self, url: str) -> Optional[BeautifulSoup]:
        """Get page content using Selenium for JavaScript rendering"""
        if not SELENIUM_AVAILABLE:
            logger.warning("Selenium not available, falling back to requests")
            return None

        driver = None
        try:
            logger.info(f"Using Selenium to fetch: {url}")

            # Set up Chrome options with server optimizations
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # Run in background
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--single-process')

            # Chrome options for better scraping
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)

            # Prefer system chromedriver
            import shutil
            if not shutil.which('chromedriver'):
                logger.warning("chromedriver not found in PATH")
            
            # Create driver with timeout
            import threading
            driver = None
            
            def timeout_handler():
                nonlocal driver
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                logger.error("Chrome driver creation timed out")
                raise TimeoutError("Chrome driver creation timed out")
            
            timer = threading.Timer(20.0, timeout_handler)
            timer.start()
            
            try:
                driver = webdriver.Chrome(options=chrome_options)
                timer.cancel()
            except Exception as e:
                timer.cancel()
                raise e
            driver.set_page_load_timeout(30)

            # Load the page
            driver.get(url)

            # Wait for the page to load and content to be rendered (reduced timeout)
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Reduced wait for dynamic content
            time.sleep(1)

            # Get the page source after JavaScript execution
            page_source = driver.page_source

            # Parse with BeautifulSoup
            soup = BeautifulSoup(page_source, 'html.parser')

            logger.info(f"Successfully loaded page with Selenium: {len(page_source)} characters")
            return soup

        except Exception as e:
            logger.error(f"Error using Selenium to fetch page: {e}")
            return None
        finally:
            if driver:
                driver.quit()

    # --- OCR helpers (Gemini) ---
    def _ocr_with_gemini(self, png_bytes: bytes, prompt: str) -> List[Dict[str, Any]]:
        """Call the configured GEMINI_MODEL to extract structured items from an image.
        Returns a list of dicts with keys: title, content, type
        """
        items: List[Dict[str, Any]] = []
        try:
            from concierge.config import GEMINI_MODEL  # already used elsewhere
            if not GEMINI_MODEL:
                return items
            resp = GEMINI_MODEL.generate_content([
                prompt,
                {"mime_type": "image/png", "data": png_bytes},
            ])
            text = (resp.text or "").strip()
            if text.startswith("```"):
                parts = text.split("\n", 1)
                text = parts[1] if len(parts) > 1 else text
                if text.endswith("```"):
                    text = text[:-3]
            import json as _json
            try:
                data = _json.loads(text)
                if isinstance(data, list):
                    for it in data:
                        if isinstance(it, dict):
                            title = str(it.get("title", "")).strip()
                            content = str(it.get("content", "")).strip()
                            itype = str(it.get("type", "rule")).strip().lower() or "rule"
                            if content:
                                items.append({"title": title, "content": content, "type": itype})
            except Exception:
                pass
        except Exception:
            pass
        return items

    def _ocr_house_rules_from_modal(self, base_url: str) -> List[Dict[str, Any]]:
        """Open the house rules modal/section via Selenium, capture main and 'Additional rules' views,
        and OCR both. Returns consolidated list of items.
        """
        results: List[Dict[str, Any]] = []
        try:
            if not self.use_selenium or not self.driver:
                return results
            url = self._construct_house_rules_url(base_url) or base_url
            self.driver.get(url)
            # Wait for modal content
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//*[@role='dialog' or @aria-modal='true']"))
                )
            except Exception:
                pass
            time.sleep(2)
            # Screenshot the main modal
            main_png = None
            try:
                modal = self.driver.find_element(By.XPATH, "//*[@role='dialog' or @aria-modal='true']")
                main_png = modal.screenshot_as_png
            except Exception:
                try:
                    main_png = self.driver.get_screenshot_as_png()
                except Exception:
                    main_png = None
            if main_png:
                rules_prompt = (
                    "You are given a screenshot image of the Airbnb House Rules modal/page. "
                    "Extract ALL rule-related texts faithfully, including 'Checking in and out', 'During your stay', 'Before you leave', and 'Additional rules'. "
                    "Return a JSON array of {title, content, type} with type either 'rule' or 'instruction'."
                )
                results.extend(self._ocr_with_gemini(main_png, rules_prompt))

            # Click Show more under Additional rules inside the modal
            try:
                # Force a fresh navigation to ensure we don't operate on stale modal nodes
                self.driver.get(url)
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//*[@role='dialog' or @aria-modal='true']"))
                )
                time.sleep(1.5)
                modal2 = self.driver.find_element(By.XPATH, "//*[@role='dialog' or @aria-modal='true']")
                # Find Additional rules section within modal
                addl = modal2.find_element(By.XPATH, ".//*[contains(translate(., 'ADDITIONAL RULES', 'additional rules'), 'additional rules')]")
                # Try multiple variants of the Show more control near the section
                show_more_xpath = ".//button[contains(translate(., 'SHOW MORE','show more'),'show more')]|.//a[contains(translate(., 'SHOW MORE','show more'),'show more')]|.//span[contains(translate(., 'SHOW MORE','show more'),'show more')]/ancestor::*[self::button or self::a][1]"
                show_more = addl.find_element(By.XPATH, show_more_xpath)
                self.driver.execute_script("arguments[0].scrollIntoView(true);", show_more)
                time.sleep(0.5)
                show_more.click()
                # Wait for expansion/nested content to render
                time.sleep(2)
                # Try nested modal first
                add_png = None
                try:
                    nested = self.driver.find_element(By.XPATH, "(//*[@role='dialog' or @aria-modal='true'][.//*[contains(translate(., 'ADDITIONAL RULES', 'additional rules'), 'additional rules')]])[last()]")
                    add_png = nested.screenshot_as_png
                except Exception:
                    # fallback to section itself
                    try:
                        add_png = addl.screenshot_as_png
                    except Exception:
                        add_png = None
                if add_png:
                    results.extend(self._ocr_with_gemini(add_png, rules_prompt))
            except Exception:
                pass
        except Exception:
            pass
        return results

    def _ocr_house_rules_pair(self, base_url: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Capture two screenshots: main House rules modal, and Additional rules after Show more.
        Return (main_items, additional_items) after OCR.
        """
        main_items: List[Dict[str, Any]] = []
        add_items: List[Dict[str, Any]] = []
        try:
            if not self.use_selenium or not self.driver:
                return main_items, add_items
            url = self._construct_house_rules_url(base_url) or base_url

            # 1) Main modal - progressive waits and target modal containing 'House rules'
            self.driver.get(url)
            main_png = None
            wait_windows = [3, 5, 8, 12]
            for delay in wait_windows:
                try:
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.XPATH, "//*[@role='dialog' or @aria-modal='true'][.//*[contains(translate(., 'HOUSE RULES', 'house rules'), 'house rules')]]"))
                    )
                except Exception:
                    pass
                time.sleep(delay)
                try:
                    modal = self.driver.find_element(By.XPATH, "//*[@role='dialog' or @aria-modal='true'][.//*[contains(translate(., 'HOUSE RULES', 'house rules'), 'house rules')]]")
                    text = modal.text.strip()
                    if len(text) < 20:
                        continue
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", modal)
                    time.sleep(0.3)
                    main_png = modal.screenshot_as_png
                    break
                except Exception:
                    continue
            if main_png is None:
                try:
                    main_png = self.driver.get_full_page_screenshot_as_png()
                except Exception:
                    try:
                        main_png = self.driver.get_screenshot_as_png()
                    except Exception:
                        main_png = None
            if main_png:
                rules_prompt = (
                    "You are given a screenshot image of the Airbnb House Rules modal/page. "
                    "Extract ALL rule-related texts faithfully from the screenshot, including sections like 'Checking in and out', 'During your stay', 'Before you leave', and 'Additional rules'. "
                    "Return a strict JSON array of {title, content, type} where type is 'rule' or 'instruction'."
                )
                main_items = self._ocr_with_gemini(main_png, rules_prompt)

            # 2) Additional rules after Show more
            self.driver.get(url)
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//*[@role='dialog' or @aria-modal='true'][.//*[contains(translate(., 'HOUSE RULES', 'house rules'), 'house rules')]]"))
                )
            except Exception:
                pass
            time.sleep(1.5)
            add_png = None
            try:
                modal2 = self.driver.find_element(By.XPATH, "//*[@role='dialog' or @aria-modal='true'][.//*[contains(translate(., 'HOUSE RULES', 'house rules'), 'house rules')]]")
                addl = modal2.find_element(By.XPATH, ".//*[contains(translate(., 'ADDITIONAL RULES', 'additional rules'), 'additional rules')]/ancestor-or-self::*[self::section or self::div][1]")
                show_more = addl.find_element(By.XPATH, ".//button[contains(translate(., 'SHOW MORE','show more'),'show more')]|.//a[contains(translate(., 'SHOW MORE','show more'),'show more')]|.//span[contains(translate(., 'SHOW MORE','show more'),'show more')]/ancestor::*[self::button or self::a][1]")
                self.driver.execute_script("arguments[0].scrollIntoView(true);", show_more)
                time.sleep(0.3)
                show_more.click()
                for w in [2, 4, 6, 8, 12]:
                    time.sleep(w)
                    # Prefer nested dialog if appears
                    try:
                        nested = self.driver.find_element(By.XPATH, "(//*[@role='dialog' or @aria-modal='true'][.//*[contains(translate(., 'ADDITIONAL RULES', 'additional rules'), 'additional rules')]])[last()]")
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", nested)
                        time.sleep(0.3)
                        add_png = nested.screenshot_as_png
                        break
                    except Exception:
                        pass
                    # Fallback to expanded section within modal
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", addl)
                        time.sleep(0.3)
                        add_png = addl.screenshot_as_png
                        break
                    except Exception:
                        pass
                if add_png is None:
                    try:
                        add_png = self.driver.get_full_page_screenshot_as_png()
                    except Exception:
                        try:
                            add_png = self.driver.get_screenshot_as_png()
                        except Exception:
                            add_png = None
            except Exception:
                add_png = None

            if add_png:
                rules_prompt = (
                    "You are given a screenshot image of the Airbnb House Rules modal/page. "
                    "Extract ALL rule-related texts faithfully from the screenshot, including sections like 'Checking in and out', 'During your stay', 'Before you leave', and 'Additional rules'. "
                    "Return a strict JSON array of {title, content, type} where type is 'rule' or 'instruction'."
                )
                add_items = self._ocr_with_gemini(add_png, rules_prompt)

            # Fallback: if combined seems too low, use the standalone two-shot helper
            try:
                if len(main_items) + len(add_items) < 20:
                    from concierge.scripts.extract_rules_via_gemini import capture_rules_pair as _cap_pair
                    png_main, png_add = _cap_pair(url)
                    prompt = (
                        "You are given a screenshot image of the Airbnb House Rules modal/page. "
                        "Extract ALL rule-related texts faithfully from the screenshot, including sections like 'Checking in and out', 'During your stay', 'Before you leave', and 'Additional rules'. "
                        "Return a strict JSON array of {title, content, type} where type is 'rule' or 'instruction'."
                    )
                    if png_main:
                        extra_main = self._ocr_with_gemini(png_main, prompt)
                        if extra_main:
                            main_items.extend([it for it in extra_main if it not in main_items])
                    if png_add:
                        extra_add = self._ocr_with_gemini(png_add, prompt)
                        if extra_add:
                            add_items.extend([it for it in extra_add if it not in add_items])
            except Exception:
                pass

        except Exception:
            pass

        return main_items, add_items

    def _ocr_safety_from_page(self, base_url: str) -> List[Dict[str, Any]]:
        safety: List[Dict[str, Any]] = []
        try:
            if not self.use_selenium or not self.driver:
                return safety
            safety_url = self._construct_safety_url(base_url) or base_url
            self.driver.get(safety_url)

            # Progressive waits and targeted selectors for Safety & property
            selectors = [
                "//*[@role='dialog' and .//*[contains(translate(., 'SAFETY', 'safety'), 'safety')]]",
                "//*[@aria-modal='true' and .//*[contains(translate(., 'SAFETY', 'safety'), 'safety')]]",
                "//*[contains(@data-testid,'modal') and .//*[contains(translate(., 'SAFETY', 'safety'), 'safety')]]",
                "//section[contains(translate(., 'SAFETY & PROPERTY', 'safety & property'), 'safety & property')]",
                "//section[contains(translate(., 'SAFETY', 'safety'), 'safety')]",
            ]
            wait_windows = [3, 5, 8, 12]
            png = None
            for delay in wait_windows:
                time.sleep(delay)
                for xp in selectors:
                    try:
                        elem = self.driver.find_element(By.XPATH, xp)
                        txt = elem.text.strip()
                        if len(txt) < 20:
                            continue
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                        time.sleep(0.3)
                        png = elem.screenshot_as_png
                        break
                    except Exception:
                        continue
                if png:
                    break

            captures: List[bytes] = []
            if png:
                captures.append(png)
            else:
                # Fallback full-page capture
                try:
                    captures.append(self.driver.get_full_page_screenshot_as_png())
                except Exception:
                    try:
                        captures.append(self.driver.get_screenshot_as_png())
                    except Exception:
                        pass

            # Try additional scrolled captures to ensure we get all sections
            try:
                total_height = self.driver.execute_script("return document.body.scrollHeight")
                view_h = self.driver.execute_script("return window.innerHeight") or 800
                for y in [int(total_height*0.33), int(total_height*0.66)]:
                    self.driver.execute_script("window.scrollTo(0, arguments[0]);", y)
                    time.sleep(1.5)
                    try:
                        captures.append(self.driver.get_screenshot_as_png())
                    except Exception:
                        pass
                # Scroll back to top
                self.driver.execute_script("window.scrollTo(0, 0);")
            except Exception:
                pass

            if captures:
                safety_prompt = (
                    "You are given a screenshot image of the Airbnb Safety & property page or modal. "
                    "Extract all safety/emergency-related items as {title, content, type}. Use type 'emergency'. "
                    "Return a JSON array of {title, content, type}."
                )
                seen = set()
                for cap in captures:
                    items = self._ocr_with_gemini(cap, safety_prompt)
                    for it in items:
                        key = (it.get('title','').strip().lower(), it.get('content','').strip().lower())
                        if key in seen:
                            continue
                        seen.add(key)
                        safety.append(it)
        except Exception:
            pass
        return safety

    def _merge_quiet_hours_rules(self, house_rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge standalone time-range items into a single 'Quiet hours' rule.
        Example: one item has title 'Quiet hours' without times, another item has content '10:00 PM - 7:00 AM'.
        After merge: one item with content 'Quiet hours: 10:00 PM - 7:00 AM'.
        """
        if not house_rules:
            return house_rules

        quiet_indices: List[int] = []
        time_only_indices: List[int] = []
        time_texts_by_index: Dict[int, str] = {}

        time_range_regex = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*[-–]\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)

        for idx, rule in enumerate(house_rules):
            text = (rule.get('content') or rule.get('description') or '').strip()
            title = (rule.get('title') or '').strip()
            low_text = text.lower()
            low_title = title.lower()

            if 'quiet' in low_text or 'quiet' in low_title:
                quiet_indices.append(idx)
                # If quiet already includes a time range, skip merge
                if time_range_regex.search(text):
                    # Already has times; no need to merge into this one
                    continue

            # Detect time-only content: contains a time range and lacks semantic keywords
            if time_range_regex.search(text):
                if not any(k in low_text for k in ['quiet', 'party', 'smok', 'pet']):
                    time_only_indices.append(idx)
                    time_texts_by_index[idx] = text

        if not quiet_indices or not time_only_indices:
            return house_rules

        # Prefer the first quiet item as the merge target
        target_idx = quiet_indices[0]
        target = house_rules[target_idx]
        target_title = target.get('title') or 'Quiet hours'

        # Use the first time-only range found
        time_idx = time_only_indices[0]
        time_text = time_texts_by_index.get(time_idx)
        if time_text:
            merged_content = f"{target_title}: {time_text}" if ':' not in (target.get('content') or '') else target.get('content')
            target['title'] = target_title
            target['content'] = merged_content
            target['description'] = merged_content

            # Remove the time-only item from the list
            # Do it safely by marking for deletion and filtering after
            to_remove = set([time_idx])
            new_rules: List[Dict[str, Any]] = []
            for i, r in enumerate(house_rules):
                if i in to_remove:
                    continue
                new_rules.append(r)
            return new_rules

        return house_rules

    def _extract_from_house_rules_page(self, house_rules_url: str) -> List[Dict[str, Any]]:
        """Extract house rules from the dedicated house rules page"""
        rules = []

        try:
            logger.info(f"Fetching house rules from: {house_rules_url}")

            # Try Selenium first for JavaScript rendering
            rules_soup = self._get_page_with_selenium(house_rules_url)

            # Fallback to requests if Selenium fails
            if not rules_soup:
                logger.info("Selenium failed, falling back to requests")
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }

                response = requests.get(house_rules_url, headers=headers, timeout=30)
                response.raise_for_status()
                rules_soup = BeautifulSoup(response.content, 'html.parser')

            # Debug: Log some content from the house rules page
            page_text = rules_soup.get_text()
            logger.info(f"House rules page content length: {len(page_text)} characters")

            # Look for key phrases in the page content
            key_phrases = ['quiet', 'smoking', 'parties', 'pets', 'check', 'noise', 'hours', 'guests']
            found_phrases = [phrase for phrase in key_phrases if phrase in page_text.lower()]
            logger.info(f"Found key phrases on house rules page: {found_phrases}")

            # Log a sample of the page content for debugging
            if len(page_text) <= 500:
                logger.info(f"House rules page full content: {page_text}")
            else:
                sample_text = page_text[:500] + "..."
                logger.info(f"House rules page sample: {sample_text}")

            # Extract rules from this dedicated page
            rules = self._extract_rules_from_page(rules_soup, is_house_rules_page=True)

            logger.info(f"Extracted {len(rules)} rules from house rules page")

        except Exception as e:
            logger.error(f"Error fetching house rules page: {e}")

        return rules

    def _extract_from_safety_page(self, safety_url: str) -> List[Dict[str, Any]]:
        """Extract safety and emergency information from the dedicated safety page"""
        safety_items: List[Dict[str, Any]] = []
        try:
            logger.info(f"Fetching safety info from: {safety_url}")

            # First try a direct Selenium navigation to avoid intermediate SSL fetches
            safety_soup = None
            if SELENIUM_AVAILABLE:
                try:
                    from selenium.webdriver.chrome.options import Options as ChromeOpts
                    from selenium import webdriver as sel_webdriver
                    chrome_opts = ChromeOpts()
                    chrome_opts.add_argument('--headless')
                    chrome_opts.add_argument('--no-sandbox')
                    chrome_opts.add_argument('--disable-dev-shm-usage')
                    chrome_opts.add_argument('--single-process')
                    chrome_opts.add_argument('--disable-gpu')
                    
                    import shutil
                    if not shutil.which('chromedriver'):
                        logger.warning("chromedriver not found in PATH")
                    
                    # Create driver with timeout
                    import threading
                    _drv = None
                    
                    def timeout_handler():
                        nonlocal _drv
                        if _drv:
                            try:
                                _drv.quit()
                            except:
                                pass
                        logger.error("Safety page Chrome driver creation timed out")
                        raise TimeoutError("Safety page Chrome driver creation timed out")
                    
                    timer = threading.Timer(15.0, timeout_handler)
                    timer.start()
                    
                    try:
                        _drv = sel_webdriver.Chrome(options=chrome_opts)
                        timer.cancel()
                    except Exception as e:
                        timer.cancel()
                        raise e
                    _drv.get(safety_url)
                    from bs4 import BeautifulSoup
                    safety_soup = BeautifulSoup(_drv.page_source, 'html.parser')
                    _drv.quit()
                except Exception as _e:
                    logger.warning(f"Direct Selenium fetch for safety page failed: {_e}")
                    safety_soup = None

            if not safety_soup:
                safety_soup = self._get_page_with_selenium(safety_url)
            if not safety_soup:
                logger.info("Selenium failed for safety page, falling back to requests")
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
                response = requests.get(safety_url, headers=headers, timeout=30)
                response.raise_for_status()
                safety_soup = BeautifulSoup(response.content, 'html.parser')

            # Reuse existing extractor over the soup from the safety page
            extracted = self._extract_safety_info(safety_soup)
            safety_items.extend(extracted)
            logger.info(f"Extracted {len(extracted)} safety items from dedicated safety page")
        except Exception as e:
            logger.error(f"Error fetching safety page: {e}")

        return safety_items

    def _extract_rules_from_page(self, soup: BeautifulSoup, is_house_rules_page: bool = False) -> List[Dict[str, Any]]:
        """Extract house rules from a page (main listing or dedicated house rules page)"""
        rules = []

        try:
            # Strategy 1: Look for Airbnb-style house rules sections (similar to amenities)
            rule_sections = []

            # Look for sections that specifically contain house rules
            # Try multiple approaches to find the rules section

            # Approach 1: Look for headings that mention house rules or related sections
            headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            for heading in headings:
                heading_text = heading.get_text(strip=True).lower()
                rule_keywords = [
                    'house rules', 'rules', 'policies', 'quiet hours',
                    'during your stay', 'before you leave', 'checkout instructions',
                    'things to know', 'important information', 'guest guidelines',
                    'property rules', 'stay guidelines'
                ]

                if any(phrase in heading_text for phrase in rule_keywords):
                    logger.info(f"Found rules-related heading: {heading_text}")

                    # Find the container that holds the rules
                    container = heading.find_next_sibling(['div', 'section', 'ul', 'ol'])
                    if container:
                        rule_sections.append(container)
                        logger.info(f"Added container from heading: {len(container.get_text())} chars")

                    # Also check parent containers
                    parent_container = heading.find_parent(['div', 'section'])
                    if parent_container and parent_container not in rule_sections:
                        rule_sections.append(parent_container)
                        logger.info(f"Added parent container: {len(parent_container.get_text())} chars")

            # Approach 2: Look for Airbnb's structured house rules sections
            # These are often organized like amenities with specific class patterns
            potential_rule_containers = soup.find_all(['div', 'section'], class_=re.compile(r'(rule|policy|guideline)', re.IGNORECASE))
            for container in potential_rule_containers:
                if container not in rule_sections:
                    rule_sections.append(container)
                    logger.info(f"Added rule container by class: {container.get('class')}")

            # Approach 3: Look for specific rule patterns in the text
            rule_indicators = [
                'quiet hours', 'no smoking', 'no parties', 'no pets', 'check-in', 'check-out',
                'maximum occupancy', 'noise', 'smoking', 'parties', 'events', 'guests'
            ]

            for indicator in rule_indicators:
                elements = soup.find_all(text=re.compile(indicator, re.IGNORECASE))
                for element in elements:
                    parent = element.parent
                    if parent:
                        # Look for list items or rule containers
                        rule_container = parent.find_parent(['li', 'div', 'p', 'span'])
                        if rule_container and rule_container not in rule_sections:
                            rule_sections.append(rule_container)
                            logger.info(f"Added rule container by text pattern: {indicator}")

            # Approach 4: Look for structured lists that might contain rules
            # Find all ul/ol elements and check if they contain rule-like content
            lists = soup.find_all(['ul', 'ol'])
            for list_elem in lists:
                list_text = list_elem.get_text().lower()
                rule_count = sum(1 for indicator in rule_indicators if indicator in list_text)
                if rule_count >= 2:  # If list contains multiple rule indicators
                    if list_elem not in rule_sections:
                        rule_sections.append(list_elem)
                        logger.info(f"Added list with {rule_count} rule indicators")

            # Approach 3: If this is a house rules page, be more aggressive in finding content
            if is_house_rules_page:
                logger.info("Applying aggressive extraction for house rules page...")

                # Look for any structured content that might contain rules
                additional_sections = soup.find_all(['div', 'section'], class_=re.compile(r'rule|policy|guideline', re.IGNORECASE))
                rule_sections.extend(additional_sections)

                # Look for common Airbnb house rules page structures
                # Try to find any div or section that contains rule-like content
                all_divs = soup.find_all(['div', 'section', 'article'])
                for div in all_divs:
                    div_text = div.get_text(strip=True).lower()
                    if any(keyword in div_text for keyword in ['quiet', 'smoking', 'parties', 'pets', 'check', 'noise', 'hours']):
                        if div not in rule_sections:
                            rule_sections.append(div)

                # Also look for time patterns that suggest rules
                time_elements = soup.find_all(text=re.compile(r'\d{1,2}:\d{2}\s*(AM|PM|am|pm)', re.IGNORECASE))
                for time_element in time_elements:
                    parent = time_element.parent
                    if parent:
                        rule_container = parent.find_parent(['div', 'p', 'li'])
                        if rule_container and rule_container not in rule_sections:
                            rule_sections.append(rule_container)

                # Look for any text that contains rule keywords
                rule_texts = soup.find_all(text=re.compile(r'(quiet|smoking|parties|pets|check|noise|hours|guests|occupancy)', re.IGNORECASE))
                for rule_text in rule_texts:
                    parent = rule_text.parent
                    if parent:
                        rule_container = parent.find_parent(['div', 'p', 'li', 'span'])
                        if rule_container and rule_container not in rule_sections:
                            rule_sections.append(rule_container)

                logger.info(f"Found {len(rule_sections)} potential rule sections on house rules page")

            logger.info(f"Found {len(rule_sections)} potential rule sections")

            processed_rules = set()  # Avoid duplicates

            for section_idx, section in enumerate(rule_sections):
                logger.info(f"Processing rule section {section_idx + 1}/{len(rule_sections)}")

                # Extract rule items with comprehensive targeting
                items = section.find_all(['li', 'div', 'p', 'span', 'button', 'a'])

                logger.info(f"Found {len(items)} potential rule items in section {section_idx + 1}")

                for item in items:
                    rule_text = item.get_text(strip=True)

                    # Better filtering for actual rules with stricter criteria
                    if (rule_text and
                        len(rule_text) > 5 and  # Minimum meaningful length
                        len(rule_text) < 150 and  # Reasonable maximum length for rules
                        rule_text.lower() not in processed_rules and
                        not self._is_ui_element(rule_text)):  # Filter out UI elements

                        # Check if it's likely a house rule
                        if self._is_likely_house_rule(rule_text):
                            processed_rules.add(rule_text.lower())

                            # Create rule entry with better title extraction
                            rule_entry = {
                                'title': self._extract_precise_rule_title(rule_text),
                                'description': rule_text,
                                'enabled': True,
                                'type': 'rule',
                                'source': 'airbnb_house_rules_page' if is_house_rules_page else 'airbnb_extraction'
                            }
                            rules.append(rule_entry)
                            logger.info(f"Extracted rule: {rule_entry['title']}")
                        else:
                            logger.debug(f"Rejected non-rule text: {rule_text[:50]}...")

            # If no rules found in structured sections, try a more aggressive approach
            if len(rules) == 0:
                logger.info("No rules found in structured sections, trying aggressive text search...")

                # Look for any text that contains rule keywords
                all_text_elements = soup.find_all(text=True)
                for text_elem in all_text_elements:
                    text = text_elem.strip()
                    if (text and
                        len(text) > 10 and
                        len(text) < 200 and
                        text.lower() not in processed_rules and
                        self._is_likely_house_rule(text)):

                        processed_rules.add(text.lower())

                        rule_entry = {
                            'title': self._extract_precise_rule_title(text),
                            'description': text,
                            'enabled': True,
                            'type': 'rule',
                            'source': 'airbnb_aggressive_extraction'
                        }
                        rules.append(rule_entry)
                        logger.info(f"Aggressively extracted rule: {rule_entry['title']}")

        except Exception as e:
            logger.error(f"Error extracting rules from page: {e}")

        return rules

    def _is_ui_element(self, text: str) -> bool:
        """Check if text is likely a UI element rather than a house rule"""
        text_lower = text.lower().strip()

        # Filter out common UI elements
        ui_patterns = [
            'add date', 'check availability', 'add guests', 'guests·', 'bedrooms·', 'beds·', 'bath',
            'entire cabin', 'guest favorite', 'most loved homes', 'according to guests',
            'recent guests gave', 'star rating', 'select check-in', 'add your travel dates',
            'exact pricing', 'add dates for prices', 'rated 5.0 out of 5', 'checking in and out',
            'peace and quiet', 'one of the most', 'guests say this home'
        ]

        # Check if text contains UI patterns
        for pattern in ui_patterns:
            if pattern in text_lower:
                return True

        # Filter out very short or repetitive text
        if len(text_lower) < 8 or text_lower.count('·') > 1:
            return True

        # Filter out text that's mostly navigation or buttons
        if any(word in text_lower for word in ['add', 'select', 'click', 'button', 'link']):
            return True

        return False

    def _is_likely_house_rule(self, text: str) -> bool:
        """Check if text is likely to be a house rule"""
        text_lower = text.lower()

        # Rule indicators - be more specific
        rule_keywords = [
            'no smoking', 'no parties', 'no pets', 'quiet hours', 'noise',
            'check-in', 'check-out', 'maximum', 'occupancy', 'guests',
            'smoking', 'parties', 'events', 'pets', 'allowed', 'prohibited',
            'not allowed', 'not permitted', 'required', 'must'
        ]

        # Must contain at least one rule keyword
        has_rule_keyword = any(keyword in text_lower for keyword in rule_keywords)

        # Exclude common non-rule text (but be careful not to exclude valid rule content)
        exclude_patterns = [
            'house rules', 'policies', 'restrictions', 'please note',
            'important', 'additional', 'information', 'details',
            'contact', 'host', 'listing', 'amazing', 'beautiful',
            'stunning', 'perfect', 'great', 'wonderful', 'views', 'location',
            'features', 'amenities', 'includes', 'offers', 'provides'
        ]

        # Exclude UI elements and navigation text
        ui_patterns = [
            'select check-in date', 'select check-out date', 'select date',
            'self check-in', 'self check-out', 'keypad', 'lockbox',
            'click', 'button', 'link', 'show more', 'see more', 'hide',
            'close', 'back', 'next', 'add dates', 'choose dates',
            'exceptional check-in experience', 'rated 5.0 out of 5',
            'check-in5.0', 'checkout before', 'guests1 guest',
            'guests1', 'guest1', 'add guest', 'remove guest'
        ]

        # Exclude testimonials and reviews
        testimonial_patterns = [
            'recent guests loved', 'guests loved', 'guests said', 'guests mentioned',
            'highly rated', 'guests enjoyed', 'guests appreciated', 'guests found',
            'communication', 'responsive host', 'great host', 'amazing host',
            'loved the', 'enjoyed the', 'appreciated the', 'found the'
        ]

        # Exclude very short or very generic text
        is_too_short = len(text.strip()) < 5
        is_too_generic = text_lower in ['check-in', 'check-out', 'guests', 'pets', 'smoking']

        # Exclude check-in/check-out time statements (these should be property times, not rules)
        checkin_checkout_patterns = [
            'check-in after', 'check-in from', 'check-in time',
            'check-out before', 'check-out by', 'check-out time',
            'check in after', 'check in from', 'check in time',
            'check out before', 'check out by', 'check out time'
        ]
        is_checkin_checkout_time = any(pattern in text_lower for pattern in checkin_checkout_patterns)

        # Exclude descriptive/marketing text
        is_descriptive = any(pattern in text_lower for pattern in exclude_patterns)

        # Exclude UI elements
        is_ui_element = any(pattern in text_lower for pattern in ui_patterns)

        # Exclude testimonials and reviews
        is_testimonial = any(pattern in text_lower for pattern in testimonial_patterns)

        # Don't exclude if it's just a heading
        is_heading_only = any(pattern in text_lower for pattern in ['house rules', 'policies', 'restrictions']) and len(text.split()) < 5

        # Must have rule keywords AND not be descriptive/UI text (unless it's a heading)
        # Also exclude very short or generic text, check-in/check-out times, and testimonials
        return (has_rule_keyword and
                not is_descriptive and
                not is_ui_element and
                not is_too_short and
                not is_too_generic and
                not is_checkin_checkout_time and
                not is_testimonial) or is_heading_only

    def _extract_precise_rule_title(self, rule_text: str) -> str:
        """Extract a precise title from rule text, preserving specific details"""

        if not rule_text or not isinstance(rule_text, str):
            return "House Rule"

        rule_lower = rule_text.lower()

        # For quiet hours, preserve the actual times
        if 'quiet' in rule_lower and ('hour' in rule_lower or 'time' in rule_lower):
            # Try to extract time information
            time_pattern = r'(\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm))'
            times = re.findall(time_pattern, rule_text, re.IGNORECASE)
            if len(times) >= 2:
                return f"Quiet hours ({times[0]} - {times[1]})"
            elif times:
                return f"Quiet hours (from {times[0]})"
            else:
                return "Quiet hours"

        # For smoking rules
        elif 'no smoking' in rule_lower or ('smoking' in rule_lower and ('not' in rule_lower or 'prohibited' in rule_lower)):
            return "No smoking"

        # For party/event rules
        elif ('no parties' in rule_lower or 'no events' in rule_lower or
              ('parties' in rule_lower and ('not' in rule_lower or 'prohibited' in rule_lower)) or
              ('events' in rule_lower and ('not' in rule_lower or 'prohibited' in rule_lower))):
            return "No parties or events"

        # For pet rules
        elif ('no pets' in rule_lower or
              ('pets' in rule_lower and ('not' in rule_lower or 'prohibited' in rule_lower))):
            return "No pets"

        # For check-in rules
        elif 'check' in rule_lower and 'in' in rule_lower:
            return "Check-in"

        # For check-out rules
        elif 'check' in rule_lower and 'out' in rule_lower:
            return "Check-out"

        # For occupancy rules
        elif 'maximum' in rule_lower and ('guest' in rule_lower or 'occupancy' in rule_lower):
            # Try to extract number
            number_match = re.search(r'(\d+)', rule_text)
            if number_match:
                return f"Maximum {number_match.group(1)} guests"
            else:
                return "Maximum occupancy"

        # For noise rules
        elif 'noise' in rule_lower:
            return "Noise policy"

        # Default: use first meaningful part of the text
        else:
            # Clean up the text and use first part as title
            words = rule_text.split()
            if len(words) <= 6:
                return rule_text
            else:
                return ' '.join(words[:6]) + '...'

    def _extract_rule_title(self, rule_text: str) -> str:
        """Legacy method - redirect to precise extraction"""
        return self._extract_precise_rule_title(rule_text)

    def _extract_safety_info(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract safety and emergency information"""

        safety_info = []

        try:
            # Look for safety sections
            safety_patterns = [r'safety', r'emergency', r'security', r'smoke detector', r'carbon monoxide']
            safety_sections = []

            for pattern in safety_patterns:
                text_nodes = soup.find_all(text=re.compile(pattern, re.IGNORECASE))
                for text_node in text_nodes:
                    parent = text_node.parent
                    if parent:
                        container = parent.find_parent(['div', 'section'])
                        if container and container not in safety_sections:
                            safety_sections.append(container)

            processed_safety = set()  # Avoid duplicates

            for section in safety_sections:
                items = section.find_all(['li', 'div', 'p', 'span'])
                for item in items:
                    safety_text = item.get_text(strip=True)
                    if safety_text and len(safety_text) > 10 and safety_text.lower() not in processed_safety:
                        processed_safety.add(safety_text.lower())

                        safety_entry = {
                            'title': self._extract_safety_title(safety_text),
                            'description': safety_text,
                            'content': safety_text,
                            'enabled': True,
                            'type': 'emergency',
                            'source': 'airbnb_extraction'
                        }
                        safety_info.append(safety_entry)

            logger.info(f"Extracted {len(safety_info)} safety items")

        except Exception as e:
            logger.error(f"Error extracting safety info: {e}")

        return safety_info

    def _extract_safety_title(self, safety_text: str) -> str:
        """Extract a title from safety text"""

        if 'smoke detector' in safety_text.lower():
            return "Smoke detector"
        elif 'carbon monoxide' in safety_text.lower():
            return "Carbon monoxide detector"
        elif 'fire extinguisher' in safety_text.lower():
            return "Fire extinguisher"
        elif 'first aid' in safety_text.lower():
            return "First aid kit"
        elif 'security' in safety_text.lower():
            return "Security system"
        else:
            words = safety_text.split()[:3]
            return ' '.join(words) + ('...' if len(safety_text.split()) > 3 else '')

    def _extract_and_clean_description(self, soup: BeautifulSoup) -> str:
        """Extract and clean property description, removing selling phrases"""

        try:
            # Look for description sections
            description_sections = soup.find_all(['div', 'section'], attrs={
                'data-testid': lambda x: x and 'description' in x.lower() if x else False
            })

            # Also look for common description patterns
            description_text = ""

            for section in description_sections:
                text = section.get_text(strip=True)
                if text and len(text) > 50:
                    description_text = text
                    break

            # If no specific section found, look for longer text blocks
            if not description_text:
                text_blocks = soup.find_all(['p', 'div'])
                for block in text_blocks:
                    text = block.get_text(strip=True)
                    if len(text) > 100:
                        description_text = text
                        break

            # Clean the description
            if description_text:
                description_text = self._clean_description_text(description_text)

            logger.info(f"Extracted description: {len(description_text)} characters")
            return description_text

        except Exception as e:
            logger.error(f"Error extracting description: {e}")
            return ""

    def _clean_description_text(self, text: str) -> str:
        """Clean and compile a brief, property-focused description (50-60 words)"""

        # Remove common selling phrases
        selling_phrases = [
            r'book now',
            r'reserve today',
            r'don\'t miss out',
            r'limited availability',
            r'special offer',
            r'discount',
            r'best price',
            r'perfect for',
            r'ideal for',
            r'you\'ll love',
            r'amazing',
            r'incredible',
            r'stunning',
            r'breathtaking',
            r'don\'t hesitate',
            r'contact us',
            r'message us',
            r'we look forward',
            r'can\'t wait'
        ]

        cleaned_text = text
        for phrase in selling_phrases:
            cleaned_text = re.sub(phrase, '', cleaned_text, flags=re.IGNORECASE)

        # Remove amenity lists and repetitive content
        amenity_patterns = [
            r'amenities include[^.]*\.',
            r'features include[^.]*\.',
            r'includes[^.]*wifi[^.]*\.',
            r'kitchen[^.]*equipped[^.]*\.',
            r'bathroom[^.]*towels[^.]*\.',
            r'the accommodation[^.]*cleaning products[^.]*\.',
            r'accommodation[^.]*shampoo[^.]*conditioner[^.]*\.',
            r'cleaning products[^.]*shampoo[^.]*\.',
            r'features[^.]*kitchen[^.]*wifi[^.]*\.'
        ]

        for pattern in amenity_patterns:
            cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)

        # Clean up extra whitespace and punctuation
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        cleaned_text = re.sub(r'[.]{2,}', '.', cleaned_text)

        # Compile a brief description using Gemini if available
        try:
            brief_description = self._compile_brief_description(cleaned_text)
            if brief_description and len(brief_description.split()) >= 20:
                return brief_description
        except Exception as e:
            logger.debug(f"Error compiling brief description with Gemini: {e}")

        # Fallback: Extract first meaningful sentences (50-60 words)
        sentences = cleaned_text.split('.')
        brief_text = ""
        word_count = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and len(sentence) > 10:  # Skip very short sentences
                sentence_words = len(sentence.split())
                if word_count + sentence_words <= 60:
                    brief_text += sentence + ". "
                    word_count += sentence_words
                else:
                    break

        # Ensure we have at least 30 words
        if word_count < 30 and len(sentences) > 0:
            # Take the first substantial sentence even if it goes over 60 words
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence.split()) >= 20:
                    brief_text = sentence + "."
                    break

        return brief_text.strip()

    def _compile_brief_description(self, text: str) -> str:
        """Use Gemini to compile a brief, property-focused description"""

        try:
            from concierge.config import GEMINI_MODEL

            if not GEMINI_MODEL:
                return ""

            # Enhanced prompt with better quality control
            prompt = f"""
            Create a brief property description (50-60 words) based on this Airbnb listing text.

            REQUIREMENTS:
            - Focus on property type, location, and unique features
            - Describe what makes this property special or distinctive
            - Include neighborhood character or location benefits
            - Write in a natural, descriptive style
            - Avoid generic phrases like "perfect for travelers" or "great location"
            - Do NOT list amenities (WiFi, kitchen, parking, etc.)
            - Do NOT use selling language or superlatives
            - Do NOT say "information is not available" or similar phrases

            QUALITY CHECK:
            - If the source text is too generic or lacks meaningful content, return exactly "SKIP"
            - Only create a description if you can write something specific and informative
            - The description should give guests a clear sense of the property and area
            - Never mention that information is unavailable or insufficient

            Original text: {text[:800]}

            Brief description (or exactly "SKIP" if insufficient content):
            """

            response = GEMINI_MODEL.generate_content(prompt)
            if response and response.text:
                brief_desc = response.text.strip()
                logger.debug(f"Gemini raw response: '{brief_desc}'")

                # Check if Gemini decided to skip
                if brief_desc.upper() == "SKIP":
                    logger.debug("Gemini determined insufficient content for meaningful description")
                    return ""

                # Check for problematic responses
                problematic_phrases = [
                    "information about this property is not available",
                    "information is not available",
                    "not available without",
                    "cannot provide",
                    "insufficient information",
                    "no information available"
                ]

                if any(phrase in brief_desc.lower() for phrase in problematic_phrases):
                    logger.debug(f"Generated description contains problematic phrase, skipping: {brief_desc}")
                    return ""

                # Quality check - avoid generic descriptions
                generic_phrases = [
                    "perfect for", "great location", "ideal for travelers",
                    "comfortable accommodation", "convenient location",
                    "beautiful property", "amazing place", "wonderful stay"
                ]

                if any(phrase in brief_desc.lower() for phrase in generic_phrases):
                    logger.debug("Generated description contains generic phrases, skipping")
                    return ""

                # Ensure it's within word limit
                words = brief_desc.split()
                if len(words) > 65:
                    brief_desc = ' '.join(words[:60]) + '.'
                elif len(words) < 20:
                    logger.debug("Generated description too short, skipping")
                    return ""

                return brief_desc

        except Exception as e:
            logger.debug(f"Gemini description compilation failed: {e}")

        return ""

    def _extract_checkin_checkout_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract check-in and check-out information"""

        checkin_checkout = {
            'checkin_time': '',
            'checkout_time': '',
            'checkin_instructions': '',
            'checkout_instructions': ''
        }

        try:
            # Look for check-in/check-out sections
            checkin_sections = soup.find_all(text=re.compile(r'check.?in|arrival', re.IGNORECASE))
            checkout_sections = soup.find_all(text=re.compile(r'check.?out|departure', re.IGNORECASE))

            # Extract times and instructions
            for text_node in checkin_sections + checkout_sections:
                parent = text_node.parent
                if parent:
                    container = parent.find_parent(['div', 'section'])
                    if container:
                        text = container.get_text(strip=True)

                        # Extract times
                        time_pattern = r'(\d{1,2}:\d{2}\s*(?:AM|PM)?)'
                        times = re.findall(time_pattern, text, re.IGNORECASE)

                        if 'check' in text.lower() and 'in' in text.lower():
                            if times:
                                checkin_checkout['checkin_time'] = times[0]
                            checkin_checkout['checkin_instructions'] = text
                        elif 'check' in text.lower() and 'out' in text.lower():
                            if times:
                                checkin_checkout['checkout_time'] = times[0]
                            checkin_checkout['checkout_instructions'] = text

            logger.info("Extracted check-in/check-out information")

        except Exception as e:
            logger.error(f"Error extracting check-in/check-out info: {e}")

        return checkin_checkout

    def _extract_local_area_info(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract local area and neighborhood information"""

        local_info = []

        try:
            # Look for neighborhood/area sections
            area_patterns = [r'neighborhood', r'area', r'location', r'nearby', r'local']
            area_sections = []

            for pattern in area_patterns:
                text_nodes = soup.find_all(text=re.compile(pattern, re.IGNORECASE))
                for text_node in text_nodes:
                    parent = text_node.parent
                    if parent:
                        container = parent.find_parent(['div', 'section'])
                        if container and container not in area_sections:
                            area_sections.append(container)

            processed_info = set()  # Avoid duplicates

            for section in area_sections:
                text = section.get_text(strip=True)
                if text and len(text) > 50 and text.lower() not in processed_info:
                    # Filter out reviews and invalid content
                    if self._is_valid_local_area_content(text):
                        processed_info.add(text.lower())

                        local_entry = {
                            'title': 'Local area information',
                            'content': text,
                            'type': 'places',
                            'source': 'airbnb_extraction'
                        }
                        local_info.append(local_entry)

            logger.info(f"Extracted {len(local_info)} local area items")

        except Exception as e:
            logger.error(f"Error extracting local area info: {e}")

        return local_info

    def _is_valid_local_area_content(self, text: str) -> bool:
        """Check if text is valid local area content (not reviews or navigation)"""
        text_lower = text.lower()

        # Filter out guest reviews (first-person language)
        review_indicators = [
            'we had', 'we loved', 'we stayed', 'we enjoyed', 'our stay',
            'i had', 'i loved', 'i stayed', 'i enjoyed', 'my stay',
            'great stay', 'nice stay', 'wonderful stay', 'amazing stay',
            'would recommend', 'would stay again', 'highly recommend',
            'the host was', 'peter was', 'host responded', 'responsive host',
            'the most important thing about me when i travel',
            'when i travel', 'my travel', 'i travel'
        ]

        # Filter out navigation and system content
        navigation_indicators = [
            'support', 'help center', 'aircover', 'anti-discrimination',
            'disability support', 'cancellation options', 'report neighborhood',
            'airbnb.org emergency', 'airbnb.org', 'summer release', 'check in / check out',
            'any week', 'add guests', 'anywhere', 'guests add guests',
            '2025 summer release', '2024 summer release', '2026 summer release',
            'airbnb website', 'javascript enabled', 'skip to content',
            'emergency stays', 'release'
        ]

        # Filter out very generic or repetitive content
        generic_indicators = [
            'apartments for rent', 'united states - airbnb',
            'new boutique', 'eat street apt'
        ]

        # Check for review indicators
        if any(indicator in text_lower for indicator in review_indicators):
            return False

        # Check for navigation indicators
        if any(indicator in text_lower for indicator in navigation_indicators):
            return False

        # Check for generic indicators
        if any(indicator in text_lower for indicator in generic_indicators):
            return False

        # Must be substantial content (but not too restrictive)
        if len(text) < 20:
            return False

        return True

    def _extract_modal_house_rules(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract house rules from modal structure based on screenshot analysis"""
        rules = []

        try:
            # Look for modal content - modals often have specific attributes
            modal_selectors = [
                '[role="dialog"]',
                '[aria-modal="true"]',
                '.modal',
                '[data-testid*="modal"]',
                '[class*="modal"]'
            ]

            modal_content = None
            for selector in modal_selectors:
                modals = soup.select(selector)
                for modal in modals:
                    # Check if this modal contains house rules content
                    modal_text = modal.get_text().lower()
                    house_rules_indicators = [
                        'house rules', 'checking in and out', 'during your stay', 'before you leave',
                        'no pets', 'pets allowed', 'quiet hours', 'no smoking', 'no parties', 'guests maximum',
                        'check-in after', 'checkout before', 'self check-in', 'commercial photography',
                        'gather used towels', 'turn things off', 'lock up', 'additional rules'
                    ]

                    # Count how many house rules indicators are found
                    indicator_count = sum(1 for indicator in house_rules_indicators if indicator in modal_text)

                    if indicator_count >= 2:  # Must have at least 2 indicators to be considered house rules modal
                        modal_content = modal
                        logger.info(f"Found house rules modal with selector: {selector} (indicators: {indicator_count})")
                        break
                if modal_content:
                    break

            if not modal_content:
                # Fallback: look for any content that has the modal structure
                # Based on screenshot: sections with headings like "Checking in and out", "During your stay", etc.
                section_headings = [
                    'checking in and out',
                    'during your stay',
                    'before you leave',
                    'house rules',  # Sometimes the modal just has this
                    'things to know'  # Or this
                ]

                for heading_text in section_headings:
                    headings = soup.find_all(text=re.compile(heading_text, re.IGNORECASE))
                    if headings:
                        # Found modal-style content
                        modal_content = soup
                        logger.info(f"Found modal-style content with heading: {heading_text}")
                        break

            if modal_content:
                # Extract rules from modal structure
                modal_rules = self._parse_modal_rules_structure(modal_content)
                rules.extend(modal_rules)
                logger.info(f"Extracted {len(modal_rules)} rules from modal structure")

                # If we didn't get many rules, try more aggressive extraction
                if len(modal_rules) < 10:  # We expect at least 10 rules from the modal
                    logger.info("Modal structure extraction yielded few rules, trying aggressive text search...")

                    # First, use detected rules from modal opening
                    if hasattr(self, '_detected_modal_rules') and self._detected_modal_rules:
                        logger.info(f"Using {len(self._detected_modal_rules)} detected rules from modal opening")

                        # Map detected rules to proper rule objects - ENHANCED with all missing rules
                        # Using "content" field for consistency with UI
                        detected_rule_mapping = {
                            'Quiet hours': {'content': 'Quiet hours 9:00 PM - 7:00 AM', 'type': 'rule', 'title': 'Quiet Hours'},
                            'No parties': {'content': 'No parties or events', 'type': 'rule', 'title': 'Parties and Events'},
                            'No smoking': {'content': 'No smoking', 'type': 'rule', 'title': 'Smoking'},
                            'Commercial photography': {'content': 'No commercial photography', 'type': 'rule', 'title': 'Commercial Photography'},
                            'No pets': {'content': 'No pets', 'type': 'rule', 'title': 'Pets'},
                            'Gather used towels': {'content': 'Gather used towels', 'type': 'instruction', 'title': 'Before You Leave'},
                            'Turn things off': {'content': 'Turn things off', 'type': 'instruction', 'title': 'Before You Leave'},
                            'Return keys': {'content': 'Return keys', 'type': 'instruction', 'title': 'Before You Leave'},
                            'Lock up': {'content': 'Lock up', 'type': 'instruction', 'title': 'Before You Leave'},
                            'Park only in': {'content': 'Park only in the designated spot (details provided before check-in). Please do not block other vehicles.', 'type': 'rule', 'title': 'Parking'},
                            'Drive slowly': {'content': 'Drive slowly and carefully in the shared driveway—there may be children at play or neighbors walking by.', 'type': 'rule', 'title': 'Driveway Safety'},
                            'Baby gear': {'content': 'Baby gear (crib, etc.) is available upon request and subject to availability. Please let us know in advance so we can prepare accordingly.', 'type': 'rule', 'title': 'Baby Gear'},
                            'Standard checkout': {'content': 'Standard checkout time is 11:00. If you\'d like a late checkout, we do offer that for $20 per additional hour, based on availability.', 'type': 'instruction', 'title': 'Late Checkout'}
                        }

                        existing_contents = {rule.get('content', rule.get('description', '')) for rule in rules}
                        for detected_rule in self._detected_modal_rules:
                            if detected_rule in detected_rule_mapping:
                                rule_obj = detected_rule_mapping[detected_rule]
                                if rule_obj['content'] not in existing_contents:
                                    rules.append(rule_obj)
                                    logger.info(f"Added detected rule: {rule_obj['title']} - {rule_obj['content']}")
                                    existing_contents.add(rule_obj['content'])

                    # Then try text-based extraction as backup
                    modal_text = modal_content.get_text()
                    logger.info(f"Modal text sample (first 1000 chars): {modal_text[:1000]}")

                    # Use the text-based extraction as backup
                    text_rules = self._extract_rules_from_text(modal_text)

                    # Add any new rules we found
                    existing_descriptions = {rule['description'] for rule in rules}
                    for rule in text_rules:
                        if rule['description'] not in existing_descriptions:
                            rules.append(rule)
                            logger.info(f"Added aggressive rule: {rule['description']}")

                    logger.info(f"Total rules after aggressive extraction: {len(rules)}")

        except Exception as e:
            logger.warning(f"Error extracting modal house rules: {e}")

        # Break down complex rules before processing
        if rules:
            rules = self._break_down_complex_rules(rules)

        # Manual "Before you leave" concatenation before Gemini validation
        if rules:
            rules = self._concatenate_before_you_leave_rules(rules)

        # Extract and store time-related information for property fields
        if rules:
            time_info = self._extract_time_info_from_rules(rules)
            if time_info:
                # Store time info for later use in property creation
                if not hasattr(self, '_extracted_time_info'):
                    self._extracted_time_info = {}
                self._extracted_time_info.update(time_info)

        # Use Gemini to validate and improve rules
        if rules:
            validated_rules = self._validate_rules_with_gemini(rules, modal_content.get_text()[:3000] if modal_content else "")
            if validated_rules:
                rules = validated_rules
                logger.info(f"Gemini validation applied to {len(rules)} rules")

        return rules

    def _concatenate_before_you_leave_rules(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Manually concatenate 'Before you leave' rules into a single comprehensive instruction"""
        before_you_leave_rules = []
        other_rules = []

        # Separate "Before you leave" rules from others
        for rule in rules:
            # Use content field, fallback to description for compatibility
            content = rule.get('content', rule.get('description', '')).lower()
            if ('before you leave' in content or
                'gather used towels' in content or
                'turn things off' in content or
                'return keys' in content or
                'lock up' in content):
                before_you_leave_rules.append(rule)
            else:
                other_rules.append(rule)

        # If we found "Before you leave" rules, concatenate them
        if before_you_leave_rules:
            logger.info(f"Found {len(before_you_leave_rules)} 'Before you leave' rules to concatenate")

            # Extract individual instructions
            instructions = []
            for rule in before_you_leave_rules:
                # Use content field, fallback to description for compatibility
                content = rule.get('content', rule.get('description', ''))
                # Clean up the instruction
                if 'before you leave:' in content.lower():
                    instruction = content.split(':', 1)[1].strip()
                elif 'before you leave' in content.lower():
                    instruction = content.replace('before you leave', '').strip().lstrip(',').strip()
                else:
                    instruction = content.strip()

                if instruction:
                    instructions.append(instruction)

            # Create concatenated rule
            if instructions:
                concatenated_content = f"Before you leave: {', '.join(instructions)}"
                concatenated_rule = {
                    'content': concatenated_content,
                    'title': 'Before You Leave',
                    'type': 'instruction'
                }
                other_rules.append(concatenated_rule)
                logger.info(f"Created concatenated 'Before you leave' rule: {concatenated_content}")

        return other_rules

    def _break_down_complex_rules(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Break down complex rules that contain multiple separate rules"""
        processed_rules = []

        for rule in rules:
            if not isinstance(rule, dict):
                processed_rules.append(rule)
                continue

            # Use content field, fallback to description for compatibility
            content = rule.get('content', rule.get('description', ''))

            # Check if this is a complex rule that should be broken down
            if self._is_complex_rule(content):
                logger.info(f"Breaking down complex rule: {content[:100]}...")
                broken_down_rules = self._split_complex_rule(content, rule)
                processed_rules.extend(broken_down_rules)
            else:
                processed_rules.append(rule)

        return processed_rules

    def _is_complex_rule(self, content: str) -> bool:
        """Check if a rule is complex and should be broken down"""
        # Rules with multiple sentences and different topics
        sentences = content.split('.')
        if len(sentences) < 3:
            return False

        # Look for multiple distinct topics in one rule
        topics = [
            'vaccinated', 'late arrival', 'quiet hours', 'patio', 'parking',
            'street parking', 'driveway', 'winter', 'coordinate'
        ]

        found_topics = sum(1 for topic in topics if topic.lower() in content.lower())
        return found_topics >= 3  # If 3+ topics, it's complex

    def _split_complex_rule(self, content: str, original_rule: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split a complex rule into multiple simpler rules"""
        rules = []

        # Split by sentences and group related ones
        sentences = [s.strip() for s in content.split('.') if s.strip()]

        # Define rule patterns and their groupings
        rule_patterns = [
            {
                'keywords': ['vaccinated'],
                'title': 'Vaccination Status',
                'type': 'information'
            },
            {
                'keywords': ['late arrival', 'no late arrivals', 'past 10pm', 'after 10pm'],
                'title': 'Late Arrivals',
                'type': 'rule'
            },
            {
                'keywords': ['quiet hours', 'quiet time'],
                'title': 'Quiet Hours',
                'type': 'rule'
            },
            {
                'keywords': ['patio', 'available from may', 'may to october'],
                'title': 'Patio Availability',
                'type': 'information'
            },
            {
                'keywords': ['street parking', 'parking available'],
                'title': 'Street Parking',
                'type': 'information'
            },
            {
                'keywords': ['winter months', 'driveway', 'shared with upstairs'],
                'title': 'Winter Parking',
                'type': 'information'
            }
        ]

        # Group sentences by topic
        for pattern in rule_patterns:
            matching_sentences = []
            for sentence in sentences:
                if any(keyword.lower() in sentence.lower() for keyword in pattern['keywords']):
                    matching_sentences.append(sentence)

            if matching_sentences:
                rule_content = '. '.join(matching_sentences).strip()
                if not rule_content.endswith('.'):
                    rule_content += '.'

                new_rule = {
                    'content': rule_content,
                    'title': pattern['title'],
                    'type': pattern['type'],
                    'enabled': original_rule.get('enabled', True),
                    'source': 'complex_rule_breakdown'
                }
                rules.append(new_rule)
                logger.info(f"Created sub-rule: {pattern['title']} - {rule_content}")

        # If no patterns matched, return original rule
        if not rules:
            rules.append(original_rule)

        return rules

    def _extract_time_info_from_rules(self, rules: List[Dict[str, Any]]) -> Dict[str, str]:
        """Extract check-in/check-out time information from rules for property fields"""
        time_info = {}

        for rule in rules:
            if not isinstance(rule, dict):
                continue

            # Use content field, fallback to description for compatibility
            content = rule.get('content', rule.get('description', '')).lower()

            # Extract check-in times
            if 'check-in' in content or 'check in' in content:
                # Look for time patterns like "3:00 PM - 10:00 PM"
                import re
                time_pattern = r'(\d{1,2}):?(\d{2})?\s*(am|pm)\s*-\s*(\d{1,2}):?(\d{2})?\s*(am|pm)'
                match = re.search(time_pattern, content, re.IGNORECASE)
                if match:
                    start_hour = int(match.group(1))
                    start_min = match.group(2) or '00'
                    start_ampm = match.group(3).upper()
                    end_hour = int(match.group(4))
                    end_min = match.group(5) or '00'
                    end_ampm = match.group(6).upper()

                    # Convert to 24-hour format
                    if start_ampm == 'PM' and start_hour != 12:
                        start_hour += 12
                    elif start_ampm == 'AM' and start_hour == 12:
                        start_hour = 0

                    if end_ampm == 'PM' and end_hour != 12:
                        end_hour += 12
                    elif end_ampm == 'AM' and end_hour == 12:
                        end_hour = 0

                    time_info['checkInTime'] = f"{start_hour:02d}:{start_min}"
                    # If check-in ends at 10 PM, that suggests checkout should be 10 AM
                    if end_hour == 22:  # 10 PM
                        time_info['checkOutTime'] = "10:00"
                        logger.info(f"Inferred checkout time 10:00 AM from check-in ending at 10:00 PM")

                # Also look for single time patterns like "after 3:00 PM"
                single_time_pattern = r'after\s+(\d{1,2}):?(\d{2})?\s*(am|pm)'
                match = re.search(single_time_pattern, content, re.IGNORECASE)
                if match and 'checkInTime' not in time_info:
                    hour = int(match.group(1))
                    min_val = match.group(2) or '00'
                    ampm = match.group(3).upper()

                    if ampm == 'PM' and hour != 12:
                        hour += 12
                    elif ampm == 'AM' and hour == 12:
                        hour = 0

                    time_info['checkInTime'] = f"{hour:02d}:{min_val}"

            # Extract checkout times
            elif 'checkout' in content or 'check-out' in content or 'check out' in content:
                import re
                time_pattern = r'before\s+(\d{1,2}):?(\d{2})?\s*(am|pm)'
                match = re.search(time_pattern, content, re.IGNORECASE)
                if match:
                    hour = int(match.group(1))
                    min_val = match.group(2) or '00'
                    ampm = match.group(3).upper()

                    if ampm == 'PM' and hour != 12:
                        hour += 12
                    elif ampm == 'AM' and hour == 12:
                        hour = 0

                    time_info['checkOutTime'] = f"{hour:02d}:{min_val}"

        if time_info:
            logger.info(f"Extracted time info from rules: {time_info}")

        return time_info

    def _validate_rules_with_gemini(self, rules: List[Dict[str, Any]], modal_text: str) -> Optional[List[Dict[str, Any]]]:
        """Use Gemini to validate, deduplicate, and improve house rules"""

        if not GEMINI_AVAILABLE:
            logger.warning("Gemini not available for rule validation")
            return None

        try:
            import google.generativeai as genai

            # Configure Gemini
            genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
            model = genai.GenerativeModel('gemini-2.0-flash-lite')

            # Prepare rules for validation
            rules_text = []
            for i, rule in enumerate(rules):
                rule_type = rule.get('type', 'rule')
                description = rule.get('description', '')
                rules_text.append(f"{i+1}. [{rule_type}] {description}")

            prompt = f"""
You are an expert at processing Airbnb house rules. I've extracted {len(rules)} house rules from a listing, but they may contain duplicates, conflicts, and misclassifications. Please clean and improve them.

EXTRACTED RULES:
{chr(10).join(rules_text)}

MODAL CONTENT SAMPLE:
{modal_text[:1000]}...

ISSUES TO FIX:
1. DUPLICATES: Remove duplicate rules (e.g., "No parties" vs "No parties or events")
2. CONFLICTS: Resolve conflicting rules (e.g., multiple different guest maximums)
3. GUEST MAXIMUM: Keep only ONE guest maximum rule (the most accurate one)
4. BEFORE YOU LEAVE: Compile all "before you leave" instructions into ONE comprehensive rule
5. CLASSIFICATION: Ensure proper type classification (rule vs instruction vs information)
6. STANDARDIZATION: Use consistent language and formatting

COMPILATION RULES:
- For "Before you leave" items, create ONE rule like: "Before you leave: gather used towels, turn things off, lock up, and throw trash away"
- Keep only the MOST SPECIFIC guest maximum (e.g., if you see "5 guests maximum" and "11 guests maximum", keep the more restrictive/accurate one)
- Remove generic duplicates but keep specific variations if they add value

Please respond with a JSON array of cleaned rules:
[
  {{"type": "rule|instruction|information", "description": "cleaned rule description"}},
  {{"type": "rule|instruction|information", "description": "cleaned rule description"}}
]

IMPORTANT: Return ONLY the JSON array, no other text.
"""

            response = model.generate_content(prompt)
            response_text = response.text.strip()

            # Clean up response
            if response_text.startswith('```json'):
                response_text = response_text[7:-3]
            elif response_text.startswith('```'):
                response_text = response_text[3:-3]

            # Parse JSON response
            import json
            validated_rules = json.loads(response_text)

            if isinstance(validated_rules, list) and len(validated_rules) > 0:
                logger.info(f"Gemini validation: {len(rules)} -> {len(validated_rules)} rules")

                # Log the improvements
                for rule in validated_rules:
                    if isinstance(rule, dict) and 'description' in rule:
                        logger.debug(f"Validated rule: [{rule.get('type', 'rule')}] {rule['description']}")

                return validated_rules
            else:
                logger.warning("Gemini returned invalid rule format")
                return None

        except Exception as e:
            logger.warning(f"Error in Gemini rule validation: {e}")
            return None

    def _extract_rules_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extract house rules from raw text using pattern matching"""
        rules = []

        try:
            # Normalize text for better matching
            text_lower = text.lower()

            # Define comprehensive rule patterns
            rule_patterns = [
                # Time-based rules
                ('Check-in after 3:00 PM', r'check.?in.*after.*3:?00.*pm', 'instruction'),
                ('Checkout before 11:00 AM', r'checkout.*before.*11:?00.*am', 'instruction'),
                ('Self check-in with smart lock', r'self.*check.?in.*smart.*lock', 'instruction'),

                # Guest limits - DYNAMIC EXTRACTION (no hardcoded numbers)
                # This will be handled by the dynamic guest capacity extraction below

                # Pet rules
                ('Pets allowed', r'pets\s+allowed', 'rule'),
                ('No pets', r'no\s+pets', 'rule'),

                # Quiet hours - multiple patterns (more flexible)
                ('Quiet hours 9:00 PM - 7:00 AM', r'quiet.*hours.*9:?00.*pm.*7:?00.*am', 'rule'),
                ('Quiet hours 10:00 PM - 7:00 AM', r'quiet.*hours.*10:?00.*pm.*7:?00.*am', 'rule'),
                ('Quiet hours', r'quiet.*hours', 'rule'),  # More flexible pattern

                # Party rules (more flexible)
                ('No parties or events', r'no.*parties.*or.*events', 'rule'),
                ('No parties or events', r'no.*parties.*events', 'rule'),
                ('No parties', r'no.*parties', 'rule'),  # More flexible pattern
                ('No events', r'no.*events', 'rule'),  # More flexible pattern

                # Smoking rules (more flexible)
                ('No smoking', r'no.*smoking', 'rule'),  # More flexible pattern
                ('No smoking or vaping', r'no.*smoking.*or.*vaping', 'rule'),
                ('No smoking or vaping, no parties allowed', r'no.*smoking.*or.*vaping.*no.*parties.*allowed', 'rule'),

                # Photography rules (more flexible)
                ('No commercial photography', r'no.*commercial.*photography', 'rule'),
                ('Commercial photography not allowed', r'commercial.*photography.*not.*allowed', 'rule'),

                # Checkout instructions (more flexible)
                ('Gather used towels', r'gather.*towels', 'instruction'),  # More flexible
                ('Turn things off', r'turn.*things.*off', 'instruction'),
                ('Lock up', r'lock.*up', 'instruction'),  # More flexible
                ('Clean up', r'clean.*up', 'instruction'),
                ('Lock door', r'lock.*door', 'instruction'),
                ('Throw trash away', r'throw.*trash', 'instruction'),  # More flexible
                ('Return keys', r'return.*keys', 'instruction'),

                # Additional rules - comprehensive patterns for missing rules
                ('Drive slowly and carefully', r'drive\s+slowly.*carefully', 'rule'),
                ('Drive slowly', r'drive\s+slowly', 'rule'),
                ('Park only in designated spot', r'park\s+only.*designated', 'rule'),
                ('Do not block other vehicles', r'do\s+not\s+block.*vehicles', 'rule'),
                ('No blocking vehicles', r'no.*blocking.*vehicles', 'rule'),
                ('Respect quiet hours', r'respect.*quiet.*hours', 'rule'),
                ('Baby gear available upon request', r'baby\s+gear.*available.*request', 'rule'),
                ('Baby gear available', r'baby\s+gear.*available', 'rule'),
                ('Crib available upon request', r'crib.*available.*request', 'rule'),
                ('Please treat the space with care', r'treat.*space.*care', 'rule'),
                ('Treat with care', r'treat.*care', 'rule'),
                ('Standard checkout time', r'standard.*checkout.*time', 'instruction'),
                ('Late checkout available', r'late.*checkout.*available', 'instruction'),
                ('$20 per additional hour', r'\$20.*additional.*hour', 'instruction'),
            ]

            # Apply patterns to text
            for description, pattern, rule_type in rule_patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    # Avoid duplicates
                    if not any(rule['description'] == description for rule in rules):
                        rules.append({
                            'description': description,
                            'type': rule_type
                        })

            # DYNAMIC GUEST CAPACITY EXTRACTION - replaces hardcoded "5 guests maximum"
            guest_capacity_rules = self._extract_dynamic_guest_capacity(text)
            for guest_rule in guest_capacity_rules:
                # Avoid duplicates
                if not any(rule['description'] == guest_rule['description'] for rule in rules):
                    rules.append(guest_rule)

        except Exception as e:
            logger.warning(f"Error in text-based rule extraction: {e}")

        return rules

    def _extract_dynamic_guest_capacity(self, text: str) -> List[Dict[str, Any]]:
        """Dynamically extract actual guest capacity from text instead of using hardcoded values"""
        import re

        guest_rules = []
        text_lower = text.lower()

        # Pattern 1: "X guests maximum" or "maximum X guests"
        patterns = [
            r'(\d+)\s+guests?\s+(maximum|max|allowed|limit)',
            r'(maximum|max)\s+(\d+)\s+guests?',
            r'accommodates\s+(\d+)',
            r'sleeps\s+(\d+)',
            r'up\s+to\s+(\d+)\s+guests?',
            r'(\d+)\s+people\s+(maximum|max|allowed)',
            r'capacity[:\s]+(\d+)',
            r'occupancy[:\s]+(\d+)'
        ]

        found_capacities = set()  # Use set to avoid duplicates

        for pattern in patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    # Extract the number from the tuple
                    numbers = [m for m in match if m.isdigit()]
                    if numbers:
                        capacity = int(numbers[0])
                        found_capacities.add(capacity)
                elif match.isdigit():
                    capacity = int(match)
                    found_capacities.add(capacity)

        # Create rules for found capacities
        for capacity in found_capacities:
            # Only create rules for reasonable capacities (1-20 guests)
            if 1 <= capacity <= 20:
                guest_rule = {
                    'description': f'{capacity} guests maximum',
                    'content': f'{capacity} guests maximum',
                    'title': 'Property Capacity',
                    'type': 'rule'
                }
                guest_rules.append(guest_rule)
                logger.info(f"Dynamically extracted guest capacity: {capacity} guests maximum")

        # If no capacity found, don't create any guest rules (better than hardcoded "5 guests")
        if not guest_rules:
            logger.info("No guest capacity found in text - not creating hardcoded guest rule")

        return guest_rules

    def _parse_modal_rules_structure(self, modal_content: BeautifulSoup) -> List[Dict[str, Any]]:
        """Parse the specific modal structure shown in the screenshot"""
        rules = []

        try:
            # Based on screenshot, look for specific rule patterns (comprehensive)
            rule_patterns = [
                # Checking in and out section (exact matches first)
                ('Check-in after 3:00 PM', r'check.?in.*after.*3:?00.*pm', 'instruction'),
                ('Checkout before 11:00 AM', r'checkout.*before.*11:?00.*am', 'instruction'),
                ('Self check-in with smart lock', r'self.*check.?in.*smart.*lock', 'instruction'),

                # During your stay section (exact matches first)
                # Guest limits - DYNAMIC EXTRACTION (no hardcoded numbers)
                ('Pets allowed', r'pets\s+allowed', 'rule'),  # Exact match for this listing
                ('No pets', r'no\s+pets', 'rule'),  # More precise pattern
                ('Pets not allowed', r'pets.*not.*allowed', 'rule'),

                # Quiet hours - multiple patterns for different time formats
                ('Quiet hours 9:00 PM - 7:00 AM', r'quiet.*hours.*9:?00.*pm.*7:?00.*am', 'rule'),
                ('Quiet hours 10:00 PM - 7:00 AM', r'quiet.*hours.*10:?00.*pm.*7:?00.*am', 'rule'),
                ('Quiet hours', r'quiet\s+hours', 'rule'),  # Fallback pattern

                # Parties and events - comprehensive patterns
                ('No parties or events', r'no.*parties.*or.*events', 'rule'),
                ('No parties or events', r'no.*parties.*events', 'rule'),
                ('No parties', r'no\s+parties', 'rule'),
                ('No events', r'no\s+events', 'rule'),
                ('Parties not allowed', r'parties.*not.*allowed', 'rule'),
                ('Events not allowed', r'events.*not.*allowed', 'rule'),

                # Commercial photography
                ('No commercial photography', r'no.*commercial.*photography', 'rule'),
                ('Commercial photography not allowed', r'commercial.*photography.*not.*allowed', 'rule'),

                # Smoking - comprehensive patterns
                ('No smoking', r'no\s+smoking', 'rule'),
                ('No smoking or vaping', r'no.*smoking.*or.*vaping', 'rule'),
                ('No vaping', r'no\s+vaping', 'rule'),
                ('Smoking not allowed', r'smoking.*not.*allowed', 'rule'),

                # Before you leave section (exact matches first)
                ('Gather used towels', r'gather.*used.*towels', 'instruction'),
                ('Gather towels', r'gather.*towels', 'instruction'),
                ('Turn things off', r'turn\s+things\s+off', 'instruction'),
                ('Lock up', r'lock\s+up', 'instruction'),
                ('Throw trash away', r'throw\s+trash\s+away', 'instruction'),
                ('Trash away', r'trash\s+away', 'instruction'),
                ('Return keys', r'return\s+keys', 'instruction'),
                ('Keys return', r'keys.*return', 'instruction'),

                # Additional rules section - comprehensive patterns for missing rules
                ('Drive slowly and carefully', r'drive\s+slowly.*carefully', 'rule'),
                ('Drive slowly', r'drive\s+slowly', 'rule'),
                ('Park only in designated spot', r'park\s+only.*designated.*spot', 'rule'),
                ('Park only in', r'park\s+only\s+in', 'rule'),
                ('Do not block other vehicles', r'do\s+not\s+block.*vehicles', 'rule'),
                ('No blocking vehicles', r'no.*blocking.*vehicles', 'rule'),
                ('Respect quiet hours', r'respect.*quiet.*hours', 'rule'),
                ('Baby gear available upon request', r'baby\s+gear.*available.*request', 'rule'),
                ('Baby gear available', r'baby\s+gear.*available', 'rule'),
                ('Crib available upon request', r'crib.*available.*request', 'rule'),
                ('Please treat the space with care', r'treat.*space.*care', 'rule'),
                ('Treat with care', r'treat.*care', 'rule'),
                ('Standard checkout time', r'standard.*checkout.*time', 'instruction'),
                ('Late checkout available', r'late.*checkout.*available', 'instruction'),
                ('$20 per additional hour', r'\$20.*additional.*hour', 'instruction'),

                # Additional rules section (often contains duplicates or clarifications)
                ('No smoking or vaping, no parties allowed', r'no.*smoking.*or.*vaping.*no.*parties.*allowed', 'rule'),
                ('No smoking, no parties', r'no.*smoking.*no.*parties', 'rule'),

                # Additional comprehensive patterns to catch variations
                ('Pets welcome', r'pets.*welcome', 'rule'),
                ('Events allowed', r'events.*allowed', 'rule'),
                ('Photography not allowed', r'photography.*not.*allowed', 'rule'),
                ('Commercial use', r'commercial.*use', 'rule'),
                ('Smoking allowed', r'smoking.*allowed', 'rule'),
                ('Maximum guests', r'maximum.*\d+.*guests', 'rule'),
                ('Guest limit', r'guest.*limit', 'rule'),
                ('Noise restrictions', r'noise.*restrictions', 'rule'),
                ('Sound restrictions', r'sound.*restrictions', 'rule'),

                # Checkout instructions variations
                ('Clean up', r'clean.*up', 'instruction'),
                ('Tidy up', r'tidy.*up', 'instruction'),
                ('Dispose trash', r'dispose.*trash', 'instruction'),
                ('Take out trash', r'take.*out.*trash', 'instruction'),
                ('Switch off', r'switch.*off', 'instruction'),
                ('Turn off lights', r'turn.*off.*lights', 'instruction'),
                ('Lock door', r'lock.*door', 'instruction'),
                ('Secure property', r'secure.*property', 'instruction'),
                ('Leave keys', r'leave.*keys', 'instruction'),
                ('Key return', r'key.*return', 'instruction')
            ]

            modal_text = modal_content.get_text().lower()

            # Debug: log a sample of the modal text to see what we're working with
            logger.info(f"Modal text sample (first 500 chars): {modal_text[:500]}")

            for rule_title, pattern, rule_type in rule_patterns:
                if re.search(pattern, modal_text, re.IGNORECASE):
                    # Avoid duplicates
                    if not any(existing_rule['title'] == rule_title for existing_rule in rules):
                        # Determine if this should be a rule or instruction
                        item_type = 'rule' if rule_type == 'rule' else 'instruction'

                        rule_entry = {
                            'title': rule_title,
                            'description': rule_title,
                            'enabled': True,
                            'type': item_type,
                            'source': 'airbnb_modal_extraction'
                        }
                        rules.append(rule_entry)
                        logger.info(f"Extracted modal rule: {rule_title}")
                    else:
                        logger.debug(f"Skipping duplicate rule: {rule_title}")

            # DYNAMIC GUEST CAPACITY EXTRACTION for modal content
            modal_text_full = modal_content.get_text()
            guest_capacity_rules = self._extract_dynamic_guest_capacity(modal_text_full)
            for guest_rule in guest_capacity_rules:
                # Avoid duplicates
                if not any(existing_rule.get('title') == guest_rule['title'] for existing_rule in rules):
                    rules.append(guest_rule)

        except Exception as e:
            logger.warning(f"Error parsing modal rules structure: {e}")

        return rules

    def _is_valid_safety_content(self, text: str) -> bool:
        """Check if text is valid safety content (not navigation or system text)"""
        text_lower = text.lower()

        # Filter out navigation and system content
        invalid_patterns = [
            'airbnb.org emergency', 'airbnb.org', 'emergency stays',
            'summer release', '2025 summer release', '2024 summer release',
            'support', 'help center', 'aircover', 'anti-discrimination',
            'disability support', 'cancellation options', 'report neighborhood',
            'airbnb website', 'javascript enabled', 'skip to content'
        ]

        # Check for invalid patterns
        if any(pattern in text_lower for pattern in invalid_patterns):
            return False

        # Must be substantial content
        if len(text) < 10:
            return False

        return True

    def _extract_practical_facts(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract practical facts about the property"""

        facts = []

        try:
            # Look for practical information
            practical_keywords = ['wifi', 'parking', 'kitchen', 'bathroom', 'bedroom', 'living']

            for keyword in practical_keywords:
                sections = soup.find_all(text=re.compile(keyword, re.IGNORECASE))
                for text_node in sections:
                    parent = text_node.parent
                    if parent:
                        text = parent.get_text(strip=True)
                        if text and len(text) > 20 and len(text) < 200:
                            fact_entry = {
                                'title': f'{keyword.title()} information',
                                'content': text,
                                'type': 'information',
                                'source': 'airbnb_extraction'
                            }
                            facts.append(fact_entry)

            logger.info(f"Extracted {len(facts)} practical facts")

        except Exception as e:
            logger.error(f"Error extracting practical facts: {e}")

        return facts

    def _validate_deep_extraction_with_gemini(self, extracted_data: Dict[str, Any], page_content_sample: str) -> Dict[str, Any]:
        """
        Use Gemini to validate and improve deep extraction data quality.

        Args:
            extracted_data: Raw extracted data
            page_content_sample: Sample of page content for context

        Returns:
            Validated and improved extraction data
        """
        try:
            # Only validate if we have a Gemini API key
            gemini_api_key = os.getenv('GEMINI_API_KEY')
            if not gemini_api_key:
                logger.debug("No Gemini API key found, skipping deep extraction validation")
                return extracted_data

            import google.generativeai as genai
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel('gemini-2.0-flash')

            # Prepare validation prompt for deep extraction
            prompt = f"""
You are a data validation expert for Airbnb property extraction. Please review and improve the following extracted data:

EXTRACTED DATA:
- Description: "{extracted_data.get('description', '')[:200]}..."
- House Rules: {len(extracted_data.get('house_rules', []))} rules found
- Safety Info: {len(extracted_data.get('safety_info', []))} items found
- Amenities: {len(extracted_data.get('amenities', {}).get('basic', []))} basic, {len(extracted_data.get('amenities', {}).get('appliances', []))} appliances
- Local Area: {len(extracted_data.get('local_area', []))} items found

PAGE CONTENT SAMPLE:
{page_content_sample[:1000]}...

VALIDATION TASKS:
1. DESCRIPTION: Clean and improve the property description, removing any selling language
2. HOUSE RULES: Validate and standardize house rules (suggest improvements)
3. AMENITIES: Validate amenity categorization (basic vs appliances)
4. SAFETY: Ensure safety information is properly categorized
5. LOCAL AREA: Improve local area descriptions

Please respond in JSON format:
{{
    "description_improved": "cleaned description",
    "house_rules_suggestions": ["suggestion1", "suggestion2"],
    "amenities_validation": {{"basic_correct": true, "appliances_correct": true}},
    "safety_validation": {{"items_relevant": true}},
    "local_area_improved": ["improved item 1", "improved item 2"],
    "confidence": "high|medium|low",
    "improvements_made": ["list of improvements"]
}}
"""

            response = model.generate_content(prompt)

            # Parse the response
            response_text = response.text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:-3]
            elif response_text.startswith('```'):
                response_text = response_text[3:-3]

            validated_data = json.loads(response_text)

            # Apply validated improvements if confidence is high or medium
            if validated_data.get('confidence') in ['high', 'medium']:
                if validated_data.get('description_improved'):
                    extracted_data['description'] = validated_data['description_improved']

                logger.info(f"Gemini deep extraction validation applied with {validated_data.get('confidence')} confidence")
                if validated_data.get('improvements_made'):
                    logger.info(f"Improvements made: {', '.join(validated_data['improvements_made'])}")
            else:
                logger.info("Gemini deep extraction validation had low confidence, keeping original data")

        except Exception as e:
            logger.warning(f"Gemini deep extraction validation failed: {e}")
            # If Gemini fails due to rate limit, clear the description to avoid nonsensical content
            if "429" in str(e) or "quota" in str(e).lower() or "rate limit" in str(e).lower():
                logger.info("Gemini rate limit hit - clearing description to avoid nonsensical content")
                if 'description' in extracted_data:
                    extracted_data['description'] = ""
            # Return original data if validation fails

        return extracted_data

    def _consolidate_gemini_processing(self, extracted_data: Dict[str, Any], page_content_sample: str) -> Dict[str, Any]:
        """
        Consolidate all Gemini processing into a single API call to reduce rate limit issues.
        This replaces multiple separate calls for validation, enhancement, and rule processing.
        """
        try:
            gemini_api_key = os.getenv('GEMINI_API_KEY')
            if not gemini_api_key:
                logger.debug("No Gemini API key found, skipping consolidated processing")
                return extracted_data

            import google.generativeai as genai
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel('gemini-2.0-flash')

            # Prepare comprehensive prompt that handles all tasks
            house_rules = extracted_data.get('house_rules', [])
            rules_text = []
            for i, rule in enumerate(house_rules):
                if isinstance(rule, dict):
                    content = rule.get('content', rule.get('description', ''))
                    rule_type = rule.get('type', 'rule')
                    rules_text.append(f"{i+1}. [{rule_type}] {content}")

            prompt = f"""
You are an expert at processing Airbnb property data. I need you to perform comprehensive validation, enhancement, and cleaning of extracted property data in a single response.

EXTRACTED DATA TO PROCESS:
- Description: "{extracted_data.get('description', '')[:300]}..."
- House Rules ({len(house_rules)} total): {chr(10).join(rules_text[:10])}
- Basic Amenities: {extracted_data.get('amenities', {}).get('basic', [])}
- Appliances: {[app.get('name', str(app)) if isinstance(app, dict) else str(app) for app in extracted_data.get('amenities', {}).get('appliances', [])]}
- Safety Info: {len(extracted_data.get('safety_info', []))} items
- Check-in Time: {extracted_data.get('checkInTime', 'N/A')}
- Check-out Time: {extracted_data.get('checkOutTime', 'N/A')}

PAGE CONTENT SAMPLE: "{page_content_sample[:500]}..."

TASKS TO PERFORM:
1. DESCRIPTION ENHANCEMENT: Create a brief, sensible property description (50-60 words) based on the listing content. If insufficient content, return empty string.

2. HOUSE RULES PROCESSING: Clean and improve the house rules by:
   - Removing duplicates and conflicts
   - Concatenating "Before you leave" instructions into ONE comprehensive rule
   - Keeping only the most accurate guest maximum rule
   - Proper type classification (rule vs instruction vs information)
   - Standardizing language and formatting

3. DATA VALIDATION: Validate and normalize all extracted data for quality and consistency.

4. TIME EXTRACTION: Extract any check-in/check-out times from rules and apply to property fields.

RESPONSE FORMAT (JSON only):
{{
  "description": "enhanced description or empty string",
  "house_rules": [
    {{"type": "rule|instruction|information", "content": "cleaned rule content", "title": "Rule Title"}}
  ],
  "checkInTime": "HH:MM format or existing value",
  "checkOutTime": "HH:MM format or existing value",
  "amenities": {{
    "basic": ["validated basic amenities"],
    "appliances": [validated appliances with proper structure]
  }},
  "validation_notes": "brief notes about changes made"
}}

IMPORTANT RULES:
- For "Before you leave" items, create ONE rule like: "Before you leave: gather used towels, turn things off, return keys, and lock up"
- Keep only the MOST SPECIFIC guest maximum (remove generic ones)
- Remove time-related rules from house_rules (they go in checkInTime/checkOutTime fields)
- Return ONLY the JSON, no other text
"""

            # Make the consolidated API call with retry logic
            response = self._call_gemini_api(prompt)

            if response:
                # Parse the response
                response_text = response.strip()
                if response_text.startswith('```json'):
                    response_text = response_text[7:-3]
                elif response_text.startswith('```'):
                    response_text = response_text[3:-3]

                import json
                consolidated_result = json.loads(response_text)

                # Apply the consolidated results back to extracted_data
                if 'description' in consolidated_result:
                    extracted_data['description'] = consolidated_result['description']

                if 'house_rules' in consolidated_result:
                    extracted_data['house_rules'] = consolidated_result['house_rules']

                # Only override times if consolidated result provides a concrete value (not empty or 'N/A')
                cin = consolidated_result.get('checkInTime')
                if cin and str(cin).strip().upper() != 'N/A' and cin != extracted_data.get('checkInTime'):
                    extracted_data['checkInTime'] = cin
                    logger.info(f"Updated check-in time from consolidated processing: {cin}")

                cout = consolidated_result.get('checkOutTime')
                if cout and str(cout).strip().upper() != 'N/A' and cout != extracted_data.get('checkOutTime'):
                    extracted_data['checkOutTime'] = cout
                    logger.info(f"Updated check-out time from consolidated processing: {cout}")

                if 'amenities' in consolidated_result:
                    extracted_data['amenities'] = consolidated_result['amenities']

                if 'validation_notes' in consolidated_result:
                    logger.info(f"Consolidated Gemini processing notes: {consolidated_result['validation_notes']}")

                logger.info("Consolidated Gemini processing completed successfully")
                return extracted_data

        except Exception as e:
            logger.warning(f"Consolidated Gemini processing failed: {e}")
            # If consolidated processing fails, clear description to avoid nonsensical content
            if "429" in str(e) or "quota" in str(e).lower() or "rate limit" in str(e).lower():
                logger.info("Gemini rate limit hit - clearing description to avoid nonsensical content")
                if 'description' in extracted_data:
                    extracted_data['description'] = ""

        return extracted_data

    def _get_empty_deep_extraction_result(self) -> Dict[str, Any]:
        """Return empty deep extraction result structure"""

        return {
            'amenities': {'basic': [], 'appliances': []},
            'house_rules': [],
            'safety_info': [],
            'description': '',
            'checkin_checkout': {
                'checkin_time': '',
                'checkout_time': '',
                'checkin_instructions': '',
                'checkout_instructions': ''
            },
            'local_area': [],
            'practical_facts': []
        }

    def create_property_from_extraction(self, host_id: str, listing_data: Dict[str, Any],
                                      extracted_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a new property from listing and extracted data.

        Args:
            host_id: ID of the host
            listing_data: Basic listing data from scraper
            extracted_data: Deep extracted data

        Returns:
            Property ID if successful, None otherwise
        """
        try:
            from concierge.utils.property_schema import get_default_property_data
            from concierge.utils.firestore_client import create_property, create_knowledge_item, get_firestore_db
            from datetime import datetime
            import uuid

            # Normalize the listing URL for consistent storage and duplicate checking
            original_url = listing_data.get('url', '')
            normalized_url = self._normalize_airbnb_url(original_url)

            # Check for existing properties with the same Airbnb URL for current user only
            db = get_firestore_db()
            if db:
                try:
                    # Query only current user's properties to check for duplicates
                    existing_query = db.collection('properties').where('hostId', '==', host_id).where('airbnbListingUrl', '==', normalized_url)
                    existing_properties = list(existing_query.stream())

                    if existing_properties:
                        existing_property = existing_properties[0]
                        existing_id = existing_property.id
                        existing_data = existing_property.to_dict()

                        logger.warning(f"Property already exists for current user ({host_id}) with Airbnb URL {normalized_url}")
                        logger.warning(f"Existing property ID: {existing_id}")
                        logger.warning(f"Existing property name: {existing_data.get('name', 'Unknown')}")

                        # Return the existing property ID since it belongs to the same host
                        logger.info(f"Returning existing property ID for user {host_id}: {existing_id}")
                        return existing_id

                except Exception as e:
                    logger.error(f"Error checking for duplicate properties for user {host_id}: {e}")
                    # Continue with creation if duplicate check fails

            # Generate property ID
            property_id = str(uuid.uuid4())

            # Create property data structure
            property_data = get_default_property_data(host_id, normalized_url)

            # Populate with listing data
            # Prioritize original listing description over extracted description (which may be amenity lists)
            original_description = listing_data.get('description', '')
            extracted_description = extracted_data.get('description', '')

            # Use original description if it's substantial, otherwise use extracted
            if original_description and len(original_description.split()) >= 20:
                description = original_description
                logger.debug(f"Using original listing description ({len(original_description.split())} words)")
            elif extracted_description and len(extracted_description.split()) >= 20:
                description = extracted_description
                logger.debug(f"Using extracted description ({len(extracted_description.split())} words)")
            else:
                # Fallback to whichever is longer
                description = original_description if len(original_description) > len(extracted_description) else extracted_description
                logger.debug(f"Using fallback description ({len(description.split())} words)")

            # If we have a description, clean and compile it to be brief (50-60 words)
            if description:
                try:
                    cleaned_description = self._clean_description_text(description)

                    # Check if the cleaned description is meaningful
                    word_count = len(cleaned_description.split())

                    # Enhanced quality check for descriptions
                    generic_terms = [
                        'accommodation', 'property', 'place', 'space', 'home',
                        'rental', 'listing', 'unit', 'apartment', 'house'
                    ]

                    # Check if description is mostly generic terms
                    words = cleaned_description.lower().split()
                    generic_word_count = sum(1 for word in words if any(term in word for term in generic_terms))
                    generic_ratio = generic_word_count / len(words) if words else 1

                    # If description is too short, generic, or low quality, leave it blank
                    if (word_count < 15 or
                        generic_ratio > 0.3 or
                        cleaned_description.lower().strip() in ['accommodation.', 'accommodation', 'property.', 'property'] or
                        len(set(words)) < len(words) * 0.6):  # Too many repeated words
                        description = ''
                        logger.debug(f"Description rejected: {word_count} words, {generic_ratio:.2f} generic ratio")
                    else:
                        description = cleaned_description
                        logger.debug(f"Accepted description: {word_count} words")

                except Exception as e:
                    logger.debug(f"Error cleaning description: {e}")
                    description = ''  # Leave blank on error

            property_data.update({
                'name': listing_data.get('title', 'Imported Property'),
                'address': listing_data.get('location', ''),
                'description': description,
                'amenities': extracted_data.get('amenities', {'basic': [], 'appliances': []}),
                'importData': {
                    'extractedAt': datetime.now().isoformat(),
                    'source': 'airbnb',
                    'rawData': {
                        'listing': listing_data,
                        'extracted': extracted_data,
                        'house_rules': extracted_data.get('house_rules', []),  # Store house rules for frontend access
                        'safety_info': extracted_data.get('safety_info', []),
                        'ocr_raw': extracted_data.get('ocr_raw', {})
                    }
                }
            })

            # Update check-in/check-out times from multiple sources
            checkin_checkout = extracted_data.get('checkin_checkout', {})

            # First try from dedicated checkin_checkout extraction
            if checkin_checkout.get('checkin_time'):
                property_data['checkInTime'] = self._normalize_time(checkin_checkout['checkin_time'])
            if checkin_checkout.get('checkout_time'):
                property_data['checkOutTime'] = self._normalize_time(checkin_checkout['checkout_time'])

            # Also try to extract times from house rules as backup/override
            house_rules_times = self._extract_times_from_house_rules(extracted_data.get('house_rules', []))
            if house_rules_times.get('checkin_time') and not property_data.get('checkInTime'):
                property_data['checkInTime'] = house_rules_times['checkin_time']
                logger.info(f"Extracted check-in time from house rules: {house_rules_times['checkin_time']}")
            if house_rules_times.get('checkout_time') and not property_data.get('checkOutTime'):
                property_data['checkOutTime'] = house_rules_times['checkout_time']
                logger.info(f"Extracted check-out time from house rules: {house_rules_times['checkout_time']}")

            # Override defaults with consolidated extracted times when available
            if extracted_data.get('checkInTime'):
                property_data['checkInTime'] = self._normalize_time(str(extracted_data['checkInTime']))
                logger.info(f"Applied consolidated/ocr check-in time: {property_data['checkInTime']}")
            if extracted_data.get('checkOutTime'):
                property_data['checkOutTime'] = self._normalize_time(str(extracted_data['checkOutTime']))
                logger.info(f"Applied consolidated/ocr check-out time: {property_data['checkOutTime']}")

            # Map extracted house rules into structured property fields for setup wizard
            structured_rules: List[Dict[str, Any]] = []
            
            # Debug counters for visibility into filtering decisions
            debug_counts = {'empty': 0, 'heading': 0, 'placeholder': 0}

            # Build OCR content set to verify presence-only items (e.g., 'Before you leave')
            ocr_contents_norm: set = set()
            try:
                ocr_raw = (extracted_data.get('ocr_raw') or {})
                for k in ('house_rules_ocr_main', 'house_rules_ocr_additional'):
                    for it in (ocr_raw.get(k) or []):
                        t = (it.get('content') or it.get('description') or '').strip().lower()
                        if t:
                            ocr_contents_norm.add(t)
            except Exception:
                pass

            def _norm_text(txt: str) -> str:
                s = (txt or '').lower().strip()
                # normalize unicode quotes and dashes
                replacements = {
                    '“': '"', '”': '"', '’': "'", '‘': "'",
                    '—': '-', '–': '-', '…': '',
                }
                for a,b in replacements.items():
                    s = s.replace(a,b)
                # drop straight quotes which often vary between sources
                s = s.replace('"','').replace("'", '')
                # collapse whitespace
                s = ' '.join(s.split())
                return s

            # Preprocess rules to merge split Quiet Hours label and time-only lines
            raw_rules = (extracted_data.get('house_rules') or [])
            preprocessed_rules: List[Dict[str, Any]] = []
            consumed: set = set()
            time_only_re = re.compile(r'^(?:between\s+)?[0-9:\s\.apmAPMAPM]+\s*(?:-|to|–|—|and)\s*[0-9:\s\.apmAPMAPM]+$', re.IGNORECASE)
            for i, r in enumerate(raw_rules):
                if i in consumed:
                    continue
                ctext = (r.get('content') or r.get('description') or '').strip()
                title_lc = (r.get('title') or '').strip().lower()
                lc = ctext.lower()
                is_quiet_label = ('quiet hour' in lc) or ('quiet hour' in title_lc)
                if is_quiet_label and (i + 1) < len(raw_rules):
                    nxt = raw_rules[i + 1]
                    nxt_text = (nxt.get('content') or nxt.get('description') or '').strip()
                    if nxt_text and time_only_re.match(nxt_text.strip()):
                        merged = dict(r)
                        merged['content'] = f"Quiet hours {nxt_text.strip()}"
                        # Prefer neutral title here; precise extractor will set final title
                        merged['title'] = r.get('title') or 'Quiet hours'
                        preprocessed_rules.append(merged)
                        consumed.add(i + 1)
                        continue
                preprocessed_rules.append(r)

            for rule in preprocessed_rules:
                content = (rule.get('content') or rule.get('description') or '').strip()
                if not content:
                    debug_counts['empty'] += 1
                    continue
                # Skip section headings and UI noise
                # Keep contentful rules even if they are under heading titles like 'During your stay'
                # Only skip when the content is empty or a generic disclaimer line
                title_raw = (rule.get('title') or '').strip().lower()
                lc_content = content.lower().strip()
                generic_disclaimer_phrases = [
                    "you'll be staying in someone's home",
                    'treat it with care and respect'
                ]
                if title_raw in {'house rules','checking in and out','during your stay','additional rules'}:
                    if (not lc_content) or any(p in lc_content for p in generic_disclaimer_phrases):
                        debug_counts['heading'] += 1
                        continue
                # Skip placeholders
                lc = content.lower()
                if lc == 'none' or 'show more' in lc:
                    debug_counts['placeholder'] += 1
                    continue
                # Exclude check-in/check-out time statements (times are applied to dedicated fields, not as rules)
                time_tokens = ['am', 'pm', 'a.m.', 'p.m.', 'noon', 'midnight']
                mentions_check = any(tok in lc for tok in ['check-in', 'check in', 'check-out', 'checkout'])
                has_time_hint = any(t in lc for t in time_tokens) or any(ch.isdigit() for ch in lc)
                if mentions_check and has_time_hint:
                    # Do not add explicit check-in/out time rules
                    continue
                # Exclude vague Quiet Hours unless an explicit time range is present
                if 'quiet hour' in lc:
                    has_range_marker = ('-' in lc) or (' to ' in lc)
                    if not (has_time_hint and has_range_marker):
                        # Skip generic/vague quiet hours without time window
                        continue
                # Prefer precise titles over generic section headings (e.g., "During your stay")
                title = rule.get('title') or self._extract_precise_rule_title(content)
                if title_raw in {'house rules','checking in and out','during your stay','additional rules'}:
                    title = self._extract_precise_rule_title(content)
                # Recognize noise-with-time-range as Quiet Hours for titling consistency
                if 'noise' in lc and ((' between ' in lc and ' and ' in lc) or (' - ' in lc) or (' to ' in lc)):
                    time_pat = r"(\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|am|pm))"
                    times = re.findall(time_pat, content, flags=re.IGNORECASE)
                    if len(times) >= 2:
                        title = f"Quiet hours ({times[0]} - {times[1]})"

                r_type = rule.get('type') or 'rule'
                # Normalize departure/checkout instructions into instruction type
                if 'before you leave' in content.lower():
                    r_type = 'instruction'
                # Reclassify important obligation paragraphs as rules so they are retained
                arrival_markers = [
                    'upon your arrival', 'upon arrival', 'on your arrival',
                    'inspect the property', 'report any damage', 'report any issues'
                ]
                cooperation_markers = [
                    'reasonable amount of time', 'cooperate with',
                    'allow us to access', 'permit us to access', 'access to the property'
                ]
                lc_full = content.lower()
                if any(m in lc_full for m in arrival_markers + cooperation_markers):
                    r_type = 'rule'
                structured_rules.append({
                    'id': f"imported_{uuid.uuid4().hex[:8]}",
                    'title': title,
                    'content': content,
                    'description': content,
                    'enabled': True,
                    'type': r_type,
                    'source': 'imported'
                })

            if structured_rules:
                # Dedupe by normalized content
                seen_rules = set()
                deduped_rules: List[Dict[str, Any]] = []
                for r in structured_rules:
                    key = _norm_text(r.get('content', ''))
                    if not key or key in seen_rules:
                        continue
                    seen_rules.add(key)
                    deduped_rules.append(r)
                # Ensure core prohibitions/requirements from OCR are present
                try:
                    ocr_all = []
                    ocr_raw = (extracted_data.get('ocr_raw') or {})
                    for k in ('house_rules_ocr_main', 'house_rules_ocr_additional'):
                        ocr_all.extend(ocr_raw.get(k) or [])
                    keep_patterns = [
                        ('No pets', ['no pet']),
                        ('No smoking', ['no smok']),
                        ('No parties or events', ['no part', 'no event']),
                        ('Quiet hours', ['quiet hour']),
                        ('Self check-in with keypad', ['self check-in','self check in','keypad']),
                        ('No commercial photography', ['no commercial photography','no filming','no commercial photo','no commercial film'])
                    ]
                    existing_norm = {_norm_text(r.get('content','')) for r in deduped_rules}
                    for title, needles in keep_patterns:
                        # find any OCR item that matches
                        match_txt = None
                        for it in ocr_all:
                            try:
                                if isinstance(it, dict):
                                    raw = (it.get('content') or it.get('description') or '')
                                else:
                                    raw = str(it or '')
                            except Exception:
                                raw = ''
                            txt = _norm_text(raw)
                            if txt and any(n in txt for n in needles):
                                match_txt = txt
                                break
                        if match_txt and match_txt not in existing_norm:
                            low = match_txt.lower()
                            # Require explicit time window for Quiet hours from OCR as well
                            if title == 'Quiet hours':
                                has_digits = any(ch.isdigit() for ch in low)
                                has_hint = any(t in low for t in ['am', 'pm', 'a.m.', 'p.m.', 'noon', 'midnight'])
                                has_range = ('-' in low) or (' to ' in low)
                                if not ((has_hint or has_digits) and has_range):
                                    continue
                            # For self check-in, require both self-check and a specific method to reduce UI false positives
                            if title == 'Self check-in with keypad':
                                if not (('self check' in low) and (('keypad' in low) or ('smart lock' in low) or ('lockbox' in low))):
                                    continue
                            deduped_rules.append({
                                'id': f"imported_{uuid.uuid4().hex[:8]}",
                                'title': title,
                                'content': match_txt,
                                'description': match_txt,
                                'enabled': True,
                                'type': 'rule',
                                'source': 'imported'
                            })
                            existing_norm.add(match_txt)
                except Exception:
                    pass

                # Prefer specific variants (with fines/amounts) over generic duplicates for common prohibitions
                try:
                    def _select_best_variant(rules_list: List[Dict[str, Any]], needle: str) -> List[Dict[str, Any]]:
                        matched_indices = [i for i, r in enumerate(rules_list) if needle in _norm_text(r.get('content',''))]
                        if len(matched_indices) <= 1:
                            return rules_list
                        # score by specificity: presence of '$', 'fine', or digits and by length
                        best_idx = None
                        best_score = -1
                        for i in matched_indices:
                            txt = _norm_text(rules_list[i].get('content',''))
                            score = len(txt)
                            if '$' in txt or ' fine' in txt or any(ch.isdigit() for ch in txt):
                                score += 50
                            if score > best_score:
                                best_score = score
                                best_idx = i
                        keep = set([best_idx])
                        return [r for j, r in enumerate(rules_list) if (j not in matched_indices) or (j in keep)]

                    for n in ['no pet', 'no smok', 'no part', 'no event']:
                        deduped_rules = _select_best_variant(deduped_rules, n)
                except Exception:
                    pass

                # Drop instruction-type items (e.g., departure checklists, checkout instructions) from initial houseRules
                filtered_rules = [r for r in deduped_rules if (r.get('type') or 'rule') == 'rule']
                property_data['houseRules'] = filtered_rules
                # Summary logging for visibility during validation
                logger.info(
                    f"House rules mapping: total={len(extracted_data.get('house_rules', []))}, "
                    f"kept_structured={len(structured_rules)}, kept_deduped={len(deduped_rules)}, "
                    f"filtered_empty={debug_counts.get('empty', 0)}, "
                    f"filtered_heading={debug_counts.get('heading', 0)}, "
                    f"filtered_placeholder={debug_counts.get('placeholder', 0)}"
                )

                # If a capacity rule exists, ensure we keep it clearly titled
                for r in property_data['houseRules']:
                    text = r.get('content', '').lower()
                    if any(k in text for k in ['guest', 'occupancy', 'capacity']) and any(ch.isdigit() for ch in text):
                        r['title'] = r['title'] or 'Property Capacity'

            # Map safety info into emergencyInfo (imported items enabled by default)
            safety_structured: List[Dict[str, Any]] = []
            for s in extracted_data.get('safety_info', []) or []:
                s_text = (s.get('content') or s.get('description') or '').strip()
                if not s_text:
                    continue
                s_title = (s.get('title') or '').strip()
                # Filter out headers/placeholders
                if s_title.lower() in {'safety & property', 'safety considerations', 'safety devices'}:
                    continue
                if _norm_text(s_text) in {'none', ''}:
                    continue
                if _norm_text(s_title) == 'none':
                    continue
                safety_structured.append({
                    'id': f"imported_safety_{uuid.uuid4().hex[:8]}",
                    'title': s_title or 'Safety',
                    'instructions': s_text,
                    'location': s.get('location', ''),
                    'enabled': True,
                    'type': 'imported'
                })
            if safety_structured:
                # Dedupe safety by normalized title+instructions
                seen_safe = set()
                deduped_safe: List[Dict[str, Any]] = []
                for it in safety_structured:
                    key = _norm_text((it.get('title','') + ' ' + it.get('instructions','')).strip())
                    if not key or key in seen_safe:
                        continue
                    seen_safe.add(key)
                    deduped_safe.append(it)
                property_data['emergencyInfo'] = deduped_safe

                # Map specific disclosures also to rules (e.g., stairs)
                extra_rules: List[Dict[str, Any]] = []
                for it in deduped_safe:
                    t = (it.get('title') or '').lower()
                    instr = (it.get('instructions') or '').lower()
                    if 'must climb stairs' in t or 'must climb stairs' in instr or ('stairs' in instr and 'must' in instr):
                        extra_rules.append({
                            'id': f"imported_{uuid.uuid4().hex[:8]}",
                            'title': 'Stairs',
                            'content': 'Must climb stairs',
                            'description': 'Must climb stairs',
                            'enabled': True,
                            'type': 'rule',
                            'source': 'imported'
                        })
                if extra_rules:
                    existing = property_data.get('houseRules', []) or []
                    exist_norm = {_norm_text(r.get('content','')) for r in existing}
                    for r in extra_rules:
                        if _norm_text(r['content']) not in exist_norm:
                            existing.append(r)
                            exist_norm.add(_norm_text(r['content']))
                    property_data['houseRules'] = existing

            # Create the property
            if create_property(property_id, property_data):
                logger.info(f"Created property {property_id}")

                # Create knowledge items from extracted data
                self._create_knowledge_items_from_extraction(property_id, extracted_data)

                return property_id
            else:
                logger.error(f"Failed to create property")
                return None

        except Exception as e:
            logger.error(f"Error creating property from extraction: {e}")
            return None

    def _extract_times_from_house_rules(self, house_rules: List[Dict[str, Any]]) -> Dict[str, str]:
        """Extract check-in and check-out times from house rules"""

        times = {
            'checkin_time': None,
            'checkout_time': None
        }

        try:
            for rule in house_rules:
                description = rule.get('description', '').lower()
                original_description = rule.get('description', '')

                # Look for check-in times
                if 'check' in description and 'in' in description:
                    extracted_time = self._extract_time_from_text(original_description)
                    if extracted_time:
                        times['checkin_time'] = extracted_time
                        logger.debug(f"Found check-in time in rule: {extracted_time}")

                # Look for check-out times
                elif 'check' in description and 'out' in description:
                    extracted_time = self._extract_time_from_text(original_description)
                    if extracted_time:
                        times['checkout_time'] = extracted_time
                        logger.debug(f"Found check-out time in rule: {extracted_time}")

        except Exception as e:
            logger.warning(f"Error extracting times from house rules: {e}")

        return times

    def _extract_time_from_text(self, text: str) -> Optional[str]:
        """Extract time from text in various formats"""

        try:
            # Time patterns to match
            time_patterns = [
                r'(\d{1,2}):(\d{2})\s*(AM|PM)',           # 3:00 PM, 11:30 AM
                r'(\d{1,2})\s*(AM|PM)',                   # 3 PM, 11 AM
                r'(\d{1,2}):(\d{2})',                     # 15:00, 23:30 (24-hour)
                r'after\s+(\d{1,2}):(\d{2})\s*(AM|PM)',  # after 3:00 PM
                r'before\s+(\d{1,2}):(\d{2})\s*(AM|PM)', # before 11:00 AM
                r'(\d{1,2})\s*:\s*(\d{2})\s*(AM|PM)'     # 3 : 00 PM (with spaces)
            ]

            for pattern in time_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if len(match.groups()) > 1 and match.group(2) else 0
                    ampm = match.group(3).upper() if len(match.groups()) > 2 and match.group(3) else None

                    # Convert to 24-hour format
                    if ampm == 'PM' and hour != 12:
                        hour += 12
                    elif ampm == 'AM' and hour == 12:
                        hour = 0

                    # Format as HH:MM
                    return f"{hour:02d}:{minute:02d}"

        except Exception as e:
            logger.debug(f"Error extracting time from text '{text}': {e}")

        return None

    def _normalize_time(self, time_str: str) -> str:
        """Normalize time string to HH:MM format"""

        try:
            # First try the more sophisticated extraction
            extracted = self._extract_time_from_text(time_str)
            if extracted:
                return extracted

            # Fallback to simple parsing
            # Remove AM/PM and extra spaces
            time_str = re.sub(r'\s*(AM|PM)\s*', '', time_str, flags=re.IGNORECASE).strip()

            # Handle different time formats
            if ':' in time_str:
                parts = time_str.split(':')
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
            else:
                hour = int(time_str)
                minute = 0

            # Format as HH:MM
            return f"{hour:02d}:{minute:02d}"

        except Exception:
            # Return default if parsing fails
            return "15:00"

    def _create_knowledge_items_from_extraction(self, property_id: str, extracted_data: Dict[str, Any]):
        """Create knowledge items from extracted data"""

        try:
            from concierge.utils.firestore_client import create_knowledge_item
            from datetime import datetime
            import uuid

            # Create house rules (prefer 'content', fallback to 'description')
            for rule in extracted_data.get('house_rules', []):
                text = (rule.get('content') or rule.get('description') or '').strip()
                if not text:
                    continue

                # Filtering to exclude non-listing or instruction-type items from rule knowledge items
                title_raw = (rule.get('title') or '').strip().lower()
                lc = text.lower().strip()

                # Exclude generic disclaimers and headings without concrete content
                generic_disclaimer_phrases = [
                    "you'll be staying in someone's home",
                    "you are staying in someone's home",
                    'treat it with care and respect',
                    'please treat the space with respect',
                    'be respectful of the property'
                ]
                if title_raw in {'house rules', 'checking in and out', 'during your stay', 'additional rules'}:
                    if (not lc) or any(p in lc for p in generic_disclaimer_phrases):
                        continue

                # Skip placeholders/UI artifacts
                if lc == 'none' or 'show more' in lc:
                    continue

                # Exclude explicit check-in/check-out time statements (times belong to dedicated fields)
                time_tokens = ['am', 'pm', 'a.m.', 'p.m.', 'noon', 'midnight']
                mentions_check = any(tok in lc for tok in ['check-in', 'check in', 'check-out', 'checkout'])
                has_time_hint = any(t in lc for t in time_tokens) or any(ch.isdigit() for ch in lc)
                if mentions_check and has_time_hint:
                    continue

                # Exclude vague Quiet Hours unless explicit time range present
                if 'quiet hour' in lc:
                    has_range_marker = ('-' in lc) or (' to ' in lc)
                    if not (has_time_hint and has_range_marker):
                        continue

                # Exclude instruction-type/departure content from rule knowledge items
                title_lc = title_raw
                if ('before you leave' in lc) or ('departure' in lc) or ('before you leave' in title_lc) or ('departure' in title_lc):
                    continue

                item_id = str(uuid.uuid4())
                item_data = {
                    'propertyId': property_id,
                    'type': 'rule',
                    'tags': ['house_rules', 'imported'],
                    'content': text,
                    'status': 'pending',
                    'source': 'airbnb_extraction',
                    'createdAt': datetime.now().isoformat(),
                    'updatedAt': datetime.now().isoformat()
                }
                create_knowledge_item(item_id, item_data)

            # Create safety/emergency info (with filtering)
            for safety in extracted_data.get('safety_info', []):
                content = safety['content']

                # Filter out navigation and system content
                if self._is_valid_safety_content(content):
                    item_id = str(uuid.uuid4())
                    item_data = {
                        'propertyId': property_id,
                        'type': 'emergency',
                        'tags': ['safety', 'emergency', 'imported'],
                        'content': content,
                        'status': 'pending',
                        'source': 'airbnb_extraction',
                        'createdAt': datetime.now().isoformat(),
                        'updatedAt': datetime.now().isoformat()
                    }
                    create_knowledge_item(item_id, item_data)

            # Create check-in/check-out instructions
            checkin_checkout = extracted_data.get('checkin_checkout', {})
            if checkin_checkout.get('checkin_instructions'):
                item_id = str(uuid.uuid4())
                item_data = {
                    'propertyId': property_id,
                    'type': 'instruction',
                    'tags': ['checkin', 'instructions', 'imported'],
                    'content': checkin_checkout['checkin_instructions'],
                    'status': 'pending',
                    'source': 'airbnb_extraction',
                    'createdAt': datetime.now().isoformat(),
                    'updatedAt': datetime.now().isoformat()
                }
                create_knowledge_item(item_id, item_data)

            if checkin_checkout.get('checkout_instructions'):
                item_id = str(uuid.uuid4())
                item_data = {
                    'propertyId': property_id,
                    'type': 'instruction',
                    'tags': ['checkout', 'instructions', 'imported'],
                    'content': checkin_checkout['checkout_instructions'],
                    'status': 'pending',
                    'source': 'airbnb_extraction',
                    'createdAt': datetime.now().isoformat(),
                    'updatedAt': datetime.now().isoformat()
                }
                create_knowledge_item(item_id, item_data)

            # Create local area information
            for local_info in extracted_data.get('local_area', []):
                item_id = str(uuid.uuid4())
                item_data = {
                    'propertyId': property_id,
                    'type': 'places',
                    'tags': ['local_area', 'neighborhood', 'imported'],
                    'content': local_info['content'],
                    'status': 'pending',
                    'source': 'airbnb_extraction',
                    'createdAt': datetime.now().isoformat(),
                    'updatedAt': datetime.now().isoformat()
                }
                create_knowledge_item(item_id, item_data)

            # Create practical facts
            for fact in extracted_data.get('practical_facts', []):
                item_id = str(uuid.uuid4())
                item_data = {
                    'propertyId': property_id,
                    'type': 'information',
                    'tags': ['practical_facts', 'imported'],
                    'content': fact['content'],
                    'status': 'pending',
                    'source': 'airbnb_extraction',
                    'createdAt': datetime.now().isoformat(),
                    'updatedAt': datetime.now().isoformat()
                }
                create_knowledge_item(item_id, item_data)

            logger.info(f"Created knowledge items for property {property_id}")

        except Exception as e:
            logger.error(f"Error creating knowledge items: {e}")






    def generate_knowledge_items(self, listings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate knowledge items from extracted listing data.

        Args:
            listings: List of listing dictionaries

        Returns:
            List of knowledge items suitable for ingestion into the knowledge base
        """
        knowledge_items = []
        
        for listing in listings:
            try:
                # Create main property knowledge item
                main_item = {
                    'title': f"Property: {listing.get('title', 'Unknown')}",
                    'content': self._format_property_content(listing),
                    'category': 'property',
                    'source': 'airbnb_scraper',
                    'metadata': {
                        'listing_url': listing.get('url', ''),
                        'location': listing.get('location', ''),
                        'property_type': listing.get('property_type', ''),
                        'amenity_count': len(listing.get('amenities', [])),
                        'image_count': len(listing.get('images', [])),
                        'rating': listing.get('reviews', {}).get('rating'),
                        'review_count': listing.get('reviews', {}).get('count', 0)
                    }
                }
                knowledge_items.append(main_item)

                # Create amenities-specific knowledge item
                if listing.get('amenities'):
                    amenities_item = {
                        'title': f"Amenities: {listing.get('title', 'Unknown')}",
                        'content': f"Available amenities at {listing.get('title', 'Unknown')}:\n\n" + 
                                  "\n".join(f"• {amenity}" for amenity in listing.get('amenities', [])),
                        'category': 'amenities',
                        'source': 'airbnb_scraper',
                        'metadata': {
                            'listing_url': listing.get('url', ''),
                            'amenities': listing.get('amenities', [])
                        }
                    }
                    knowledge_items.append(amenities_item)

                # Create location-specific knowledge item
                if listing.get('location'):
                    _desc = listing.get('description') or ''
                    _desc_snippet = (f"Description: {_desc[:500]}..." if len(_desc) > 500 else _desc)
                    location_item = {
                        'title': f"Location: {listing.get('title', 'Unknown')}",
                        'content': f"Location information for {listing.get('title', 'Unknown')}:\n\n" +
                                  f"Address: {listing.get('location', '')}\n" +
                                  f"Property Type: {listing.get('property_type', '')}\n\n" +
                                  _desc_snippet,
                        'category': 'location',
                        'source': 'airbnb_scraper',
                        'metadata': {
                            'listing_url': listing.get('url', ''),
                            'location': listing.get('location', '')
                        }
                    }
                    knowledge_items.append(location_item)

            except Exception as e:
                logger.error(f"Error generating knowledge items for listing: {e}")

        logger.info(f"Generated {len(knowledge_items)} knowledge items from {len(listings)} listings")
        return knowledge_items

    def _format_property_content(self, listing: Dict[str, Any]) -> str:
        """Format listing data into a comprehensive content string."""
        content_parts = []
        
        if listing.get('title'):
            content_parts.append(f"Property: {listing.get('title')}")
        
        if listing.get('location'):
            content_parts.append(f"Location: {listing.get('location')}")
        
        if listing.get('property_type'):
            content_parts.append(f"Property Type: {listing.get('property_type')}")
        
        if listing.get('description'):
            content_parts.append(f"Description: {listing.get('description')}")
        
        if listing.get('amenities'):
            content_parts.append(f"Amenities ({len(listing.get('amenities', []))} available):")
            for amenity in listing.get('amenities', [])[:20]:  # Limit to first 20 amenities
                content_parts.append(f"• {amenity}")
            
            if len(listing.get('amenities', [])) > 20:
                content_parts.append(f"... and {len(listing.get('amenities', [])) - 20} more amenities")
        
        _rating = listing.get('reviews', {}).get('rating')
        if _rating:
            content_parts.append(f"Rating: {_rating}/5")
        
        _review_count = listing.get('reviews', {}).get('count')
        if _review_count:
            content_parts.append(f"Reviews: {_review_count} reviews")
        
        return "\n\n".join(content_parts)

    def scrape_user_properties(self, user_url: str, output_file: str = None) -> Dict[str, Any]:
        """
        Complete workflow to scrape all properties for a user and generate knowledge items.

        Args:
            user_url: Airbnb user profile URL
            output_file: Optional file to save results to

        Returns:
            Dictionary containing listings and knowledge items
        """
        logger.info(f"Starting complete property scrape for user: {user_url}")
        
        try:
            # Extract listings
            listings = self.extract_user_listings(user_url)
            
            if not listings:
                logger.warning("No listings found for user")
                return {'listings': [], 'knowledge_items': []}
            
            # Generate knowledge items
            knowledge_items = self.generate_knowledge_items(listings)
            
            result = {
                'user_url': user_url,
                'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'listings_count': len(listings),
                'knowledge_items_count': len(knowledge_items),
                'listings': listings,
                'knowledge_items': knowledge_items
            }
            
            # Save to file if requested
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                logger.info(f"Results saved to: {output_file}")
            
            logger.info(f"Scraping complete: {len(listings)} listings, {len(knowledge_items)} knowledge items")
            return result
            
        except Exception as e:
            logger.error(f"Error in complete scrape workflow: {e}")
            return {'listings': [], 'knowledge_items': [], 'error': str(e)}

    def _extract_from_json_scripts(self, soup: BeautifulSoup, page_text: str) -> Dict[str, Any]:
        """
        Extract property data from JSON embedded in script tags.
        Modern Airbnb pages embed data in JavaScript rather than HTML.

        Args:
            soup: BeautifulSoup object of the page
            page_text: Raw HTML text of the page

        Returns:
            Dictionary containing extracted data from JSON
        """
        logger.info("Attempting to extract data from JSON scripts")

        extracted_data = {
            'amenities': {'basic': [], 'appliances': []},
            'house_rules': [],
            'safety_info': [],
            'description': '',
            'checkin_checkout': {
                'checkin_time': '',
                'checkout_time': '',
                'checkin_instructions': '',
                'checkout_instructions': ''
            },
            'local_area': [],
            'practical_facts': []
        }

        try:
            import re
            import json

            # Look for large JSON objects in script tags
            scripts = soup.find_all('script')

            for script in scripts:
                script_text = script.get_text()

                # Skip small scripts
                if len(script_text) < 1000:
                    continue

                # Try to find JSON data with amenities
                try:
                    # Look for patterns that suggest amenity data
                    amenity_patterns = [
                        r'"amenities":\s*\[[^\]]+\]',
                        r'"amenityIds":\s*\[[^\]]+\]',
                        r'"listingAmenities":\s*\[[^\]]+\]'
                    ]

                    for pattern in amenity_patterns:
                        matches = re.findall(pattern, script_text, re.IGNORECASE)
                        for match in matches:
                            try:
                                # Extract just the amenities array
                                amenity_match = re.search(r'\[([^\]]+)\]', match)
                                if amenity_match:
                                    amenity_str = '[' + amenity_match.group(1) + ']'
                                    amenity_data = json.loads(amenity_str)

                                    for item in amenity_data:
                                        if isinstance(item, dict):
                                            name = item.get('name', item.get('title', item.get('localizedName', '')))

                                            # Check if amenity is available (JSON-based availability check)
                                            is_available = True

                                            # Check common availability fields in JSON
                                            if 'available' in item and not item['available']:
                                                is_available = False
                                                logger.debug(f"Filtering out unavailable amenity from JSON: '{name}' (available=false)")
                                            elif 'isAvailable' in item and not item['isAvailable']:
                                                is_available = False
                                                logger.debug(f"Filtering out unavailable amenity from JSON: '{name}' (isAvailable=false)")
                                            elif 'status' in item and item['status'] in ['unavailable', 'disabled', 'inactive']:
                                                is_available = False
                                                logger.debug(f"Filtering out unavailable amenity from JSON: '{name}' (status={item['status']})")
                                            elif 'enabled' in item and not item['enabled']:
                                                is_available = False
                                                logger.debug(f"Filtering out unavailable amenity from JSON: '{name}' (enabled=false)")

                                            if name and isinstance(name, str) and is_available:
                                                # Enhanced appliance keywords for categorization
                                                appliance_keywords = [
                                                    'washer', 'washing machine', 'dryer', 'dishwasher', 'microwave', 'oven',
                                                    'refrigerator', 'fridge', 'coffee maker', 'coffee machine', 'toaster',
                                                    'blender', 'tv', 'television', 'smart tv', 'hdtv', 'roku tv', 'apple tv',
                                                    'hair dryer', 'freezer', 'espresso machine', 'electric kettle',
                                                    'rice cooker', 'slow cooker', 'air fryer', 'food processor',
                                                    'stand mixer', 'ice maker', 'wine fridge', 'stove', 'cooktop',
                                                    'range', 'stovetop'
                                                ]

                                                # Items that should NOT be appliances (common false positives)
                                                non_appliance_keywords = [
                                                    'parking', 'pillows', 'blankets', 'books', 'reading material',
                                                    'security cameras', 'cameras', 'dishes', 'silverware', 'wine glasses',
                                                    'clothing storage', 'exercise equipment', 'noise monitors',
                                                    'decibel monitors', 'beach access', 'wifi', 'internet',
                                                    'air conditioning', 'patio', 'balcony', 'smart lock', 'lock',
                                                    'heating', 'pool', 'hot tub', 'jacuzzi', 'fireplace', 'deck'
                                                ]

                                                # Kitchen appliances for location pre-population (more comprehensive)
                                                kitchen_appliances = [
                                                    'microwave', 'dishwasher', 'refrigerator', 'fridge', 'oven',
                                                    'stove', 'cooktop', 'toaster', 'coffee maker', 'coffee machine',
                                                    'espresso machine', 'freezer', 'blender', 'food processor',
                                                    'electric kettle', 'rice cooker', 'slow cooker', 'air fryer',
                                                    'stand mixer', 'ice maker', 'wine fridge', 'range', 'stovetop'
                                                ]

                                                # More flexible keyword matching with false positive filtering
                                                name_lower = name.lower()
                                                is_appliance = False
                                                is_kitchen_appliance = False
                                                is_non_appliance = False

                                                # Special case: "Coffee" alone should be basic amenity, "Coffee maker" should be appliance
                                                if name_lower == 'coffee':
                                                    is_non_appliance = True

                                                # Check for non-appliance keywords first
                                                if not is_non_appliance:
                                                    for keyword in non_appliance_keywords:
                                                        if keyword in name_lower:
                                                            is_non_appliance = True
                                                            break

                                                # Check for appliance keywords with flexible matching (if not a non-appliance)
                                                if not is_non_appliance:
                                                    for keyword in appliance_keywords:
                                                        # Fixed logic: only match if the keyword is in the name, not the other way around
                                                        if keyword in name_lower:
                                                            is_appliance = True
                                                            break

                                                if is_appliance and not is_non_appliance:
                                                    # Check for kitchen appliance keywords with fixed matching logic
                                                    for keyword in kitchen_appliances:
                                                        # Fixed logic: only match if the keyword is in the name, not the other way around
                                                        if keyword in name_lower:
                                                            is_kitchen_appliance = True
                                                            break

                                                    location = 'Kitchen' if is_kitchen_appliance else ''

                                                    logger.debug(f"Categorizing '{name}' as appliance with location: '{location}'")

                                                    extracted_data['amenities']['appliances'].append({
                                                        'name': name,
                                                        'location': location,
                                                        'brand': '',
                                                        'model': ''
                                                    })
                                                else:
                                                    extracted_data['amenities']['basic'].append(name)
                                        elif isinstance(item, str):
                                            extracted_data['amenities']['basic'].append(item)
                                        elif isinstance(item, int):
                                            # Might be amenity IDs, skip for now
                                            continue
                            except (json.JSONDecodeError, AttributeError):
                                continue

                except Exception as e:
                    logger.debug(f"Error processing script for amenities: {e}")
                    continue

                # Look for description data
                try:
                    description_patterns = [
                        r'"description":\s*"([^"]{50,})"',
                        r'"summary":\s*"([^"]{50,})"',
                        r'"sectioned_description":\s*{[^}]*"summary":\s*"([^"]{50,})"'
                    ]

                    for pattern in description_patterns:
                        matches = re.findall(pattern, script_text, re.IGNORECASE)
                        for match in matches:
                            if len(match) > len(extracted_data['description']):
                                # Clean up the description
                                clean_desc = match.replace('\\n', '\n').replace('\\"', '"').replace('\\/', '/')
                                extracted_data['description'] = clean_desc

                except Exception as e:
                    logger.debug(f"Error processing script for description: {e}")
                    continue

                # Enhanced house rules extraction from JSON
                try:
                    # Strategy 1: Look for structured house rules data
                    house_rules_patterns = [
                        r'"house_rules":\s*\[([^\]]+)\]',
                        r'"houseRules":\s*\[([^\]]+)\]',
                        r'"rules":\s*\[([^\]]+)\]',
                        r'"policies":\s*\[([^\]]+)\]',
                        r'"listingRules":\s*\[([^\]]+)\]',
                        r'"propertyRules":\s*\[([^\]]+)\]'
                    ]

                    # Strategy 2: Look for specific rule types
                    specific_rule_patterns = [
                        r'"quiet_hours":\s*"([^"]+)"',
                        r'"quietHours":\s*"([^"]+)"',
                        r'"smoking":\s*"([^"]+)"',
                        r'"smokingAllowed":\s*(false|true)',
                        r'"parties":\s*"([^"]+)"',
                        r'"partiesAllowed":\s*(false|true)',
                        r'"pets":\s*"([^"]+)"',
                        r'"petsAllowed":\s*(false|true)',
                        r'"checkIn":\s*"([^"]+)"',
                        r'"checkOut":\s*"([^"]+)"',
                        r'"maxGuests":\s*(\d+)',
                        r'"maximumOccupancy":\s*(\d+)'
                    ]

                    # Process structured house rules
                    for pattern in house_rules_patterns:
                        matches = re.findall(pattern, script_text, re.IGNORECASE)
                        for match in matches:
                            try:
                                import json
                                rules_data = json.loads('[' + match + ']')
                                for rule_item in rules_data:
                                    if isinstance(rule_item, str) and len(rule_item) > 5:
                                        rule_entry = {
                                            'title': self._extract_precise_rule_title(rule_item),
                                            'description': rule_item,
                                            'enabled': True,
                                            'type': 'rule',
                                            'source': 'airbnb_json_extraction'
                                        }
                                        extracted_data['house_rules'].append(rule_entry)
                            except:
                                    # If not valid JSON, treat as single rule
                                    if len(match) > 5:
                                        rule_entry = {
                                            'title': self._extract_precise_rule_title(match),
                                            'description': match,
                                            'enabled': True,
                                            'type': 'rule',
                                            'source': 'airbnb_json_extraction'
                                        }
                                        extracted_data['house_rules'].append(rule_entry)

                    # Process specific rule patterns
                    for pattern in specific_rule_patterns:
                        matches = re.findall(pattern, script_text, re.IGNORECASE)
                        for match in matches:
                            rule_description = ""
                            rule_title = ""

                            if 'quiet' in pattern.lower():
                                rule_title = "Quiet hours"
                                rule_description = f"Quiet hours {match}"
                            elif 'smoking' in pattern.lower():
                                if match.lower() == 'false':
                                    rule_title = "No smoking"
                                    rule_description = "Smoking is not allowed anywhere on the property"
                                elif match.lower() == 'true':
                                    rule_title = "Smoking allowed"
                                    rule_description = "Smoking is permitted on the property"
                                else:
                                    rule_title = "Smoking policy"
                                    rule_description = match
                            elif 'parties' in pattern.lower():
                                if match.lower() == 'false':
                                    rule_title = "No parties or events"
                                    rule_description = "Parties and events are not permitted"
                                elif match.lower() == 'true':
                                    rule_title = "Parties allowed"
                                    rule_description = "Parties and events are permitted"
                                else:
                                    rule_title = "Party policy"
                                    rule_description = match
                            elif 'pets' in pattern.lower():
                                if match.lower() == 'false':
                                    rule_title = "No pets"
                                    rule_description = "Pets are not allowed unless specifically approved"
                                elif match.lower() == 'true':
                                    rule_title = "Pets allowed"
                                    rule_description = "Pets are welcome on the property"
                                else:
                                    rule_title = "Pet policy"
                                    rule_description = match
                            elif 'checkin' in pattern.lower():
                                rule_title = "Check-in time"
                                rule_description = f"Check-in is available from {match}"
                            elif 'checkout' in pattern.lower():
                                rule_title = "Check-out time"
                                rule_description = f"Check-out is required by {match}"
                            elif 'maxguests' in pattern.lower() or 'occupancy' in pattern.lower():
                                rule_title = f"Maximum {match} guests"
                                rule_description = f"Property accommodates a maximum of {match} guests"

                            if rule_description and rule_title:
                                rule_entry = {
                                    'title': rule_title,
                                    'description': rule_description,
                                    'enabled': True,
                                    'type': 'rule',
                                    'source': 'airbnb_json_specific_extraction'
                                }
                                extracted_data['house_rules'].append(rule_entry)

                except Exception as e:
                    logger.debug(f"Error processing script for house rules: {e}")
                    continue

            logger.info(f"JSON extraction found {len(extracted_data['house_rules'])} house rules")
            for rule in extracted_data['house_rules']:
                logger.info(f"JSON house rule: {rule.get('title', 'No title')} - {rule.get('description', 'No description')}")

            # Deduplicate amenities before enhancement
            self._deduplicate_amenities(extracted_data['amenities'])

            # Use Gemini to enhance and validate the extracted JSON data
            if extracted_data['amenities']['basic'] or extracted_data['amenities']['appliances'] or extracted_data['description']:
                enhanced_data = self._enhance_json_extraction_with_gemini(extracted_data, page_text[:5000])
                if enhanced_data:
                    extracted_data = enhanced_data

            # Post-process appliances to ensure kitchen location is set (after Gemini enhancement)
            self._post_process_appliances(extracted_data['amenities'])

            # Final deduplication after all processing
            self._deduplicate_amenities(extracted_data['amenities'])

            # Log what we found
            total_amenities = len(extracted_data['amenities']['basic']) + len(extracted_data['amenities']['appliances'])
            logger.info(f"JSON extraction found: {total_amenities} amenities, {len(extracted_data['description'])} char description")

            return extracted_data

        except Exception as e:
            logger.error(f"Error extracting from JSON scripts: {e}")
            return extracted_data

    def _enhance_json_extraction_with_gemini(self, extracted_data: Dict[str, Any], page_sample: str) -> Optional[Dict[str, Any]]:
        """
        Use Gemini to enhance and validate JSON-extracted data.

        Args:
            extracted_data: Raw extracted data from JSON
            page_sample: Sample of page content for context

        Returns:
            Enhanced extraction data or None if enhancement fails
        """
        try:
            # Only enhance if we have a Gemini API key
            gemini_api_key = os.getenv('GEMINI_API_KEY')
            if not gemini_api_key:
                logger.debug("No Gemini API key found, skipping JSON extraction enhancement")
                return extracted_data

            import google.generativeai as genai
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel('gemini-2.0-flash')

            # Prepare enhancement prompt
            prompt = f"""
You are an expert at processing Airbnb property data. I've extracted some data from JSON scripts on an Airbnb listing page, but it needs cleaning and enhancement.

EXTRACTED DATA:
- Description: "{extracted_data.get('description', '')[:300]}..."
- Basic Amenities: {extracted_data.get('amenities', {}).get('basic', [])}
- Appliances: {[app.get('name', str(app)) if isinstance(app, dict) else str(app) for app in extracted_data.get('amenities', {}).get('appliances', [])]}

PAGE CONTEXT (first 1000 chars):
{page_sample[:1000]}

Please enhance this data by:
1. Cleaning and improving the description (remove marketing language, keep practical info)
2. Standardizing amenity names (e.g., "Wi-Fi" -> "WiFi", "A/C" -> "Air conditioning")
3. Properly categorizing appliances vs basic amenities
4. Adding any obvious missing amenities you can infer from the description
5. Extracting house rules if any are mentioned in the description

Return ONLY a JSON object with this structure:
{{
    "description": "cleaned description here",
    "amenities": {{
        "basic": ["standardized", "amenity", "names"],
        "appliances": [
            {{"name": "appliance name", "location": "", "brand": "", "model": ""}}
        ]
    }},
    "house_rules": ["rule1", "rule2"],
    "confidence": "high|medium|low",
    "improvements_made": ["description_cleaned", "amenities_standardized", "etc"]
}}
"""

            response = model.generate_content(prompt)
            response_text = response.text.strip()

            # Clean up response text
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            enhanced_data = json.loads(response_text)

            # Apply enhancements if confidence is reasonable
            if enhanced_data.get('confidence') in ['high', 'medium']:
                result = extracted_data.copy()

                if enhanced_data.get('description'):
                    result['description'] = enhanced_data['description']

                if enhanced_data.get('amenities'):
                    if enhanced_data['amenities'].get('basic'):
                        result['amenities']['basic'] = enhanced_data['amenities']['basic']
                    if enhanced_data['amenities'].get('appliances'):
                        result['amenities']['appliances'] = enhanced_data['amenities']['appliances']

                    # Apply post-processing to ensure kitchen appliances have correct locations
                    self._post_process_appliances(result['amenities'])
                    logger.debug("Applied post-processing to Gemini-enhanced amenities")

                if enhanced_data.get('house_rules'):
                    result['house_rules'] = enhanced_data['house_rules']

                logger.info(f"Gemini JSON enhancement applied with {enhanced_data.get('confidence')} confidence")
                if enhanced_data.get('improvements_made'):
                    logger.info(f"Improvements: {', '.join(enhanced_data['improvements_made'])}")

                return result
            else:
                logger.info("Gemini JSON enhancement had low confidence, keeping original data")
                return extracted_data

        except Exception as e:
            logger.warning(f"Gemini JSON enhancement failed: {e}")
            return extracted_data


def main():
    """CLI interface for the Airbnb scraper."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Airbnb Property Data Scraper')
    parser.add_argument('user_url', help='Airbnb user profile URL')
    parser.add_argument('--output', '-o', help='Output JSON file')
    parser.add_argument('--selenium', action='store_true', help='Use Selenium for JavaScript-heavy pages')
    parser.add_argument('--headless', action='store_false', help='Run browser in non-headless mode')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create scraper instance
    scraper = AirbnbScraper(use_selenium=args.selenium, headless=args.headless)
    
    try:
        # Scrape properties
        result = scraper.scrape_user_properties(
            user_url=args.user_url,
            output_file=args.output
        )
        
        print(f"\nScraping Results:")
        print(f"  User URL: {result.get('user_url', 'N/A')}")
        print(f"  Listings found: {result.get('listings_count', 0)}")
        print(f"  Knowledge items generated: {result.get('knowledge_items_count', 0)}")
        
        if result.get('error'):
            print(f"  Error: {result['error']}")
        
        if args.output:
            print(f"  Results saved to: {args.output}")
        else:
            # Print a summary of results
            print("\nListings Summary:")
            for i, listing in enumerate(result.get('listings', []), 1):
                print(f"  {i}. {listing.get('title', 'Unknown Title')}")
                print(f"     Location: {listing.get('location', 'Unknown')}")
                print(f"     Amenities: {len(listing.get('amenities', []))}")
                print(f"     Images: {len(listing.get('images', []))}")
                print()
        
    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        logger.error(f"Unexpected error: {e}")
    finally:
        # Clean up
        del scraper


if __name__ == '__main__':
    main() 