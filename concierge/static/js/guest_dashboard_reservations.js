/*
 * Reservation functionality for the guest dashboard
 */

import {
    dashboardState,
    getConfirmedPropertyId,
    setConfirmedPropertyId,
    fetchPropertyDetails,
    shouldAllowTestProperties,
    fetchPropertyKnowledgeItems
} from './guest_dashboard_utils.js';

// --- Reservation Globals ---
let currentReservations = [];
let currentPropertyIndex = 0;
let isLoadingReservations = false;
let isLoadingPropertyDetails = false;
let storedPropertyDetails = {}; // Cache for property details

// --- Reservation Loading ---
async function loadReservations() {
    console.log("Loading reservations...");

    if (isLoadingReservations) {
        console.log("Already loading reservations, skipping.");
        return;
    }

    // Update loading state in both local and shared state
    isLoadingReservations = true;
    dashboardState.isLoadingReservations = true;

    // Show loading spinner and hide any existing reservation cards
    showLoadingSpinner(true);

    // Hide any existing reservation cards while loading
    const reservationsContainer = document.getElementById('reservations-container');
    if (reservationsContainer) {
        reservationsContainer.style.display = 'none';
    }

    try {
        // Get the user's phone number and ID
        const phoneNumber = window.PHONE_NUMBER || '';
        const userId = window.CURRENT_USER_ID || '';

        if (!userId && !phoneNumber) {
            console.warn("No user ID or phone number available for reservation lookup.");
            throw new Error("User identification missing. Please log in again.");
        }

        // Call the API to get reservations - prefer user ID if available
        let apiUrl;
        if (userId) {
            apiUrl = `/api/reservations/${userId}`;
            console.log("Using user ID for reservation lookup:", userId);
        } else {
            apiUrl = `/api/reservations?phone=${encodeURIComponent(phoneNumber)}`;
            console.log("Using phone number for reservation lookup:", phoneNumber);
        }

        console.log("Calling reservations API endpoint:", apiUrl);
        const response = await fetch(apiUrl);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log("Reservations API response:", data);

        if (data.success && data.reservations && Array.isArray(data.reservations)) {
            // Filter out test properties if not in development mode
            const allowTestProperties = shouldAllowTestProperties();
            const filteredReservations = allowTestProperties
                ? data.reservations
                : data.reservations.filter(res => !isTestProperty(res.propertyId));

            // Normalize reservation data to ensure consistent field names
            const normalizedReservations = filteredReservations.map(res => normalizeReservation(res));

            // Sort reservations by date (active first, then upcoming, then past)
            const sortedReservations = sortReservationsByDate(normalizedReservations);

            // Store the reservations in our centralized state
            dashboardState.reservations = sortedReservations;

            // For backward compatibility
            currentReservations = sortedReservations;

            // If we have reservations, determine which one should be active
            if (currentReservations.length > 0) {
                // Get the current confirmed property ID (if any)
                const confirmedId = getConfirmedPropertyId();

                // Try to find the index of the reservation with the confirmed property ID
                let targetIndex = -1;
                let finalPropertyId = null;

                if (confirmedId) {
                    // If we have a confirmed property ID, try to find a matching reservation
                    targetIndex = currentReservations.findIndex(res => res.propertyId === confirmedId);

                    // If we found a match, use that property ID
                    if (targetIndex !== -1) {
                        finalPropertyId = confirmedId;
                    }
                }

                // If no match found or no confirmed ID, use the first active or upcoming reservation
                if (targetIndex === -1) {
                    console.log("No reservation found matching confirmed property ID, selecting best reservation based on dates");

                    const now = new Date();

                    // First priority: Find active reservations (current stay)
                    const activeReservations = currentReservations.filter(res => {
                        const startDate = new Date(res.startDate);
                        const endDate = new Date(res.endDate);
                        return startDate <= now && endDate >= now;
                    });

                    if (activeReservations.length > 0) {
                        console.log("Found active reservations (current stay):", activeReservations.length);
                        // If multiple active reservations, use the one with the latest end date
                        activeReservations.sort((a, b) => new Date(b.endDate) - new Date(a.endDate));
                        targetIndex = currentReservations.findIndex(res => res.id === activeReservations[0].id);
                        finalPropertyId = activeReservations[0].propertyId;
                    } else {
                        // Second priority: Find upcoming reservations
                        const upcomingReservations = currentReservations.filter(res => {
                            const startDate = new Date(res.startDate);
                            return startDate > now;
                        });

                        if (upcomingReservations.length > 0) {
                            console.log("Found upcoming reservations:", upcomingReservations.length);
                            // Sort by start date to find the earliest upcoming one
                            upcomingReservations.sort((a, b) => new Date(a.startDate) - new Date(b.startDate));
                            targetIndex = currentReservations.findIndex(res => res.id === upcomingReservations[0].id);
                            finalPropertyId = upcomingReservations[0].propertyId;
                        } else {
                            // Last resort: Use the most recent past reservation
                            console.log("No active or upcoming reservations found, using most recent past reservation");
                            const pastReservations = [...currentReservations]; // Create a copy
                            pastReservations.sort((a, b) => new Date(b.endDate) - new Date(a.endDate));
                            targetIndex = currentReservations.findIndex(res => res.id === pastReservations[0].id);
                            finalPropertyId = pastReservations[0].propertyId;
                        }
                    }

                    // Fallback if something went wrong with the logic above
                    if (targetIndex === -1) {
                        console.warn("Failed to find a suitable reservation with date logic, defaulting to first reservation");
                        targetIndex = 0;
                        finalPropertyId = currentReservations[0].propertyId;
                    }
                }

                // Update the current property index
                currentPropertyIndex = targetIndex;
                console.log(`Setting current property index to ${currentPropertyIndex}`);

                // Get the selected reservation
                const selectedReservation = currentReservations[currentPropertyIndex];

                // Update the current reservation in our state
                dashboardState.currentReservation = selectedReservation;

                // For backward compatibility
                window.currentReservation = selectedReservation;

                // Set the confirmed property ID to the selected reservation's property ID if needed
                // Only set the property ID once to avoid multiple property changes
                if (finalPropertyId && finalPropertyId !== getConfirmedPropertyId()) {
                    console.log(`Setting confirmed property ID to ${finalPropertyId}`);
                    setConfirmedPropertyId(finalPropertyId);
                } else {
                    console.log(`Keeping existing property ID: ${getConfirmedPropertyId()}`);
                }

                // Collect all unique property IDs from reservations
                const propertyIds = new Set(currentReservations.map(res => res.propertyId));
                console.log(`Prefetching details for ${propertyIds.size} properties`);

                // Start with the selected property to ensure it loads first
                await fetchPropertyDetails(finalPropertyId || selectedReservation.propertyId, true);

                // Then load the rest in the background
                for (const pid of propertyIds) {
                    if (pid !== (finalPropertyId || selectedReservation.propertyId)) {
                        fetchPropertyDetails(pid, false).catch(err => {
                            console.warn(`Error prefetching property ${pid}:`, err);
                        });
                    }
                }

                // Now render the reservations
                renderReservationCards(currentReservations);

                // Update the UI to show the selected property
                updateSelectedPropertyUI();
            } else {
                console.log("No reservations found after filtering.");
                showNoReservationsMessage();
            }
        } else {
            console.warn("No reservations returned or API error:", data);
            dashboardState.errors.reservations = "No reservations found";
            showNoReservationsMessage();
        }
    } catch (error) {
        console.error("Error loading reservations:", error);
        dashboardState.errors.reservations = error.message;
        showErrorMessage(`Error loading reservations: ${error.message}`);
    } finally {
        // Update loading state in both local and shared state
        isLoadingReservations = false;
        dashboardState.isLoadingReservations = false;
        showLoadingSpinner(false);

        // Show the reservations container if we have reservations
        if (reservationsContainer && currentReservations.length > 0) {
            reservationsContainer.style.display = 'block';
        }
    }
}

