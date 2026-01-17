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
from datetime import datetime, timezone

from google import genai
from google.genai import types

from .ai_helpers import get_relevant_context, format_prompt_with_rag

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
            logging.error("GEMINI_API_KEY not found in environment variables")
            return False

        # Create Gemini client
        client = genai.Client(http_options={"api_version": "v1alpha"}, api_key=api_key)

        # Configure response modalities (audio)
        config = types.LiveConnectConfig(
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            )
        )

        # Set up queue for audio chunks
        audio_queue = queue.Queue()

        # Ensure property_context is a dictionary
        if property_context is None:
            property_context = {}

        # Try to get guest name from active sessions or Firestore reservations
        guest_name = property_context.get('guestName', '')

        # If caller number is provided, try to find guest name from DynamoDB
        if not guest_name and caller_number:
            try:
                # Import DynamoDB client functions dynamically to avoid circular imports
                import importlib.util
                spec = importlib.util.find_spec('utils.dynamodb_client')
                if spec:
                    dynamodb_client = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(dynamodb_client)

                    # Look up reservations by phone number
                    reservations = dynamodb_client.list_reservations_by_phone(caller_number)
                    if reservations:
                        # Use the first reservation's guest name
                        guest_name = reservations[0].get('GuestName')
                        if guest_name:
                            property_context['guestName'] = guest_name
                            logging.info(f"Found guest name from DynamoDB for caller {caller_number}: {guest_name}")
            except Exception as e:
                logging.error(f"Error finding guest name for caller {caller_number} in DynamoDB: {e}")
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
                logging.info(f"Gemini Live session started for {sid}")

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
                                try:
                                    from concierge.utils.firestore_client import get_firestore_client
                                    db = get_firestore_client()
                                except Exception:
                                    try:
                                        from concierge.utils.firestore_client import get_firestore_client
                                        db = get_firestore_client()
                                    except Exception:
                                        from firebase_admin import firestore
                                        db = firestore.client()
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
                                        'description': prop_data.get('description', '')
                                    })

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

                # Create a more detailed initial prompt with property details
                greeting_parts = []

                # Add phone call specific greeting if this is a phone call
                if caller_number:
                    greeting_parts.append(f"You are Staycee, a helpful concierge assistant for {property_name}, answering a phone call.")
                    greeting_parts.append(f"The caller's phone number is {caller_number}.")
                else:
                    greeting_parts.append(f"You are Staycee, a helpful concierge assistant for {property_name}.")

                greeting_parts.append(f"The guest's name is {guest_name}. Address them by name occasionally in your responses.")

                # Add any available property details
                if 'location' in property_context and property_context['location']:
                    greeting_parts.append(f"The property is located at {property_context['location']}.")

                if 'wifiNetwork' in property_context and 'wifiPassword' in property_context:
                    greeting_parts.append(f"The WiFi network is {property_context['wifiNetwork']} and the password is {property_context['wifiPassword']}.")

                # Fetch property knowledge items from DynamoDB
                try:
                    logging.info(f"Fetching knowledge items for property {property_id}")
                    # Import DynamoDB client functions dynamically to avoid circular imports
                    import importlib.util
                    spec = importlib.util.find_spec('utils.dynamodb_client')
                    if spec:
                        dynamodb_client = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(dynamodb_client)

                        # Get knowledge items for this property
                        knowledge_items = dynamodb_client.list_knowledge_items_by_property(property_id)

                        if knowledge_items:
                            # Format knowledge items as Q&A pairs
                            formatted_knowledge_items = []
                            for item in knowledge_items:
                                # Only include approved items
                                if item.get('Status') == 'approved':
                                    question = item.get('Question', '')
                                    answer = item.get('Answer', '')
                                    if question and answer:
                                        formatted_knowledge_items.append(f"Q: {question}\nA: {answer}")

                            # Add formatted knowledge items to the prompt
                            if formatted_knowledge_items:
                                knowledge_text = "\n\n".join(formatted_knowledge_items)
                                greeting_parts.append(f"\nProperty Knowledge Base (Q&A Format):\n{knowledge_text}")
                                logging.info(f"Added {len(formatted_knowledge_items)} knowledge items to system prompt")
                except Exception as e:
                    logging.error(f"Error fetching knowledge items: {e}")
                    traceback.print_exc()
                    # Continue without knowledge items

                # Add instructions for tool usage
                greeting_parts.append("IMPORTANT: Use the queryKnowledgeBase tool when you need specific information about amenities, check-in/out times, house rules, or local attractions.")
                greeting_parts.append("When asked for information you don't have, say you'll look it up, then use the tool to search for the answer.")

                # Add final greeting instruction
                greeting_parts.append("Greet the guest warmly and ask how you can help them with their stay. Keep your response brief and friendly.")

                # Send initial prompt as properly formatted content
                initial_prompt = " ".join(greeting_parts)

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

    Args:
        sid (str): Socket.IO session ID
        session: Gemini Live session
    """
    session_info = active_sessions.get(sid)
    if not session_info:
        logging.error(f"Session info not found for {sid}")
        return

    audio_queue = session_info['audio_queue']
    last_transcription = ""

    try:
        while True:
            turn = session.receive()
            async for response in turn:
                # Handle audio data
                if audio_data := response.data:
                    audio_queue.put_nowait(audio_data)

                # Handle text transcription
                if text := response.text:
                    # Accumulate text (for full response)
                    last_transcription += text

            # End of turn - store the complete response
            if last_transcription and sid in active_sessions:
                session_info = active_sessions[sid]
                # Add to conversation history
                conversation_entry = {
                    'role': 'assistant',
                    'text': last_transcription,
                    'timestamp': datetime.now(timezone.utc)
                }
                session_info['conversation_history'].append(conversation_entry)

                # Store in Firestore if available
                await store_conversation_in_firestore(sid, 'assistant', last_transcription)

                # Reset for next turn
                last_transcription = ""
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
        logging.error(f"Error sending audio to Gemini Live for {sid}: {e}")
        traceback.print_exc()
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
        logging.warning(f"get_audio_chunk: No active session for {sid}")
        return None

    audio_queue = active_sessions[sid]['audio_queue']

    try:
        # Try with a longer blocking timeout to increase chances of getting audio
        # when it becomes available shortly after the call
        try:
            # Increased timeout to 250ms for better chance of getting audio
            audio_data = audio_queue.get(block=True, timeout=0.25)
            logging.debug(f"Retrieved {len(audio_data) if audio_data else 0} bytes of audio data for {sid}")
            return audio_data
        except queue.Empty:
            # If nothing after timeout, do a final non-blocking check
            try:
                audio_data = audio_queue.get(block=False)
                logging.debug(f"Retrieved {len(audio_data) if audio_data else 0} bytes of audio data for {sid} (non-blocking)")
                return audio_data
            except queue.Empty:
                # Still nothing available
                return None
    except Exception as e:
        logging.error(f"Error getting audio chunk for {sid}: {e}", exc_info=True)
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
    Store conversation entry in Firestore.

    Args:
        sid (str): Socket.IO session ID
        role (str): 'user' or 'assistant'
        text (str): Message text
    """
    if sid not in active_sessions:
        return

    session_info = active_sessions[sid]
    db_firestore = session_info.get('db_firestore')

    if not db_firestore:
        return

    try:
        # Get conversation details
        property_id = session_info.get('property_id')
        property_context = session_info.get('property_context', {})

        # Create conversation document
        timestamp = datetime.now(timezone.utc)
        conversation_ref = db_firestore.collection('conversations').document()

        conversation_data = {
            'propertyId': property_id,
            'reservationId': property_context.get('reservationId'),
            'role': role,
            'text': text,
            'timestamp': timestamp,
            'channel': 'voice_call',
            'sessionId': sid
        }

        # Add context used if this is an assistant response
        if role == 'assistant' and session_info.get('last_context_used'):
            conversation_data['contextUsed'] = session_info['last_context_used']

        # Store in Firestore
        await asyncio.to_thread(conversation_ref.set, conversation_data)

    except Exception as e:
        logging.error(f"Error storing conversation in Firestore: {e}")
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
    db_firestore = session_info.get('db_firestore')
    conversation_history = session_info.get('conversation_history', [])
    property_id = session_info.get('property_id')

    if not db_firestore or not conversation_history or not property_id:
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
            return

        summary = response.text

        # Store summary in Firestore
        timestamp = datetime.now(timezone.utc)
        summary_ref = db_firestore.collection('conversation_summaries').document()

        summary_data = {
            'propertyId': property_id,
            'sessionId': sid,
            'summary': summary,
            'messageCount': len(conversation_history),
            'timestamp': timestamp,
            'channel': 'voice_call'
        }

        # Store in Firestore
        await asyncio.to_thread(summary_ref.set, summary_data)

    except Exception as e:
        logging.error(f"Error generating conversation summary: {e}")
        # Continue even if summary generation fails