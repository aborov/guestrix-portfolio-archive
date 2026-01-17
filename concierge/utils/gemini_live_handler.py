"""
Gemini Live API handler for real-time voice interactions.

This module provides functionality to interact with Gemini Live API for voice-based AI.
It adapts code from the gemini_live_test.py script to work with Socket.IO handlers.
"""

import asyncio
import base64
import io
import traceback
import os
import threading
import queue
import logging
import sys
from datetime import datetime, timezone

# Import Google Generative AI
try:
    from google import generativeai as genai
    from google.generativeai import types
except ImportError:
    # Fallback import
    import google.generativeai as genai
    from google.generativeai import types

from .ai_helpers import get_relevant_context, format_prompt_with_rag, get_current_time, GEMINI_FUNCTION_DECLARATIONS

# Setup detailed logging for the handler
handler_logger = logging.getLogger('gemini_live_handler')
handler_logger.setLevel(logging.INFO)
# Add file handler if not already added
if not any(isinstance(h, logging.FileHandler) for h in handler_logger.handlers):
    try:
        file_handler = logging.FileHandler('/var/log/gemini_live_handler.log')
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        handler_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to set up file logging for gemini_live_handler: {e}")
        # Fall back to using the root logger
        handler_logger = logging

# Log startup information
handler_logger.info("=" * 80)
handler_logger.info("Gemini Live Handler Initializing")
handler_logger.info(f"Python version: {sys.version}")
handler_logger.info(f"Google Generative AI version: {genai.__version__ if hasattr(genai, '__version__') else 'unknown'}")
handler_logger.info("=" * 80)

# --- Constants ---
GEMINI_LIVE_MODEL = "models/gemini-2.0-flash-live-001"
AUDIO_SAMPLE_RATE = 24000  # For Gemini Live output

# Map of active sessions
# sid -> {
#   'session': gemini_live_session,
#   'audio_queue': queue.Queue(),  # Audio from Gemini to client
#   'property_id': str,
#   'property_context': dict,
#   'task': asyncio.Task  # Background task managing the session
# }
active_sessions = {}

# --- Session Management ---

