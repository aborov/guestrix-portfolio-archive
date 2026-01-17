import requests
from icalendar import Calendar
import re
from datetime import datetime, date, timezone
import traceback
import uuid

# --- Import Firestore client functions ---
from concierge.utils.firestore_client import (
    get_firestore_client,
    get_property,
    list_property_reservations,
    create_reservation,
    update_reservation,
    delete_reservation
)

# --- Import date utilities ---
from concierge.utils.date_utils import parse_ical_date, to_date_only

# --- Reservation Fetching Function ---
def fetch_and_parse_ical(url: str) -> list[dict]:
    """
    Fetches iCalendar data from a URL, parses it, and extracts reservation details.
    Filters out block-off records (like "Not available" entries) to only return real reservations.

    Args:
        url: The iCal URL to fetch data from.

    Returns:
        A list of dictionaries, where each dictionary represents a real reservation
        with 'summary', 'start', 'end', 'description', and 'phone_last_4' keys.
        Returns an empty list if fetching or parsing fails.
    """
    events = []
    if not url:
        print("[fetch_and_parse_ical] Error: No URL provided.")
        return events

    try:
        print(f"[fetch_and_parse_ical] Fetching data from: {url}")
        response = requests.get(url, timeout=15) # Add a timeout
        response.raise_for_status()  # Raise an error for bad status codes (4xx or 5xx)
        ical_data = response.text
        print(f"[fetch_and_parse_ical] Successfully fetched data (length: {len(ical_data)}).")

        calendar = Calendar.from_ical(ical_data)
        print(f"[fetch_and_parse_ical] Parsing calendar data...")

        count = 0
        filtered_count = 0
        for component in calendar.walk():
            if component.name == "VEVENT":
                count += 1
                start_dt = component.get("dtstart").dt if component.get("dtstart") else None
                end_dt = component.get("dtend").dt if component.get("dtend") else None
                description = component.get("description", "")
                summary = component.get("summary", "")

                # Convert dates to date-only format using utility function
                if start_dt:
                    try:
                        start_date_str = parse_ical_date(start_dt)
                    except ValueError as e:
                        print(f"Error parsing start date {start_dt}: {e}")
                        continue
                else:
                    continue

                if end_dt:
                    try:
                        end_date_str = parse_ical_date(end_dt)
                    except ValueError as e:
                        print(f"Error parsing end date {end_dt}: {e}")
                        continue
                else:
                    continue

                # Filter out block-off records and non-reservation entries
                if _is_block_off_record(summary):
                    filtered_count += 1
                    print(f"[fetch_and_parse_ical] Filtered out block-off record: '{summary}'")
                    continue

                # Attempt to extract last 4 digits of phone number from description
                phone_last_4 = None
                if description:
                    # Regex to find patterns like "Phone Number (Last 4 Digits): XXXX" or just 4 digits
                    match = re.search(r'Phone Number \(Last 4 Digits\):\s*(\d{4})', description)
                    if match:
                        phone_last_4 = match.group(1)
                    else:
                        # Fallback: look for any 4-digit sequence if specific text not found
                        match_fallback = re.search(r'\b(\d{4})\b', description)
                        if match_fallback:
                             # Be cautious with fallback, might match years etc. Add context check if needed.
                             # For now, assume any 4 digits might be the phone suffix.
                             phone_last_4 = match_fallback.group(1)

                event = {
                    "summary": summary,
                    "start": start_date_str,
                    "end": end_date_str,
                    "description": description,
                    "phone_last_4": phone_last_4
                }
                events.append(event)

        print(f"[fetch_and_parse_ical] Parsed {count} VEVENT components, filtered out {filtered_count} block-off records, found {len(events)} real reservations.")
        return events

    except requests.exceptions.RequestException as e:
        print(f"[fetch_and_parse_ical] Error fetching URL {url}: {e}")
        return []
    except Exception as e:
        print(f"[fetch_and_parse_ical] Error parsing iCal data from {url}: {e}")
        traceback.print_exc() # Print detailed traceback for parsing errors
        return []


