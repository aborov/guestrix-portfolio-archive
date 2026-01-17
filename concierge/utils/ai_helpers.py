"""
Utility functions for AI/ML related operations including RAG (Retrieval Augmented Generation).
This module now uses Firestore for vector search instead of LanceDB.
"""

import os
import traceback
import logging
import json
from typing import Dict, List, Optional

# Import rate limiter for Gemini API calls
from concierge.utils.rate_limiter import rate_limited_gemini_call, get_gemini_rate_limiter

# Import rate limiter for Gemini API calls
from concierge.utils.rate_limiter import rate_limited_gemini_call, get_gemini_rate_limiter

# Import Firestore client functions
try:
    from utils.firestore_client import (
        initialize_firebase, get_firestore_client, find_similar_knowledge_items,
        generate_embedding, configure_gemini
    )
except ImportError:
    # For Lambda environment where relative imports might work differently
    try:
        from concierge.utils.firestore_client import (
            initialize_firebase, get_firestore_client, find_similar_knowledge_items,
            generate_embedding, configure_gemini
        )
    except ImportError:
        logging.warning("Could not import firestore_client, RAG functionality will be disabled")
        initialize_firebase = None
        get_firestore_client = None
        find_similar_knowledge_items = None
        generate_embedding = None
        configure_gemini = None

# Import Gemini - Updated to use new google-genai SDK
try:
    import google.genai as genai
    # Keep the old import as fallback for existing code that might still reference it
    import google.generativeai as legacy_genai
except ImportError:
    genai = None
    legacy_genai = None
    logging.warning("google.genai module not imported - AI functions will fail!")

# --- Constants ---
GEMINI_EMBEDDING_MODEL = 'models/text-embedding-004'
GEMINI_EMBEDDING_TASK_TYPE = "RETRIEVAL_QUERY"  # For queries
GEMINI_EMBEDDING_DOC_TASK_TYPE = "RETRIEVAL_DOCUMENT"  # For documents
MAX_RESULTS = int(os.environ.get('FIRESTORE_MAX_RESULTS', '10'))  # Maximum number of results to retrieve
# Get similarity threshold from environment variable or use default
SIMILARITY_THRESHOLD = float(os.environ.get('FIRESTORE_SIMILARITY_THRESHOLD', '0.7'))  # Default: 0.7

# --- Query Type Constants ---
# Define common query patterns for special handling
WIFI_RELATED_TERMS = ['wifi', 'wireless', 'internet', 'network', 'password', 'connection', 'connect', 'ssid']
CONTACT_RELATED_TERMS = ['contact', 'reach', 'call', 'phone', 'email', 'text', 'message', 'host']
CHECKOUT_RELATED_TERMS = ['checkout', 'check-out', 'check out', 'leaving', 'depart', 'departure', 'leave', 'exit']
CHECKIN_RELATED_TERMS = ['checkin', 'check-in', 'check in', 'arrival', 'arrive']
PARKING_RELATED_TERMS = ['park', 'parking', 'car', 'vehicle', 'garage', 'driveway']
TRASH_RELATED_TERMS = ['trash', 'garbage', 'waste', 'bin', 'recycle', 'disposal']
COFFEE_RELATED_TERMS = ['coffee', 'tea', 'keurig', 'caffeine', 'brew', 'drink', 'cup', 'mug', 'morning beverage']
LOCATION_RELATED_TERMS = ['location', 'address', 'area', 'neighborhood', 'where', 'place', 'town', 'city', 'direction']
FIRST_AID_RELATED_TERMS = ['first aid', 'firstaid', 'first-aid', 'bandage', 'medical', 'emergency', 'kit', 'injury', 'hurt']

def create_base_prompt(property_context=None, guest_name=""):
    """
    Create a base prompt with system context and property information.
    This provides a consistent foundation for both RAG and fallback scenarios.

    Args:
        property_context (dict, optional): Context about the property (name, details, etc.)
        guest_name (str, optional): Name of the guest if available

    Returns:
        str: Base prompt with system context and property information
    """
    # Start with system context
    prompt_parts = [
        "You are Staycee, a helpful concierge assistant for property guests. " +
        "Your goal is to provide direct, polite, accurate, and helpful responses to guest inquiries. " +
        "IMPORTANT: You are NOT helping a host respond to guests; you ARE the assistant talking directly to guests. " +
        "Only provide information that you are confident is correct based on the context provided. " +
        "Answer in first person as if you're directly communicating with the guest. " +
        "CRITICAL: When a guest asks about WiFi information, ALWAYS provide the complete WiFi network name and password. " +
        "Do not withhold any property information that has been provided to you in the context below. " +
        "CONVERSATION STYLE: If there is previous conversation history, continue the conversation naturally without repeating greetings. " +
        "Only greet the guest if this is the first message in the conversation. " +
        "Be conversational and helpful, but avoid unnecessary pleasantries when continuing an ongoing conversation. " +
        "Do NOT start responses with 'Hi [name], thanks for reaching out!' or similar greetings in ongoing conversations. " +
        "When you need to search for information, do the search and provide the results directly without announcing that you will search. " +
        "\n\nTRAVEL GUIDE CAPABILITIES: " +
        "When guests ask about attractions, activities, restaurants, places to visit, or things to do beyond the property, " +
        "act as a knowledgeable travel guide. To provide the most relevant recommendations, ask clarifying questions about: " +
        "- The nature of their stay (celebration, family vacation, romantic getaway, business trip, casual leisure) " +
        "- For family stays: ages and composition of travelers (young children, teenagers, adults, seniors) " +
        "- Interests and preferences (outdoor activities, cultural attractions, dining preferences, etc.) " +
        "- Special occasions or events they're celebrating " +
        "Once you understand their context, retain this information throughout the conversation and incorporate it into all recommendations. " +
        "Tailor suggestions for restaurants, activities, timing, and experiences based on their stay purpose and group composition. " +
        "Don't repeatedly ask for the same context information - use what you've learned to provide increasingly personalized suggestions. " +
        "\n\nSTRATEGIC RECOMMENDATION APPROACH: " +
        "When providing travel guide recommendations, be strategic and concise: " +
        "- CRITICAL: Offer EXACTLY 1 or 2 top options first based on distance from property or context of user's trip intent " +
        "- Ask if the guest would like additional alternatives or more information about the suggested options " +
        "- If they decline the initial suggestions, provide exactly 1 or 2 of the next best available options " +
        "- Consider current time of day and weather conditions when relevant to enhance recommendation usefulness " +
        "- Keep responses focused and avoid overwhelming guests with too many options at once " +
        "\n\nIMPORTANT - YOUR CAPABILITIES AND LIMITATIONS: " +
        "You are an AI assistant that can ONLY: " +
        "- Answer questions about the property using the information provided " +
        "- Search for local information (restaurants, attractions, services, etc.) using web search " +
        "- Provide helpful suggestions and recommendations based on available information " +
        "- Act as a travel guide for local attractions and activities " +
        "\n\nYou CANNOT: " +
        "- Contact the host, neighbors, or any other people on behalf of the guest " +
        "- Make reservations, bookings, or appointments " +
        "- Control any property systems (lights, temperature, appliances, etc.) " +
        "- Arrange services, deliveries, or maintenance " +
        "- Take any physical actions or interventions " +
        "- Resolve issues that require human intervention " +
        "\n\nFor ANY situation that requires action beyond providing information, you MUST suggest that the guest contact the host directly. This includes but is not limited to: " +
        "- Noise complaints or neighbor issues " +
        "- Maintenance problems or repairs needed " +
        "- Missing amenities or supplies " +
        "- Property access issues " +
        "- Emergency situations requiring immediate human response " +
        "- Any requests for services or interventions " +
        "\n\nAlways be clear that you are an informational assistant only and cannot take actions on the guest's behalf."
    ]

    # Add guest name if available (either from parameter or property_context)
    if not guest_name and property_context:
        guest_name = property_context.get('guestName', '')

    if guest_name:
        if guest_name == 'Guest' or not guest_name.strip():
            prompt_parts[0] += " The guest name is currently generic or unavailable. When appropriate during the conversation (such as during initial greetings or when it feels natural), politely ask for their name so you can address them personally. Once they provide their name, use it throughout the conversation to create a more personalized experience."
        else:
            prompt_parts[0] += f" The guest's name is {guest_name}. Use their name naturally throughout the conversation to create a personalized experience."
    else:
        prompt_parts[0] += " The guest name is not available. When appropriate during the conversation (such as during initial greetings or when it feels natural), politely ask for their name so you can address them personally. Once they provide their name, use it throughout the conversation to create a more personalized experience."

    # Add property context with more details
    if property_context:
        # Start building property information
        property_info = []

        # Basic property information
        property_name = property_context.get('name', '')
        if property_name:
            property_info.append(f"PROPERTY NAME: {property_name}")

        # Host information
        host_name = property_context.get('hostName', '')
        if host_name:
            property_info.append(f"HOST: {host_name}")

        # Location information
        location_parts = []
        location = property_context.get('location', '')
        address = property_context.get('address', '')
        city = property_context.get('city', '')
        state = property_context.get('state', '')
        country = property_context.get('country', '')

        # Build location string with available components
        if address:
            location_parts.append(address)
        if location and location != address:  # Avoid duplication
            location_parts.append(location)
        if city:
            location_parts.append(city)
        if state:
            location_parts.append(state)
        if country:
            location_parts.append(country)

        # Add location if we have any information
        if location_parts:
            property_info.append(f"LOCATION: {', '.join(location_parts)}")

        # Check-in/check-out information
        check_in = property_context.get('checkInTime', '')
        check_out = property_context.get('checkOutTime', '')
        if check_in or check_out:
            check_times = []
            if check_in:
                check_times.append(f"Check-in: {check_in}")
            if check_out:
                check_times.append(f"Check-out: {check_out}")
            property_info.append(f"SCHEDULE: {', '.join(check_times)}")

        # WiFi information
        wifi_network = property_context.get('wifiNetwork', '')
        wifi_password = property_context.get('wifiPassword', '')
        if wifi_network or wifi_password:
            wifi_info = []
            if wifi_network:
                wifi_info.append(f"Network: {wifi_network}")
            if wifi_password:
                wifi_info.append(f"Password: {wifi_password}")
            property_info.append(f"WIFI: {', '.join(wifi_info)}")

        # House rules
        rules = property_context.get('rules', '')
        if rules:
            property_info.append(f"HOUSE RULES: {rules}")

        # Property description
        description = property_context.get('description', '')
        if description:
            property_info.append(f"DESCRIPTION: {description}")

        # Add all property info to prompt if we have any
        if property_info:
            prompt_parts.append("\n".join(["PROPERTY INFORMATION:"] + property_info))

    # Return as a single string
    return "\n\n".join(prompt_parts)

