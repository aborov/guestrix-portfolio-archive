"""
DEPRECATED: This file contains LanceDB-based utilities that are no longer used.
The application has migrated to Firestore for vector search.
Use concierge/utils/firestore_ai_helpers.py instead.

Legacy utility functions for AI/ML related operations including RAG (Retrieval Augmented Generation).
"""

import os
import json
import traceback
import logging

# Import our caching helpers
try:
    from utils.cache_helpers import lancedb_cache, cached_connection
except ImportError:
    # For Lambda environment where relative imports might work differently
    try:
        from concierge.utils.cache_helpers import lancedb_cache, cached_connection
    except ImportError:
        lancedb_cache = None
        cached_connection = None
        logging.warning("Could not import cache_helpers, caching will be disabled")

# Optional imports - will try to load these but fallback if not available
try:
    import lancedb
except ImportError:
    lancedb = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

# --- Constants ---
GEMINI_EMBEDDING_MODEL = 'models/text-embedding-004'
GEMINI_EMBEDDING_TASK_TYPE = "RETRIEVAL_QUERY"  # For queries
GEMINI_EMBEDDING_DOC_TASK_TYPE = "RETRIEVAL_DOCUMENT"  # For documents
MAX_RESULTS = 5  # Maximum number of results to retrieve
# Get similarity threshold from environment variable or use default
SIMILARITY_THRESHOLD = float(os.environ.get('LANCEDB_SIMILARITY_THRESHOLD', '0.25'))  # Default: 0.25

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
        "When you need to search for information, do the search and provide the results directly without announcing that you will search."
    ]

    # Add guest name if available (either from parameter or property_context)
    if not guest_name and property_context:
        guest_name = property_context.get('guestName', '')

    if guest_name:
        prompt_parts[0] += f" The guest's name is {guest_name}. Use their name occasionally when responding to them."

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
    Generate embeddings for a given text using Gemini API.

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
            logging.error("Google Generative AI module not available")
            return None

        # Generate embedding using Gemini API
        embedding_result = genai.embed_content(
            model=GEMINI_EMBEDDING_MODEL,
            content=[text],  # API expects a list
            task_type=task_type
        )

        # Check if embedding was generated successfully
        if ('embedding' in embedding_result and
            isinstance(embedding_result['embedding'], list) and
            len(embedding_result['embedding']) > 0):
            return embedding_result['embedding'][0]
        else:
            logging.error(f"Failed to generate embedding. Response: {embedding_result}")
            return None
    except Exception as e:
        logging.error(f"Error generating embedding: {e}")
        traceback.print_exc()
        return None

