#!/usr/bin/env python3
"""
Telnyx Bidirectional Streaming with Gemini Live API

This module implements bidirectional audio streaming between Telnyx phone calls
and Google's Gemini Live API. It handles WebSocket connections from Telnyx,
processes the audio, and streams it to Gemini Live API, then returns Gemini's
responses back to the caller.

Based on the Telnyx WebSocket Media Streaming API:
https://developers.telnyx.com/docs/voice/programmable-voice/media-streaming
"""

import os
import json
import time
import base64
import logging
import asyncio
import argparse
import aiohttp
import websockets
from aiohttp import web
from dotenv import load_dotenv

# Import Firebase and Firestore
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    logger = logging.getLogger(__name__)
    logger.info("Firebase Admin SDK imported successfully")
except ImportError:
    logger.warning("Firebase Admin SDK not installed. Context retrieval will not work.")
    firebase_admin = None
    firestore = None

# Import our modules
try:
    # Try relative imports first (for package usage)
    from .gemini_live_client import GeminiLiveClient
    from .audio_processor import resample_audio, encode_audio, decode_audio
    from .call_manager import CallManager
    from .utils import setup_logging, load_config, parse_arguments, mask_api_key
    from .websocket_adapter import websocket_adapter
except ImportError:
    # Fall back to direct imports (for direct script execution)
    from gemini_live_client import GeminiLiveClient
    from audio_processor import resample_audio, encode_audio, decode_audio
    from call_manager import CallManager
    from utils import setup_logging, load_config, parse_arguments, mask_api_key
    from websocket_adapter import websocket_adapter

# Load environment variables
load_dotenv()

# Configure logging
logger = setup_logging()

