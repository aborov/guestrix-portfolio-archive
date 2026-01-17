"""
AI helper functions for Concierge application using Firestore for RAG.
This module provides functions for retrieving relevant context from Firestore
and generating responses using Gemini.
"""

import os
import logging
import time
import traceback
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timezone
import json

# Import Firestore client
from concierge.utils.firestore_client import (
    initialize_firebase, get_firestore_client, find_similar_knowledge_items,
    generate_embedding, configure_gemini
)

# Import Gemini
try:
    import google.generativeai as genai
except ImportError:
    genai = None
    logging.warning("google.generativeai module not imported - AI functions will fail!")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
MAX_RESULTS = 10
SIMILARITY_THRESHOLD = 0.7  # Minimum similarity score (0-1) to include in results

# Global variables
firestore_db = None
gen_ai_client = None

# Simple in-memory cache for RAG results
rag_cache = {}

def get_relevant_context(query_text: str, property_id: str, limit: int = MAX_RESULTS, threshold: float = SIMILARITY_THRESHOLD) -> Dict:
    """
    Retrieve relevant context from Firestore based on query text and property ID.

    Args:
        query_text: The user's query or utterance
        property_id: The ID of the property to filter by
        limit: Maximum number of results to return
        threshold: Similarity threshold (0-1)

    Returns:
        dict: {
            'found': bool,
            'context': str,
            'items': list of dict with relevant items
        }
    """
    results = {
        'found': False,
        'context': "",
        'items': []
    }

    # Check cache first
    cache_key = f"{property_id}:{query_text}"
    if cache_key in rag_cache:
        logger.info(f"Using cached RAG results for query: {query_text[:50]}...")
        return rag_cache[cache_key]

    try:
        # Find similar knowledge items in Firestore
        similar_items = find_similar_knowledge_items(query_text, property_id, limit)

        if not similar_items:
            logger.info(f"No relevant context found for property: {property_id}")
            # Cache the empty results too to avoid redundant queries
            rag_cache[cache_key] = results
            return results

        # Process results
        context_parts = []
        items = []

        for item in similar_items:
            # Skip items with low similarity
            similarity = item.get('similarity', 0)
            if similarity < threshold:
                continue

            # Create item dictionary
            item_dict = {
                'id': item.get('id', 'unknown'),
                'text': item.get('content', ''),
                'similarity': similarity
            }
            items.append(item_dict)
            context_parts.append(item.get('content', ''))

        # If no items passed the threshold, return empty results
        if not items:
            logger.info(f"No items passed the similarity threshold ({threshold})")
            rag_cache[cache_key] = results
            return results

        # Join context parts
        context = "\n\n".join(context_parts)

        results['found'] = True
        results['context'] = context
        results['items'] = items

        # Cache the successful results
        rag_cache[cache_key] = results

        return results

    except Exception as e:
        logger.error(f"Error retrieving relevant context: {e}")
        traceback.print_exc()
        return results

def create_base_prompt(property_context: Dict) -> str:
    """
    Create a base prompt with property information.

    Args:
        property_context: Dictionary containing property information

    Returns:
        str: The base prompt
    """
    if not property_context:
        return "You are Guestrix, an AI assistant for vacation rental guests."

    property_name = property_context.get('name', 'this property')
    host_name = property_context.get('hostName', 'the host')

    prompt = f"""You are Guestrix, an AI assistant for guests staying at {property_name}.
Your role is to provide helpful, accurate information about the property and assist guests during their stay.

PROPERTY INFORMATION:
- Property Name: {property_name}
- Host: {host_name}
"""

    # Add address if available
    if 'address' in property_context and property_context['address']:
        prompt += f"- Address: {property_context['address']}\n"

    # Add description if available
    if 'description' in property_context and property_context['description']:
        prompt += f"\nPROPERTY DESCRIPTION:\n{property_context['description']}\n"

    prompt += "\nGUIDELINES:\n"
    prompt += "- Be friendly, helpful, and concise in your responses.\n"
    prompt += "- If you don't know the answer to a question, politely say so and suggest contacting the host.\n"
    prompt += "- Never make up information about the property.\n"
    prompt += "- Prioritize information from the property knowledge base over general knowledge.\n"

    return prompt

