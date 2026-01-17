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
import numpy as np  # For generating test tones
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
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
logging.getLogger('websockets.server').setLevel(logging.INFO) # Reduce default verbosity
logging.getLogger('websockets.protocol').setLevel(logging.INFO)
logging.info("WebSocket server starting with DEBUG logging level")

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

    # Decode Opus to PCM before sending to Gemini Live Handler
    try:
        # Get or create Opus decoder
        call_state = active_calls[stream_id]
        opus_decoder = call_state.get("opus_decoder_telnyx_to_gemini")
        if not opus_decoder:
            # Initialize Opus decoder
            logging.info(f"Initializing Opus decoder for {stream_id}")
            opus_decoder = opuslib.Decoder(TELNYX_SAMPLE_RATE, OPUS_CHANNELS)
            call_state["opus_decoder_telnyx_to_gemini"] = opus_decoder
            logging.info(f"Opus decoder initialized for {stream_id}")

        # Decode Opus to PCM
        pcm_data = opus_decoder.decode(opus_bytes, TELNYX_OPUS_FRAME_SIZE)
        pcm_bytes = pcm_data.tobytes()
        logging.debug(f"Decoded {len(opus_bytes)} bytes of Opus to {len(pcm_bytes)} bytes of PCM for {stream_id}")

        # Send PCM data to Gemini Live Handler
        success = process_audio_chunk(stream_id, pcm_bytes)
        if success:
            logging.debug(f"Forwarded PCM chunk to Gemini Live handler for {stream_id}")
        else:
            logging.warning(f"Failed to forward PCM chunk to Gemini Live handler for {stream_id}. Session might be inactive.")
    except Exception as e:
        logging.error(f"Error processing/sending audio to Gemini Live handler for {stream_id}: {e}", exc_info=True)


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
                logging.info(f"Received {len(audio_chunk)} bytes of audio from Gemini Live for {stream_id}")

                # Check if audio is silent (for debugging)
                def is_silent(audio_data, threshold=100):
                    """Check if audio data is mostly silent"""
                    try:
                        samples = array.array('h')
                        samples.frombytes(audio_data)
                        if not samples:
                            return True
                        # Calculate RMS amplitude
                        rms = np.sqrt(np.mean(np.array(samples, dtype=np.float32) ** 2))
                        is_silent = rms < threshold
                        if is_silent:
                            logging.warning(f"Audio appears to be silent (RMS: {rms:.2f}, threshold: {threshold})")
                        return is_silent
                    except Exception as e:
                        logging.error(f"Error checking for silence: {e}")
                        return False

                # Log if audio is silent
                is_silent(audio_chunk)

                # Encode PCM to Opus for Telnyx
                try:
                    # Get or create Opus encoder
                    opus_encoder = call_state.get("opus_encoder_gemini_to_telnyx")
                    if not opus_encoder:
                        # Initialize Opus encoder (convert from Gemini's 24kHz to Telnyx's 16kHz)
                        logging.info(f"Initializing Opus encoder for {stream_id}")

                        # First, we need to resample from GEMINI_AUDIO_SAMPLE_RATE (24kHz) to TELNYX_SAMPLE_RATE (16kHz)
                        def resample_audio(pcm_data, src_rate, dst_rate):
                            """Improved audio resampling from one rate to another using linear interpolation"""
                            try:
                                # Convert bytes to int16 samples
                                samples = array.array('h')
                                samples.frombytes(pcm_data)

                                # Log sample details for debugging
                                logging.debug(f"Original PCM: {len(samples)} samples, min={min(samples) if samples else 0}, max={max(samples) if samples else 0}")

                                # Calculate ratio
                                ratio = dst_rate / src_rate

                                # Create new array for resampled data
                                resampled = array.array('h')

                                # Use numpy for better quality resampling
                                try:
                                    # Convert to numpy array for better processing
                                    np_samples = np.array(samples)

                                    # Calculate number of output samples
                                    output_length = int(len(np_samples) * ratio)

                                    # Create time arrays for interpolation
                                    orig_time = np.arange(len(np_samples))
                                    new_time = np.linspace(0, len(np_samples) - 1, output_length)

                                    # Use linear interpolation for better quality
                                    resampled_np = np.interp(new_time, orig_time, np_samples)

                                    # Convert back to int16
                                    resampled_np = resampled_np.astype(np.int16)

                                    # Convert to array.array
                                    resampled = array.array('h', resampled_np.tolist())

                                    logging.debug(f"Resampled using numpy interpolation: {len(resampled)} samples")
                                except Exception as np_err:
                                    logging.warning(f"Numpy resampling failed, falling back to simple method: {np_err}")

                                    # Fallback to simple resampling if numpy fails
                                    resampled = array.array('h')
                                    for i in range(int(len(samples) * ratio)):
                                        src_idx = int(i / ratio)
                                        if src_idx < len(samples):
                                            resampled.append(samples[src_idx])

                                # Log resampled details for debugging
                                logging.debug(f"Resampled PCM: {len(resampled)} samples, min={min(resampled) if resampled else 0}, max={max(resampled) if resampled else 0}")

                                # Apply a slight volume boost to ensure audibility
                                boost_factor = 1.2  # 20% volume boost
                                for i in range(len(resampled)):
                                    # Apply boost with clipping protection
                                    boosted_value = int(resampled[i] * boost_factor)
                                    # Clip to int16 range
                                    if boosted_value > 32767:
                                        boosted_value = 32767
                                    elif boosted_value < -32768:
                                        boosted_value = -32768
                                    resampled[i] = boosted_value

                                return resampled.tobytes()
                            except Exception as e:
                                logging.error(f"Error resampling audio: {e}", exc_info=True)
                                # Return original data if resampling fails
                                return pcm_data

                        # Create the encoder with explicit settings
                        opus_encoder = opuslib.Encoder(TELNYX_SAMPLE_RATE, OPUS_CHANNELS, OPUS_APPLICATION)
                        opus_encoder.bitrate = OPUS_BITRATE
                        # Set additional encoder parameters for voice optimization
                        opus_encoder.vbr = 1  # Variable bitrate (1 = on)
                        opus_encoder.complexity = 10  # Highest complexity for better quality
                        opus_encoder.packet_loss_perc = 0  # Assume no packet loss
                        opus_encoder.inband_fec = 0  # Forward error correction off
                        opus_encoder.dtx = 0  # Disable discontinuous transmission

                        call_state["opus_encoder_gemini_to_telnyx"] = opus_encoder
                        call_state["resample_fn"] = resample_audio
                        logging.info(f"Opus encoder initialized for {stream_id} with optimized settings")

                    # Resample the audio from Gemini (24kHz) to Telnyx (16kHz)
                    resample_fn = call_state.get("resample_fn")
                    resampled_audio = resample_fn(audio_chunk, GEMINI_AUDIO_SAMPLE_RATE, TELNYX_SAMPLE_RATE)
                    logging.debug(f"Resampled {len(audio_chunk)} bytes to {len(resampled_audio)} bytes for {stream_id}")

                    # Convert bytes to int16 samples for Opus encoding
                    samples = array.array('h')
                    samples.frombytes(resampled_audio)

                    # Ensure we have enough samples for a full frame
                    if len(samples) < TELNYX_OPUS_FRAME_SIZE:
                        # Pad with silence if needed
                        padding = array.array('h', [0] * (TELNYX_OPUS_FRAME_SIZE - len(samples)))
                        samples.extend(padding)
                        logging.debug(f"Padded samples from {len(samples) - len(padding)} to {len(samples)} for {stream_id}")

                    # Encode to Opus - convert samples to bytes first
                    samples_bytes = samples.tobytes()
                    logging.debug(f"Preparing to encode {len(samples_bytes)} bytes of PCM data with {len(samples)} samples for {stream_id}")

                    # Ensure we have the right number of samples for Opus frame
                    if len(samples) != TELNYX_OPUS_FRAME_SIZE:
                        logging.warning(f"Sample count mismatch: got {len(samples)}, expected {TELNYX_OPUS_FRAME_SIZE} for {stream_id}")
                        # Adjust samples if needed (pad or truncate)
                        if len(samples) < TELNYX_OPUS_FRAME_SIZE:
                            # Pad with silence
                            padding = array.array('h', [0] * (TELNYX_OPUS_FRAME_SIZE - len(samples)))
                            samples.extend(padding)
                            samples_bytes = samples.tobytes()
                            logging.debug(f"Padded samples to {len(samples)} for {stream_id}")
                        else:
                            # Truncate to frame size
                            samples = samples[:TELNYX_OPUS_FRAME_SIZE]
                            samples_bytes = samples.tobytes()
                            logging.debug(f"Truncated samples to {TELNYX_OPUS_FRAME_SIZE} for {stream_id}")

                    # Encode to Opus with explicit frame size
                    opus_encoded_chunk = opus_encoder.encode(samples_bytes, TELNYX_OPUS_FRAME_SIZE)

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
                    logging.debug(f"Sent audio chunk ({len(audio_chunk)} bytes raw) back to Telnyx for {stream_id}")
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
    logging.info(f"New Telnyx connection established from {remote_address}. Path: {path}")

    # Parse query parameters from path to get caller's phone number
    caller_number = None
    if '?' in path:
        query_string = path.split('?', 1)[1]
        params = query_string.split('&')
        for param in params:
            if '=' in param:
                key, value = param.split('=', 1)
                if key == 'caller_number':
                    caller_number = value
                    logging.info(f"Extracted caller number from path: {caller_number}")

    stream_id = None # Initialize stream_id

    try:
        # --- Initial Message Loop (Wait for 'start') ---
        async for initial_message in websocket:
            try:
                data = json.loads(initial_message)
                logging.debug(f"Received initial message from Telnyx: {json.dumps(data)[:200]}..." if not data.get('event') == 'media' else f"Received initial media message for {data.get('stream_id')}, ignoring until start event.")
            except json.JSONDecodeError:
                logging.error(f"Received non-JSON initial message from Telnyx: {initial_message[:200]}...")
                continue # Skip malformed messages

            event = data.get("event")
            if event == "start" or event == "connected":
                # Extract call_control_id and stream_id
                if event == "start":
                    call_control_id = data.get("start", {}).get("call_control_id")
                    stream_id = data.get("stream_id") # Use Telnyx provided stream_id as SID
                    # --- !!! CRITICAL: Get Property ID !!! ---
                    # Assuming property_id is passed in the 'start' payload
                    # Adjust this key based on how Telnyx sends it (e.g., custom headers)
                    property_id = data.get("start", {}).get("property_id") # EXAMPLE KEY
                    # --- !!! ---
                else:  # event == "connected"
                    call_control_id = data.get("call_control_id")
                    stream_id = data.get("stream_id")
                    if not stream_id:
                        # Generate a unique stream_id if not provided
                        stream_id = str(uuid.uuid4())
                    property_id = None  # Will be looked up by caller_number later

                logging.info(f"Received '{event}' event. Call Control ID: {call_control_id}, Stream ID: {stream_id}, Property ID: {property_id}")

                if not call_control_id or not stream_id:
                    logging.error(f"Received '{event}' event missing 'call_control_id' or 'stream_id'. Data: {data}")
                    continue # Wait for a valid start message

                # --- Check for Property ID ---
                if not property_id:
                    logging.error(f"CRITICAL: Received 'start' event for {stream_id} WITHOUT 'property_id'. Cannot initialize Gemini context. Data: {data}")
                    # Decide how to handle: close connection, send error message?
                    # For now, log error and continue, but Gemini context will be limited/missing.
                    # await websocket.close(code=1008, reason="Missing required property_id")
                    # return

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
                    # Import DynamoDB client functions dynamically to avoid circular imports
                    try:
                        # Import DynamoDB client directly from the parent directory
                        sys.path.append(os.path.join(parent_dir, '..'))
                        from utils import dynamodb_client

                        # Look up reservations by phone number
                        reservations = dynamodb_client.list_reservations_by_phone(caller_number)
                        if reservations:
                            # Use the first reservation's property ID
                            # In a real implementation, you might want to choose the most relevant one
                            property_id = reservations[0].get('PropertyId')
                            logging.info(f"Found property ID {property_id} for caller {caller_number}")
                            # Update the property_id in active_calls
                            active_calls[stream_id]["property_id"] = property_id
                    except Exception as e:
                        logging.error(f"Error finding property for caller {caller_number}: {e}")
                        # Continue with no property_id

                # Create Gemini Live session using the handler
                success = await create_gemini_live_session(stream_id, property_id, caller_number=caller_number) # Using stream_id as session ID

                if success:
                    logging.info(f"Successfully initiated Gemini Live session via handler for {stream_id}")
                    # Start the background task to forward Gemini audio back to Telnyx
                    send_task = asyncio.create_task(send_gemini_audio_to_telnyx(stream_id))
                    active_calls[stream_id]["send_audio_task"] = send_task
                    logging.info(f"Started Gemini->Telnyx audio forwarder task for {stream_id}")

                    # Send a test tone to verify the audio path
                    try:
                        # Generate a simple sine wave test tone (1 second, 440 Hz)
                        sample_rate = TELNYX_SAMPLE_RATE
                        duration = 1.0  # seconds
                        frequency = 440.0  # Hz (A4 note)
                        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
                        # Increase amplitude for better audibility (0.8 instead of 0.5)
                        test_tone = (32767 * 0.8 * np.sin(2 * np.pi * frequency * t)).astype(np.int16)

                        # Get or create Opus encoder with optimized settings
                        opus_encoder = opuslib.Encoder(TELNYX_SAMPLE_RATE, OPUS_CHANNELS, OPUS_APPLICATION)
                        opus_encoder.bitrate = OPUS_BITRATE
                        # Set additional encoder parameters for voice optimization
                        opus_encoder.vbr = 1  # Variable bitrate (1 = on)
                        opus_encoder.complexity = 10  # Highest complexity for better quality
                        opus_encoder.packet_loss_perc = 0  # Assume no packet loss
                        opus_encoder.inband_fec = 0  # Forward error correction off
                        opus_encoder.dtx = 0  # Disable discontinuous transmission

                        active_calls[stream_id]["opus_encoder_gemini_to_telnyx"] = opus_encoder

                        logging.info(f"Sending test tone ({len(test_tone)} samples) to Telnyx for {stream_id}")

                        # Encode the test tone to Opus
                        frame_size = TELNYX_OPUS_FRAME_SIZE
                        for i in range(0, len(test_tone), frame_size):
                            # Get a frame of audio
                            frame = test_tone[i:i+frame_size]
                            if len(frame) < frame_size:
                                # Pad with silence if needed
                                frame = np.pad(frame, (0, frame_size - len(frame)), 'constant')

                            # Convert to array.array for consistency with main audio path
                            frame_array = array.array('h', frame.tolist())
                            frame_bytes = frame_array.tobytes()

                            # Encode to Opus with explicit frame size
                            opus_encoded_chunk = opus_encoder.encode(frame_bytes, frame_size)

                            # Base64 encode for Telnyx
                            encoded_payload = base64.b64encode(opus_encoded_chunk).decode('utf-8')

                            # Send to Telnyx
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
                            await websocket.send(json.dumps(media_message))

                        logging.info(f"Sent test tone to Telnyx for {stream_id}")
                    except Exception as e:
                        logging.error(f"Error sending test tone to Telnyx for {stream_id}: {e}", exc_info=True)

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
                 logging.warning(f"Unexpected initial event type: {event}")


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

# --- Main Function (Updated) ---
async def main():
    """Starts the WebSocket server and the cleanup task."""
    # Start the inactive call cleanup task
    # We don't need to store the task reference since it runs for the lifetime of the application
    asyncio.create_task(_cleanup_inactive_calls())
    logging.info("Started inactive call cleanup task.")

    # Define WebSocket server startup
    async with websockets.serve(
        _handle_telnyx_connection,
        WEBSOCKET_HOST,
        WEBSOCKET_PORT,
        # Increase ping interval/timeout for potentially long-lived connections
        ping_interval=60, # Send pings every 60 seconds
        ping_timeout=30   # Wait 30 seconds for pong response
    ):
        logging.info(f"WebSocket server started on ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
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