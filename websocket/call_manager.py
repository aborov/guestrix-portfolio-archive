#!/usr/bin/env python3
"""
Call Manager

This module provides a class for managing active calls, including tracking
call state, WebSocket connections, and Gemini clients.
"""

import time
import logging
import asyncio
from typing import Dict, Any, Optional, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)
logger = logging.getLogger(__name__)

class CallManager:
    """
    Manager for active calls.

    This class provides methods for tracking active calls, including their
    state, WebSocket connections, and Gemini clients.
    """

    def __init__(self, inactive_timeout: int = 300):
        """
        Initialize the call manager.

        Args:
            inactive_timeout: The timeout in seconds after which inactive calls are cleaned up
        """
        self.active_calls = {}  # Dictionary of active calls
        self.inactive_timeout = inactive_timeout  # Timeout in seconds

        # Start the cleanup task
        self.cleanup_task = None

        logger.info(f"Initialized call manager with inactive timeout of {inactive_timeout} seconds")

    def start_cleanup_task(self):
        """Start the inactive call cleanup task."""
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._cleanup_inactive_calls())
            logger.info("Started inactive call cleanup task")

    async def _cleanup_inactive_calls(self):
        """Periodically clean up inactive calls."""
        try:
            while True:
                # Wait for a while before checking
                await asyncio.sleep(60)  # Check every minute

                # Get current time
                current_time = time.time()

                # Find inactive calls
                inactive_calls = []
                for stream_id, call_state in self.active_calls.items():
                    last_active = call_state.get("last_active_timestamp", 0)
                    if current_time - last_active > self.inactive_timeout:
                        inactive_calls.append(stream_id)

                # Clean up inactive calls
                for stream_id in inactive_calls:
                    logger.info(f"Cleaning up inactive call: {stream_id}")
                    await self.remove_call(stream_id)

                # Log status
                if inactive_calls:
                    logger.info(f"Cleaned up {len(inactive_calls)} inactive calls")
                logger.debug(f"Active calls: {len(self.active_calls)}")

        except asyncio.CancelledError:
            logger.info("Inactive call cleanup task cancelled")
        except Exception as e:
            logger.error(f"Error in inactive call cleanup task: {e}", exc_info=True)

    def add_call(self, stream_id: str, call_control_id: str, from_number: str,
                 to_number: str, telnyx_ws, gemini_client, **kwargs) -> Dict[str, Any]:
        """
        Add a new call to the manager.

        Args:
            stream_id: The stream ID for this call
            call_control_id: The Telnyx call control ID
            from_number: The caller's phone number
            to_number: The called phone number
            telnyx_ws: The WebSocket connection to Telnyx
            gemini_client: The Gemini client for this call
            **kwargs: Additional call state parameters

        Returns:
            The call state dictionary
        """
        # Create call state
        call_state = {
            "stream_id": stream_id,
            "call_control_id": call_control_id,
            "from_number": from_number,
            "to_number": to_number,
            "telnyx_ws": telnyx_ws,
            "gemini_client": gemini_client,
            "start_timestamp": time.time(),
            "last_active_timestamp": time.time(),
            "media_packets_received": 0,
            "media_packets_sent": 0,
            "property_id": None,
            "context": None,
            "guest_name": None,
            "caller_phone_number": from_number,
            "reconnect_attempts": 0,
            "transcription_active": False
        }

        # Add any additional parameters
        call_state.update(kwargs)

        # Add to active calls
        self.active_calls[stream_id] = call_state

        # Log call details
        property_id = call_state.get("property_id")
        guest_name = call_state.get("guest_name")
        context_length = len(call_state.get("context", "")) if call_state.get("context") else 0

        log_message = f"Added new call: {stream_id} from {from_number} to {to_number}"
        if property_id:
            log_message += f", property: {property_id}"
        if guest_name:
            log_message += f", guest: {guest_name}"
        if context_length > 0:
            log_message += f", context: {context_length} chars"

        logger.info(log_message)

        return call_state

    async def remove_call(self, stream_id: str) -> bool:
        """
        Remove a call from the manager.

        Args:
            stream_id: The stream ID of the call to remove

        Returns:
            True if the call was removed, False otherwise
        """
        # Check if call exists
        if stream_id not in self.active_calls:
            logger.warning(f"Cannot remove call {stream_id}: not found")
            return False

        # Get call state
        call_state = self.active_calls[stream_id]

        # Disconnect Gemini client
        gemini_client = call_state.get("gemini_client")
        if gemini_client:
            try:
                await gemini_client.disconnect()
                logger.info(f"Disconnected Gemini client for call {stream_id}")
            except Exception as e:
                logger.error(f"Error disconnecting Gemini client for call {stream_id}: {e}", exc_info=True)

        # Remove from active calls
        del self.active_calls[stream_id]

        logger.info(f"Removed call: {stream_id}")

        return True

    def get_call(self, stream_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the state of a call.

        Args:
            stream_id: The stream ID of the call

        Returns:
            The call state dictionary, or None if the call is not found
        """
        return self.active_calls.get(stream_id)

    def update_call_activity(self, stream_id: str) -> bool:
        """
        Update the last active timestamp for a call.

        Args:
            stream_id: The stream ID of the call

        Returns:
            True if the call was updated, False otherwise
        """
        # Check if call exists
        if stream_id not in self.active_calls:
            logger.warning(f"Cannot update call {stream_id}: not found")
            return False

        # Update last active timestamp
        self.active_calls[stream_id]["last_active_timestamp"] = time.time()

        return True

    def update_call_property(self, stream_id: str, property_id: str, context: Dict[str, Any]) -> bool:
        """
        Update the property information for a call.

        Args:
            stream_id: The stream ID of the call
            property_id: The property ID
            context: The property context

        Returns:
            True if the call was updated, False otherwise
        """
        # Check if call exists
        if stream_id not in self.active_calls:
            logger.warning(f"Cannot update call {stream_id}: not found")
            return False

        # Update property information
        self.active_calls[stream_id]["property_id"] = property_id
        self.active_calls[stream_id]["context"] = context

        logger.info(f"Updated property information for call {stream_id}: {property_id}")

        return True

    def increment_media_packets(self, stream_id: str, direction: str = "received") -> bool:
        """
        Increment the media packet count for a call.

        Args:
            stream_id: The stream ID of the call
            direction: The direction of the media packet ("received" or "sent")

        Returns:
            True if the call was updated, False otherwise
        """
        # Check if call exists
        if stream_id not in self.active_calls:
            logger.warning(f"Cannot increment media packets for call {stream_id}: not found")
            return False

        # Increment media packet count
        if direction == "received":
            self.active_calls[stream_id]["media_packets_received"] += 1
        elif direction == "sent":
            self.active_calls[stream_id]["media_packets_sent"] += 1

        return True

    def call_exists(self, stream_id: str) -> bool:
        """
        Check if a call exists.

        Args:
            stream_id: The stream ID of the call

        Returns:
            True if the call exists, False otherwise
        """
        return stream_id in self.active_calls

    def get_active_calls(self) -> List[Dict[str, Any]]:
        """
        Get a list of all active calls.

        Returns:
            A list of call state dictionaries
        """
        return list(self.active_calls.values())

    def get_call_count(self) -> int:
        """
        Get the number of active calls.

        Returns:
            The number of active calls
        """
        return len(self.active_calls)

    def update_call_state(self, stream_id: str, state_updates: Dict[str, Any]) -> bool:
        """
        Update the state of a call with arbitrary key-value pairs.

        Args:
            stream_id: The stream ID of the call
            state_updates: Dictionary of state updates to apply

        Returns:
            True if the call was updated, False otherwise
        """
        # Check if call exists
        if stream_id not in self.active_calls:
            logger.warning(f"Cannot update call state for {stream_id}: not found")
            return False

        # Update call state
        for key, value in state_updates.items():
            self.active_calls[stream_id][key] = value

        logger.debug(f"Updated call state for {stream_id}: {state_updates.keys()}")

        return True