def format_prompt_with_rag(user_query: str, property_context: Dict, rag_results: Dict, conversation_history: List = None) -> str:
    """
    Format a prompt with RAG results and conversation history.

    Args:
        user_query: The user's query or message
        property_context: Dictionary containing property information
        rag_results: Results from get_relevant_context
        conversation_history: Previous conversation messages

    Returns:
        str: The formatted prompt
    """
    # Start with a base prompt with property information
    prompt_parts = [create_base_prompt(property_context)]

    # Add RAG context if available
    if rag_results and rag_results.get('found', False) and rag_results.get('items', []):
        rag_context = "PROPERTY KNOWLEDGE:\n\n"
        for item in rag_results.get('items', []):
            text = item.get('text', '').strip()
            # Skip empty items
            if not text:
                continue
            rag_context += f"{text}\n\n"
        prompt_parts.append(rag_context)
    else:
        prompt_parts.append("I don't have specific information about this property. If I can't answer a question, I'll let you know.")

    # Add conversation history if available
    if conversation_history and len(conversation_history) > 0:
        history_text = "CONVERSATION HISTORY:\n"
        for entry in conversation_history:
            role = "Guest" if entry.get('role') == 'user' else "Assistant"
            history_text += f"{role}: {entry.get('text', '')}\n\n"
        prompt_parts.append(history_text)

    # Add user query
    prompt_parts.append(f"GUEST QUERY: {user_query}")

    # Return the formatted prompt
    return "\n\n".join(prompt_parts)

def process_query_with_rag(user_query: str, property_id: str, property_context: Dict = None, conversation_history: List = None) -> Dict:
    """
    Process a user query with RAG and return a response from Gemini.

    Args:
        user_query: The user's query or message
        property_id: The property ID
        property_context: Context about the property
        conversation_history: Previous conversation messages

    Returns:
        dict: {
            'response': str,
            'has_context': bool,
            'context_used': list of context items used (if any)
        }
    """
    result = {
        'response': '',
        'has_context': False,
        'context_used': []
    }

    try:
        # Configure Gemini if not already configured
        if not genai:
            logger.error("Gemini API not available")
            result['response'] = "I'm sorry, I'm having trouble connecting to my knowledge base. Please try again later."
            return result

        if not configure_gemini():
            logger.error("Failed to configure Gemini")
            result['response'] = "I'm sorry, I'm having trouble connecting to my knowledge base. Please try again later."
            return result

        # Get relevant context from Firestore
        logger.info(f"Fetching context from Firestore for property_id: {property_id}")
        rag_results = get_relevant_context(user_query, property_id)

        # Log results of context lookup
        if rag_results.get('found'):
            logger.info(f"Found {len(rag_results.get('items', []))} relevant items in knowledge base")
            for idx, item in enumerate(rag_results.get('items', [])):
                logger.info(f"Context item {idx+1}: similarity={item.get('similarity', 0):.4f}, text='{item.get('text', '')[:100]}...'")
        else:
            logger.warning(f"No relevant context found in knowledge base for property_id: {property_id}")

        # Format prompt with RAG context and conversation history
        prompt = format_prompt_with_rag(
            user_query=user_query,
            property_context=property_context,
            rag_results=rag_results,
            conversation_history=conversation_history
        )

        # Generate response with Gemini
        try:
            # Configure Gemini model (without tools for now)
            generation_config = {
                "temperature": 0.2,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 1024,
            }

            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            ]

            # Initialize Gemini model (without tools to avoid API issues)
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash-lite",
                generation_config=generation_config,
                safety_settings=safety_settings
            )

            # Generate response
            response = model.generate_content(prompt)

            # Extract response text
            if hasattr(response, 'text'):
                response_text = response.text
            else:
                response_text = str(response)

            # Set result values
            result['response'] = response_text
            result['has_context'] = rag_results.get('found', False)
            result['context_used'] = rag_results.get('items', [])

            return result

        except Exception as e:
            logger.error(f"Error generating response with Gemini: {e}")
            traceback.print_exc()
            result['response'] = "I'm sorry, I encountered an error while processing your request. Please try again later."
            return result

    except Exception as e:
        logger.error(f"Error in process_query_with_rag: {e}")
        traceback.print_exc()
        result['response'] = "I'm sorry, I encountered an error while processing your request. Please try again later."
        return result

