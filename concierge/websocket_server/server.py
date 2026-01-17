import asyncio
import websockets
import json
import base64
import time
import logging
import os
import opuslib  # Now needed for PCM to Opus encoding
import struct
import array
import traceback
from dotenv import load_dotenv
from collections import deque
import uuid
import websockets.protocol

# --- Add Gemini Live Handler Import ---
# Adjust the path based on your project structure
# Assuming utils is a sibling directory to websocket_server
import sys
parent_dir = os.path.dirname(os.path.abspath(__file__))
utils_path = os.path.join(parent_dir, '..', 'utils')
if utils_path not in sys.path:
    sys.path.append(utils_path)
try:
    from gemini_live_handler import (
        create_gemini_live_session,
        process_audio_chunk,
        get_audio_chunk,
        end_gemini_live_session,
        AUDIO_SAMPLE_RATE as GEMINI_AUDIO_SAMPLE_RATE, # Use sample rate from handler
        # Add other necessary imports from handler if needed
    )
    logging.info("Successfully imported gemini_live_handler.")
except ImportError as e:
    logging.error(f"Failed to import gemini_live_handler: {e}. Ensure utils directory is in sys.path.")
    # Handle the error appropriately, maybe exit or use a fallback
    sys.exit(1)
# --- End Gemini Live Handler Import ---


# --- Configuration & Globals ---
load_dotenv()
# GEMINI_API_KEY is now used by gemini_live_handler internally
WEBSOCKET_HOST = os.getenv("WEBSOCKET_HOST", "0.0.0.0")  # Listen on all interfaces
WEBSOCKET_PORT = int(os.getenv("WEBSOCKET_PORT", 8080))
TELNYX_SAMPLE_RATE = 16000  # Telnyx expects Opus audio at 16kHz
OPUS_CHANNELS = 1  # Mono audio
OPUS_FRAME_DURATION_MS = 20  # Standard frame duration
OPUS_APPLICATION = opuslib.APPLICATION_VOIP  # Optimize for voice
OPUS_BITRATE = 32000  # 32 kbps, good for voice
# Frame size for Opus encoding (samples per frame)
TELNYX_OPUS_FRAME_SIZE = TELNYX_SAMPLE_RATE * OPUS_FRAME_DURATION_MS // 1000

# Global dictionary to store active call states (simplified)
active_calls = {} # Key: stream_id -> Value: { "telnyx_ws": websocket, "last_active_timestamp": float, "property_id": str, "send_audio_task": asyncio.Task }
INACTIVE_CALL_CLEANUP_INTERVAL_S = 30
INACTIVE_CALL_TIMEOUT_S = 60

# Setup detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Log to console
        logging.FileHandler('/var/log/websocket_server.log')  # Log to file
    ]
)
# Set specific loggers to appropriate levels
logging.getLogger('websockets.server').setLevel(logging.INFO)
logging.getLogger('websockets.protocol').setLevel(logging.INFO)
logging.getLogger('asyncio').setLevel(logging.INFO)

# Log startup information
logging.info("=" * 80)
logging.info("WebSocket Server Starting")
logging.info(f"Python version: {sys.version}")
logging.info(f"Websockets version: {websockets.__version__}")
logging.info(f"Opuslib version: {opuslib.__version__ if hasattr(opuslib, '__version__') else 'unknown'}")
logging.info("=" * 80)