async def create_gemini_live_session(sid, property_id, property_context=None, db_firestore=None, caller_number=None):
    """
    Create a new Gemini Live session for a client.

    Args:
        sid (str): Socket.IO session ID
        property_id (str): Property ID for context retrieval
        property_context (dict, optional): Property details
        db_firestore (object, optional): Firestore client for conversation storage
        caller_number (str, optional): Phone number of the caller for phone calls

    Returns:
        bool: Success status
    """
    try:
        # Check if API key is configured
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            handler_logger.error("GEMINI_API_KEY not found in environment variables")
            return False

        # Create Gemini client
        client = genai.Client(http_options={"api_version": "v1alpha"}, api_key=api_key)

        # Configure response modalities (audio) with transcription enabled and function calling
        config = types.LiveConnectConfig(
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            ),
            # Enable transcription for both input and output audio
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            # Add function calling tools
            tools=[{"function_declarations": GEMINI_FUNCTION_DECLARATIONS}]
        )

        # Set up queue for audio chunks
        audio_queue = queue.Queue()

        # Ensure property_context is a dictionary
        if property_context is None:
            property_context = {}

        # Try to get guest name from active sessions or Firestore reservations
        guest_name = property_context.get('guestName', '')

        # If caller number is provided, try to find guest name from Firestore
        if not guest_name and caller_number:
            try:
                # Import Firestore client functions dynamically to avoid circular imports
                import importlib.util
                spec = importlib.util.find_spec('utils.firestore_client')
                if spec:
                    firestore_client = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(firestore_client)

                    # Look up reservations by phone number
                    reservations = firestore_client.find_reservations_by_phone(caller_number)
                    if reservations:
                        # Use the first reservation's guest name
                        # Try different field names for guest name
                        guest_name = (
                            reservations[0].get('guestName') or
                            reservations[0].get('GuestName') or
                            reservations[0].get('guest_name')
                        )
                        if guest_name:
                            property_context['guestName'] = guest_name
                            handler_logger.info(f"Found guest name from Firestore for caller {caller_number}: {guest_name}")

                            # If property_id is not provided but found in reservation, use it
                            if not property_id:
                                property_id = (
                                    reservations[0].get('propertyId') or
                                    reservations[0].get('PropertyId') or
                                    reservations[0].get('property_id') or
                                    reservations[0].get('property')
                                )
                                if property_id:
                                    handler_logger.info(f"Found property ID from Firestore for caller {caller_number}: {property_id}")
            except Exception as e:
                handler_logger.error(f"Error finding guest name for caller {caller_number} in Firestore: {e}")
                handler_logger.error(traceback.format_exc())
                # Continue without guest name

        # If guest name still not found and we have Firestore, check for a reservation
        if not guest_name and db_firestore and property_id:
            try:
                # Check for an active reservation for this property
                from datetime import datetime
                now = datetime.now()

                # Query reservations for this property that are currently active
                reservations_ref = db_firestore.collection('reservations')
                query = reservations_ref.where('propertyId', '==', property_id) \
                                      .where('startDate', '<=', now) \
                                      .where('endDate', '>=', now) \
                                      .limit(1)

                reservation_docs = query.get()

                for doc in reservation_docs:
                    res_data = doc.to_dict()
                    if 'guestName' in res_data:
                        guest_name = res_data['guestName']
                        property_context['guestName'] = guest_name
                        logging.info(f"Found guest name from Firestore reservation: {guest_name}")
                    break  # Just get the first one

            except Exception as e:
                logging.error(f"Error fetching reservation info from Firestore: {e}")
                # Continue without guest name

        # Store in active sessions
        active_sessions[sid] = {
            'session': None,  # Will be set once connected
            'audio_queue': audio_queue,
            'property_id': property_id,
            'property_context': property_context,
            'db_firestore': db_firestore,
            'caller_number': caller_number,  # Store caller's phone number if available
            'task': None,  # Will be set once task starts
            'conversation_history': [],  # Store conversation segments
            'last_context_used': None,  # Last used context
        }

        # Start background task for session management
        loop = asyncio.get_event_loop()
        task = loop.create_task(
            manage_gemini_live_session(sid, client, config, property_id, caller_number)
        )
        active_sessions[sid]['task'] = task

        return True
    except Exception as e:
        logging.error(f"Error creating Gemini Live session: {e}")
        traceback.print_exc()
        return False