def get_relevant_context(query_text, property_id, lancedb_path=None, limit=MAX_RESULTS, threshold=SIMILARITY_THRESHOLD):
    """
    Retrieve relevant context from LanceDB based on query text and property ID.
    Optimized with caching and connection reuse to reduce S3 requests.

    Args:
        query_text (str): The user's query or utterance
        property_id (str): The ID of the property to filter by
        lancedb_path (str): Path to LanceDB (defaults to app config)
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
            'qna_id': 'ee429b77-f83b-4ca9-8757-9b5f9870cb9a',
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
                'qna_id': 'ae59As0rkir81saz53zQ',
                'text': 'Question: How do I make coffee?\nAnswer: Place a K-Cup pod in the holder, close the lid, and press the \'brew\' button. Make sure to fill the water reservoir before starting.',
                'similarity': 0.95
            }
        else:
            # Default to coffee maker info
            coffee_item = {
                'qna_id': '3XOI7uFJTdYZ6oCjyjvR',
                'text': 'Question: What kind of coffee maker is provided?\nAnswer: The coffee maker is a Keurig machine. The model is RY-3214.',
                'similarity': 0.95
            }

        results['items'] = [coffee_item]
        results['context'] = coffee_item['text']
        return results

    try:
        # Check if LanceDB is available
        if lancedb is None:
            logging.error("LanceDB module not available")
            return results

        # Validate inputs
        if not query_text or not property_id:
            logging.warning(f"Invalid inputs: query_text='{query_text}', property_id='{property_id}'")
            return results

        # Get LanceDB path (from param, env, or default)
        if not lancedb_path:
            # Use the global constant which already handles environment variables
            lancedb_path = LANCEDB_S3_URI
            logging.info(f"Using LanceDB path from constant: {lancedb_path}")

            # Log additional debug info
            logging.info(f"FLASK_ENV: {os.environ.get('FLASK_ENV')}")
            logging.info(f"LANCEDB_S3_URI: {os.environ.get('LANCEDB_S3_URI')}")
            logging.info(f"LANCEDB_PATH: {os.environ.get('LANCEDB_PATH')}")

        # Get table name
        table_name = os.environ.get('LANCEDB_TABLE_NAME', LANCEDB_TABLE_NAME)

        # Check cache first if available
        if lancedb_cache is not None:
            cached_results = lancedb_cache.get(property_id, query_text, table_name)
            if cached_results is not None:
                logging.info(f"Using cached results for property_id={property_id}")
                return cached_results

        # Generate embedding for query (only if cache miss)
        logging.info(f"Generating embedding for query: '{query_text[:50]}...'")
        query_embedding = generate_embedding(query_text)
        if not query_embedding:
            logging.warning(f"Could not generate embedding for query: {query_text}")
            return results
        else:
            logging.info(f"Successfully generated embedding of length {len(query_embedding)}")

        # Connect to LanceDB - use cached connection if available
        logging.info(f"Connecting to LanceDB at: {lancedb_path}")
        if cached_connection is not None:
            db = cached_connection(lancedb_path)
        else:
            db = lancedb.connect(lancedb_path)

        if db is None:
            logging.error(f"Failed to connect to LanceDB at: {lancedb_path}")
            return results

        # Check if we have cached table schema
        if lancedb_cache is not None:
            table_schema = lancedb_cache.get_table_schema(table_name)
            if table_schema is None:
                # If not in cache, check if table exists and cache the schema
                table_names = db.table_names()
                logging.info(f"Available tables in LanceDB: {table_names}")

                if table_name not in table_names:
                    logging.warning(f"LanceDB table '{table_name}' does not exist")
                    return results

                # Cache the table names to avoid future lookups
                lancedb_cache.cache_table_schema(table_name, table_names)
            else:
                logging.debug(f"Using cached table schema for {table_name}")
        else:
            # No cache available, check if table exists
            table_names = db.table_names()
            if table_name not in table_names:
                logging.warning(f"LanceDB table '{table_name}' does not exist")
                return results

        # Open table - this is an expensive operation that hits S3
        logging.info(f"Opening table '{table_name}'")
        try:
            # Import the batch query function from cache_helpers if available
            try:
                from utils.cache_helpers import batch_query_lancedb
            except ImportError:
                try:
                    from concierge.utils.cache_helpers import batch_query_lancedb
                except ImportError:
                    batch_query_lancedb = None

            # Use batch query if available to reduce S3 requests
            if batch_query_lancedb is not None:
                logging.info("Using batch query to reduce S3 requests")
                batch_results = batch_query_lancedb(db, table_name, [query_embedding], property_id, limit)
                query_results = batch_results.get(0) if 0 in batch_results else None

                if query_results is None or query_results.empty:
                    logging.info(f"No relevant context found for property: {property_id}")

                    # Cache the empty results too to avoid redundant queries
                    if lancedb_cache is not None:
                        lancedb_cache.set(property_id, query_text, table_name, results)

                    return results
            else:
                # Fall back to standard query if batch function not available
                table = db.open_table(table_name)

                # Log the filter condition being used
                logging.info(f"Querying with filter: property_id = '{property_id}'")

                # Query for relevant items filtered by property_id
                query_results = (table.search(query_embedding)
                                .where(f"property_id = '{property_id}'")
                                .limit(limit)
                                .to_pandas())

                # Check if we got results
                if query_results.empty:
                    logging.info(f"No relevant context found for property: {property_id}")

                    # Cache the empty results too to avoid redundant queries
                    if lancedb_cache is not None:
                        lancedb_cache.set(property_id, query_text, table_name, results)

                    return results
        except Exception as table_err:
            logging.error(f"Error opening or querying table: {table_err}")
            return results

        # Filter results by similarity threshold
        if '_distance' in query_results.columns:
            # Convert distance to similarity (assuming cosine distance)
            query_results['raw_similarity'] = 1 - query_results['_distance']
            query_results['similarity'] = query_results['raw_similarity'].abs()

            # Log only a summary of results for debugging to reduce log volume
            logging.info(f"Found {len(query_results)} results with similarity range: {query_results['similarity'].min():.4f} to {query_results['similarity'].max():.4f}")

            # Use absolute value for filtering
            filtered_results = query_results[query_results['similarity'] >= threshold]

            if filtered_results.empty:
                logging.info(f"No results meet similarity threshold ({threshold})")

                # --- OPTIMIZED SPECIAL HANDLING FOR COMMON QUERIES ---
                # This allows retrieving results for common query types even with lower similarity scores
                query_lower = query_text.lower()

                # Define a function to check for term matches to reduce code duplication
                def check_term_matches(terms, description):
                    if any(term in query_lower for term in terms):
                        logging.info(f"Query is about {description}, checking for relevant entries despite low similarity")

                        # Check if 'question' column exists in the dataframe
                        if 'question' in query_results.columns:
                            term_results = query_results[query_results['question'].str.contains('|'.join(terms), case=False, regex=True)]

                            if not term_results.empty:
                                logging.info(f"Found {len(term_results)} {description} entries despite low similarity")
                                return term_results
                            else:
                                logging.info(f"No {description} entries found in results")
                        else:
                            logging.info(f"Cannot check for {description} entries: 'question' column not found")
                    return None

                # Check for matches in order of priority
                term_categories = [
                    (WIFI_RELATED_TERMS, "WiFi"),
                    (CONTACT_RELATED_TERMS, "contacting the host"),
                    (CHECKOUT_RELATED_TERMS, "checkout"),
                    (CHECKIN_RELATED_TERMS, "checkin"),
                    (PARKING_RELATED_TERMS, "parking"),
                    (TRASH_RELATED_TERMS, "trash/garbage"),
                    (FIRST_AID_RELATED_TERMS, "first aid"),
                    (COFFEE_RELATED_TERMS, "coffee/drinks"),
                    (LOCATION_RELATED_TERMS, "location/address")
                ]

                # Try each category in turn
                for terms, description in term_categories:
                    term_results = check_term_matches(terms, description)
                    if term_results is not None:
                        filtered_results = term_results
                        break

                # --- END OPTIMIZED SPECIAL HANDLING ---

                if filtered_results.empty:  # Still empty after special handling
                    # Cache the empty results too to avoid redundant queries
                    if lancedb_cache is not None:
                        lancedb_cache.set(property_id, query_text, table_name, results)
                    return results

            # Format results - optimized to reduce memory usage
            items = []
            context_parts = []

            # Limit the number of results to process to reduce memory usage
            max_results_to_process = min(limit, len(filtered_results))
            processed_results = filtered_results.head(max_results_to_process)

            for _, row in processed_results.iterrows():
                # Get text content with fallback
                if 'text' in row:
                    text_content = row['text']
                elif 'question' in row and 'answer' in row:
                    text_content = f"Question: {row['question']}\nAnswer: {row['answer']}"
                else:
                    # Skip rows without usable content
                    continue

                # Create item dictionary
                item = {
                    'qna_id': row.get('id', row.get('qna_id', 'unknown')),
                    'text': text_content,
                    'similarity': float(row.get('similarity', 0))
                }
                items.append(item)
                context_parts.append(text_content)

            # Join context parts
            context = "\n\n".join(context_parts)

            results['found'] = True
            results['context'] = context
            results['items'] = items

            # Cache the successful results
            if lancedb_cache is not None:
                lancedb_cache.set(property_id, query_text, table_name, results)

            return results
    except Exception as e:
        logging.error(f"Error retrieving context from LanceDB: {e}")
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

    # Add detailed instructions for using tools
    tools_instruction = (
        "AVAILABLE TOOLS:\n\n"
        "1. searchTool - Use this tool to search the web for real-time information.\n"
        "   - Use for: Location details, nearby attractions, restaurants, transportation options, current events\n"
        "   - ALWAYS use this tool when asked about: restaurants, attractions, things to do, weather, directions, transportation\n"
        "   - ALWAYS use this tool when you don't have specific information about something in the property context\n"
        "   - Example: When asked \"What restaurants are nearby?\", use searchTool with query \"restaurants near [property address]\"\n\n"
        "2. ragTool - Use this tool to retrieve specific property information.\n"
        "   - Use for: Property amenities, house rules, WiFi details, check-in/out procedures\n"
        "   - Example: When asked \"Where are extra towels kept?\", use ragTool with query \"extra towels\" and the property ID\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "- When a guest asks about the property location, nearby places, or surrounding area, you MUST use searchTool\n"
        "- When they ask about specific property details like amenities or house rules, you MUST use ragTool\n"
        "- If you don't know the answer and it's not in the provided context, ALWAYS use searchTool to find information\n"
        "- DO NOT make up information or say you don't have information without first trying to use searchTool\n"
        "- NEVER respond with \"I don't have that specific information\" without first using searchTool to try to find an answer"
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

    # Add detailed instructions for using tools
    tools_instruction = (
        "AVAILABLE TOOLS:\n\n"
        "1. searchTool - Use this tool to search the web for real-time information.\n"
        "   - Use for: Location details, nearby attractions, restaurants, transportation options, current events\n"
        "   - ALWAYS use this tool when asked about: restaurants, attractions, things to do, weather, directions, transportation\n"
        "   - ALWAYS use this tool when you don't have specific information about something in the property context\n"
        "   - Example: When asked \"What restaurants are nearby?\", use searchTool with query \"restaurants near [property address]\"\n\n"
        "2. ragTool - Use this tool to retrieve specific property information.\n"
        "   - Use for: Property amenities, house rules, WiFi details, check-in/out procedures\n"
        "   - Example: When asked \"Where are extra towels kept?\", use ragTool with query \"extra towels\" and the property ID\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "- When a guest asks about the property location, nearby places, or surrounding area, you MUST use searchTool\n"
        "- When they ask about specific property details like amenities or house rules, you MUST use ragTool\n"
        "- If you don't know the answer and it's not in the provided context, ALWAYS use searchTool to find information\n"
        "- DO NOT make up information or say you don't have information without first trying to use searchTool\n"
        "- NEVER respond with \"I don't have that specific information\" without first using searchTool to try to find an answer"
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

def process_query_with_rag(user_query, property_id, property_context=None, conversation_history=None):
    """
    Process a user query with RAG and return a response from Gemini.

    Args:
        user_query (str): The user's query or message
        property_id (str): The property ID
        property_context (dict, optional): Context about the property
        conversation_history (list, optional): Previous conversation messages

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
        logging.info(f"Processing query with RAG: query='{user_query}', property_id='{property_id}'")

        # Validate property_id
        if not property_id:
            logging.warning("No property_id provided for RAG lookup")
            result['response'] = "I don't have property-specific information available. Please make sure you're properly authenticated."
            return result

        # Get relevant context from LanceDB
        logging.info(f"Fetching context from LanceDB for property_id: {property_id}")
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

        # Format prompt with RAG context and conversation history
        prompt = format_prompt_with_rag(user_query, property_context, rag_results, conversation_history)
        logging.info(f"Generated prompt length: {len(prompt)} characters")

        # Log key parts of the prompt for debugging (without exposing sensitive info)
        if len(prompt) > 1000:
            # Log first 200 and last 200 characters to avoid excessive logging
            logging.info(f"Prompt start: {prompt[:200]}...")
            logging.info(f"Prompt end: ...{prompt[-200:]}")
        else:
            logging.info(f"Full prompt: {prompt}")

        # Generate response from Gemini with Google Search tool
        model = genai.GenerativeModel('gemini-2.0-flash')

        # Configure Google Search tool for Gemini
        try:
            # Add Google Search tool using the correct format for Gemini 2.0
            logging.info("Adding Google Search tool to Gemini request")

            # Use the native Google Search tool format for Gemini 2.0
            tools = [{"google_search": {}}]

            # Generate response with Google Search tool
            response = model.generate_content(
                prompt,
                tools=tools
            )

            logging.info("Successfully called Gemini with Google Search and RAG tools")

        except Exception as tool_error:
            # Fallback to regular generation if tool setup fails
            logging.error(f"Error setting up Google Search tool: {tool_error}")
            logging.warning("Falling back to standard Gemini generation without Google Search tool")
            response = model.generate_content(prompt)

        if response and hasattr(response, 'text'):
            result['response'] = response.text
            result['has_context'] = rag_results.get('found', False)
            if rag_results.get('items'):
                result['context_used'] = rag_results['items']

            # Log the response (truncated for readability)
            response_text = response.text
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
            logging.error(f"Empty or invalid response from Gemini: {response}")
            result['response'] = "I'm sorry, I'm having trouble processing your request. Can you please try again?"

        return result

    except Exception as e:
        logging.error(f"Error processing query with RAG: {e}")
        traceback.print_exc()
        result['response'] = "I'm sorry, I'm having trouble accessing the information you need. How else can I assist you?"

    return result

