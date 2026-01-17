#!/usr/bin/env python3
"""
Fix for Audio Processor

This script fixes the audio processor to handle the "not a whole number of frames" error.
"""

import sys
import os

# Path to the file to fix
file_path = "/home/ubuntu/telnyx_websocket/websocket/audio_processor.py"

# Read the file
with open(file_path, 'r') as f:
    content = f.read()

# Fix the resample_audio function
old_function = """def resample_audio(audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
    \"\"\"
    Resample audio from one sample rate to another.
    
    Args:
        audio_data: The audio data to resample
        from_rate: The original sample rate
        to_rate: The target sample rate
    
    Returns:
        The resampled audio data
    \"\"\"
    try:
        # Check if resampling is needed
        if from_rate == to_rate:
            return audio_data
        
        # Use audioop to resample the audio
        # The second parameter (2) indicates 16-bit audio (2 bytes per sample)
        # The third parameter (1) indicates mono audio (1 channel)
        resampled_audio, _ = audioop.ratecv(audio_data, BYTES_PER_SAMPLE, AUDIO_CHANNELS, from_rate, to_rate, None)
        
        logger.debug(f"Resampled {len(audio_data)} bytes of audio from {from_rate}Hz to {to_rate}Hz, resulting in {len(resampled_audio)} bytes")
        
        return resampled_audio
    
    except Exception as e:
        logger.error(f"Error resampling audio: {e}", exc_info=True)
        # Return original audio data if resampling fails
        return audio_data"""

new_function = """def resample_audio(audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
    \"\"\"
    Resample audio from one sample rate to another.
    
    Args:
        audio_data: The audio data to resample
        from_rate: The original sample rate
        to_rate: The target sample rate
    
    Returns:
        The resampled audio data
    \"\"\"
    try:
        # Check if resampling is needed
        if from_rate == to_rate:
            return audio_data
        
        # Check if the audio data is a whole number of frames
        # Each frame is BYTES_PER_SAMPLE * AUDIO_CHANNELS bytes
        frame_size = BYTES_PER_SAMPLE * AUDIO_CHANNELS
        if len(audio_data) % frame_size != 0:
            # Pad the audio data to make it a whole number of frames
            padding_bytes = frame_size - (len(audio_data) % frame_size)
            audio_data = audio_data + b'\\x00' * padding_bytes
            logger.debug(f"Padded audio data with {padding_bytes} bytes to make it a whole number of frames")
        
        # Use audioop to resample the audio
        # The second parameter (2) indicates 16-bit audio (2 bytes per sample)
        # The third parameter (1) indicates mono audio (1 channel)
        resampled_audio, _ = audioop.ratecv(audio_data, BYTES_PER_SAMPLE, AUDIO_CHANNELS, from_rate, to_rate, None)
        
        logger.debug(f"Resampled {len(audio_data)} bytes of audio from {from_rate}Hz to {to_rate}Hz, resulting in {len(resampled_audio)} bytes")
        
        return resampled_audio
    
    except Exception as e:
        logger.error(f"Error resampling audio: {e}", exc_info=True)
        # Return original audio data if resampling fails
        return audio_data"""

# Replace the function
content = content.replace(old_function, new_function)

# Write the file back
with open(file_path, 'w') as f:
    f.write(content)

print(f"Fixed audio processor in {file_path}")

# Now let's restart the service
import subprocess
subprocess.run(["sudo", "systemctl", "restart", "telnyx-gemini.service"])

print("Restarted the service")
