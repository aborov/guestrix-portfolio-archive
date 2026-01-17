#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gemini Live API Reference Implementation

This module provides a reference implementation for the Gemini Live API using WebSockets.
Based on the example at https://github.com/google-gemini/cookbook/blob/main/quickstarts/websockets/Get_started_LiveAPI.py
"""

import os
import json
import base64
import logging
import asyncio
import aiohttp
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GeminiLiveClient:
    """
    Client for the Gemini Live API using WebSockets.
    
    This client provides methods for sending audio and text to the Gemini Live API
    and receiving audio and text responses.
    """
    
    def __init__(self, api_key):
        """
        Initialize the Gemini Live client.
        
        Args:
            api_key: The Gemini API key
        """
        self.api_key = api_key
        self.session = None
        self.websocket = None
        self.is_connected = False
        
        # Initialize queues for audio and text
        self.output_audio_queue = asyncio.Queue()
        self.output_text_queue = asyncio.Queue()
    
    async def connect(self):
        """Connect to the Gemini Live API."""
        # Create a session
        self.session = aiohttp.ClientSession()
        
        # Create the WebSocket URL with the API key
        ws_url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={self.api_key}&alt=json"
        
        # Connect to the WebSocket
        logger.info(f"Connecting to Gemini Live API: {ws_url.replace(self.api_key, 'REDACTED')}")
        self.websocket = await self.session.ws_connect(ws_url)
        logger.info("Connected to Gemini Live API WebSocket")
        
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
        logger.info("Sent initial configuration to Gemini Live API")
        
        self.is_connected = True
    
    async def send_text(self, text):
        """
        Send a text prompt to Gemini Live API.
        
        Args:
            text: The text prompt to send
        """
        if not self.is_connected:
            logger.warning("Cannot send text: client is not connected")
            return
        
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
        logger.info(f"Sent text prompt to Gemini: {text}")
    
    async def send_audio(self, audio_data):
        """
        Send audio to Gemini Live API.
        
        Args:
            audio_data: The audio data to send
        """
        if not self.is_connected:
            logger.warning("Cannot send audio: client is not connected")
            return
        
        # Create audio append message
        audio_append = {
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(audio_data).decode()
        }
        
        # Send the message
        await self.websocket.send_json(audio_append)
        logger.info(f"Sent {len(audio_data)} bytes of audio to Gemini")
    
    async def receive_messages(self):
        """Receive messages from the Gemini Live API."""
        if not self.is_connected:
            logger.warning("Cannot receive messages: client is not connected")
            return
        
        try:
            async for msg in self.websocket:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {msg.data}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.warning("WebSocket closed")
                    break
        except Exception as e:
            logger.error(f"Error receiving messages: {e}")
        finally:
            self.is_connected = False
    
    async def _handle_message(self, data):
        """
        Handle a message from the Gemini Live API.
        
        Args:
            data: The message data
        """
        try:
            # Parse the message
            message = json.loads(data)
            
            # Log the message type
            message_type = message.get("type", "unknown")
            logger.debug(f"Received message type: {message_type}")
            
            # Handle different message types
            if message_type == "response.audio.delta" and "delta" in message:
                # Handle audio response
                audio_data = base64.b64decode(message["delta"])
                logger.info(f"Received {len(audio_data)} bytes of audio from Gemini")
                await self.output_audio_queue.put(audio_data)
                
            elif message_type == "response.content.delta" and "delta" in message:
                # Handle text response
                if "text" in message["delta"]:
                    text = message["delta"]["text"]
                    logger.info(f"Received text from Gemini: {text}")
                    await self.output_text_queue.put(text)
                    
            elif message_type == "error":
                # Handle error
                error = message.get("error", {})
                error_message = error.get("message", "Unknown error")
                logger.error(f"Received error from Gemini: {error_message}")
                
            # Add more message type handlers as needed
                
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON: {data}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def get_audio(self):
        """
        Get audio from the output queue.
        
        Returns:
            Audio data if available, None otherwise
        """
        try:
            return await asyncio.wait_for(self.output_audio_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None
    
    async def get_text(self):
        """
        Get text from the output queue.
        
        Returns:
            Text if available, None otherwise
        """
        try:
            return await asyncio.wait_for(self.output_text_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None
    
    async def disconnect(self):
        """Disconnect from the Gemini Live API."""
        logger.info("Disconnecting from Gemini Live API")
        
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        
        if self.session:
            await self.session.close()
            self.session = None
        
        self.is_connected = False
        logger.info("Disconnected from Gemini Live API")

async def test_client():
    """Test the Gemini Live client."""
    # Load environment variables
    load_dotenv()
    
    # Get API key
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        logger.error("API key not found in environment variables")
        return
    
    # Create a client
    client = GeminiLiveClient(api_key)
    
    try:
        # Connect to the Gemini Live API
        await client.connect()
        
        # Start receiving messages in the background
        receive_task = asyncio.create_task(client.receive_messages())
        
        # Send a text prompt
        await client.send_text("Hello, Gemini! This is a test message.")
        
        # Wait for a response
        logger.info("Waiting for response...")
        
        # Wait for up to 10 seconds for a response
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < 10:
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
        
        # Cancel the receive task
        receive_task.cancel()
        try:
            await receive_task
        except asyncio.CancelledError:
            pass
        
        # Disconnect
        await client.disconnect()
        
        return True
    
    except Exception as e:
        logger.error(f"Error testing Gemini Live client: {e}")
        return False

async def main():
    """Main function."""
    # Test the client
    success = await test_client()
    
    if success:
        logger.info("Gemini Live client test completed successfully")
    else:
        logger.error("Gemini Live client test failed")

if __name__ == "__main__":
    asyncio.run(main())
