#!/usr/bin/env python3
"""
Property data schema definitions for the new setup process.

This module defines the structure for property data including the new amenities format
and validation functions for the multi-step setup process.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime

# Default amenities structure
DEFAULT_AMENITIES = {
    "basic": [],
    "appliances": []
}

# Default property structure for new imports
DEFAULT_PROPERTY_STRUCTURE = {
    "name": "",
    "address": "",
    "description": "",
    "hostId": "",
    "status": "inactive",
    "new": True,  # Flag for new properties requiring setup
    "icalUrl": "",
    "checkInTime": "15:00",
    "checkOutTime": "11:00",
    "wifiDetails": {
        "network": "",
        "password": ""
    },
    "amenities": DEFAULT_AMENITIES,
    "houseRules": [],  # Will be populated with default rules during setup
    "airbnbListingUrl": "",
    "importData": {
        "extractedAt": None,
        "source": "airbnb",
        "rawData": {}
    },
    "setupProgress": {
        "step1_basic": False,
        "step2_rules": False,
        "step3_emergency": False,
        "step4_facts": False,
        "step5_review": False
    },
    "createdAt": None,
    "updatedAt": None
}

# Property Facts questions based on onboarding CSV
PROPERTY_FACTS_QUESTIONS = [
    {
        "id": "special_features",
        "question": "What makes your property special?",
        "placeholder": "Describe unique features, views, or amenities that set your property apart...",
        "type": "information"
    },
    {
        "id": "neighborhood_info",
        "question": "What should guests know about the neighborhood?",
        "placeholder": "Describe the area, noise level, local character, nearby attractions...",
        "type": "information"
    },
    {
        "id": "bedding_configuration",
        "question": "What's the bedding configuration in each room?",
        "placeholder": "Describe beds in each room (e.g., Master: 1 King, Guest: 2 Twins)...",
        "type": "information"
    },
    {
        "id": "transportation",
        "question": "What's the best way to get around the area?",
        "placeholder": "Public transport, parking, ride-sharing, walking distance to attractions...",
        "type": "information"
    },
    {
        "id": "local_tips",
        "question": "Any local tips or recommendations you'd like to share?",
        "placeholder": "Hidden gems, local favorites, things to avoid, seasonal considerations...",
        "type": "places"
    },
    {
        "id": "property_quirks",
        "question": "Are there any quirks or things guests should be careful about?",
        "placeholder": "Stairs, low ceilings, sensitive neighbors, tricky locks, etc...",
        "type": "instruction"
    }
]

# Default house rules
DEFAULT_HOUSE_RULES = [
    {
        "id": "no_smoking",
        "title": "No smoking",
        "description": "Smoking is not allowed anywhere on the property",
        "enabled": True,
        "type": "rule"
    },
    {
        "id": "no_parties",
        "title": "No parties or events",
        "description": "Parties and events are not permitted",
        "enabled": True,
        "type": "rule"
    },
    {
        "id": "quiet_hours",
        "title": "Quiet hours",
        "description": "Please keep noise to a minimum between 10 PM and 8 AM",
        "enabled": True,
        "type": "rule"
    },
    {
        "id": "no_pets",
        "title": "No pets",
        "description": "Pets are not allowed unless specifically approved",
        "enabled": False,
        "type": "rule"
    },
    {
        "id": "check_in_time",
        "title": "Check-in time",
        "description": "Check-in is available from 3:00 PM onwards",
        "enabled": True,
        "type": "rule"
    },
    {
        "id": "check_out_time",
        "title": "Check-out time",
        "description": "Check-out is required by 11:00 AM",
        "enabled": True,
        "type": "rule"
    },
    {
        "id": "max_occupancy",
        "title": "Maximum occupancy",
        "description": "Property accommodates a maximum of [X] guests",
        "enabled": True,
        "type": "rule"
    }
]

# Default emergency information
DEFAULT_EMERGENCY_INFO = [
    {
        "id": "emergency_contact",
        "title": "Emergency contact information",
        "description": "How to contact the host in case of emergency",
        "content": "",
        "enabled": False,
        "type": "emergency"
    },
    {
        "id": "water_shutoff",
        "title": "Water main shut-off location",
        "description": "Where to find the water main shut-off valve",
        "content": "",
        "enabled": False,
        "type": "emergency"
    },
    {
        "id": "electrical_panel",
        "title": "Electrical panel location",
        "description": "Where to find the electrical panel/circuit breaker",
        "content": "",
        "enabled": False,
        "type": "emergency"
    },
    {
        "id": "fire_extinguisher",
        "title": "Fire extinguisher location",
        "description": "Where to find fire extinguisher and how to use it",
        "content": "",
        "enabled": False,
        "type": "emergency"
    },
    {
        "id": "first_aid",
        "title": "First aid kit location",
        "description": "Where to find the first aid kit",
        "content": "",
        "enabled": False,
        "type": "emergency"
    },
    {
        "id": "nearest_hospital",
        "title": "Nearest hospital/pharmacy",
        "description": "Location and contact information for nearest medical facilities",
        "content": "",
        "enabled": False,
        "type": "emergency"
    }
]

def validate_amenities_structure(amenities: Dict) -> bool:
    """
    Validate the amenities structure.
    
    Args:
        amenities: Amenities dictionary to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(amenities, dict):
        return False
    
    # Check required keys
    if 'basic' not in amenities or 'appliances' not in amenities:
        return False
    
    # Validate basic amenities
    if not isinstance(amenities['basic'], list):
        return False
    
    # Validate appliances
    if not isinstance(amenities['appliances'], list):
        return False
    
    # Validate appliance structure
    for appliance in amenities['appliances']:
        if not isinstance(appliance, dict):
            return False
        
        required_fields = ['name']
        for field in required_fields:
            if field not in appliance:
                return False
    
    return True