# === Enhanced function: Check if item exists in LanceDB and verify content match ===
def check_item_in_lancedb_with_content(property_id: str, item_id: str, dynamo_question: str = None,
                                       dynamo_answer: str = None, lancedb_path: str = None) -> dict:
    """
    Checks if a specific knowledge item exists in LanceDB and verifies content match with DynamoDB.

    Args:
        property_id (str): The ID of the property.
        item_id (str): The ID of the knowledge item.
        dynamo_question (str, optional): The question text from DynamoDB to compare against.
        dynamo_answer (str, optional): The answer text from DynamoDB to compare against.
        lancedb_path (str): Path to LanceDB (defaults to env var or local path).

    Returns:
        dict: A dictionary containing:
            - 'exists' (bool): True if the item exists in LanceDB
            - 'content_match' (bool): True if question and answer content matches (or None if item doesn't exist)
            - 'details' (dict): Details about content mismatches if any
    """
    result = {
        'exists': False,
        'content_match': None,
        'details': {}
    }

    try:
        # Check if LanceDB is available
        if lancedb is None:
            logging.warning("LanceDB module not available for check.")
            result['details']['error'] = "LanceDB module not available"
            return result

        # Validate inputs
        if not property_id or not item_id:
            logging.warning(f"Invalid inputs for LanceDB check: property_id='{property_id}', item_id='{item_id}'")
            result['details']['error'] = "Invalid inputs (missing property_id or item_id)"
            return result

        # Get LanceDB path (from param, env, or default)
        if not lancedb_path:
            # First check for S3 URI which should be used in production
            if os.environ.get('LANCEDB_S3_URI'):
                lancedb_path = os.environ.get('LANCEDB_S3_URI')
                logging.info(f"Using S3 LanceDB path: {lancedb_path}")
            # Then check for explicit local path
            elif os.environ.get('LANCEDB_PATH'):
                lancedb_path = os.environ.get('LANCEDB_PATH')
                logging.info(f"Using explicit local LanceDB path: {lancedb_path}")
            # Finally fall back to default local path
            else:
                lancedb_path = './.lancedb'
                logging.info(f"Using default local LanceDB path: {lancedb_path}")

            # Log additional debug info
            logging.info(f"FLASK_ENV: {os.environ.get('FLASK_ENV')}")
            logging.info(f"LANCEDB_S3_URI: {os.environ.get('LANCEDB_S3_URI')}")
            logging.info(f"LANCEDB_PATH: {os.environ.get('LANCEDB_PATH')}")

        logging.info(f"LanceDB content check: Using path: {lancedb_path} for item check.")

        # Connect to LanceDB
        logging.info(f"Connecting to LanceDB at: {lancedb_path} for content check.")
        db = lancedb.connect(lancedb_path)

        # Get list of all tables
        table_names = db.table_names()
        logging.info(f"Available tables in LanceDB: {table_names}")

        # Get the default table name
        default_table_name = os.environ.get('LANCEDB_TABLE_NAME', LANCEDB_TABLE_NAME)

        # Tables to check in order of priority
        tables_to_check = []

        # First add property-specific table if it exists
        property_table = f"knowledge_{property_id}"
        if property_table in table_names:
            tables_to_check.append(property_table)

        # Then add the default table if it exists
        if default_table_name in table_names and default_table_name not in tables_to_check:
            tables_to_check.append(default_table_name)

        # Then add other tables that have "knowledge" in the name, excluding any backup tables
        for table_name in table_names:
            if (table_name not in tables_to_check and
                "knowledge" in table_name.lower() and
                "backup" not in table_name.lower()):
                tables_to_check.append(table_name)

        logging.info(f"Will check for item in these tables: {tables_to_check}")

        if not tables_to_check:
            logging.warning(f"No suitable knowledge tables found in LanceDB.")
            result['details']['error'] = "No suitable knowledge tables found"
            return result

        # Check each table for the item
        for table_name in tables_to_check:
            try:
                logging.info(f"Checking table '{table_name}' for item {item_id}...")
                table = db.open_table(table_name)

                # Try to get the item with a direct query
                # First try with the exact ID
                query_result = table.search().where(f"id = '{item_id}'").to_pandas()

                # If not found, try with just the UUID part (in case of prefix#uuid format)
                if query_result.empty and '#' in item_id:
                    # Extract the UUID part (last part after #)
                    uuid_part = item_id.split('#')[-1]
                    logging.info(f"Item not found with full ID '{item_id}', trying with UUID part '{uuid_part}'")
                    query_result = table.search().where(f"id = '{uuid_part}'").to_pandas()

                # If we found the item, check content match
                if not query_result.empty:
                    result['exists'] = True
                    result['details']['table'] = table_name

                    # Store the actual ID found in LanceDB
                    result['details']['lancedb_id'] = query_result.iloc[0].get('id', '')

                    # Get the item data
                    lance_item = query_result.iloc[0]

                    # If we have dynamo_question and dynamo_answer, check content match
                    if dynamo_question is not None and dynamo_answer is not None:
                        lance_question = lance_item.get('question', '')
                        lance_answer = lance_item.get('answer', '')

                        # Check content match
                        question_match = dynamo_question.strip() == lance_question.strip()
                        answer_match = dynamo_answer.strip() == lance_answer.strip()

                        result['content_match'] = question_match and answer_match

                        # Add details if content doesn't match
                        if not result['content_match']:
                            result['details']['mismatches'] = {
                                'question_match': question_match,
                                'answer_match': answer_match
                            }

                            if not question_match:
                                result['details']['lance_question'] = lance_question

                            if not answer_match:
                                result['details']['lance_answer'] = lance_answer

                    return result

            except Exception as table_err:
                logging.warning(f"Error checking table '{table_name}': {table_err}")
                result['details']['table_error'] = str(table_err)
                continue

        # If we get here, the item wasn't found in any table
        logging.warning(f"Item '{item_id}' for property '{property_id}' not found in any LanceDB table.")
        return result

    except Exception as e:
        # Log the error
        logging.warning(f"Error checking item '{item_id}' for property '{property_id}' in LanceDB: {e}")
        import traceback
        traceback.print_exc()
        result['details']['error'] = str(e)
        return result

