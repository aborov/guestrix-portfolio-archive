"""
Date utility functions for consistent date handling across the application.

This module provides centralized date handling to ensure consistency between:
- iCal parsing and storage
- Firestore and DynamoDB storage
- UI display and JavaScript handling
- Conversation data mapping
"""

from datetime import datetime, date, timezone
from typing import Union, Optional
import re


def to_date_only(date_input: Union[datetime, date, str]) -> str:
    """
    Convert any date input to a date-only string format (YYYY-MM-DD).
    
    This function ensures all dates are stored and handled consistently
    as date-only strings, avoiding timezone-related issues.
    
    Args:
        date_input: datetime object, date object, or ISO string
        
    Returns:
        Date string in YYYY-MM-DD format
        
    Raises:
        ValueError: If the input cannot be parsed as a date
    """
    if date_input is None:
        raise ValueError("Date input cannot be None")
    
    if isinstance(date_input, str):
        # Handle ISO format strings
        if 'T' in date_input:
            # Parse datetime string and extract date part
            try:
                dt = datetime.fromisoformat(date_input.replace('Z', '+00:00'))
                return dt.date().isoformat()
            except ValueError:
                # Try parsing without timezone info
                dt = datetime.fromisoformat(date_input.split('T')[0])
                return dt.date().isoformat()
        else:
            # Already a date string, validate format
            try:
                parsed_date = datetime.strptime(date_input, '%Y-%m-%d').date()
                return parsed_date.isoformat()
            except ValueError:
                raise ValueError(f"Invalid date string format: {date_input}")
    
    elif isinstance(date_input, datetime):
        return date_input.date().isoformat()
    
    elif isinstance(date_input, date):
        return date_input.isoformat()
    
    else:
        raise ValueError(f"Unsupported date input type: {type(date_input)}")


def parse_ical_date(ical_date: Union[datetime, date]) -> str:
    """
    Parse iCal date/datetime and return as date-only string.
    
    Args:
        ical_date: Date or datetime from iCal parsing
        
    Returns:
        Date string in YYYY-MM-DD format
    """
    if isinstance(ical_date, date) and not isinstance(ical_date, datetime):
        return ical_date.isoformat()
    elif isinstance(ical_date, datetime):
        return ical_date.date().isoformat()
    else:
        raise ValueError(f"Invalid iCal date type: {type(ical_date)}")


def format_date_for_display(date_input: Union[str, datetime, date], format_type: str = 'short') -> str:
    """
    Format a date for display in UI templates.
    
    Args:
        date_input: Date string, datetime, or date object
        format_type: 'short' (Jan 15, 2024), 'long' (January 15, 2024), 'iso' (2024-01-15)
        
    Returns:
        Formatted date string
    """
    if date_input is None:
        return 'N/A'
    
    try:
        # Convert to date object
        if isinstance(date_input, str):
            if 'T' in date_input:
                # Parse datetime string and extract date
                dt = datetime.fromisoformat(date_input.replace('Z', '+00:00'))
                date_obj = dt.date()
            else:
                # Parse date string
                date_obj = datetime.strptime(date_input, '%Y-%m-%d').date()
        elif isinstance(date_input, datetime):
            date_obj = date_input.date()
        elif isinstance(date_input, date):
            date_obj = date_input
        else:
            return 'Invalid Date'
        
        # Format based on type
        if format_type == 'short':
            return date_obj.strftime('%b %d, %Y')  # Jan 15, 2024
        elif format_type == 'long':
            return date_obj.strftime('%B %d, %Y')  # January 15, 2024
        elif format_type == 'iso':
            return date_obj.isoformat()  # 2024-01-15
        else:
            return date_obj.strftime('%b %d, %Y')  # Default to short
            
    except (ValueError, TypeError):
        return 'Invalid Date'


