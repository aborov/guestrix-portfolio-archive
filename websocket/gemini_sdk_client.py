#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gemini SDK Client

This module provides a client for the Gemini Live API using the official Google AI Python SDK.
"""

import os
import time
import base64
import logging
import asyncio
import threading
from typing import Optional, Dict, Any, List, Callable
from queue import Queue

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google.generativeai.types import GenerationConfig

# Configure logging
logger = logging.getLogger("telnyx_bidirectional")

class GeminiSdkClient:
    """
    Client for the Gemini Live API using the official Google AI Python SDK.

    This client provides methods for sending audio and text to the Gemini Live API
    and receiving audio and text responses.
    """

    def __init__(self, api_key: str, stream_id: str = "default"):
        """
        Initialize the Gemini SDK client.

        Args:
            api_key: The Gemini API key
            stream_id: A unique identifier for this stream
        """
        self.api_key = api_key
        self.stream_id = stream_id
        self.is_running = False
        self.is_connected = False

        # Initialize queues for audio and text
        self.input_audio_queue = asyncio.Queue()
        self.output_audio_queue = asyncio.Queue()
        self.text_queue = asyncio.Queue()

        # Initialize the model
        self.model = None
        self.response_generator = None
        self.response_thread = None

        # Initialize the audio buffer
        self.audio_buffer = b""

        # Initialize the response handler
        self.response_handler = None

        logger.info(f"Initialized Gemini SDK client for stream ID: {self.stream_id}")

    async def connect(self) -> str:
        """
        Connect to the Gemini Live API.

        Returns:
            A welcome message from the API
        """
        try:
            # Configure the API key
            genai.configure(api_key=self.api_key)
            logger.info(f"Configured Gemini API key for stream ID: {self.stream_id}")

            # Initialize the model
            # List available models to find one that supports streaming
            models = genai.list_models()
            available_models = [model.name for model in models if "gemini" in model.name.lower()]
            logger.info(f"Available Gemini models: {available_models}")

            # Find the live model in the available models
            live_model = None
            for model_name in available_models:
                if "live" in model_name.lower():
                    live_model = model_name
                    logger.info(f"Found live model: {live_model}")
                    break

            # If no live model found, use the known model name
            if not live_model:
                live_model = "models/gemini-2.0-flash-live-001"
                logger.warning(f"No live model found in available models, using: {live_model}")

            # Use the live model for streaming
            self.model = genai.GenerativeModel(
                model_name=live_model,
                generation_config=GenerationConfig(
                    temperature=0.7,
                    top_p=0.95,
                    top_k=40,
                    candidate_count=1,
                    max_output_tokens=1024
                ),
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
            )
            logger.info(f"Initialized Gemini model for stream ID: {self.stream_id}")

            # Set state
            self.is_connected = True
            self.is_running = True

            # Start the response handler thread
            self.start_response_handler()

            # Return a welcome message
            welcome_message = "Connected to Gemini Live API. You can start speaking now."
            return welcome_message

        except Exception as e:
            logger.error(f"Error connecting to Gemini Live API for stream ID {self.stream_id}: {e}", exc_info=True)
            self.is_running = False
            self.is_connected = False
            return f"Error connecting to Gemini Live API: {e}"

    async def disconnect(self):
        """Disconnect from the Gemini Live API."""
        logger.info(f"Disconnecting from Gemini Live API for stream ID: {self.stream_id}")

        # Stop the response handler thread
        if self.response_handler and self.response_handler.is_alive():
            self.is_running = False
            self.response_handler.join(timeout=2.0)
            if self.response_handler.is_alive():
                logger.warning(f"Response handler thread did not terminate for stream ID: {self.stream_id}")

        # Clear the queues
        while not self.input_audio_queue.empty():
            try:
                await self.input_audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        while not self.output_audio_queue.empty():
            try:
                await self.output_audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        while not self.text_queue.empty():
            try:
                await self.text_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Reset state
        self.is_running = False
        self.is_connected = False
        self.model = None
        self.response_generator = None

        logger.info(f"Disconnected from Gemini Live API for stream ID: {self.stream_id}")

    def start_response_handler(self):
        """Start the response handler thread."""
        if self.response_handler and self.response_handler.is_alive():
            logger.warning(f"Response handler thread already running for stream ID: {self.stream_id}")
            return

        self.response_handler = threading.Thread(
            target=self._handle_responses,
            name=f"gemini-response-handler-{self.stream_id}",
            daemon=True
        )
        self.response_handler.start()
        logger.info(f"Started response handler thread for stream ID: {self.stream_id}")

    def _handle_responses(self):
        """Handle responses from the Gemini Live API."""
        logger.info(f"Response handler thread started for stream ID: {self.stream_id}")

        try:
            while self.is_running:
                # Check if there's audio in the buffer
                if len(self.audio_buffer) > 0:
                    # Process the audio buffer
                    audio_data = self.audio_buffer
                    self.audio_buffer = b""

                    # Create a prompt with the audio
                    prompt = [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "audio_data": {
                                        "data": base64.b64encode(audio_data).decode()
                                    }
                                }
                            ]
                        }
                    ]

                    try:
                        # Generate a response
                        response = self.model.generate_content(
                            prompt,
                            stream=True
                        )

                        # Process the response
                        for chunk in response:
                            if not self.is_running:
                                break

                            # Handle text response
                            if hasattr(chunk, "text") and chunk.text:
                                text = chunk.text
                                logger.info(f"Received text from Gemini for stream ID {self.stream_id}: {text}")

                                # Put the text in the queue
                                asyncio.run_coroutine_threadsafe(
                                    self.text_queue.put(text),
                                    asyncio.get_event_loop()
                                )

                            # Handle audio response
                            if hasattr(chunk, "audio") and chunk.audio:
                                audio_data = base64.b64decode(chunk.audio)
                                logger.info(f"Received {len(audio_data)} bytes of audio from Gemini for stream ID: {self.stream_id}")

                                # Put the audio in the queue
                                asyncio.run_coroutine_threadsafe(
                                    self.output_audio_queue.put(audio_data),
                                    asyncio.get_event_loop()
                                )

                    except Exception as e:
                        logger.error(f"Error generating response for stream ID {self.stream_id}: {e}", exc_info=True)

                # Sleep to avoid busy waiting
                time.sleep(0.1)

        except Exception as e:
            logger.error(f"Error in response handler thread for stream ID {self.stream_id}: {e}", exc_info=True)
        finally:
            logger.info(f"Response handler thread stopped for stream ID: {self.stream_id}")

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

        # Add audio to the buffer
        self.audio_buffer += audio_data
        logger.info(f"Added {len(audio_data)} bytes of audio to buffer for stream ID: {self.stream_id}, buffer size: {len(self.audio_buffer)}")

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
            # Create a prompt with the text
            prompt = [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": text
                        }
                    ]
                }
            ]

            # Generate a response
            response = self.model.generate_content(
                prompt,
                stream=True
            )

            # Process the response in a separate thread
            threading.Thread(
                target=self._process_text_response,
                args=(response,),
                daemon=True
            ).start()

            logger.info(f"Sent text prompt to Gemini for stream ID {self.stream_id}: {text}")

        except Exception as e:
            logger.error(f"Error sending text to Gemini for stream ID {self.stream_id}: {e}", exc_info=True)

    def _process_text_response(self, response):
        """Process a text response from the Gemini Live API."""
        try:
            for chunk in response:
                if not self.is_running:
                    break

                # Handle text response
                if hasattr(chunk, "text") and chunk.text:
                    text = chunk.text
                    logger.info(f"Received text from Gemini for stream ID {self.stream_id}: {text}")

                    # Put the text in the queue
                    asyncio.run_coroutine_threadsafe(
                        self.text_queue.put(text),
                        asyncio.get_event_loop()
                    )

        except Exception as e:
            logger.error(f"Error processing text response for stream ID {self.stream_id}: {e}", exc_info=True)

    async def get_audio(self) -> Optional[bytes]:
        """
        Get audio from the output queue.

        Returns:
            Audio data if available, None otherwise
        """
        try:
            # Try to get audio from the queue with a timeout
            audio_data = await asyncio.wait_for(self.output_audio_queue.get(), timeout=0.1)
            return audio_data
        except asyncio.TimeoutError:
            # No audio available
            return None
        except Exception as e:
            logger.error(f"Error getting audio for stream ID {self.stream_id}: {e}", exc_info=True)
            return None

    async def get_text(self) -> Optional[str]:
        """
        Get text from the output queue.

        Returns:
            Text if available, None otherwise
        """
        try:
            # Try to get text from the queue with a timeout
            text = await asyncio.wait_for(self.text_queue.get(), timeout=0.1)
            return text
        except asyncio.TimeoutError:
            # No text available
            return None
        except Exception as e:
            logger.error(f"Error getting text for stream ID {self.stream_id}: {e}", exc_info=True)
            return None
