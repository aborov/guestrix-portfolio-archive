#!/usr/bin/env python3
"""
Audio Processor

This module provides functions for processing audio data, including
resampling, encoding, and decoding between different formats.
"""

import logging
import audioop
import numpy as np
from typing import Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
TELNYX_SAMPLE_RATE = 16000  # Telnyx G722 uses 16kHz
GEMINI_SAMPLE_RATE = 24000  # Gemini provides audio at 24kHz
AUDIO_CHANNELS = 1  # Mono audio
BYTES_PER_SAMPLE = 2  # 16-bit audio
TELNYX_CODEC = "G722"  # Using G722 codec for Telnyx

def resample_audio(audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
    """
    Resample audio from one sample rate to another.

    Args:
        audio_data: The audio data to resample
        from_rate: The original sample rate
        to_rate: The target sample rate

    Returns:
        The resampled audio data
    """
    try:
        # Check if resampling is needed
        if from_rate == to_rate:
            logger.debug(f"No resampling needed, rates match: {from_rate}Hz")
            return audio_data

        # Log audio data details
        logger.info(f"Resampling {len(audio_data)} bytes of audio from {from_rate}Hz to {to_rate}Hz")

        # Check if audio data is valid
        if not audio_data or len(audio_data) < BYTES_PER_SAMPLE:
            logger.warning(f"Invalid audio data for resampling: {len(audio_data)} bytes")
            return audio_data

        # Use audioop to resample the audio
        # The second parameter (2) indicates 16-bit audio (2 bytes per sample)
        # The third parameter (1) indicates mono audio (1 channel)
        resampled_audio, _ = audioop.ratecv(audio_data, BYTES_PER_SAMPLE, AUDIO_CHANNELS, from_rate, to_rate, None)

        # Calculate resampling ratio for verification
        expected_ratio = to_rate / from_rate
        actual_ratio = len(resampled_audio) / len(audio_data)

        logger.info(f"Resampled {len(audio_data)} bytes of audio from {from_rate}Hz to {to_rate}Hz, resulting in {len(resampled_audio)} bytes")
        logger.info(f"Resampling ratio - Expected: {expected_ratio:.2f}, Actual: {actual_ratio:.2f}")

        return resampled_audio

    except Exception as e:
        logger.error(f"Error resampling audio: {e}", exc_info=True)
        # Return original audio data if resampling fails
        return audio_data

def encode_audio(audio_data: bytes, codec: str = "OPUS") -> bytes:
    """
    Encode audio data using the specified codec.

    Args:
        audio_data: The raw PCM audio data to encode
        codec: The codec to use (e.g., "OPUS", "PCMU", "PCMA", "G722")

    Returns:
        The encoded audio data
    """
    try:
        # For now, we'll just return the raw PCM data
        # In a real implementation, this would encode the audio using the specified codec
        logger.debug(f"Encoding {len(audio_data)} bytes of audio using {codec} codec")

        # TODO: Implement actual encoding using the specified codec
        # This would typically use a library like opuslib for OPUS encoding

        return audio_data

    except Exception as e:
        logger.error(f"Error encoding audio: {e}", exc_info=True)
        # Return original audio data if encoding fails
        return audio_data

def decode_audio(audio_data: bytes, codec: str = "OPUS") -> bytes:
    """
    Decode audio data from the specified codec.

    Args:
        audio_data: The encoded audio data to decode
        codec: The codec used to encode the audio

    Returns:
        The decoded PCM audio data
    """
    try:
        # For now, we'll just return the raw data
        # In a real implementation, this would decode the audio from the specified codec
        logger.debug(f"Decoding {len(audio_data)} bytes of audio from {codec} codec")

        # TODO: Implement actual decoding using the specified codec
        # This would typically use a library like opuslib for OPUS decoding

        return audio_data

    except Exception as e:
        logger.error(f"Error decoding audio: {e}", exc_info=True)
        # Return original audio data if decoding fails
        return audio_data

def convert_pcm_to_opus(pcm_data: bytes, sample_rate: int = 16000) -> bytes:
    """
    Convert PCM audio data to OPUS format.

    Args:
        pcm_data: The PCM audio data to convert
        sample_rate: The sample rate of the PCM audio

    Returns:
        The OPUS-encoded audio data
    """
    try:
        # In a real implementation, this would use opuslib to encode the PCM data
        # For now, we'll just return the PCM data
        logger.debug(f"Converting {len(pcm_data)} bytes of PCM audio to OPUS at {sample_rate}Hz")

        # TODO: Implement actual OPUS encoding
        # This would typically use a library like opuslib

        return pcm_data

    except Exception as e:
        logger.error(f"Error converting PCM to OPUS: {e}", exc_info=True)
        # Return original audio data if conversion fails
        return pcm_data

def convert_opus_to_pcm(opus_data: bytes, sample_rate: int = 16000) -> bytes:
    """
    Convert OPUS audio data to PCM format.

    Args:
        opus_data: The OPUS audio data to convert
        sample_rate: The target sample rate for the PCM audio

    Returns:
        The PCM audio data
    """
    try:
        # In a real implementation, this would use opuslib to decode the OPUS data
        # For now, we'll just return the OPUS data
        logger.debug(f"Converting {len(opus_data)} bytes of OPUS audio to PCM at {sample_rate}Hz")

        # TODO: Implement actual OPUS decoding
        # This would typically use a library like opuslib

        return opus_data

    except Exception as e:
        logger.error(f"Error converting OPUS to PCM: {e}", exc_info=True)
        # Return original audio data if conversion fails
        return opus_data

def adjust_volume(audio_data: bytes, factor: float = 1.0) -> bytes:
    """
    Adjust the volume of audio data.

    Args:
        audio_data: The audio data to adjust
        factor: The volume adjustment factor (1.0 = no change, 0.5 = half volume, 2.0 = double volume)

    Returns:
        The volume-adjusted audio data
    """
    try:
        # Use audioop to adjust the volume
        # The second parameter (2) indicates 16-bit audio (2 bytes per sample)
        adjusted_audio = audioop.mul(audio_data, BYTES_PER_SAMPLE, factor)

        logger.debug(f"Adjusted volume of {len(audio_data)} bytes of audio by factor {factor}")

        return adjusted_audio

    except Exception as e:
        logger.error(f"Error adjusting volume: {e}", exc_info=True)
        # Return original audio data if adjustment fails
        return audio_data

def detect_silence(audio_data: bytes, threshold: int = 500) -> bool:
    """
    Detect if audio data contains silence.

    Args:
        audio_data: The audio data to check
        threshold: The RMS threshold below which audio is considered silence

    Returns:
        True if the audio is silence, False otherwise
    """
    try:
        # Use audioop to calculate the RMS of the audio
        # The second parameter (2) indicates 16-bit audio (2 bytes per sample)
        rms = audioop.rms(audio_data, BYTES_PER_SAMPLE)

        # Check if RMS is below threshold
        is_silence = rms < threshold

        logger.debug(f"Audio RMS: {rms}, threshold: {threshold}, is_silence: {is_silence}")

        return is_silence

    except Exception as e:
        logger.error(f"Error detecting silence: {e}", exc_info=True)
        # Assume not silence if detection fails
        return False
