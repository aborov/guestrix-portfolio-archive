#!/usr/bin/env python3
import os
import sys
import json
import time
import requests
import argparse
from datetime import datetime, timedelta

# Get Telnyx API key from environment
TELNYX_API_KEY = os.getenv("TELNYX_API_KEY")

def get_call_events(call_control_id=None, event_type=None, hours=1):
    """
    Get call events from Telnyx API.

    Args:
        call_control_id: Optional call control ID to filter by
        event_type: Optional event type to filter by (e.g., 'call.transcription')
        hours: Number of hours to look back for events (default: 1)
    """
    print(f"Querying Telnyx API for call events...")

    # Calculate time range
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)

    # Format times for API
    start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Base URL for call events
    url = "https://api.telnyx.com/v2/call_events"

    # Headers
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {TELNYX_API_KEY}"
    }

    # Query parameters
    params = {
        "filter[occurred_at][gte]": start_time_str,
        "filter[occurred_at][lte]": end_time_str,
        "page[size]": 100  # Maximum page size
    }

    # Add call control ID filter if provided
    if call_control_id:
        params["filter[call_control_id]"] = call_control_id
        print(f"Filtering by call control ID: {call_control_id}")

    # Add event type filter if provided
    if event_type:
        params["filter[event_type]"] = event_type
        print(f"Filtering by event type: {event_type}")

    print(f"Looking for events from {start_time_str} to {end_time_str}")

    # Send the request
    response = requests.get(url, headers=headers, params=params)

    if response.status_code == 200:
        result = response.json()
        events = result.get("data", [])
        print(f"Found {len(events)} events")
        return events
    else:
        print(f"Failed to get call events: {response.status_code} - {response.text}")
        return []

def get_call_details(call_control_id):
    """
    Get detailed information about a specific call.

    Args:
        call_control_id: The call control ID to get details for
    """
    print(f"Getting details for call {call_control_id}...")

    # URL for call details
    url = f"https://api.telnyx.com/v2/calls/{call_control_id}"

    # Headers
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {TELNYX_API_KEY}"
    }

    # Send the request
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        result = response.json()
        return result.get("data", {})
    else:
        print(f"Failed to get call details: {response.status_code} - {response.text}")
        return {}

def get_transcription_status(call_control_id):
    """
    Get transcription status for a specific call.

    Args:
        call_control_id: The call control ID to check transcription status for
    """
    print(f"Checking transcription status for call {call_control_id}...")

    # Get all events for this call
    events = get_call_events(call_control_id=call_control_id)

    # Filter for transcription events
    transcription_events = [event for event in events if event.get("event_type") == "call.transcription"]

    if transcription_events:
        print(f"Found {len(transcription_events)} transcription events for call {call_control_id}")
        for event in transcription_events:
            payload = event.get("payload", {})
            transcription_data = payload.get("transcription_data", {})
            if not transcription_data and "transcript" in payload:
                transcription_data = payload

            transcript = transcription_data.get("transcript", "")
            is_final = transcription_data.get("is_final", False)
            confidence = transcription_data.get("confidence", 0)

            print(f"Transcript: '{transcript}', Final: {is_final}, Confidence: {confidence}")
    else:
        print(f"No transcription events found for call {call_control_id}")

        # Check if transcription was started
        transcription_start_events = [event for event in events if
                                     event.get("event_type") == "call.command" and
                                     event.get("payload", {}).get("command_id", "").startswith("transcription_start")]

        if transcription_start_events:
            print(f"Found {len(transcription_start_events)} transcription start commands for call {call_control_id}")
            for event in transcription_start_events:
                print(f"Transcription start command: {json.dumps(event.get('payload', {}), indent=2)}")
        else:
            print(f"No transcription start commands found for call {call_control_id}")

def list_recent_calls(hours=1):
    """
    List recent calls from Telnyx API.

    Args:
        hours: Number of hours to look back for calls (default: 1)
    """
    print(f"Listing recent calls from the past {hours} hours...")

    # Get call.initiated events
    events = get_call_events(event_type="call.initiated", hours=hours)

    if events:
        print(f"Found {len(events)} recent calls:")
        for event in events:
            # Debug the event structure
            print(f"Event structure: {json.dumps(event, indent=2)}")

            # Try to extract call details
            payload = event.get("payload", {})
            call_control_id = payload.get("call_control_id", "")
            from_number = payload.get("from", "")
            to_number = payload.get("to", "")
            occurred_at = event.get("occurred_at", "")

            print(f"Call ID: {call_control_id}")
            print(f"  From: {from_number}")
            print(f"  To: {to_number}")
            print(f"  Time: {occurred_at}")
            print()
    else:
        print("No recent calls found")

def main():
    parser = argparse.ArgumentParser(description="Query Telnyx API for call transcription")
    parser.add_argument("--call-id", help="Call control ID to check transcription for")
    parser.add_argument("--list-calls", action="store_true", help="List recent calls")
    parser.add_argument("--hours", type=float, default=1, help="Number of hours to look back (default: 1)")
    parser.add_argument("--event-type", help="Filter by event type (e.g., call.transcription)")

    args = parser.parse_args()

    if args.list_calls:
        list_recent_calls(hours=args.hours)
    elif args.call_id:
        get_transcription_status(args.call_id)
    elif args.event_type:
        events = get_call_events(event_type=args.event_type, hours=args.hours)
        print(json.dumps(events, indent=2))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