def normalize_reservation_dates(reservation_data: dict) -> dict:
    """
    Normalize reservation date fields to consistent format.
    
    This function handles the various field names used across different
    parts of the application and ensures consistent date-only format.
    
    Args:
        reservation_data: Dictionary containing reservation data
        
    Returns:
        Dictionary with normalized date fields
    """
    normalized = reservation_data.copy()
    
    # Map of possible field names to standard names
    date_field_mappings = {
        'startDate': ['startDate', 'StartDate', 'checkInDate', 'CheckInDate', 'start'],
        'endDate': ['endDate', 'EndDate', 'checkOutDate', 'CheckOutDate', 'end']
    }
    
    for standard_field, possible_fields in date_field_mappings.items():
        date_value = None
        
        # Find the first available field
        for field in possible_fields:
            if field in reservation_data and reservation_data[field]:
                date_value = reservation_data[field]
                break
        
        if date_value:
            try:
                normalized[standard_field] = to_date_only(date_value)
            except ValueError as e:
                print(f"Warning: Could not normalize {standard_field}: {e}")
                normalized[standard_field] = None
        else:
            normalized[standard_field] = None
    
    return normalized


def is_date_in_range(check_date: Union[str, datetime, date], 
                    start_date: Union[str, datetime, date], 
                    end_date: Union[str, datetime, date]) -> bool:
    """
    Check if a date falls within a date range (inclusive).
    
    Args:
        check_date: Date to check
        start_date: Start of range
        end_date: End of range
        
    Returns:
        True if check_date is within the range
    """
    try:
        check_date_str = to_date_only(check_date)
        start_date_str = to_date_only(start_date)
        end_date_str = to_date_only(end_date)
        
        return start_date_str <= check_date_str <= end_date_str
    except (ValueError, TypeError):
        return False


def get_current_date_string() -> str:
    """
    Get current date as a date-only string.
    
    Returns:
        Current date in YYYY-MM-DD format
    """
    return datetime.now(timezone.utc).date().isoformat()


def ensure_date_only_format(date_input: Union[str, datetime, date, None]) -> Optional[str]:
    """
    Ensure date is in date-only format (YYYY-MM-DD) regardless of input format.
    
    This function is specifically designed to handle reservation dates
    and prevent timezone issues by always returning date-only strings.
    
    Args:
        date_input: Any date input (datetime, date, string, or None)
        
    Returns:
        Date string in YYYY-MM-DD format or None if input is invalid/None
    """
    if date_input is None:
        return None
    
    try:
        return to_date_only(date_input)
    except (ValueError, TypeError):
        return None


def format_date_for_ui(date_input: Union[str, datetime, date, None]) -> str:
    """
    Format date specifically for UI display with consistent formatting.
    
    This ensures that dates display the same way regardless of user timezone
    by treating all reservation dates as date-only values.
    
    Args:
        date_input: Date to format
        
    Returns:
        Formatted date string for display (e.g., "Jan 15, 2024") or "Invalid Date"
    """
    if date_input is None:
        return "Invalid Date"
    
    try:
        date_only_str = ensure_date_only_format(date_input)
        if not date_only_str:
            return "Invalid Date"
        
        # Parse the date-only string and format for display
        date_obj = datetime.strptime(date_only_str, '%Y-%m-%d').date()
        return date_obj.strftime('%b %d, %Y')  # Jan 15, 2024
    except (ValueError, TypeError):
        return "Invalid Date"


def is_reservation_active(start_date: Union[str, datetime, date], 
                         end_date: Union[str, datetime, date]) -> bool:
    """
    Check if a reservation is currently active (guest is staying).
    
    Args:
        start_date: Reservation start date
        end_date: Reservation end date
        
    Returns:
        True if reservation is active today
    """
    today = get_current_date_string()
    return is_date_in_range(today, start_date, end_date)


def is_reservation_upcoming(start_date: Union[str, datetime, date]) -> bool:
    """
    Check if a reservation is upcoming (starts in the future).
    
    Args:
        start_date: Reservation start date
        
    Returns:
        True if reservation starts in the future
    """
    try:
        today = get_current_date_string()
        start_date_str = to_date_only(start_date)
        return start_date_str > today
    except (ValueError, TypeError):
        return False