def _is_block_off_record(summary: str) -> bool:
    """
    Determines if an iCal event is a block-off record rather than a real reservation.

    Args:
        summary: The event summary/title

    Returns:
        True if this appears to be a block-off record, False if it's likely a real reservation
    """
    if not summary:
        return True  # Events without summaries are likely not real reservations

    summary_lower = summary.lower()

    # Common patterns for block-off records
    block_off_patterns = [
        "not available",
        "blocked",
        "unavailable",
        "maintenance",
        "owner use",
        "personal use",
        "cleaning",
        "repair"
    ]

    # Check if summary contains block-off patterns (but be careful with "not available")
    for pattern in block_off_patterns:
        if pattern == "not available":
            # Be more specific with "not available" to avoid false positives
            continue  # Handle this separately below
        elif pattern in summary_lower:
            return True

    # Airbnb-specific patterns
    if "airbnb" in summary_lower and "not available" in summary_lower:
        return True

    # More specific "not available" patterns - avoid false positives
    if summary_lower == "not available" or summary_lower.endswith("(not available)"):
        return True

    # VRBO/other platform patterns (can be extended as needed)
    if summary_lower in ["blocked", "unavailable", "owner block"]:
        return True

    # If summary suggests it's a reservation but has no meaningful description,
    # it might still be a real reservation (some platforms have minimal descriptions)
    # So we're conservative here and only filter obvious block-offs

    return False
# --- End Reservation Fetching Function ---

