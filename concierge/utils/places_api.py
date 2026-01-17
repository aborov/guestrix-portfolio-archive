"""
Google Places API integration for accurate location-based recommendations.

This module provides functions to:
- Search for nearby places (restaurants, attractions, etc.)
- Get accurate distances and travel times
- Retrieve detailed place information (hours, ratings, reviews, price level)
- Calculate routes with different travel modes (walking, driving, transit, biking)
"""

import os
import logging
import requests
from typing import Dict, List, Optional, Tuple
from functools import lru_cache

logger = logging.getLogger(__name__)

# Google Places API configuration
GOOGLE_PLACES_API_KEY = os.getenv('GOOGLE_PLACES_API_KEY')
PLACES_API_BASE_URL = "https://maps.googleapis.com/maps/api/place"
DISTANCE_MATRIX_API_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
DIRECTIONS_API_URL = "https://maps.googleapis.com/maps/api/directions/json"

# Place type mappings for better categorization
PLACE_TYPE_MAP = {
    'restaurant': 'restaurant',
    'cafe': 'cafe',
    'coffee': 'cafe',
    'bar': 'bar',
    'attraction': 'tourist_attraction',
    'museum': 'museum',
    'park': 'park',
    'shopping': 'shopping_mall',
    'grocery': 'grocery_or_supermarket',
    'pharmacy': 'pharmacy',
    'hospital': 'hospital',
    'gas_station': 'gas_station',
    'atm': 'atm',
    'bank': 'bank'
}


def is_places_api_enabled() -> bool:
    """Check if Google Places API is configured."""
    return bool(GOOGLE_PLACES_API_KEY)


def get_coordinates_from_address(address: str) -> Optional[Tuple[float, float]]:
    """
    Convert an address to coordinates using Google Geocoding API.
    
    Args:
        address: The address to geocode
        
    Returns:
        Tuple of (latitude, longitude) or None if geocoding fails
    """
    if not GOOGLE_PLACES_API_KEY:
        logger.warning("Google Places API key not configured")
        return None
    
    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            'address': address,
            'key': GOOGLE_PLACES_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') == 'OK' and data.get('results'):
            location = data['results'][0]['geometry']['location']
            return (location['lat'], location['lng'])
        else:
            logger.warning(f"Geocoding failed for address: {address}, status: {data.get('status')}")
            return None
            
    except Exception as e:
        logger.error(f"Error geocoding address {address}: {e}")
        return None


def search_nearby_places(
    location: str,
    place_type: Optional[str] = None,
    keyword: Optional[str] = None,
    radius: int = 5000,
    min_rating: Optional[float] = None,
    price_level: Optional[int] = None,
    open_now: bool = False,
    max_results: int = 10
) -> Dict:
    """
    Search for nearby places using Google Places API.
    
    Args:
        location: Address or coordinates (lat,lng) of the property
        place_type: Type of place (restaurant, cafe, attraction, etc.)
        keyword: Additional keywords to refine search
        radius: Search radius in meters (default 5000m = ~3 miles)
        min_rating: Minimum rating (1-5)
        price_level: Price level (1-4, where 1 is cheapest)
        open_now: Only return places open now
        max_results: Maximum number of results to return
        
    Returns:
        Dictionary with search results and metadata
    """
    if not GOOGLE_PLACES_API_KEY:
        return {
            'success': False,
            'error': 'Google Places API not configured',
            'places': []
        }
    
    try:
        # Get coordinates from address if needed
        if ',' in location and location.replace(',', '').replace('.', '').replace('-', '').replace(' ', '').isdigit():
            # Already coordinates
            coordinates = location
        else:
            # Convert address to coordinates
            coords = get_coordinates_from_address(location)
            if not coords:
                return {
                    'success': False,
                    'error': f'Could not geocode location: {location}',
                    'places': []
                }
            coordinates = f"{coords[0]},{coords[1]}"
        
        # Build request parameters
        url = f"{PLACES_API_BASE_URL}/nearbysearch/json"
        params = {
            'location': coordinates,
            'radius': radius,
            'key': GOOGLE_PLACES_API_KEY
        }
        
        # Map place type to Google's format
        if place_type:
            mapped_type = PLACE_TYPE_MAP.get(place_type.lower(), place_type)
            params['type'] = mapped_type
        
        if keyword:
            params['keyword'] = keyword
        
        if open_now:
            params['opennow'] = 'true'
        
        # Make API request
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') != 'OK':
            logger.warning(f"Places API returned status: {data.get('status')}")
            if data.get('status') == 'ZERO_RESULTS':
                return {
                    'success': True,
                    'places': [],
                    'message': 'No places found matching your criteria'
                }
            return {
                'success': False,
                'error': f"Places API error: {data.get('status')}",
                'places': []
            }
        
        # Process results
        places = []
        for result in data.get('results', [])[:max_results]:
            # Filter by rating if specified
            if min_rating and result.get('rating', 0) < min_rating:
                continue
            
            # Filter by price level if specified
            if price_level and result.get('price_level', 0) != price_level:
                continue
            
            place_info = {
                'name': result.get('name'),
                'place_id': result.get('place_id'),
                'address': result.get('vicinity'),
                'rating': result.get('rating'),
                'user_ratings_total': result.get('user_ratings_total'),
                'price_level': result.get('price_level'),
                'types': result.get('types', []),
                'open_now': result.get('opening_hours', {}).get('open_now'),
                'location': result.get('geometry', {}).get('location')
            }
            places.append(place_info)
        
        return {
            'success': True,
            'places': places,
            'total_results': len(places)
        }
        
    except Exception as e:
        logger.error(f"Error searching nearby places: {e}")
        return {
            'success': False,
            'error': str(e),
            'places': []
        }


