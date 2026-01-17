#!/usr/bin/env python3
"""
Test script to verify Gemini Live API transcription configuration.
This script tests the configuration without making actual calls.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the concierge directory to the path
sys.path.append('concierge')

try:
    import google.genai as genai
    from google.genai import types
    print("✅ Successfully imported google.genai")
except ImportError as e:
    print(f"❌ Failed to import google.genai: {e}")
    sys.exit(1)

def test_transcription_config():
    """Test the Gemini Live API transcription configuration."""
    
    # Get API key
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ GEMINI_API_KEY not found in environment variables")
        return False
    
    print("✅ Found GEMINI_API_KEY")
    
    try:
        # Create Gemini client
        client = genai.Client(http_options={"api_version": "v1alpha"}, api_key=api_key)
        print("✅ Successfully created Gemini client")
        
        # Test the transcription configuration
        config = types.LiveConnectConfig(
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            ),
            # Enable transcription for both input and output audio
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig()
        )
        print("✅ Successfully created LiveConnectConfig with transcription enabled")
        
        # Test the configuration by checking its attributes
        print(f"✅ Response modalities: {config.response_modalities}")
        print(f"✅ Voice name: {config.speech_config.voice_config.prebuilt_voice_config.voice_name}")
        print(f"✅ Input audio transcription enabled: {config.input_audio_transcription is not None}")
        print(f"✅ Output audio transcription enabled: {config.output_audio_transcription is not None}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating configuration: {e}")
        return False

def test_types_availability():
    """Test if all required types are available."""
    
    required_types = [
        'LiveConnectConfig',
        'SpeechConfig', 
        'VoiceConfig',
        'PrebuiltVoiceConfig',
        'AudioTranscriptionConfig'
    ]
    
    for type_name in required_types:
        if hasattr(types, type_name):
            print(f"✅ {type_name} is available")
        else:
            print(f"❌ {type_name} is NOT available")
            return False
    
    return True

if __name__ == "__main__":
    print("🧪 Testing Gemini Live API Transcription Configuration")
    print("=" * 60)
    
    # Test types availability
    print("\n📋 Testing types availability...")
    types_ok = test_types_availability()
    
    if not types_ok:
        print("\n❌ Some required types are missing. Please check your google.genai version.")
        sys.exit(1)
    
    # Test configuration
    print("\n⚙️ Testing transcription configuration...")
    config_ok = test_transcription_config()
    
    if config_ok:
        print("\n🎉 All tests passed! Transcription configuration should work correctly.")
    else:
        print("\n❌ Configuration test failed. Please check the error messages above.")
        sys.exit(1)
