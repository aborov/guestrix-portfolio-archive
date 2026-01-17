#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telnyx to Gemini Integration

This module provides a solution for integrating Telnyx with Gemini using the Telnyx speak API
as a fallback when the Gemini Live API is not available.
"""

import os
import json
import base64
import logging
import asyncio
import aiohttp
from dotenv import load_dotenv
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TelnyxGeminiIntegration:
    """
    Integration between Telnyx and Gemini.
    
    This class provides methods for sending audio from Telnyx to Gemini and
    sending text from Gemini to Telnyx.
    """
    
    def __init__(self, telnyx_api_key: str, gemini_api_key: str, call_control_id: str):
        """
        Initialize the Telnyx Gemini integration.
        
        Args:
            telnyx_api_key: The Telnyx API key
            gemini_api_key: The Gemini API key
            call_control_id: The Telnyx call control ID
        """
        self.telnyx_api_key = telnyx_api_key
        self.gemini_api_key = gemini_api_key
        self.call_control_id = call_control_id
        
        # Initialize sessions
        self.telnyx_session = None
        self.gemini_session = None
        
        # Initialize WebSockets
        self.telnyx_websocket = None
        self.gemini_websocket = None
        
        # Initialize state
        self.is_connected = False
        self.is_running = False
        
        # Initialize tasks
        self.tasks = []
        
        logger.info(f"Initialized Telnyx Gemini integration for call control ID: {call_control_id}")
    
    async def connect(self):
        """Connect to Telnyx and Gemini."""
        try:
            # Create sessions
            self.telnyx_session = aiohttp.ClientSession()
            self.gemini_session = aiohttp.ClientSession()
            
            # Connect to Gemini
            await self._connect_to_gemini()
            
            # Set state
            self.is_running = True
            
            # Start tasks
            self._start_tasks()
            
            logger.info(f"Connected to Telnyx and Gemini for call control ID: {self.call_control_id}")
            return True
        except Exception as e:
            logger.error(f"Error connecting to Telnyx and Gemini for call control ID {self.call_control_id}: {e}", exc_info=True)
            await self.disconnect()
            return False
    
    async def _connect_to_gemini(self):
        """Connect to the Gemini Live API."""
        try:
            # Create the WebSocket URL with the API key
            ws_url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={self.gemini_api_key}&alt=json"
            
            # Connect to the WebSocket
            logger.info(f"Connecting to Gemini Live API: {ws_url.replace(self.gemini_api_key, 'REDACTED')}")
            
            # Set connection options
            options = {
                'heartbeat': 30.0,  # Send heartbeat every 30 seconds
                'compress': 15,     # Enable compression
                'autoclose': False,  # Don't auto-close the connection
                'max_msg_size': 0   # No limit on message size
            }
            
            self.gemini_websocket = await self.gemini_session.ws_connect(ws_url, **options)
            logger.info(f"Connected to Gemini Live API WebSocket for call control ID: {self.call_control_id}")
            
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
                                    "text": "You are a helpful assistant. Please respond to the caller's questions."
                                }
                            ]
                        }
                    ]
                }
            }
            
            # Send the configuration
            await self.gemini_websocket.send_json(initial_config)
            logger.info(f"Sent initial configuration to Gemini Live API for call control ID: {self.call_control_id}")
            
            self.is_connected = True
            return True
        except Exception as e:
            logger.error(f"Error connecting to Gemini Live API for call control ID {self.call_control_id}: {e}", exc_info=True)
            return False
    
    def _start_tasks(self):
        """Start the tasks for processing messages."""
        # Cancel existing tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # Clear the tasks list
        self.tasks = []
        
        # Create new tasks
        self.tasks.append(asyncio.create_task(self._process_gemini_messages()))
        
        logger.info(f"Started tasks for call control ID: {self.call_control_id}")
    
    async def _process_gemini_messages(self):
        """Process messages from the Gemini Live API."""
        try:
            logger.info(f"Started Gemini message processor for call control ID: {self.call_control_id}")
            
            if not self.gemini_websocket:
                logger.error(f"Gemini WebSocket is None for call control ID: {self.call_control_id}")
                return
            
            message_count = 0
            
            async for msg in self.gemini_websocket:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    message_count += 1
                    logger.debug(f"Received Gemini WebSocket text message #{message_count} for call control ID {self.call_control_id}, length: {len(msg.data)}")
                    await self._handle_gemini_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"Gemini WebSocket error for call control ID {self.call_control_id}: {msg.data}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.warning(f"Gemini WebSocket closed for call control ID {self.call_control_id}")
                    break
            
            logger.info(f"Gemini WebSocket connection closed for call control ID: {self.call_control_id}, processed {message_count} messages")
            
        except asyncio.CancelledError:
            logger.info(f"Gemini message processor cancelled for call control ID: {self.call_control_id}")
            raise
        except Exception as e:
            logger.error(f"Error processing Gemini messages for call control ID {self.call_control_id}: {e}", exc_info=True)
        finally:
            # Ensure we clean up
            self.is_connected = False
            logger.info(f"Gemini message processor stopped for call control ID: {self.call_control_id}")
    
    async def _handle_gemini_message(self, data: str):
        """Handle a message from the Gemini Live API."""
        try:
            # Parse the message
            message = json.loads(data)
            
            # Log the message type
            message_type = message.get("type")
            if message_type:
                logger.debug(f"Received Gemini message type: {message_type} for call control ID: {self.call_control_id}")
            
            # Handle different message types
            if message_type == "response.audio.delta" and "delta" in message:
                # Handle audio response
                try:
                    audio_data = base64.b64decode(message["delta"])
                    audio_size = len(audio_data)
                    
                    if audio_size > 0:
                        logger.info(f"Received {audio_size} bytes of audio from Gemini for call control ID: {self.call_control_id}")
                        
                        # Send audio to Telnyx
                        await self._send_audio_to_telnyx(audio_data)
                    else:
                        logger.warning(f"Received empty audio data from Gemini for call control ID: {self.call_control_id}")
                except Exception as audio_error:
                    logger.error(f"Error processing audio data for call control ID {self.call_control_id}: {audio_error}", exc_info=True)
            
            elif message_type == "response.content.delta" and "delta" in message:
                # Handle text response
                if "text" in message["delta"]:
                    text = message["delta"]["text"]
                    logger.info(f"Received text from Gemini for call control ID {self.call_control_id}: {text}")
                    
                    # Send text to Telnyx as fallback
                    await self._send_text_to_telnyx(text)
            
            elif message_type == "error":
                # Handle error
                error_msg = message.get('error', {}).get('message', 'Unknown error')
                error_code = message.get('error', {}).get('code', 'unknown')
                logger.error(f"Gemini Live API error for call control ID {self.call_control_id}: [{error_code}] {error_msg}")
                
                # Send error message to Telnyx as fallback
                await self._send_text_to_telnyx(f"I'm sorry, I encountered an error. Please try again.")
            
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON for call control ID {self.call_control_id}: {data[:200]}...")
        except Exception as e:
            logger.error(f"Error handling Gemini message for call control ID {self.call_control_id}: {e}", exc_info=True)
    
    async def _send_audio_to_telnyx(self, audio_data: bytes):
        """Send audio to Telnyx."""
        try:
            # Encode audio as base64
            encoded_audio = base64.b64encode(audio_data).decode('utf-8')
            
            # Create media event
            media_event = {
                "event": "media",
                "media": {
                    "payload": encoded_audio
                }
            }
            
            # Send to Telnyx
            if self.telnyx_websocket and not self.telnyx_websocket.closed:
                await self.telnyx_websocket.send_json(media_event)
                logger.info(f"Sent {len(audio_data)} bytes of audio to Telnyx for call control ID: {self.call_control_id}")
            else:
                logger.warning(f"Cannot send audio to Telnyx: WebSocket closed for call control ID: {self.call_control_id}")
        except Exception as e:
            logger.error(f"Error sending audio to Telnyx for call control ID {self.call_control_id}: {e}", exc_info=True)
    
    async def _send_text_to_telnyx(self, text: str):
        """Send text to Telnyx using the speak API as fallback."""
        try:
            # Create the speak API URL
            url = f"https://api.telnyx.com/v2/calls/{self.call_control_id}/actions/speak"
            
            # Create the speak API request
            speak_request = {
                "payload": text,
                "voice": "female",
                "language": "en-US"
            }
            
            # Set headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.telnyx_api_key}"
            }
            
            # Send the request
            async with self.telnyx_session.post(url, json=speak_request, headers=headers) as response:
                if response.status == 200:
                    logger.info(f"Sent text to Telnyx speak API for call control ID {self.call_control_id}: {text}")
                else:
                    response_text = await response.text()
                    logger.error(f"Error sending text to Telnyx speak API for call control ID {self.call_control_id}: {response.status} {response_text}")
        except Exception as e:
            logger.error(f"Error sending text to Telnyx speak API for call control ID {self.call_control_id}: {e}", exc_info=True)
    
    async def send_audio_to_gemini(self, audio_data: bytes):
        """Send audio to Gemini."""
        try:
            if not self.is_connected or not self.gemini_websocket or self.gemini_websocket.closed:
                logger.warning(f"Cannot send audio to Gemini: WebSocket closed for call control ID: {self.call_control_id}")
                
                # Try to reconnect
                if not await self._connect_to_gemini():
                    logger.error(f"Failed to reconnect to Gemini for call control ID: {self.call_control_id}")
                    return
            
            # Create audio append message
            audio_append = {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(audio_data).decode()
            }
            
            # Send the message
            await self.gemini_websocket.send_json(audio_append)
            logger.info(f"Sent {len(audio_data)} bytes of audio to Gemini for call control ID: {self.call_control_id}")
        except Exception as e:
            logger.error(f"Error sending audio to Gemini for call control ID {self.call_control_id}: {e}", exc_info=True)
    
    async def send_text_to_gemini(self, text: str):
        """Send text to Gemini."""
        try:
            if not self.is_connected or not self.gemini_websocket or self.gemini_websocket.closed:
                logger.warning(f"Cannot send text to Gemini: WebSocket closed for call control ID: {self.call_control_id}")
                
                # Try to reconnect
                if not await self._connect_to_gemini():
                    logger.error(f"Failed to reconnect to Gemini for call control ID: {self.call_control_id}")
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
            await self.gemini_websocket.send_json(text_content)
            logger.info(f"Sent text to Gemini for call control ID {self.call_control_id}: {text}")
        except Exception as e:
            logger.error(f"Error sending text to Gemini for call control ID {self.call_control_id}: {e}", exc_info=True)
    
    async def disconnect(self):
        """Disconnect from Telnyx and Gemini."""
        logger.info(f"Disconnecting from Telnyx and Gemini for call control ID: {self.call_control_id}")
        
        # Set state
        self.is_running = False
        self.is_connected = False
        
        # Cancel tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Close WebSockets
        if self.gemini_websocket:
            await self.gemini_websocket.close()
            self.gemini_websocket = None
        
        if self.telnyx_websocket:
            await self.telnyx_websocket.close()
            self.telnyx_websocket = None
        
        # Close sessions
        if self.gemini_session:
            await self.gemini_session.close()
            self.gemini_session = None
        
        if self.telnyx_session:
            await self.telnyx_session.close()
            self.telnyx_session = None
        
        logger.info(f"Disconnected from Telnyx and Gemini for call control ID: {self.call_control_id}")

async def test_integration():
    """Test the Telnyx Gemini integration."""
    # Load environment variables
    load_dotenv()
    
    # Get API keys
    telnyx_api_key = os.getenv("TELNYX_API_KEY")
    gemini_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    if not telnyx_api_key:
        logger.error("Telnyx API key not found in environment variables")
        return False
    
    if not gemini_api_key:
        logger.error("Gemini API key not found in environment variables")
        return False
    
    # Create a test call control ID
    call_control_id = "test-call-control-id"
    
    # Create the integration
    integration = TelnyxGeminiIntegration(telnyx_api_key, gemini_api_key, call_control_id)
    
    try:
        # Connect to Telnyx and Gemini
        if not await integration.connect():
            logger.error("Failed to connect to Telnyx and Gemini")
            return False
        
        # Send a test message to Gemini
        await integration.send_text_to_gemini("Hello, Gemini! This is a test message.")
        
        # Wait for a response
        logger.info("Waiting for response...")
        await asyncio.sleep(5)
        
        # Disconnect
        await integration.disconnect()
        
        return True
    except Exception as e:
        logger.error(f"Error testing Telnyx Gemini integration: {e}", exc_info=True)
        return False

async def main():
    """Main function."""
    # Test the integration
    success = await test_integration()
    
    if success:
        logger.info("Telnyx Gemini integration test completed successfully")
    else:
        logger.error("Telnyx Gemini integration test failed")

if __name__ == "__main__":
    asyncio.run(main())