# --- Process Telnyx Media (Simplified for Gemini Live) ---
async def _process_telnyx_media(stream_id, payload):
    """Processes incoming Telnyx media messages by forwarding Opus data to Gemini Live."""
    logging.debug(f"===> ENTERING _process_telnyx_media for {stream_id}")
    if not stream_id or stream_id not in active_calls:
        logging.warning(f"_process_telnyx_media called with invalid or missing stream_id: {stream_id}")
        return

    call_state = active_calls[stream_id]
    call_state["last_active_timestamp"] = time.time() # Update activity timestamp

    # Decode the Opus payload from base64
    try:
        # Telnyx sends Opus encoded audio in the payload
        opus_bytes = base64.b64decode(payload)
        logging.debug(f"Received {len(opus_bytes)} bytes of OPUS audio from Telnyx for {stream_id}")
    except (TypeError, base64.binascii.Error) as e:
        logging.error(f"Error decoding base64 payload for {stream_id}: {e}")
        return

    # Convert Opus to PCM before sending to Gemini Live Handler
    try:
        # Get or create Opus decoder
        call_state = active_calls[stream_id]
        opus_decoder = call_state.get("opus_decoder_telnyx_to_gemini")
        if not opus_decoder:
            # Initialize Opus decoder
            logging.info(f"Initializing Opus decoder for {stream_id}")
            try:
                opus_decoder = opuslib.Decoder(TELNYX_SAMPLE_RATE, OPUS_CHANNELS)
                call_state["opus_decoder_telnyx_to_gemini"] = opus_decoder
                logging.info(f"Opus decoder initialized for {stream_id}")
            except Exception as init_err:
                logging.error(f"Failed to initialize Opus decoder for {stream_id}: {init_err}", exc_info=True)
                return

        # Log the size of the opus data for debugging
        logging.debug(f"Attempting to decode {len(opus_bytes)} bytes of Opus data for {stream_id}")

        # Check if the opus data is valid
        if len(opus_bytes) < 4:  # Opus frames should be at least a few bytes
            logging.warning(f"Opus data too small ({len(opus_bytes)} bytes) for {stream_id}, skipping")
            return

        # Decode the Opus data
        try:
            pcm_data = opus_decoder.decode(opus_bytes, TELNYX_OPUS_FRAME_SIZE)
        except opuslib.exceptions.OpusError as oe:
            # Handle specific Opus errors
            error_msg = str(oe)
            # Check for common error messages
            if 'corrupted stream' in error_msg or 'buffer too small' in error_msg:
                # These are common with streaming audio and can be safely ignored
                logging.debug(f"Opus decoding issue for {stream_id}: {error_msg} - ignoring this frame")
            else:
                # Log other Opus errors at warning level
                logging.warning(f"Opus decoding error for {stream_id}: {error_msg}")
            return

        # Handle different return types from the decoder
        try:
            if isinstance(pcm_data, bytes):
                pcm_bytes = pcm_data
                logging.debug(f"Opus decoder returned bytes directly for {stream_id}")
            elif hasattr(pcm_data, 'tobytes'):
                pcm_bytes = pcm_data.tobytes()
                logging.debug(f"Converted array to bytes for {stream_id}")
            else:
                # Convert to bytes if it's another type
                pcm_bytes = bytes(pcm_data)
                logging.debug(f"Converted {type(pcm_data)} to bytes for {stream_id}")

            # Send PCM data to Gemini Live Handler
            success = process_audio_chunk(stream_id, pcm_bytes)
            if not success:
                logging.warning(f"Failed to forward PCM chunk to Gemini Live handler for {stream_id}. Session might be inactive.")
        except Exception as e:
            # Log other exceptions as errors
            logging.error(f"Error processing/sending audio to Gemini Live handler for {stream_id}: {e}", exc_info=True)
    except Exception as outer_e:
        logging.error(f"Outer exception in _process_telnyx_media for {stream_id}: {outer_e}", exc_info=True)


# --- Remove _connect_to_gemini function ---
# This logic is now handled by gemini_live_handler.create_gemini_live_session