// Helper function to normalize reservation data
function normalizeReservation(reservation) {
    // Create a normalized object with consistent field names
    return {
        id: reservation.id || reservation.Id || reservation.reservationId || reservation.ReservationId,
        propertyId: reservation.propertyId || reservation.PropertyId || reservation.property_id,
        propertyName: reservation.propertyName || reservation.PropertyName || reservation.property_name || "Property",
        propertyAddress: reservation.propertyAddress || reservation.PropertyAddress || reservation.property_address || "",
        startDate: reservation.startDate || reservation.StartDate || reservation.checkInDate || reservation.CheckInDate,
        endDate: reservation.endDate || reservation.EndDate || reservation.checkOutDate || reservation.CheckOutDate,
        guestName: reservation.guestName || reservation.GuestName || reservation.guest_name || "",
        guestPhoneNumber: reservation.guestPhoneNumber || reservation.GuestPhoneNumber || reservation.guest_phone_number || "",
        guestPhoneLast4: reservation.guestPhoneLast4 || reservation.GuestPhoneLast4 || "",
        status: reservation.status || reservation.Status || "active",
        summary: reservation.summary || reservation.Summary || "",
        description: reservation.description || reservation.Description || "",
        additionalContacts: reservation.additionalContacts || reservation.AdditionalContacts ||
                           reservation.additional_contacts || [],
        createdAt: reservation.createdAt || reservation.CreatedAt || reservation.created_at || "",
        updatedAt: reservation.updatedAt || reservation.UpdatedAt || reservation.updated_at || ""
    };
}

