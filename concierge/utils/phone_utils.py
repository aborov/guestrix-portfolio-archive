"""
Phone number utilities for the Guestrix system.
Handles phone number normalization, validation, and matching.
"""

import re
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

def normalize_phone_number(phone: str) -> str:
    """
    Normalize phone number for consistent lookup and storage.
    
    Args:
        phone: Raw phone number string
        
    Returns:
        Normalized phone number (digits only, US format)
    """
    if not phone:
        return ""
    
    # Remove all non-digits
    digits_only = ''.join(filter(str.isdigit, phone))
    
    # Handle US numbers
    if len(digits_only) == 11 and digits_only.startswith('1'):
        # Remove leading 1 for US numbers
        return digits_only[1:]
    elif len(digits_only) == 10:
        # Already 10 digits, assume US
        return digits_only
    elif len(digits_only) > 10:
        # International number, return as-is
        return digits_only
    else:
        # Less than 10 digits, return as-is (might be partial)
        return digits_only

def generate_phone_variations(phone: str) -> List[str]:
    """
    Generate different variations of a phone number for flexible matching.
    
    Args:
        phone: Normalized phone number
        
    Returns:
        List of phone number variations
    """
    if not phone:
        return []
    
    normalized = normalize_phone_number(phone)
    variations = [
        phone,  # Original format
        normalized,  # Normalized format
        f"+1{normalized}",  # With +1 country code
        f"1{normalized}",  # With 1 country code
    ]
    
    # Add formatted version for 10-digit US numbers
    if len(normalized) == 10:
        formatted = f"({normalized[:3]}) {normalized[3:6]}-{normalized[6:]}"
        variations.append(formatted)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_variations = []
    for variation in variations:
        if variation not in seen:
            seen.add(variation)
            unique_variations.append(variation)
    
    return unique_variations

def validate_phone_number(phone_number: str) -> bool:
    """
    Validate phone number format.
    
    Args:
        phone_number: Phone number to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not phone_number:
        return False
    
    # Remove all non-digit characters except +
    clean_phone = re.sub(r'[^\d+]', '', phone_number)
    
    # Basic validation patterns
    patterns = [
        r'^\+1\d{10}$',  # US format: +1xxxxxxxxxx
        r'^\+\d{10,15}$',  # International format: +xxxxxxxxxxxx
        r'^\d{10}$',  # US without country code: xxxxxxxxxx
    ]
    
    for pattern in patterns:
        if re.match(pattern, clean_phone):
            return True
    
    return False

def clean_phone_for_storage(phone_number: str) -> str:
    """
    Clean and format phone number for consistent storage.
    
    Args:
        phone_number: Phone number to clean
        
    Returns:
        Cleaned phone number in +1xxxxxxxxxx format
    """
    if not phone_number:
        return ""
    
    # Remove all non-digit characters except +
    clean_phone = re.sub(r'[^\d+]', '', phone_number)
    
    # If no country code, assume US
    if not clean_phone.startswith('+'):
        if len(clean_phone) == 10:
            clean_phone = '+1' + clean_phone
        elif len(clean_phone) == 11 and clean_phone.startswith('1'):
            clean_phone = '+' + clean_phone
        else:
            # For other lengths, add +1 anyway
            clean_phone = '+1' + clean_phone
    
    return clean_phone

def phones_match(phone1: str, phone2: str) -> bool:
    """
    Check if two phone numbers match after cleaning.
    
    Args:
        phone1: First phone number
        phone2: Second phone number
        
    Returns:
        True if they match, False otherwise
    """
    if not phone1 or not phone2:
        return False
    
    clean1 = clean_phone_for_storage(phone1)
    clean2 = clean_phone_for_storage(phone2)
    
    return clean1 == clean2

def get_phone_last_4(phone: str) -> str:
    """
    Get the last 4 digits of a normalized phone number.
    
    Args:
        phone: Phone number
        
    Returns:
        Last 4 digits, or empty string if less than 4 digits
    """
    normalized = normalize_phone_number(phone)
    return normalized[-4:] if len(normalized) >= 4 else ""

def format_phone_display(phone_number: str) -> str:
    """
    Format phone number for display purposes.
    
    Args:
        phone_number: Phone number to format
        
    Returns:
        Formatted phone number for display
    """
    if not phone_number:
        return ""
    
    clean_phone = clean_phone_for_storage(phone_number)
    
    # Format US numbers as (XXX) XXX-XXXX
    if clean_phone.startswith('+1') and len(clean_phone) == 12:
        digits = clean_phone[2:]  # Remove +1
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    
    # For other formats, just return as-is
    return clean_phone

def get_last_4_digits(phone_number: str) -> str:
    """
    Get the last 4 digits of a phone number.
    
    Args:
        phone_number: Phone number to extract from
        
    Returns:
        Last 4 digits as string
    """
    if not phone_number:
        return ""
    
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone_number)
    
    # Return last 4 digits
    return digits[-4:] if len(digits) >= 4 else digits 