# --- Send Gemini Audio to Telnyx Task ---
async def send_gemini_audio_to_telnyx(stream_id: str):
    """Periodically checks for audio from Gemini Live and sends it back to Telnyx."""
    logging.info(f"Starting Gemini->Telnyx audio forwarder task for {stream_id}")
    while stream_id in active_calls:
        try:
            call_state = active_calls[stream_id]
            telnyx_ws = call_state.get("telnyx_ws")
            if not telnyx_ws or telnyx_ws.closed:
                logging.warning(f"Telnyx WebSocket closed for {stream_id}. Stopping forwarder task.")
                break

            # Get audio chunk from Gemini Live handler queue (non-blocking)
            audio_chunk = get_audio_chunk(stream_id)

            if audio_chunk:
                logging.debug(f"Received {len(audio_chunk)} bytes of audio from Gemini Live for {stream_id}")
                # Gemini Live handler provides audio ready to be sent (likely PCM).
                # Telnyx expects Opus. We need to encode PCM -> Opus here.
                # TODO: Implement PCM to Opus encoding before sending.
                # For now, sending raw PCM which Telnyx might ignore or handle incorrectly.
                # Need an Opus encoder here.

                # Encode PCM to Opus for Telnyx
                try:
                    # Get or create Opus encoder
                    opus_encoder = call_state.get("opus_encoder_gemini_to_telnyx")
                    if not opus_encoder:
                        # Initialize Opus encoder (convert from Gemini's 24kHz to Telnyx's 16kHz)
                        logging.info(f"Initializing Opus encoder for {stream_id}")

                        # First, we need to resample from GEMINI_AUDIO_SAMPLE_RATE (24kHz) to TELNYX_SAMPLE_RATE (16kHz)
                        # This is a simple implementation - a more sophisticated resampling might be needed
                        def resample_audio(pcm_data, src_rate, dst_rate):
                            """Simple audio resampling from one rate to another"""
                            try:
                                # Convert bytes to int16 samples
                                samples = array.array('h')
                                samples.frombytes(pcm_data)

                                # Calculate ratio
                                ratio = dst_rate / src_rate

                                # Create new array for resampled data
                                resampled = array.array('h')

                                # Simple resampling by picking samples at calculated intervals
                                for i in range(int(len(samples) * ratio)):
                                    src_idx = int(i / ratio)
                                    if src_idx < len(samples):
                                        resampled.append(samples[src_idx])

                                return resampled.tobytes()
                            except Exception as e:
                                logging.error(f"Error resampling audio: {e}")
                                # Return original data if resampling fails
                                return pcm_data

                        # Create the encoder
                        opus_encoder = opuslib.Encoder(TELNYX_SAMPLE_RATE, OPUS_CHANNELS, OPUS_APPLICATION)
                        opus_encoder.bitrate = OPUS_BITRATE
                        call_state["opus_encoder_gemini_to_telnyx"] = opus_encoder
                        call_state["resample_fn"] = resample_audio
                        logging.info(f"Opus encoder initialized for {stream_id}")

                    # Resample the audio from Gemini (24kHz) to Telnyx (16kHz)
                    resample_fn = call_state.get("resample_fn")
                    resampled_audio = resample_fn(audio_chunk, GEMINI_AUDIO_SAMPLE_RATE, TELNYX_SAMPLE_RATE)

                    # Convert bytes to int16 samples for Opus encoding
                    samples = array.array('h')
                    samples.frombytes(resampled_audio)

                    # Encode to Opus
                    opus_encoded_chunk = opus_encoder.encode(samples, TELNYX_OPUS_FRAME_SIZE)

                    # Base64 encode for Telnyx
                    encoded_payload = base64.b64encode(opus_encoded_chunk).decode('utf-8')
                    logging.info(f"Successfully encoded {len(resampled_audio)} bytes of PCM to {len(opus_encoded_chunk)} bytes of Opus for {stream_id}")


                    media_message = {
                        "event": "media",
                        "stream_id": stream_id,
                        "media": {
                            "payload": encoded_payload,
                            "media_format": {
                                "encoding": "opus",
                                "sample_rate": TELNYX_SAMPLE_RATE,
                                "channels": OPUS_CHANNELS
                            }
                        }
                    }
                    await telnyx_ws.send(json.dumps(media_message))
                    call_state["last_active_timestamp"] = time.time() # Update activity
                except Exception as encode_send_err:
                     logging.error(f"Error encoding/sending Gemini audio to Telnyx for {stream_id}: {encode_send_err}", exc_info=True)

            else:
                # No audio data currently available, wait a bit
                await asyncio.sleep(0.01)  # Small sleep to prevent busy-waiting

        except asyncio.CancelledError:
            logging.info(f"Gemini->Telnyx audio forwarder task cancelled for {stream_id}")
            break
        except KeyError:
             logging.warning(f"Stream {stream_id} removed while forwarder task was running.")
             break # Exit loop if call state is gone
        except websockets.exceptions.ConnectionClosed:
            logging.warning(f"Telnyx connection closed for {stream_id} during forwarder task.")
            await cleanup_call(stream_id, "Telnyx connection closed")
            break
        except Exception as e:
            logging.error(f"Unexpected error in Gemini->Telnyx forwarder task for {stream_id}: {e}", exc_info=True)
            await asyncio.sleep(1) # Wait longer on unexpected errors

    logging.info(f"Exiting Gemini->Telnyx audio forwarder task for {stream_id}")


