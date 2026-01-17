#!/usr/bin/env python3
"""
Airbnb Integration Module

This module integrates the Airbnb scraper with the existing concierge knowledge base system,
allowing hosts to automatically populate their property knowledge base with data from their
Airbnb listings.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

# Import the Airbnb scraper
from .airbnb_scraper import AirbnbScraper

# Import existing AI and knowledge base utilities
try:
    from .ai_helpers import process_query_with_rag, generate_embedding
    from .firestore_client import create_knowledge_item, list_knowledge_items_by_property
    AI_HELPERS_AVAILABLE = True
except ImportError as e:
    logging.warning(f"AI helpers not available: {e}")
    AI_HELPERS_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AirbnbPropertyIntegrator:
    """
    Integrates Airbnb property data with the concierge knowledge base system.
    """

    def __init__(self, property_id: str, use_selenium: bool = False):
        """
        Initialize the integrator.

        Args:
            property_id: The property ID in the concierge system
            use_selenium: Whether to use Selenium for scraping
        """
        self.property_id = property_id
        self.scraper = AirbnbScraper(use_selenium=use_selenium)
        self.logger = logging.getLogger(f"{__name__}.{property_id}")

    def import_airbnb_property_data(self, user_url: str) -> Dict[str, Any]:
        """
        Import property data from Airbnb user profile OR a single listing URL and add to knowledge base.

        Args:
            user_url: Airbnb user profile URL

        Returns:
            Dictionary with import results and statistics
        """
        self.logger.info(f"Starting Airbnb data import for property {self.property_id}")
        
        results = {
            'property_id': self.property_id,
            'user_url': user_url,
            'imported_at': datetime.now().isoformat(),
            'listings_scraped': 0,
            'knowledge_items_created': 0,
            'knowledge_items_updated': 0,
            'errors': [],
            'success': False
        }

        try:
            # Step 1: Scrape Airbnb data
            self.logger.info("Scraping Airbnb property data...")
            listings: List[Dict[str, Any]] = []
            knowledge_items: List[Dict[str, Any]] = []

            # Option A: direct listing URL support
            if '/rooms/' in user_url:
                self.logger.info("Detected direct listing URL; extracting single listing details")
                listing = self.scraper.extract_listing_details(user_url)
                if not listing:
                    results['errors'].append("Failed to extract details from listing URL")
                    return results
                listings = [listing]
                knowledge_items = self.scraper.generate_knowledge_items(listings)
            else:
                # Default: user profile URL flow
                scraping_result = self.scraper.scrape_user_properties(user_url)
                if scraping_result.get('error'):
                    results['errors'].append(f"Scraping error: {scraping_result['error']}")
                    return results
                listings = scraping_result.get('listings', [])
                knowledge_items = scraping_result.get('knowledge_items', [])
            
            results['listings_scraped'] = len(listings)
            
            if not listings:
                results['errors'].append("No listings found in Airbnb profile")
                return results

            # Step 2: Process and enhance knowledge items with AI if available
            if AI_HELPERS_AVAILABLE:
                self.logger.info("Enhancing knowledge items with AI...")
                enhanced_knowledge_items = self._enhance_knowledge_items_with_ai(knowledge_items)
            else:
                self.logger.warning("AI helpers not available, using raw knowledge items")
                enhanced_knowledge_items = knowledge_items

            # Step 3: Add to knowledge base
            self.logger.info("Adding knowledge items to knowledge base...")
            for item in enhanced_knowledge_items:
                try:
                    # Add property_id to metadata
                    item['metadata'] = item.get('metadata', {})
                    item['metadata']['property_id'] = self.property_id
                    item['metadata']['source'] = 'airbnb_import'
                    item['metadata']['imported_at'] = results['imported_at']

                    # Check if similar item already exists
                    existing_items = self._find_similar_knowledge_items(item)
                    
                    if existing_items:
                        # Update existing item
                        self._update_knowledge_item(existing_items[0], item)
                        results['knowledge_items_updated'] += 1
                        self.logger.info(f"Updated existing knowledge item: {item['title']}")
                    else:
                        # Create new item
                        self._create_knowledge_item(item)
                        results['knowledge_items_created'] += 1
                        self.logger.info(f"Created new knowledge item: {item['title']}")

                except Exception as e:
                    error_msg = f"Error processing knowledge item '{item.get('title', 'Unknown')}': {e}"
                    results['errors'].append(error_msg)
                    self.logger.error(error_msg)

            results['success'] = True
            self.logger.info(f"Import completed successfully: {results['knowledge_items_created']} created, {results['knowledge_items_updated']} updated")

        except Exception as e:
            error_msg = f"Unexpected error during import: {e}"
            results['errors'].append(error_msg)
            self.logger.error(error_msg)

        return results

    def _enhance_knowledge_items_with_ai(self, knowledge_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enhance knowledge items using AI to improve content and generate additional Q&A pairs.

        Args:
            knowledge_items: List of raw knowledge items from scraper

        Returns:
            List of enhanced knowledge items
        """
        enhanced_items = []
        
        for item in knowledge_items:
            try:
                enhanced_item = item.copy()
                
                # Generate additional Q&A pairs based on the content
                if 'content' in item and item['content']:
                    additional_qna = self._generate_qna_from_content(item['content'], item.get('title', ''))
                    if additional_qna:
                        enhanced_item['generated_qna'] = additional_qna
                
                # Generate embeddings for better search
                if 'content' in item and item['content']:
                    try:
                        embedding = generate_embedding(item['content'])
                        if embedding:
                            enhanced_item['embedding'] = embedding
                    except Exception as e:
                        self.logger.warning(f"Failed to generate embedding for item '{item.get('title', 'Unknown')}': {e}")
                
                enhanced_items.append(enhanced_item)
                
            except Exception as e:
                self.logger.error(f"Error enhancing knowledge item '{item.get('title', 'Unknown')}': {e}")
                # Add the original item if enhancement fails
                enhanced_items.append(item)

        return enhanced_items

    def _generate_qna_from_content(self, content: str, title: str) -> List[Dict[str, str]]:
        """
        Generate Q&A pairs from content using AI.

        Args:
            content: The content to generate Q&A from
            title: The title/context

        Returns:
            List of Q&A dictionaries
        """
        try:
            # Import the Q&A generation function
            from .ai_helpers import generate_qna_with_gemini
            
            # Create a simple property details dict for the function
            property_details = {
                'name': title,
                'description': content[:500]  # Limit to first 500 chars
            }
            
            qna_items = generate_qna_with_gemini(content, property_details)
            return qna_items
            
        except Exception as e:
            self.logger.error(f"Error generating Q&A from content: {e}")
            return []

    def _find_similar_knowledge_items(self, new_item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Find existing knowledge items that are similar to the new item.

        Args:
            new_item: The new knowledge item to check

        Returns:
            List of similar existing items
        """
        try:
            if not AI_HELPERS_AVAILABLE:
                return []

            # Get existing items for this property, then filter by category locally
            existing_items = list_knowledge_items_by_property(self.property_id)
            
            # Simple similarity check based on title and category
            similar_items = []
            new_title = new_item.get('title', '').lower()
            new_category = new_item.get('category', '')
            
            for existing_item in existing_items:
                existing_title = existing_item.get('title', '').lower()
                existing_category = existing_item.get('category', '')
                
                # Check for title similarity and same category
                if (new_category == existing_category and 
                    (new_title in existing_title or existing_title in new_title)):
                    similar_items.append(existing_item)
            
            return similar_items
            
        except Exception as e:
            self.logger.error(f"Error finding similar knowledge items: {e}")
            return []

    def _create_knowledge_item(self, item: Dict[str, Any]) -> bool:
        """
        Create a new knowledge item in the knowledge base.

        Args:
            item: Knowledge item dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            if not AI_HELPERS_AVAILABLE:
                self.logger.warning("Cannot create knowledge item - AI helpers not available")
                return False

            # Create knowledge item data in the new schema format
            item_data = {
                'sourceId': f"airbnb_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                'propertyId': self.property_id,
                'type': item.get('category', 'general'),
                'tags': item.get('tags', []),
                'content': item.get('content', ''),
                'status': 'approved',  # Auto-approve Airbnb imports
                'createdAt': datetime.now().isoformat(),
                'updatedAt': datetime.now().isoformat()
            }

            # Generate a unique item ID
            import uuid
            item_id = str(uuid.uuid4())

            result = create_knowledge_item(item_id, item_data)
            
            return result is not None
            
        except Exception as e:
            self.logger.error(f"Error creating knowledge item: {e}")
            return False

    def _update_knowledge_item(self, existing_item: Dict[str, Any], new_item: Dict[str, Any]) -> bool:
        """
        Update an existing knowledge item with new data.

        Args:
            existing_item: The existing knowledge item
            new_item: The new knowledge item data

        Returns:
            True if successful, False otherwise
        """
        try:
            # For now, we'll just log that we would update
            # The actual update implementation would depend on the specific knowledge base structure
            self.logger.info(f"Would update knowledge item '{existing_item.get('title', 'Unknown')}' with new data")
            
            # TODO: Implement actual update logic when the update function is available
            # This might involve merging content, updating metadata, etc.
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating knowledge item: {e}")
            return False

    def generate_property_summary(self, user_url: str) -> Dict[str, Any]:
        """
        Generate a comprehensive property summary from Airbnb data (user profile or single listing) without importing to knowledge base.

        Args:
            user_url: Airbnb user profile URL

        Returns:
            Dictionary containing property summary
        """
        self.logger.info(f"Generating property summary for {user_url}")
        
        try:
            # Scrape Airbnb data
            listings: List[Dict[str, Any]] = []
            if '/rooms/' in user_url:
                self.logger.info("Detected direct listing URL; generating summary for a single listing")
                listing = self.scraper.extract_listing_details(user_url)
                if listing:
                    listings = [listing]
                else:
                    return {'error': 'Failed to extract listing details'}
            else:
                scraping_result = self.scraper.scrape_user_properties(user_url)
                if scraping_result.get('error'):
                    return {'error': scraping_result['error']}
                listings = scraping_result.get('listings', [])
            
            if not listings:
                return {'error': 'No listings found'}

            # Generate summary
            summary = {
                'property_count': len(listings),
                'total_amenities': 0,
                'unique_amenities': set(),
                'locations': [],
                'property_types': [],
                'average_rating': 0,
                'total_reviews': 0,
                'listings_detail': []
            }

            total_rating = 0
            rated_properties = 0

            for listing in listings:
                # Collect amenities
                amenities = listing.get('amenities', [])
                summary['total_amenities'] += len(amenities)
                summary['unique_amenities'].update(amenities)
                
                # Collect locations
                if listing.get('location'):
                    summary['locations'].append(listing['location'])
                
                # Collect property types
                if listing.get('property_type'):
                    summary['property_types'].append(listing['property_type'])
                
                # Calculate ratings
                rating = listing.get('reviews', {}).get('rating')
                if rating:
                    total_rating += rating
                    rated_properties += 1
                
                review_count = listing.get('reviews', {}).get('count', 0)
                summary['total_reviews'] += review_count
                
                # Add listing detail
                summary['listings_detail'].append({
                    'title': listing.get('title', 'Unknown'),
                    'location': listing.get('location', 'Unknown'),
                    'amenities_count': len(amenities),
                    'rating': rating,
                    'review_count': review_count,
                    'url': listing.get('url')
                })

            # Calculate averages
            summary['unique_amenities'] = list(summary['unique_amenities'])
            summary['unique_amenities_count'] = len(summary['unique_amenities'])
            
            if rated_properties > 0:
                summary['average_rating'] = round(total_rating / rated_properties, 2)

            return summary

        except Exception as e:
            self.logger.error(f"Error generating property summary: {e}")
            return {'error': str(e)}


# Convenience functions for direct use
def import_airbnb_properties(property_id: str, user_url: str, use_selenium: bool = False) -> Dict[str, Any]:
    """
    Convenience function to import Airbnb properties for a given property ID.

    Args:
        property_id: The property ID in the concierge system
        user_url: Airbnb user profile URL
        use_selenium: Whether to use Selenium for scraping

    Returns:
        Dictionary with import results
    """
    integrator = AirbnbPropertyIntegrator(property_id, use_selenium=use_selenium)
    return integrator.import_airbnb_property_data(user_url)


def preview_airbnb_properties(property_id: str, user_url: str, use_selenium: bool = False) -> Dict[str, Any]:
    """
    Convenience function to preview Airbnb properties without importing to knowledge base.

    Args:
        property_id: The property ID in the concierge system
        user_url: Airbnb user profile URL  
        use_selenium: Whether to use Selenium for scraping

    Returns:
        Dictionary with property summary
    """
    integrator = AirbnbPropertyIntegrator(property_id, use_selenium=use_selenium)
    return integrator.generate_property_summary(user_url)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Airbnb Property Integration Tool (accepts Airbnb user profile URL or direct listing URL)')
    parser.add_argument('property_id', help='Property ID in concierge system')
    parser.add_argument('user_url', help='Airbnb user profile URL or direct listing URL (e.g., https://www.airbnb.com/rooms/123...)')
    parser.add_argument('--import', action='store_true', help='Import to knowledge base (default: preview only)')
    parser.add_argument('--selenium', action='store_true', help='Use Selenium for scraping')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if getattr(args, 'import'):
        print("Importing Airbnb properties to knowledge base...")
        result = import_airbnb_properties(args.property_id, args.user_url, args.selenium)
        
        print(f"\nImport Results:")
        print(f"  Property ID: {result.get('property_id')}")
        print(f"  Listings scraped: {result.get('listings_scraped', 0)}")
        print(f"  Knowledge items created: {result.get('knowledge_items_created', 0)}")
        print(f"  Knowledge items updated: {result.get('knowledge_items_updated', 0)}")
        print(f"  Success: {result.get('success', False)}")
        
        if result.get('errors'):
            print(f"  Errors:")
            for error in result['errors']:
                print(f"    - {error}")
    else:
        print("Previewing Airbnb properties (not importing to knowledge base)...")
        result = preview_airbnb_properties(args.property_id, args.user_url, args.selenium)
        
        if result.get('error'):
            print(f"Error: {result['error']}")
        else:
            print(f"\nProperty Preview:")
            print(f"  Properties found: {result.get('property_count', 0)}")
            print(f"  Total amenities: {result.get('total_amenities', 0)}")
            print(f"  Unique amenities: {result.get('unique_amenities_count', 0)}")
            print(f"  Average rating: {result.get('average_rating', 'N/A')}")
            print(f"  Total reviews: {result.get('total_reviews', 0)}")
            
            print(f"\nListing Details:")
            for i, listing in enumerate(result.get('listings_detail', []), 1):
                print(f"  {i}. {listing.get('title', 'Unknown')}")
                print(f"     Location: {listing.get('location', 'Unknown')}")
                print(f"     Amenities: {listing.get('amenities_count', 0)}")
                print(f"     Rating: {listing.get('rating', 'N/A')}")
                print(f"     Reviews: {listing.get('review_count', 0)}")
                print() 