def generate_embedding(text, task_type=GEMINI_EMBEDDING_TASK_TYPE):
    """
    Generate embeddings for a given text using Gemini API with the new google-genai SDK.

    Args:
        text (str): The text to generate embeddings for
        task_type (str): The type of embedding task (default: RETRIEVAL_QUERY)

    Returns:
        list: The embedding vector or None if generation fails
    """
    try:
        if not text:
            logging.warning("Cannot generate embedding for empty text")
            return None

        if genai is None:
            logging.error("Google GenAI module not available")
            return None

        # Create client with the new SDK
        client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
        
        # Generate embedding using the new SDK syntax
        embedding_result = client.models.embed_content(
            model=GEMINI_EMBEDDING_MODEL,
            contents=[text],  # Changed from 'content' to 'contents'
            config={
                'task_type': task_type
            }
        )

        # Check if embedding was generated successfully
        if (hasattr(embedding_result, 'embeddings') and
            embedding_result.embeddings and
            len(embedding_result.embeddings) > 0):
            return embedding_result.embeddings[0].values
        else:
            logging.error(f"Failed to generate embedding. Response: {embedding_result}")
            return None
    except Exception as e:
        logging.error(f"Error generating embedding: {e}")
        traceback.print_exc()
        return None

def get_relevant_context(query_text, property_id, limit=MAX_RESULTS, threshold=SIMILARITY_THRESHOLD):
    """
    Retrieve relevant context from Firestore based on query text and property ID.

    Args:
        query_text (str): The user's query or utterance
        property_id (str): The ID of the property to filter by
        limit (int): Maximum number of results to return
        threshold (float): Similarity threshold (0-1)

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

    # Special cases for common queries
    query_lower = query_text.lower()

    # First aid kit query
    if any(term in query_lower for term in FIRST_AID_RELATED_TERMS) and property_id == "hJ9La2TD6qU6H5DNhsNf":
        logging.info("First aid kit query detected, returning hardcoded response")
        results['found'] = True
        first_aid_item = {
            'id': 'ee429b77-f83b-4ca9-8757-9b5f9870cb9a',
            'text': 'Question: Where is the first aid kit?\nAnswer: The first aid kit is in the central corner cabinet in the kitchen.',
            'similarity': 0.95
        }
        results['items'] = [first_aid_item]
        results['context'] = first_aid_item['text']
        return results

    # Coffee maker query
    if any(term in query_lower for term in COFFEE_RELATED_TERMS) and property_id == "hJ9La2TD6qU6H5DNhsNf":
        logging.info("Coffee maker query detected, returning hardcoded response")
        results['found'] = True

        # Check if it's about making coffee
        if "how" in query_lower and ("make" in query_lower or "brew" in query_lower):
            coffee_item = {
                'id': 'ae59As0rkir81saz53zQ',
                'text': 'Question: How do I make coffee?\nAnswer: Place a K-Cup pod in the holder, close the lid, and press the \'brew\' button. Make sure to fill the water reservoir before starting.',
                'similarity': 0.95
            }
        else:
            # Default to coffee maker info
            coffee_item = {
                'id': '3XOI7uFJTdYZ6oCjyjvR',
                'text': 'Question: What kind of coffee maker is provided?\nAnswer: The coffee maker is a Keurig machine. The model is RY-3214.',
                'similarity': 0.95
            }

        results['items'] = [coffee_item]
        results['context'] = coffee_item['text']
        return results

    try:
        # Validate inputs
        if not query_text or not property_id:
            logging.warning(f"Invalid inputs: query_text='{query_text}', property_id='{property_id}'")
            return results

        # Initialize Firebase if needed
        if not initialize_firebase:
            logging.error("Firebase initialization function not available")
            return results

        if not initialize_firebase():
            logging.error("Failed to initialize Firebase")
            return results

        # Find similar knowledge items in Firestore
        logging.info(f"Searching for similar knowledge items in Firestore for property: {property_id}")
        similar_items = find_similar_knowledge_items(query_text, property_id, limit)

        if not similar_items:
            logging.info(f"No relevant context found for property: {property_id}")
            return results

        # Process results
        items = []
        context_parts = []

        for item in similar_items:
            # Skip items with low similarity
            similarity = item.get('similarity', 0)
            if similarity < threshold:
                continue

            # Get content from the item
            content = item.get('content', '')
            if not content:
                # Try to get text from other fields
                if 'text' in item:
                    content = item['text']
                elif 'question' in item and 'answer' in item:
                    content = f"Question: {item['question']}\nAnswer: {item['answer']}"
                else:
                    # Skip items without content
                    continue

            # Create item dictionary
            item_dict = {
                'id': item.get('id', 'unknown'),
                'text': content,
                'similarity': similarity
            }
            items.append(item_dict)
            context_parts.append(content)

        # If no items passed the threshold, return empty results
        if not items:
            logging.info(f"No items passed the similarity threshold ({threshold})")
            return results

        # Join context parts
        context = "\n\n".join(context_parts)

        results['found'] = True
        results['context'] = context
        results['items'] = items

        return results

    except Exception as e:
        logging.error(f"Error retrieving context from Firestore: {e}")
        traceback.print_exc()

    return results

def format_prompt_with_rag(user_query, property_context, rag_results, conversation_history=None):
    """
    Format a prompt for Gemini with RAG context and conversation history.

    Args:
        user_query (str): The user's query or message
        property_context (dict): Context about the property
        rag_results (dict): Results from the RAG system
        conversation_history (list, optional): Previous conversation messages

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

    # Add simple tool guidance without exposing technical details
    tools_instruction = (
        "SEARCH CAPABILITY: You have access to web search to find current information about local attractions, " +
        "restaurants, transportation, weather, and other location-specific details. Use this capability when guests " +
        "ask about the surrounding area or when you need up-to-date information that isn't in the property context. " +
        "Always provide helpful, accurate information and search for details when needed."
    )
    prompt_parts.append(tools_instruction)

    # Add conversation history if available
    if conversation_history and len(conversation_history) > 0:
        conversation_context = "PREVIOUS CONVERSATION:\n"
        for message_entry in conversation_history:
            role = message_entry.get('role', '')
            text = message_entry.get('text', '')
            if role.lower() == 'user':
                conversation_context += f"Guest: {text}\n"
            elif role.lower() == 'assistant' or role.lower() == 'ai':
                conversation_context += f"You: {text}\n"
        prompt_parts.append(conversation_context)

    # Add user query
    prompt_parts.append(f"GUEST QUERY: {user_query}")

    # Return the formatted prompt
    return "\n\n".join(prompt_parts)