async def manage_gemini_live_session(sid, client, config, property_id, caller_number=None):
    """
    Manage the Gemini Live session in a background task.

    Args:
        sid (str): Socket.IO session ID
        client (genai.Client): Gemini client
        config (types.LiveConnectConfig): Session configuration
        property_id (str): Property ID for context
        caller_number (str, optional): Phone number of the caller for phone calls
    """
    try:
        # Start the Gemini Live session
        async with client.aio.live.connect(model=GEMINI_LIVE_MODEL, config=config) as session:
            # Store the session in the active sessions map
            if sid in active_sessions:
                active_sessions[sid]['session'] = session
                handler_logger.info(f"Gemini Live session started for {sid}")

                # Get initial property context (if available)
                session_info = active_sessions[sid]
                property_context = session_info.get('property_context', {})

                # Extract guest name
                guest_name = property_context.get('guestName', 'Guest')

                # Fetch detailed property information if needed
                if not property_context or len(property_context) < 3:  # Only has minimal info
                    try:
                        # Import function dynamically to avoid circular imports
                        import importlib.util
                        spec = importlib.util.find_spec('utils.ai_helpers')
                        if spec:
                            ai_helpers = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(ai_helpers)

                            # Try to get more detailed property info from Firestore
                            from concurrent.futures import ThreadPoolExecutor
                            with ThreadPoolExecutor() as executor:
                                # Retrieve property info from Firestore in a thread
                                from concierge.utils.firestore_client import get_firestore_client
                                db = get_firestore_client()
                                prop_ref = db.collection('properties').document(property_id)
                                prop_doc = await asyncio.to_thread(prop_ref.get)

                                if prop_doc.exists:
                                    prop_data = prop_doc.to_dict()
                                    # Update with more complete property information
                                    property_context.update({
                                        'name': prop_data.get('name', property_context.get('name', f'Property {property_id}')),
                                        'hostName': prop_data.get('hostName', property_context.get('hostName', 'the host')),
                                        'location': prop_data.get('location', property_context.get('location', '')),
                                        'address': prop_data.get('address', ''),
                                        'description': prop_data.get('description', ''),
                                        'property_id': property_id  # Ensure property_id is included for timezone detection
                                    })

                                    # Extract timezone from multiple possible keys
                                    tz_keys = ['timezone', 'timeZone', 'TimeZone', 'tz', 'TZ', 'localTimezone', 'localTimeZone']
                                    tz_value = None
                                    for k in tz_keys:
                                        if k in prop_data and prop_data[k]:
                                            tz_value = prop_data[k]
                                            break
                                    if tz_value:
                                        property_context['timezone'] = tz_value
                                        handler_logger.info(f"Found timezone in property data: {tz_value}")
                                    else:
                                        handler_logger.warning(f"No timezone found in property data for {property_id}")

                                    # Add WiFi details if available
                                    if 'wifiDetails' in prop_data and isinstance(prop_data['wifiDetails'], dict):
                                        wifi = prop_data['wifiDetails']
                                        property_context['wifiNetwork'] = wifi.get('network', '')
                                        property_context['wifiPassword'] = wifi.get('password', '')

                                    # Update session info with enhanced property context
                                    session_info['property_context'] = property_context
                                    logging.info(f"Enhanced property context for {sid} with Firestore data")
                    except Exception as e:
                        logging.error(f"Error fetching enhanced property info: {e}")
                        # Continue with limited property context

                # Build a more comprehensive initial greeting
                property_name = property_context.get('name', f'Property {property_id}')
                is_fallback = property_context.get('fallback', False)

                # Create a more detailed initial prompt with property details
                greeting_parts = []

                # Handle fallback case (no property ID found)
                if is_fallback:
                    greeting_parts.append(f"You are Staycee, a helpful concierge assistant answering a phone call.")
                    greeting_parts.append(f"The caller's phone number is {caller_number}.")
                    greeting_parts.append("You don't have information about which property the caller is associated with.")
                    greeting_parts.append("Politely ask the caller which property they're calling about and their name.")
                    greeting_parts.append("Explain that you need this information to provide them with specific details about their stay.")
                    greeting_parts.append("Once they provide the property name, tell them you'll look it up and transfer them to the right assistant.")
                # Normal case with property information
                else:
                    # Add phone call specific greeting if this is a phone call
                    if caller_number:
                        greeting_parts.append(f"You are Staycee, a helpful concierge assistant for {property_name}, answering a phone call.")
                        greeting_parts.append(f"The caller's phone number is {caller_number}.")
                    else:
                        greeting_parts.append(f"You are Staycee, a helpful concierge assistant for {property_name}.")

                    if guest_name:
                        greeting_parts.append(f"The guest's name is {guest_name}. Address them by name occasionally in your responses.")

                # Add any available property details
                if 'location' in property_context and property_context['location']:
                    greeting_parts.append(f"The property is located at {property_context['location']}.")

                if 'wifiNetwork' in property_context and 'wifiPassword' in property_context:
                    greeting_parts.append(f"The WiFi network is {property_context['wifiNetwork']} and the password is {property_context['wifiPassword']}.")

                # Fetch property knowledge items from Firestore (skip in fallback case)
                if not is_fallback and property_id != "unknown":
                    try:
                        handler_logger.info(f"Fetching knowledge items for property {property_id}")
                        # Get Firestore client
                        from concierge.utils.firestore_client import get_firestore_client
                        db = get_firestore_client()

                        # Query knowledge items for this property
                        knowledge_ref = db.collection('knowledge')
                        query = knowledge_ref.where('propertyId', '==', property_id)
                        knowledge_docs = query.stream()

                        # Format knowledge items based on their type
                        formatted_knowledge_items = []
                        for doc in knowledge_docs:
                            item = doc.to_dict()
                            item_id = doc.id

                            # Only include items with status 'active' or 'approved'
                            status = item.get('status', '')
                            if status.lower() not in ['active', 'approved']:
                                continue

                            # Get content and type
                            content = item.get('content', '')
                            item_type = item.get('type', '')
                            tags = item.get('tags', [])

                            if not content:
                                continue

                            # Format based on type
                            if item_type.lower() == 'qa' or item_type.lower() == 'q&a':
                                # Try to extract question and answer
                                if 'question' in item and 'answer' in item:
                                    question = item.get('question', '')
                                    answer = item.get('answer', '')
                                    if question and answer:
                                        formatted_knowledge_items.append(f"Q: {question}\nA: {answer}")
                                else:
                                    # Assume content is already in Q&A format
                                    formatted_knowledge_items.append(content)
                            elif item_type.lower() == 'instruction':
                                # Format as instruction
                                formatted_knowledge_items.append(f"INSTRUCTION: {content}")
                            elif item_type.lower() == 'info':
                                # Format as information with tags
                                tag_str = ', '.join(tags) if tags else 'general'
                                formatted_knowledge_items.append(f"INFO ({tag_str}): {content}")
                            elif item_type.lower() == 'places':
                                # Format as places information
                                formatted_knowledge_items.append(f"PLACES: {content}")
                            else:
                                # Default format with type and tags
                                tag_str = ', '.join(tags) if tags else ''
                                type_tag = f"{item_type.upper()}{' - ' + tag_str if tag_str else ''}"
                                formatted_knowledge_items.append(f"{type_tag}: {content}")

                        # Add formatted knowledge items to the prompt
                        if formatted_knowledge_items:
                            knowledge_text = "\n\n".join(formatted_knowledge_items)
                            greeting_parts.append(f"\nProperty Knowledge Base:\n{knowledge_text}")
                            handler_logger.info(f"Added {len(formatted_knowledge_items)} knowledge items from Firestore to system prompt")
                    except Exception as e:
                        handler_logger.error(f"Error fetching knowledge items: {e}")
                        handler_logger.error(traceback.format_exc())
                        # Continue without knowledge items

                # Add instructions for tool usage (different for fallback case)
                if is_fallback:
                    greeting_parts.append("IMPORTANT: You don't have access to property information since you don't know which property the caller is associated with.")
                    greeting_parts.append("Focus on identifying the property and the caller's name. Don't try to answer specific questions about a property until you have this information.")
                    greeting_parts.append("Once you have the property information, let the caller know you'll transfer them to the right assistant.")

                    # Add final greeting instruction for fallback
                    greeting_parts.append("Greet the caller warmly, explain that you're the Guestrix concierge assistant, and ask which property they're calling about. Keep your response brief and friendly.")
                else:
                    greeting_parts.append("IMPORTANT: You have access to the following tools:")
                    greeting_parts.append("1. queryKnowledgeBase: Use this tool when you need specific information about amenities, check-in/out times, house rules, or local attractions.")
                    greeting_parts.append("2. get_current_time: Use this function when guests ask about the current time, date, or when you need to provide time-sensitive information. This will give you the accurate current time in the property's timezone.")
                    greeting_parts.append("When asked for information you don't have, say you'll look it up, then use the appropriate tool to search for the answer.")
                    greeting_parts.append("When guests ask 'what time is it' or similar time-related questions, use the get_current_time function to provide accurate timezone-aware responses.")

                    # Add final greeting instruction for normal case
                    greeting_parts.append("Greet the guest warmly and ask how you can help them with their stay. Keep your response brief and friendly.")

                # Send initial prompt as properly formatted content
                initial_prompt = " ".join(greeting_parts)
                
                # Log the system prompt for debugging (truncated)
                handler_logger.info(f"Voice call system prompt length: {len(initial_prompt)} characters")
                handler_logger.info(f"System prompt includes get_current_time: {'get_current_time' in initial_prompt}")
                if len(initial_prompt) > 500:
                    handler_logger.info(f"System prompt preview: {initial_prompt[:500]}...")
                else:
                    handler_logger.info(f"Full system prompt: {initial_prompt}")

                # Create Content object
                welcome_content = types.Content(
                    role="user",
                    parts=[types.Part(text=initial_prompt)]
                )

                # Send with end_of_turn=True to signal completion
                await session.send_client_content(turns=welcome_content, turn_complete=True)

                # Start receiving responses from Gemini
                await receive_gemini_responses(sid, session)
    except asyncio.CancelledError:
        logging.info(f"Gemini Live session task cancelled for {sid}")
    except Exception as e:
        logging.error(f"Error in Gemini Live session for {sid}: {e}")
        traceback.print_exc()
    finally:
        # Clean up session
        if sid in active_sessions:
            if active_sessions[sid].get('session'):
                # Session already closed by context manager
                active_sessions[sid]['session'] = None
            logging.info(f"Gemini Live session ended for {sid}")

