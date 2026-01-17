#!/usr/bin/env python3
"""
Gemini Live Client

This module provides a client for interacting with Google's Gemini Live API
for bidirectional audio streaming. It handles connecting to the API, sending
audio data, and receiving responses.
"""

import os
import json
import time
import base64
import asyncio
import logging
import queue
from typing import Optional, Dict, Any, List
import aiohttp
# Import Google Generative AI SDK if needed
# from google import generativeai as genai

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
GEMINI_SAMPLE_RATE = 24000  # Gemini provides audio at 24kHz
AUDIO_CHANNELS = 1  # Mono audio
DEFAULT_VOICE = "Aoede"  # Default Gemini voice

class GeminiLiveClient:
    """
    Client for interacting with Gemini Live API.

    This class provides methods for connecting to Gemini Live API,
    sending audio data, and receiving responses.
    """

    def __init__(self, api_key: str, model: str, stream_id: str, voice: str = DEFAULT_VOICE, context: str = None):
        """
        Initialize the Gemini Live client.

        Args:
            api_key: The Gemini API key
            model: The Gemini model to use
            stream_id: The stream ID for this connection
            voice: The voice to use for responses
            context: Optional context information about the property and guest
        """
        self.api_key = api_key
        self.model = model
        self.stream_id = stream_id
        self.voice = voice
        self.context = context

        # WebSocket connection
        self.websocket = None
        self.session = None

        # State tracking
        self.is_connected = False
        self.is_running = False
        self.connection_attempts = 0
        self.last_connection_time = None
        self.last_message_received_time = None
        self.last_message_sent_time = None
        self.connection_state = "initialized"
        self.connection_error = None

        # Audio queues
        self.input_audio_queue = asyncio.Queue()  # Audio to send to Gemini
        self.output_audio_queue = asyncio.Queue()  # Audio received from Gemini
        self.text_queue = asyncio.Queue()  # Text received from Gemini
        self.transcription_queue = asyncio.Queue()  # Transcriptions received from Gemini

        # Debugging stats
        self.audio_packets_received = 0
        self.audio_bytes_received = 0
        self.audio_packets_sent = 0
        self.audio_bytes_sent = 0
        self.text_messages_received = 0
        self.text_messages_sent = 0
        self.errors_encountered = 0

        # Tasks
        self.tasks = []

        logger.info(f"Initialized Gemini Live client for stream ID: {stream_id}")

    async def connect(self) -> str:
        """
        Connect to Gemini Live API using WebSocket.

        Returns:
            A welcome message from Gemini
        """
        # Update connection state and attempts
        self.connection_attempts += 1
        self.connection_state = "connecting"
        self.connection_error = None
        connection_attempt_start = time.time()

        logger.info(f"[GEMINI-DEBUG] Connection attempt #{self.connection_attempts} for stream ID: {self.stream_id}")

        try:
            # If already connected, disconnect first
            if self.websocket is not None or self.session is not None:
                logger.info(f"[GEMINI-DEBUG] Cleaning up existing connections for stream ID: {self.stream_id}")
                await self.disconnect()

            # Create a new session with longer timeout
            connection_timeout = aiohttp.ClientTimeout(total=30, connect=20, sock_connect=20, sock_read=20)
            self.session = aiohttp.ClientSession(timeout=connection_timeout)
            logger.info(f"[GEMINI-DEBUG] Created new aiohttp session with timeout={connection_timeout}")

            # Connect to Gemini Live API
            ws_url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={self.api_key}&alt=json"
            masked_url = ws_url.replace(self.api_key, 'REDACTED')
            logger.info(f"[GEMINI-DEBUG] Connecting to Gemini Live API: {masked_url}")

            # Update connection state
            self.connection_state = "establishing_websocket"

            # Connect with timeout and keep-alive options
            connection_start = time.time()
            try:
                self.websocket = await self.session.ws_connect(
                    ws_url,
                    timeout=connection_timeout,
                    heartbeat=10.0,  # Send heartbeat every 10 seconds
                    compress=15,     # Enable compression
                    autoclose=False, # Don't auto-close the connection
                    max_msg_size=0,  # No limit on message size
                    receive_timeout=30.0  # Increase receive timeout
                )
                connection_time = time.time() - connection_start
                logger.info(f"[GEMINI-DEBUG] WebSocket connection established in {connection_time:.2f} seconds for stream ID: {self.stream_id}")

                # Log WebSocket details
                if self.websocket:
                    logger.info(f"[GEMINI-DEBUG] WebSocket state: closed={self.websocket.closed}, "
                               f"protocol={self.websocket.protocol}, "
                               f"compress={self.websocket.compress}")
            except Exception as ws_error:
                connection_time = time.time() - connection_start
                logger.error(f"[GEMINI-DEBUG] WebSocket connection failed after {connection_time:.2f} seconds: {ws_error}")
                self.connection_state = "websocket_connection_failed"
                self.connection_error = str(ws_error)
                raise

            # Update connection state
            self.connection_state = "websocket_connected"
            self.last_connection_time = time.time()
            self.is_connected = True
            self.is_running = True

            # Send initial configuration
            logger.info(f"[GEMINI-DEBUG] Sending initial configuration for stream ID: {self.stream_id}")
            self.connection_state = "sending_initial_config"
            await self._send_initial_config()

            # Update connection state
            self.connection_state = "initial_config_sent"
            logger.info(f"[GEMINI-DEBUG] Initial configuration sent successfully for stream ID: {self.stream_id}")

            # Start processing tasks
            self.connection_state = "starting_processing_tasks"
            self.tasks = [
                asyncio.create_task(self._process_websocket_messages()),
                asyncio.create_task(self._process_input_audio())
            ]
            logger.info(f"[GEMINI-DEBUG] Started processing tasks for stream ID: {self.stream_id}")

            # Update final connection state
            self.connection_state = "connected"
            total_connection_time = time.time() - connection_attempt_start
            logger.info(f"[GEMINI-DEBUG] Connection established in {total_connection_time:.2f} seconds for stream ID: {self.stream_id}")

            # Return a welcome message
            welcome_message = "Hello! I'm Gemini, your AI assistant. How can I help you today?"
            return welcome_message

        except asyncio.TimeoutError:
            connection_time = time.time() - connection_attempt_start
            logger.error(f"[GEMINI-DEBUG] Timeout connecting to Gemini Live API after {connection_time:.2f} seconds for stream ID: {self.stream_id}")
            self.is_running = False
            self.is_connected = False
            self.connection_state = "timeout"
            self.connection_error = "Connection timeout"
            self.errors_encountered += 1
            return "Timeout connecting to Gemini Live API."

        except Exception as e:
            connection_time = time.time() - connection_attempt_start
            logger.error(f"[GEMINI-DEBUG] Error connecting to Gemini Live API after {connection_time:.2f} seconds for stream ID {self.stream_id}: {e}", exc_info=True)
            self.is_running = False
            self.is_connected = False
            self.connection_state = "error"
            self.connection_error = str(e)
            self.errors_encountered += 1
            return f"Error connecting to Gemini Live API: {e}"

    async def _send_initial_config(self):
        """Send initial configuration to Gemini Live API."""
        try:
            # Create initial configuration based on LiveKit documentation
            initial_config = {
                "type": "session.config",
                "config": {
                    "model": f"models/{self.model}",
                    "generationConfig": {
                        "temperature": 0.7,
                        "topP": 0.95,
                        "topK": 40,
                        "candidateCount": 1,
                        "maxOutputTokens": 1024,
                        "responseModalities": ["AUDIO"]  # Only request AUDIO modality
                    },
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": "Hello, I'm calling for assistance."
                                }
                            ]
                        }
                    ],
                    "tools": [
                        {
                            "google_search": {}
                        }
                    ],
                    "systemInstruction": {
                        "parts": [
                            {
                                "text": self._create_system_prompt()
                            }
                        ]
                    },
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": self.voice
                            }
                        },
                        "languageCode": "en-US"
                    },
                    # Enable transcription for both input and output audio
                    "inputAudioTranscription": {},
                    "outputAudioTranscription": {}
                }
            }

            # Send configuration
            await self.websocket.send_json(initial_config)
            logger.info("Sent initial configuration to Gemini Live API")

        except Exception as e:
            logger.error(f"Error sending initial configuration: {e}", exc_info=True)
            raise

    def _create_system_prompt(self) -> str:
        """Create the system prompt for Gemini Live API."""
        # Create a system prompt that matches the format used in the guest dashboard
        system_prompt = """
        You are Staycee, a helpful AI concierge assistant.
        You are speaking with a guest over the phone.
        Your goal is to assist the guest with any questions or needs they have regarding their stay.
        Be conversational, friendly, and helpful.

        Keep your responses concise and conversational, as they will be read aloud over the phone.
        Limit your responses to 3-4 sentences maximum.

        CRITICAL INFRASTRUCTURE PROTECTION:
        If a guest asks about the location of critical infrastructure elements such as water shutoff valves, electrical panels, fuse boxes, circuit breakers, gas shutoff valves, HVAC system controls, air handler units, ventilation system access, sump pumps, water heaters, or other mechanical systems, you MUST first ask the guest to explain the specific reason they need this information. Only provide access details if there is a genuine emergency situation such as fire, smoke, electrical hazards, water leaks, flooding, pipe bursts, gas leaks, HVAC system failures causing dangerous temperatures, or any situation where immediate access would prevent property damage or ensure guest safety. For non-emergency requests, politely explain that this information is restricted for safety and security reasons, and suggest they contact the host directly.

        You have access to the following tools:
        1. google_search: Use this tool to search for information about local attractions, restaurants, services, or any other information that would be helpful to the guest.
        """

        # Add context if available
        if self.context:
            system_prompt += f"\n\nHere is important information about the property and guest:\n{self.context}\n"
            logger.info(f"[GEMINI-DEBUG] Added {len(self.context)} characters of context to system prompt for stream ID: {self.stream_id}")
        else:
            logger.warning(f"[GEMINI-DEBUG] No context available for stream ID: {self.stream_id}")

        return system_prompt

    async def _process_websocket_messages(self):
        """Process messages from the Gemini Live API WebSocket."""
        message_count = 0
        last_heartbeat = time.time()
        start_time = time.time()

        try:
            logger.info(f"Started WebSocket message processor for stream ID: {self.stream_id}")

            # Log WebSocket state
            if self.websocket:
                logger.info(f"WebSocket state for stream ID {self.stream_id}: closed={self.websocket.closed}, "
                           f"protocol={self.websocket.protocol}, "
                           f"compress={self.websocket.compress}")
            else:
                logger.error(f"WebSocket is None for stream ID {self.stream_id}")
                return

            try:
                async for msg in self.websocket:
                    # Update heartbeat timestamp
                    current_time = time.time()
                    if current_time - last_heartbeat > 10:
                        logger.debug(f"WebSocket heartbeat for stream ID: {self.stream_id}, received {message_count} messages so far")
                        last_heartbeat = current_time

                        # Send a ping to keep the connection alive
                        if not self.websocket.closed:
                            try:
                                await self.websocket.ping()
                                logger.debug(f"Sent ping to WebSocket for stream ID: {self.stream_id}")
                            except Exception as ping_error:
                                logger.warning(f"Error sending ping to WebSocket for stream ID {self.stream_id}: {ping_error}")

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        message_count += 1
                        logger.debug(f"Received WebSocket text message #{message_count} for stream ID {self.stream_id}, length: {len(msg.data)}")
                        await self._handle_websocket_message(msg.data)
                    elif msg.type == aiohttp.WSMsgType.BINARY:
                        message_count += 1
                        logger.debug(f"Received WebSocket binary message #{message_count} for stream ID {self.stream_id}, length: {len(msg.data)}")
                        # Handle binary data if needed
                        pass
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket error for stream ID {self.stream_id}: {msg.data}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.warning(f"WebSocket closed for stream ID {self.stream_id}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSING:
                        logger.warning(f"WebSocket closing for stream ID {self.stream_id}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSE:
                        logger.warning(f"WebSocket close frame received for stream ID {self.stream_id}")
                        break
                    elif msg.type == aiohttp.WSMsgType.PONG:
                        logger.debug(f"Received pong from WebSocket for stream ID: {self.stream_id}")
                    else:
                        logger.warning(f"Unknown WebSocket message type for stream ID {self.stream_id}: {msg.type}")
            except aiohttp.ClientConnectionError as conn_error:
                logger.error(f"Connection error in WebSocket message processor for stream ID {self.stream_id}: {conn_error}")
            except asyncio.CancelledError:
                logger.info(f"WebSocket message processor cancelled for stream ID: {self.stream_id}")
                raise
            except Exception as e:
                logger.error(f"Error in WebSocket message loop for stream ID {self.stream_id}: {e}", exc_info=True)

            duration = time.time() - start_time
            logger.info(f"WebSocket connection closed for stream ID: {self.stream_id}, processed {message_count} messages in {duration:.2f} seconds")

        except asyncio.CancelledError:
            logger.info(f"WebSocket message processor cancelled for stream ID: {self.stream_id}")
            raise
        except aiohttp.ClientConnectionError as e:
            logger.error(f"Connection error in WebSocket message processor for stream ID {self.stream_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error processing WebSocket messages for stream ID {self.stream_id}: {e}", exc_info=True)
        finally:
            # Ensure we clean up
            self.is_running = False
            self.is_connected = False
            logger.info(f"WebSocket message processor stopped for stream ID: {self.stream_id}")

    async def _handle_websocket_message(self, data: str):
        """Handle a message from the Gemini Live API WebSocket."""
        try:
            # Update last message received time
            self.last_message_received_time = time.time()

            # Parse the message
            message = json.loads(data)

            # Log the message type
            message_type = message.get("type")
            if message_type:
                logger.debug(f"[GEMINI-DEBUG] Received message type: {message_type} for stream ID: {self.stream_id}")
            else:
                logger.warning(f"[GEMINI-DEBUG] Received message without type for stream ID: {self.stream_id}")
                logger.debug(f"[GEMINI-DEBUG] Message content: {data[:200]}...")

            # Handle different message types
            if message_type == "response.audio.delta" and "delta" in message:
                # Handle audio response
                try:
                    audio_data = base64.b64decode(message["delta"])
                    audio_size = len(audio_data)
                    self.audio_packets_received += 1
                    self.audio_bytes_received += audio_size

                    if audio_size > 0:
                        # Log first few bytes as hex for debugging
                        hex_preview = ' '.join([f'{b:02x}' for b in audio_data[:16]])
                        logger.debug(f"[GEMINI-DEBUG] Audio packet #{self.audio_packets_received} preview for stream ID {self.stream_id}: {hex_preview}...")

                        # Put audio in the queue
                        await self.output_audio_queue.put(audio_data)
                        logger.info(f"[GEMINI-DEBUG] Queued {audio_size} bytes of audio from Gemini for stream ID: {self.stream_id}, queue size: {self.output_audio_queue.qsize()}")

                        # Log periodic stats
                        if self.audio_packets_received % 5 == 0:
                            logger.info(f"[GEMINI-DEBUG] Audio stats for stream ID {self.stream_id}: Received {self.audio_packets_received} packets, {self.audio_bytes_received} bytes total")
                    else:
                        logger.warning(f"[GEMINI-DEBUG] Received empty audio data from Gemini for stream ID: {self.stream_id}")
                except Exception as audio_error:
                    logger.error(f"[GEMINI-DEBUG] Error processing audio data for stream ID {self.stream_id}: {audio_error}", exc_info=True)
                    self.errors_encountered += 1

            elif message_type == "response.content.delta" and "delta" in message:
                # Handle text response
                if "text" in message["delta"]:
                    text = message["delta"]["text"]
                    await self.text_queue.put(text)
                    self.text_messages_received += 1
                    logger.info(f"[GEMINI-DEBUG] Received text from Gemini for stream ID {self.stream_id}: {text}")
                else:
                    logger.debug(f"[GEMINI-DEBUG] Received content delta without text for stream ID {self.stream_id}: {message['delta']}")

            elif message_type == "session.updated":
                # Session was updated successfully
                logger.info(f"[GEMINI-DEBUG] Gemini Live session updated successfully for stream ID: {self.stream_id}")
                self.connection_state = "session_updated"

            elif message_type == "session.started":
                # Session was started
                logger.info(f"[GEMINI-DEBUG] Gemini Live session started for stream ID: {self.stream_id}")
                self.connection_state = "session_started"

            elif message_type == "session.stopped":
                # Session was stopped
                logger.info(f"[GEMINI-DEBUG] Gemini Live session stopped for stream ID: {self.stream_id}")
                self.connection_state = "session_stopped"

                # Check if this was expected or unexpected
                if self.is_running:
                    logger.warning(f"[GEMINI-DEBUG] Unexpected session stop while client was still running for stream ID: {self.stream_id}")
                    self.is_running = False
                    self.is_connected = False
                    self.errors_encountered += 1

            elif message_type == "error":
                # Handle error
                error_msg = message.get('error', {}).get('message', 'Unknown error')
                error_code = message.get('error', {}).get('code', 'unknown')
                logger.error(f"[GEMINI-DEBUG] Gemini Live API error for stream ID {self.stream_id}: [{error_code}] {error_msg}")
                # Log the full message for debugging
                logger.error(f"[GEMINI-DEBUG] Full error message: {message}")

                # Update error state
                self.connection_state = "error_received"
                self.connection_error = f"[{error_code}] {error_msg}"
                self.errors_encountered += 1

            # Handle transcription messages
            elif "serverContent" in message:
                server_content = message["serverContent"]

                # Handle input transcription (user speech)
                if "inputTranscription" in server_content:
                    input_text = server_content["inputTranscription"].get("text", "")
                    if input_text.strip():
                        logger.info(f"[GEMINI-DEBUG] User speech transcription for stream ID {self.stream_id}: {input_text}")
                        await self.transcription_queue.put({"role": "user", "text": input_text.strip()})

                # Handle output transcription (AI speech)
                if "outputTranscription" in server_content:
                    output_text = server_content["outputTranscription"].get("text", "")
                    if output_text.strip():
                        logger.info(f"[GEMINI-DEBUG] AI speech transcription for stream ID {self.stream_id}: {output_text}")
                        await self.transcription_queue.put({"role": "assistant", "text": output_text.strip()})

            else:
                # Log unknown message types
                logger.warning(f"[GEMINI-DEBUG] Received unknown message type from Gemini for stream ID {self.stream_id}: {message_type}")
                logger.debug(f"[GEMINI-DEBUG] Full message: {data[:200]}...")

        except json.JSONDecodeError:
            logger.error(f"[GEMINI-DEBUG] Error decoding JSON for stream ID {self.stream_id}: {data[:200]}...")
            self.errors_encountered += 1
        except Exception as e:
            logger.error(f"[GEMINI-DEBUG] Error handling WebSocket message for stream ID {self.stream_id}: {e}", exc_info=True)
            self.errors_encountered += 1

    async def _process_input_audio(self):
        """Process audio from the input queue and send it to Gemini Live API."""
        audio_packets_sent = 0
        total_bytes_sent = 0
        start_time = time.time()
        last_status_time = start_time

        try:
            logger.info(f"Started processing input audio for stream ID: {self.stream_id}")

            while self.is_running:
                # Get audio from the queue
                try:
                    audio_data = await asyncio.wait_for(self.input_audio_queue.get(), timeout=0.5)
                    logger.debug(f"Got {len(audio_data)} bytes of audio from queue for stream ID: {self.stream_id}, queue size: {self.input_audio_queue.qsize()}")
                except asyncio.TimeoutError:
                    # No audio in the queue, continue
                    continue

                # Send audio to Gemini Live API
                if self.is_connected and self.websocket:
                    if self.websocket.closed:
                        logger.warning(f"WebSocket closed, cannot send audio for stream ID: {self.stream_id}")
                        continue

                    try:
                        # Create audio append message with format information
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(audio_data).decode(),
                            "audioFormat": {
                                "sampleRateHertz": 24000,  # Gemini expects 24kHz audio
                                "encoding": "LINEAR16",    # PCM format
                                "channelCount": 1          # Mono audio
                            }
                        }

                        # Send the message
                        await self.websocket.send_json(audio_append)
                        audio_packets_sent += 1
                        total_bytes_sent += len(audio_data)
                        logger.debug(f"Sent packet #{audio_packets_sent} ({len(audio_data)} bytes) to Gemini for stream ID: {self.stream_id}")

                        # Log periodic status
                        current_time = time.time()
                        if current_time - last_status_time > 5.0:  # Log status every 5 seconds
                            duration = current_time - start_time
                            rate = total_bytes_sent / duration if duration > 0 else 0
                            logger.info(f"Audio status for {self.stream_id}: Sent {audio_packets_sent} packets, {total_bytes_sent} bytes total, {rate:.2f} bytes/sec")
                            last_status_time = current_time
                    except aiohttp.ClientConnectionError as e:
                        logger.error(f"Connection error sending audio to Gemini for stream ID {self.stream_id}: {e}")
                        break
                    except Exception as e:
                        logger.error(f"Error sending audio to Gemini for stream ID {self.stream_id}: {e}", exc_info=True)
                        break
                else:
                    logger.warning(f"Cannot send audio: client not connected for stream ID: {self.stream_id}")

                # Mark the task as done
                self.input_audio_queue.task_done()

            duration = time.time() - start_time
            rate = total_bytes_sent / duration if duration > 0 else 0
            logger.info(f"Stopped processing input audio for stream ID: {self.stream_id}. Sent {audio_packets_sent} packets, {total_bytes_sent} bytes total in {duration:.2f} seconds ({rate:.2f} bytes/sec)")

        except asyncio.CancelledError:
            logger.info(f"Audio processing task cancelled for stream ID: {self.stream_id}")
            raise
        except Exception as e:
            logger.error(f"Error in audio processing task for stream ID {self.stream_id}: {e}", exc_info=True)
        finally:
            logger.info("Stopped processing input audio")

    # SDK-based response processor (not used)
    # async def _process_responses(self) -> None:
    #     """Process responses from the Gemini Live API using the SDK."""
    #     pass

    async def send_audio(self, audio_data: bytes):
        """
        Send audio to Gemini Live API.

        Args:
            audio_data: The audio data to send
        """
        if not self.is_running:
            logger.warning(f"Cannot send audio: client is not running for stream ID: {self.stream_id}")

            # Try to reconnect if the client is not running
            try:
                logger.info(f"Attempting to reconnect Gemini client for stream ID: {self.stream_id}")
                await self.connect()
                # If reconnection is successful, continue with sending audio
                if self.is_running:
                    logger.info(f"Reconnected Gemini client for stream ID: {self.stream_id}")
                else:
                    logger.warning(f"Failed to reconnect Gemini client for stream ID: {self.stream_id}")
                    return
            except Exception as e:
                logger.error(f"Error reconnecting Gemini client for stream ID {self.stream_id}: {e}", exc_info=True)
                return

        # Add audio to the queue
        await self.input_audio_queue.put(audio_data)
        logger.info(f"Queued {len(audio_data)} bytes of audio to send to Gemini for stream ID: {self.stream_id}")

    async def send_text(self, text: str):
        """
        Send a text prompt to Gemini Live API.

        Args:
            text: The text prompt to send
        """
        if not self.is_running:
            logger.warning(f"Cannot send text: client is not running for stream ID: {self.stream_id}")

            # Try to reconnect if the client is not running
            try:
                logger.info(f"Attempting to reconnect Gemini client for stream ID: {self.stream_id}")
                await self.connect()
                # If reconnection is successful, continue with sending text
                if self.is_running:
                    logger.info(f"Reconnected Gemini client for stream ID: {self.stream_id}")
                else:
                    logger.warning(f"Failed to reconnect Gemini client for stream ID: {self.stream_id}")
                    return
            except Exception as e:
                logger.error(f"Error reconnecting Gemini client for stream ID {self.stream_id}: {e}", exc_info=True)
                return

        try:
            # Create text content message
            text_content = {
                "type": "input_content.update",
                "content": {
                    "parts": [
                        {
                            "text": text
                        }
                    ]
                }
            }

            # Send the message
            await self.websocket.send_json(text_content)
            logger.info(f"Sent text prompt to Gemini for stream ID {self.stream_id}: {text}")

        except Exception as e:
            logger.error(f"Error sending text to Gemini for stream ID {self.stream_id}: {e}", exc_info=True)

            # Try to reconnect if there was an error sending the message
            try:
                logger.info(f"Attempting to reconnect Gemini client after send error for stream ID: {self.stream_id}")
                await self.connect()
                # If reconnection is successful, try sending the text again
                if self.is_running:
                    logger.info(f"Reconnected Gemini client for stream ID: {self.stream_id}")
                    text_content = {
                        "type": "input_content.update",
                        "content": {
                            "parts": [
                                {
                                    "text": text
                                }
                            ]
                        }
                    }
                    await self.websocket.send_json(text_content)
                    logger.info(f"Resent text prompt to Gemini for stream ID {self.stream_id}: {text}")
                else:
                    logger.warning(f"Failed to reconnect Gemini client for stream ID: {self.stream_id}")
            except Exception as reconnect_error:
                logger.error(f"Error reconnecting Gemini client for stream ID {self.stream_id}: {reconnect_error}", exc_info=True)

    async def get_audio(self) -> Optional[bytes]:
        """
        Get audio from Gemini Live API.

        Returns:
            Audio data or None if no audio is available
        """
        try:
            # Try to get audio from the queue (non-blocking)
            audio_data = self.output_audio_queue.get_nowait()
            if audio_data:
                logger.info(f"Retrieved {len(audio_data)} bytes of audio from Gemini queue for stream ID: {self.stream_id}")
            return audio_data
        except asyncio.QueueEmpty:
            # No audio in the queue
            return None

    async def get_text(self) -> Optional[str]:
        """
        Get text from Gemini Live API.

        Returns:
            Text or None if no text is available
        """
        try:
            # Try to get text from the queue (non-blocking)
            return self.text_queue.get_nowait()
        except asyncio.QueueEmpty:
            # No text in the queue
            return None

    async def get_transcription(self) -> Optional[dict]:
        """
        Get transcription from Gemini Live API.

        Returns:
            Transcription dict with 'role' and 'text' keys, or None if no transcription is available
        """
        try:
            # Try to get transcription from the queue (non-blocking)
            return self.transcription_queue.get_nowait()
        except asyncio.QueueEmpty:
            # No transcription in the queue
            return None

    async def disconnect(self):
        """Disconnect from Gemini Live API."""
        logger.info(f"[GEMINI-DEBUG] Disconnecting from Gemini Live API for stream ID: {self.stream_id}")

        # Set state
        self.is_running = False
        self.is_connected = False
        self.connection_state = "disconnecting"

        # Cancel tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
                logger.debug(f"[GEMINI-DEBUG] Cancelled task for stream ID: {self.stream_id}")

        # Close WebSocket
        if self.websocket:
            try:
                await self.websocket.close()
                logger.debug(f"[GEMINI-DEBUG] Closed WebSocket for stream ID: {self.stream_id}")
            except Exception as e:
                logger.error(f"[GEMINI-DEBUG] Error closing WebSocket for stream ID {self.stream_id}: {e}")
            self.websocket = None

        # Close session
        if self.session:
            try:
                await self.session.close()
                logger.debug(f"[GEMINI-DEBUG] Closed aiohttp session for stream ID: {self.stream_id}")
            except Exception as e:
                logger.error(f"[GEMINI-DEBUG] Error closing aiohttp session for stream ID {self.stream_id}: {e}")
            self.session = None

        self.connection_state = "disconnected"
        logger.info(f"[GEMINI-DEBUG] Disconnected from Gemini Live API for stream ID: {self.stream_id}")

    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get detailed connection status for debugging.

        Returns:
            A dictionary with connection status information
        """
        current_time = time.time()

        # Calculate time since last activity
        time_since_connection = None
        if self.last_connection_time:
            time_since_connection = current_time - self.last_connection_time

        time_since_message_received = None
        if self.last_message_received_time:
            time_since_message_received = current_time - self.last_message_received_time

        time_since_message_sent = None
        if self.last_message_sent_time:
            time_since_message_sent = current_time - self.last_message_sent_time

        # Build status dictionary
        status = {
            "stream_id": self.stream_id,
            "is_connected": self.is_connected,
            "is_running": self.is_running,
            "connection_state": self.connection_state,
            "connection_error": self.connection_error,
            "connection_attempts": self.connection_attempts,
            "last_connection_time": self.last_connection_time,
            "time_since_connection": time_since_connection,
            "last_message_received_time": self.last_message_received_time,
            "time_since_message_received": time_since_message_received,
            "last_message_sent_time": self.last_message_sent_time,
            "time_since_message_sent": time_since_message_sent,
            "audio_stats": {
                "packets_received": self.audio_packets_received,
                "bytes_received": self.audio_bytes_received,
                "packets_sent": self.audio_packets_sent,
                "bytes_sent": self.audio_bytes_sent,
            },
            "text_stats": {
                "messages_received": self.text_messages_received,
                "messages_sent": self.text_messages_sent,
            },
            "errors_encountered": self.errors_encountered,
            "websocket_state": "closed" if not self.websocket or self.websocket.closed else "open",
            "input_queue_size": self.input_audio_queue.qsize() if self.input_audio_queue else 0,
            "output_queue_size": self.output_audio_queue.qsize() if self.output_audio_queue else 0,
        }

        return status
