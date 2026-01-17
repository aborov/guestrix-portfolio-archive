#!/usr/bin/env python3
"""
Gemini Live Client using the official Google Generative AI SDK

This module provides a client for interacting with Google's Gemini Live API
for bidirectional audio streaming using the official SDK. It handles connecting
to the API, sending audio data, and receiving responses.
"""

import asyncio
import base64
import logging
import time
from typing import Optional, Dict, Any, List, Callable, Awaitable

from google import generativeai as genai
from google.generativeai.types import content_types
from google.generativeai.types.generation_types import (
    GenerationConfig, 
    SpeechConfig, 
    VoiceConfig, 
    PrebuiltVoiceConfig
)

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
    Client for interacting with Gemini Live API using the official SDK.
    """

    def __init__(
        self, 
        api_key: str, 
        model: str, 
        stream_id: str, 
        voice: str = DEFAULT_VOICE,
        on_audio_callback: Optional[Callable[[bytes], Awaitable[None]]] = None,
        on_text_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ):
        """
        Initialize the Gemini Live client.

        Args:
            api_key: The Gemini API key
            model: The Gemini model to use
            stream_id: The stream ID for this connection
            voice: The voice to use for responses
            on_audio_callback: Callback function for audio responses
            on_text_callback: Callback function for text responses
        """
        self.api_key = api_key
        self.model = model
        self.stream_id = stream_id
        self.voice = voice
        self.on_audio_callback = on_audio_callback
        self.on_text_callback = on_text_callback
        
        # Configure the Gemini client
        genai.configure(api_key=self.api_key)
        
        # Client and session
        self.genai_client = None
        self.session = None
        
        # State tracking
        self.is_connected = False
        self.is_running = False
        
        # Audio queues
        self.input_audio_queue = asyncio.Queue()  # Audio to send to Gemini
        self.output_audio_queue = asyncio.Queue()  # Audio received from Gemini
        self.text_queue = asyncio.Queue()  # Text received from Gemini
        
        # Processing task
        self.processing_task = None
        
        logger.info(f"Initialized Gemini Live client for stream ID: {stream_id}")
    
    async def connect(self) -> str:
        """
        Connect to Gemini Live API using the official SDK.

        Returns:
            A welcome message from Gemini
        """
        try:
            # If already connected, disconnect first
            if self.session is not None:
                logger.info(f"Cleaning up existing connections for stream ID: {self.stream_id}")
                await self.disconnect()
            
            # Create the Gemini client
            self.genai_client = genai.GenerativeModel(self.model)
            
            # Create speech config
            speech_config = SpeechConfig(
                voice_config=VoiceConfig(
                    prebuilt_voice_config=PrebuiltVoiceConfig(
                        voice_name=self.voice
                    )
                ),
                language_code="en-US"
            )
            
            # Create generation config
            generation_config = GenerationConfig(
                temperature=0.7,
                top_p=0.95,
                top_k=40,
                candidate_count=1,
                max_output_tokens=1024,
                response_modalities=["AUDIO"]  # Only request AUDIO modality
            )
            
            # Create system instruction
            system_instruction = content_types.Content(
                parts=[content_types.Part(text=self._create_system_prompt())]
            )
            
            # Connect to the Live API
            logger.info(f"Connecting to Gemini Live API for stream ID: {self.stream_id}")
            
            # Create the session
            self.session = await self.genai_client.aio.live.connect(
                config={
                    "generation_config": generation_config,
                    "system_instruction": system_instruction,
                    "speech_config": speech_config,
                    "tools": [{"google_search": {}}]
                }
            )
            
            logger.info(f"Connected to Gemini Live API for stream ID: {self.stream_id}")
            
            # Set state
            self.is_connected = True
            self.is_running = True
            
            # Start processing task
            self.processing_task = asyncio.create_task(self._process_responses())
            
            # Return a welcome message
            welcome_message = "Hello! I'm Gemini, your AI assistant. How can I help you today?"
            return welcome_message
            
        except Exception as e:
            logger.error(f"Error connecting to Gemini Live API for stream ID {self.stream_id}: {e}", exc_info=True)
            self.is_running = False
            self.is_connected = False
            
            # Clean up resources
            if self.session:
                try:
                    await self.session.close()
                except Exception as close_error:
                    logger.error(f"Error closing session for stream ID {self.stream_id}: {close_error}")
                self.session = None
            
            return f"Error connecting to Gemini Live API: {e}"
    
    async def disconnect(self) -> None:
        """
        Disconnect from the Gemini Live API.
        """
        logger.info(f"Disconnecting from Gemini Live API for stream ID: {self.stream_id}")
        
        # Set state
        self.is_running = False
        self.is_connected = False
        
        # Cancel processing task
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
            self.processing_task = None
        
        # Close session
        if self.session:
            try:
                await self.session.close()
            except Exception as e:
                logger.error(f"Error closing session for stream ID {self.stream_id}: {e}")
            self.session = None
        
        logger.info(f"Disconnected from Gemini Live API for stream ID: {self.stream_id}")
    
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

        return system_prompt
    
    async def _process_responses(self) -> None:
        """Process responses from the Gemini Live API."""
        try:
            logger.info(f"Started response processor for stream ID: {self.stream_id}")
            
            while self.is_running and self.session:
                try:
                    # Receive response from Gemini
                    response = await self.session.receive()
                    
                    if response is None:
                        logger.warning(f"Received None response from Gemini for stream ID: {self.stream_id}")
                        continue
                    
                    # Process audio data
                    if response.data:
                        audio_data = response.data
                        audio_size = len(audio_data)
                        
                        if audio_size > 0:
                            # Log audio details
                            logger.info(f"Received {audio_size} bytes of audio from Gemini for stream ID: {self.stream_id}")
                            
                            # Put audio in the queue
                            await self.output_audio_queue.put(audio_data)
                            
                            # Call the audio callback if provided
                            if self.on_audio_callback:
                                await self.on_audio_callback(audio_data)
                    
                    # Process text data
                    if response.text:
                        text = response.text
                        logger.info(f"Received text from Gemini for stream ID {self.stream_id}: {text}")
                        
                        # Put text in the queue
                        await self.text_queue.put(text)
                        
                        # Call the text callback if provided
                        if self.on_text_callback:
                            await self.on_text_callback(text)
                
                except asyncio.CancelledError:
                    logger.info(f"Response processor cancelled for stream ID: {self.stream_id}")
                    raise
                except Exception as e:
                    logger.error(f"Error processing response for stream ID {self.stream_id}: {e}", exc_info=True)
            
            logger.info(f"Stopped response processor for stream ID: {self.stream_id}")
            
        except asyncio.CancelledError:
            logger.info(f"Response processor cancelled for stream ID: {self.stream_id}")
            raise
        except Exception as e:
            logger.error(f"Error in response processor for stream ID {self.stream_id}: {e}", exc_info=True)
        finally:
            self.is_running = False
            self.is_connected = False
    
    async def send_audio(self, audio_data: bytes) -> None:
        """
        Send audio to Gemini Live API.
        
        Args:
            audio_data: The audio data to send
        """
        if not self.is_running or not self.session:
            logger.warning(f"Cannot send audio: client is not running for stream ID: {self.stream_id}")
            return
        
        try:
            # Create audio part
            audio_part = content_types.Part(
                inline_data=content_types.InlineData(
                    mime_type="audio/pcm",
                    data=base64.b64encode(audio_data).decode()
                )
            )
            
            # Send the audio
            await self.session.send(audio_part)
            logger.debug(f"Sent {len(audio_data)} bytes of audio to Gemini for stream ID: {self.stream_id}")
            
        except Exception as e:
            logger.error(f"Error sending audio to Gemini for stream ID {self.stream_id}: {e}", exc_info=True)
    
    async def send_text(self, text: str) -> None:
        """
        Send text to Gemini Live API.
        
        Args:
            text: The text to send
        """
        if not self.is_running or not self.session:
            logger.warning(f"Cannot send text: client is not running for stream ID: {self.stream_id}")
            return
        
        try:
            # Send the text
            logger.info(f"Sending text for stream ID: {self.stream_id}")
            await self.session.send(text, end_of_turn=True)
            logger.info(f"Text sent for stream ID: {self.stream_id}")
            
        except Exception as e:
            logger.error(f"Error sending text for stream ID {self.stream_id}: {e}", exc_info=True)
    
    async def get_audio(self) -> Optional[bytes]:
        """
        Get audio from the output queue.
        
        Returns:
            Audio data or None if the queue is empty
        """
        try:
            if self.output_audio_queue.empty():
                return None
            
            return await self.output_audio_queue.get()
        except Exception as e:
            logger.error(f"Error getting audio for stream ID {self.stream_id}: {e}", exc_info=True)
            return None
    
    async def get_text(self) -> Optional[str]:
        """
        Get text from the text queue.
        
        Returns:
            Text or None if the queue is empty
        """
        try:
            if self.text_queue.empty():
                return None
            
            return await self.text_queue.get()
        except Exception as e:
            logger.error(f"Error getting text for stream ID {self.stream_id}: {e}", exc_info=True)
            return None