# --- Handle Telnyx Connection (Updated) ---
async def _handle_telnyx_connection(websocket, path):
    """Handles a single WebSocket connection from Telnyx."""
    remote_address = websocket.remote_address if hasattr(websocket, 'remote_address') else 'unknown'
    connection_id = id(websocket)  # Get a unique ID for this connection
    logging.info(f"New Telnyx connection established from {remote_address}. Path: {path}, Connection ID: {connection_id}")

    # Log WebSocket details
    ws_info = {
        "remote_address": remote_address,
        "path": path,
        "connection_id": connection_id,
        "protocol": websocket.subprotocol if hasattr(websocket, 'subprotocol') else 'unknown',
        "open": not websocket.closed if hasattr(websocket, 'closed') else 'unknown'
    }
    logging.info(f"WebSocket connection details: {ws_info}")

    # Parse query parameters from path to get caller's phone number and property ID
    caller_number = None
    property_id = None
    query_params = {}

    if '?' in path:
        query_string = path.split('?', 1)[1]
        params = query_string.split('&')
        for param in params:
            if '=' in param:
                key, value = param.split('=', 1)
                query_params[key] = value
                if key == 'caller_number':
                    caller_number = value
                    logging.info(f"Extracted caller number from path: {caller_number}")
                elif key == 'property_id':
                    property_id = value
                    logging.info(f"Extracted property ID from path: {property_id}")

    logging.info(f"All query parameters: {query_params}")
    stream_id = None # Initialize stream_id

    try:
        # --- Initial Message Loop (Wait for 'start') ---
        async for initial_message in websocket:
            try:
                data = json.loads(initial_message)
                # Log the full message for debugging, but truncate media payloads
                if data.get('event') == 'media':
                    logging.debug(f"Received initial media message for {data.get('stream_id')}, ignoring until start event.")
                else:
                    # Log the full message for non-media events
                    logging.info(f"Received initial message from Telnyx: {json.dumps(data)}")
            except json.JSONDecodeError:
                logging.error(f"Received non-JSON initial message from Telnyx: {initial_message[:200]}...")
                continue # Skip malformed messages

            event = data.get("event")
            if event == "start":
                # Extract call_control_id and stream_id
                call_control_id = data.get("start", {}).get("call_control_id")
                stream_id = data.get("stream_id") # Use Telnyx provided stream_id as SID

                # Log the full start event data
                logging.info(f"START EVENT DETAILS: {json.dumps(data.get('start', {}))}")

                # Check if property_id was already extracted from query parameters
                # If not, try to get it from the 'start' payload
                start_property_id = data.get("start", {}).get("property_id")
                if start_property_id and not property_id:
                    property_id = start_property_id
                    logging.info(f"Using property ID from start event: {property_id}")

                logging.info(f"Received 'start' event. Call Control ID: {call_control_id}, Stream ID: {stream_id}, Property ID: {property_id}")

                if not call_control_id or not stream_id:
                    logging.error(f"Received 'start' event missing 'call_control_id' or 'stream_id'. Data: {data}")
                    continue # Wait for a valid start message

                # --- Check for Property ID ---
                if not property_id:
                    logging.warning(f"No property_id found for {stream_id}. Will attempt to find it based on caller number.")

                if stream_id in active_calls:
                    logging.warning(f"Received duplicate 'start' triggering event for existing stream {stream_id}. Cleaning up old state.")
                    await cleanup_call(stream_id, "Duplicate start event received")

                logging.info(f"Initiating Gemini Live session for stream {stream_id} with property {property_id}")

                # Initialize call state
                active_calls[stream_id] = {
                    "telnyx_ws": websocket,
                    "last_active_timestamp": time.time(),
                    "call_control_id": call_control_id,
                    "property_id": property_id, # Store property_id
                    "caller_number": caller_number, # Store caller's phone number
                    "send_audio_task": None, # Task for sending Gemini->Telnyx
                     # Add opus_encoder_gemini_to_telnyx later if needed
                }

                # If we have a caller number but no property_id, try to find the property based on caller's number
                if caller_number and not property_id:
                    logging.info(f"Attempting to find property for caller: {caller_number}")

                    # Use Firestore to look up property based on caller's phone number
                    try:
                        # Import the Firestore client
                        from firestore_client import list_reservations_by_phone, get_firestore_db

                        # Get reservations for this phone number
                        reservations = list_reservations_by_phone(caller_number)

                        if reservations:
                            # Sort reservations by check-in date (most recent first)
                            # Try different field names for check-in date
                            sorted_reservations = sorted(
                                reservations,
                                key=lambda r: r.get('checkInDate', r.get('CheckInDate', r.get('check_in_date', ''))),
                                reverse=True
                            )

                            # Get the property ID from the first reservation
                            first_reservation = sorted_reservations[0]

                            # Try different field names for property ID
                            property_id = (
                                first_reservation.get('propertyId') or
                                first_reservation.get('PropertyId') or
                                first_reservation.get('property_id') or
                                first_reservation.get('property')
                            )

                            if property_id:
                                logging.info(f"Found property ID {property_id} for caller {caller_number}")

                                # Update the property_id in active_calls
                                active_calls[stream_id]["property_id"] = property_id

                                # Get guest name from reservation
                                guest_name = (
                                    first_reservation.get('guestName') or
                                    first_reservation.get('GuestName') or
                                    first_reservation.get('guest_name')
                                )

                                if guest_name:
                                    active_calls[stream_id]["guest_name"] = guest_name
                                    logging.info(f"Set guest name to: {guest_name}")
                                else:
                                    # Extract the last 4 digits of the caller's number for a default guest name
                                    clean_number = ''.join(filter(str.isdigit, caller_number))
                                    last_four_digits = clean_number[-4:] if len(clean_number) >= 4 else clean_number
                                    guest_name = f"Guest {last_four_digits}"
                                    active_calls[stream_id]["guest_name"] = guest_name
                                    logging.info(f"Set default guest name to: {guest_name}")
                            else:
                                logging.warning(f"No property ID found in reservation for caller {caller_number}")
                        else:
                            logging.warning(f"No reservations found for caller {caller_number}")

                            # Extract the last 4 digits of the caller's number for a default guest name
                            clean_number = ''.join(filter(str.isdigit, caller_number))
                            last_four_digits = clean_number[-4:] if len(clean_number) >= 4 else clean_number

                            # For fallback, use a default property ID
                            # This should be removed in production
                            property_id = None
                            guest_name = f"Guest {last_four_digits}"
                            active_calls[stream_id]["guest_name"] = guest_name
                            logging.info(f"Set fallback guest name to: {guest_name}")
                    except Exception as e:
                        logging.error(f"Error in Firestore property lookup for caller {caller_number}: {e}")
                        logging.error(traceback.format_exc())

                # Create Gemini Live session using the handler
                # Pass guest name if available
                guest_name = active_calls[stream_id].get("guest_name")
                property_context = {"guestName": guest_name} if guest_name else None

                # If no property ID was found, use a fallback message
                if not property_id:
                    logging.warning(f"No property ID found for caller {caller_number}. Using fallback greeting.")
                    # Create a special property context for the fallback case
                    property_context = property_context or {}
                    property_context["fallback"] = True
                    property_context["caller_number"] = caller_number
                    # Use a placeholder property ID
                    property_id = "unknown"

                success = await create_gemini_live_session(
                    stream_id,
                    property_id,
                    property_context=property_context,
                    caller_number=caller_number
                ) # Using stream_id as session ID

                if success:
                    logging.info(f"Successfully initiated Gemini Live session via handler for {stream_id}")
                    # Start the background task to forward Gemini audio back to Telnyx
                    send_task = asyncio.create_task(send_gemini_audio_to_telnyx(stream_id))
                    active_calls[stream_id]["send_audio_task"] = send_task
                    logging.info(f"Started Gemini->Telnyx audio forwarder task for {stream_id}")
                    # Break out of the initial message loop, proceed to media handling
                    break
                else:
                    logging.error(f"Failed to create Gemini Live session for {stream_id}. Closing connection.")
                    await cleanup_call(stream_id, "Failed to initialize Gemini Live session")
                    # Ensure connection is closed if cleanup doesn't do it
                    if not websocket.closed:
                        await websocket.close(code=1011, reason="Backend session initialization failed")
                    return # Exit handler for this connection

            elif event == "media":
                # Ignore media messages received before the 'start' event
                temp_stream_id = data.get("stream_id")
                logging.debug(f"Ignoring pre-start media message for stream_id: {temp_stream_id}")
                continue
            else:
                 # Log other unexpected initial events
                 logging.warning(f"Received unexpected initial event '{event}' for connection from {remote_address}")


        # --- Media Handling Loop (After 'start') ---
        if not stream_id or stream_id not in active_calls:
             logging.error(f"Exiting handler for {remote_address}. Failed to get valid stream_id from 'start' event.")
             return # Should not happen if break condition worked, but safety check

        logging.info(f"Starting media processing loop for stream {stream_id}")
        async for message in websocket:
            # Ensure the call is still considered active before processing
            if stream_id not in active_calls:
                logging.warning(f"Stream {stream_id} no longer active. Stopping processing for {remote_address}.")
                break

            try:
                data = json.loads(message)
                event = data.get("event")

                if event == "media":
                    payload = data.get("media", {}).get("payload")
                    media_stream_id = data.get("stream_id")

                    if not payload:
                        logging.warning(f"Received media event with no payload for {media_stream_id}")
                        continue

                    if media_stream_id != stream_id:
                         logging.warning(f"Received media for unexpected stream_id {media_stream_id} (expected {stream_id}). Ignoring.")
                         continue

                    # Process the media payload (forward to Gemini Live handler)
                    await _process_telnyx_media(stream_id, payload)

                elif event == "stop":
                    logging.info(f"Received 'stop' event for stream {stream_id}. Reason: {data.get('stop', {}).get('reason', 'N/A')}")
                    await cleanup_call(stream_id, "Received stop event from Telnyx")
                    break # Exit the message loop

                # Handle other Telnyx events if necessary (e.g., dtmf, transcription)
                else:
                    logging.debug(f"Received non-media/non-stop event for {stream_id}: {event}")
                    # Update timestamp even for non-media events to keep connection alive if needed
                    if stream_id in active_calls:
                        active_calls[stream_id]["last_active_timestamp"] = time.time()


            except json.JSONDecodeError:
                logging.error(f"Received non-JSON message from Telnyx for {stream_id}: {message[:200]}...")
                continue
            except Exception as e:
                logging.error(f"Error processing Telnyx message for {stream_id}: {e}", exc_info=True)
                # Decide if we need to break or continue based on error

    except websockets.exceptions.ConnectionClosedOK:
        logging.info(f"Telnyx connection closed normally for {stream_id if stream_id else remote_address}.")
    except websockets.exceptions.ConnectionClosedError as e:
        logging.error(f"Telnyx connection closed with error for {stream_id if stream_id else remote_address}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error in Telnyx connection handler for {stream_id if stream_id else remote_address}: {e}", exc_info=True)
    finally:
        logging.info(f"Exiting Telnyx connection handler for {stream_id if stream_id else remote_address}.")
        if stream_id and stream_id in active_calls:
            await cleanup_call(stream_id, "Telnyx connection handler exited")