// Helper function to sort reservations by date
function sortReservationsByDate(reservations) {
    // Use the centralized date utilities
    return window.DateUtils.sortReservationsByDate(reservations);
}

// --- Property Details Loading ---
async function loadPropertyDetails(propertyId) {
    console.log(`Loading property details for property ID: ${propertyId}`);

    if (isLoadingPropertyDetails) {
        console.log("Already loading property details, skipping.");
        return;
    }

    isLoadingPropertyDetails = true;
    showLoadingSpinner(true);

    try {
        // Check if we already have this property in the cache
        if (storedPropertyDetails[propertyId]) {
            console.log("Using cached property details:", storedPropertyDetails[propertyId]);
            updatePropertyInfo(storedPropertyDetails[propertyId]);

            // Set the confirmed property ID using the setter function
            setConfirmedPropertyId(propertyId);

            // Check if chat button can be enabled
            if (typeof checkAndEnableChatButton === 'function') {
                checkAndEnableChatButton();
            }

            isLoadingPropertyDetails = false;
            showLoadingSpinner(false);
            return;
        }

        // Fetch property details
        const propertyDetails = await fetchPropertyDetails(propertyId, true);

        if (propertyDetails) {
            console.log("Property details loaded:", propertyDetails);

            // Cache the property details
            storedPropertyDetails[propertyId] = propertyDetails;

            // Update the UI with property details
            updatePropertyInfo(propertyDetails);

            // Set the confirmed property ID using the setter function
            setConfirmedPropertyId(propertyId);

            // Check if chat button can be enabled
            if (typeof checkAndEnableChatButton === 'function') {
                checkAndEnableChatButton();
            }
        } else {
            console.warn("No property details returned.");
            showErrorMessage("Error loading property details. Please try again later.");
        }
    } catch (error) {
        console.error("Error loading property details:", error);
        showErrorMessage("Error loading property details. Please try again later.");
    } finally {
        isLoadingPropertyDetails = false;
        showLoadingSpinner(false);
    }
}

// --- Reservation Card Rendering ---
function renderReservationCards(reservations) {
    console.log("Rendering reservation cards:", reservations);

    const reservationsContainer = document.getElementById('reservations-container');
    if (!reservationsContainer) {
        console.log("Guest dashboard uses modal-based reservations, skipping main container rendering.");
        // For guest dashboard, we don't render main reservation cards - only modal content
        return;
    }

    // Clear existing cards
    reservationsContainer.innerHTML = '';

    if (reservations.length === 0) {
        showNoReservationsMessage();
        return;
    }

    // Create a card for each reservation
    reservations.forEach((reservation, index) => {
        const card = createReservationCard(reservation, index);
        reservationsContainer.appendChild(card);
    });

    // Show the reservations container
    reservationsContainer.style.display = 'block';

    // Hide the no reservations message
    const noReservationsContainer = document.getElementById('no-reservations');
    if (noReservationsContainer) {
        noReservationsContainer.style.display = 'none';
    }
}