# Get API keys from environment variables
TELNYX_API_KEY = os.getenv("TELNYX_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Log the API keys (masked for security)
logger.info(f"Telnyx API key loaded: {mask_api_key(TELNYX_API_KEY)}")
logger.info(f"Gemini API key loaded: {mask_api_key(GEMINI_API_KEY)}")

# Constants
TELNYX_SAMPLE_RATE = 16000  # Telnyx expects audio at 16kHz
GEMINI_SAMPLE_RATE = 24000  # Gemini provides audio at 24kHz
AUDIO_CHANNELS = 1  # Mono audio
GEMINI_LIVE_MODEL = "gemini-2.0-flash-live-001"  # Model ID for voice calls

# Initialize call manager
call_manager = CallManager()

# Dictionary to store call contexts by call control ID
call_contexts = {}

# Import Google Generative AI
try:
    import google.generativeai as genai
    logger.info("Google Generative AI imported successfully")
except ImportError:
    logger.warning("Failed to import Google Generative AI. Make sure it's installed.")

# Import Firebase and Firestore
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    logger.info("Firebase Admin SDK imported successfully")
except ImportError:
    logger.warning("Firebase Admin SDK not installed. Context retrieval will not work.")
    firebase_admin = None
    firestore = None

# Import audio processing libraries
try:
    import audioop
    logger.info("Audio processing libraries imported successfully")
except ImportError:
    logger.warning("Failed to import audio processing libraries. Make sure they're installed.")

async def handle_websocket(websocket, path):
    """
    Handle WebSocket connections from Telnyx.

    This function processes incoming WebSocket connections from Telnyx,
    extracts audio data, sends it to Gemini Live API, and returns
    Gemini's responses back to the caller.

    Args:
        websocket: The WebSocket connection
        path: The request path
    """
    remote_address = websocket.remote_address if hasattr(websocket, 'remote_address') else 'unknown'
    logger.info(f"New Telnyx connection from {remote_address}. Path: {path}")

    # Extract caller number from path if available
    caller_number = None
    if '?' in path:
        query_string = path.split('?', 1)[1]
        params = query_string.split('&')
        for param in params:
            if '=' in param:
                key, value = param.split('=', 1)
                if key == 'caller_number':
                    caller_number = value
                    logger.info(f"Extracted caller number: {caller_number}")

    # Variables to track the WebSocket connection
    stream_id = None
    gemini_client = None

    try:
        # Send connected event
        connected_event = {
            "event": "connected",
            "version": "1.0.0"
        }
        await websocket.send(json.dumps(connected_event))
        logger.info(f"Sent connected event: {connected_event}")

        # Process incoming messages
        async for message in websocket:
            try:
                data = json.loads(message)
                event_type = data.get('event')

                # Log the event (excluding media payloads for brevity)
                if event_type != 'media':
                    logger.info(f"Received WebSocket message: {data}")
                else:
                    logger.debug(f"Received media event for stream ID: {data.get('stream_id')}")

                # Handle different event types
                if event_type == 'start':
                    # Extract stream ID and call details
                    stream_id = data.get('stream_id')
                    start_data = data.get('start', {})
                    call_control_id = start_data.get('call_control_id')
                    from_number = start_data.get('from')
                    to_number = start_data.get('to')

                    logger.info(f"[WS-DEBUG] Call started - Stream ID: {stream_id}, From: {from_number}, To: {to_number}")

                    # Get context for the call based on caller's phone number
                    # First check if we already have context for this call control ID
                    context = None
                    property_id = None
                    guest_name = None

                    if call_control_id in call_contexts:
                        logger.info(f"[WS-DEBUG] Found existing context for call control ID: {call_control_id}")
                        context_info = call_contexts[call_control_id]
                        context = context_info.get("context")
                        property_id = context_info.get("property_id")
                        guest_name = context_info.get("guest_name")
                        logger.info(f"[WS-DEBUG] Using context from call_contexts dictionary")
                    else:
                        # If not, retrieve it based on the caller's phone number
                        logger.info(f"[WS-DEBUG] No existing context found, getting context for caller: {from_number}")
                        try:
                            context, property_id, guest_name = await _get_context_for_caller(from_number)
                            logger.info(f"[WS-DEBUG] Successfully retrieved context for caller: {from_number}")
                        except Exception as e:
                            logger.error(f"[WS-DEBUG] Error getting context for caller: {from_number}: {e}", exc_info=True)
                            context = ""
                            property_id = None
                            guest_name = None

                        # Store in call_contexts for future use
                        call_contexts[call_control_id] = {
                            "context": context,
                            "property_id": property_id,
                            "guest_name": guest_name,
                            "caller_phone_number": from_number
                        }
                        logger.info(f"[WS-DEBUG] Stored context in call_contexts dictionary")

                    # Store property ID and guest name in call state
                    call_state = {
                        "property_id": property_id,
                        "guest_name": guest_name,
                        "context": context,
                        "caller_phone_number": from_number
                    }

                    if property_id:
                        logger.info(f"[WS-DEBUG] Found property ID: {property_id} for caller: {from_number}")
                    else:
                        logger.warning(f"[WS-DEBUG] No property found for caller: {from_number}")

                    if guest_name:
                        logger.info(f"[WS-DEBUG] Found guest name: {guest_name} for caller: {from_number}")
                    else:
                        logger.warning(f"[WS-DEBUG] No guest name found for caller: {from_number}")

                    # Initialize Gemini Live client for this call with context
                    logger.info(f"[WS-DEBUG] Initializing Gemini Live client for stream ID: {stream_id}")
                    logger.info(f"[WS-DEBUG] Using model: {GEMINI_LIVE_MODEL}, voice: Aoede")
                    logger.info(f"[WS-DEBUG] Context length: {len(context) if context else 0} characters")

                    try:
                        gemini_client = GeminiLiveClient(
                            api_key=GEMINI_API_KEY,
                            model=GEMINI_LIVE_MODEL,
                            stream_id=stream_id,
                            voice="Aoede",  # Explicitly set the voice to Aoede
                            context=context  # Pass the context to the client
                        )
                        logger.info(f"[WS-DEBUG] Successfully initialized Gemini Live client")
                    except Exception as e:
                        logger.error(f"[WS-DEBUG] Error initializing Gemini Live client: {e}", exc_info=True)
                        # Create a minimal client that will trigger the fallback mechanism
                        gemini_client = GeminiLiveClient(
                            api_key=GEMINI_API_KEY,
                            model=GEMINI_LIVE_MODEL,
                            stream_id=stream_id,
                            voice="Aoede"
                        )
                        logger.info(f"[WS-DEBUG] Created minimal Gemini Live client for fallback")

                    # Store call information
                    call_manager.add_call(
                        stream_id=stream_id,
                        call_control_id=call_control_id,
                        from_number=from_number,
                        to_number=to_number,
                        telnyx_ws=websocket,
                        gemini_client=gemini_client,
                        **call_state  # Add context and property information
                    )

                    # Connect to Gemini Live API
                    logger.info(f"[WS-DEBUG] Connecting to Gemini Live API for stream ID: {stream_id}")
                    try:
                        welcome_message = await gemini_client.connect()

                        # Check if connection was successful
                        if gemini_client.is_connected and gemini_client.is_running:
                            # Log the welcome message but don't send it as audio
                            # Instead, we'll prompt Gemini to generate a proper audio response
                            logger.info(f"[WS-DEBUG] Gemini connected with welcome message: {welcome_message}")

                            # Get connection status for debugging
                            status = gemini_client.get_connection_status()
                            logger.info(f"[WS-DEBUG] Connection state: {status['connection_state']}")
                            logger.info(f"[WS-DEBUG] WebSocket state: {status['websocket_state']}")

                            # Start audio forwarding task - this will handle sending audio from Gemini to Telnyx
                            logger.info(f"[WS-DEBUG] Starting audio forwarding task for stream ID: {stream_id}")
                            asyncio.create_task(forward_gemini_audio(stream_id, websocket))

                            # Create a personalized welcome message if we have guest information
                            welcome_prompt = "Please welcome the caller and ask how you can help them today."
                            if guest_name:
                                welcome_prompt = f"Please welcome {guest_name} and ask how you can help them today."

                            # Send a text prompt to Gemini to generate a welcome message with audio
                            logger.info(f"[WS-DEBUG] Sending welcome prompt to Gemini for stream ID: {stream_id}")
                            await gemini_client.send_text(welcome_prompt)
                            logger.info(f"[WS-DEBUG] Sent welcome prompt to Gemini for stream ID: {stream_id}")
                        else:
                            # Connection failed, use fallback
                            logger.warning(f"[WS-DEBUG] Gemini Live connection failed for stream ID: {stream_id}")
                            logger.warning(f"[WS-DEBUG] Connection state: {gemini_client.connection_state}")
                            logger.warning(f"[WS-DEBUG] Connection error: {gemini_client.connection_error}")

                            # Start audio forwarding task - this will handle the fallback mechanism
                            logger.info(f"[WS-DEBUG] Starting audio forwarding task with fallback for stream ID: {stream_id}")
                            asyncio.create_task(forward_gemini_audio(stream_id, websocket))

                            # Use fallback immediately
                            logger.info(f"[WS-DEBUG] Using fallback TTS for stream ID: {stream_id}")
                            await _use_fallback_tts(stream_id, call_control_id, False)
                    except Exception as e:
                        # Error connecting, use fallback
                        logger.error(f"[WS-DEBUG] Error connecting to Gemini Live API for stream ID: {stream_id}: {e}", exc_info=True)

                        # Start audio forwarding task - this will handle the fallback mechanism
                        logger.info(f"[WS-DEBUG] Starting audio forwarding task with fallback for stream ID: {stream_id}")
                        asyncio.create_task(forward_gemini_audio(stream_id, websocket))

                        # Use fallback immediately
                        logger.info(f"[WS-DEBUG] Using fallback TTS for stream ID: {stream_id}")
                        await _use_fallback_tts(stream_id, call_control_id, False)

                elif event_type == 'media' and stream_id:
                    # Process media event
                    media = data.get('media', {})
                    payload = media.get('payload', '')

                    # Get call state
                    call_state = call_manager.get_call(stream_id)
                    if not call_state:
                        logger.warning(f"Received media for unknown stream ID: {stream_id}")
                        continue

                    # Update call state
                    call_manager.update_call_activity(stream_id)

                    # Track media packets
                    media_packets_received = call_state.get("media_packets_received", 0) + 1
                    call_manager.increment_media_packets(stream_id, "received")

                    # Log periodic status for incoming packets
                    if media_packets_received % 10 == 0:
                        logger.info(f"Received {media_packets_received} media packets for stream ID: {stream_id}")

                    # Decode the base64 audio data
                    try:
                        audio_data = base64.b64decode(payload)
                        logger.info(f"Decoded {len(audio_data)} bytes of audio from Telnyx for stream ID: {stream_id}")

                        # Check for silence or very small audio packets
                        if len(audio_data) < 100:
                            logger.warning(f"Received very small audio packet ({len(audio_data)} bytes) for stream ID: {stream_id}")

                        # Send the audio to Gemini Live API
                        gemini_client = call_state.get("gemini_client")
                        if gemini_client:
                            # Resample the audio to Gemini's sample rate
                            resampled_audio = resample_audio(audio_data, TELNYX_SAMPLE_RATE, GEMINI_SAMPLE_RATE)
                            logger.info(f"Resampled to {len(resampled_audio)} bytes for Gemini (24kHz)")

                            # Send to Gemini
                            await gemini_client.send_audio(resampled_audio)
                        else:
                            logger.warning(f"No Gemini client available for stream ID: {stream_id}")
                    except Exception as e:
                        logger.error(f"Error processing media for stream ID {stream_id}: {e}", exc_info=True)

                elif event_type == 'stop' and stream_id:
                    # Handle call end
                    logger.info(f"Call ended for stream ID: {stream_id}")

                    # Clean up resources
                    await call_manager.remove_call(stream_id)

                elif event_type == 'dtmf':
                    # Handle DTMF event
                    dtmf = data.get('dtmf', {})
                    digit = dtmf.get('digit')
                    logger.info(f"Received DTMF event for stream ID: {stream_id}, digit: {digit}")

                    # Send a response to the DTMF event
                    dtmf_response = {
                        "event": "media",
                        "media": {
                            "payload": base64.b64encode(f"You pressed {digit}".encode()).decode()
                        }
                    }
                    await websocket.send(json.dumps(dtmf_response))
                    logger.info(f"Sent DTMF response to stream ID: {stream_id}")

                elif event_type == 'error':
                    # Handle error event
                    payload = data.get('payload', {})
                    error_code = payload.get('code')
                    error_title = payload.get('title')
                    error_detail = payload.get('detail')

                    logger.error(f"Telnyx stream error: {error_title} ({error_code}) - {error_detail}")

                    # Handle specific error codes
                    if error_code == 100002:  # Unknown stream error
                        logger.warning(f"Received unknown stream error for stream ID: {stream_id}. Continuing processing.")
                        # Continue processing despite the error
                        continue

                    # For other errors, try to recover
                    if gemini_client and not gemini_client.is_running:
                        logger.info(f"Attempting to reconnect Gemini client after stream error for stream ID: {stream_id}")
                        try:
                            await gemini_client.connect()
                            if gemini_client.is_running:
                                logger.info(f"Successfully reconnected Gemini client for stream ID: {stream_id}")
                            else:
                                logger.warning(f"Failed to reconnect Gemini client for stream ID: {stream_id}")
                        except Exception as e:
                            logger.error(f"Error reconnecting Gemini client after stream error: {e}", exc_info=True)

                else:
                    # Handle unknown event type
                    logger.warning(f"Received unknown event type: {event_type}")
                    logger.warning(f"Full message: {data}")

            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON: {message}")
            except Exception as e:
                logger.error(f"Error handling message: {e}", exc_info=True)

    except websockets.exceptions.ConnectionClosed as e:
        logger.info(f"WebSocket connection closed: {e}")
    except Exception as e:
        logger.error(f"Error in WebSocket handler: {e}", exc_info=True)
    finally:
        # Clean up resources when the connection is closed
        if stream_id and call_manager.call_exists(stream_id):
            await call_manager.remove_call(stream_id)
        logger.info(f"WebSocket connection from {remote_address} closed")

async def handle_http_request(request):
    """Handle HTTP webhook requests from Telnyx."""
    try:
        # Parse the request body
        body = await request.json()

        # Log the raw webhook payload for debugging
        logger.info(f"[WEBHOOK-RAW] Received webhook payload: {json.dumps(body)}")

        # Extract event data
        event_data = body.get('data', {})
        event_type = event_data.get('event_type')
        payload = event_data.get('payload', {})
        call_control_id = payload.get('call_control_id')

        logger.info(f"Received webhook: {event_type} for call control ID: {call_control_id}")

        # Process different event types
        if event_type == 'call.initiated':
            # Handle new call
            logger.info(f"[WEBHOOK-DEBUG] Call initiated: {call_control_id}")

            # Extract caller information
            caller_number = payload.get('from')
            to_number = payload.get('to')

            if caller_number:
                logger.info(f"[WEBHOOK-DEBUG] Call from {caller_number} to {to_number}")

                # Get context for the call based on caller's phone number
                logger.info(f"[WEBHOOK-DEBUG] Getting context for caller: {caller_number}")
                try:
                    context, property_id, guest_name = await _get_context_for_caller(caller_number)

                    if property_id:
                        logger.info(f"[WEBHOOK-DEBUG] Found property ID: {property_id} for caller: {caller_number}")
                    else:
                        logger.warning(f"[WEBHOOK-DEBUG] No property found for caller: {caller_number}")

                    if guest_name:
                        logger.info(f"[WEBHOOK-DEBUG] Found guest name: {guest_name} for caller: {caller_number}")
                    else:
                        logger.warning(f"[WEBHOOK-DEBUG] No guest name found for caller: {caller_number}")

                    logger.info(f"[WEBHOOK-DEBUG] Context length: {len(context) if context else 0} characters")

                    # Store context in a global dictionary for later use
                    call_contexts[call_control_id] = {
                        "context": context,
                        "property_id": property_id,
                        "guest_name": guest_name,
                        "caller_phone_number": caller_number
                    }
                    logger.info(f"[WEBHOOK-DEBUG] Stored context for call control ID: {call_control_id}")
                except Exception as e:
                    logger.error(f"[WEBHOOK-DEBUG] Error getting context for caller: {caller_number}: {e}", exc_info=True)
                    # Initialize with empty context
                    call_contexts[call_control_id] = {
                        "context": "",
                        "property_id": None,
                        "guest_name": None,
                        "caller_phone_number": caller_number
                    }
                    logger.info(f"[WEBHOOK-DEBUG] Stored empty context for call control ID: {call_control_id}")

                # Answer the call
                logger.info(f"[WEBHOOK-DEBUG] Answering call: {call_control_id}")
                result = await answer_call(call_control_id)
                logger.info(f"[WEBHOOK-DEBUG] Answer call result: {result}")

        elif event_type == 'call.answered':
            # Handle call answered event
            logger.info(f"[WEBHOOK-DEBUG] Call answered: {call_control_id}")

            # Log context information if available
            if call_control_id in call_contexts:
                context_info = call_contexts[call_control_id]
                property_id = context_info.get("property_id")
                guest_name = context_info.get("guest_name")
                context = context_info.get("context")

                if property_id:
                    logger.info(f"[WEBHOOK-DEBUG] Using property ID: {property_id} for call: {call_control_id}")
                if guest_name:
                    logger.info(f"[WEBHOOK-DEBUG] Using guest name: {guest_name} for call: {call_control_id}")
                logger.info(f"[WEBHOOK-DEBUG] Context length: {len(context) if context else 0} characters")
            else:
                logger.warning(f"[WEBHOOK-DEBUG] No context found for call: {call_control_id}")

            # Start bidirectional streaming
            logger.info(f"[WEBHOOK-DEBUG] Starting bidirectional streaming for call: {call_control_id}")
            result = await start_bidirectional_streaming(call_control_id)
            logger.info(f"[WEBHOOK-DEBUG] Start bidirectional streaming result: {result}")

        elif event_type == 'streaming.started':
            # Handle streaming started
            logger.info(f"[WEBHOOK-DEBUG] Streaming started for call: {call_control_id}")

            # Get context information if available
            if call_control_id in call_contexts:
                context_info = call_contexts[call_control_id]
                property_id = context_info.get("property_id")
                guest_name = context_info.get("guest_name")
                context = context_info.get("context")
                caller_number = context_info.get("caller_phone_number")

                logger.info(f"[WEBHOOK-DEBUG] Streaming started with context for call: {call_control_id}")

                # Find the stream ID for this call control ID (will be set when WebSocket connection is established)
                # This will be used later when the WebSocket connection is established
                # and the Gemini Live client is created

                # For now, just log that we have context ready
                logger.info(f"[WEBHOOK-DEBUG] Context ready for streaming, waiting for WebSocket connection")
            else:
                logger.warning(f"[WEBHOOK-DEBUG] No context found for call: {call_control_id} during streaming.started event")

        elif event_type == 'streaming.stopped':
            # Handle streaming stopped
            logger.info(f"[WEBHOOK-DEBUG] Streaming stopped for call: {call_control_id}")

        elif event_type == 'call.hangup':
            # Handle call hangup
            logger.info(f"[WEBHOOK-DEBUG] Call hangup: {call_control_id}")

        elif event_type == 'call.transcription':
            # Handle transcription event
            logger.info(f"[WEBHOOK-DEBUG] Received transcription event for call: {call_control_id}")

            # Log the raw payload for debugging
            logger.info(f"[WEBHOOK-DEBUG] Raw transcription payload: {json.dumps(payload)}")

            # Extract transcription data according to Telnyx documentation
            # The transcription data should be in payload.transcription_data
            transcription_data = payload.get('transcription_data', {})

            # If transcription_data is not found, try the old format
            if not transcription_data:
                # Try old format where data might be directly in payload
                transcription_data = payload
                logger.info(f"[WEBHOOK-DEBUG] Using fallback transcription data format")

            # Extract transcript, is_final, and confidence
            transcript = transcription_data.get('transcript', '')
            is_final = transcription_data.get('is_final', False)
            confidence = transcription_data.get('confidence', 0)

            logger.info(f"[WEBHOOK-DEBUG] Transcription details - Text: '{transcript}', Final: {is_final}, Confidence: {confidence}")

            # Find the stream ID for this call control ID
            stream_id = None
            for sid, call_info in call_manager.active_calls.items():
                if call_info.get("call_control_id") == call_control_id:
                    stream_id = sid
                    logger.info(f"[WEBHOOK-DEBUG] Found matching stream ID: {stream_id} for call control ID: {call_control_id}")
                    break

            if stream_id:
                # Process the transcription
                await _handle_transcription_event(event_data, stream_id, call_control_id)
            else:
                logger.warning(f"[WEBHOOK-DEBUG] Could not find stream ID for call control ID: {call_control_id}")
                # Try to find the call in call_contexts
                if call_control_id in call_contexts:
                    logger.info(f"[WEBHOOK-DEBUG] Found call in call_contexts but not in active_calls. Call may be initializing.")

                    # Even if we don't have a stream ID yet, we can still log the transcript
                    # This helps with debugging transcription issues
                    logger.info(f"[WEBHOOK-DEBUG] Received transcript without stream ID: '{transcript}'")
                else:
                    logger.warning(f"[WEBHOOK-DEBUG] Call not found in call_contexts either. This may be an orphaned call.")

        # Return success response
        return web.json_response({"message": "Webhook received"})

    except Exception as e:
        logger.error(f"Error handling webhook: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)

async def answer_call(call_control_id):
    """
    Answer a call using the Telnyx API.
    """
    try:
        # Create the answer command
        url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/answer"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {TELNYX_API_KEY}"
        }
        data = {
            "client_state": "aGF2ZSBhIG5pY2UgZGF5ID1d"
        }

        # Send the answer command
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                result = await response.json()
                logger.info(f"Answer call result: {result}")
                return result

    except Exception as e:
        logger.error(f"Error answering call: {e}", exc_info=True)
        return None

async def start_bidirectional_streaming(call_control_id):
    """
    Start bidirectional streaming for a call using the Telnyx API.

    This function configures the call to stream audio to our WebSocket server
    and enables bidirectional streaming so we can send audio back to the caller.
    """
    try:
        # Get the WebSocket URL
        websocket_url = os.getenv("WEBSOCKET_URL", "wss://voice.guestrix.ai/ws/")

        # Create the streaming command
        url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/streaming_start"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {TELNYX_API_KEY}"
        }
        data = {
            "stream_url": websocket_url,
            "stream_track": "both_tracks",
            "bidirectional": True,
            "stream_bidirectional_codec": "G722",  # Changed from OPUS to G722 for lower compute/memory requirements
            "stream_bidirectional_sampling_rate": 16000
        }

        # Send the streaming command
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                result = await response.json()
                logger.info(f"Start bidirectional streaming result: {result}")
                return result

    except Exception as e:
        logger.error(f"Error starting bidirectional streaming: {e}", exc_info=True)
        return None