async def receive_gemini_responses(sid, session):
    """
    Continuously receive responses from Gemini Live and queue audio chunks.
    Also handles transcriptions for both input and output audio.

    Args:
        sid (str): Socket.IO session ID
        session: Gemini Live session
    """
    session_info = active_sessions.get(sid)
    if not session_info:
        logging.error(f"Session info not found for {sid}")
        return

    audio_queue = session_info['audio_queue']
    last_output_transcription = ""

    try:
        while True:
            turn = session.receive()
            async for response in turn:
                # Handle function calls
                if hasattr(response, 'function_call') and response.function_call:
                    function_name = response.function_call.name
                    function_id = getattr(response.function_call, 'id', None)
                    handler_logger.info(f"Function call detected in voice call for {sid}: {function_name} (id: {function_id})")
                    
                    if function_name == "get_current_time":
                        try:
                            # Execute the function with property context
                            property_context = session_info.get('property_context', {})
                            # Extra debug: log context used for timezone detection
                            try:
                                handler_logger.warning(f"[TIMEZONE DEBUG] Voice call property_context before get_current_time: {property_context}")
                                handler_logger.warning(f"[TIMEZONE DEBUG] Property context keys: {list(property_context.keys())}")
                                if 'timezone' in property_context:
                                    handler_logger.warning(f"[TIMEZONE DEBUG] Timezone value: {property_context['timezone']}")
                                else:
                                    handler_logger.warning(f"[TIMEZONE DEBUG] No timezone key found in property context")
                            except Exception:
                                pass
                            time_result = get_current_time(property_context)
                            handler_logger.info(f"Function result for {sid}: {time_result}")
                            
                            # Validate the function result
                            if not time_result or not isinstance(time_result, dict):
                                handler_logger.error(f"Invalid function result: {time_result}")
                                raise Exception(f"Invalid function result: {time_result}")
                            
                            # Send proper function response back to Gemini Live API
                            function_response_part = types.Part.from_function_response(
                                name=function_name,
                                response=time_result
                            )
                            
                            function_response_content = types.Content(
                                role="function",
                                parts=[function_response_part]
                            )
                            
                            handler_logger.info(f"Sending function response for {sid}")
                            handler_logger.info(f"Function result: {time_result}")
                            
                            try:
                                await session.send_client_content(turns=function_response_content, turn_complete=True)
                                handler_logger.info(f"Successfully sent function response for {sid}")
                            except Exception as send_error:
                                handler_logger.error(f"Failed to send function response for {sid}: {send_error}")
                                raise send_error
                        except Exception as func_error:
                            handler_logger.error(f"Error executing get_current_time function: {func_error}")
                            handler_logger.error(traceback.format_exc())
                            
                            # Send error function response
                            error_response = {"error": str(func_error)}
                            error_function_response_part = types.Part.from_function_response(
                                name=function_name,
                                response=error_response
                            )
                            
                            error_function_response_content = types.Content(
                                role="function",
                                parts=[error_function_response_part]
                            )
                            
                            handler_logger.info(f"Sending error function response for {sid}")
                            await session.send_client_content(turns=error_function_response_content, turn_complete=True)

                # Handle audio data
                if audio_data := response.data:
                    audio_queue.put_nowait(audio_data)

                # Handle output audio transcription (AI speech)
                if text := response.text:
                    # Accumulate text (for full response)
                    last_output_transcription += text

                # Handle server content for transcriptions
                if hasattr(response, 'server_content') and response.server_content:
                    server_content = response.server_content

                    # Handle input audio transcription (user speech)
                    if hasattr(server_content, 'input_transcription') and server_content.input_transcription:
                        input_text = server_content.input_transcription.text
                        if input_text and input_text.strip():
                            handler_logger.info(f"User speech transcription for {sid}: {input_text}")

                            # Store user transcription immediately
                            await store_conversation_in_firestore(sid, 'user', input_text.strip())

                            # Add to conversation history
                            conversation_entry = {
                                'role': 'user',
                                'text': input_text.strip(),
                                'timestamp': datetime.now(timezone.utc)
                            }
                            session_info['conversation_history'].append(conversation_entry)

                    # Handle output audio transcription (AI speech) - alternative path
                    if hasattr(server_content, 'output_transcription') and server_content.output_transcription:
                        output_text = server_content.output_transcription.text
                        if output_text and output_text.strip():
                            handler_logger.info(f"AI speech transcription for {sid}: {output_text}")
                            last_output_transcription += output_text

            # End of turn - store the complete AI response transcription
            if last_output_transcription and sid in active_sessions:
                session_info = active_sessions[sid]
                # Add to conversation history
                conversation_entry = {
                    'role': 'assistant',
                    'text': last_output_transcription.strip(),
                    'timestamp': datetime.now(timezone.utc)
                }
                session_info['conversation_history'].append(conversation_entry)

                # Store in DynamoDB
                await store_conversation_in_firestore(sid, 'assistant', last_output_transcription.strip())

                # Reset for next turn
                last_output_transcription = ""
    except Exception as e:
        logging.error(f"Error receiving Gemini responses for {sid}: {e}")
        traceback.print_exc()