def format_fallback_prompt(user_query, property_context=None, conversation_history=None):
    """
    Format a prompt for Gemini fallback scenarios without RAG results.

    Args:
        user_query (str): The user's query or message
        property_context (dict, optional): Context about the property
        conversation_history (list, optional): Previous conversation messages

    Returns:
        str: The formatted fallback prompt
    """
    # Start with a base prompt with property information
    prompt_parts = [create_base_prompt(property_context)]

    # Add a note about limited information
    prompt_parts.append("I don't have specific information about this property. If I can't answer a question, I'll let you know.")

    # Add simple tool guidance without exposing technical details
    tools_instruction = (
        "SEARCH CAPABILITY: You have access to web search to find current information about local attractions, " +
        "restaurants, transportation, weather, and other location-specific details. Use this capability when guests " +
        "ask about the surrounding area or when you need up-to-date information that isn't in the property context. " +
        "Always provide helpful, accurate information and search for details when needed."
    )
    prompt_parts.append(tools_instruction)

    # Add conversation history if available
    if conversation_history and len(conversation_history) > 0:
        conversation_context = "PREVIOUS CONVERSATION:\n"
        for message_entry in conversation_history:
            role = message_entry.get('role', '')
            text = message_entry.get('text', '')
            if role.lower() == 'user':
                conversation_context += f"Guest: {text}\n"
            elif role.lower() == 'assistant' or role.lower() == 'ai':
                conversation_context += f"You: {text}\n"
        prompt_parts.append(conversation_context)

    # Add user query
    prompt_parts.append(f"GUEST QUERY: {user_query}")

    # Return the formatted prompt
    return "\n\n".join(prompt_parts)

def generate_conversation_summary(messages, property_context=None, reservation_info=None, guest_name=None):
    """
    Generate a summary of a conversation using the Gemini model with new google-genai SDK.

    Args:
        messages: List of message objects with 'role' and 'text' keys
        property_context: Optional dictionary with property information
        reservation_info: Optional dictionary with reservation details
        guest_name: Optional guest name from the conversation record (takes priority)

    Returns:
        A string containing the conversation summary
    """
    try:
        # Import Gemini model - using new SDK
        import google.genai as genai

        if not messages or len(messages) == 0:
            return "No messages to summarize."

        # Check if Gemini SDK is available
        if genai is None:
            return "Gemini model not available for summarization."

        # Format the conversation for the model
        conversation_text = ""
        for msg in messages:
            role = "Guest" if msg.get('role', '').lower() == 'user' else "Assistant"
            text = msg.get('text', '')
            conversation_text += f"{role}: {text}\n\n"

        # Extract property and guest information for context
        property_name = "Unknown Property"
        property_location = ""
        final_guest_name = "the guest"
        check_in = ""
        check_out = ""

        # Prioritize guest name from conversation record (passed as parameter)
        if guest_name and guest_name.strip() and guest_name.lower() not in ['guest', 'unknown guest', 'the guest']:
            final_guest_name = guest_name
            print(f"Using guest name from conversation record: {final_guest_name}")
        else:
            # Fallback to property context and reservation info
            if property_context:
                property_name = property_context.get('name', property_name)
                property_location = property_context.get('address', property_context.get('location', ''))
                context_guest_name = property_context.get('guestName', '')
                if context_guest_name and context_guest_name.lower() not in ['guest', 'unknown guest', 'the guest']:
                    final_guest_name = context_guest_name
                    print(f"Using guest name from property context: {final_guest_name}")

            if reservation_info:
                res_guest_name = reservation_info.get('guestName', '')
                if res_guest_name and res_guest_name.lower() not in ['guest', 'unknown guest', 'the guest']:
                    final_guest_name = res_guest_name
                    print(f"Using guest name from reservation info: {final_guest_name}")
                check_in = reservation_info.get('startDate', '')
                check_out = reservation_info.get('endDate', '')

        # Set property info even if guest name came from conversation record
        if property_context:
            property_name = property_context.get('name', property_name)
            property_location = property_context.get('address', property_context.get('location', ''))

            # Format dates if they exist using date utilities
            if check_in:
                try:
                    from concierge.utils.date_utils import format_date_for_display
                    check_in = format_date_for_display(check_in, 'iso')
                except:
                    pass

            if check_out:
                try:
                    from concierge.utils.date_utils import format_date_for_display
                    check_out = format_date_for_display(check_out, 'iso')
                except:
                    pass

        # Create the prompt for summarization with context (brief overview of the whole conversation)
        prompt = f"""
        Summarize this entire conversation between a guest and an AI concierge for {property_name}{' at ' + property_location if property_location else ''}.
        {f'The guest is staying from {check_in} to {check_out}.' if check_in and check_out else ''}

        Requirements:
        - Provide a brief overview of all topics discussed and the key answers given
        - 2–3 sentences, neutral tone, host-facing
        - Max 350 characters
        - No quotes, no filler, no step-by-step

        Conversation:
        {conversation_text}

        Output (<=350 chars):
        """

        # Generate the summary using new Gemini SDK with rate limiting
        try:
            client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
            
            def make_summary_call():
                return client.models.generate_content(
                    model='gemini-2.5-flash-lite',
                    contents=prompt
                )
            
            response = rate_limited_gemini_call(make_summary_call, max_retries=2)
            summary = response.text.strip()
        except Exception as e:
            logging.error(f"Error calling new Gemini SDK for summary: {e}")
            # Fallback to legacy gemini_model if available
            try:
                from concierge.utils.gemini_config import gemini_model
                if gemini_model:
                    response = gemini_model.generate_content(prompt)
                    summary = response.text.strip()
                else:
                    return "Unable to generate summary - no model available."
            except Exception as fallback_error:
                logging.error(f"Fallback summary generation failed: {fallback_error}")
                return "Unable to generate summary due to an error."

        # If summary is too long, truncate it to 500 characters
            if len(summary) > 350:
                summary = summary[:347] + "..."

        return summary
    except Exception as e:
        logging.error(f"Error generating conversation summary: {e}")
        return "Unable to generate summary due to an error."