# --- Background Job to Update Reservations using Firestore --- #
def update_all_reservations():
    """Fetches reservations for all properties with an iCal URL and updates Firestore."""
    print("[Scheduler] Running update_all_reservations job...")

    try:
        # Initialize Firestore
        db = get_firestore_client()
        if not db:
            print("[Scheduler] Error: Could not initialize Firestore.")
            return

        # Fetch all properties from Firestore
        properties_ref = db.collection('properties')
        properties = []

        # Get all properties with their document IDs
        for doc in properties_ref.stream():
            property_data = doc.to_dict()
            # Ensure the property has an ID (use document ID if not present in data)
            if 'id' not in property_data:
                property_data['id'] = doc.id
            properties.append(property_data)

        if not properties:
            print("[Scheduler] Error: No properties found in Firestore.")
            return

        updated_count = 0
        for property_data in properties:
            # Get property ID - this should be the Firestore document ID
            property_id = property_data.get('id')
            if not property_id:
                print("[Scheduler] Error: Invalid property ID format.")
                continue

            # Check if property is active - skip inactive properties
            property_status = property_data.get('status', 'active')
            if property_status != 'active':
                print(f"[Scheduler] Skipping inactive property {property_id} (status: {property_status})")
                continue

            # Get iCal URL from property data
            ical_url = property_data.get('icalUrl')

            if ical_url:
                print(f"[Scheduler] Processing property {property_id} with URL: {ical_url}")
                fetched_events = fetch_and_parse_ical(ical_url)

                if fetched_events is not None: # Check if fetch was successful (returned list, even if empty)
                    # 1. Get existing reservations for this property from Firestore
                    print(f"[Scheduler] Loading existing reservations for property {property_id}...")
                    existing_reservations = list_property_reservations(property_id)
                    existing_by_date = {}  # Dictionary to map date ranges to existing reservations

                    # Group existing reservations by dates and other identifying info for better matching
                    for reservation in existing_reservations:
                        start_date = reservation.get('startDate')
                        end_date = reservation.get('endDate')

                        if start_date and end_date:
                            # Create a key based on start and end dates
                            date_key = f"{start_date}_{end_date}"
                            reservation_id = reservation.get('id')
                            
                            # If multiple reservations exist for the same date range, store as a list
                            if date_key not in existing_by_date:
                                existing_by_date[date_key] = []
                            
                            existing_by_date[date_key].append({
                                'id': reservation_id,
                                'data': reservation
                            })

                    print(f"[Scheduler] Found {len(existing_reservations)} existing reservations for property {property_id}")

                    # 2. Process fetched events
                    print(f"[Scheduler] Processing {len(fetched_events)} fetched events for property {property_id}...")

                    # Keep track of processed reservations to identify ones to delete later
                    processed_ids = set()

                    updates_count = 0
                    added_count = 0

                    for event in fetched_events:
                        # Get date strings (already normalized by fetch_and_parse_ical)
                        start_date = event.get('start')
                        end_date = event.get('end')

                        if not (start_date and end_date):
                            print(f"[Scheduler] Skipping event for property {property_id} due to missing start/end dates. Event: {event}")
                            continue

                        # Create date key for matching
                        date_key = f"{start_date}_{end_date}"

                        # Check if this reservation already exists
                        matched_reservation = None
                        if date_key in existing_by_date:
                            # Find the best match among reservations with the same dates
                            candidates = existing_by_date[date_key]
                            
                            # Try to find exact match by summary and last 4 digits
                            for candidate in candidates:
                                candidate_data = candidate['data']
                                
                                # Check if summary matches (if both exist)
                                summary_match = (
                                    not event.get('summary') or 
                                    not candidate_data.get('summary') or 
                                    candidate_data.get('summary') == event.get('summary')
                                )
                                
                                # Check if last 4 digits match (if both exist)
                                phone_match = (
                                    not event.get('phone_last_4') or 
                                    not candidate_data.get('guestPhoneLast4') or 
                                    candidate_data.get('guestPhoneLast4') == event.get('phone_last_4')
                                )
                                
                                # If we have a good match, use this reservation
                                if summary_match and phone_match:
                                    matched_reservation = candidate
                                    break
                            
                            # If no exact match found, use the first candidate (most conservative approach)
                            if not matched_reservation and candidates:
                                matched_reservation = candidates[0]
                                print(f"[Scheduler] Using first candidate for date range {date_key} (no exact match found)")

                        if matched_reservation:
                            # Update existing reservation with new data from iCal
                            existing_data = matched_reservation['data']
                            reservation_id = matched_reservation['id']

                            # Mark as processed
                            processed_ids.add(reservation_id)
                            
                            # Remove this reservation from candidates to avoid double-processing
                            if date_key in existing_by_date:
                                existing_by_date[date_key] = [c for c in existing_by_date[date_key] if c['id'] != reservation_id]

                            # Preserve existing contact information
                            guest_phone_number = existing_data.get('guestPhoneNumber')
                            # Check multiple possible field names for additional contacts
                            additional_contacts = (
                                existing_data.get('additional_contacts') or
                                existing_data.get('additionalContacts') or
                                existing_data.get('AdditionalContacts') or
                                []
                            )
                            guest_name = existing_data.get('guestName')

                            # Check if any fields need updating - be conservative
                            update_needed = False
                            update_data = {}

                            # Only update fields from iCal that have actually changed and are meaningful
                            if event.get('summary') and existing_data.get('summary') != event.get('summary'):
                                update_data['summary'] = event.get('summary')
                                update_needed = True
                                print(f"[Scheduler] Summary changed for reservation {reservation_id}: '{existing_data.get('summary')}' -> '{event.get('summary')}'")

                            if event.get('description') and existing_data.get('description') != event.get('description'):
                                update_data['description'] = event.get('description')
                                update_needed = True
                                print(f"[Scheduler] Description changed for reservation {reservation_id}")

                            # Update last 4 digits only if we didn't have a full phone number already and the new value is different
                            if (not guest_phone_number and 
                                event.get('phone_last_4') and 
                                existing_data.get('guestPhoneLast4') != event.get('phone_last_4')):
                                update_data['guestPhoneLast4'] = event.get('phone_last_4')
                                update_needed = True
                                print(f"[Scheduler] Phone last 4 changed for reservation {reservation_id}: '{existing_data.get('guestPhoneLast4')}' -> '{event.get('phone_last_4')}'")

                            # Preserve additional contacts if they exist
                            if additional_contacts:
                                update_data['additional_contacts'] = additional_contacts
                                update_needed = True
                                print(f"[Scheduler] Preserving {len(additional_contacts)} additional contacts for reservation {reservation_id}")

                            # Preserve guest name if it exists
                            if guest_name:
                                update_data['guestName'] = guest_name

                            # Preserve guest phone number if it exists
                            if guest_phone_number:
                                update_data['guestPhoneNumber'] = guest_phone_number

                            # CRITICAL FIX: Always preserve existing dates to prevent them from being set to null
                            # This prevents the date normalization process from nullifying dates when only
                            # preserving additional contacts or other fields
                            update_data['startDate'] = existing_data.get('startDate')
                            update_data['endDate'] = existing_data.get('endDate')

                            # If no meaningful changes detected, skip the update entirely
                            if not update_needed:
                                print(f"[Scheduler] No changes detected for reservation {reservation_id}, skipping update")
                                continue

                            # Add update timestamp
                            update_data['updatedAt'] = datetime.now(timezone.utc)

                            if update_needed:
                                # Use the update_reservation function to update the reservation
                                update_reservation(reservation_id, update_data)
                                updates_count += 1
                                print(f"[Scheduler] Updated reservation {reservation_id} for property {property_id}")
                        else:
                            # This is a new reservation
                            reservation_data = {
                                'propertyId': property_id,
                                'startDate': start_date,
                                'endDate': end_date,
                                'summary': event.get('summary'),
                                'description': event.get('description'),
                                'guestPhoneLast4': event.get('phone_last_4'),
                                'status': 'active',
                                'createdAt': datetime.now(timezone.utc),
                                'updatedAt': datetime.now(timezone.utc)
                            }

                            # Create new reservation in Firestore
                            new_id = create_reservation(reservation_data)
                            if new_id:
                                added_count += 1
                                print(f"[Scheduler] Added new reservation {new_id} for property {property_id}")

                    # 3. Handle reservations to delete (those not in the fetched events)
                    # Be very conservative - only delete if we're sure they're no longer valid
                    deleted_count = 0
                    preserved_count = 0
                    
                    for reservation in existing_reservations:
                        reservation_id = reservation.get('id')
                        if reservation_id and reservation_id not in processed_ids:
                            # Check if this reservation has custom contact info that should be preserved
                            # Check multiple possible field names for additional contacts
                            additional_contacts_to_check = (
                                reservation.get('additional_contacts') or
                                reservation.get('additionalContacts') or
                                reservation.get('AdditionalContacts') or
                                []
                            )
                            has_custom_contacts = (
                                reservation.get('guestPhoneNumber') or
                                (additional_contacts_to_check and len(additional_contacts_to_check) > 0)
                            )

                            # Also check if this reservation is in the future - be more conservative about deleting future reservations
                            is_future_reservation = False
                            try:
                                start_date_str = reservation.get('startDate')
                                if start_date_str:
                                    # Parse the date string and ensure it has timezone information
                                    if 'T' in start_date_str and start_date_str.endswith('Z'):
                                        # Handle ISO format with Z suffix
                                        start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
                                    elif 'T' in start_date_str:
                                        # Handle ISO format, add UTC timezone if missing
                                        try:
                                            start_date = datetime.fromisoformat(start_date_str)
                                            if start_date.tzinfo is None:
                                                start_date = start_date.replace(tzinfo=timezone.utc)
                                        except ValueError:
                                            # Fallback: parse as date-only and assume midnight UTC
                                            date_only = datetime.strptime(start_date_str.split('T')[0], '%Y-%m-%d')
                                            start_date = date_only.replace(tzinfo=timezone.utc)
                                    else:
                                        # Handle date-only format (YYYY-MM-DD)
                                        date_only = datetime.strptime(start_date_str, '%Y-%m-%d')
                                        start_date = date_only.replace(tzinfo=timezone.utc)
                                    
                                    now = datetime.now(timezone.utc)
                                    is_future_reservation = start_date > now
                            except Exception as date_err:
                                print(f"[Scheduler] Error parsing date for reservation {reservation_id}: {date_err}")
                                # If we can't parse the date, assume it's future to be safe
                                is_future_reservation = True

                            # Only delete if:
                            # 1. No custom contacts
                            # 2. Not a future reservation (or we couldn't determine the date)
                            # 3. The reservation is clearly outdated
                            should_preserve = (
                                has_custom_contacts or 
                                is_future_reservation
                            )

                            if should_preserve:
                                preserved_count += 1
                                if has_custom_contacts:
                                    print(f"[Scheduler] Preserving reservation {reservation_id} with custom contacts for property {property_id}")
                                if is_future_reservation:
                                    print(f"[Scheduler] Preserving future reservation {reservation_id} for property {property_id}")
                            else:
                                # Use the delete_reservation function to delete the reservation
                                delete_reservation(reservation_id)
                                deleted_count += 1
                                print(f"[Scheduler] Deleted past reservation {reservation_id} for property {property_id}")

                    print(f"[Scheduler] Reservation sync complete for property {property_id}: {updates_count} updated, {added_count} added, {deleted_count} deleted, {preserved_count} preserved")
                    updated_count += 1
                else:
                    print(f"[Scheduler] Failed to fetch or parse iCal data for property {property_id}.")

        print(f"[Scheduler] update_all_reservations job finished. Processed {updated_count} properties with URLs.")

    except Exception as e:
        print(f"[Scheduler] Error in update_all_reservations job: {e}")
        traceback.print_exc()
