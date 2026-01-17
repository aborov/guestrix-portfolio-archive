from flask import request, session, current_app
from flask_socketio import emit, disconnect, join_room, leave_room
from functools import wraps
import traceback # For logging
from datetime import datetime, timezone
from google.cloud.firestore_v1.base_query import FieldFilter

# We need access to the SocketIO instance created in app.py
# We will pass it in during registration. For type hinting/intellisense,
# we can import it conditionally or use a placeholder.
# from app import socketio # Avoid circular import - pass instance instead
from flask_socketio import SocketIO # For type hinting

# We also need access to shared state and utilities
from concierge.auth.utils import verify_token # For token verification
from concierge.utils.firestore_client import get_firestore_db, get_property # Import Firestore client
from concierge.utils.ai_helpers import process_text_query_with_tools # Import text chat processing function

# --- Global state (managed here or passed in/imported if refactored further) ---
# These dictionaries store runtime state. Consider a more robust state management
# approach (e.g., a dedicated class or Redis) for larger applications.
active_sessions = {} # Maps sid -> {'user_id': ..., 'property_id': ... (optional)}
active_calls = {}    # Maps sid -> {'property_id': ..., 'status': ..., 'user_id': ...}
conversation_history = {} # Maps sid -> list of conversation messages

# --- Authentication Decorator for SocketIO ---
# Ensures events (other than 'connect') only run for authenticated sessions.
def socketio_authenticated_only(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        sid = request.sid
        if sid not in active_sessions:
            print(f"Unauthorized Socket.IO event from SID {sid}. Disconnecting.")
            # It's often better to just disconnect than to emit an error to an
            # unauthenticated client, but emitting can help client-side debugging.
            emit('server_error', {'error': 'Not authenticated or session expired.', 'action': 'disconnect'}, room=sid)
            disconnect(sid) # Force disconnect the specific client
            return None # Stop processing the event
        else:
            # Inject user_id into the handler's arguments for convenience
            # Ensure the handler accepts user_id=None or similar if not always needed
            handler_kwargs = args[0] if args and isinstance(args[0], dict) else {}
            kwargs['user_id'] = active_sessions[sid].get('user_id')
            # Note: Original arguments are often passed as a single dict for socketio events
            # This decorator might need adjustment based on how handlers receive args.
            # Let's assume handlers take (data, user_id=None)

            # Reconstruct args for the handler
            original_data = args[0] if args else {}
            return f(original_data, user_id=kwargs['user_id'])
            # If handlers just use kwargs: return f(*args, **kwargs)
    return wrapped

# --- Registration Function ---
# This function will be called from app.py to attach handlers to the SocketIO instance
def register_socketio_handlers(socketio: SocketIO):

    @socketio.on('connect')
    def handle_connect():
        """Handles new Socket.IO connections and authenticates users via user_id."""
        sid = request.sid
        
        try:
            # Parse all query parameters safely
            user_id = request.args.get('user_id')
            property_id = request.args.get('property_id')  
            guest_name = request.args.get('guest_name')
            
            print(f"Connection attempt from SID: {sid}")
            print(f"  - User ID: {'Yes' if user_id else 'No'}")
            print(f"  - Property ID: {'Yes' if property_id else 'No'}")
            print(f"  - Guest Name: {'Yes' if guest_name else 'No'}")

            if not user_id:
                print(f"Socket connection from {sid} rejected: No user_id provided.")
                # Emit error before rejecting to help with debugging
                try:
                    emit('connection_error', {
                        'error': 'No user_id provided',
                        'sid': sid
                    }, room=sid)
                except Exception as emit_error:
                    print(f"Failed to emit connection error: {emit_error}")
                return False # Reject connection

            # Get Firestore DB client with proper error handling
            try:
                db = get_firestore_db()
                if not db:
                    print(f"Socket connection from {sid} rejected: Firestore (db) not available.")
                    try:
                        emit('connection_error', {
                            'error': 'Database not available', 
                            'sid': sid
                        }, room=sid)
                    except Exception:
                        pass
                    return False # Reject connection (server config issue)
            except Exception as firestore_error:
                print(f"Socket connection from {sid} rejected: Firestore initialization error: {firestore_error}")
                traceback.print_exc()
                try:
                    emit('connection_error', {
                        'error': f'Database initialization error: {str(firestore_error)}',
                        'sid': sid
                    }, room=sid)
                except Exception:
                    pass
                return False

            # Get user from Firestore to verify existence
            try:
                from concierge.utils.firestore_client import get_user
                user_data = get_user(user_id)

                if not user_data:
                    print(f"Socket connection from {sid} rejected: User {user_id} not found in Firestore.")
                    try:
                        emit('connection_error', {
                            'error': f'User {user_id} not found',
                            'sid': sid
                        }, room=sid)
                    except Exception:
                        pass
                    return False # Reject connection

                # Store user_id and any additional data associated with this session ID
                session_data = {'user_id': user_id}
                
                # Add optional parameters if provided
                if property_id:
                    session_data['property_id'] = property_id
                    print(f"  - Stored property_id: {property_id}")
                    
                if guest_name:
                    session_data['guest_name'] = guest_name
                    print(f"  - Stored guest_name: {guest_name}")
                
                active_sessions[sid] = session_data
                print(f"Client connected and authenticated: SID {sid}, User ID: {user_id}")

                # Send success response
                try:
                    emit('connection_success', {
                        'sid': sid, 
                        'message': 'Successfully connected and authenticated.'
                    }, room=sid)
                except Exception as emit_error:
                    print(f"Warning: Failed to emit connection_success: {emit_error}")
                    # Don't fail the connection just because emit failed
                
                return True # Accept connection

            except Exception as user_error:
                # Log the specific error during user verification
                print(f"Socket connection failed for {sid}: User verification exception: {user_error}")
                traceback.print_exc()
                try:
                    emit('connection_error', {
                        'error': f'User verification failed: {str(user_error)}',
                        'sid': sid
                    }, room=sid)
                except Exception:
                    pass
                return False # Reject connection

        except Exception as e:
            # Catch any other unexpected errors to prevent WSGI issues
            print(f"Socket connection failed for {sid}: Unexpected error in connect handler: {e}")
            traceback.print_exc()
            
            # Try to emit error, but don't let this exception bubble up
            try:
                emit('connection_error', {
                    'error': f'Unexpected server error: {str(e)}',
                    'sid': sid
                }, room=sid)
            except Exception as emit_error:
                print(f"Failed to emit error message: {emit_error}")
            
            # Always return False to reject the connection cleanly
            return False

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handles client disconnections and cleans up associated state."""
        sid = request.sid
        print(f"Client disconnected: SID {sid}")

        # Clean up call state if this SID was in an active call
        if sid in active_calls:
            call_info = active_calls.pop(sid)
            user_id_call = call_info.get('user_id', 'N/A')
            property_id = call_info.get('property_id', 'N/A')
            print(f"Cleaned up active call state for SID {sid} (User: {user_id_call}, Property: {property_id})")
            # TODO: Potentially notify other parties (e.g., Host dashboard) about the call ending abruptly.
            # Example: emit('call_ended_notification', {'user_id': user_id_call, 'reason': 'disconnect'}, room=f'host_{property_id}')

        # Clean up conversation history
        if sid in conversation_history:
            history_length = len(conversation_history[sid])
            conversation_history.pop(sid)
            print(f"Cleaned up conversation history for SID {sid} ({history_length} messages)")

        # Clean up session info
        if sid in active_sessions:
            session_info = active_sessions.pop(sid)
            user_id_session = session_info.get('user_id', 'N/A')
            conversation_id = session_info.get('conversation_id')
            property_id = session_info.get('property_id')

            # Log conversation ID if it exists
            if conversation_id:
                print(f"Disconnected session had conversation ID: {conversation_id}")

                # Mark text chat conversation as completed on disconnect (finalization)
                try:
                    if property_id:
                        from datetime import datetime, timezone
                        from concierge.utils.dynamodb_client import update_conversation
                        update_conversation(
                            property_id,
                            conversation_id,
                            {
                                'Status': 'completed',
                                'EndTime': datetime.now(timezone.utc).isoformat(),
                                'CompletionReason': 'disconnect'
                            }
                        )
                        print(f"Finalized conversation {conversation_id} as completed (disconnect)")
                except Exception as finalize_err:
                    print(f"Failed to finalize conversation {conversation_id} on disconnect: {finalize_err}")

            # Optional: Leave user-specific room if joined during connect
            # if user_id_session: leave_room(user_id_session, sid=sid)
            print(f"Removed session info for SID {sid} (User: {user_id_session})")
        else:
             print(f"No active session found for disconnecting SID: {sid}") # Should usually not happen if connect succeeded

    # --- Handle explicit user disconnect events ---
    @socketio.on('user_disconnect')
    def handle_user_disconnect(data):
        """Handles explicit user disconnect events sent by client."""
        sid = request.sid
        
        try:
            reason = data.get('reason', 'Unknown') if data else 'Unknown'
            timestamp = data.get('timestamp') if data else None
            inactivity_duration = data.get('inactivity_duration_ms') if data else None
            
            print(f"Received user_disconnect event from SID {sid}")
            print(f"  - Reason: {reason}")
            if timestamp:
                print(f"  - Timestamp: {timestamp}")
            if inactivity_duration:
                print(f"  - Inactivity duration: {inactivity_duration}ms")
            
            # Acknowledge the disconnect
            try:
                emit('disconnect_acknowledged', {
                    'message': 'Disconnect event received',
                    'reason': reason
                }, room=sid)
            except Exception as emit_error:
                print(f"Failed to emit disconnect acknowledgment: {emit_error}")
            
            # Mark text chat conversation as completed immediately on inactivity timeout
            try:
                session_info = active_sessions.get(sid, {})
                conversation_id = session_info.get('conversation_id')
                property_id = session_info.get('property_id')
                if conversation_id and property_id and reason.lower().startswith('inactivity'):
                    from datetime import datetime, timezone
                    from concierge.utils.dynamodb_client import update_conversation
                    update_conversation(
                        property_id,
                        conversation_id,
                        {
                            'Status': 'completed',
                            'EndTime': datetime.now(timezone.utc).isoformat(),
                            'CompletionReason': 'inactivity_timeout',
                            'InactivityDurationMs': inactivity_duration
                        }
                    )
                    print(f"Finalized conversation {conversation_id} as completed (inactivity timeout)")
            except Exception as finalize_err:
                print(f"Failed to finalize conversation on inactivity timeout: {finalize_err}")

            # Let the normal disconnect handler clean up when the actual disconnect happens
            
        except Exception as e:
            print(f"Error handling user_disconnect event from {sid}: {e}")
            traceback.print_exc()

    # --- ADDED: Auth Message Handler ---
    @socketio.on('auth')
    def handle_auth(data):
        """Handles authentication messages sent after connection."""
        sid = request.sid
        
        try:
            user_id = data.get('user_id')
            property_id = data.get('property_id')
            guest_name = data.get('guest_name')
            system_prompt = data.get('system_prompt')
            reservation_id = data.get('reservation_id')  # Extract reservation_id from auth message
            phone_number = data.get('phone_number')  # Extract phone_number from auth message

            print(f"Received 'auth' message from SID: {sid}. User ID provided: {'Yes' if user_id else 'No'}")
            if reservation_id:
                print(f"Reservation ID provided in auth: {reservation_id}")
            if phone_number:
                print(f"Phone number provided in auth: {phone_number}")

            # Check if already authenticated via connect
            if sid in active_sessions and active_sessions[sid].get('user_id'):
                user_id = active_sessions[sid].get('user_id')
                print(f"User already authenticated via connect: SID {sid}, User ID: {user_id}")

                # Update session with additional data
                try:
                    if property_id:
                        active_sessions[sid]['property_id'] = property_id
                    if guest_name:
                        active_sessions[sid]['guest_name'] = guest_name
                    if system_prompt:
                        active_sessions[sid]['system_prompt'] = system_prompt
                        print(f"Stored system prompt in session (length: {len(system_prompt)})")
                        # Log the first 100 characters of the system prompt for debugging
                        if len(system_prompt) > 100:
                            print(f"System prompt starts with: {system_prompt[:100]}...")
                    if reservation_id:
                        active_sessions[sid]['reservation_id'] = reservation_id
                        print(f"Stored reservation ID in session: {reservation_id}")
                    if phone_number:
                        active_sessions[sid]['phone_number'] = phone_number
                        print(f"Stored phone number in session: {phone_number}")

                    # Send success response
                    emit('auth_success', {'message': 'Authentication successful'}, room=sid)
                    return
                except Exception as session_error:
                    print(f"Error updating session for {sid}: {session_error}")
                    emit('error', {'message': f'Session update error: {str(session_error)}'}, room=sid)
                    return

            # If not already authenticated, verify user_id
            if not user_id:
                print(f"Authentication failed for {sid}: No user_id provided in auth message.")
                emit('error', {'message': 'Authentication failed: No user ID provided'}, room=sid)
                return

            # Get Firestore DB client
            try:
                db = get_firestore_db()
                if not db:
                    print(f"Authentication failed for {sid}: Firestore (db) not available.")
                    emit('error', {'message': 'Authentication failed: Database not available'}, room=sid)
                    return
            except Exception as db_error:
                print(f"Authentication failed for {sid}: Database error: {db_error}")
                emit('error', {'message': 'Authentication failed: Database error'}, room=sid)
                return

            try:
                # Get user from Firestore to verify existence
                from concierge.utils.firestore_client import get_user
                user_data = get_user(user_id)

                if not user_data:
                    print(f"Authentication failed for {sid}: User {user_id} not found in Firestore.")
                    emit('error', {'message': 'Authentication failed: User not found'}, room=sid)
                    return

                # Store user_id and additional data in session
                active_sessions[sid] = {'user_id': user_id}
                if property_id:
                    active_sessions[sid]['property_id'] = property_id
                if guest_name:
                    active_sessions[sid]['guest_name'] = guest_name
                if system_prompt:
                    active_sessions[sid]['system_prompt'] = system_prompt
                    print(f"Stored system prompt in session (length: {len(system_prompt)})")
                    # Log the first 100 characters of the system prompt for debugging
                    if len(system_prompt) > 100:
                        print(f"System prompt starts with: {system_prompt[:100]}...")
                if reservation_id:
                    active_sessions[sid]['reservation_id'] = reservation_id
                    print(f"Stored reservation ID in session: {reservation_id}")
                if phone_number:
                    active_sessions[sid]['phone_number'] = phone_number
                    print(f"Stored phone number in session: {phone_number}")

                print(f"Client authenticated via message: SID {sid}, User ID: {user_id}")

                # Send success response
                emit('auth_success', {'message': 'Authentication successful'}, room=sid)
            except Exception as user_verify_error:
                print(f"Authentication error for {sid}: {user_verify_error}")
                traceback.print_exc()
                emit('error', {'message': f'Authentication error: {str(user_verify_error)}'}, room=sid)
        except Exception as e:
            print(f"Unexpected error in auth handler for {sid}: {e}")
            traceback.print_exc()
            emit('error', {'message': f'Unexpected authentication error: {str(e)}'}, room=sid)

    # === New Voice Call Handlers ===

    @socketio.on('start_call')
    @socketio_authenticated_only
    def handle_start_call(data, user_id): # Added user_id from decorator
        """Handles the request from a client to start a voice call."""
        sid = request.sid
        property_id = data.get('property_id') # Client should send which property they are calling about

        print(f"Received 'start_call' from SID: {sid}, User: {user_id}, Property: {property_id}") # DEBUG

        if not property_id:
             print(f"Rejecting 'start_call' from {sid}: Missing property_id.")
             emit('call_error', {'error': 'Property ID is required to start a call.'}, room=sid)
             return

        if sid in active_calls:
             print(f"Rejecting 'start_call' from {sid}: User already in a call.")
             emit('call_error', {'error': 'You are already in an active call.'}, room=sid)
             return

        # --- ADDED: Get Property Context ---
        property_context = {}
        guest_name = "Guest"  # Default
        reservation_id = None

        # Get Firestore DB client
        db = get_firestore_db()
        if db:
            try:
                # Get property details
                property_ref = db.collection('properties').document(property_id)
                property_doc = property_ref.get()
                if property_doc.exists:
                    property_context = property_doc.to_dict()
                    # Ensure property_id present for downstream tools (timezone lookup)
                    try:
                        property_context['property_id'] = property_id
                    except Exception:
                        pass
                else:
                    # If property doc not found, still pass property_id for later lookups
                    property_context = {'property_id': property_id}

                # Try to find user's active reservation for this property
                user_ref = db.collection('users').document(user_id)
                user_doc = user_ref.get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    user_phone = user_data.get('phone_number')

                    if user_phone:
                        # Find active reservation for this phone and property
                        now = datetime.now(timezone.utc)
                        reservations_ref = db.collection('reservations')
                        # Check both primary phone number
                        query = reservations_ref.where(filter=FieldFilter('propertyId', '==', property_id))\
                                             .where(filter=FieldFilter('startDate', '<=', now))\
                                             .where(filter=FieldFilter('endDate', '>=', now))

                        active_reservations = list(query.stream())
                        matched_reservation = None

                        # First try to match by primary phone number
                        for res_doc in active_reservations:
                            res_data = res_doc.to_dict()
                            # Check both field names for guest phone number
                            if res_data.get('guestPhoneNumber') == user_phone or res_data.get('guest_phone') == user_phone:
                                matched_reservation = res_doc
                                reservation_id = res_doc.id
                                property_id = res_data.get('propertyId') or res_data.get('property_id')
                                guest_name = res_data.get('guestName', guest_name)
                                print(f"Matched primary phone for active reservation: {reservation_id}")
                                break

                        # If no match found, try additional contacts
                        if not matched_reservation:
                            for res_doc in active_reservations:
                                res_data = res_doc.to_dict()
                                additional_contacts = res_data.get('additional_contacts', [])

                                for contact in additional_contacts:
                                    # Check all possible field names for phone numbers
                                    contact_phone = contact.get('phone') or contact.get('phoneNumber') or contact.get('phone_number')

                                    if contact_phone == user_phone:
                                        matched_reservation = res_doc
                                        reservation_id = res_doc.id
                                        property_id = res_data.get('propertyId') or res_data.get('property_id')
                                        guest_name = contact.get('name', guest_name)  # Use the specific contact's name
                                        print(f"Matched additional contact phone for active reservation: {reservation_id}")
                                        break

                                if matched_reservation:
                                    break

                        # If a match was found by either method
                        if matched_reservation:
                            res_data = matched_reservation.to_dict()
                            # Add reservation info to property context
                            property_context['guestName'] = guest_name
                            property_context['reservationId'] = reservation_id

                            print(f"Found active reservation for user {user_id} at property {property_id}: {reservation_id}")
                        else:
                            print(f"No active reservation found for user {user_id} at property {property_id}")
            except Exception as e:
                print(f"Error getting property context: {e}")
                traceback.print_exc()
                # Continue even without property context
        # --- END UPDATED ---

        # Ensure property_id is present in property_context for downstream timezone lookups
        try:
            if property_id:
                property_context['property_id'] = property_id
        except Exception:
            pass

        # Store call state
        active_calls[sid] = {
            'user_id': user_id,
            'property_id': property_id,
            'status': 'active', # Other statuses could be 'ringing', 'connecting' etc.
            'property_context': property_context,
            'guest_name': guest_name,
            'reservation_id': reservation_id
        }

        # Add user_id to active_sessions if needed (decorator might handle this)
        if sid in active_sessions:
             active_sessions[sid]['property_id'] = property_id # Store property in session too

        print(f"Call started for SID: {sid}, User: {user_id}, Property: {property_id}")

        # Acknowledge call start to the client
        emit('call_started', {'message': 'Call initiated successfully.', 'property_id': property_id}, room=sid)

        # --- ADDED: Initialize Gemini Live Session ---
        from concierge.utils.gemini_live_handler import create_gemini_live_session
        import asyncio

        # Initialize Gemini Live session
        asyncio.create_task(create_gemini_live_session(sid, property_id, property_context, get_firestore_db()))
        # --- END ADDED ---


    @socketio.on('end_call')
    @socketio_authenticated_only
    def handle_end_call(data, user_id): # Added user_id
        """Handles the request from a client to end a voice call."""
        sid = request.sid
        print(f"Received 'end_call' from SID: {sid}, User: {user_id}") # DEBUG

        if sid not in active_calls:
            print(f"Ignoring 'end_call' from {sid}: No active call found for this session.")
            # Optionally send an error back, but might not be necessary
            # emit('call_error', {'error': 'No active call to end.'}, room=sid)
            return

        call_info = active_calls.pop(sid) # Remove from active calls
        property_id = call_info.get('property_id', 'N/A')

        print(f"Call ended for SID: {sid}, User: {user_id}, Property: {property_id}")

        # Acknowledge call end to the client
        emit('call_ended', {'message': 'Call ended successfully.'}, room=sid)

        # --- ADDED: End Gemini Live Session ---
        from concierge.utils.gemini_live_handler import end_gemini_live_session
        import asyncio

        # End Gemini Live session
        asyncio.create_task(end_gemini_live_session(sid))
        # --- END ADDED ---


    @socketio.on('audio_chunk_to_server')
    @socketio_authenticated_only
    def handle_audio_chunk(data, user_id): # Added user_id
        """Handles receiving an audio chunk from the client during an active call."""
        sid = request.sid

        if sid not in active_calls:
             print(f"Warning: Received audio chunk from {sid} (User: {user_id}) but no active call found. Ignoring.")
             # emit('call_error', {'error': 'Cannot process audio, no active call.'}, room=sid)
             return

        audio_data = data.get('audio') # Assuming client sends {'audio': blob_or_base64_data}
        if not audio_data:
             print(f"Warning: Received empty audio chunk from {sid} (User: {user_id}).")
             return

        # --- ADDED: Process Audio with Gemini Live ---
        from concierge.utils.gemini_live_handler import process_audio_chunk, get_audio_chunk

        # Send audio to Gemini Live
        if process_audio_chunk(sid, audio_data):
            # Check if there's audio to send back to client
            response_audio = get_audio_chunk(sid)
            if response_audio:
                # Send audio back to client
                emit('audio_chunk_to_client', {'audio': response_audio}, room=sid)
        # --- END ADDED ---

    # --- ADDED: Speech-to-Text (STT) Result Handler ---
    @socketio.on('stt_result')
    @socketio_authenticated_only
    def handle_stt_result(data, user_id):
        """Handles receiving speech-to-text results from the client."""
        sid = request.sid

        if sid not in active_calls:
            print(f"Warning: Received STT result from {sid} (User: {user_id}) but no active call found. Ignoring.")
            return

        transcription = data.get('text')
        if not transcription:
            print(f"Warning: Received empty STT result from {sid} (User: {user_id}).")
            return

        print(f"Received STT result from SID: {sid}, User: {user_id}: '{transcription}'")

        # Process with RAG
        from concierge.utils.gemini_live_handler import process_voice_query_with_rag
        import asyncio

        # Process the transcribed query with RAG
        asyncio.create_task(process_voice_query_with_rag(sid, transcription))

    # --- NEW: Knowledge Base RAG Query Handler ---
    @socketio.on('rag_query')
    @socketio_authenticated_only
    def handle_rag_query(data, user_id):
        """Handle RAG query requests from client for Gemini Live tool calls."""
        sid = request.sid
        property_id = data.get('property_id')
        query = data.get('query')

        if not property_id or not query:
            emit('rag_results', {
                'error': 'Missing property_id or query',
                'items': []
            })
            return

        print(f"Received RAG query from SID: {sid}, User: {user_id}, Property: {property_id}")
        print(f"Query: '{query}'")
        print(f"Property ID type: {type(property_id).__name__}, Value format: '{property_id}'")

        # Get relevant context using existing function
        from concierge.utils.ai_helpers import get_relevant_context
        try:
            # Add extra debug log before calling get_relevant_context
            print(f"Calling get_relevant_context with property_id='{property_id}', type={type(property_id).__name__}")

            rag_results = get_relevant_context(query, property_id)

            # Log query results for debugging
            items_count = len(rag_results.get('items', []))
            print(f"get_relevant_context returned {items_count} items. Query successful: {rag_results.get('found', False)}")

            # Format results for cleaner presentation to the model
            formatted_results = {
                'success': True,
                'items': rag_results.get('items', []),
                'sources': rag_results.get('sources', [])
            }

            # Include the original query for reference
            formatted_results['query'] = query

            print(f"Sending RAG results back to client. Found {len(formatted_results['items'])} items.")
            emit('rag_results', formatted_results)
        except Exception as e:
            print(f"Error processing RAG query: {e}")
            emit('rag_results', {
                'error': f'Error retrieving knowledge: {str(e)}',
                'items': []
            })

    @socketio.on('text_message_from_user')
    @socketio_authenticated_only
    def handle_text_message(data, user_id): # Added user_id
        """Handles receiving a text message from the client (e.g., text chat)."""
        sid = request.sid

        # Check if data is in the expected format with payload
        if isinstance(data, dict) and 'payload' in data:
            payload = data.get('payload', {})
            message_text = payload.get('message')
            property_id_from_payload = payload.get('property_id')
        else:
            # Fallback for direct data format
            message_text = data.get('message')
            property_id_from_payload = data.get('property_id')

        if not message_text:
             print(f"Warning: Received empty text message from {sid} (User: {user_id}).")
             emit('chat_error', {'error': 'Cannot send empty message.'}, room=sid)
             return

        print(f"Received text message from SID: {sid}, User: {user_id}: '{message_text}'")

        # --- Check for property_id in message payload ---
        if property_id_from_payload:
            print(f"Property ID provided in message payload: {property_id_from_payload}")

        # --- UPDATED: Use Session Data First, Then Find Active Reservation & Property ID ---
        property_id = property_id_from_payload  # Use from payload if available
        guest_name = "Guest" # Default
        reservation_id = None
        error_message = None

        # First, try to get data from the session (passed from guest dashboard)
        if sid in active_sessions:
            session_data = active_sessions[sid]

            # Use session data if available (this comes from the guest dashboard auth)
            if not property_id and session_data.get('property_id'):
                property_id = session_data.get('property_id')
                print(f"Using property ID from session: {property_id}")

            if session_data.get('guest_name') and session_data.get('guest_name') != "Guest":
                guest_name = session_data.get('guest_name')
                print(f"Using guest name from session: {guest_name}")

            if session_data.get('reservation_id'):
                reservation_id = session_data.get('reservation_id')
                print(f"Using reservation ID from session: {reservation_id}")

        # Only look up reservation if we still don't have property_id (fallback)
        if not property_id:
            try:
                # Import DynamoDB client functions
                from concierge.utils.dynamodb_client import get_user, list_reservations_by_phone

                # 1. Get user's phone number
                user_data = get_user(user_id)
                if not user_data:
                    error_message = "User profile not found."
                    print(f"Error for SID {sid}: {error_message} (User ID: {user_id})")
                else:
                    user_phone = user_data.get('PhoneNumber') or user_data.get('phone_number')
                    if not user_phone:
                        error_message = "User phone number not found in profile."
                        print(f"Error for SID {sid}: {error_message} (User ID: {user_id})")
                    else:
                        # 2. Find active reservations for this phone number using DynamoDB
                        print(f"Looking up reservations for phone number: {user_phone}")
                        reservations = list_reservations_by_phone(user_phone)

                        # Filter for active reservations
                        now = datetime.now(timezone.utc).isoformat()
                        active_reservations = []

                        for res in reservations:
                            start_date = res.get('StartDate')
                            end_date = res.get('EndDate')

                            if start_date and end_date and start_date <= now and end_date >= now:
                                active_reservations.append(res)

                        print(f"Found {len(active_reservations)} active reservations out of {len(reservations)} total")

                        if active_reservations:
                            # Use the first active reservation
                            matched_reservation = active_reservations[0]

                            # Extract reservation ID from SK if needed
                            if 'ReservationId' in matched_reservation:
                                reservation_id = matched_reservation.get('ReservationId')
                            elif 'SK' in matched_reservation and matched_reservation['SK'].startswith('RESERVATION#'):
                                reservation_id = matched_reservation['SK'].replace('RESERVATION#', '')
                            else:
                                reservation_id = None

                            # Extract property ID from PK if needed
                            if 'PropertyId' in matched_reservation:
                                property_id = matched_reservation.get('PropertyId')
                            elif 'PK' in matched_reservation and matched_reservation['PK'].startswith('PROPERTY#'):
                                property_id = matched_reservation['PK'].replace('PROPERTY#', '')
                            else:
                                property_id = None

                            # Get guest name
                            guest_name = matched_reservation.get('GuestName', guest_name)

                            if not property_id:
                                error_message = "Active reservation found, but property ID is missing."
                                print(f"Error for SID {sid}: {error_message} (Reservation ID: {reservation_id})")
                            else:
                                print(f"Context for SID {sid}: User {user_id} ({guest_name}) asking about Property {property_id} (Reservation {reservation_id})")

                                # Store phone number in property_context for later use
                                if not 'property_context' in active_sessions[sid]:
                                    active_sessions[sid]['property_context'] = {}

                                active_sessions[sid]['property_context']['guestPhone'] = user_phone
                        else:
                            error_message = "No active reservation found for your phone number."
                            print(f"Info for SID {sid}: {error_message} (Phone: {user_phone})")
            except Exception as e:
                error_message = "An error occurred while retrieving reservation details."
                print(f"Error fetching reservation details for SID {sid}, User {user_id}: {e}")
                traceback.print_exc()
        # --- END UPDATED ---

        # --- IMPLEMENT AI Response Generation (tools-only, no RAG) ---
        from concierge.utils.ai_helpers import process_text_query_with_tools

        assistant_response_text = ""

        if error_message:
            # Personalize error message with user's phone number if available
            user_phone = ""
            try:
                if user_id:
                    # Get Firestore DB client
                    db = get_firestore_db()
                    if db:
                        user_ref = db.collection('users').document(user_id)
                        user_doc = user_ref.get()
                        if user_doc.exists:
                            user_data = user_doc.to_dict()
                            user_phone = user_data.get('phone_number', "")
            except:
                pass

            if "No active reservation found" in error_message and user_phone:
                assistant_response_text = f"I'm sorry, I couldn't find any active reservations associated with your phone number ({user_phone}). If you're a guest staying at one of our properties, please make sure you're using the same phone number that was provided during booking, or ask your host to add your phone number to the reservation."
            else:
                assistant_response_text = f"Sorry, I encountered an issue: {error_message} Please contact the property host for assistance."
        elif property_id:
            try:
                # Get property details for context
                property_context = {}
                property_name = "this property"
                
                # Get property from Firestore
                property_data = get_property(property_id)

                # Extract WiFi details from property data if available
                if property_data:
                    wifi_details = property_data.get('wifiDetails', {})
                    if wifi_details:
                        property_context = {}
                        property_context['wifiNetwork'] = wifi_details.get('network', '')
                        property_context['wifiPassword'] = wifi_details.get('password', '')
                        print(f"Extracted WiFi details - Network: {property_context.get('wifiNetwork')}, Password: {property_context.get('wifiPassword')}")

                    # Add location information for timezone detection
                    location_fields = ['address', 'location', 'city', 'state', 'country', 'name', 'timezone']
                    for field in location_fields:
                        if field in property_data and property_data[field]:
                            property_context[field] = property_data[field]
                        # Also try capitalized versions
                        cap_field = field.capitalize()
                        if cap_field in property_data and property_data[cap_field]:
                            property_context[field] = property_data[cap_field]
                    
                    # Add property_id for fallback timezone lookup
                    property_context['property_id'] = property_id

                    # Add any relevant reservation details to context
                    property_context['guestName'] = guest_name
                    if reservation_id:
                        property_context['reservationId'] = reservation_id

                        # Try to get more reservation details from Firestore
                        try:
                            from concierge.utils.firestore_client import get_reservation
                            reservation_data = get_reservation(reservation_id)
                            if reservation_data:
                                # Add check-in and check-out times if available
                                if 'startDate' in reservation_data:
                                    property_context['checkInTime'] = reservation_data.get('startDate')
                                if 'endDate' in reservation_data:
                                    property_context['checkOutTime'] = reservation_data.get('endDate')
                                # Add any other useful reservation details
                                if 'guestName' in reservation_data and not property_context.get('guestName'):
                                    property_context['guestName'] = reservation_data.get('guestName')
                        except Exception as res_err:
                            print(f"Warning: Error fetching reservation details for {reservation_id}: {res_err}")
                else:
                    property_context = {}

                # Get system prompt from session if available
                system_prompt = None
                if sid in active_sessions and 'system_prompt' in active_sessions[sid]:
                    system_prompt = active_sessions[sid]['system_prompt']
                    print(f"Using system prompt from session (length: {len(system_prompt)})")

                # Get conversation history for this session
                chat_history = []
                if sid in conversation_history:
                    chat_history = conversation_history[sid]
                    print(f"Using conversation history with {len(chat_history)} messages")

                # Process query with text chat tools (includes Google Search tool and system prompt)
                print(f"Processing text query for property {property_id}: '{message_text}'")
                print(f"[HANDLERS DEBUG] Calling process_text_query_with_tools from ai_helpers")
                result = process_text_query_with_tools(
                    message_text,
                    property_context=property_context,
                    conversation_history=chat_history,
                    system_prompt=system_prompt
                )

                # Use the generated response
                assistant_response_text = result['response']

                # Log context usage (process_text_query_with_tools doesn't return has_context)
                if 'has_context' in result and result['has_context']:
                    context_count = len(result.get('context_used', []))
                    print(f"Response generated with {context_count} context items from knowledge base")
                else:
                    print("Response generated without knowledge base context")

                # Update conversation history in memory
                if sid not in conversation_history:
                    conversation_history[sid] = []

                # Add user message to history
                conversation_history[sid].append({
                    'role': 'user',
                    'text': message_text
                })

                # Add AI response to history
                conversation_history[sid].append({
                    'role': 'assistant',
                    'text': assistant_response_text
                })

                # Limit history to last 10 messages (5 exchanges) to prevent context overflow
                if len(conversation_history[sid]) > 10:
                    conversation_history[sid] = conversation_history[sid][-10:]

                print(f"Updated conversation history for SID {sid}, now has {len(conversation_history[sid])} messages")

                # Store conversation in DynamoDB
                try:
                    # Import DynamoDB client functions
                    from concierge.utils.dynamodb_client import (
                        create_conversation_session,
                        add_message_to_conversation,
                        get_conversation
                    )

                    # Check if we have a conversation ID for this session
                    conversation_id = active_sessions[sid].get('conversation_id')

                    # If no conversation ID exists, create a new conversation session
                    if not conversation_id:
                        # Get reservation ID from session
                        reservation_id = active_sessions[sid].get('reservation_id')

                        # If no reservation ID in session, try to find it from property context
                        if not reservation_id and property_context:
                            reservation_id = property_context.get('reservationId')

                        if reservation_id:
                            print(f"Using reservation ID for new conversation: {reservation_id}")

                        # Get phone number from session or property context
                        phone_number = None

                        # First try to get phone number from session (from guest dashboard auth)
                        if sid in active_sessions and active_sessions[sid].get('phone_number'):
                            phone_number = active_sessions[sid]['phone_number']
                            print(f"Using phone number from session auth: {phone_number}")
                        elif sid in active_sessions and active_sessions[sid].get('property_context', {}).get('guestPhone'):
                            phone_number = active_sessions[sid]['property_context']['guestPhone']
                            print(f"Using phone number from session property context: {phone_number}")
                        elif property_context and property_context.get('guestPhone'):
                            phone_number = property_context.get('guestPhone')
                            print(f"Using phone number from property context: {phone_number}")

                        conversation_id = create_conversation_session(
                            property_id=property_id,
                            user_id=user_id,
                            guest_name=guest_name,
                            reservation_id=reservation_id,
                            phone_number=phone_number
                        )

                        if conversation_id:
                            # Store the conversation ID in the session
                            active_sessions[sid]['conversation_id'] = conversation_id
                            print(f"Created new conversation session with ID: {conversation_id}")
                            try:
                                emit('conversation_started', {
                                    'conversation_id': conversation_id,
                                    'property_id': property_id
                                }, room=sid)
                            except Exception as emit_err:
                                print(f"Failed to emit conversation_started: {emit_err}")
                        else:
                            print("Failed to create conversation session")

                    # Add the user message to the conversation
                    if conversation_id:
                        # Add user message
                        # Check if we have a phone number for this user
                        phone_number = None
                        if property_context and property_context.get('guestPhone'):
                            phone_number = property_context.get('guestPhone')

                        # Create message data with phone number if available
                        user_message_data = {
                            'role': 'user',
                            'text': message_text
                        }

                        if phone_number:
                            user_message_data['phone_number'] = phone_number
                            print(f"Including phone number {phone_number} in user message")

                        add_message_to_conversation(
                            conversation_id=conversation_id,
                            property_id=property_id,
                            message_data=user_message_data
                        )

                        # Add AI response
                        add_message_to_conversation(
                            conversation_id=conversation_id,
                            property_id=property_id,
                            message_data={
                                'role': 'assistant',
                                'text': assistant_response_text,
                                'context_used': result.get('context_used', [])
                            }
                        )

                        print(f"Added messages to conversation {conversation_id}")
                    else:
                        print("Warning: No conversation ID available, messages not stored in DynamoDB")

                    # We no longer store conversations in Firestore - DynamoDB only

                except Exception as e:
                    print(f"Warning: Failed to store conversation in DynamoDB: {e}")
                    # Continue even if storage fails

            except Exception as e:
                print(f"Error processing message with RAG: {e}")
                traceback.print_exc()
                assistant_response_text = f"I'm sorry {guest_name}, I'm having trouble understanding your question right now. How else can I assist you with your stay at this property?"
        else:
             # No property context available
             assistant_response_text = "I'm sorry, I can't find information about your current reservation. Please make sure you're using the same phone number that was used for your booking, or ask the host to add your contact information."
        # --- END RAG Implementation ---

        print(f"Sending response to SID {sid}: {assistant_response_text}")
        emit('text_message_from_ai', {'message': assistant_response_text}, room=sid)

    # --- NEW: Tool Configuration Handler ---
    @socketio.on('configure_tools')
    @socketio_authenticated_only
    def handle_configure_tools(data, user_id):
        """Handle tool configuration requests from client."""
        sid = request.sid

        # Check if data is in the expected format with payload
        if isinstance(data, dict) and 'payload' in data:
            payload = data.get('payload', {})
        else:
            payload = data

        property_id = payload.get('property_id')
        enable_rag = payload.get('enable_rag', True)
        enable_google_search = payload.get('enable_google_search', True)

        print(f"Received tool configuration from SID: {sid}, User: {user_id}")
        print(f"Property ID: {property_id}, Enable RAG: {enable_rag}, Enable Google Search: {enable_google_search}")

        # Store tool configuration in session
        if sid in active_sessions:
            active_sessions[sid]['tools_config'] = {
                'property_id': property_id,
                'enable_rag': enable_rag,
                'enable_google_search': enable_google_search
            }
            print(f"Tool configuration stored for session {sid}")

            # Send confirmation
            emit('tools_configured', {
                'success': True,
                'message': 'Tools configured successfully'
            }, room=sid)
        else:
            print(f"Cannot store tool configuration: Session {sid} not found")
            emit('tools_configured', {
                'success': False,
                'error': 'Session not found'
            }, room=sid)

    @socketio.on('update_guest_name')
    @socketio_authenticated_only
    def handle_update_guest_name(data, user_id):
        """Handle guest name updates from the client."""
        sid = request.sid
        
        try:
            guest_name = data.get('guest_name')
            if not guest_name:
                print(f"Warning: Empty guest name received from SID {sid}")
                emit('guest_name_update_error', {
                    'error': 'Guest name cannot be empty'
                }, room=sid)
                return
            
            print(f"Updating guest name for SID {sid} to: {guest_name}")
            
            # Update the session data with the new guest name
            if sid in active_sessions:
                active_sessions[sid]['guest_name'] = guest_name
                print(f"Successfully updated guest name in session for SID {sid}")
                
                # Clear the system prompt so it gets regenerated with the new guest name
                # The system prompt will be recreated on the next message with the updated guest name
                if 'system_prompt' in active_sessions[sid]:
                    del active_sessions[sid]['system_prompt']
                    print(f"Cleared system prompt for SID {sid} - will be regenerated with new guest name")
                
                # Send confirmation back to client with instruction to refresh system prompt
                emit('guest_name_updated', {
                    'success': True,
                    'guest_name': guest_name,
                    'message': 'Guest name updated successfully',
                    'refresh_system_prompt': True
                }, room=sid)
            else:
                print(f"Cannot update guest name: Session {sid} not found")
                emit('guest_name_update_error', {
                    'error': 'Session not found'
                }, room=sid)
                
        except Exception as e:
            print(f"Error updating guest name for SID {sid}: {e}")
            traceback.print_exc()
            emit('guest_name_update_error', {
                'error': f'Failed to update guest name: {str(e)}'
            }, room=sid)

    @socketio.on('update_system_prompt')
    @socketio_authenticated_only
    def handle_update_system_prompt(data, user_id):
        """Handle system prompt updates from the client."""
        sid = request.sid
        
        try:
            system_prompt = data.get('system_prompt')
            if not system_prompt:
                print(f"Warning: Empty system prompt received from SID {sid}")
                return
            
            print(f"Updating system prompt for SID {sid} (length: {len(system_prompt)})")
            
            # Update the session data with the new system prompt
            if sid in active_sessions:
                active_sessions[sid]['system_prompt'] = system_prompt
                print(f"Successfully updated system prompt in session for SID {sid}")
                
                # Send confirmation back to client
                emit('system_prompt_updated', {
                    'success': True,
                    'message': 'System prompt updated successfully'
                }, room=sid)
            else:
                print(f"Cannot update system prompt: Session {sid} not found")
                
        except Exception as e:
            print(f"Error updating system prompt for SID {sid}: {e}")
            traceback.print_exc()

    # Add other handlers from app.py if they exist (e.g., 'start_stream', 'stop_stream')
    # Make sure to add the @socketio_authenticated_only decorator if they require auth.

    print("Socket.IO handlers registered.")