# --- Remove receive_and_forward_gemini_audio function ---
# This logic is now handled by gemini_live_handler and send_gemini_audio_to_telnyx


# --- Cleanup Inactive Calls (Updated) ---
async def _cleanup_inactive_calls():
    """Periodically checks for and cleans up inactive calls."""
    while True:
        await asyncio.sleep(INACTIVE_CALL_CLEANUP_INTERVAL_S)
        now = time.time()
        inactive_stream_ids = []
        active_call_count = len(active_calls) # Get count before iteration

        # Avoid modifying dict during iteration
        all_stream_ids = list(active_calls.keys())

        for stream_id in all_stream_ids:
            # Check if stream_id still exists, could be removed by another task
            if stream_id not in active_calls:
                continue

            call_state = active_calls[stream_id]
            last_active = call_state.get("last_active_timestamp", 0)

            if (now - last_active) > INACTIVE_CALL_TIMEOUT_S:
                logging.warning(f"Stream {stream_id} inactive for > {INACTIVE_CALL_TIMEOUT_S}s. Scheduling for cleanup.")
                inactive_stream_ids.append(stream_id)

        if inactive_stream_ids:
             logging.info(f"Found {len(inactive_stream_ids)} inactive streams to clean up (out of {active_call_count} total).")
             for stream_id in inactive_stream_ids:
                 # Double-check existence before cleanup
                 if stream_id in active_calls:
                      await cleanup_call(stream_id, "Call inactive timeout")
        else:
             logging.debug(f"Periodic cleanup check: No inactive calls found among {active_call_count} active calls.")

