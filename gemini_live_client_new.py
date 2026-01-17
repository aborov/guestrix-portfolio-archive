#!/usr/bin/env python3
"""
Gemini Live Client

This module provides a client for interacting with Google's Gemini Live API
for bidirectional audio streaming. It handles connecting to the API, sending
audio data, and receiving responses.
"""

import os
import json
import base64
import asyncio
import logging
import queue
from typing import Optional, Dict, Any, List
import aiohttp
from google import generativeai as genai
from google.generativeai import types

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
    
    def __init__(self, api_key: str, model: str, stream_id: str, voice: str = DEFAULT_VOICE):
        """
        Initialize the Gemini Live client.
        
        Args:
            api_key: The Gemini API key
            model: The Gemini model to use
            stream_id: The stream ID for this connection
            voice: The voice to use for responses
        """
        self.api_key = api_key
        self.model = model
        self.stream_id = stream_id
        self.voice = voice
        
        # WebSocket connection
        self.websocket = None
        self.session = None
        
        # State tracking
        self.is_connected = False
        self.is_running = False
        
        # Audio queues
        self.input_audio_queue = asyncio.Queue()  # Audio to send to Gemini
        self.output_audio_queue = asyncio.Queue()  # Audio received from Gemini
        self.text_queue = asyncio.Queue()  # Text received from Gemini
        
        # Tasks
        self.tasks = []
        
        logger.info(f"Initialized Gemini Live client for stream ID: {stream_id}")
    
    async def connect(self) -> str:
        """
        Connect to Gemini Live API.
        
        Returns:
            A welcome message from Gemini
        """
        try:
            # Create a new session
            self.session = aiohttp.ClientSession()
            
            # Connect to Gemini Live API
            ws_url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={self.api_key}&alt=json"
            logger.info(f"Connecting to Gemini Live API: {ws_url.replace(self.api_key, 'REDACTED')}")
            
            try:
                self.websocket = await self.session.ws_connect(ws_url, timeout=30)
                logger.info("Connected to Gemini Live API WebSocket")
                
                # Set state
                self.is_connected = True
                self.is_running = True
                
                # Send initial configuration
                await self._send_initial_config()
                
                # Wait a moment for the configuration to be processed
                await asyncio.sleep(1)
                
                # Check if the connection is still open
                if self.websocket.closed:
                    logger.error("WebSocket connection closed after sending configuration")
                    self.is_running = False
                    self.is_connected = False
                    return "Sorry, I'm having trouble connecting to the AI service. Please try again later."
                
                # Start processing tasks
                self.tasks = [
                    asyncio.create_task(self._process_websocket_messages()),
                    asyncio.create_task(self._process_input_audio())
                ]
                
                # Return a welcome message
                welcome_message = "Hello! I'm Gemini, your AI assistant. How can I help you today?"
                return welcome_message
                
            except aiohttp.ClientError as ce:
                logger.error(f"Error connecting to Gemini Live API: {ce}", exc_info=True)
                self.is_running = False
                self.is_connected = False
                return "Sorry, I'm having trouble connecting to the AI service. Please try again later."
            
        except Exception as e:
            logger.error(f"Error connecting to Gemini Live API: {e}", exc_info=True)
            self.is_running = False
            self.is_connected = False
            return "Sorry, I'm having trouble connecting to the AI service. Please try again later."
    
    async def _send_initial_config(self):
        """Send initial configuration to Gemini Live API."""
        try:
            # Create initial configuration
            initial_config = {
                "setup": {
                    "model": f"models/{self.model}",
                    "generationConfig": {
                        "responseModalities": ["AUDIO"],
                        "speechConfig": {
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {
                                    "voiceName": self.voice
                                }
                            },
                            "languageCode": "en-US"
                        }
                    },
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
                    }
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
        
        You have access to the following tools:
        1. google_search: Use this tool to search for information about local attractions, restaurants, services, or any other information that would be helpful to the guest.
        """
        
        return system_prompt
    
    async def _process_websocket_messages(self):
        """Process messages from the Gemini Live API WebSocket."""
        try:
            async for msg in self.websocket:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_websocket_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {msg.data}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.error("WebSocket connection closed by server")
                    break
            
            logger.info("WebSocket connection closed")
            
        except Exception as e:
            logger.error(f"Error processing WebSocket messages: {e}", exc_info=True)
        finally:
            # Ensure we clean up
            self.is_running = False
            logger.info("Stopped processing WebSocket messages")
    
    async def _handle_websocket_message(self, data: str):
        """Handle a message from the Gemini Live API WebSocket."""
        try:
            # Parse the message
            message = json.loads(data)
            
            # Log the message type
            message_type = message.get("type")
            if message_type:
                logger.debug(f"Received message type: {message_type}")
            
            # Handle different message types
            if message_type == "response.audio.delta" and "delta" in message:
                # Handle audio response
                audio_data = base64.b64decode(message["delta"])
                await self.output_audio_queue.put(audio_data)
                logger.debug(f"Queued {len(audio_data)} bytes of audio from Gemini")
                
            elif message_type == "response.content.delta" and "delta" in message:
                # Handle text response
                if "text" in message["delta"]:
                    text = message["delta"]["text"]
                    await self.text_queue.put(text)
                    logger.debug(f"Received text from Gemini: {text}")
            
            elif message_type == "session.updated":
                # Session was updated successfully
                logger.info("Gemini Live session updated successfully")
            
            elif message_type == "error":
                # Handle error
                error_message = message.get('error', {}).get('message', 'Unknown error')
                logger.error(f"Gemini Live API error: {error_message}")
                
                # Log the full error message for debugging
                logger.error(f"Full error message: {message}")
                
                # Set is_running to False to prevent further audio processing
                self.is_running = False
            
            # Log the full message for debugging (except for audio data)
            if message_type != "response.audio.delta":
                logger.debug(f"Full message: {message}")
            
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON: {data}")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}", exc_info=True)
    
    async def _process_input_audio(self):
        """Process audio from the input queue and send it to Gemini Live API."""
        try:
            while self.is_running:
                # Get audio from the queue
                try:
                    audio_data = await asyncio.wait_for(self.input_audio_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    # No audio in the queue, continue
                    continue
                
                # Send audio to Gemini Live API
                if self.is_connected and self.websocket and not self.websocket.closed:
                    # Create audio append message
                    audio_append = {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(audio_data).decode()
                    }
                    
                    # Send the message
                    await self.websocket.send_json(audio_append)
                    logger.debug(f"Sent {len(audio_data)} bytes of audio to Gemini")
                
                # Mark the task as done
                self.input_audio_queue.task_done()
                
        except Exception as e:
            logger.error(f"Error processing input audio: {e}", exc_info=True)
        finally:
            logger.info("Stopped processing input audio")
    
    async def send_audio(self, audio_data: bytes):
        """
        Send audio to Gemini Live API.
        
        Args:
            audio_data: The audio data to send
        """
        if not self.is_running:
            logger.warning("Cannot send audio: client is not running")
            return
        
        # Add audio to the queue
        await self.input_audio_queue.put(audio_data)
    
    async def get_audio(self) -> Optional[bytes]:
        """
        Get audio from Gemini Live API.
        
        Returns:
            Audio data or None if no audio is available
        """
        try:
            # Try to get audio from the queue (non-blocking)
            return self.output_audio_queue.get_nowait()
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