// --- Create Reservation Card ---
function createReservationCard(reservation, index) {
    const card = document.createElement('div');
    card.className = 'card mb-3 reservation-card shadow-sm';
    card.dataset.propertyId = reservation.propertyId;
    card.dataset.index = index;
    card.dataset.reservationId = reservation.id;

    // Format dates - use centralized date utilities for consistent display
    let formattedStartDate = window.DateUtils.formatDateForDisplay(reservation.startDate);
    let formattedEndDate = window.DateUtils.formatDateForDisplay(reservation.endDate);

    // Determine reservation status using centralized utilities
    const status = window.DateUtils.getReservationStatus(reservation.startDate, reservation.endDate);
    const statusBadge = `<span class="badge ${status.class}">${status.text}</span>`;
    
    // Apply appropriate card styling based on status
    if (status.text === 'Active') {
        card.classList.add('border-success');
    } else if (status.text === 'Past') {
        card.classList.add('text-muted');
    }

    // Get property details from cache if available
    let propertyName = null;
    let propertyAddress = null;
    let detailsLoaded = false;

    // First check if we have real property details in the cache
    if (dashboardState.propertyCache[reservation.propertyId]) {
        const cachedProperty = dashboardState.propertyCache[reservation.propertyId];

        // Check if the cached details look valid
        if (cachedProperty.name && cachedProperty.name !== "Property" &&
            !cachedProperty.name.includes("House") &&
            cachedProperty.address && cachedProperty.address !== "123 Beach Avenue") {

            propertyName = cachedProperty.name;
            propertyAddress = cachedProperty.address;
            detailsLoaded = true;
            console.log(`Using cached property details for ${reservation.propertyId}: ${propertyName}, ${propertyAddress}`);
        } else {
            console.warn(`Cached property details for ${reservation.propertyId} look like placeholder values, will fetch fresh data`);
        }
    }

    // If we don't have valid details from cache, create temporary property info
    if (!detailsLoaded) {
        // First try to get meaningful info from the reservation itself, without using obvious placeholders
        if (reservation.propertyName && !reservation.propertyName.includes("House") && reservation.propertyName !== "Property") {
            propertyName = reservation.propertyName;
            console.log(`Using non-placeholder property name from reservation: ${propertyName}`);
        } else {
            // Create a temporary name from property ID
            propertyName = `Property ${reservation.propertyId.substring(0, 6)}...`;
            console.log(`Created temporary property name from ID: ${propertyName}`);
        }

        if (reservation.propertyAddress && reservation.propertyAddress !== "123 Beach Avenue" && reservation.propertyAddress !== "") {
            propertyAddress = reservation.propertyAddress;
            console.log(`Using non-placeholder address from reservation: ${propertyAddress}`);
        } else {
            propertyAddress = "Loading address...";
        }

        // Don't use placeholder values for display, but show loading indicator
        const displayName = propertyName.includes("Property") ? "Loading property details..." : propertyName;
        const displayAddress = propertyAddress === "Loading address..." ? "Address loading..." : propertyAddress;

        propertyName = displayName;
        propertyAddress = displayAddress;

        // Trigger a fetch of property details to update the card later
        fetchPropertyDetails(reservation.propertyId, false, true)  // Force refresh
            .then(details => {
                if (details) {
                    updatePropertyCardInfo(reservation.propertyId, details.name, details.address);
                } else {
                    // If API fails, at least show something meaningful
                    const fallbackName = `Property ${reservation.propertyId.substring(0, 6)}`;
                    updatePropertyCardInfo(reservation.propertyId, fallbackName, "Address unavailable");
                }
            })
            .catch(err => {
                console.warn(`Error fetching property details for ${reservation.propertyId}:`, err);
                // Still update with fallback values on error
                const fallbackName = `Property ${reservation.propertyId.substring(0, 6)}`;
                updatePropertyCardInfo(reservation.propertyId, fallbackName, "Address unavailable");
            });
    }

    // Create unique IDs for property info elements so we can update them later
    const titleId = `property-title-${reservation.propertyId}`;
    const addressId = `property-address-${reservation.propertyId}`;

    // Check for additional contacts
    let contactsHtml = '';
    if (reservation.additionalContacts && reservation.additionalContacts.length > 0) {
        contactsHtml = '<div class="mt-2 small"><strong>Additional Contacts:</strong><ul class="list-unstyled mb-0">';
        for (const contact of reservation.additionalContacts) {
            const contactName = contact.name || 'Guest';
            const contactPhone = contact.phone || 'No phone';
            contactsHtml += `<li>${contactName}: ${contactPhone}</li>`;
        }
        contactsHtml += '</ul></div>';
    }

    // Create card content
    card.innerHTML = `
        <div class="card-header d-flex justify-content-between align-items-center">
            <h5 id="${titleId}" class="card-title mb-0 property-name">${propertyName || 'Property'}</h5>
            ${statusBadge}
        </div>
        <div class="card-body">
            <p id="${addressId}" class="card-subtitle mb-2 text-muted property-address">${propertyAddress || 'Address loading...'}</p>
            <div class="row mb-3">
                <div class="col-6">
                    <strong>Check-in:</strong><br>
                    ${formattedStartDate}
                </div>
                <div class="col-6">
                    <strong>Check-out:</strong><br>
                    ${formattedEndDate}
                </div>
            </div>
            ${contactsHtml}
            <div class="mt-3" id="select-button-container-${index}">
                <button class="btn btn-primary select-property-btn" data-index="${index}">
                    Select
                </button>
            </div>
        </div>
    `;

    // Get the current confirmed property ID
    const confirmedId = getConfirmedPropertyId();

    // Add active class to the current property
    // Check both the index and the property ID to ensure correct highlighting
    if (index === currentPropertyIndex || reservation.propertyId === confirmedId) {
        card.classList.add('active');
        card.classList.add('border-primary');
        card.classList.add('border-2');
        console.log(`Marking reservation card as active: index=${index}, propertyId=${reservation.propertyId}`);

        // Remove the select button for the active card
        const selectButtonContainer = card.querySelector('#select-button-container-' + index);
        if (selectButtonContainer) {
            selectButtonContainer.style.display = 'none';
        }
    }

    // Add click event listener to the select button
    const selectButton = card.querySelector('.select-property-btn');
    if (selectButton) {
        selectButton.addEventListener('click', () => {
            selectProperty(index);
        });
    }

    return card;
}