def process_query_with_tools(user_query: str, property_id: str, property_context: Dict = None, conversation_history: List = None) -> Dict:
    """
    Process a user query with RAG and tools, returning a response from Gemini.
    This version supports function calling with tools.

    Args:
        user_query: The user's query or message
        property_id: The property ID
        property_context: Context about the property
        conversation_history: Previous conversation messages

    Returns:
        dict: {
            'response': str,
            'has_context': bool,
            'context_used': list of context items used (if any),
            'tool_calls': list of tool calls made (if any)
        }
    """
    result = {
        'response': '',
        'has_context': False,
        'context_used': [],
        'tool_calls': []
    }

    try:
        # Configure Gemini if not already configured
        if not genai:
            logger.error("Gemini API not available")
            result['response'] = "I'm sorry, I'm having trouble connecting to my knowledge base. Please try again later."
            return result

        if not configure_gemini():
            logger.error("Failed to configure Gemini")
            result['response'] = "I'm sorry, I'm having trouble connecting to my knowledge base. Please try again later."
            return result

        # Get relevant context from Firestore
        logger.info(f"Fetching context from Firestore for property_id: {property_id}")
        rag_results = get_relevant_context(user_query, property_id)

        # Format prompt with RAG context and conversation history
        prompt = format_prompt_with_rag(
            user_query=user_query,
            property_context=property_context,
            rag_results=rag_results,
            conversation_history=conversation_history
        )

        # Define RAG tool
        rag_tool = {
            "name": "retrievePropertyInfo",
            "description": "Retrieve specific information about the property from the knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The specific information to retrieve about the property"
                    }
                },
                "required": ["query"]
            }
        }

        # Define Google Search tool
        search_tool = {
            "name": "googleSearch",
            "description": "Search Google for information about places, events, facts, or anything else that might require up-to-date or general knowledge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query"
                    }
                },
                "required": ["query"]
            }
        }

        # Configure Gemini model
        generation_config = {
            "temperature": 0.2,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 1024,
        }

        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]

        # Use sequential approach to avoid "Tool use with function calling is unsupported" error
        # First try with function calling only (get_current_time and search_nearby_places)
        
        # Define get_current_time function
        from concierge.utils.ai_helpers import get_current_time
        from concierge.utils.places_api import find_nearby_with_details, is_places_api_enabled
        
        get_current_time_declaration = genai.types.FunctionDeclaration(
            name="get_current_time",
            description="Get the current date and time for the property location. Use this when the guest asks about the current time, date, dining recommendations, business hours, or any time-sensitive information. Always call this function when discussing restaurants, activities, or services that depend on current time of day.",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
        
        # Define search_nearby_places function
        search_nearby_places_declaration = genai.types.FunctionDeclaration(
            name="search_nearby_places",
            description="Search for nearby places like restaurants, cafes, attractions, shopping, etc. with accurate distances, travel times, ratings, hours, and price levels. Use this INSTEAD of google_search for ANY location-based queries about places around the property. This provides structured data with walking/driving distances, ratings, open hours, and more accurate information than web search.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for (e.g., 'Italian restaurants', 'coffee shops', 'tourist attractions')"
                    },
                    "place_type": {
                        "type": "string",
                        "description": "Optional category: restaurant, cafe, bar, attraction, museum, park, shopping, grocery, pharmacy, hospital, gas_station, atm, bank",
                        "enum": ["restaurant", "cafe", "bar", "attraction", "museum", "park", "shopping", "grocery", "pharmacy", "hospital", "gas_station", "atm", "bank"]
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5, max: 10)"
                    },
                    "radius": {
                        "type": "integer",
                        "description": "Search radius in meters (default: 5000m ≈ 3 miles)"
                    },
                    "travel_mode": {
                        "type": "string",
                        "description": "Travel mode for distance calculation: walking, driving, transit, or bicycling",
                        "enum": ["walking", "driving", "transit", "bicycling"]
                    }
                },
                "required": ["query"]
            }
        )
        
        # Try function calling first
        # Include Places API if enabled
        function_declarations = [get_current_time_declaration]
        if is_places_api_enabled():
            function_declarations.append(search_nearby_places_declaration)
            logger.info("[FIRESTORE AI] Places API enabled - including search_nearby_places tool")
        
        def make_function_call():
            return genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                generation_config=generation_config,
                safety_settings=safety_settings
            ).generate_content(
                prompt,
                tools=[genai.types.Tool(function_declarations=function_declarations)]
            )

        response = make_function_call()
        tool_calls = []
        
        # Handle potential function calls (get_current_time and search_nearby_places)
        function_called = False
        if response and hasattr(response, 'candidates') and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            function_called = True
                            function_call = part.function_call
                            
                            if function_call.name == "get_current_time":
                                logger.info("[FIRESTORE AI] Function call detected: get_current_time")
                                
                                # Call the actual function
                                time_result = get_current_time(property_context)
                                logger.info(f"[FIRESTORE AI] get_current_time result: {time_result}")
                                
                                # Record the tool call
                                tool_calls.append({
                                    'name': 'get_current_time',
                                    'result': time_result
                                })
                                
                                # Create follow-up prompt with the time information
                                time_info = f"Current time information: {time_result['full_datetime']}"
                                follow_up_prompt = f"{prompt}\n\n{time_info}\n\nPlease provide your response using this current time information."
                                
                                # Generate final response with time context
                                response = genai.GenerativeModel(
                                    model_name="gemini-2.5-flash",
                                    generation_config=generation_config,
                                    safety_settings=safety_settings
                                ).generate_content(follow_up_prompt)
                                break
                            
                            elif function_call.name == "search_nearby_places":
                                logger.info("[FIRESTORE AI] Function call detected: search_nearby_places")
                                
                                # Extract arguments
                                args = {}
                                if hasattr(function_call, 'args') and function_call.args:
                                    args = dict(function_call.args)
                                
                                logger.info(f"[FIRESTORE AI] search_nearby_places args: {args}")
                                
                                # Get property location
                                property_location = None
                                if property_context:
                                    # Try to build full address
                                    address_parts = []
                                    for field in ['address', 'city', 'state', 'country']:
                                        if field in property_context and property_context[field]:
                                            address_parts.append(property_context[field])
                                    if address_parts:
                                        property_location = ', '.join(address_parts)
                                
                                if not property_location:
                                    logger.warning("[FIRESTORE AI] No property location available for Places API search")
                                    follow_up_prompt = f"{prompt}\n\nI couldn't determine the property location to search nearby places. Please provide a response without location search."
                                    response = genai.GenerativeModel(
                                        model_name="gemini-2.5-flash",
                                        generation_config=generation_config,
                                        safety_settings=safety_settings
                                    ).generate_content(follow_up_prompt)
                                    break
                                
                                # Call Places API
                                places_result = find_nearby_with_details(
                                    property_location=property_location,
                                    query=args.get('query', ''),
                                    place_type=args.get('place_type'),
                                    max_results=args.get('max_results', 5),
                                    radius=args.get('radius', 5000),
                                    travel_mode=args.get('travel_mode', 'walking')
                                )
                                
                                logger.info(f"[FIRESTORE AI] Places API returned {places_result.get('total_results', 0)} results")
                                
                                # Record the tool call
                                tool_calls.append({
                                    'name': 'search_nearby_places',
                                    'args': args,
                                    'result': places_result
                                })
                                
                                # Format places info for the model
                                if places_result.get('success') and places_result.get('places'):
                                    from concierge.utils.places_api import format_place_for_response
                                    places_info = f"Found {len(places_result['places'])} nearby places:\n\n"
                                    for i, place in enumerate(places_result['places'], 1):
                                        places_info += f"{i}. {format_place_for_response(place)}\n"
                                    
                                    follow_up_prompt = f"{prompt}\n\nNearby places search results:\n{places_info}\n\nPlease provide a helpful response based on these results. Present 1-2 top recommendations and ask if the guest would like more options."
                                else:
                                    error_msg = places_result.get('error', 'No results found')
                                    follow_up_prompt = f"{prompt}\n\nPlaces search returned no results: {error_msg}. Please provide an alternative response or suggestion."
                                
                                # Generate final response with places context
                                response = genai.GenerativeModel(
                                    model_name="gemini-2.5-flash",
                                    generation_config=generation_config,
                                    safety_settings=safety_settings
                                ).generate_content(follow_up_prompt)
                                break

        # If no function was called and no text response, try Google Search
        if not function_called and (not response or not hasattr(response, 'text') or not response.text.strip()):
            logger.info("[FIRESTORE AI] No function call made, trying Google Search fallback")
            
            def make_search_call():
                return genai.GenerativeModel(
                    model_name="gemini-2.5-flash",
                    generation_config=generation_config,
                    safety_settings=safety_settings
                ).generate_content(
                    prompt,
                    tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())]
                )
            
            response = make_search_call()

        # Extract final response text
        if hasattr(response, 'text'):
            response_text = response.text
        else:
            response_text = str(response)

        # Set result values
        result['response'] = response_text
        result['has_context'] = rag_results.get('found', False)
        result['context_used'] = rag_results.get('items', [])
        result['tool_calls'] = tool_calls

        return result

    except Exception as e:
        logger.error(f"Error in process_query_with_tools: {e}")
        traceback.print_exc()
        result['response'] = "I'm sorry, I encountered an error while processing your request. Please try again later."
        return result