def process_audio_chunk(sid, audio_data):
    """
    Process an audio chunk from the client and send to Gemini Live.

    Args:
        sid (str): Socket.IO session ID
        audio_data (bytes): Audio data from client

    Returns:
        bool: Success status
    """
    if sid not in active_sessions:
        logging.warning(f"No active Gemini Live session for {sid}")
        return False

    session_info = active_sessions[sid]
    session = session_info.get('session')

    if not session:
        logging.warning(f"Gemini Live session not initialized for {sid}")
        return False

    try:
        # Send audio to Gemini Live (async)
        asyncio.create_task(
            session.send_realtime_input(
                input={"data": audio_data, "mime_type": "audio/pcm"}
            )
        )
        return True
    except Exception as e:
        handler_logger.error(f"Error sending audio to Gemini Live for {sid}: {e}")
        handler_logger.error(traceback.format_exc())
        return False

def get_audio_chunk(sid):
    """
    Get the next audio chunk from Gemini Live for the client.

    Args:
        sid (str): Socket.IO session ID

    Returns:
        bytes or None: Audio data or None if no data available
    """
    if sid not in active_sessions:
        return None

    audio_queue = active_sessions[sid]['audio_queue']

    try:
        # Non-blocking get with timeout
        return audio_queue.get(block=False)
    except queue.Empty:
        return None
    except Exception as e:
        handler_logger.error(f"Error getting audio chunk for {sid}: {e}")
        return None

