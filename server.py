#!/usr/bin/env python3
"""
LiveKit server for integrating Twilio and Gemini Live.

This module provides a server for integrating Twilio SIP trunking with
Google's Gemini Live API using LiveKit.
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from twilio.twiml.voice_response import VoiceResponse

from utils import setup_logging, load_config, log_config
from gemini_agent import GeminiAgent
from twilio_integration import TwilioIntegration
from audio_processor import resample_audio

# Configure logging
logger = setup_logging()

# Load configuration
config = load_config()
log_config(config)

# Initialize Flask app with relative template path
script_dir = os.path.dirname(os.path.abspath(__file__))
template_folder = os.path.join(script_dir, "livekit_local", "templates")
app = Flask(__name__, template_folder=template_folder)
CORS(app)

# Initialize Gemini agent
gemini_agent = GeminiAgent(
    api_key=config["gemini"]["api_key"],
    model=config["gemini"]["model"],
    voice=config["gemini"]["voice"],
    temperature=0.8
)

# Initialize Twilio integration
twilio_integration = TwilioIntegration(
    account_sid=config["twilio"]["account_sid"],
    auth_token=config["twilio"]["auth_token"],
    phone_number=config["twilio"]["phone_number"],
    livekit_sip_uri=f"sip:{config['livekit']['host']}:8080"
)

# Active calls
active_calls = {}

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "ok"})

@app.route("/client", methods=["GET"])
def client():
    """Serve the Twilio Client page."""
    return render_template("client.html")

@app.route("/twilio/voice", methods=["POST"])
def twilio_voice_webhook():
    """
    Handle Twilio voice webhooks.

    This endpoint is called by Twilio when a call is received.
    """
    try:
        # Get request data
        request_data = request.form.to_dict()

        # Log the request
        logger.info(f"Received Twilio voice webhook: {json.dumps(request_data)}")

        # Handle the incoming call
        twiml = twilio_integration.handle_incoming_call(request_data)

        # Return the TwiML response
        return twiml

    except Exception as e:
        logger.error(f"Error handling Twilio voice webhook: {e}")

        # Return a simple TwiML response
        response = VoiceResponse()
        response.say("Sorry, there was an error processing your call.")
        response.hangup()

        return str(response)

@app.route("/twilio/client", methods=["GET", "POST"])
def twilio_client_webhook():
    """
    Handle Twilio Client capability token request.

    This endpoint is called by Twilio when a client needs a capability token.
    """
    try:
        logger.info("Received Twilio Client capability token request")

        # Get the room name from the request
        room_name = request.args.get("room")
        logger.info(f"Room name: {room_name}")

        # Generate a capability token for the client
        # This token allows the client to make and receive calls
        from twilio.jwt.client import ClientCapabilityToken

        # Create a capability token
        token = ClientCapabilityToken(
            account_sid=config["twilio"]["account_sid"],
            auth_token=config["twilio"]["auth_token"]
        )

        # Allow the client to receive calls
        token.allow_client_incoming("guestrix")

        # Generate the token
        token_str = token.to_jwt().decode("utf-8")

        # Return the token as JSON
        return jsonify({"token": token_str})

    except Exception as e:
        logger.error(f"Error handling Twilio Client capability token request: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/twilio/sip", methods=["GET", "POST"])
def twilio_sip_webhook():
    """
    Handle Twilio SIP WebSocket connection.

    This endpoint is called by Twilio when a SIP WebSocket connection is established.
    """
    try:
        logger.info("Received Twilio SIP WebSocket connection")

        # This endpoint will be used by Twilio to establish a WebSocket connection
        # We'll need to upgrade the connection to a WebSocket and then proxy it to LiveKit

        # For now, just return a 200 OK to test the connection
        return "OK"

    except Exception as e:
        logger.error(f"Error handling Twilio SIP WebSocket connection: {e}")
        return "Error", 500

@app.route("/livekit/sip", methods=["POST"])
def livekit_sip_webhook():
    """
    Handle LiveKit SIP webhooks.

    This endpoint is called by LiveKit when a SIP event occurs.
    """
    try:
        # Get request data
        request_data = request.json

        # Log the request
        logger.info(f"Received LiveKit SIP webhook: {json.dumps(request_data)}")

        # Handle the event
        event_type = request_data.get("type")

        if event_type == "participant_joined":
            # A participant joined the call
            participant_id = request_data.get("participant", {}).get("id")
            room_name = request_data.get("room", {}).get("name")

            logger.info(f"Participant {participant_id} joined room {room_name}")

            # Start a new Gemini agent session for this call
            asyncio.create_task(start_call_session(participant_id, room_name))

        elif event_type == "participant_left":
            # A participant left the call
            participant_id = request_data.get("participant", {}).get("id")
            room_name = request_data.get("room", {}).get("name")

            logger.info(f"Participant {participant_id} left room {room_name}")

            # End the Gemini agent session for this call
            asyncio.create_task(end_call_session(participant_id))

        return jsonify({"status": "ok"})

    except Exception as e:
        logger.error(f"Error handling LiveKit SIP webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

async def start_call_session(participant_id: str, room_name: str) -> None:
    """
    Start a new call session with Gemini Live API.

    Args:
        participant_id: The participant ID
        room_name: The room name
    """
    try:
        logger.info(f"Starting call session for participant {participant_id} in room {room_name}")

        # Create a new Gemini agent session
        session = await gemini_agent.create_session()

        # Store the session
        active_calls[participant_id] = {
            "session": session,
            "room_name": room_name,
            "start_time": asyncio.get_event_loop().time()
        }

        # Start the conversation
        await gemini_agent.start_conversation("Hello, I'm your AI concierge assistant. How can I help you today?")

        logger.info(f"Call session started for participant {participant_id}")

    except Exception as e:
        logger.error(f"Error starting call session: {e}")

async def end_call_session(participant_id: str) -> None:
    """
    End a call session with Gemini Live API.

    Args:
        participant_id: The participant ID
    """
    try:
        logger.info(f"Ending call session for participant {participant_id}")

        # Get the session
        call_data = active_calls.get(participant_id)
        if not call_data:
            logger.warning(f"No call session found for participant {participant_id}")
            return

        # Close the session
        await gemini_agent.close()

        # Remove the session
        del active_calls[participant_id]

        logger.info(f"Call session ended for participant {participant_id}")

    except Exception as e:
        logger.error(f"Error ending call session: {e}")

async def process_audio(participant_id: str, audio_data: bytes) -> None:
    """
    Process audio data from a participant.

    Args:
        participant_id: The participant ID
        audio_data: The audio data
    """
    try:
        # Get the call data
        call_data = active_calls.get(participant_id)
        if not call_data:
            logger.warning(f"No call session found for participant {participant_id}")
            return

        # Resample the audio if needed
        resampled_audio = resample_audio(
            audio_data,
            config["twilio"]["sample_rate"],
            config["gemini"]["sample_rate"]
        )

        # Send the audio to Gemini
        await gemini_agent.send_audio(resampled_audio)

        # Receive audio from Gemini
        response_audio = await gemini_agent.receive_audio()

        if response_audio:
            # Resample the response audio if needed
            resampled_response = resample_audio(
                response_audio,
                config["gemini"]["sample_rate"],
                config["twilio"]["sample_rate"]
            )

            # Send the response audio back to the participant
            # This would be handled by LiveKit's SIP integration
            pass

    except Exception as e:
        logger.error(f"Error processing audio: {e}")

def run_server():
    """Run the server."""
    host = config["server"]["host"]
    port = 5001  # Hardcoded to avoid conflict with AirPlay

    logger.info(f"Starting server on {host}:{port}")
    app.run(host=host, port=port, debug=False)

if __name__ == "__main__":
    run_server()