# --- End Background Job --- #

# --- Single Property Reservation Sync Function ---
def sync_property_reservations(property_id: str, ical_url: str = None) -> dict:
    """
    Syncs reservations for a single property from its iCal URL.
    
    Args:
        property_id: The property ID to sync reservations for
        ical_url: Optional iCal URL. If not provided, will get from property data
        
    Returns:
        Dictionary with sync results: {'success': bool, 'stats': {...}, 'error': str}
    """
    try:
        print(f"[sync_property_reservations] Starting sync for property {property_id}")
        
        # Get iCal URL if not provided
        if not ical_url:
            property_data = get_property(property_id)
            if not property_data:
                return {'success': False, 'error': 'Property not found'}

            # Check if property is active
            property_status = property_data.get('status', 'active')
            if property_status != 'active':
                return {'success': False, 'error': f'Property is inactive (status: {property_status}). Only active properties can sync reservations.'}

            ical_url = property_data.get('icalUrl')
            if not ical_url:
                return {'success': False, 'error': 'Property does not have an iCal URL configured'}
        
        # Fetch events from iCal
        print(f"[sync_property_reservations] Fetching events from: {ical_url}")
        fetched_events = fetch_and_parse_ical(ical_url)
        
        if fetched_events is None:
            return {'success': False, 'error': 'Failed to fetch or parse iCal data'}
        
        # Get existing reservations for this property
        existing_reservations = list_property_reservations(property_id)
        existing_by_date = {}
        
        # Group existing reservations by dates for easier matching
        for reservation in existing_reservations:
            start_date = reservation.get('startDate')
            end_date = reservation.get('endDate')
            
            if start_date and end_date:
                date_key = f"{start_date}_{end_date}"
                reservation_id = reservation.get('id')
                existing_by_date[date_key] = {
                    'id': reservation_id,
                    'data': reservation
                }
        
        # Process fetched events
        processed_ids = set()
        updates_count = 0
        added_count = 0
        
        for event in fetched_events:
            start_date = event.get('start')
            end_date = event.get('end')
            
            if not (start_date and end_date):
                continue
            
            date_key = f"{start_date}_{end_date}"
            
            # Check if this reservation already exists
            if date_key in existing_by_date:
                # Update existing reservation
                existing_item = existing_by_date[date_key]
                existing_data = existing_item['data']
                reservation_id = existing_item['id']
                
                processed_ids.add(reservation_id)
                
                # Preserve existing contact information
                guest_phone_number = existing_data.get('guestPhoneNumber')
                additional_contacts = (
                    existing_data.get('additional_contacts') or
                    existing_data.get('additionalContacts') or
                    existing_data.get('AdditionalContacts') or
                    []
                )
                guest_name = existing_data.get('guestName')
                
                # Check if any fields need updating
                update_needed = False
                update_data = {}
                
                if existing_data.get('summary') != event.get('summary'):
                    update_data['summary'] = event.get('summary')
                    update_needed = True
                
                if existing_data.get('description') != event.get('description'):
                    update_data['description'] = event.get('description')
                    update_needed = True
                
                if not guest_phone_number and event.get('phone_last_4') and existing_data.get('guestPhoneLast4') != event.get('phone_last_4'):
                    update_data['guestPhoneLast4'] = event.get('phone_last_4')
                    update_needed = True
                
                # Preserve additional contacts if they exist
                if additional_contacts:
                    update_data['additional_contacts'] = additional_contacts
                    update_needed = True
                
                # Preserve guest name if it exists
                if guest_name:
                    update_data['guestName'] = guest_name
                
                # Preserve guest phone number if it exists
                if guest_phone_number:
                    update_data['guestPhoneNumber'] = guest_phone_number
                
                # Always preserve existing dates to prevent them from being set to null
                update_data['startDate'] = existing_data.get('startDate')
                update_data['endDate'] = existing_data.get('endDate')
                
                # Add update timestamp
                update_data['updatedAt'] = datetime.now(timezone.utc)
                
                if update_needed:
                    update_reservation(reservation_id, update_data)
                    updates_count += 1
            else:
                # This is a new reservation
                reservation_data = {
                    'propertyId': property_id,
                    'startDate': start_date,
                    'endDate': end_date,
                    'summary': event.get('summary'),
                    'description': event.get('description'),
                    'guestPhoneLast4': event.get('phone_last_4'),
                    'status': 'active',
                    'createdAt': datetime.now(timezone.utc),
                    'updatedAt': datetime.now(timezone.utc)
                }
                
                new_id = create_reservation(reservation_data)
                if new_id:
                    added_count += 1
        
        # Handle reservations to delete (those not in the fetched events)
        deleted_count = 0
        for reservation in existing_reservations:
            reservation_id = reservation.get('id')
            if reservation_id and reservation_id not in processed_ids:
                # Check if this reservation has custom contact info that should be preserved
                additional_contacts_to_check = (
                    reservation.get('additional_contacts') or
                    reservation.get('additionalContacts') or
                    reservation.get('AdditionalContacts') or
                    []
                )
                has_custom_contacts = (
                    reservation.get('guestPhoneNumber') or
                    (additional_contacts_to_check and len(additional_contacts_to_check) > 0)
                )
                
                if not has_custom_contacts:
                    delete_reservation(reservation_id)
                    deleted_count += 1
        
        print(f"[sync_property_reservations] Sync complete for property {property_id}: {updates_count} updated, {added_count} added, {deleted_count} deleted")
        
        return {
            'success': True,
            'stats': {
                'updated': updates_count,
                'added': added_count,
                'deleted': deleted_count,
                'total_events': len(fetched_events)
            }
        }
        
    except Exception as e:
        print(f"[sync_property_reservations] Error syncing reservations for property {property_id}: {e}")
        traceback.print_exc()
        return {'success': False, 'error': str(e)}
# --- End Single Property Reservation Sync Function ---