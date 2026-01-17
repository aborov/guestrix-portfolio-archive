#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gemini Live WebSocket Client

This module provides a client for the Gemini Live API using WebSockets.
Based on the documentation at https://ai.google.dev/gemini-api/docs/live
"""

import os
import json
import time
import base64
import logging
import asyncio
import aiohttp
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List, Callable

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GeminiLiveWebSocketClient:
    """
    Client for the Gemini Live API using WebSockets.

    This client provides methods for sending audio and text to the Gemini Live API
    and receiving audio and text responses.
    """

    def __init__(self, api_key: str, stream_id: str = "default"):
        """
        Initialize the Gemini Live WebSocket client.

        Args:
            api_key: The Gemini API key
            stream_id: A unique identifier for this stream
        """
        self.api_key = api_key
        self.stream_id = stream_id
        self.is_running = False
        self.is_connected = False

        # Initialize WebSocket
        self.session = None
        self.websocket = None

        # Initialize queues for audio and text
        self.input_audio_queue = asyncio.Queue()
        self.output_audio_queue = asyncio.Queue()
        self.text_queue = asyncio.Queue()

        # Initialize tasks
        self.tasks = []

        logger.info(f"Initialized Gemini Live WebSocket client for stream ID: {self.stream_id}")

    async def connect(self) -> str:
        """
        Connect to the Gemini Live API.

        Returns:
            A welcome message from the API
        """
        try:
            # Clean up existing connections
            if self.is_connected:
                await self.disconnect()

            # Create a session
            self.session = aiohttp.ClientSession()

            # Create the WebSocket URL with the API key
            ws_url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={self.api_key}&alt=json"

            # Connect to the WebSocket
            logger.info(f"Connecting to Gemini Live API: {ws_url.replace(self.api_key, 'REDACTED')}")

            # Set connection options
            options = {
                'timeout': aiohttp.ClientTimeout(total=30),
                'heartbeat': 30.0,  # Send heartbeat every 30 seconds
                'compress': 15,     # Enable compression
                'autoclose': False,  # Don't auto-close the connection
                'max_msg_size': 0   # No limit on message size
            }

            self.websocket = await self.session.ws_connect(ws_url, **options)
            logger.info(f"Connected to Gemini Live API WebSocket for stream ID: {self.stream_id}")
            logger.info(f"WebSocket state: closed={self.websocket.closed}, protocol={self.websocket.protocol}, compress={self.websocket.compress}")

            # Send initial configuration
            initial_config = {
                "type": "session.config",
                "config": {
                    "model": "gemini-2.0-flash-live-001",
                    "generationConfig": {
                        "temperature": 0.7,
                        "topP": 0.95,
                        "topK": 40,
                        "candidateCount": 1,
                        "maxOutputTokens": 1024
                    },
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": "Hello, Gemini! This is a test message."
                                }
                            ]
                        }
                    ]
                }
            }

            # Send the configuration
            await self.websocket.send_json(initial_config)
            logger.info(f"Sent initial configuration to Gemini Live API for stream ID: {self.stream_id}")

            # Set state
            self.is_connected = True
            self.is_running = True

            # Start tasks
            self._start_tasks()

            # Return a welcome message
            return "Connected to Gemini Live API. You can start speaking now."

        except Exception as e:
            logger.error(f"Error connecting to Gemini Live API for stream ID {self.stream_id}: {e}", exc_info=True)
            self.is_running = False
            self.is_connected = False
            return f"Error connecting to Gemini Live API: {e}"

    def _start_tasks(self):
        """Start the tasks for processing messages."""
        # Cancel existing tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Clear the tasks list
        self.tasks = []

        # Create new tasks
        self.tasks.append(asyncio.create_task(self._process_websocket_messages()))
        self.tasks.append(asyncio.create_task(self._process_input_audio()))

        logger.info(f"Started tasks for stream ID: {self.stream_id}")

    async def _process_websocket_messages(self):
        """Process messages from the Gemini Live API WebSocket."""
        try:
            logger.info(f"Started WebSocket message processor for stream ID: {self.stream_id}")

            if not self.websocket:
                logger.error(f"WebSocket is None for stream ID: {self.stream_id}")
                return

            message_count = 0
            start_time = time.time()
            last_heartbeat = start_time

            logger.info(f"WebSocket state for stream ID {self.stream_id}: closed={self.websocket.closed}, protocol={self.websocket.protocol}, compress={self.websocket.compress}")

            async for msg in self.websocket:
                # Update heartbeat timestamp
                current_time = time.time()
                if current_time - last_heartbeat > 30:
                    logger.debug(f"WebSocket heartbeat for stream ID: {self.stream_id}, received {message_count} messages so far")
                    last_heartbeat = current_time

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
                else:
                    logger.warning(f"Unknown WebSocket message type for stream ID {self.stream_id}: {msg.type}")

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
            # Parse the message
            message = json.loads(data)

            # Log the message type
            message_type = message.get("type")
            if message_type:
                logger.debug(f"Received message type: {message_type} for stream ID: {self.stream_id}")
            else:
                logger.warning(f"Received message without type for stream ID: {self.stream_id}")
                logger.debug(f"Message content: {data[:200]}...")

            # Handle different message types
            if message_type == "response.audio.delta" and "delta" in message:
                # Handle audio response
                try:
                    audio_data = base64.b64decode(message["delta"])
                    audio_size = len(audio_data)

                    if audio_size > 0:
                        # Log first few bytes as hex for debugging
                        hex_preview = ' '.join([f'{b:02x}' for b in audio_data[:16]])
                        logger.debug(f"Audio preview for stream ID {self.stream_id}: {hex_preview}...")

                        # Put audio in the queue
                        await self.output_audio_queue.put(audio_data)
                        logger.info(f"Queued {audio_size} bytes of audio from Gemini for stream ID: {self.stream_id}, queue size: {self.output_audio_queue.qsize()}")
                    else:
                        logger.warning(f"Received empty audio data from Gemini for stream ID: {self.stream_id}")
                except Exception as audio_error:
                    logger.error(f"Error processing audio data for stream ID {self.stream_id}: {audio_error}", exc_info=True)

            elif message_type == "response.content.delta" and "delta" in message:
                # Handle text response
                if "text" in message["delta"]:
                    text = message["delta"]["text"]
                    await self.text_queue.put(text)
                    logger.info(f"Received text from Gemini for stream ID {self.stream_id}: {text}")
                else:
                    logger.debug(f"Received content delta without text for stream ID {self.stream_id}: {message['delta']}")

            elif message_type == "session.updated":
                # Session was updated successfully
                logger.info(f"Gemini Live session updated successfully for stream ID: {self.stream_id}")

            elif message_type == "session.started":
                # Session was started
                logger.info(f"Gemini Live session started for stream ID: {self.stream_id}")

            elif message_type == "session.stopped":
                # Session was stopped
                logger.info(f"Gemini Live session stopped for stream ID: {self.stream_id}")

            elif message_type == "error":
                # Handle error
                error_msg = message.get('error', {}).get('message', 'Unknown error')
                error_code = message.get('error', {}).get('code', 'unknown')
                logger.error(f"Gemini Live API error for stream ID {self.stream_id}: [{error_code}] {error_msg}")
                # Log the full message for debugging
                logger.error(f"Full error message: {message}")

            else:
                # Log unknown message types
                logger.warning(f"Received unknown message type from Gemini for stream ID {self.stream_id}: {message_type}")
                logger.debug(f"Full message: {data[:200]}...")

        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON for stream ID {self.stream_id}: {data[:200]}...")
        except Exception as e:
            logger.error(f"Error handling WebSocket message for stream ID {self.stream_id}: {e}", exc_info=True)

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
                        # Create audio append message
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(audio_data).decode()
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

    async def disconnect(self):
        """Disconnect from Gemini Live API."""
        logger.info(f"Disconnecting from Gemini Live API for stream ID: {self.stream_id}")

        # Set state
        self.is_running = False
        self.is_connected = False

        # Cancel tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Close WebSocket
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

        # Close session
        if self.session:
            await self.session.close()
            self.session = None

        logger.info(f"Disconnected from Gemini Live API for stream ID: {self.stream_id}")

async def test_client(api_key):
    """Test the Gemini Live WebSocket client."""
    # Create a client
    client = GeminiLiveWebSocketClient(api_key, stream_id="test-stream")

    try:
        # Connect to the Gemini Live API
        welcome_message = await client.connect()
        logger.info(f"Welcome message: {welcome_message}")

        # Send a text prompt
        await client.send_text("Hello, Gemini! This is a test message.")

        # Wait for a response
        logger.info("Waiting for response...")

        # Wait for up to 10 seconds for a response
        start_time = time.time()
        while time.time() - start_time < 10:
            # Check for text response
            text = await client.get_text()
            if text:
                logger.info(f"Received text: {text}")
                break

            # Check for audio response
            audio = await client.get_audio()
            if audio:
                logger.info(f"Received {len(audio)} bytes of audio")
                break

            # Sleep to avoid busy waiting
            await asyncio.sleep(0.1)

        # Disconnect
        await client.disconnect()
        logger.info("Disconnected from Gemini Live API")

        return True

    except Exception as e:
        logger.error(f"Error testing Gemini Live WebSocket client: {e}", exc_info=True)
        return False

async def main():
    """Main function."""
    # Load environment variables
    load_dotenv()

    # Get API key
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    if not api_key:
        logger.error("API key not found in environment variables")
        return

    # Test the client
    success = await test_client(api_key)

    if success:
        logger.info("Gemini Live WebSocket client test completed successfully")
    else:
        logger.error("Gemini Live WebSocket client test failed")

if __name__ == "__main__":
    asyncio.run(main())