# === FIXED FUNCTION: Check if specific item exists in LanceDB ===
def check_item_in_lancedb(property_id: str, item_id: str, lancedb_path: str = None) -> bool:
    """
    Checks if a specific knowledge item (identified by item_id) exists in LanceDB
    for the given property_id.

    Args:
        property_id (str): The ID of the property.
        item_id (str): The ID of the knowledge item (should match Firestore doc ID).
        lancedb_path (str): Path to LanceDB (defaults to env var or local path).

    Returns:
        bool: True if the item exists, False otherwise.
    """
    # Use our enhanced function but only return the 'exists' boolean
    result = check_item_in_lancedb_with_content(property_id, item_id, lancedb_path=lancedb_path)
    return result['exists']

# === NEW BATCH FUNCTION: Check multiple items in LanceDB in a single query ===
def batch_check_items_in_lancedb(property_id: str, items: list, lancedb_path: str = None, force_refresh: bool = False) -> dict:
    """
    Efficiently checks multiple knowledge items in LanceDB with a single connection.
    This reduces S3 requests significantly compared to checking items individually.

    Args:
        property_id (str): The ID of the property.
        items (list): List of dictionaries containing knowledge items with at least 'id', 'Question', and 'Answer' fields.
        lancedb_path (str): Path to LanceDB (defaults to env var or local path).
        force_refresh (bool): If True, ignore cache and force a fresh check.

    Returns:
        dict: A dictionary mapping item IDs to their LanceDB status:
            {
                'item_id': {
                    'exists': bool,
                    'content_match': bool or None,
                    'details': dict with any mismatch details
                },
                ...
            }
    """
    results = {}

    # Initialize all items with default values
    for item in items:
        item_id = item.get('SK', '').split('#')[-1] if item.get('SK') else ''
        if not item_id:
            continue

        results[item_id] = {
            'exists': False,
            'content_match': None,
            'details': {}
        }

    try:
        # Check if LanceDB is available
        if lancedb is None:
            logging.warning("LanceDB module not available for batch check.")
            return results

        # Validate inputs
        if not property_id or not items:
            logging.warning(f"Invalid inputs for batch LanceDB check: property_id='{property_id}', items count={len(items) if items else 0}")
            return results

        # Determine LanceDB path
        if lancedb_path is None:
            # Use the global constant which already handles environment variables
            lancedb_path = LANCEDB_S3_URI
            logging.info(f"Using LanceDB path from constant: {lancedb_path}")

        logging.info(f"LanceDB batch check: Using path: {lancedb_path} for {len(items)} items")

        # Connect to LanceDB - use cached connection if available
        if cached_connection is not None:
            db = cached_connection(lancedb_path)
        else:
            db = lancedb.connect(lancedb_path)

        if db is None:
            logging.error(f"Failed to connect to LanceDB at: {lancedb_path}")
            return results

        # Get list of all tables
        table_names = db.table_names()
        logging.info(f"Available tables in LanceDB: {table_names}")

        # Get the default table name
        default_table_name = os.environ.get('LANCEDB_TABLE_NAME', LANCEDB_TABLE_NAME)

        # Tables to check in order of priority
        tables_to_check = []

        # First add the default table if it exists
        if default_table_name in table_names:
            tables_to_check.append(default_table_name)

        # Then add property-specific table if it exists
        property_table = f"knowledge_{property_id}"
        if property_table in table_names and property_table not in tables_to_check:
            tables_to_check.append(property_table)

        # Then add other tables that have "knowledge" in the name, excluding any backup tables
        for table_name in table_names:
            if (table_name not in tables_to_check and
                "knowledge" in table_name.lower() and
                "backup" not in table_name.lower()):
                tables_to_check.append(table_name)

        logging.info(f"Will check for items in these tables: {tables_to_check}")

        if not tables_to_check:
            logging.warning(f"No suitable knowledge tables found in LanceDB.")
            return results

        # Check each table for the items
        for table_name in tables_to_check:
            try:
                logging.info(f"Checking table '{table_name}' for {len(items)} items...")

                # Get all item IDs to check
                item_ids = []
                uuid_parts = {}  # Map from UUID part to original item ID

                for item in items:
                    item_id = item.get('SK', '').split('#')[-1] if item.get('SK') else ''
                    if not item_id:
                        continue

                    item_ids.append(item_id)

                    # If the ID contains '#', also check with just the UUID part
                    if '#' in item_id:
                        uuid_part = item_id.split('#')[-1]
                        uuid_parts[uuid_part] = item_id

                if not item_ids:
                    continue

                # Check if we have cached results for these items (unless force_refresh is True)
                cached_results = {}
                if lancedb_cache is not None and not force_refresh:
                    cached_results = lancedb_cache.batch_get(property_id, item_ids, table_name)

                # If we have cached results for all items, use them
                if cached_results and len(cached_results) == len(item_ids):
                    logging.info(f"Batch cache HIT for {property_id} with {len(item_ids)} items")

                    # Process cached results
                    for item_id, exists in cached_results.items():
                        if exists:
                            results[item_id]['exists'] = True
                            results[item_id]['details']['table'] = table_name

                    # Skip to next table
                    continue
                else:
                    logging.info(f"Batch cache MISS for {property_id} with {len(item_ids)} items")

                # If we get here, we need to query LanceDB
                # Import the batch check function from cache_helpers if available
                try:
                    from utils.cache_helpers import batch_check_items_existence
                except ImportError:
                    try:
                        from concierge.utils.cache_helpers import batch_check_items_existence
                    except ImportError:
                        batch_check_items_existence = None

                # Use batch check if available
                if batch_check_items_existence is not None:
                    logging.info(f"Using batch_check_items_existence for {len(item_ids)} items")

                    # Combine original IDs and UUID parts for a single query
                    all_ids_to_check = item_ids + list(uuid_parts.keys())

                    # Split into smaller batches if there are too many IDs to avoid query size limits
                    batch_size = 50  # Adjust based on your database limits
                    existence_results = {}

                    for i in range(0, len(all_ids_to_check), batch_size):
                        batch_ids = all_ids_to_check[i:i+batch_size]
                        logging.info(f"Checking batch {i//batch_size + 1} with {len(batch_ids)} IDs")

                        batch_results = batch_check_items_existence(db, table_name, batch_ids)
                        existence_results.update(batch_results)

                    # Cache the results
                    if lancedb_cache is not None:
                        lancedb_cache.batch_set(property_id, existence_results, table_name)

                    # Process existence results
                    for item_id in item_ids:
                        if existence_results.get(item_id, False):
                            results[item_id]['exists'] = True
                            results[item_id]['details']['table'] = table_name
                            results[item_id]['details']['lancedb_id'] = item_id

                    # Check UUID parts
                    for uuid_part, original_id in uuid_parts.items():
                        if existence_results.get(uuid_part, False):
                            results[original_id]['exists'] = True
                            results[original_id]['details']['table'] = table_name
                            results[original_id]['details']['lancedb_id'] = uuid_part

                    # For items that exist, we need to get their content to check for matches
                    existing_items = [item_id for item_id, result in results.items() if result.get('exists', False)]

                    if existing_items:
                        # Open the table to get content
                        table = db.open_table(table_name)

                        # Process existing items in batches to avoid query size limits
                        for i in range(0, len(existing_items), batch_size):
                            batch_existing_items = existing_items[i:i+batch_size]
                            logging.info(f"Checking content for batch {i//batch_size + 1} with {len(batch_existing_items)} existing items")

                            # Build a WHERE clause for this batch of existing items
                            where_clause = " OR ".join([f"id = '{item_id}'" for item_id in batch_existing_items])

                            # Add UUID parts for existing items in this batch
                            batch_uuid_parts = [uuid_part for uuid_part, original_id in uuid_parts.items()
                                              if original_id in batch_existing_items and results[original_id].get('exists', False)]
                            if batch_uuid_parts:
                                where_clause += " OR " + " OR ".join([f"id = '{uuid_part}'" for uuid_part in batch_uuid_parts])

                            logging.info(f"Executing content query for batch with WHERE clause: {where_clause[:100]}...")
                            batch_query_result = table.search().where(where_clause).to_pandas()

                            if not batch_query_result.empty:
                                # Process each found item in this batch
                                for _, lance_item in batch_query_result.iterrows():
                                    lance_id = lance_item.get('id', '')

                                    # Determine the original item ID
                                    original_id = None
                                    if lance_id in item_ids:
                                        original_id = lance_id
                                    elif lance_id in uuid_parts:
                                        original_id = uuid_parts[lance_id]

                                    if not original_id:
                                        logging.warning(f"Found item with ID '{lance_id}' but can't match to original items")
                                        continue

                                    # Find the original item
                                    original_item = None
                                    for item in items:
                                        item_id = item.get('SK', '').split('#')[-1] if item.get('SK') else ''
                                        if item_id == original_id:
                                            original_item = item
                                            break

                                    if not original_item:
                                        logging.warning(f"Can't find original item for ID '{original_id}'")
                                        continue

                                    # Check content match
                                    dynamo_question = original_item.get('Question', '')
                                    dynamo_answer = original_item.get('Answer', '')

                                    lance_question = lance_item.get('question', '')
                                    lance_answer = lance_item.get('answer', '')

                                    # Check content match
                                    question_match = dynamo_question.strip() == lance_question.strip()
                                    answer_match = dynamo_answer.strip() == lance_answer.strip()

                                    results[original_id]['content_match'] = question_match and answer_match

                                    # Add details if content doesn't match
                                    if not results[original_id]['content_match']:
                                        results[original_id]['details']['mismatches'] = {
                                            'question_match': question_match,
                                            'answer_match': answer_match
                                        }

                                        if not question_match:
                                            results[original_id]['details']['lance_question'] = lance_question

                                        if not answer_match:
                                            results[original_id]['details']['lance_answer'] = lance_answer
                    else:
                        # No existing items, skip content check
                        logging.info("No existing items found, skipping content check")
                else:
                    # Fall back to standard query
                    table = db.open_table(table_name)

                    # Process items in batches to avoid query size limits
                    batch_size = 50  # Adjust based on your database limits

                    for i in range(0, len(item_ids), batch_size):
                        batch_item_ids = item_ids[i:i+batch_size]
                        logging.info(f"Checking batch {i//batch_size + 1} with {len(batch_item_ids)} IDs")

                        # First check with exact IDs
                        where_clause = " OR ".join([f"id = '{item_id}'" for item_id in batch_item_ids])

                        # Add UUID parts for this batch if any
                        batch_uuid_parts = {k: v for k, v in uuid_parts.items() if v in batch_item_ids}
                        if batch_uuid_parts:
                            where_clause += " OR " + " OR ".join([f"id = '{uuid_part}'" for uuid_part in batch_uuid_parts.keys()])

                        logging.info(f"Executing batch query with WHERE clause: {where_clause[:100]}...")
                        batch_query_result = table.search().where(where_clause).to_pandas()

                        if not batch_query_result.empty:
                            logging.info(f"Found {len(batch_query_result)} items in batch")

                            # Process each found item in this batch
                            for _, lance_item in batch_query_result.iterrows():
                                lance_id = lance_item.get('id', '')

                                # Determine the original item ID
                                original_id = None
                                if lance_id in item_ids:
                                    original_id = lance_id
                                elif lance_id in uuid_parts:
                                    original_id = uuid_parts[lance_id]

                                if not original_id:
                                    logging.warning(f"Found item with ID '{lance_id}' but can't match to original items")
                                    continue

                                # Find the original item
                                original_item = None
                                for item in items:
                                    item_id = item.get('SK', '').split('#')[-1] if item.get('SK') else ''
                                    if item_id == original_id:
                                        original_item = item
                                        break

                                if not original_item:
                                    logging.warning(f"Can't find original item for ID '{original_id}'")
                                    continue

                                # Mark as existing
                                results[original_id]['exists'] = True
                                results[original_id]['details']['table'] = table_name
                                results[original_id]['details']['lancedb_id'] = lance_id

                                # Check content match
                                dynamo_question = original_item.get('Question', '')
                                dynamo_answer = original_item.get('Answer', '')

                                lance_question = lance_item.get('question', '')
                                lance_answer = lance_item.get('answer', '')

                                # Check content match
                                question_match = dynamo_question.strip() == lance_question.strip()
                                answer_match = dynamo_answer.strip() == lance_answer.strip()

                                results[original_id]['content_match'] = question_match and answer_match

                                # Add details if content doesn't match
                                if not results[original_id]['content_match']:
                                    results[original_id]['details']['mismatches'] = {
                                        'question_match': question_match,
                                        'answer_match': answer_match
                                    }

                                    if not question_match:
                                        results[original_id]['details']['lance_question'] = lance_question

                                    if not answer_match:
                                        results[original_id]['details']['lance_answer'] = lance_answer

            except Exception as table_err:
                logging.warning(f"Error checking table '{table_name}': {table_err}")
                traceback.print_exc()
                continue

        # Log a summary of the results
        existing_count = sum(1 for result in results.values() if result.get('exists', False))
        mismatch_count = sum(1 for result in results.values() if result.get('content_match') is False)
        logging.info(f"Batch check summary: {len(results)} items checked, {existing_count} exist in LanceDB, {mismatch_count} have content mismatches")

        return results

    except Exception as e:
        # Log the error
        logging.warning(f"Error in batch check for property '{property_id}': {e}")
        import traceback
        traceback.print_exc()
        return results