async def end_gemini_live_session(sid):
    """
    End a Gemini Live session.

    Args:
        sid (str): Socket.IO session ID

    Returns:
        bool: Success status
    """
    if sid not in active_sessions:
        logging.warning(f"No active Gemini Live session found for {sid}")
        return False

    try:
        session_info = active_sessions[sid]

        # Cancel the background task
        task = session_info.get('task')
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Session will be closed automatically in the task's finally block

        # Generate and store conversation summary if needed
        if session_info.get('conversation_history'):
            await generate_conversation_summary(sid)

        # Clean up session
        del active_sessions[sid]

        return True
    except Exception as e:
        logging.error(f"Error ending Gemini Live session for {sid}: {e}")
        traceback.print_exc()
        return False

async def process_voice_query_with_rag(sid, transcription):
    """
    Process a transcribed voice query with RAG and update session context.

    Args:
        sid (str): Socket.IO session ID
        transcription (str): Transcribed user query

    Returns:
        bool: Success status
    """
    if sid not in active_sessions:
        logging.warning(f"No active Gemini Live session for {sid}")
        return False

    session_info = active_sessions[sid]
    property_id = session_info.get('property_id')

    if not property_id:
        logging.warning(f"No property ID found for session {sid}")
        return False

    try:
        # Get property context from session
        property_context = session_info.get('property_context', {})

        # Ensure guest name is included in context if available
        guest_name = property_context.get('guestName', '')
        if not 'guestName' in property_context and guest_name:
            property_context['guestName'] = guest_name

        # Get conversation history
        conversation_history = session_info.get('conversation_history', [])

        # Get relevant context from LanceDB
        rag_results = get_relevant_context(transcription, property_id)

        # Store results for conversation tracking
        session_info['last_context_used'] = rag_results.get('items', [])

        # Format prompt with RAG context and conversation history
        prompt = format_prompt_with_rag(
            user_query=transcription,
            property_context=property_context,
            rag_results=rag_results,
            conversation_history=conversation_history
        )

        # Send to Gemini Live using proper Content/Part format
        session = session_info.get('session')
        if session:
            # Create Content object
            from google.genai import types
            user_content = types.Content(
                role="user",
                parts=[types.Part(text=prompt)]
            )

            # Send with turn_complete=True to signal this is a complete message
            await session.send_client_content(turns=user_content, turn_complete=True)

            # Add to conversation history
            conversation_entry = {
                'role': 'user',
                'text': transcription,
                'timestamp': datetime.now(timezone.utc)
            }
            session_info['conversation_history'].append(conversation_entry)

            # Store in Firestore if available
            await store_conversation_in_firestore(sid, 'user', transcription)

            return True
        else:
            logging.warning(f"Gemini Live session not available for {sid}")
            return False
    except Exception as e:
        logging.error(f"Error processing voice query with RAG for {sid}: {e}")
        traceback.print_exc()
        return False