// Helper function to update property info on a reservation card after async fetch
function updatePropertyCardInfo(propertyId, propertyName, propertyAddress) {
    const titleElement = document.getElementById(`property-title-${propertyId}`);
    const addressElement = document.getElementById(`property-address-${propertyId}`);

    // Validate inputs to avoid showing placeholders
    if (propertyName && propertyName.includes("Property") && propertyName.length < 20) {
        // This looks like a generic property name, make it look nicer
        propertyName = `Property ${propertyId.substring(0, 6)}`;
    }

    if (propertyAddress === "123 Beach Avenue" || !propertyAddress) {
        propertyAddress = "Address unavailable";
    }

    if (titleElement && propertyName) {
        titleElement.textContent = propertyName;
    }

    if (addressElement && propertyAddress) {
        addressElement.textContent = propertyAddress;
    }

    console.log(`Updated reservation card for property ${propertyId} with name: ${propertyName}, address: ${propertyAddress}`);

    // Also update cache for future use
    if (!dashboardState.propertyCache[propertyId]) {
        dashboardState.propertyCache[propertyId] = {
            propertyId: propertyId,
            name: propertyName,
            address: propertyAddress,
            source: "fallback-ui-update"
        };
    }
}

// --- Select Property ---
async function selectProperty(index) {
    try {
        // Validation - make sure index is valid
        if (index === undefined || index === null || isNaN(index)) {
            console.error("Invalid index provided to selectProperty:", index);
            return;
        }

        // Ensure reservations are loaded
        if (!currentReservations || currentReservations.length === 0) {
            console.error("Cannot select property: No reservations loaded");
            return;
        }

        // Safety check for index bounds
        if (index < 0 || index >= currentReservations.length) {
            console.error(`Invalid property index ${index}, max is ${currentReservations.length - 1}`);
            return;
        }

        // Show loading spinner during property switch
        showLoadingSpinner(true);

        try {
            // Get reservation at specified index
            const reservation = currentReservations[index];
            if (!reservation) {
                throw new Error(`No reservation found at index ${index}`);
            }

            const propertyId = reservation.propertyId || reservation.PropertyId;
            if (!propertyId) {
                throw new Error(`No property ID found in reservation at index ${index}`);
            }

            console.log(`Switching to property ID: ${propertyId} (index: ${index})`);

            // Update the current property index
            currentPropertyIndex = index;

            // Update the current reservation in our state
            dashboardState.currentReservation = reservation;
            window.currentReservation = reservation; // For backward compatibility

            // Set the confirmed property ID - this triggers a propertyIdChanged event
            setConfirmedPropertyId(propertyId);

            // Update the UI to show the selected property
            updateSelectedPropertyUI();

            // Fetch property details (force refresh to get latest)
            await fetchPropertyDetails(propertyId, true, true);

            // Fetch knowledge items
            try {
                await fetchPropertyKnowledgeItems(propertyId);
            } catch (err) {
                console.warn(`Error fetching knowledge items: ${err.message}`);
                // Non-critical error, continue execution
            }

            console.log(`Property switch complete to ${propertyId}`);
            return true;
        } catch (error) {
            console.error("Error during property switch:", error);
            showErrorMessage(`Error selecting property: ${error.message}`);
            return false;
        } finally {
            // Hide the loading spinner regardless of success/failure
            showLoadingSpinner(false);
        }
    } catch (error) {
        console.error("Unhandled error in selectProperty:", error);
        showLoadingSpinner(false);
        return false;
    }
}