async def get_call_details(call_control_id):
    """
    Get call details from Telnyx API.
    """
    try:
        url = f"https://api.telnyx.com/v2/calls/{call_control_id}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {TELNYX_API_KEY}"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                result = await response.json()
                logger.info(f"Call details result: {result}")
                return result

    except Exception as e:
        logger.error(f"Error getting call details: {e}", exc_info=True)
        return None

async def send_text_to_telnyx(call_control_id, text, use_default_voice=False):
    """
    Send text to Telnyx using the speak command.

    This function uses the Telnyx API to convert text to speech and play it to the caller.
    It uses the preferred voice settings for better audio quality.

    Args:
        call_control_id: The Telnyx call control ID
        text: The text to speak
        use_default_voice: Whether to use the default Telnyx voice (free) instead of Azure neural voice
    """
    try:
        # Create the speak command
        url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/speak"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {TELNYX_API_KEY}"
        }

        # Choose voice based on parameter
        if use_default_voice:
            # Use default Telnyx voice (free)
            data = {
                "payload": text,
                "voice": "Telnyx.en-US.Standard-A",  # Default female voice
                "language": "en-US",
                "payload_type": "text"
            }
            logger.info(f"Using default Telnyx voice for message: '{text}'")
        else:
            # Use Azure neural voice for better quality
            data = {
                "payload": text,
                "voice": "Azure.en-US-Ava:DragonHDLatestNeural",
                "language": "en-US",
                "payload_type": "text"
            }
            logger.info(f"Using Azure neural voice for message: '{text}'")

        # Send the speak command
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                result = await response.json()
                logger.info(f"Speak result: {result}")
                return result

    except Exception as e:
        logger.error(f"Error sending text to Telnyx: {e}", exc_info=True)
        return None

async def _use_fallback_tts(stream_id, call_control_id, already_sent=False):
    """
    Use Telnyx speak API as a fallback when Gemini is not available.

    Args:
        stream_id: The stream ID for the call
        call_control_id: The Telnyx call control ID
        already_sent: Whether a fallback message has already been sent (ignored now)
    """
    if not call_control_id:
        logger.warning(f"[FALLBACK-DEBUG] Cannot use fallback TTS for {stream_id}: no call control ID")
        return

    # Check if we've already sent a fallback message
    call_state = call_manager.get_call(stream_id)
    fallback_sent = call_state.get("fallback_sent", False) if call_state else False
    fallback_count = call_state.get("fallback_count", 0) if call_state else 0

    # Log the fallback status
    if fallback_sent:
        logger.info(f"[FALLBACK-DEBUG] Fallback already sent for {stream_id}, using Gemini API directly (count: {fallback_count})")
    else:
        logger.info(f"[FALLBACK-DEBUG] First fallback for {stream_id}, sending initial message")

    try:
        # If this is the first fallback, send the initial message
        if not fallback_sent:
            # Send fallback message
            fallback_text = "We're sorry, but we're unable to process your call at this time. Please try again later."
            logger.info(f"[FALLBACK-DEBUG] Sending fallback message to Telnyx for {stream_id}")
            result = await send_text_to_telnyx(call_control_id, fallback_text, use_default_voice=True)

            if result and result.get('data', {}).get('result') == 'ok':
                logger.info(f"[FALLBACK-DEBUG] Successfully sent fallback message to Telnyx for {stream_id}")

                # Mark fallback as sent in call state
                call_manager.update_call_state(stream_id, {
                    "fallback_sent": True,
                    "fallback_count": fallback_count + 1,
                    "fallback_first_time": time.time()
                })
            else:
                logger.warning(f"[FALLBACK-DEBUG] Failed to send fallback message to Telnyx for {stream_id}: {result}")
        else:
            # Update fallback count
            call_manager.update_call_state(stream_id, {
                "fallback_count": fallback_count + 1,
                "fallback_last_time": time.time()
            })

        # Skip Gemini API fallback as per requirements
        logger.info(f"[FALLBACK-DEBUG] Skipping Gemini API fallback for {stream_id} as per requirements")

        # Skip transcription as per requirements to avoid costs
        logger.info(f"[FALLBACK-DEBUG] Skipping Telnyx transcription for {stream_id} as per requirements")
    except Exception as e:
        logger.error(f"[FALLBACK-DEBUG] Error in fallback TTS for {stream_id}: {e}", exc_info=True)