def process_query_with_rag(user_query, property_id, property_context=None, conversation_history=None, system_prompt=None):
    """
    Process a user query with RAG and return a response from Gemini.

    Args:
        user_query (str): The user's query or message
        property_id (str): The property ID
        property_context (dict, optional): Context about the property
        conversation_history (list, optional): Previous conversation messages
        system_prompt (str, optional): Custom system prompt to use instead of the default format

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
        # Check if genai is available
        if genai is None:
            logging.error("Google Generative AI module not available")
            result['response'] = "I'm sorry, I'm having trouble accessing my AI capabilities right now. Please try again later."
            return result
        # Log information about the RAG request
        logging.info(f"Processing query with RAG: query='{user_query}', property_id='{property_id}', system_prompt available: {system_prompt is not None}")

        # Validate property_id
        if not property_id:
            logging.warning("No property_id provided for RAG lookup")
            result['response'] = "I don't have property-specific information available. Please make sure you're properly authenticated."
            return result

        # Get relevant context from Firestore
        logging.info(f"Searching for similar knowledge items in Firestore for property: {property_id}")
        rag_results = get_relevant_context(user_query, property_id)
        
        # Continue with RAG processing...
        result['response'] = "RAG processing not fully implemented"
        return result
        
    except Exception as e:
        logging.error(f"Error in process_query_with_rag: {e}")
        result['response'] = "I'm sorry, I'm having trouble processing your request right now."
        return result
 
# === Text Chat (No-RAG) Helper ===
def process_text_query_with_tools(user_query, property_context=None, conversation_history=None, system_prompt=None):
    """
    Process a user text query WITHOUT RAG retrieval. Uses a shared system prompt that
    already contains property context (and optionally knowledge items) similar to voice calls.

    The model is given both google_search and get_current_time tools and will decide when
    to use them. If a function call to get_current_time is returned, we execute it and
    perform a single follow-up call including the function result to complete the reply.

    Args:
        user_query (str): The user's query or message
        property_context (dict, optional): Property details for local tools (timezone)
        conversation_history (list, optional): Previous conversation messages (role/text)
        system_prompt (str, optional): Shared system prompt to use

    Returns:
        dict: { 'response': str }
    """
    result = {
        'response': ''
    }

    try:
        if genai is None:
            logging.error("Google Generative AI module not available")
            result['response'] = "I'm having trouble accessing my AI capabilities right now. Please try again later."
            return result

        # Build the prompt: prefer provided system_prompt; otherwise fall back to base prompt
        prompt_parts = []

        if system_prompt:
            logging.info(f"[TEXT CHAT] Using provided shared system prompt (length: {len(system_prompt)})")
            prompt_parts.append(system_prompt)
        else:
            logging.info("[TEXT CHAT] No system prompt provided, building a minimal base prompt")
            prompt_parts.append(create_base_prompt(property_context))

        # Add conversation history if available
        if conversation_history and len(conversation_history) > 0:
            conversation_context = "\n\nPREVIOUS CONVERSATION:\n"
            for message_entry in conversation_history:
                role = message_entry.get('role', '')
                text = message_entry.get('text', '')
                if role.lower() == 'user':
                    conversation_context += f"Guest: {text}\n"
                elif role.lower() in ['assistant', 'ai']:
                    conversation_context += f"You: {text}\n"
            prompt_parts.append(conversation_context)

        # Add current user query
        prompt_parts.append(f"GUEST QUERY: {user_query}")
        prompt = "\n\n".join(prompt_parts)

        # Create client and configure tools: both google_search and function calling
        client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
        
        # Import Places API functions
        from concierge.utils.places_api import find_nearby_with_details, is_places_api_enabled

        function_declarations = [
            genai.types.FunctionDeclaration(
                name="get_current_time",
                description="Get the current date and time for the property location. Use this when the guest asks about the current time, date, dining recommendations, business hours, or any time-sensitive information. Always call this function when discussing restaurants, activities, or services that depend on current time of day.",
                parameters=genai.types.Schema(
                    type=genai.types.Type.OBJECT,
                    properties={},
                    required=[]
                )
            )
        ]
        
        # Add Places API if enabled
        if is_places_api_enabled():
            function_declarations.append(
                genai.types.FunctionDeclaration(
                    name="search_nearby_places",
                    description="Search for nearby places like restaurants, cafes, attractions, shopping, etc. with accurate distances, travel times, ratings, hours, and price levels. Use this INSTEAD of google_search for ANY location-based queries about places around the property. This provides structured data with walking/driving distances, ratings, open hours, and more accurate information than web search.",
                    parameters=genai.types.Schema(
                        type=genai.types.Type.OBJECT,
                        properties={
                            "query": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="What to search for (e.g., 'Italian restaurants', 'coffee shops', 'tourist attractions')"
                            ),
                            "place_type": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="Optional category: restaurant, cafe, bar, attraction, museum, park, shopping, grocery, pharmacy, hospital, gas_station, atm, bank",
                                enum=["restaurant", "cafe", "bar", "attraction", "museum", "park", "shopping", "grocery", "pharmacy", "hospital", "gas_station", "atm", "bank"]
                            ),
                            "max_results": genai.types.Schema(
                                type=genai.types.Type.INTEGER,
                                description="Maximum number of results to return (default: 5, max: 10)"
                            ),
                            "radius": genai.types.Schema(
                                type=genai.types.Type.INTEGER,
                                description="Search radius in meters (default: 5000m ≈ 3 miles)"
                            ),
                            "travel_mode": genai.types.Schema(
                                type=genai.types.Type.STRING,
                                description="Travel mode for distance calculation: walking, driving, transit, or bicycling",
                                enum=["walking", "driving", "transit", "bicycling"]
                            )
                        },
                        required=["query"]
                    )
                )
            )
            logging.info("[TEXT CHAT] Places API enabled - including search_nearby_places tool")

        # Try function calling first
        def make_function_call():
            return client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    tools=[genai.types.Tool(function_declarations=function_declarations)]
                )
            )

        logging.info("[TEXT CHAT DEBUG] Attempting function call with get_current_time")
        response = rate_limited_gemini_call(make_function_call, max_retries=2)
        logging.info(f"[TEXT CHAT DEBUG] Function call response received: {response is not None}")

        # Handle potential function calls (get_current_time and search_nearby_places)
        try:
            function_called = False
            if response and hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'function_call') and part.function_call:
                                fname = part.function_call.name
                                logging.info(f"[TEXT CHAT] Function call detected: {fname}")
                                
                                if fname == "get_current_time":
                                    function_called = True
                                    time_result = get_current_time(property_context)
                                    logging.info(f"[TEXT CHAT] get_current_time result: {time_result}")

                                    follow_up_prompt = f"{prompt}\n\nFunction call result: {time_result}\n\nPlease provide a natural response using this current time information."

                                    def make_follow_up_call():
                                        return client.models.generate_content(
                                            model='gemini-2.5-flash',
                                            contents=follow_up_prompt
                                        )

                                    response = rate_limited_gemini_call(make_follow_up_call, max_retries=2)
                                    break
                                
                                elif fname == "search_nearby_places":
                                    function_called = True
                                    logging.info("[TEXT CHAT] Function call detected: search_nearby_places")
                                    
                                    # Extract arguments
                                    args = {}
                                    if hasattr(part.function_call, 'args') and part.function_call.args:
                                        args = dict(part.function_call.args)
                                    
                                    logging.info(f"[TEXT CHAT] search_nearby_places args: {args}")
                                    
                                    # Get property location
                                    property_location = None
                                    if property_context:
                                        address_parts = []
                                        for field in ['address', 'city', 'state', 'country']:
                                            if field in property_context and property_context[field]:
                                                address_parts.append(property_context[field])
                                        if address_parts:
                                            property_location = ', '.join(address_parts)
                                    
                                    if not property_location:
                                        logging.warning("[TEXT CHAT] No property location available for Places API search")
                                        follow_up_prompt = f"{prompt}\n\nI couldn't determine the property location to search nearby places. Please provide a response without location search."
                                        
                                        def make_error_call():
                                            return client.models.generate_content(
                                                model='gemini-2.5-flash',
                                                contents=follow_up_prompt
                                            )
                                        
                                        response = rate_limited_gemini_call(make_error_call, max_retries=2)
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
                                    
                                    logging.info(f"[TEXT CHAT] Places API returned {places_result.get('total_results', 0)} results")
                                    
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
                                    def make_places_call():
                                        return client.models.generate_content(
                                            model='gemini-2.5-flash',
                                            contents=follow_up_prompt
                                        )
                                    
                                    response = rate_limited_gemini_call(make_places_call, max_retries=2)
                                    break
                    
                    if function_called:
                        break
        except Exception as func_err:
            logging.warning(f"[TEXT CHAT] Error while handling function call: {func_err}")

        # If no function was called and no text response, try Google Search
        if not function_called and (not response or not hasattr(response, 'text') or not response.text.strip()):
            logging.info("[TEXT CHAT DEBUG] No function call made, trying Google Search fallback")
            
            def make_search_call():
                return client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())]
                    )
                )
            
            logging.info("[TEXT CHAT DEBUG] Making Google Search call")
            response = rate_limited_gemini_call(make_search_call, max_retries=2)
        else:
            logging.info(f"[TEXT CHAT DEBUG] Function called: {function_called}, Response has text: {response and hasattr(response, 'text') and bool(response.text.strip())}")

        # Extract text
        if response and getattr(response, 'text', None):
            result['response'] = response.text
        else:
            # Try to extract from candidates
            extracted_text = None
            try:
                if response and hasattr(response, 'candidates') and response.candidates:
                    for candidate in response.candidates:
                        if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts'):
                            for part in candidate.content.parts:
                                if getattr(part, 'text', None):
                                    extracted_text = part.text
                                    break
                        if extracted_text:
                            break
            except Exception as parse_err:
                logging.warning(f"[TEXT CHAT] Could not extract text from candidates: {parse_err}")

            if extracted_text:
                result['response'] = extracted_text
            else:
                logging.error(f"[TEXT CHAT] Empty or invalid response from Gemini: {response}")
                result['response'] = "I'm sorry, I'm having trouble processing that right now. Could you try again?"

        return result

    except Exception as e:
        logging.error(f"Error processing text query with tools: {e}")
        traceback.print_exc()

        # Fallbacks for common property info that we can answer without the model
        try:
            ql = (user_query or '').lower()
            if property_context:
                if any(k in ql for k in ['wifi', 'internet', 'password']):
                    wifi_network = property_context.get('wifiNetwork', '')
                    wifi_password = property_context.get('wifiPassword', '')
                    if wifi_network or wifi_password:
                        result['response'] = f"WiFi details — Network: {wifi_network or 'Not provided'}{', Password: ' + wifi_password if wifi_password else ''}"
                        return result

                if any(k in ql for k in ['check in', 'check-in', 'check out', 'check-out']):
                    ci = property_context.get('checkInTime', '')
                    co = property_context.get('checkOutTime', '')
                    if ci or co:
                        result['response'] = f"Check-in: {ci or 'N/A'}{', Check-out: ' + co if co else ''}"
                        return result
        except Exception:
            pass

        result['response'] = "I'm sorry, I'm having trouble accessing the information you need. How else can I assist you?"
        return result


# === Firestore Vector Search ===
def get_relevant_context(user_query, property_id):
    """
    Get relevant context from Firestore using vector search.
    
    Args:
        user_query (str): The user's query
        property_id (str): The property ID to search within
        
    Returns:
        dict: Contains 'found' (bool) and 'items' (list) with relevant context
    """
    try:
        # Get relevant context from Firestore
        logging.info(f"Searching for similar knowledge items in Firestore for property: {property_id}")
        rag_results = get_relevant_context(user_query, property_id)

        # Initialize property information flags
        has_name = False
        has_host = False
        has_address = False
        has_wifi = False

        # Log results of context lookup
        if rag_results.get('found'):
            logging.info(f"Found {len(rag_results.get('items', []))} relevant items in knowledge base")
            for idx, item in enumerate(rag_results.get('items', [])):
                logging.info(f"Context item {idx+1}: similarity={item.get('similarity', 0):.4f}, text='{item.get('text', '')[:100]}...'")
        else:
            logging.warning(f"No relevant context found in knowledge base for property_id: {property_id}")

        # If no property_context provided, create a minimal one
        if not property_context:
            logging.warning(f"No property_context provided for property {property_id}, using minimal context")
            property_context = {'name': f'Property {property_id}', 'hostName': 'Your Host'}
        else:
            # Log the property context we received
            logging.info(f"Received property_context with keys: {', '.join(property_context.keys())}")

            # Check if we have essential fields
            has_name = 'name' in property_context and property_context['name'] != f'Property {property_id}'
            has_host = 'hostName' in property_context and property_context['hostName'] not in ['the host', 'Your Host']
            has_address = 'address' in property_context or 'location' in property_context
            has_wifi = 'wifiNetwork' in property_context or 'wifiPassword' in property_context

            logging.info(f"Property context check - Name: {has_name}, Host: {has_host}, Address: {has_address}, WiFi: {has_wifi}")

            # Log specific fields for debugging
            if has_name:
                logging.info(f"Property name: {property_context.get('name')}")
            if has_host:
                logging.info(f"Host name: {property_context.get('hostName')}")
            if has_address:
                address_value = property_context.get('address', property_context.get('location', ''))
                logging.info(f"Address: {address_value}")
            if has_wifi:
                logging.info(f"WiFi details available: network={bool(property_context.get('wifiNetwork'))}, password={bool(property_context.get('wifiPassword'))}")

        # Format prompt based on whether a custom system prompt is provided
        if system_prompt:
            logging.info(f"Using provided system prompt (length: {len(system_prompt)})")

            # Start with the system prompt
            prompt_parts = [system_prompt]

            # Add relevant RAG results if available
            if rag_results and rag_results.get('found') and rag_results.get('items'):
                knowledge_context = "\n\nRELEVANT PROPERTY INFORMATION:\n"
                for item in rag_results.get('items', []):
                    knowledge_context += f"- {item.get('text', '')}\n"
                prompt_parts.append(knowledge_context)

            # Add conversation history if available
            if conversation_history and len(conversation_history) > 0:
                conversation_context = "\n\nPREVIOUS CONVERSATION:\n"
                for message_entry in conversation_history:
                    role = message_entry.get('role', '')
                    text = message_entry.get('text', '')
                    if role.lower() == 'user':
                        conversation_context += f"USER: {text}\n"
                    elif role.lower() == 'assistant' or role.lower() == 'ai':
                        conversation_context += f"ASSISTANT: {text}\n"
                prompt_parts.append(conversation_context)

            # Add the current user message
            prompt_parts.append(f"\nUSER: {user_query}\nASSISTANT:")

            # Combine all prompt parts
            prompt = "\n".join(prompt_parts)
        else:
            # Use the default prompt formatting function
            prompt = format_prompt_with_rag(user_query, property_context, rag_results, conversation_history)

        logging.info(f"Generated prompt length: {len(prompt)} characters")

        # Log key parts of the prompt for debugging (without exposing sensitive info)
        if len(prompt) > 1000:
            # Log first 200 and last 200 characters to avoid excessive logging
            logging.info(f"Prompt start: {prompt[:200]}...")
            logging.info(f"Prompt end: ...{prompt[-200:]}")
        else:
            logging.info(f"Full prompt: {prompt}")

        # Generate response from Gemini with conditional tool usage
        try:
            # Create client with the new google-genai SDK
            logging.info("Initializing Google GenAI client with conditional tool usage")
            
            client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
            
            # Define function declarations for time queries
            function_declarations = [
                genai.types.FunctionDeclaration(
                    name="get_current_time",
                    description="Get the current date and time for the property location. Use this when the guest asks about the current time, date, or when you need to provide time-sensitive information.",
                    parameters=genai.types.Schema(
                        type=genai.types.Type.OBJECT,
                        properties={},
                        required=[]
                    )
                )
            ]
            
            # Check if this is a current-time/date query (narrow phrases to avoid false positives like 'when is checkout')
            query_lower = user_query.lower()
            time_keywords = [
                'what time is it',
                'what is the time',
                "what's the time",
                'current time',
                'time now',
                'local time',
                'current date',
                "today's date",
                'date today'
            ]
            matched_kw = next((kw for kw in time_keywords if kw in query_lower), None)
            is_time_query = matched_kw is not None
            logging.info(f"[TEXT CHAT DEBUG] Time-query detection: {is_time_query} (matched='{matched_kw}')")
            
            def make_search_call():
                if is_time_query:
                    # For time queries, prioritize function calling
                    return client.models.generate_content(
                        model='gemini-2.5-flash-lite',
                        contents=prompt,
                        config=genai.types.GenerateContentConfig(
                            tools=[genai.types.Tool(function_declarations=function_declarations)]
                        )
                    )
                else:
                    # For other queries, use Google Search ONLY (no function calling to avoid API conflict)
                    return client.models.generate_content(
                        model='gemini-2.5-flash-lite',
                        contents=prompt,
                        config=genai.types.GenerateContentConfig(
                            tools=[
                                genai.types.Tool(google_search=genai.types.GoogleSearch())
                            ]
                        )
                    )
            
            # Use the new SDK syntax for Google Search with rate limiting
            response = rate_limited_gemini_call(make_search_call, max_retries=2)
            
            # Check for function calls in the response
            if response and hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'function_call') and part.function_call:
                                fname = part.function_call.name
                                logging.info(f"[TEXT CHAT DEBUG] Function call detected: {fname}")
                                if fname == "get_current_time":
                                    function_called = True
                                    logging.info("[TEXT CHAT] Function call detected: get_current_time")
                                    
                                    # Call the actual function
                                    time_result = get_current_time(property_context)
                                    logging.info(f"[TEXT CHAT] get_current_time result: {time_result}")
                                    
                                    # Create follow-up prompt with the time information
                                    time_info = f"Current time information: {time_result['full_datetime']}"
                                    follow_up_prompt = f"{prompt}\n\n{time_info}\n\nPlease provide your response using this current time information."
                                    
                                    # Generate final response with time context
                                    def make_follow_up_call():
                                        return client.models.generate_content(
                                            model='gemini-2.5-flash',
                                            contents=follow_up_prompt
                                        )
                                    
                                    logging.info("[TEXT CHAT DEBUG] Making follow-up call with time context")
                                    response = rate_limited_gemini_call(make_follow_up_call, max_retries=2)
                                    break
            
            logging.info(f"Successfully called Gemini with {'function calling only' if is_time_query else 'Google Search only'} using new SDK")

        except Exception as tool_error:
            # Fallback to regular generation if function calling fails
            logging.warning(f"Function calling failed: {tool_error}")
            logging.info("Falling back to regular Gemini generation")
            
            try:
                # Create client for fallback with function calling still enabled
                client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
                
                # Define function declarations for fallback too
                function_declarations = [
                    genai.types.FunctionDeclaration(
                        name="get_current_time",
                        description="Get the current date and time for the property location. Use this when the guest asks about the current time, date, or when you need to provide time-sensitive information.",
                        parameters=genai.types.Schema(
                            type=genai.types.Type.OBJECT,
                            properties={},
                            required=[]
                        )
                    )
                ]
                
                def make_fallback_call():
                    return client.models.generate_content(
                        model='gemini-2.5-flash-lite',
                        contents=prompt,
                        config=genai.types.GenerateContentConfig(
                            tools=[genai.types.Tool(function_declarations=function_declarations)]
                        )
                    )
                
                response = rate_limited_gemini_call(make_fallback_call, max_retries=2)
                
                # Check for function calls in fallback response too
                if response and hasattr(response, 'candidates') and response.candidates:
                    for candidate in response.candidates:
                        if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts'):
                            for part in candidate.content.parts:
                                if hasattr(part, 'function_call') and part.function_call:
                                    function_name = part.function_call.name
                                    logging.warning(f"[TEXT CHAT DEBUG] Function call detected in fallback: {function_name}")
                                    
                                    if function_name == "get_current_time":
                                        # Execute the function with property context
                                        time_result = get_current_time(property_context)
                                        logging.warning(f"[TEXT CHAT DEBUG] Fallback function result: {time_result}")
                                        
                                        # Continue the conversation with the function result
                                        follow_up_prompt = f"{prompt}\n\nFunction call result: {time_result}\n\nPlease provide a natural response using this current time information."
                                        
                                        def make_follow_up_fallback_call():
                                            return client.models.generate_content(
                                                model='gemini-2.5-flash-lite',
                                                contents=follow_up_prompt
                                            )
                                        
                                        response = rate_limited_gemini_call(make_follow_up_fallback_call, max_retries=2)
                                        break
            except Exception as fallback_error:
                logging.error(f"Fallback generation also failed: {fallback_error}")
                raise fallback_error

        if response and getattr(response, 'text', None):
            result['response'] = response.text
            result['has_context'] = rag_results.get('found', False)
            if rag_results.get('items'):
                result['context_used'] = rag_results['items']

            # Log the response (truncated for readability)
            response_text = response.text or ''
            if len(response_text) > 500:
                logging.info(f"Gemini response (truncated): '{response_text[:500]}...'")
            else:
                logging.info(f"Gemini response: '{response_text}'")

            # Check if response contains requested information when available
            query_lower = user_query.lower()

            # Check for WiFi information in response
            if ('wifi' in query_lower or 'internet' in query_lower or 'password' in query_lower) and has_wifi:
                wifi_in_response = ('wifi' in response_text.lower() and
                                    ('password' in response_text.lower() or 'network' in response_text.lower()))

                if wifi_in_response:
                    logging.info("WiFi information successfully included in response")
                else:
                    logging.warning("User asked about WiFi but response may not include complete WiFi details")

            # Check for address information in response
            if ('address' in query_lower or 'location' in query_lower or 'where' in query_lower) and has_address:
                address_in_response = ('address' in response_text.lower() or
                                      property_context.get('address', '') in response_text or
                                      property_context.get('location', '') in response_text)

                if address_in_response:
                    logging.info("Address information successfully included in response")
                else:
                    logging.warning("User asked about location but response may not include complete address details")

            # Check if the response appears to be a fallback response
            if "I don't have that specific information" in response_text or "I don't have information about" in response_text:
                logging.warning("Generated response indicates no specific information available")
        else:
            # Try to extract text from candidates if available
            extracted_text = None
            try:
                if response and hasattr(response, 'candidates') and response.candidates:
                    for candidate in response.candidates:
                        if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts'):
                            for part in candidate.content.parts:
                                if getattr(part, 'text', None):
                                    extracted_text = part.text
                                    break
                        if extracted_text:
                            break
            except Exception as parse_err:
                logging.warning(f"Could not extract text from response candidates: {parse_err}")

            if extracted_text:
                result['response'] = extracted_text
                result['has_context'] = rag_results.get('found', False)
                if rag_results.get('items'):
                    result['context_used'] = rag_results['items']
                logging.info("Extracted response text from candidates.")
            else:
                logging.error(f"Empty or invalid response from Gemini: {response}")
                result['response'] = "I'm sorry, I'm having trouble processing your request. Can you please try again?"

        return result

    except Exception as e:
        logging.error(f"Error processing query with RAG: {e}")
        traceback.print_exc()
        
        # Check if this is a quota exceeded error and provide intelligent fallback
        error_str = str(e).lower()
        if '429' in error_str or 'quota' in error_str or 'resource_exhausted' in error_str:
            logging.info("Detected quota exceeded error, providing intelligent fallback response")
            
            # Check if this is a WiFi-related query and we have WiFi context
            query_lower = user_query.lower()
            if ('wifi' in query_lower or 'password' in query_lower or 'internet' in query_lower) and property_context:
                wifi_network = property_context.get('wifiNetwork', '')
                wifi_password = property_context.get('wifiPassword', '')
                
                if wifi_network and wifi_password:
                    result['response'] = f"Here are the WiFi details for your stay:\n\n **Network:** {wifi_network}\n **Password:** {wifi_password}\n\nJust connect to the network and enter the password when prompted!"
                    result['has_context'] = True
                    logging.info("Provided WiFi information from property context as fallback")
                    return result
            
            # Check for basic property information queries
            if ('property' in query_lower or 'name' in query_lower or 'address' in query_lower or 'location' in query_lower) and property_context:
                property_name = property_context.get('name', property_context.get('Name', 'this property'))
                property_address = property_context.get('address', property_context.get('location', ''))
                
                if 'name' in query_lower and property_name:
                    result['response'] = f"You're staying at **{property_name}**"
                    if property_address:
                        result['response'] += f" located in {property_address}"
                    result['response'] += "."
                    result['has_context'] = True
                    logging.info("Provided property name from context as fallback")
                    return result
                elif ('address' in query_lower or 'location' in query_lower) and property_address:
                    result['response'] = f"The property is located at: **{property_address}**"
                    result['has_context'] = True
                    logging.info("Provided property address from context as fallback")
                    return result
            
            # Check for check-in/check-out time queries
            if ('check' in query_lower or 'time' in query_lower) and property_context:
                checkin_time = property_context.get('checkInTime', '')
                checkout_time = property_context.get('checkOutTime', '')
                
                if 'in' in query_lower and checkin_time:
                    result['response'] = f"Check-in time is **{checkin_time}**"
                    result['has_context'] = True
                    logging.info("Provided check-in time from context as fallback")
                    return result
                elif 'out' in query_lower and checkout_time:
                    result['response'] = f"Check-out time is **{checkout_time}**"
                    result['has_context'] = True
                    logging.info("Provided check-out time from context as fallback")
                    return result
                elif checkin_time and checkout_time:
                    result['response'] = f"**Check-in:** {checkin_time}\n**Check-out:** {checkout_time}"
                    result['has_context'] = True
                    logging.info("Provided check-in/out times from context as fallback")
                    return result
            
            # Generic quota exceeded message
            result['response'] = "I'm currently experiencing high usage and my AI engine is temporarily unavailable. However, I can still help you with basic information about your stay. Try asking about WiFi, check-in times, or property details!"
            
        else:
            # Non-quota error
            result['response'] = "I'm sorry, I'm having trouble accessing the information you need. How else can I assist you?"

    return result

# === Firestore Vector Search Functions ===
# These functions replace the previous LanceDB functions

def check_item_in_firestore(property_id: str, item_id: str) -> bool:
    """
    Checks if a specific knowledge item (identified by item_id) exists in Firestore
    for the given property_id.

    Args:
        property_id (str): The ID of the property.
        item_id (str): The ID of the knowledge item.

    Returns:
        bool: True if the item exists, False otherwise.
    """
    try:
        # Initialize Firebase if needed
        if not initialize_firebase:
            logging.error("Firebase initialization function not available")
            return False

        if not initialize_firebase():
            logging.error("Failed to initialize Firebase")
            return False

        # Get Firestore client
        db = get_firestore_client()
        if not db:
            logging.error("Failed to get Firestore client")
            return False

        # Check if the item exists in Firestore
        doc_ref = db.collection('properties').document(property_id).collection('knowledge').document(item_id)
        doc = doc_ref.get()

        exists = doc.exists
        logging.info(f"Item '{item_id}' for property '{property_id}' exists in Firestore: {exists}")
        return exists

    except Exception as e:
        logging.error(f"Error checking item '{item_id}' for property '{property_id}' in Firestore: {e}")
        traceback.print_exc()
        return False

def get_knowledge_item_from_firestore(property_id: str, item_id: str) -> dict:
    """
    Retrieves a specific knowledge item from Firestore.

    Args:
        property_id (str): The ID of the property.
        item_id (str): The ID of the knowledge item.

    Returns:
        dict: The knowledge item data or an empty dict if not found.
    """
    try:
        # Initialize Firebase if needed
        if not initialize_firebase:
            logging.error("Firebase initialization function not available")
            return {}

        if not initialize_firebase():
            logging.error("Failed to initialize Firebase")
            return {}

        # Get Firestore client
        db = get_firestore_client()
        if not db:
            logging.error("Failed to get Firestore client")
            return {}

        # Get the document from Firestore
        doc_ref = db.collection('properties').document(property_id).collection('knowledge').document(item_id)
        doc = doc_ref.get()

        if not doc.exists:
            logging.warning(f"Knowledge item '{item_id}' not found for property '{property_id}'")
            return {}

        # Get the data and add the ID
        data = doc.to_dict()
        data['id'] = doc.id

        return data

    except Exception as e:
        logging.error(f"Error retrieving knowledge item '{item_id}' for property '{property_id}': {e}")
        traceback.print_exc()
        return {}

# === FUNCTION: Batch check multiple items in Firestore ===
def batch_check_items_in_firestore(property_id: str, item_ids: list) -> dict:
    """
    Efficiently checks multiple knowledge items in Firestore with a single connection.

    Args:
        property_id (str): The ID of the property.
        item_ids (list): List of item IDs to check.

    Returns:
        dict: Dictionary mapping item IDs to existence status (True/False).
    """
    results = {}

    # Initialize all items as not found
    for item_id in item_ids:
        results[item_id] = False

    if not item_ids:
        return results

    try:
        # Initialize Firebase if needed
        if not initialize_firebase:
            logging.error("Firebase initialization function not available")
            return results

        if not initialize_firebase():
            logging.error("Failed to initialize Firebase")
            return results

        # Get Firestore client
        db = get_firestore_client()
        if not db:
            logging.error("Failed to get Firestore client")
            return results

        # Get the knowledge collection reference
        knowledge_collection = db.collection('properties').document(property_id).collection('knowledge')

        # Check each item ID
        for item_id in item_ids:
            doc = knowledge_collection.document(item_id).get()
            results[item_id] = doc.exists

        return results

    except Exception as e:
        logging.error(f"Error batch checking items for property '{property_id}' in Firestore: {e}")
        traceback.print_exc()
        return results


def get_current_time(property_context=None):
    """
    Function for Gemini to call to get the current date and time.
    Returns current datetime in the property's timezone if available.
    
    Args:
        property_context (dict, optional): Property information including location/timezone
    
    Returns:
        dict: Contains current date and time information
    """
    from datetime import datetime, timezone, timedelta
    import re
    
    try:
        # Get current UTC time
        now_utc = datetime.now(timezone.utc)
        
        # Try to determine timezone from property context
        tz_offset = 0  # Default UTC offset
        tz_name = "UTC"
        tzinfo_obj = None  # Prefer ZoneInfo when possible
        
        # Debug logging
        logging.warning(f"[TIMEZONE DEBUG] get_current_time called with property_context: {property_context}")
        
        if property_context:
            # Check for explicit timezone in property data
            if 'timezone' in property_context and property_context['timezone']:
                tz_name = property_context['timezone']
                logging.info(f"Using explicit timezone from property: {tz_name}")
                # Attempt to use IANA timezone via zoneinfo first
                try:
                    from zoneinfo import ZoneInfo
                    tzinfo_obj = ZoneInfo(tz_name)
                except Exception as e:
                    # Fallback to common name/abbreviation mapping
                    logging.warning(f"ZoneInfo lookup failed for '{tz_name}': {e}. Falling back to offset mapping.")
                    tz_map = {
                        'America/Phoenix': (-7, 'MST'),
                        'US/Arizona': (-7, 'MST'),
                        'MST': (-7, 'MST'),
                        'MDT': (-6, 'MDT'),
                        'PST': (-8, 'PST'),
                        'PDT': (-7, 'PDT'),
                        'CST': (-6, 'CST'),
                        'CDT': (-5, 'CDT'),
                        'EST': (-5, 'EST'),
                        'EDT': (-4, 'EDT'),
                    }
                    if tz_name in tz_map:
                        tz_offset, tz_name = tz_map[tz_name]
            else:
                # Try to infer timezone from location/address
                location_text = ""
                for field in ['address', 'location', 'city', 'state', 'country', 'name']:
                    if field in property_context and property_context[field]:
                        location_text += f" {property_context[field]}"
                
                # If no location data but we have property_id, try to fetch property data
                if not location_text.strip() and 'property_id' in property_context:
                    property_id = property_context['property_id']
                    logging.info(f"No location data in context, attempting to fetch for property_id: {property_id}")
                    
                    try:
                        # Try to get property data from Firestore
                        from concierge.utils.firestore_client import get_firestore_client
                        db = get_firestore_client()
                        if db:
                            prop_ref = db.collection('properties').document(property_id)
                            prop_doc = prop_ref.get()
                            if prop_doc.exists:
                                prop_data = prop_doc.to_dict()
                                logging.info(f"Fetched property data for timezone detection: {list(prop_data.keys())}")
                                # Extract location fields from fetched data
                                for field in ['address', 'location', 'city', 'state', 'country', 'name']:
                                    if field in prop_data and prop_data[field]:
                                        location_text += f" {prop_data[field]}"
                                    # Also try capitalized versions
                                    cap_field = field.capitalize()
                                    if cap_field in prop_data and prop_data[cap_field]:
                                        location_text += f" {prop_data[cap_field]}"
                    except Exception as e:
                        logging.warning(f"Could not fetch property data for timezone detection: {e}")
                        # Universal fallback: use user's local timezone when property data is unavailable
                        try:
                            import time
                            local_offset_seconds = -time.timezone
                            if time.daylight and time.localtime().tm_isdst:
                                local_offset_seconds = -time.altzone
                            local_offset_hours = local_offset_seconds // 3600
                            tz_offset = local_offset_hours
                            tz_name = time.tzname[time.localtime().tm_isdst] if time.tzname else f"UTC{local_offset_hours:+d}"
                            logging.info(f"Using system local timezone as fallback: {tz_name} (UTC{local_offset_hours:+d})")
                        except Exception as tz_err:
                            logging.warning(f"Could not determine local timezone: {tz_err}")
                            # Final fallback to UTC
                            tz_offset = 0
                            tz_name = "UTC"
                
                location_text = location_text.lower()
                
                # Debug logging
                logging.warning(f"[TIMEZONE DEBUG] Location text for timezone detection: '{location_text}'")
                
                # Common timezone mappings based on location
                # Note: Using standard time zones (not accounting for DST automatically)
                if any(term in location_text for term in ['arizona', 'phoenix', 'scottsdale', 'tucson']):
                    # Arizona doesn't observe DST, so it's MST year-round (UTC-7)
                    tz_offset = -7
                    tz_name = "MST"
                    logging.info(f"Detected Arizona/MST timezone from location: {location_text}")
                elif any(term in location_text for term in ['california', 'los angeles', 'san francisco', 'san diego']):
                    # Pacific Time: PST (UTC-8) or PDT (UTC-7) 
                    tz_offset = -8  # Using PST as default
                    tz_name = "PST"
                elif any(term in location_text for term in ['new york', 'florida', 'miami', 'atlanta']):
                    # Eastern Time: EST (UTC-5) or EDT (UTC-4)
                    tz_offset = -5  # Using EST as default
                    tz_name = "EST"
                elif any(term in location_text for term in ['texas', 'dallas', 'houston', 'chicago', 'illinois', 'indiana', 'cedar lake']):
                    # Central Time: CST (UTC-6) or CDT (UTC-5)
                    tz_offset = -6  # Using CST as default
                    tz_name = "CST"
                elif any(term in location_text for term in ['colorado', 'denver', 'utah', 'montana']):
                    # Mountain Time: MST (UTC-7) or MDT (UTC-6)
                    tz_offset = -7  # Using MST as default
                    tz_name = "MST"
        
        # Apply timezone to get local time (prefer tzinfo_obj if available)
        if tzinfo_obj is not None:
            local_time = now_utc.astimezone(tzinfo_obj)
            tz_label = local_time.tzname() or tz_name
        else:
            local_time = now_utc.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=tz_offset)))
            tz_label = tz_name
        
        # Format the time in a user-friendly way
        formatted_date = local_time.strftime("%A, %B %d, %Y")
        formatted_time = local_time.strftime("%I:%M %p")
        
        return {
            "current_date": formatted_date,
            "current_time": formatted_time,
            "timezone": tz_label,
            "full_datetime": f"{formatted_date} at {formatted_time} {tz_label}"
        }
        
    except Exception as e:
        logging.error(f"Error getting current time: {e}")
        # Fallback to basic datetime
        now = datetime.now()
        return {
            "current_date": now.strftime("%A, %B %d, %Y"),
            "current_time": now.strftime("%I:%M %p"),
            "timezone": "Local Time",
            "full_datetime": f"{now.strftime('%A, %B %d, %Y')} at {now.strftime('%I:%M %p')}"
        }


# Function calling schema for Gemini
GEMINI_FUNCTION_DECLARATIONS = [
    {
        "name": "get_current_time",
        "description": "Get the current date and time. Use this when the guest asks about the current time, date, or when you need to provide time-sensitive information.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]