def create_appliance_entry(name: str, location: str = "", brand: str = "", model: str = "") -> Dict:
    """
    Create a properly structured appliance entry.
    
    Args:
        name: Name of the appliance
        location: Location in the property
        brand: Brand name
        model: Model number
        
    Returns:
        Appliance dictionary
    """
    return {
        "name": name,
        "location": location,
        "brand": brand,
        "model": model
    }

def validate_property_structure(property_data: Dict) -> List[str]:
    """
    Validate property data structure and return list of validation errors.
    
    Args:
        property_data: Property data to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    # Check required fields
    required_fields = ['name', 'hostId', 'status']
    for field in required_fields:
        if field not in property_data or not property_data[field]:
            errors.append(f"Missing required field: {field}")
    
    # Validate amenities if present
    if 'amenities' in property_data:
        if not validate_amenities_structure(property_data['amenities']):
            errors.append("Invalid amenities structure")
    
    # Validate setup progress if present
    if 'setupProgress' in property_data:
        setup_progress = property_data['setupProgress']
        if not isinstance(setup_progress, dict):
            errors.append("Invalid setupProgress structure")
        else:
            expected_steps = ['step1_basic', 'step2_rules', 'step3_emergency', 'step4_facts', 'step5_review']
            for step in expected_steps:
                if step not in setup_progress:
                    errors.append(f"Missing setup progress step: {step}")
    
    return errors

def get_default_property_data(host_id: str, listing_url: str = "") -> Dict:
    """
    Get default property data structure for a new property.

    Args:
        host_id: ID of the host creating the property
        listing_url: Airbnb listing URL (required for duplicate prevention)

    Returns:
        Default property data dictionary
    """
    property_data = DEFAULT_PROPERTY_STRUCTURE.copy()
    property_data['hostId'] = host_id
    property_data['airbnbListingUrl'] = listing_url  # Store for duplicate prevention
    property_data['createdAt'] = datetime.now().isoformat()
    property_data['updatedAt'] = datetime.now().isoformat()

    return property_data