async def _verify_transcription_working(stream_id, call_control_id, timeout_seconds=15):
    """
    Verify that transcription is working by checking if we receive any transcription events.
    If no transcription events are received within the timeout period, try alternative approaches.

    Args:
        stream_id: The stream ID for the call
        call_control_id: The Telnyx call control ID
        timeout_seconds: How long to wait for transcription events before considering it failed
    """
    try:
        logger.info(f"[TRANSCRIPT-VERIFY] Starting transcription verification for {stream_id}")

        # Wait for the specified timeout
        await asyncio.sleep(timeout_seconds)

        # Check if the call still exists
        call_state = call_manager.get_call(stream_id)
        if not call_state:
            logger.info(f"[TRANSCRIPT-VERIFY] Call no longer exists for {stream_id}, canceling verification")
            return

        # Check if we've received any transcription events
        transcription_start_time = call_state.get("transcription_start_time", 0)
        last_transcript_time = call_state.get("last_transcript_time", 0)

        # If we have a last_transcript_time that's after the transcription_start_time,
        # then transcription is working
        if last_transcript_time > transcription_start_time:
            logger.info(f"[TRANSCRIPT-VERIFY] Transcription is working for {stream_id}, received transcript at {last_transcript_time}")
            return

        # If we haven't received any transcription events, try alternative approaches
        logger.warning(f"[TRANSCRIPT-VERIFY] No transcription events received for {stream_id} after {timeout_seconds} seconds")

        # Try stopping and restarting transcription
        logger.info(f"[TRANSCRIPT-VERIFY] Stopping and restarting transcription for {stream_id}")

        # First stop transcription
        await _stop_telnyx_transcription(stream_id, call_control_id)

        # Wait a moment
        await asyncio.sleep(2)

        # Then restart with alternative parameters
        await _try_alternative_transcription(stream_id, call_control_id)

    except Exception as e:
        logger.error(f"[TRANSCRIPT-VERIFY] Error verifying transcription for {stream_id}: {e}", exc_info=True)

async def _stop_telnyx_transcription(stream_id, call_control_id):
    """
    Stop Telnyx transcription for a call.

    Args:
        stream_id: The stream ID for the call
        call_control_id: The Telnyx call control ID
    """
    try:
        logger.info(f"[TRANSCRIPT-DEBUG] Stopping Telnyx transcription for {stream_id}")

        # Telnyx API endpoint for transcription stop
        url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/transcription_stop"

        # Headers
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {TELNYX_API_KEY}"
        }

        # Send the request
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers) as response:
                status_code = response.status
                result = await response.json()
                logger.info(f"[TRANSCRIPT-DEBUG] Transcription stop result: {result}")

                if status_code == 200 or (result and result.get('data', {}).get('result') == 'ok'):
                    logger.info(f"[TRANSCRIPT-DEBUG] Successfully stopped transcription for {stream_id}")

                    # Update call state
                    call_manager.update_call_state(stream_id, {"transcription_active": False})
                    return True
                else:
                    logger.warning(f"[TRANSCRIPT-DEBUG] Failed to stop transcription for {stream_id}: {result}")
                    return False

    except Exception as e:
        logger.error(f"[TRANSCRIPT-DEBUG] Error stopping transcription for {stream_id}: {e}", exc_info=True)
        return False

async def _try_alternative_transcription(stream_id, call_control_id):
    """
    Try alternative transcription parameters if the default ones aren't working.

    Args:
        stream_id: The stream ID for the call
        call_control_id: The Telnyx call control ID
    """
    try:
        logger.info(f"[TRANSCRIPT-DEBUG] Trying alternative transcription parameters for {stream_id}")

        # Telnyx API endpoint for transcription
        url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/transcription_start"

        # Headers
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {TELNYX_API_KEY}"
        }

        # Try with engine A (Google) instead of B (Telnyx)
        data = {
            "language": "en",  # Language code
            "transcription_engine": "A",  # Try Google engine
            "transcription_tracks": "inbound",  # Transcribe the caller's speech
            "transcription_webhook_url": os.getenv("TELNYX_WEBHOOK_URL", "https://voice.guestrix.ai/telnyx/"),
            "transcription_webhook_method": "POST"
        }

        logger.info(f"[TRANSCRIPT-DEBUG] Using alternative engine A (Google) for transcription")

        # Send the request
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                status_code = response.status
                result = await response.json()
                logger.info(f"[TRANSCRIPT-DEBUG] Alternative transcription start result: {result}")

                if status_code == 200 or (result and result.get('data', {}).get('result') == 'ok'):
                    logger.info(f"[TRANSCRIPT-DEBUG] Successfully started alternative transcription for {stream_id}")

                    # Update call state
                    call_manager.update_call_state(stream_id, {
                        "transcription_active": True,
                        "transcription_start_time": time.time(),
                        "using_alternative_transcription": True
                    })
                    return True
                else:
                    logger.warning(f"[TRANSCRIPT-DEBUG] Failed to start alternative transcription for {stream_id}: {result}")
                    return False

    except Exception as e:
        logger.error(f"[TRANSCRIPT-DEBUG] Error starting alternative transcription for {stream_id}: {e}", exc_info=True)
        return False

async def _use_gemini_fallback(stream_id, call_control_id):
    """
    Use Gemini API directly as a fallback when Gemini Live API is not available.

    NOTE: This function is currently disabled as per requirements to avoid
    transcribing caller's audio on Telnyx side due to cost considerations.
    The fallback message is sent directly in _use_fallback_tts.

    Args:
        stream_id: The stream ID for the call
        call_control_id: The Telnyx call control ID
    """
    # Log that we're skipping Gemini fallback
    logger.info(f"[FALLBACK-DEBUG] Skipping Gemini API fallback for {stream_id} as per requirements")

    # Return immediately without doing anything
    return

