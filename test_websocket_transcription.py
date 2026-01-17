#!/usr/bin/env python3
"""
Test script to verify WebSocket server transcription configuration.
This script tests the Gemini Live client configuration without making actual calls.
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the deploy_websocket directory to the path
deploy_websocket_dir = os.path.join(os.path.dirname(__file__), 'deploy_websocket')
sys.path.append(deploy_websocket_dir)

try:
    from websocket.gemini_live_client import GeminiLiveClient
    print("✅ Successfully imported GeminiLiveClient")
    print(f"🔍 Imported from: {GeminiLiveClient.__module__}")

    # Check the file path
    import inspect
    file_path = inspect.getfile(GeminiLiveClient)
    print(f"🔍 File path: {file_path}")
except ImportError as e:
    print(f"❌ Failed to import GeminiLiveClient: {e}")
    sys.exit(1)

async def test_gemini_client():
    """Test the Gemini Live client configuration."""

    # Get API key
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY not found in environment variables")
        return False

    print("✅ Found GEMINI_API_KEY")

    try:
        # Create Gemini Live client
        client = GeminiLiveClient(
            api_key=api_key,
            model="gemini-2.0-flash-live-001",
            stream_id="test-stream-123",
            voice="Aoede"
        )
        print("✅ Successfully created GeminiLiveClient")

        # Test that transcription queue exists
        print(f"🔍 Client attributes: {[attr for attr in dir(client) if not attr.startswith('_')]}")
        if hasattr(client, 'transcription_queue'):
            print("✅ Transcription queue is available")
        else:
            print("❌ Transcription queue is NOT available")
            return False

        # Test that get_transcription method exists
        if hasattr(client, 'get_transcription'):
            print("✅ get_transcription method is available")
        else:
            print("❌ get_transcription method is NOT available")
            return False

        return True

    except Exception as e:
        print(f"❌ Error creating client: {e}")
        return False

async def main():
    print("🧪 Testing WebSocket Server Transcription Configuration")
    print("=" * 60)

    # Test client configuration
    print("\n⚙️ Testing Gemini Live client...")
    client_ok = await test_gemini_client()

    if client_ok:
        print("\n🎉 All tests passed! WebSocket server transcription should work correctly.")
        print("\n📋 Next steps:")
        print("1. Deploy the updated WebSocket server")
        print("2. Make a voice call to test transcription")
        print("3. Check logs for transcription messages")
        print("4. Verify transcriptions appear in guest dashboard")
    else:
        print("\n❌ Tests failed. Please check the error messages above.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