# --- Test Connection Handler ---
async def _handle_test_connection(websocket, path):
    """Handles a test connection to verify the WebSocket server is working."""
    remote_address = websocket.remote_address if hasattr(websocket, 'remote_address') else 'unknown'
    logging.info(f"Test connection received from {remote_address}. Path: {path}")

    try:
        # Send a simple test message
        test_response = {
            "status": "ok",
            "message": "WebSocket server is running",
            "timestamp": time.time(),
            "server_info": {
                "host": WEBSOCKET_HOST,
                "port": WEBSOCKET_PORT,
                "active_calls": len(active_calls)
            }
        }
        await websocket.send(json.dumps(test_response))
        logging.info(f"Sent test response to {remote_address}")

        # Wait for a message or timeout
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            logging.info(f"Received test message from {remote_address}: {message}")

            # Echo the message back
            await websocket.send(json.dumps({"echo": message}))
            logging.info(f"Echoed message back to {remote_address}")
        except asyncio.TimeoutError:
            logging.info(f"No message received from test client {remote_address} within timeout")
        except websockets.exceptions.ConnectionClosed:
            logging.info(f"Test client {remote_address} disconnected")
    except Exception as e:
        logging.error(f"Error in test connection handler: {e}", exc_info=True)
    finally:
        logging.info(f"Test connection from {remote_address} completed")