// --- Update Selected Property UI ---
function updateSelectedPropertyUI() {
    // Get the current confirmed property ID
    const confirmedId = getConfirmedPropertyId();
    console.log(`Updating selected property UI. Current index: ${currentPropertyIndex}, Property ID: ${confirmedId}`);

    // Update reservation cards
    const reservationCards = document.querySelectorAll('.reservation-card');
    reservationCards.forEach((card, index) => {
        const cardPropertyId = card.dataset.propertyId;
        const cardIndex = parseInt(card.dataset.index);

        // Check if this card matches either the current index or the confirmed property ID
        const isActive = (cardIndex === currentPropertyIndex) || (cardPropertyId === confirmedId);

        if (isActive) {
            // Add active styling
            card.classList.add('active');
            card.classList.add('border-primary');
            card.classList.add('border-2');

            console.log(`Marking card as active: index=${cardIndex}, propertyId=${cardPropertyId}`);

            // Hide the select button for the active card
            const selectButtonContainer = card.querySelector('#select-button-container-' + cardIndex);
            if (selectButtonContainer) {
                selectButtonContainer.style.display = 'none';
            }

            // If this card is active but not the current index, update the current index
            if (cardIndex !== currentPropertyIndex && cardPropertyId === confirmedId) {
                console.log(`Updating currentPropertyIndex from ${currentPropertyIndex} to ${cardIndex}`);
                currentPropertyIndex = cardIndex;
            }
        } else {
            // Remove active styling
            card.classList.remove('active');
            card.classList.remove('border-primary');
            card.classList.remove('border-2');

            // Show and enable the select button for inactive cards
            const selectButtonContainer = card.querySelector('#select-button-container-' + cardIndex);
            if (selectButtonContainer) {
                selectButtonContainer.style.display = 'block';
            }
        }
    });
}

// --- UI Helper Functions ---
function showLoadingSpinner(show) {
    const spinner = document.getElementById('loading-spinner');
    if (spinner) {
        spinner.style.display = show ? 'flex' : 'none';
    }
}

function showErrorMessage(message) {
    const errorContainer = document.getElementById('error-container');
    if (errorContainer) {
        errorContainer.textContent = message;
        errorContainer.style.display = 'block';
    }
}

