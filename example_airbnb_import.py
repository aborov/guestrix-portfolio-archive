#!/usr/bin/env python3
"""
Example: Airbnb Property Import

This script demonstrates how to use the Airbnb scraper to import property data
from an Airbnb user profile into the concierge knowledge base system.

Usage:
    python example_airbnb_import.py

Note: You'll need to install the required dependencies first:
    pip install beautifulsoup4 selenium lxml
"""

import os
import json
import sys
from datetime import datetime

# Add the concierge module to the path
sys.path.append('concierge')

def main():
    """
    Example usage of the Airbnb scraper and integration system.
    """
    
    print("🏠 Airbnb Property Import Example")
    print("=" * 50)
    
    # Example Airbnb user URL (replace with actual URL)
    example_user_url = "https://www.airbnb.com/users/show/13734172"
    
    # Example property ID (replace with actual property ID from your system)
    example_property_id = "prop_example_123"
    
    print(f"User URL: {example_user_url}")
    print(f"Property ID: {example_property_id}")
    print()
    
    try:
        # Method 1: Preview properties without importing to knowledge base
        print("📋 Step 1: Previewing Airbnb properties...")
        
        from concierge.utils.airbnb_integration import preview_airbnb_properties
        
        preview_result = preview_airbnb_properties(
            property_id=example_property_id,
            user_url=example_user_url,
            use_selenium=False  # Try without Selenium first
        )
        
        if preview_result.get('error'):
            print(f"❌ Error during preview: {preview_result['error']}")
            
            # Try with Selenium if basic scraping fails
            print("🔄 Retrying with Selenium...")
            preview_result = preview_airbnb_properties(
                property_id=example_property_id,
                user_url=example_user_url,
                use_selenium=True
            )
        
        if preview_result.get('error'):
            print(f"❌ Error: {preview_result['error']}")
            return
        
        # Display preview results
        print("✅ Preview Results:")
        print(f"   Properties found: {preview_result.get('property_count', 0)}")
        print(f"   Total amenities: {preview_result.get('total_amenities', 0)}")
        print(f"   Unique amenities: {preview_result.get('unique_amenities_count', 0)}")
        print(f"   Average rating: {preview_result.get('average_rating', 'N/A')}")
        print(f"   Total reviews: {preview_result.get('total_reviews', 0)}")
        print()
        
        # Display listing details
        print("📝 Listing Details:")
        for i, listing in enumerate(preview_result.get('listings_detail', []), 1):
            print(f"   {i}. {listing.get('title', 'Unknown')}")
            print(f"      Location: {listing.get('location', 'Unknown')}")
            print(f"      Amenities: {listing.get('amenities_count', 0)}")
            print(f"      Rating: {listing.get('rating', 'N/A')}/5")
            print(f"      Reviews: {listing.get('review_count', 0)}")
            print(f"      URL: {listing.get('url', 'N/A')}")
            print()
        
        # Save preview results to file
        preview_filename = f"airbnb_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(preview_filename, 'w', encoding='utf-8') as f:
            json.dump(preview_result, f, indent=2, ensure_ascii=False)
        print(f"📄 Preview results saved to: {preview_filename}")
        print()
        
        # Method 2: Ask user if they want to import to knowledge base
        user_input = input("🤔 Would you like to import these properties to the knowledge base? (y/N): ").strip().lower()
        
        if user_input in ['y', 'yes']:
            print("📥 Step 2: Importing to knowledge base...")
            
            from concierge.utils.airbnb_integration import import_airbnb_properties
            
            import_result = import_airbnb_properties(
                property_id=example_property_id,
                user_url=example_user_url,
                use_selenium=preview_result.get('used_selenium', False)  # Use same method as preview
            )
            
            # Display import results
            print("✅ Import Results:")
            print(f"   Property ID: {import_result.get('property_id')}")
            print(f"   Listings scraped: {import_result.get('listings_scraped', 0)}")
            print(f"   Knowledge items created: {import_result.get('knowledge_items_created', 0)}")
            print(f"   Knowledge items updated: {import_result.get('knowledge_items_updated', 0)}")
            print(f"   Success: {import_result.get('success', False)}")
            
            if import_result.get('errors'):
                print(f"   Errors:")
                for error in import_result['errors']:
                    print(f"     - {error}")
            
            # Save import results to file
            import_filename = f"airbnb_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(import_filename, 'w', encoding='utf-8') as f:
                json.dump(import_result, f, indent=2, ensure_ascii=False)
            print(f"📄 Import results saved to: {import_filename}")
        else:
            print("⏭️  Skipping knowledge base import.")
        
        print()
        print("✨ Example completed successfully!")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Make sure you have installed the required dependencies:")
        print("   pip install beautifulsoup4 selenium lxml")
        print("   Also ensure you're running from the correct directory.")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


def demo_direct_scraper():
    """
    Demonstrate using the Airbnb scraper directly (without integration).
    """
    print("🔧 Direct Scraper Demo")
    print("=" * 30)
    
    try:
        from concierge.utils.airbnb_scraper import AirbnbScraper
        
        # Create scraper instance
        scraper = AirbnbScraper(use_selenium=False)
        
        # Example URL
        user_url = "https://www.airbnb.com/users/show/13734172"
        
        # Scrape properties
        result = scraper.scrape_user_properties(user_url)
        
        print(f"Scraping Results:")
        print(f"  User URL: {result.get('user_url', 'N/A')}")
        print(f"  Listings found: {result.get('listings_count', 0)}")
        print(f"  Knowledge items generated: {result.get('knowledge_items_count', 0)}")
        
        # Save results
        filename = f"direct_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  Results saved to: {filename}")
        
    except Exception as e:
        print(f"Error in direct scraper demo: {e}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Airbnb Property Import Example')
    parser.add_argument('--demo-direct', action='store_true', help='Run direct scraper demo')
    parser.add_argument('--user-url', help='Airbnb user URL to scrape')
    parser.add_argument('--property-id', help='Property ID for integration')
    
    args = parser.parse_args()
    
    if args.demo_direct:
        demo_direct_scraper()
    elif args.user_url and args.property_id:
        # Custom run with provided arguments
        print(f"Running with custom arguments:")
        print(f"  User URL: {args.user_url}")
        print(f"  Property ID: {args.property_id}")
        
        # Modify the example to use provided arguments
        # This would be similar to main() but with custom values
        try:
            from concierge.utils.airbnb_integration import preview_airbnb_properties
            
            result = preview_airbnb_properties(
                property_id=args.property_id,
                user_url=args.user_url,
                use_selenium=False
            )
            
            print("Results:", json.dumps(result, indent=2))
        except Exception as e:
            print(f"Error: {e}")
    else:
        main() 