async def _get_context_for_caller(phone_number):
    """
    Get context for a call based on the caller's phone number.

    This function looks up reservations in Firestore where the caller's phone number
    matches either the last 4 digits of the main contact's phone number or the full
    phone number of an additional contact. It then retrieves property details and
    knowledge items for the matched property.

    Args:
        phone_number: The caller's phone number

    Returns:
        A tuple containing (context_string, property_id, guest_name)
    """
    try:
        if not phone_number:
            logger.warning("[CONTEXT-DEBUG] No phone number provided for context retrieval")
            return "", None, None

        # Clean the phone number (remove non-numeric characters)
        clean_number = ''.join(filter(str.isdigit, phone_number))
        last_four_digits = clean_number[-4:] if len(clean_number) >= 4 else clean_number

        logger.info(f"[CONTEXT-DEBUG] Looking up context for phone number ending in {last_four_digits}")

        # Initialize Firebase if not already done
        if not firebase_admin._apps:
            try:
                # Try to load credentials from the credentials directory
                cred_path = "/home/ubuntu/telnyx_websocket/credentials/clean-art-454915-d9-firebase-adminsdk-fbsvc-9e1734f79e.json"
                logger.info(f"[CONTEXT-DEBUG] Trying to load Firebase credentials from: {cred_path}")

                try:
                    # Check if the file exists
                    if os.path.exists(cred_path):
                        logger.info(f"[CONTEXT-DEBUG] Firebase credentials file exists at: {cred_path}")
                        cred = firebase_admin.credentials.Certificate(cred_path)
                        logger.info("[CONTEXT-DEBUG] Successfully loaded Firebase credentials from file")
                    else:
                        logger.warning(f"[CONTEXT-DEBUG] Firebase credentials file not found at: {cred_path}")

                        # Try to load from environment variable path
                        env_cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
                        if env_cred_path and os.path.exists(env_cred_path):
                            logger.info(f"[CONTEXT-DEBUG] Trying to load Firebase credentials from environment variable path: {env_cred_path}")
                            cred = firebase_admin.credentials.Certificate(env_cred_path)
                            logger.info("[CONTEXT-DEBUG] Successfully loaded Firebase credentials from environment variable path")
                        else:
                            # Try to use Firebase project ID from environment variables
                            firebase_project_id = os.environ.get('FIREBASE_PROJECT_ID')
                            if firebase_project_id:
                                logger.info(f"[CONTEXT-DEBUG] Using Firebase project ID from environment variables: {firebase_project_id}")

                                # Initialize with default app
                                logger.info("[CONTEXT-DEBUG] Initializing Firebase with default app")
                                firebase_admin.initialize_app()
                                logger.info("[CONTEXT-DEBUG] Successfully initialized Firebase with default app")

                                # Return early since we've already initialized the app
                                db = firestore.client()
                                logger.info("[CONTEXT-DEBUG] Successfully got Firestore client")
                                return "", None, None
                            else:
                                logger.error("[CONTEXT-DEBUG] No Firebase project ID found in environment variables")
                                return "", None, None
                except Exception as e:
                    logger.error(f"[CONTEXT-DEBUG] Error loading Firebase credentials: {e}", exc_info=True)
                    return "", None, None

                firebase_admin.initialize_app(cred)
                logger.info("[CONTEXT-DEBUG] Firebase initialized successfully")
            except Exception as e:
                logger.error(f"[CONTEXT-DEBUG] Error initializing Firebase: {e}", exc_info=True)
                return "", None, None

        # Get Firestore client
        db = firestore.client()
        logger.info("[CONTEXT-DEBUG] Got Firestore client")

        # Look up reservations where the phone number matches
        reservations_ref = db.collection('reservations')

        # Query for reservations where the main contact's phone number ends with the last 4 digits
        # Improved query to better match phone numbers ending with the last 4 digits
        logger.info(f"[CONTEXT-DEBUG] Querying for reservations with mainContactPhone ending in {last_four_digits}")
        main_contact_query = reservations_ref.where('mainContactPhone', '>=', f'...{last_four_digits}').where('mainContactPhone', '<=', f'...{last_four_digits}\uf8ff').limit(10)
        main_contact_results = list(main_contact_query.stream())
        logger.info(f"[CONTEXT-DEBUG] Found {len(main_contact_results)} potential reservations matching main contact phone")

        # For additional contacts, we need to fetch all reservations with additionalContacts field
        # and then manually filter them
        logger.info(f"[CONTEXT-DEBUG] Querying for reservations with additionalContacts field")

        # First try to query with the exact structure (camelCase field)
        additional_contact_query1 = reservations_ref.where('additionalContacts', 'array_contains', {'phone': phone_number}).limit(10)
        additional_contact_results1 = list(additional_contact_query1.stream())
        logger.info(f"[CONTEXT-DEBUG] Found {len(additional_contact_results1)} reservations with exact additionalContacts match")

        # Try with underscore field name
        additional_contact_query2 = reservations_ref.where('additional_contacts', 'array_contains', {'phone': phone_number}).limit(10)
        additional_contact_results2 = list(additional_contact_query2.stream())
        logger.info(f"[CONTEXT-DEBUG] Found {len(additional_contact_results2)} reservations with exact additional_contacts match")

        # Then try a more general approach - get all reservations
        # and manually filter them
        additional_contact_results3 = []
        try:
            # Get all recent reservations (limit to a reasonable number)
            # Try with startDate field first
            try:
                all_reservations_query = reservations_ref.order_by('startDate', direction='DESCENDING').limit(100)
                all_reservations = list(all_reservations_query.stream())
                logger.info(f"[CONTEXT-DEBUG] Fetched {len(all_reservations)} recent reservations using startDate field")
            except Exception as e:
                logger.warning(f"[CONTEXT-DEBUG] Error fetching reservations with startDate: {e}")
                try:
                    # Fall back to checkIn field if startDate fails
                    all_reservations_query = reservations_ref.order_by('checkIn', direction='DESCENDING').limit(100)
                    all_reservations = list(all_reservations_query.stream())
                    logger.info(f"[CONTEXT-DEBUG] Fetched {len(all_reservations)} recent reservations using checkIn field")
                except Exception as e2:
                    logger.warning(f"[CONTEXT-DEBUG] Error fetching reservations with checkIn: {e2}")
                    # If both fail, just get all reservations without ordering
                    all_reservations_query = reservations_ref.limit(100)
                    all_reservations = list(all_reservations_query.stream())
                    logger.info(f"[CONTEXT-DEBUG] Fetched {len(all_reservations)} recent reservations without ordering")

            # Manually filter reservations with matching additional contacts
            for doc in all_reservations:
                reservation = doc.to_dict()

                # Check both field names
                additional_contacts_camel = reservation.get('additionalContacts', [])
                additional_contacts_underscore = reservation.get('additional_contacts', [])

                # Combine both fields
                all_additional_contacts = additional_contacts_camel + additional_contacts_underscore

                # Skip if no additional contacts
                if not all_additional_contacts:
                    continue

                # Check each additional contact
                for contact in all_additional_contacts:
                    # Handle different possible structures
                    contact_phone = None
                    if isinstance(contact, dict):
                        contact_phone = contact.get('phone')
                    elif isinstance(contact, str):
                        contact_phone = contact

                    # Clean the phone number for comparison
                    if contact_phone:
                        clean_contact_phone = ''.join(filter(str.isdigit, contact_phone))

                        # Check for full match or last 4 digits match
                        if (clean_contact_phone == clean_number or
                            (len(clean_contact_phone) >= 4 and clean_contact_phone.endswith(last_four_digits))):
                            logger.info(f"[CONTEXT-DEBUG] Found matching additional contact in reservation {doc.id}: {contact_phone}")
                            reservation['id'] = doc.id
                            additional_contact_results3.append(doc)
                            break
        except Exception as e:
            logger.error(f"[CONTEXT-DEBUG] Error searching for additional contacts: {e}", exc_info=True)

        logger.info(f"[CONTEXT-DEBUG] Found {len(additional_contact_results3)} reservations with manual additionalContacts search")

        # Combine all additional contact results, ensuring no duplicates
        # Create a set of document IDs to track which documents we've already seen
        seen_doc_ids = set()
        additional_contact_results = []

        # Process results from the first query (camelCase field)
        for doc in additional_contact_results1:
            if doc.id not in seen_doc_ids:
                seen_doc_ids.add(doc.id)
                additional_contact_results.append(doc)
                logger.info(f"[CONTEXT-DEBUG] Added reservation {doc.id} from camelCase query")

        # Process results from the second query (underscore field)
        for doc in additional_contact_results2:
            if doc.id not in seen_doc_ids:
                seen_doc_ids.add(doc.id)
                additional_contact_results.append(doc)
                logger.info(f"[CONTEXT-DEBUG] Added reservation {doc.id} from underscore query")

        # Process results from the manual search
        for doc in additional_contact_results3:
            if doc.id not in seen_doc_ids:
                seen_doc_ids.add(doc.id)
                additional_contact_results.append(doc)
                logger.info(f"[CONTEXT-DEBUG] Added reservation {doc.id} from manual search")

        logger.info(f"[CONTEXT-DEBUG] Combined {len(additional_contact_results)} unique reservations with additional contacts")

        logger.info(f"[CONTEXT-DEBUG] Found {len(main_contact_results)} reservations matching main contact phone")
        logger.info(f"[CONTEXT-DEBUG] Found {len(additional_contact_results)} reservations matching additional contact phone")

        # Combine results
        matching_reservations = []
        property_ids = set()

        for doc in main_contact_results:
            reservation = doc.to_dict()
            reservation['id'] = doc.id  # Add document ID
            if reservation.get('propertyId'):
                # Verify the last 4 digits actually match
                main_phone = reservation.get('mainContactPhone', '')
                clean_main_phone = ''.join(filter(str.isdigit, main_phone))
                if clean_main_phone.endswith(last_four_digits):
                    logger.info(f"[CONTEXT-DEBUG] Matched reservation {doc.id} with main contact phone ending in {last_four_digits}")
                    matching_reservations.append(reservation)
                    property_ids.add(reservation['propertyId'])
                else:
                    logger.warning(f"[CONTEXT-DEBUG] False positive match for reservation {doc.id}: {main_phone} does not end with {last_four_digits}")

        # Process additional contact results
        for doc in additional_contact_results:
            # Skip if this is not a Firestore DocumentSnapshot
            if not hasattr(doc, 'to_dict'):
                continue

            reservation = doc.to_dict()
            reservation['id'] = doc.id  # Add document ID

            if reservation.get('propertyId'):
                # Log the match details
                logger.info(f"[CONTEXT-DEBUG] Matched reservation {doc.id} with additional contact")

                # Check if this reservation is already in the matching_reservations list
                if not any(r.get('id') == doc.id for r in matching_reservations):
                    matching_reservations.append(reservation)
                    property_ids.add(reservation['propertyId'])
                    logger.info(f"[CONTEXT-DEBUG] Added reservation {doc.id} to matching reservations")
                else:
                    logger.info(f"[CONTEXT-DEBUG] Reservation {doc.id} already in matching reservations, skipping")

        if not matching_reservations:
            logger.warning(f"[CONTEXT-DEBUG] No matching reservations found for phone number ending in {last_four_digits}")
            return "", None, None

        logger.info(f"[CONTEXT-DEBUG] Found {len(matching_reservations)} matching reservations for phone number ending in {last_four_digits}")
        logger.info(f"[CONTEXT-DEBUG] Property IDs: {', '.join(property_ids)}")

        # Get property details for the first matching reservation
        first_reservation = matching_reservations[0]
        property_id = first_reservation.get('propertyId')

        if not property_id:
            logger.warning("[CONTEXT-DEBUG] No property ID found in the matching reservation")
            return "", None, None

        # Get property details
        logger.info(f"[CONTEXT-DEBUG] Getting property details for property ID: {property_id}")
        property_ref = db.collection('properties').document(property_id)
        property_doc = property_ref.get()

        if not property_doc.exists:
            logger.warning(f"[CONTEXT-DEBUG] Property {property_id} not found in Firestore")
            return "", property_id, None

        property_data = property_doc.to_dict()
        property_data['id'] = property_doc.id  # Add document ID
        logger.info(f"[CONTEXT-DEBUG] Retrieved property: {property_data.get('name', 'Unknown')}")

        # Get knowledge items for the property
        logger.info(f"[CONTEXT-DEBUG] Getting knowledge items for property ID: {property_id}")
        knowledge_items = []

        # Try to get knowledge items from various collections
        try:
            # First try the knowledge_items collection (new format)
            logger.info(f"[CONTEXT-DEBUG] Checking knowledge_items collection for property {property_id}")
            knowledge_items_ref = db.collection('knowledge_items')
            knowledge_items_query = knowledge_items_ref.where('propertyId', '==', property_id).limit(50)
            knowledge_items_docs = list(knowledge_items_query.stream())

            if knowledge_items_docs:
                logger.info(f"[CONTEXT-DEBUG] Found {len(knowledge_items_docs)} knowledge items in knowledge_items collection")
                for doc in knowledge_items_docs:
                    item = doc.to_dict()
                    item['id'] = doc.id  # Add document ID
                    knowledge_items.append(item)
            else:
                # If no items found, try the knowledge collection (old format)
                logger.info(f"[CONTEXT-DEBUG] No items in knowledge_items collection, trying knowledge collection")
                knowledge_ref = db.collection('knowledge')
                knowledge_query = knowledge_ref.where('propertyId', '==', property_id).limit(50)
                knowledge_docs = list(knowledge_query.stream())

                if knowledge_docs:
                    logger.info(f"[CONTEXT-DEBUG] Found {len(knowledge_docs)} knowledge items in knowledge collection")
                    for doc in knowledge_docs:
                        item = doc.to_dict()
                        item['id'] = doc.id  # Add document ID
                        knowledge_items.append(item)
                else:
                    # If still no items found, try the subcollection approach
                    logger.info(f"[CONTEXT-DEBUG] No items in knowledge collection, trying subcollection")
                    subcollection_ref = db.collection('properties').document(property_id).collection('knowledge')
                    subcollection_docs = list(subcollection_ref.stream())

                    if subcollection_docs:
                        logger.info(f"[CONTEXT-DEBUG] Found {len(subcollection_docs)} knowledge items in subcollection")
                        for doc in subcollection_docs:
                            item = doc.to_dict()
                            item['id'] = doc.id  # Add document ID
                            knowledge_items.append(item)
                    else:
                        # Finally, check if there's a knowledge field in the property document
                        logger.info(f"[CONTEXT-DEBUG] No items in subcollection, checking property document")
                        property_doc = db.collection('properties').document(property_id).get()
                        property_data = property_doc.to_dict()

                        if 'knowledge' in property_data and isinstance(property_data['knowledge'], list):
                            logger.info(f"[CONTEXT-DEBUG] Found {len(property_data['knowledge'])} knowledge items in property document")
                            for item in property_data['knowledge']:
                                if isinstance(item, dict):
                                    knowledge_items.append(item)
                        else:
                            logger.warning(f"[CONTEXT-DEBUG] No knowledge items found for property {property_id}")
        except Exception as knowledge_error:
            logger.error(f"[CONTEXT-DEBUG] Error retrieving knowledge items: {knowledge_error}", exc_info=True)

        # Get guest name
        guest_name = first_reservation.get('mainContactName', '')
        logger.info(f"[CONTEXT-DEBUG] Guest name from main contact: {guest_name}")

        # If guest name is not available in the main contact, check additional contacts
        if not guest_name:
            additional_contacts = first_reservation.get('additionalContacts', []) + first_reservation.get('additional_contacts', [])
            for contact in additional_contacts:
                if isinstance(contact, dict) and contact.get('phone') == phone_number and contact.get('name'):
                    guest_name = contact.get('name')
                    logger.info(f"[CONTEXT-DEBUG] Found guest name in additional contacts: {guest_name}")
                    break

        # Build context string with more comprehensive prompt
        property_name = property_data.get('name', 'the property')
        host_name = property_data.get('hostName', '')

        # Get property address
        address = property_data.get('address', {})
        address_str = ""
        if address:
            # Handle both object and string address formats
            if isinstance(address, dict):
                address_str = ', '.join(filter(None, [
                    address.get('street'),
                    address.get('city'),
                    address.get('state'),
                    address.get('zip')
                ]))
            else:
                # If address is a string, use it directly
                address_str = address

        # Create a more comprehensive prompt similar to the guest dashboard
        if address_str:
            context = f"You are Staycee, a helpful AI concierge assistant for {property_name} located at {address_str}."
        else:
            context = f"You are Staycee, a helpful AI concierge assistant for {property_name}."

        # Add guest name if available
        if guest_name:
            context += f" You are speaking with {guest_name}, a guest at this property."
        else:
            context += f" You are speaking with a guest at this property."

        # Add host name if available
        if host_name:
            context += f" The host for this property is {host_name}."

        # Add goal and tone guidance
        context += f"\nYour goal is to assist the guest with any questions or needs they have regarding their stay."
        context += f"\nBe conversational, friendly, and helpful."

        # Add today's date
        from datetime import date
        today = date.today().strftime("%B %d, %Y")
        context += f"\n\nToday's date is {today}."

        # Add tool usage instructions
        context += f"\n\nYou have access to the following tools:"
        context += f"\n1. google_search: Use this tool to search for information about local attractions, restaurants, services, or any other information that would be helpful to the guest."

        context += f"\n\nWhen using the google_search tool:"
        context += f"\n- First tell the guest \"Let me search for that information for you\""
        context += f"\n- After receiving the search results, provide a concise and helpful summary"
        context += f"\n- If the search results don't provide relevant information, let the guest know"

        # Add property details section header
        context += "\n\nPROPERTY DETAILS:"

        # Add WiFi details if available
        wifi_network = property_data.get('wifiNetwork')
        wifi_password = property_data.get('wifiPassword')
        if wifi_network and wifi_password:
            context += f"\n\nWiFi Network: {wifi_network}\nWiFi Password: {wifi_password}"

        # Add check-in/check-out details from reservation
        # Try both field naming conventions
        check_in = first_reservation.get('checkIn') or first_reservation.get('startDate')
        check_out = first_reservation.get('checkOut') or first_reservation.get('endDate')
        if check_in and check_out:
            context += f"\n\nCheck-in date: {check_in}\nCheck-out date: {check_out}"

        # Add knowledge items
        if knowledge_items:
            context += "\n\nHere is some important information about the property:\n"

            # Group knowledge items by type
            items_by_type = {}
            for item in knowledge_items:
                item_type = item.get('type', 'General')
                if item_type not in items_by_type:
                    items_by_type[item_type] = []
                items_by_type[item_type].append(item)

            # Add each type of knowledge item
            for item_type, items in items_by_type.items():
                if item_type:
                    context += f"\n{item_type.upper()}:\n"

                for item in items:
                    content = item.get('content', '')

                    if content:
                        context += f"{content}\n\n"

                # Add extra line break between types
                context += "\n"

        logger.info(f"[CONTEXT-DEBUG] Generated context ({len(context)} chars) for property {property_id}")
        return context, property_id, guest_name

    except Exception as e:
        logger.error(f"[CONTEXT-DEBUG] Error retrieving context for phone number {phone_number}: {e}", exc_info=True)
        return "", None, None