async def store_conversation_in_firestore(sid, role, text):
    """
    Store conversation entry in DynamoDB.

    Args:
        sid (str): Socket.IO session ID
        role (str): 'user' or 'assistant'
        text (str): Message text
    """
    if sid not in active_sessions:
        return

    session_info = active_sessions[sid]
    property_id = session_info.get('property_id')
    property_context = session_info.get('property_context', {})

    if not property_id:
        logging.warning(f"No property ID found for session {sid}, cannot store conversation")
        return

    try:
        # Import DynamoDB client functions dynamically to avoid circular imports
        import importlib.util
        spec = importlib.util.find_spec('concierge.utils.dynamodb_client')
        if not spec:
            logging.error("Could not import dynamodb_client module")
            return

        dynamodb_client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dynamodb_client)

        # Check if we have a conversation ID for this session
        conversation_id = session_info.get('conversation_id')

        # If no conversation ID exists, create a new conversation session
        if not conversation_id:
            # Get user ID if available
            user_id = property_context.get('userId', 'system')

            # Get guest name if available
            guest_name = property_context.get('guestName', '')

            # Get reservation ID if available
            reservation_id = property_context.get('reservationId')

            # Get phone number if available
            phone_number = session_info.get('caller_number')

            # Create new conversation session for voice call
            conversation_id = await asyncio.to_thread(
                dynamodb_client.create_conversation_session,
                property_id=property_id,
                user_id=user_id,
                guest_name=guest_name,
                reservation_id=reservation_id,
                phone_number=phone_number,
                channel='voice_call'
            )

            if conversation_id:
                # Store the conversation ID in the session
                session_info['conversation_id'] = conversation_id
                logging.info(f"Created new conversation session with ID: {conversation_id}")
            else:
                logging.error("Failed to create conversation session")
                return

        # Create message data
        message_data = {
            'role': role,
            'text': text
        }

        # Add phone number if this is a user message and it's available
        if role == 'user':
            caller_number = session_info.get('caller_number')
            if caller_number:
                message_data['phone_number'] = caller_number

        # Add context used if this is an assistant response
        if role == 'assistant' and session_info.get('last_context_used'):
            message_data['context_used'] = session_info['last_context_used']

        # Add message to conversation
        success = await asyncio.to_thread(
            dynamodb_client.add_message_to_conversation,
            conversation_id=conversation_id,
            property_id=property_id,
            message_data=message_data
        )

        if success:
            logging.info(f"Added {role} message to conversation {conversation_id}")
        else:
            logging.error(f"Failed to add message to conversation {conversation_id}")

    except Exception as e:
        logging.error(f"Error storing conversation in DynamoDB: {e}")
        logging.error(traceback.format_exc())
        # Continue even if storage fails

