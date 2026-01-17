from flask import Blueprint, request, jsonify, current_app
import os
import traceback
import logging
import requests

# Create Blueprint
search_bp = Blueprint('search', __name__)

@search_bp.route('', methods=['POST'])
def google_search():
    """
    API endpoint to perform a Google search.
    
    Expected JSON payload:
    {
        "query": "The search query"
    }
    
    Returns:
    {
        "success": true/false,
        "results": [list of search results]
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data provided"}), 400
        
        query = data.get('query')
        
        if not query:
            return jsonify({"success": False, "error": "No query provided"}), 400
        
        # Log the request
        current_app.logger.info(f"Google search request: '{query}'")
        
        # Get Google Search API key and CX from environment variables
        api_key = os.getenv('GOOGLE_SEARCH_API_KEY')
        cx = os.getenv('GOOGLE_SEARCH_CX')
        
        if not api_key or not cx:
            current_app.logger.error("Google Search API key or CX not configured")
            return jsonify({
                "success": False,
                "error": "Search service not configured",
                "results": []
            }), 500
        
        # Perform the search using Google Custom Search API
        search_url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cx}&q={query}"
        response = requests.get(search_url)
        
        if response.status_code != 200:
            current_app.logger.error(f"Google Search API error: {response.status_code} - {response.text}")
            return jsonify({
                "success": False,
                "error": f"Search API error: {response.status_code}",
                "results": []
            }), 500
        
        # Parse the response
        search_results = response.json()
        
        # Extract the relevant information
        results = []
        if 'items' in search_results:
            for item in search_results['items']:
                results.append({
                    'title': item.get('title', ''),
                    'link': item.get('link', ''),
                    'snippet': item.get('snippet', '')
                })
        
        # Log the results
        current_app.logger.info(f"Found {len(results)} search results for query: '{query}'")
        
        # Return the results
        return jsonify({
            "success": True,
            "results": results
        })
    
    except Exception as e:
        current_app.logger.error(f"Error in Google search API: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "results": []
        }), 500