async def _start_telnyx_transcription(stream_id, call_control_id):
    """
    Start Telnyx transcription for a call.

    Args:
        stream_id: The stream ID for the call
        call_control_id: The Telnyx call control ID
    """
    try:
        logger.info(f"[TRANSCRIPT-DEBUG] Starting Telnyx transcription for {stream_id}")

        # Check if transcription is already active
        call_state = call_manager.get_call(stream_id)
        if call_state and call_state.get("transcription_active"):
            logger.info(f"[TRANSCRIPT-DEBUG] Transcription already active for {stream_id}, skipping")
            return {"status": "already_active"}

        # Telnyx API endpoint for transcription
        url = f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/transcription_start"
        logger.info(f"[TRANSCRIPT-DEBUG] Using Telnyx API URL: {url}")

        # Headers
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {TELNYX_API_KEY}"
        }
        logger.info(f"[TRANSCRIPT-DEBUG] Using API key: {mask_api_key(TELNYX_API_KEY)}")

        # Request data with correct parameters according to Telnyx documentation
        # Use "en" for language and engine B (Telnyx) for better accuracy and lower latency
        data = {
            "language": "en",  # Language code
            "transcription_engine": "B",  # Use Telnyx's in-house engine for better accuracy
            "transcription_tracks": "inbound",  # Transcribe the caller's speech
            # Add webhook URL to ensure transcription events are sent to our webhook endpoint
            "transcription_webhook_url": os.getenv("TELNYX_WEBHOOK_URL", "https://voice.guestrix.ai/telnyx/"),
            # Add method to ensure webhook is sent via POST
            "transcription_webhook_method": "POST"
        }
        logger.info(f"[TRANSCRIPT-DEBUG] Using language: en with Telnyx transcription engine")
        logger.info(f"[TRANSCRIPT-DEBUG] Using webhook URL: {data.get('transcription_webhook_url')}")

        # Send the request
        logger.info(f"[TRANSCRIPT-DEBUG] Sending transcription start request for {stream_id}")
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                status_code = response.status
                logger.info(f"[TRANSCRIPT-DEBUG] Received response with status code: {status_code}")

                result = await response.json()
                logger.info(f"[TRANSCRIPT-DEBUG] Transcription start result: {result}")

                if status_code == 200 or (result and result.get('data', {}).get('result') == 'ok'):
                    logger.info(f"[TRANSCRIPT-DEBUG] Successfully started transcription for {stream_id}")

                    # Update call state to indicate transcription is active
                    call_manager.update_call_state(stream_id, {
                        "transcription_active": True,
                        "transcription_start_time": time.time()
                    })
                    logger.info(f"[TRANSCRIPT-DEBUG] Updated call state to indicate transcription is active")

                    # Log success
                    logger.info(f"[TRANSCRIPT-DEBUG] Transcription started successfully for {stream_id}")
                else:
                    logger.warning(f"[TRANSCRIPT-DEBUG] Failed to start transcription for {stream_id}: {result}")

                    # Try to extract error details for better debugging
                    error_message = result.get('errors', [{}])[0].get('detail', 'Unknown error') if result.get('errors') else 'Unknown error'
                    logger.warning(f"[TRANSCRIPT-DEBUG] Error details: {error_message}")

                return result

    except Exception as e:
        logger.error(f"[TRANSCRIPT-DEBUG] Error starting transcription for {stream_id}: {e}", exc_info=True)
        return None