async def generate_conversation_summary(sid):
    """
    Generate and store a summary of the conversation.

    Args:
        sid (str): Socket.IO session ID
    """
    if sid not in active_sessions:
        return

    session_info = active_sessions[sid]
    conversation_history = session_info.get('conversation_history', [])
    property_id = session_info.get('property_id')
    conversation_id = session_info.get('conversation_id')

    if not conversation_history or not property_id or not conversation_id:
        logging.warning(f"Missing required data for generating summary: property_id={property_id}, conversation_id={conversation_id}, history_length={len(conversation_history)}")
        return

    try:
        # Format conversation history for summarization
        conversation_text = ""
        for entry in conversation_history:
            role = "Guest" if entry.get('role') == 'user' else "AI"
            conversation_text += f"{role}: {entry.get('text', '')}\n\n"

        # Generate summary using Gemini
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logging.error("GEMINI_API_KEY not found in environment variables")
            return

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')

        prompt = (
            "Please summarize the following conversation between a guest and an AI assistant. "
            "Focus on the main topics discussed, questions asked, information provided, and any "
            "action items or next steps. Keep the summary concise but comprehensive.\n\n"
            f"CONVERSATION:\n{conversation_text}"
        )

        response = await asyncio.to_thread(model.generate_content, prompt)

        if not response or not hasattr(response, 'text'):
            logging.error("Failed to generate summary: empty or invalid response from Gemini")
            return

        summary = response.text
        logging.info(f"Generated summary for conversation {conversation_id}: {summary[:100]}...")

        # Import DynamoDB client functions dynamically to avoid circular imports
        import importlib.util
        spec = importlib.util.find_spec('concierge.utils.dynamodb_client')
        if not spec:
            logging.error("Could not import dynamodb_client module")
            return

        dynamodb_client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dynamodb_client)

        # Update the conversation with the summary
        success = await asyncio.to_thread(
            dynamodb_client.update_conversation,
            property_id=property_id,
            conversation_id=conversation_id,
            update_data={
                'Summary': summary,
                'MessageCount': len(conversation_history),
                'Channel': 'voice_call'
            }
        )

        if success:
            logging.info(f"Added summary to conversation {conversation_id}")
        else:
            logging.error(f"Failed to add summary to conversation {conversation_id}")

    except Exception as e:
        logging.error(f"Error generating conversation summary: {e}")
        logging.error(traceback.format_exc())
        # Continue even if summary generation fails