def get_place_details(place_id: str, fields: Optional[List[str]] = None) -> Dict:
    """
    Get detailed information about a specific place.
    
    Args:
        place_id: Google Places ID
        fields: Specific fields to retrieve (default: common useful fields)
        
    Returns:
        Dictionary with place details
    """
    if not GOOGLE_PLACES_API_KEY:
        return {
            'success': False,
            'error': 'Google Places API not configured'
        }
    
    try:
        # Default fields if not specified
        if not fields:
            fields = [
                'name', 'formatted_address', 'formatted_phone_number',
                'website', 'rating', 'user_ratings_total', 'price_level',
                'opening_hours', 'reviews', 'photos', 'types', 'geometry'
            ]
        
        url = f"{PLACES_API_BASE_URL}/details/json"
        params = {
            'place_id': place_id,
            'fields': ','.join(fields),
            'key': GOOGLE_PLACES_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') != 'OK':
            return {
                'success': False,
                'error': f"Places API error: {data.get('status')}"
            }
        
        result = data.get('result', {})
        
        # Format opening hours in a more readable way
        opening_hours = result.get('opening_hours', {})
        if opening_hours:
            hours_info = {
                'open_now': opening_hours.get('open_now'),
                'weekday_text': opening_hours.get('weekday_text', [])
            }
        else:
            hours_info = None
        
        # Get top reviews
        reviews = result.get('reviews', [])[:3]  # Top 3 reviews
        formatted_reviews = []
        for review in reviews:
            formatted_reviews.append({
                'author': review.get('author_name'),
                'rating': review.get('rating'),
                'text': review.get('text'),
                'time': review.get('relative_time_description')
            })
        
        place_details = {
            'success': True,
            'name': result.get('name'),
            'address': result.get('formatted_address'),
            'phone': result.get('formatted_phone_number'),
            'website': result.get('website'),
            'rating': result.get('rating'),
            'total_ratings': result.get('user_ratings_total'),
            'price_level': result.get('price_level'),
            'opening_hours': hours_info,
            'reviews': formatted_reviews,
            'types': result.get('types', []),
            'location': result.get('geometry', {}).get('location')
        }
        
        return place_details
        
    except Exception as e:
        logger.error(f"Error getting place details: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def calculate_distance_and_duration(
    origin: str,
    destination: str,
    mode: str = 'walking'
) -> Dict:
    """
    Calculate distance and travel time between two locations.
    
    Args:
        origin: Starting address or coordinates
        destination: Destination address or coordinates
        mode: Travel mode (walking, driving, transit, bicycling)
        
    Returns:
        Dictionary with distance and duration information
    """
    if not GOOGLE_PLACES_API_KEY:
        return {
            'success': False,
            'error': 'Google Places API not configured'
        }
    
    try:
        params = {
            'origins': origin,
            'destinations': destination,
            'mode': mode,
            'key': GOOGLE_PLACES_API_KEY
        }
        
        response = requests.get(DISTANCE_MATRIX_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') != 'OK':
            return {
                'success': False,
                'error': f"Distance Matrix API error: {data.get('status')}"
            }
        
        # Extract result
        element = data['rows'][0]['elements'][0]
        
        if element.get('status') != 'OK':
            return {
                'success': False,
                'error': f"No route found: {element.get('status')}"
            }
        
        return {
            'success': True,
            'distance': {
                'text': element['distance']['text'],
                'meters': element['distance']['value']
            },
            'duration': {
                'text': element['duration']['text'],
                'seconds': element['duration']['value']
            },
            'mode': mode
        }
        
    except Exception as e:
        logger.error(f"Error calculating distance: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def get_directions(
    origin: str,
    destination: str,
    mode: str = 'walking',
    alternatives: bool = False
) -> Dict:
    """
    Get detailed directions between two locations.
    
    Args:
        origin: Starting address or coordinates
        destination: Destination address or coordinates
        mode: Travel mode (walking, driving, transit, bicycling)
        alternatives: Whether to provide alternative routes
        
    Returns:
        Dictionary with route information
    """
    if not GOOGLE_PLACES_API_KEY:
        return {
            'success': False,
            'error': 'Google Places API not configured'
        }
    
    try:
        params = {
            'origin': origin,
            'destination': destination,
            'mode': mode,
            'alternatives': 'true' if alternatives else 'false',
            'key': GOOGLE_PLACES_API_KEY
        }
        
        response = requests.get(DIRECTIONS_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') != 'OK':
            return {
                'success': False,
                'error': f"Directions API error: {data.get('status')}"
            }
        
        routes = []
        for route in data.get('routes', []):
            leg = route['legs'][0]
            
            route_info = {
                'distance': leg['distance']['text'],
                'duration': leg['duration']['text'],
                'start_address': leg['start_address'],
                'end_address': leg['end_address'],
                'steps': []
            }
            
            # Get simplified step-by-step directions
            for step in leg['steps'][:10]:  # Limit to first 10 steps
                route_info['steps'].append({
                    'instruction': step['html_instructions'],
                    'distance': step['distance']['text'],
                    'duration': step['duration']['text']
                })
            
            routes.append(route_info)
        
        return {
            'success': True,
            'routes': routes,
            'mode': mode
        }
        
    except Exception as e:
        logger.error(f"Error getting directions: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def find_nearby_with_details(
    property_location: str,
    query: str,
    place_type: Optional[str] = None,
    max_results: int = 5,
    radius: int = 5000,
    travel_mode: str = 'walking'
) -> Dict:
    """
    Comprehensive search that combines nearby search with distance calculation and details.
    This is the main function to use for guest queries.
    
    Args:
        property_location: Address or coordinates of the property
        query: Search query (e.g., "Italian restaurants", "coffee shops")
        place_type: Optional place type filter
        max_results: Maximum number of results
        radius: Search radius in meters
        travel_mode: Mode of travel for distance calculation
        
    Returns:
        Dictionary with enriched place information including distances
    """
    if not GOOGLE_PLACES_API_KEY:
        return {
            'success': False,
            'error': 'Google Places API not configured. Please add GOOGLE_PLACES_API_KEY to environment variables.',
            'places': []
        }
    
    try:
        # Search for nearby places
        search_result = search_nearby_places(
            location=property_location,
            place_type=place_type,
            keyword=query,
            radius=radius,
            max_results=max_results * 2  # Get more results for filtering
        )
        
        if not search_result.get('success'):
            return search_result
        
        places = search_result.get('places', [])
        if not places:
            return {
                'success': True,
                'places': [],
                'message': f'No places found matching "{query}" within {radius}m'
            }
        
        # Enrich each place with distance and duration
        enriched_places = []
        for place in places[:max_results]:
            # Calculate distance and duration
            if place.get('location'):
                destination = f"{place['location']['lat']},{place['location']['lng']}"
                distance_info = calculate_distance_and_duration(
                    origin=property_location,
                    destination=destination,
                    mode=travel_mode
                )
                
                if distance_info.get('success'):
                    place['distance'] = distance_info['distance']['text']
                    place['duration'] = distance_info['duration']['text']
                    place['distance_meters'] = distance_info['distance']['meters']
                    place['walkable'] = distance_info['distance']['meters'] <= 1600  # ~1 mile
            
            enriched_places.append(place)
        
        # Sort by distance
        enriched_places.sort(key=lambda x: x.get('distance_meters', float('inf')))
        
        return {
            'success': True,
            'places': enriched_places,
            'total_results': len(enriched_places),
            'property_location': property_location,
            'search_query': query,
            'travel_mode': travel_mode
        }
        
    except Exception as e:
        logger.error(f"Error in find_nearby_with_details: {e}")
        return {
            'success': False,
            'error': str(e),
            'places': []
        }


# Price level descriptions
PRICE_LEVEL_DESC = {
    1: "Inexpensive",
    2: "Moderate", 
    3: "Expensive",
    4: "Very Expensive"
}


def format_place_for_response(place: Dict) -> str:
    """
    Format a place dictionary into a readable text response.
    
    Args:
        place: Place dictionary from API results
        
    Returns:
        Formatted string describing the place
    """
    parts = [f"**{place.get('name')}**"]
    
    if place.get('rating'):
        stars = '⭐' * int(place['rating'])
        parts.append(f"{stars} {place['rating']}/5")
        if place.get('user_ratings_total'):
            parts.append(f"({place['user_ratings_total']} reviews)")
    
    if place.get('price_level'):
        price_desc = PRICE_LEVEL_DESC.get(place['price_level'], '')
        if price_desc:
            parts.append(f"Price: {price_desc}")
    
    if place.get('distance'):
        parts.append(f"📍 {place['distance']} away")
        if place.get('duration'):
            parts.append(f"({place['duration']} {place.get('travel_mode', 'walk')})")
    
    if place.get('open_now') is not None:
        status = "🟢 Open now" if place['open_now'] else "🔴 Closed"
        parts.append(status)
    
    if place.get('address'):
        parts.append(f"Address: {place['address']}")
    
    return ' • '.join(parts)


