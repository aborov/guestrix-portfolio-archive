#!/usr/bin/env python3
"""
Simple Socket.IO server for text chat
This is a temporary solution while the AWS API Gateway WebSocket is being fixed
"""

import os
import json
import logging
import asyncio
import argparse
from datetime import datetime
from aiohttp import web
import socketio
import google.generativeai as genai

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Socket.IO server
sio = socketio.AsyncServer(
    async_mode='aiohttp',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True
)
app = web.Application()
sio.attach(app)

# Active connections
active_connections = {}

# Configure Gemini
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = 'gemini-2.0-flash'

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("Gemini API configured")
else:
    logger.warning("GEMINI_API_KEY not set, AI responses will be simulated")

# Socket.IO event handlers
@sio.event
async def connect(sid, environ, auth):
    """Handle new connection"""
    logger.info(f"New connection: {sid}")
    
    # Check for authentication token
    token = auth.get('token') if auth else None
    if not token:
        # Try to get token from query params
        query = environ.get('QUERY_STRING', '')
        import urllib.parse
        params = dict(urllib.parse.parse_qsl(query))
        token = params.get('token')
    
    if not token:
        logger.warning(f"Connection {sid} rejected: No authentication token")
        return False
    
    # Store connection info
    active_connections[sid] = {
        'connected_at': datetime.now().isoformat(),
        'token': token,
        'property_id': None
    }
    
    # Send welcome message
    await sio.emit('message', {
        'type': 'auth_success',
        'payload': {
            'message': 'Connected to chat service'
        }
    }, room=sid)
    
    return True

@sio.event
async def disconnect(sid):
    """Handle disconnection"""
    logger.info(f"Connection closed: {sid}")
    if sid in active_connections:
        del active_connections[sid]

@sio.event
async def message(sid, data):
    """Handle incoming messages"""
    logger.info(f"Message from {sid}: {data}")
    
    try:
        # Parse message data
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                data = {'message': data}
        
        # Extract message content and property ID
        message_text = data.get('payload', {}).get('message', '')
        property_id = data.get('payload', {}).get('property_id', '')
        
        # Store property ID if provided
        if property_id and sid in active_connections:
            active_connections[sid]['property_id'] = property_id
        
        # Generate AI response
        response = await generate_ai_response(message_text, property_id)
        
        # Send response back to client
        await sio.emit('message', {
            'type': 'message',
            'payload': {
                'message': response,
                'sender': 'ai'
            },
            'timestamp': datetime.now().timestamp()
        }, room=sid)
        
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        await sio.emit('message', {
            'type': 'error',
            'payload': {
                'message': f"Error processing message: {str(e)}"
            }
        }, room=sid)

@sio.event
async def ping(sid, data):
    """Handle ping messages (keepalive)"""
    logger.info(f"Ping from {sid}")
    await sio.emit('message', {
        'type': 'pong',
        'payload': {
            'message': 'Connection alive'
        },
        'timestamp': datetime.now().timestamp()
    }, room=sid)

async def generate_ai_response(message, property_id=None):
    """Generate AI response using Gemini or fallback to simulated response"""
    if not GEMINI_API_KEY:
        # Simulate AI response
        return f"This is a simulated response to: '{message}'"
    
    try:
        # Create a system prompt
        system_prompt = "You are a helpful concierge assistant for a vacation rental property."
        if property_id:
            system_prompt += f" The property ID is {property_id}."
        
        # Generate response with Gemini
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            [
                {"role": "system", "parts": [system_prompt]},
                {"role": "user", "parts": [message]}
            ],
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 800,
            }
        )
        
        return response.text
    except Exception as e:
        logger.error(f"Error generating AI response: {e}", exc_info=True)
        return f"I'm sorry, I encountered an error processing your request. Please try again."

async def on_startup(app):
    """Startup tasks"""
    logger.info("Socket.IO server starting up")

async def on_shutdown(app):
    """Shutdown tasks"""
    logger.info("Socket.IO server shutting down")

# Register startup/shutdown handlers
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Socket.IO server for text chat')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8083, help='Port to bind to')
    args = parser.parse_args()
    
    logger.info(f"Starting Socket.IO server on {args.host}:{args.port}")
    web.run_app(app, host=args.host, port=args.port)
