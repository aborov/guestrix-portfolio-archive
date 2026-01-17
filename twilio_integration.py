#!/usr/bin/env python3
"""
Twilio SIP trunk integration for LiveKit.

This module provides classes and functions for integrating Twilio SIP trunking
with LiveKit for telephony integration.
"""

import os
import logging
from typing import Dict, Any, Optional, List, Callable
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Dial

# Configure logging
logger = logging.getLogger("livekit.twilio")

class TwilioIntegration:
    """
    Twilio SIP trunk integration for LiveKit.

    This class provides methods for configuring and managing a Twilio SIP trunk
    for use with LiveKit.
    """

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        phone_number: Optional[str] = None,
        livekit_sip_uri: Optional[str] = None
    ):
        """
        Initialize the Twilio integration.

        Args:
            account_sid: The Twilio account SID
            auth_token: The Twilio auth token
            phone_number: The Twilio phone number to use
            livekit_sip_uri: The LiveKit SIP URI to use
        """
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.phone_number = phone_number
        # For production, use a public domain. For testing with ngrok, we need to use a TCP tunnel
        # since SIP requires direct TCP/UDP access which ngrok free tier doesn't support for TCP tunnels

        # For testing with Twilio, we need to use a SIP URI that Twilio can reach
        # This won't work with localhost, as Twilio can't reach your local machine
        # Instead, we'll use a special Twilio Client endpoint that can connect to any publicly accessible WebSocket endpoint

        # Format: client:username
        # This tells Twilio to connect to the client with the specified username
        # We'll configure the client to connect to our WebSocket endpoint in the TwiML response

        self.livekit_sip_uri = livekit_sip_uri or "client:guestrix"

        # Note: For this to work in production, you would need:
        # 1. A public IP address or domain pointing to your LiveKit SIP server
        # 2. Proper port forwarding for UDP/TCP on port 8080
        # 3. Update this URI to use that public address

        # Initialize Twilio client
        self.client = Client(account_sid, auth_token)

        logger.info(f"Initialized Twilio integration with account SID {account_sid[:4]}...{account_sid[-4:]}")
        if phone_number:
            logger.info(f"Using phone number {phone_number}")
        if livekit_sip_uri:
            logger.info(f"Using LiveKit SIP URI {livekit_sip_uri}")

    def generate_twiml_for_livekit(self, livekit_room_name: str) -> str:
        """
        Generate TwiML for connecting to a LiveKit room.

        Args:
            livekit_room_name: The name of the LiveKit room to connect to

        Returns:
            The generated TwiML
        """
        try:
            logger.info(f"Generating TwiML for LiveKit room {livekit_room_name}")

            # Create a new TwiML response
            response = VoiceResponse()

            # Add a Dial verb with a SIP endpoint
            dial = Dial()

            # Add the SIP endpoint
            if self.livekit_sip_uri:
                # For Twilio Client, we need to add the WebSocket URL as a parameter
                # The ngrok URL should be the public URL of your server

                # Get the ngrok URL from the environment or use a default for testing
                ngrok_url = os.environ.get("NGROK_URL", "2146-75-194-21-68.ngrok-free.app")

                # Add the room name as a parameter to the client URI
                client_uri = f"{self.livekit_sip_uri}?room={livekit_room_name}"

                # Add the client to the dial verb
                dial.client(
                    "guestrix",
                    url=f"https://{ngrok_url}/twilio/client"
                )

            # Add the Dial verb to the response
            response.append(dial)

            # Convert to string
            twiml = str(response)

            logger.info(f"Generated TwiML: {twiml}")
            return twiml

        except Exception as e:
            logger.error(f"Error generating TwiML: {e}")
            raise

    def handle_incoming_call(self, request_data: Dict[str, Any]) -> str:
        """
        Handle an incoming call webhook from Twilio.

        Args:
            request_data: The webhook request data

        Returns:
            The TwiML response
        """
        try:
            # Get the caller's phone number
            caller = request_data.get("From", "unknown")
            called = request_data.get("To", "unknown")

            logger.info(f"Handling incoming call from {caller} to {called}")

            # Create a room name based on the caller's phone number
            # Remove the + from the phone number and use it as the room name
            room_name = f"call-{caller.replace('+', '')}"

            # Generate TwiML for connecting to LiveKit
            twiml = self.generate_twiml_for_livekit(room_name)

            return twiml

        except Exception as e:
            logger.error(f"Error handling incoming call: {e}")

            # Return a simple TwiML response
            response = VoiceResponse()
            response.say("Sorry, there was an error processing your call.")
            response.hangup()

            return str(response)