# --- Main Function (Updated) ---
async def main():
    """Starts the WebSocket server and the cleanup task."""
    # Start the inactive call cleanup task
    # We don't need to store the task reference since it runs for the lifetime of the application
    asyncio.create_task(_cleanup_inactive_calls())
    logging.info("Started inactive call cleanup task.")

    # Create a WebSocket server with multiple handlers based on path
    async def router(websocket, path):
        """Routes WebSocket connections to the appropriate handler based on path."""
        if path.startswith('/test'):
            await _handle_test_connection(websocket, path)
        else:
            await _handle_telnyx_connection(websocket, path)

    # Define WebSocket server startup with improved connection handling
    async with websockets.serve(
        router,  # Use the router function to handle connections
        WEBSOCKET_HOST,
        WEBSOCKET_PORT,
        # Increase ping interval/timeout for potentially long-lived connections
        ping_interval=30,  # Send pings every 30 seconds (more frequent)
        ping_timeout=20,   # Wait 20 seconds for pong response
        close_timeout=10,  # Wait 10 seconds for close frame
        max_size=None,     # No limit on message size
        max_queue=32       # Increase message queue size
    ):
        logging.info(f"WebSocket server started on ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
        logging.info(f"Test endpoint available at ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}/test")
        # Keep the server running indefinitely until interrupted
        await asyncio.Future()  # This will run forever

    # Cleanup task will be cancelled when the server stops if using TaskGroup
    # Or handle cancellation explicitly if needed
    # cleanup_task.cancel()
    # await cleanup_task # Wait for cleanup task to finish if cancelled

# --- Remove log_request function if not needed ---

# --- Cleanup Call (Updated) ---
async def cleanup_call(stream_id: str, reason: str):
    """Cleans up resources associated with a specific call stream_id."""
    if stream_id not in active_calls:
        logging.debug(f"Cleanup requested for already removed stream_id: {stream_id}")
        return

    logging.info(f"Cleaning up call for stream_id: {stream_id}. Reason: {reason}")
    call_state = active_calls.pop(stream_id) # Remove from active calls first

    # Close Telnyx WebSocket connection if open
    telnyx_ws = call_state.get("telnyx_ws")
    if telnyx_ws and not telnyx_ws.closed:
        try:
            await telnyx_ws.close(code=1000, reason=f"Call cleanup: {reason}")
            logging.info(f"Closed Telnyx WebSocket for {stream_id}")
        except Exception as e:
            logging.error(f"Error closing Telnyx WebSocket for {stream_id}: {e}")

    # End Gemini Live session via handler
    logging.info(f"Ending Gemini Live session via handler for {stream_id}")
    await end_gemini_live_session(stream_id) # Use the handler's end function

    # Cancel the Gemini->Telnyx audio forwarder task
    send_task = call_state.get("send_audio_task")
    if send_task and not send_task.done():
        send_task.cancel()
        try:
            await send_task # Allow task to handle cancellation
        except asyncio.CancelledError:
            logging.info(f"Gemini->Telnyx audio forwarder task cancelled successfully for {stream_id}")
        except Exception as e:
             logging.error(f"Error awaiting cancelled send_audio_task for {stream_id}: {e}")


    # Clean up Opus encoders/decoders
    if call_state.get("opus_encoder_gemini_to_telnyx"):
        # Clean up the Opus encoder
        try:
            # No explicit cleanup needed for opuslib, just remove the reference
            del call_state["opus_encoder_gemini_to_telnyx"]
            logging.info(f"Cleaned up Opus encoder for {stream_id}")
        except Exception as e:
            logging.error(f"Error cleaning up Opus encoder for {stream_id}: {e}")

    # Clean up Opus decoder
    if call_state.get("opus_decoder_telnyx_to_gemini"):
        try:
            # No explicit cleanup needed for opuslib, just remove the reference
            del call_state["opus_decoder_telnyx_to_gemini"]
            logging.info(f"Cleaned up Opus decoder for {stream_id}")
        except Exception as e:
            logging.error(f"Error cleaning up Opus decoder for {stream_id}: {e}")

    # Clean up the resampling function
    if call_state.get("resample_fn"):
        del call_state["resample_fn"]


    logging.info(f"Finished cleanup for stream_id: {stream_id}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logging.error(f"Server exited with unexpected error: {e}", exc_info=True)