async def _handle_transcription_event(event_data, stream_id, call_control_id):
    """
    Handle a transcription event from Telnyx.

    Args:
        event_data: The event data from Telnyx
        stream_id: The stream ID for the call
        call_control_id: The Telnyx call control ID
    """
    try:
        # Extract transcription data according to Telnyx documentation
        payload = event_data.get('payload', {})

        # Log the raw transcription data for debugging
        logger.info(f"[TRANSCRIPT-DEBUG] Raw transcription data: {json.dumps(payload)}")

        # The transcription data should be in payload.transcription_data
        transcription_data = payload.get('transcription_data', {})

        # If transcription_data is not found, try alternative formats
        if not transcription_data:
            if 'transcription' in payload:
                # Try format where data is in payload.transcription
                transcription_data = payload.get('transcription', {})
                logger.info(f"[TRANSCRIPT-DEBUG] Using alternative format 1 for transcription data")
            elif 'transcript' in payload:
                # Try format where data is directly in payload
                transcription_data = payload
                logger.info(f"[TRANSCRIPT-DEBUG] Using alternative format 2 for transcription data")
            else:
                logger.warning(f"[TRANSCRIPT-DEBUG] Could not find transcription data in payload")
                transcription_data = {}
        else:
            logger.info(f"[TRANSCRIPT-DEBUG] Using standard format for transcription data")

        # Extract transcript, is_final, and confidence from the transcription data
        transcript = transcription_data.get('transcript', '')
        is_final = transcription_data.get('is_final', False)
        confidence = transcription_data.get('confidence', 0)

        if not transcript:
            logger.warning(f"[TRANSCRIPT-DEBUG] Empty transcript received for {stream_id}")
            return

        logger.info(f"[TRANSCRIPT-DEBUG] Received transcription for {stream_id}: '{transcript}' (final: {is_final}, confidence: {confidence})")

        # Only process final transcriptions to avoid duplicate processing
        if not is_final:
            logger.debug(f"[TRANSCRIPT-DEBUG] Skipping non-final transcription for {stream_id}")
            return

        # Store the transcript in the call state for use by the fallback mechanism
        call_manager.update_call_state(stream_id, {
            "last_transcript": transcript,
            "last_transcript_time": time.time(),
            "transcript_confidence": confidence
        })
        logger.info(f"[TRANSCRIPT-DEBUG] Stored transcript in call state: {transcript}")

        # Get call information and context
        call_info = call_manager.get_call(stream_id)
        if not call_info:
            logger.warning(f"[TRANSCRIPT-DEBUG] No call information found for stream ID: {stream_id}")
            return

        # Check if we should use Gemini Live client if it's available and running
        gemini_client = call_info.get("gemini_client")
        if gemini_client and gemini_client.is_running:
            logger.info(f"[TRANSCRIPT-DEBUG] Gemini Live client is running, sending text directly to it")
            try:
                # Send the transcript directly to Gemini Live
                await gemini_client.send_text(transcript)
                logger.info(f"[TRANSCRIPT-DEBUG] Successfully sent transcript to Gemini Live: {transcript}")
                # No need to continue with fallback mechanism
                return
            except Exception as e:
                logger.error(f"[TRANSCRIPT-DEBUG] Error sending transcript to Gemini Live: {e}", exc_info=True)
                logger.info(f"[TRANSCRIPT-DEBUG] Falling back to Gemini API")
                # Continue with fallback mechanism
        else:
            logger.info(f"[TRANSCRIPT-DEBUG] Gemini Live client not available or not running, using Gemini API fallback")

        # Get context from call state if available
        context = call_info.get("context")
        property_id = call_info.get("property_id")
        guest_name = call_info.get("guest_name")
        caller_phone_number = call_info.get("caller_phone_number", "")

        # If no context in call state, try to retrieve it
        if not context:
            logger.info(f"[TRANSCRIPT-DEBUG] No context in call state, retrieving for caller: {caller_phone_number}")
            context, property_id, guest_name = await _get_context_for_caller(caller_phone_number)

            # Update call state with retrieved context
            call_manager.update_call_state(stream_id, {
                "context": context,
                "property_id": property_id,
                "guest_name": guest_name
            })

        # Log context information
        if property_id:
            logger.info(f"[TRANSCRIPT-DEBUG] Using property ID: {property_id}")
        else:
            logger.warning(f"[TRANSCRIPT-DEBUG] No property ID available for transcription")

        if guest_name:
            logger.info(f"[TRANSCRIPT-DEBUG] Using guest name: {guest_name}")
        else:
            logger.warning(f"[TRANSCRIPT-DEBUG] No guest name available for transcription")

        logger.info(f"[TRANSCRIPT-DEBUG] Context length: {len(context) if context else 0} characters")

        # Configure Gemini
        logger.info(f"[TRANSCRIPT-DEBUG] Configuring Gemini API for {stream_id}")
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')

        # Create personalized prompt with context and transcript
        guest_reference = "the guest" if not guest_name else guest_name
        prompt = f"""You are Staycee, a helpful AI concierge assistant.

        {context}

        {guest_reference} just said: "{transcript}"

        Please respond to {guest_reference}'s question or request. Keep your response concise and conversational,
        as it will be read aloud over the phone. Limit your response to 3-4 sentences maximum."""

        # Generate response
        logger.info(f"[TRANSCRIPT-DEBUG] Generating response from Gemini API for {stream_id}")
        response = model.generate_content(prompt)
        response_text = response.text

        logger.info(f"[TRANSCRIPT-DEBUG] Generated response for transcription: {response_text}")

        # Send response to Telnyx
        logger.info(f"[TRANSCRIPT-DEBUG] Sending response to Telnyx for {stream_id}")
        result = await send_text_to_telnyx(call_control_id, response_text)
        if result and result.get('data', {}).get('result') == 'ok':
            logger.info(f"[TRANSCRIPT-DEBUG] Successfully sent transcription response to Telnyx for {stream_id}")

            # Update call state with response information
            call_manager.update_call_state(stream_id, {
                "last_response": response_text,
                "last_response_time": time.time()
            })
        else:
            logger.warning(f"[TRANSCRIPT-DEBUG] Failed to send transcription response to Telnyx for {stream_id}: {result}")

    except Exception as e:
        logger.error(f"[TRANSCRIPT-DEBUG] Error handling transcription event for {stream_id}: {e}", exc_info=True)

async def get_gemini_connection_status(stream_id):
    """
    Get detailed connection status for a Gemini Live client.

    This function retrieves and logs detailed connection status information
    for debugging purposes.

    Args:
        stream_id: The stream ID for the call

    Returns:
        A dictionary with connection status information or None if not found
    """
    try:
        # Get call information
        call_info = call_manager.get_call(stream_id)
        if not call_info:
            logger.warning(f"[DEBUG] No call information found for stream ID: {stream_id}")
            return None

        # Get Gemini client
        gemini_client = call_info.get("gemini_client")
        if not gemini_client:
            logger.warning(f"[DEBUG] No Gemini client found for stream ID: {stream_id}")
            return None

        # Get connection status
        status = gemini_client.get_connection_status()

        # Log detailed status
        logger.info(f"[DEBUG] Gemini connection status for {stream_id}:")
        logger.info(f"[DEBUG] - Connected: {status['is_connected']}")
        logger.info(f"[DEBUG] - Running: {status['is_running']}")
        logger.info(f"[DEBUG] - State: {status['connection_state']}")
        logger.info(f"[DEBUG] - Error: {status['connection_error']}")
        logger.info(f"[DEBUG] - Connection attempts: {status['connection_attempts']}")

        if status['last_connection_time']:
            logger.info(f"[DEBUG] - Last connection: {status['time_since_connection']:.2f} seconds ago")

        if status['last_message_received_time']:
            logger.info(f"[DEBUG] - Last message received: {status['time_since_message_received']:.2f} seconds ago")

        if status['last_message_sent_time']:
            logger.info(f"[DEBUG] - Last message sent: {status['time_since_message_sent']:.2f} seconds ago")

        logger.info(f"[DEBUG] - Audio packets received: {status['audio_stats']['packets_received']}")
        logger.info(f"[DEBUG] - Audio bytes received: {status['audio_stats']['bytes_received']}")
        logger.info(f"[DEBUG] - Audio packets sent: {status['audio_stats']['packets_sent']}")
        logger.info(f"[DEBUG] - Audio bytes sent: {status['audio_stats']['bytes_sent']}")
        logger.info(f"[DEBUG] - Text messages received: {status['text_stats']['messages_received']}")
        logger.info(f"[DEBUG] - Text messages sent: {status['text_stats']['messages_sent']}")
        logger.info(f"[DEBUG] - Errors encountered: {status['errors_encountered']}")
        logger.info(f"[DEBUG] - WebSocket state: {status['websocket_state']}")
        logger.info(f"[DEBUG] - Input queue size: {status['input_queue_size']}")
        logger.info(f"[DEBUG] - Output queue size: {status['output_queue_size']}")

        return status
    except Exception as e:
        logger.error(f"[DEBUG] Error getting Gemini connection status for {stream_id}: {e}", exc_info=True)
        return None