function showNoReservationsMessage() {
    const noReservationsContainer = document.getElementById('no-reservations');
    if (noReservationsContainer) {
        noReservationsContainer.style.display = 'block';
    }

    // Hide the reservations container
    const reservationsContainer = document.getElementById('reservations-container');
    if (reservationsContainer) {
        reservationsContainer.style.display = 'none';
    }
}

function updatePropertyInfo(propertyDetails) {
    const propertyNameElement = document.getElementById('property-name');
    if (propertyNameElement) {
        propertyNameElement.textContent = propertyDetails.name || 'Unknown Property';
    }

    const propertyAddressElement = document.getElementById('property-address');
    if (propertyAddressElement) {
        propertyAddressElement.textContent = propertyDetails.address || 'No address available';
    }

    // Update property details in our centralized state
    dashboardState.propertyName = propertyDetails.name || 'Unknown Property';
    dashboardState.propertyAddress = propertyDetails.address || 'No address available';

    // For backward compatibility
    window.confirmedPropertyName = propertyDetails.name || 'Unknown Property';
    window.confirmedPropertyAddress = propertyDetails.address || 'No address available';
}

function isTestProperty(propertyId) {
    return propertyId && (
        propertyId.includes('test') ||
        propertyId.includes('demo') ||
        propertyId === 'sample-property-123'
    );
}

// --- Phone-based Reservation Lookup ---
async function findReservationsByPhone(phoneNumber) {
    console.log(`Looking up reservations for phone number: ${phoneNumber}`);

    if (!phoneNumber) {
        console.warn("No phone number provided for reservation lookup.");
        return [];
    }

    try {
        // Call the API to get reservations
        const response = await fetch(`/api/reservations?phone=${encodeURIComponent(phoneNumber)}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log("Phone-based reservations lookup result:", data);

        if (data.success && data.reservations && Array.isArray(data.reservations)) {
            // Store the reservations in our centralized state
            dashboardState.reservations = data.reservations;

            // For backward compatibility
            currentReservations = data.reservations;

            return data.reservations;
        } else {
            console.warn("No reservations found for phone number:", phoneNumber);
            return [];
        }
    } catch (error) {
        console.error("Error looking up reservations by phone:", error);
        return [];
    }
}

// Listen for property ID changes from other components
document.addEventListener('propertyIdChanged', (event) => {
    const { propertyId, previousPropertyId } = event.detail;
    console.log(`Property ID changed event received: ${previousPropertyId || 'unset'} -> ${propertyId}`);

    // Only update if we have reservations loaded
    if (currentReservations && currentReservations.length > 0) {
        // Find the index of the reservation with this property ID
        const index = currentReservations.findIndex(res => res.propertyId === propertyId);

        if (index !== -1 && index !== currentPropertyIndex) {
            console.log(`Updating reservation selection to match property ID change: index ${index}`);
            currentPropertyIndex = index;
            updateSelectedPropertyUI();
        }
    }
});

// Listen for property details updates to update reservation cards
document.addEventListener('propertyDetailsUpdated', (event) => {
    const { propertyId, propertyDetails } = event.detail;
    console.log(`Property details updated for ${propertyId}`);

    // Update any reservation cards for this property
    const cards = document.querySelectorAll(`.reservation-card[data-property-id="${propertyId}"]`);

    cards.forEach(card => {
        // Update property name and address
        const titleElement = card.querySelector(`#property-title-${propertyId}`);
        const addressElement = card.querySelector(`#property-address-${propertyId}`);

        if (titleElement && propertyDetails && propertyDetails.name) {
            titleElement.textContent = propertyDetails.name;
        }

        if (addressElement && propertyDetails && propertyDetails.address) {
            addressElement.textContent = propertyDetails.address;
        }

        console.log(`Updated reservation card for property ${propertyId} with name: ${propertyDetails ? propertyDetails.name : 'unknown'}, address: ${propertyDetails ? propertyDetails.address : 'unknown'}`);
    });
});

// Export functions for use in other modules
export {
    loadReservations,
    loadPropertyDetails,
    selectProperty,
    findReservationsByPhone,
    currentReservations,
    currentPropertyIndex,
    storedPropertyDetails
};