async def forward_gemini_audio(stream_id, websocket):
    """
    Forward audio from Gemini Live API to Telnyx.

    This function continuously checks for audio from Gemini Live API
    and forwards it to Telnyx via the WebSocket connection.

    If the Gemini Live API is not available, it falls back to using the Telnyx speak API.
    """
    logger.info(f"Starting Gemini->Telnyx audio forwarder for {stream_id}")
    audio_packets_sent = 0
    total_bytes_sent = 0
    start_time = time.time()  # Track start time for rate calculations

    # Rate limiting for reconnection attempts
    last_reconnect_time = 0
    min_reconnect_interval = 2.0  # Minimum seconds between reconnection attempts

    # We'll use the call state to track reconnection attempts

    try:
        while call_manager.call_exists(stream_id):
            call_state = call_manager.get_call(stream_id)
            if not call_state:
                logger.warning(f"Call state not found for {stream_id}")
                break

            gemini_client = call_state.get("gemini_client")
            if not gemini_client:
                logger.warning(f"Gemini client not found for {stream_id}")
                break

            # Check if Gemini client is running
            if not gemini_client.is_running:
                # Apply rate limiting for reconnection attempts
                current_time = time.time()
                time_since_last_reconnect = current_time - last_reconnect_time

                if time_since_last_reconnect < min_reconnect_interval:
                    # Too soon to attempt another reconnection
                    logger.debug(f"Rate limiting reconnection for {stream_id}, waiting {min_reconnect_interval - time_since_last_reconnect:.1f}s")
                    await asyncio.sleep(0.1)  # Small delay to prevent CPU overuse
                    continue

                # Update last reconnect time
                last_reconnect_time = current_time

                # Try to reconnect
                logger.warning(f"[AUDIO-DEBUG] Gemini client not running for {stream_id}, attempting to reconnect")

                # Get connection status for debugging
                await get_gemini_connection_status(stream_id)

                # Get call control ID for fallback
                call_state = call_manager.get_call(stream_id)
                call_control_id = call_state.get("call_control_id")

                # Track reconnection attempts
                reconnect_attempts = call_state.get("reconnect_attempts", 0) + 1
                call_manager.update_call_state(stream_id, {"reconnect_attempts": reconnect_attempts})

                # Limit reconnection attempts to avoid infinite loops
                if reconnect_attempts <= 2:  # Try up to 2 times
                    try:
                        # Attempt to reconnect with exponential backoff
                        backoff_time = min_reconnect_interval * (2 ** (reconnect_attempts - 1))
                        logger.info(f"[AUDIO-DEBUG] Reconnection attempt {reconnect_attempts}/2 for {stream_id} with {backoff_time:.1f}s backoff")

                        # Wait for backoff time
                        await asyncio.sleep(backoff_time)

                        # Attempt to reconnect
                        logger.info(f"[AUDIO-DEBUG] Attempting to reconnect Gemini client for {stream_id}")
                        welcome_message = await gemini_client.connect()

                        # Check if reconnection was successful
                        if gemini_client.is_running:
                            logger.info(f"[AUDIO-DEBUG] Successfully reconnected Gemini client for {stream_id} (attempt {reconnect_attempts}/2)")
                            logger.info(f"[AUDIO-DEBUG] Welcome message: {welcome_message}")

                            # Get updated connection status
                            await get_gemini_connection_status(stream_id)

                            # Send a welcome message to let the caller know we're back
                            if call_control_id and audio_packets_sent == 0:
                                reconnect_text = "I'm back online now. How can I help you today?"
                                await send_text_to_telnyx(call_control_id, reconnect_text)
                                logger.info(f"[AUDIO-DEBUG] Sent reconnection message to Telnyx for {stream_id}")
                                audio_packets_sent += 1  # Mark as sent to avoid repeated messages
                        else:
                            # If reconnection fails, use Telnyx speak API as fallback
                            logger.warning(f"[AUDIO-DEBUG] Failed to reconnect Gemini client for {stream_id} (attempt {reconnect_attempts}/2)")
                            logger.warning(f"[AUDIO-DEBUG] Connection state: {gemini_client.connection_state}")
                            logger.warning(f"[AUDIO-DEBUG] Connection error: {gemini_client.connection_error}")

                            # Use fallback immediately after first failed reconnection attempt
                            logger.info(f"[AUDIO-DEBUG] Using fallback TTS for {stream_id}")
                            await _use_fallback_tts(stream_id, call_control_id)
                    except Exception as e:
                        logger.error(f"[AUDIO-DEBUG] Error reconnecting Gemini client for {stream_id}: {e}", exc_info=True)

                        # Use fallback immediately after error
                        logger.info(f"[AUDIO-DEBUG] Using fallback TTS after error for {stream_id}")
                        await _use_fallback_tts(stream_id, call_control_id)
                else:
                    # Too many reconnection attempts, switch to fallback permanently
                    logger.warning(f"[AUDIO-DEBUG] Too many reconnection attempts ({reconnect_attempts}) for {stream_id}, switching to fallback permanently")

                    # Use fallback
                    logger.info(f"[AUDIO-DEBUG] Using fallback TTS after too many reconnection attempts for {stream_id}")
                    await _use_fallback_tts(stream_id, call_control_id)

                    # Mark call as using fallback permanently
                    call_manager.update_call_state(stream_id, {"using_fallback_permanently": True})

                    # Add a delay to avoid hammering the server
                    await asyncio.sleep(min_reconnect_interval * 2)

            # Get audio from Gemini
            audio_chunk = await gemini_client.get_audio()
            if audio_chunk:
                # Log before resampling
                audio_size = len(audio_chunk)
                logger.info(f"Received {audio_size} bytes of audio from Gemini for {stream_id}")

                # Log audio details for debugging
                if audio_size > 0:
                    # Log first few bytes as hex for debugging
                    hex_preview = ' '.join([f'{b:02x}' for b in audio_chunk[:16]])
                    logger.debug(f"Audio preview from Gemini for {stream_id}: {hex_preview}...")

                    # Resample audio to Telnyx's sample rate
                    resampled_audio = resample_audio(audio_chunk, GEMINI_SAMPLE_RATE, TELNYX_SAMPLE_RATE)
                    resampled_size = len(resampled_audio)
                    logger.info(f"Resampled to {resampled_size} bytes for Telnyx (16kHz), ratio: {resampled_size/audio_size:.2f}")

                    # Log resampled audio preview
                    if resampled_size > 0:
                        resampled_hex = ' '.join([f'{b:02x}' for b in resampled_audio[:16]])
                        logger.debug(f"Resampled audio preview for {stream_id}: {resampled_hex}...")

                        # Encode as base64
                        encoded_audio = base64.b64encode(resampled_audio).decode('utf-8')

                        # Send to Telnyx
                        media_event = {
                            "event": "media",
                            "media": {
                                "payload": encoded_audio
                            }
                        }

                        try:
                            if not websocket.closed:
                                await websocket.send(json.dumps(media_event))
                                audio_packets_sent += 1
                                total_bytes_sent += resampled_size
                                logger.info(f"Sent packet #{audio_packets_sent} ({resampled_size} bytes) to Telnyx for {stream_id}")
                                call_manager.increment_media_packets(stream_id, "sent")

                                # Log periodic status
                                if audio_packets_sent % 5 == 0:
                                    duration = time.time() - start_time if 'start_time' in locals() else 0
                                    rate = total_bytes_sent / duration if duration > 0 else 0
                                    logger.info(f"Status for {stream_id}: Sent {audio_packets_sent} packets, {total_bytes_sent} bytes total, {rate:.2f} bytes/sec")
                            else:
                                logger.warning(f"WebSocket closed, cannot send audio for {stream_id}")
                                break
                        except Exception as e:
                            logger.error(f"Error sending audio to Telnyx: {e}", exc_info=True)
                            break
                    else:
                        logger.warning(f"Resampling produced empty audio data for {stream_id}")
                else:
                    logger.warning(f"Received empty audio chunk from Gemini for {stream_id}")

            # Small delay to prevent CPU overuse
            await asyncio.sleep(0.01)
    except Exception as e:
        logger.error(f"Error in audio forwarder: {e}", exc_info=True)
    finally:
        logger.info(f"Stopped audio forwarder for {stream_id}. Total sent: {audio_packets_sent} packets, {total_bytes_sent} bytes")

async def start_servers():
    """
    Start both HTTP and WebSocket servers.
    """
    # Start the call manager cleanup task
    call_manager.start_cleanup_task()

    # Create the HTTP app
    app = web.Application()
    app.router.add_post('/telnyx/', handle_http_request)

    # Start the HTTP server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8082)
    await site.start()
    logger.info("HTTP server started on http://0.0.0.0:8082/telnyx/")

    # Start the WebSocket server
    # Use the adapter to handle different websockets library versions
    # This ensures compatibility between different versions of the library
    handler_with_adapter = await websocket_adapter(handle_websocket)
    await websockets.serve(handler_with_adapter, '0.0.0.0', 8083)
    logger.info("WebSocket server started on ws://0.0.0.0:8083 (with version adapter)")

    # Keep the servers running
    await asyncio.Future()

if __name__ == "__main__":
    # Parse command line arguments
    args = parse_arguments()

    # Set log level based on arguments
    if args.debug:
        logger.setLevel(logging.DEBUG)

    # Run the server
    asyncio.run(start_servers())
