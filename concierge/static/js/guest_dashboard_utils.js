/*
 * Utility functions for the guest dashboard
 */

// Global state management for shared data across modules
const dashboardState = {
    // User information
    userId: null,
    guestName: "Guest",
    phoneNumber: null,
    idToken: null,

    // Property information
    propertyId: null,
    propertyName: null,
    propertyAddress: null,
    propertyDetails: null,
    knowledgeItems: null,

    // Reservation information
    reservations: [],
    currentReservation: null,

    // Property cache - stores details for all properties
    propertyCache: {},

    // Loading states
    isLoadingProperty: false,
    isLoadingKnowledge: false,
    isLoadingReservations: false,

    // Error states
    errors: {
        reservations: null,
        property: null,
        knowledge: null
    },

    // Guest name management
    guestNameSource: null
};

// Initialize window properties for backward compatibility
window.confirmedPropertyId = dashboardState.propertyId;
window.confirmedPropertyName = dashboardState.propertyName;
window.confirmedPropertyAddress = dashboardState.propertyAddress;
window.storedIdToken = dashboardState.idToken;

// Utility function to parse dates correctly (handles both simple dates and ISO datetime strings)
function parseDateSafely(dateStr) {
    // Use the centralized date utilities
    return window.DateUtils.parseDateSafely(dateStr);
}

// Getter for property ID with fallbacks
function getConfirmedPropertyId() {
    // First check our state
    if (dashboardState.propertyId) {
        return dashboardState.propertyId;
    }

    // Then check various fallbacks
    const effectivePropertyId = window.PROPERTY_ID ||
                               document.body.dataset.propertyId ||
                               (document.getElementById('template-data')?.dataset.propertyId);

    // If found in fallback, update our state
    if (effectivePropertyId) {
        setConfirmedPropertyId(effectivePropertyId);
    }

    return dashboardState.propertyId;
}

// Setter for property ID that updates all references
function setConfirmedPropertyId(propertyId) {
    if (!propertyId) return null;

    // Check if this is a change or just a redundant call
    const currentId = dashboardState.propertyId;
    if (currentId === propertyId) {
        console.log(`Property ID already set to ${propertyId}, no change needed`);
        return propertyId;
    }

    console.log(`Setting confirmed property ID: ${propertyId} (was: ${currentId || 'unset'})`);

    // Update in all places to ensure consistency
    dashboardState.propertyId = propertyId;
    window.confirmedPropertyId = propertyId;
    window.PROPERTY_ID = propertyId;
    document.body.dataset.propertyId = propertyId;

    // Dispatch a custom event to notify other components of the property ID change
    const event = new CustomEvent('propertyIdChanged', {
        detail: {
            propertyId: propertyId,
            previousPropertyId: currentId
        }
    });
    document.dispatchEvent(event);

    // Log confirmation of update
    console.log(`Property ID updated to ${propertyId} in all references`);

    return propertyId;
}

// Helper function to add a message to the chat
function addMessageToChat(message, sender = 'ai', messageType = 'model') {
    // Check if chatMessages element exists
    const chatMessages = document.getElementById('chat-messages');
    if (!chatMessages) {
        console.warn("Chat messages container not found, cannot add message:", message);
        // Queue this message to be added when the chat container is available
        if (!window.pendingChatMessages) {
            window.pendingChatMessages = [];
        }
        window.pendingChatMessages.push({message, sender, messageType});

        // Try to add the message later when the DOM might be fully loaded
        setTimeout(() => {
            const chatMessagesRetry = document.getElementById('chat-messages');
            if (chatMessagesRetry) {
                // Process this message and any other pending messages
                if (window.pendingChatMessages && window.pendingChatMessages.length > 0) {
                    window.pendingChatMessages.forEach(msg => {
                        addMessageToChat(msg.message, msg.sender, msg.messageType);
                    });
                    window.pendingChatMessages = [];
                }
            }
        }, 1000);
        return;
    }

    // Avoid consecutive duplicate "Listening..." messages in chat
    if (typeof message === 'string' && message.trim() === 'Listening...') {
        let lastMessageText = null;
        const lastEl = chatMessages.lastElementChild;
        if (lastEl) {
            // Try modern renderer content
            const contentEl = lastEl.querySelector ? lastEl.querySelector('.chat-message-content') : null;
            if (contentEl && contentEl.textContent) {
                lastMessageText = contentEl.textContent.trim();
            } else {
                // Try legacy system message structure
                const sysSpan = lastEl.querySelector ? lastEl.querySelector('span') : null;
                if (sysSpan && sysSpan.textContent) {
                    lastMessageText = sysSpan.textContent.trim();
                } else if (lastEl.textContent) {
                    lastMessageText = lastEl.textContent.trim();
                }
            }
        }
        if (lastMessageText === 'Listening...') {
            console.log('Skipping duplicate "Listening..." message');
            return;
        }
    }

    // Track AI messages for feedback system
    if ((sender.toLowerCase() === 'ai' || sender.toLowerCase() === 'assistant') && 
        (messageType === 'model' || messageType === 'staycee' || typeof messageType === 'undefined')) {
        // Import and call feedback tracking function
        import('./guest_dashboard_feedback.js').then(module => {
            if (module.incrementMessageCount) {
                module.incrementMessageCount();
            }
        }).catch(error => {
            console.warn("Could not load feedback module:", error);
        });
    }

    // Use the new displayChatMessage function if available (from text chat module)
    if (typeof window.displayChatMessage === 'function') {
        const role = sender.toLowerCase() === 'user' || sender.toLowerCase() === 'you' ? 'user' :
                    (messageType === 'model' || messageType === 'staycee' ? 'assistant' : 'system');
        window.displayChatMessage(role, message);
        return;
    }

    // Fallback to old behavior if displayChatMessage is not available
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('chat-message');

    if (sender.toLowerCase() === 'user' || sender.toLowerCase() === 'you') {
        messageDiv.classList.add('user-message');
        messageDiv.textContent = `You: ${message}`; // Keep simple user message
    } else {
        messageDiv.classList.add('ai-message');

        // Distinguish between AI model responses and system messages
        if (messageType === 'model' || messageType === 'staycee') {
            // This is a response from Staycee (the AI model)
            messageDiv.textContent = `Staycee: ${message}`;
        } else {
            // This is a system/connection message
            messageDiv.textContent = message; // No prefix for system messages
            messageDiv.classList.add('system-message'); // Add class for potential styling
        }
    }

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight; // Scroll to bottom
}

// Helper function to fetch property details
async function fetchPropertyDetails(propertyId, isMainProperty = true, forceRefresh = false) {
    // Validate property ID
    if (!propertyId) {
        console.error("Cannot fetch property details: No property ID provided");
        return null;
    }

    // Check if we already have this property in our cache
    if (!forceRefresh && dashboardState.propertyCache[propertyId]) {
        const cachedDetails = dashboardState.propertyCache[propertyId];

        // Validate the cached details to ensure they're not placeholders
        if (isValidPropertyDetails(cachedDetails)) {
            console.log(`Using cached property details for ${propertyId} from dashboardState.propertyCache`);

            // If this is the main property, update the main state as well
            if (isMainProperty) {
                // Update main state
                dashboardState.propertyDetails = cachedDetails;
                dashboardState.propertyName = cachedDetails.name;
                dashboardState.propertyAddress = cachedDetails.address;

                // For backward compatibility
                window.propertyDetails = cachedDetails;
                window.confirmedPropertyName = cachedDetails.name;
                window.confirmedPropertyAddress = cachedDetails.address;

                // Trigger an update event
                dispatchPropertyDetailsUpdatedEvent(propertyId);
            }

            return cachedDetails;
        } else {
            console.warn(`Cached property details for ${propertyId} look invalid, fetching fresh data`);
        }
    }

    // If not in cache or force refresh requested, fetch from API
    console.log(`Fetching property details for ${propertyId} from API`);

    try {
        // FIXED: Use the correct API endpoint (singular 'property' not plural 'properties')
        const response = await fetch(`/api/property/${propertyId}`);
        if (!response.ok) {
            // If the primary endpoint fails, try the alternate endpoint
            console.warn(`Primary API endpoint failed with ${response.status}, trying alternate endpoint...`);
            const alternateResponse = await fetch(`/api/properties/${propertyId}`);
            if (!alternateResponse.ok) {
                throw new Error(`Both API endpoints failed: ${response.status} and ${alternateResponse.status}`);
            }
            return await handlePropertyApiResponse(alternateResponse, propertyId, isMainProperty);
        }

        return await handlePropertyApiResponse(response, propertyId, isMainProperty);
    } catch (error) {
        console.error(`Error fetching property details for ${propertyId}:`, error);

        // Create fallback property details if all else fails
        const fallbackProperty = createFallbackPropertyDetails(propertyId);

        // Temporary fallback - if cache exists, use it even if it was invalid
        if (dashboardState.propertyCache[propertyId]) {
            console.warn(`Using potentially invalid cached property details for ${propertyId} as fallback`);
            return dashboardState.propertyCache[propertyId];
        } else if (fallbackProperty) {
            console.warn(`Created fallback property details for ${propertyId}`);
            // Store in cache to avoid repeated API failures
            dashboardState.propertyCache[propertyId] = fallbackProperty;
            return fallbackProperty;
        }

        return null;
    }
}

// Helper function to handle property API response processing
async function handlePropertyApiResponse(response, propertyId, isMainProperty) {
    const data = await response.json();
    if (!data.success) {
        throw new Error(data.message || 'Error fetching property details');
    }

    const propertyDetails = data.property;
    if (!propertyDetails) {
        throw new Error('No property details returned from API');
    }

    // Normalize the data to ensure consistent field names
    const normalizedDetails = normalizePropertyDetails(propertyDetails, propertyId);

    // Validate the API details to ensure they're not placeholders
    if (!isValidPropertyDetails(normalizedDetails)) {
        console.warn(`API returned potentially invalid property details for ${propertyId}, using with caution`);
    }

    // Store in cache
    dashboardState.propertyCache[propertyId] = normalizedDetails;

    // Update main state if this is the main property
    if (isMainProperty) {
        dashboardState.propertyDetails = normalizedDetails;
        dashboardState.propertyName = normalizedDetails.name;
        dashboardState.propertyAddress = normalizedDetails.address;

        // For backward compatibility
        window.propertyDetails = normalizedDetails;
        window.confirmedPropertyName = normalizedDetails.name;
        window.confirmedPropertyAddress = normalizedDetails.address;

        console.log(`Confirmed property name: ${normalizedDetails.name}`);
        console.log(`Confirmed property address: ${normalizedDetails.address}`);
    }

    // Trigger an update event
    dispatchPropertyDetailsUpdatedEvent(propertyId);

    return normalizedDetails;
}

// Create fallback property details when API fails
function createFallbackPropertyDetails(propertyId) {
    // Check if we have this property in any reservation
    if (dashboardState.reservations && dashboardState.reservations.length > 0) {
        const matchingReservation = dashboardState.reservations.find(res =>
            res.propertyId === propertyId ||
            res.PropertyId === propertyId);

        if (matchingReservation) {
            // Extract whatever information we can from the reservation
            let propertyName = "Unknown Property";
            let propertyAddress = "Address unavailable";

            // Check reservation fields in different formats
            if (matchingReservation.propertyName && !matchingReservation.propertyName.includes("House")) {
                propertyName = matchingReservation.propertyName;
            } else if (matchingReservation.PropertyName && !matchingReservation.PropertyName.includes("House")) {
                propertyName = matchingReservation.PropertyName;
            } else {
                // Create a generic name based on property ID
                propertyName = `Property ${propertyId.substring(0, 6)}`;
            }

            if (matchingReservation.propertyAddress && matchingReservation.propertyAddress !== "123 Beach Avenue") {
                propertyAddress = matchingReservation.propertyAddress;
            } else if (matchingReservation.PropertyAddress && matchingReservation.PropertyAddress !== "123 Beach Avenue") {
                propertyAddress = matchingReservation.PropertyAddress;
            }

            // Create and return fallback details
            return {
                propertyId: propertyId,
                name: propertyName,
                address: propertyAddress,
                isPlaceholder: true,
                source: "fallback-from-reservation"
            };
        }
    }

    // Ultimate fallback with generic info
    return {
        propertyId: propertyId,
        name: `Property ${propertyId.substring(0, 6)}`,
        address: "Address not available",
        isPlaceholder: true,
        source: "generic-fallback"
    };
}

// Helper function to validate property details to ensure they're not placeholders
function isValidPropertyDetails(details) {
    // If no details at all, invalid
    if (!details) return false;

    // Check name - suspicious if it contains common placeholder patterns
    if (!details.name) return false;

    const nameSuspicious =
        details.name === "Property" ||
        details.name.includes("House") && details.name.includes("hsNf") ||
        details.name.includes("House") && details.name.includes("200c");

    // Check address - suspicious if it matches common placeholder patterns
    const addressSuspicious =
        !details.address ||
        details.address === "123 Beach Avenue" ||
        details.address === "Address loading...";

    // If both name and address look suspicious, consider invalid
    if (nameSuspicious && addressSuspicious) {
        console.warn(`Property details look like placeholders: name=${details.name}, address=${details.address}`);
        return false;
    }

    // Otherwise, consider it valid enough
    return true;
}

// Helper function to trigger a custom event when property details are updated
function dispatchPropertyDetailsUpdatedEvent(propertyId) {
    const event = new CustomEvent('propertyDetailsUpdated', {
        detail: { propertyId }
    });
    document.dispatchEvent(event);
    console.log(`Property details updated for ${propertyId}`);
}

// Helper function to normalize property details
function normalizePropertyDetails(propertyDetails, propertyId) {
    // Create a normalized object with consistent field names
    const normalized = {
        propertyId: propertyDetails.propertyId || propertyDetails.PropertyId || propertyId,
        name: propertyDetails.name || propertyDetails.Name || "Property",
        address: propertyDetails.address || propertyDetails.Address || "Address not available",
        checkInTime: propertyDetails.checkInTime || propertyDetails.CheckInTime || "",
        checkOutTime: propertyDetails.checkOutTime || propertyDetails.CheckOutTime || "",
        wifiNetwork: propertyDetails.wifiNetwork || propertyDetails.WifiNetwork || "",
        wifiPassword: propertyDetails.wifiPassword || propertyDetails.WifiPassword || "",
        hostName: propertyDetails.hostName || propertyDetails.HostName || "Host",
        hostId: propertyDetails.hostId || propertyDetails.HostId || "",
        description: propertyDetails.description || propertyDetails.Description || "",
        rules: propertyDetails.rules || propertyDetails.Rules || "",
        amenities: propertyDetails.amenities || propertyDetails.Amenities || []
    };

    // Copy any other fields that might be useful
    for (const key in propertyDetails) {
        if (!normalized.hasOwnProperty(key.toLowerCase())) {
            normalized[key] = propertyDetails[key];
        }
    }

    return normalized;
}

// Function to fetch property knowledge items from Firestore
async function fetchPropertyKnowledgeItems(propertyId) {
    // Validate property ID
    if (!propertyId) {
        console.error("Cannot fetch knowledge items: No property ID provided");
        return null;
    }

    // Check if we already have knowledge items for this property
    if (dashboardState.knowledgeItems && dashboardState.propertyId === propertyId) {
        console.log(`Using cached knowledge items for property ${propertyId}`);
        return dashboardState.knowledgeItems;
    }

    // Check if we're already loading knowledge items
    if (dashboardState.isLoadingKnowledge) {
        console.log("Already loading knowledge items, waiting for completion...");
        // Wait for the current loading to complete
        return new Promise(resolve => {
            const checkInterval = setInterval(() => {
                if (!dashboardState.isLoadingKnowledge) {
                    clearInterval(checkInterval);
                    resolve(dashboardState.knowledgeItems);
                }
            }, 100);
        });
    }

    try {
        // Set loading state
        dashboardState.isLoadingKnowledge = true;

        console.log(`Fetching knowledge items for property ${propertyId} from API`);
        const response = await fetch(`/api/knowledge-items?propertyId=${encodeURIComponent(propertyId)}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        if (data.items && Array.isArray(data.items) && data.items.length > 0) {
            // Store raw items in our state
            dashboardState.knowledgeItems = data.items;

            // Store in property details for access in system prompt (for backward compatibility)
            if (dashboardState.propertyDetails) {
                dashboardState.propertyDetails.knowledgeItems = data.items;
            }
            if (window.propertyDetails) {
                window.propertyDetails.knowledgeItems = data.items;
                console.log("Stored raw knowledge items in propertyDetails.knowledgeItems");
            }

            // Format Firestore items as context information
            const formattedKnowledgeItems = data.items.map(item => {
                // Format based on item type
                const typePrefix = item.type ? `[${item.type.toUpperCase()}] ` : '';
                return `${typePrefix}${item.content}`;
            }).join('\n\n');

            // Store formatted items for backward compatibility
            window.propertyKnowledgeItems = formattedKnowledgeItems;

            console.log("Retrieved knowledge items from Firestore:", data.items.length, "items found");
            console.log("Formatted knowledge items stored in window.propertyKnowledgeItems");

            // Log the first few items for debugging
            if (data.items.length > 0) {
                console.log("Sample knowledge items:", data.items.slice(0, 3));
            }

            return data.items;
        } else {
            // Fallback to property rules if no knowledge items found
            const propertyData = dashboardState.propertyDetails || window.propertyDetails || {};
            if (propertyData.rules) {
                console.log("No specific knowledge items found, using property rules as knowledge base");
                const rules = propertyData.rules.split(/\n|;/).filter(rule => rule.trim());

                if (rules.length > 0) {
                    const formattedRules = rules.map(rule => {
                        return `[RULE] ${rule.trim()}`;
                    }).join('\n\n');

                    // Store formatted rules
                    window.propertyKnowledgeItems = formattedRules;

                    // Create synthetic knowledge items from rules
                    const ruleItems = rules.map(rule => ({
                        type: 'RULE',
                        content: rule.trim(),
                        propertyId: propertyId
                    }));

                    // Store in our state
                    dashboardState.knowledgeItems = ruleItems;

                    return ruleItems;
                } else {
                    window.propertyKnowledgeItems = "";
                    dashboardState.knowledgeItems = [];
                    return [];
                }
            } else {
                console.log("No knowledge items or rules found for property:", propertyId);
                window.propertyKnowledgeItems = "";
                dashboardState.knowledgeItems = [];
                return [];
            }
        }
    } catch (error) {
        console.warn("Error fetching knowledge items from Firestore:", error);
        // Attempt fallback to property rules on error
        try {
            const propertyData = dashboardState.propertyDetails || window.propertyDetails || {};
            if (propertyData.rules) {
                const rules = propertyData.rules.split(/\n|;/).filter(rule => rule.trim());
                if (rules.length > 0) {
                    const formattedRules = rules.map(rule => {
                        return `[RULE] ${rule.trim()}`;
                    }).join('\n\n');

                    // Store formatted rules
                    window.propertyKnowledgeItems = formattedRules;

                    // Create synthetic knowledge items from rules
                    const ruleItems = rules.map(rule => ({
                        type: 'RULE',
                        content: rule.trim(),
                        propertyId: propertyId
                    }));

                    // Store in our state
                    dashboardState.knowledgeItems = ruleItems;

                    console.log("Fallback to property rules successful");
                    return ruleItems;
                }
            }

            // If we get here, fallback failed
            window.propertyKnowledgeItems = "";
            dashboardState.knowledgeItems = [];
            return [];
        } catch (fallbackError) {
            console.warn("Fallback to property rules failed:", fallbackError);
            window.propertyKnowledgeItems = "";
            dashboardState.knowledgeItems = [];
            return [];
        }
    } finally {
        // Clear loading state
        dashboardState.isLoadingKnowledge = false;
    }
}

// Function to create a shared system prompt for both voice and text chat
function createSharedSystemPrompt() {
    // Get data from our centralized state - use window.dashboardState for consistency
    const globalDashboardState = window.dashboardState || dashboardState;
    const propertyName = globalDashboardState.propertyName || window.confirmedPropertyName || "this property";
    const propertyAddress = globalDashboardState.propertyAddress || window.confirmedPropertyAddress || "";
    
    // Get the most up-to-date guest name with proper fallback order
    const guestName = globalDashboardState.guestName || window.GUEST_NAME || "Guest";
    
    console.log("[SHARED PROMPT DEBUG] Creating shared system prompt for property:", propertyName);
    console.log("[SHARED PROMPT DEBUG] Property details available:", propertyDetails ? "Yes" : "No");
    console.log("[SHARED PROMPT DEBUG] Knowledge items available:", globalDashboardState.knowledgeItems ? "Yes" : "No");
    console.log("[SHARED PROMPT DEBUG] Using guest name:", guestName);
    console.log("[SHARED PROMPT DEBUG] globalDashboardState.guestName:", globalDashboardState.guestName);
    console.log("[SHARED PROMPT DEBUG] window.GUEST_NAME:", window.GUEST_NAME);
    console.log("[SHARED PROMPT DEBUG] Guest name is 'Guest':", guestName === 'Guest');
    console.log("[SHARED PROMPT DEBUG] Will include name asking instruction:", guestName === 'Guest');
    
    // Ensure propertyDetails is properly initialized before accessing it
    const propertyDetailsAvailable = typeof propertyDetails !== 'undefined' && propertyDetails;
    console.log("createSharedSystemPrompt: propertyDetails available:", propertyDetailsAvailable);
    
    // Get property data from various sources
    const propertyData = globalDashboardState.propertyDetails || window.propertyDetails || {};
    
    // Get knowledge items from various sources
    let knowledgeItems = [];
    if (globalDashboardState.knowledgeItems && globalDashboardState.knowledgeItems.length > 0) {
        knowledgeItems = globalDashboardState.knowledgeItems;
        console.log("createSharedSystemPrompt: Using knowledge items from globalDashboardState, count:", knowledgeItems.length);
    } else if (propertyDetailsAvailable && propertyDetails.knowledgeItems && propertyDetails.knowledgeItems.length > 0) {
        knowledgeItems = propertyDetails.knowledgeItems;
        console.log("createSharedSystemPrompt: Using knowledge items from propertyDetails, count:", knowledgeItems.length);
    } else if (window.propertyKnowledgeItems && window.propertyKnowledgeItems.length > 0) {
        knowledgeItems = window.propertyKnowledgeItems;
        console.log("createSharedSystemPrompt: Using knowledge items from window.propertyKnowledgeItems, count:", knowledgeItems.length);
    }

    // Build comprehensive property context
    let propertyContextParts = [
        "PROPERTY INFORMATION:",
        `Property Name: ${propertyName}`,
        `Address: ${propertyAddress}`,
        `Guest: ${guestName}`
    ];

    // Add host information
    const hostName = propertyData.hostName || propertyData.HostName || "your host";
    propertyContextParts.push(`Host: ${hostName}`);

    // Add location details
    if (propertyData.city || propertyData.City) {
        propertyContextParts.push(`City: ${propertyData.city || propertyData.City}`);
    }
    if (propertyData.state || propertyData.State) {
        propertyContextParts.push(`State: ${propertyData.state || propertyData.State}`);
    }
    if (propertyData.country || propertyData.Country) {
        propertyContextParts.push(`Country: ${propertyData.country || propertyData.Country}`);
    }

    // Add schedule information
    if (propertyData.checkInTime || propertyData.CheckInTime || propertyData.checkOutTime || propertyData.CheckOutTime) {
        const checkIn = propertyData.checkInTime || propertyData.CheckInTime || '';
        const checkOut = propertyData.checkOutTime || propertyData.CheckOutTime || '';
        propertyContextParts.push(`Schedule: Check-in ${checkIn}${checkOut ? `, Check-out ${checkOut}` : ''}`);
    }

    // Add WiFi information
    const wifiNetwork = propertyData.wifiNetwork || propertyData.WifiNetwork || propertyData.wifiDetails?.network;
    const wifiPassword = propertyData.wifiPassword || propertyData.WifiPassword || propertyData.wifiDetails?.password;
    if (wifiNetwork || wifiPassword) {
        propertyContextParts.push(`WiFi Network: ${wifiNetwork || 'Not provided'}${wifiPassword ? `, Password: ${wifiPassword}` : ''}`);
    }

    // Add property description
    if (propertyData.Description || propertyData.description) {
        propertyContextParts.push(`Description: ${propertyData.Description || propertyData.description}`);
    }

    // Add amenities information
    if (propertyData.amenities) {
        if (propertyData.amenities.basic && propertyData.amenities.basic.length > 0) {
            propertyContextParts.push(`Basic Amenities: ${propertyData.amenities.basic.join(', ')}`);
        }
        if (propertyData.amenities.appliances && propertyData.amenities.appliances.length > 0) {
            const appliancesList = propertyData.amenities.appliances.map(appliance => {
                if (typeof appliance === 'string') return appliance;
                const parts = [appliance.name];
                if (appliance.location) parts.push(`(${appliance.location})`);
                if (appliance.brand) parts.push(`[${appliance.brand}]`);
                return parts.join(' ');
            }).join(', ');
            propertyContextParts.push(`Appliances: ${appliancesList}`);
        }
    }

    // Add house rules
    if (propertyData.rules || propertyData.Rules) {
        propertyContextParts.push(`House Rules: ${propertyData.rules || propertyData.Rules}`);
    }
    // Also check for structured house rules
    if (propertyData.houseRules && Array.isArray(propertyData.houseRules) && propertyData.houseRules.length > 0) {
        const enabledRules = propertyData.houseRules
            .filter(rule => rule.enabled)
            .map(rule => rule.title || rule.content || rule.description)
            .join(', ');
        if (enabledRules) {
            propertyContextParts.push(`House Rules: ${enabledRules}`);
        }
    }

    // Add emergency information
    if (propertyData.emergencyInfo && Array.isArray(propertyData.emergencyInfo) && propertyData.emergencyInfo.length > 0) {
        const enabledEmergencyInfo = propertyData.emergencyInfo.filter(info => info.enabled && (info.instructions || info.location));
        if (enabledEmergencyInfo.length > 0) {
            const emergencyDetails = enabledEmergencyInfo.map(info => {
                const parts = [info.title];
                if (info.location) parts.push(`Location: ${info.location}`);
                if (info.instructions) parts.push(`Instructions: ${info.instructions}`);
                return parts.join(' - ');
            }).join('; ');
            propertyContextParts.push(`Emergency Information: ${emergencyDetails}`);
        }
    }

    // Add property facts (other information)
    if (propertyData.propertyFacts && Array.isArray(propertyData.propertyFacts) && propertyData.propertyFacts.length > 0) {
        const enabledFacts = propertyData.propertyFacts.filter(fact => fact.enabled && fact.answer);
        if (enabledFacts.length > 0) {
            const factsDetails = enabledFacts.map(fact => `${fact.question}: ${fact.answer}`).join('; ');
            propertyContextParts.push(`Property Facts: ${factsDetails}`);
        }
    }

    // Add knowledge base items
    if (window.propertyKnowledgeItems) {
        propertyContextParts.push(`Knowledge Base (Q&A Format):\n${window.propertyKnowledgeItems}`);
    }

    // Get reservation details for the system prompt
    let reservationContext = "";
    const currentReservation = globalDashboardState.currentReservation || window.currentReservation;

    if (currentReservation) {
        const checkInDate = currentReservation.startDate || currentReservation.StartDate ||
                           currentReservation.checkInDate || currentReservation.CheckInDate;
        const checkOutDate = currentReservation.endDate || currentReservation.EndDate ||
                            currentReservation.checkOutDate || currentReservation.CheckOutDate;

        if (checkInDate || checkOutDate) {
            reservationContext = "\n\nReservation Details:\n";
            if (checkInDate) {
                const checkInFormatted = window.DateUtils ? window.DateUtils.formatDateForDisplay(checkInDate) : new Date(checkInDate).toLocaleDateString();
                reservationContext += `Check-in: ${checkInFormatted}\n`;
            }
            if (checkOutDate) {
                const checkOutFormatted = window.DateUtils ? window.DateUtils.formatDateForDisplay(checkOutDate) : new Date(checkOutDate).toLocaleDateString();
                reservationContext += `Check-out: ${checkOutFormatted}\n`;
            }
            console.log("Added reservation context to system prompt:", reservationContext);
        }
    }

    // Build the system prompt
    let systemPrompt = `You are Staycee, a helpful AI concierge assistant for "${propertyName}" located at "${propertyAddress}".
You are speaking with ${guestName}, a guest at this property.
The host for this property is ${hostName}.
Your goal is to assist the guest with any questions or needs they have regarding their stay.
Be conversational, friendly, and helpful.

${guestName === 'Guest' ? 'IMPORTANT: The guest name is currently generic. When appropriate during the conversation (such as during initial greetings or when it feels natural), politely ask for their name so you can address them personally. Once they provide their name, use it throughout the conversation to create a more personalized experience.' : `Use the guest's name (${guestName}) naturally throughout the conversation to create a personalized experience.`}

TRAVEL GUIDE CAPABILITIES:
When guests ask about attractions, activities, restaurants, or places to visit beyond the property, act as a knowledgeable travel guide. Provide helpful recommendations while gathering minimal essential context.

CLARIFICATION STRATEGY:
For travel guide requests, use this decision tree:

SPECIFIC REQUESTS (e.g.     running trails, coffee shops, Italian restaurants): 
- Ask 1 quick clarifying question ONLY if essential for safety/suitability
- Then immediately search and provide recommendations

BROAD REQUESTS (e.g. activities, restaurants, things to do):
- Ask 1-2 targeted questions to understand their situation
- Focus on: group composition (family vs couple vs solo) AND one preference (outdoor vs indoor, casual vs upscale)
- Then immediately search and provide tailored recommendations

ESSENTIAL CONTEXT TO GATHER:
- Group composition + stay nature: "Are you here with family, as a couple for a romantic getaway, solo for business, or just a casual leisure trip?"
- Key preference: What type of [activity/dining/experience] appeals to you most?

AVOID asking about: budget, transportation, celebration details, specific dietary restrictions (unless they mention allergies)

CRITICAL CONTEXT RETENTION RULES:
1. NEVER re-ask questions that have already been answered in the current conversation
2. Before asking any clarifying question, check if the guest has already provided that information
3. If you have partial context, only ask for the missing pieces - do not repeat questions about information already provided
4. Always reference and build upon previously provided context when making recommendations
5. If a guest points out you're repeating questions, immediately acknowledge the mistake and proceed with the information you already have

IMMEDIATE SEARCH AND RESPONSE RULE:
NEVER announce that you will search. Instead, immediately use the google_search tool and provide results directly. Do not use phrases like "Let me search" or "I will look for" - just search and deliver recommendations in one response.

EXAMPLE CORRECT RESPONSES:

SPECIFIC REQUEST (minimal clarification):
Guest: "I'm looking for scenic running trails for a beginner runner"
Correct Response: "Are you comfortable with 2-3 mile distances?" [After answer, immediately search and provide:] "Here are top beginner-friendly scenic trails: 1) Cedar Lake Loop Trail - 2.5 miles, flat terrain, beautiful lake views. 2) Meadowbrook Nature Trail - 1.8 miles, easy grade, shaded path. Would you like directions to either of these, or would you like to see more options?"

BROAD REQUEST (gather essential context then deliver):
Guest: "What activities are there around here?"
Correct Response: "Are you here with family, as a couple for a romantic getaway, solo for business, or just a casual leisure trip? And do you prefer outdoor activities or indoor attractions?" [Wait for their answer, then immediately search and provide tailored recommendations in the next response]

FOLLOW-UP REQUEST (use existing context):
Guest: "What about dinner options?" (after establishing they're a couple on a romantic getaway who enjoy outdoor activities)
Correct Response: [Use get_current_time first, then google_search with temporal context like "romantic restaurants open Tuesday evening [location]"] "Since you're here for a romantic getaway and enjoy outdoor activities, here are two perfect dinner spots open tonight: 1) Lakeside Bistro - intimate outdoor patio with lake views, farm-to-table cuisine, open until 10pm. 2) Mountain View Restaurant - rooftop dining with sunset views, local specialties, reservations available. Which sounds more appealing, or would you like to see more options?"

WHEN GUEST POINTS OUT REPETITION:
Guest: "You already asked me that, do you remember?"
Correct Response: [Use google_search tool immediately, then provide results like:] "I remember you're traveling as a couple and enjoy outdoor activities. Here are great [specific request based on context]: 1) [Option 1 with details] 2) [Option 2 with details]. Which interests you more, or would you like additional options?"

WHEN GUEST ASKS ABOUT MISSING INFORMATION:
Guest: "What happened to the running trail?" or "Where are those recommendations you promised?"
Correct Response: [Use google_search tool immediately, then provide results like:] "Here are top beginner-friendly scenic running trails near Cedar Lake: 1) Cedar Lake Loop Trail - 2.5 miles, flat terrain, beautiful lake views. 2) Meadowbrook Nature Trail - 1.8 miles, easy grade, shaded path. Which would you prefer, or would you like to see more options?"

SEARCH AND RESPONSE APPROACH:
- For location-based queries (restaurants, cafes, attractions, etc.), ALWAYS use search_nearby_places tool - it provides accurate distances, ratings, hours, and prices
- For general information or current events, use google_search tool
- For activity/dining requests, first call get_current_time to understand temporal context
- CRITICAL: Provide EXACTLY 1 or 2 recommendations only - NEVER provide more than 2 options
- Include practical details from search_nearby_places: distance (walking/driving), ratings, hours, price level, why it fits their needs
- Always ask if they'd like additional alternatives: "Would you like to see more options?"
- Never announce searching - just deliver results immediately
- The search_nearby_places tool automatically calculates accurate walking/driving distances and travel times
- Avoid overwhelming guests with too many choices at once

${propertyContextParts.join('\n')}${reservationContext}

Today's date is ${new Date().toLocaleDateString()}.

IMPORTANT - YOUR CAPABILITIES AND LIMITATIONS:  
You are an AI assistant that can ONLY:
- Answer questions about the property using the information provided above
- Search for local information (restaurants, attractions, services, etc.) using web search
- Provide helpful suggestions and recommendations based on available information
- Act as a travel guide for local attractions and activities

You CANNOT:
- Contact the host, neighbors, or any other people on behalf of the guest
- Make reservations, bookings, or appointments
- Control any property systems (lights, temperature, appliances, etc.)
- Arrange services, deliveries, or maintenance
- Take any physical actions or interventions
- Resolve issues that require human intervention

For ANY situation that requires action beyond providing information, you MUST suggest that the guest contact the host directly. This includes but is not limited to:
- Noise complaints or neighbor issues
- Maintenance problems or repairs needed
- Missing amenities or supplies
- Property access issues
- Emergency situations requiring immediate human response
- Any requests for services or interventions

Always be clear that you are an informational assistant only and cannot take actions on the guest's or host's behalf.

CRITICAL INFRASTRUCTURE PROTECTION:
If a guest asks about the location of critical infrastructure elements such as:
- Water shutoff valves or main water controls
- Electrical panels, fuse boxes, or circuit breakers
- Gas shutoff valves or gas meter access
- HVAC system controls, air handler units, or ventilation system access
- Sump pumps, water heaters, or other mechanical systems
- Any utility controls or emergency shutoffs

You MUST first ask the guest to explain the specific reason they need this information. Only provide access details if there is a genuine emergency situation such as:
- Fire, smoke, or electrical hazards
- Water leaks, flooding, or pipe bursts
- Gas leaks or gas-related safety concerns
- HVAC system failures causing dangerous temperatures
- Any situation where immediate access to these systems would prevent property damage or ensure guest safety

For non-emergency requests (routine questions, curiosity, general maintenance), politely explain that this information is restricted for safety and security reasons, and suggest they contact the host directly for any non-emergency infrastructure needs.

You have access to the following tools:
1. search_nearby_places: Use this tool for ANY location-based queries about nearby places (restaurants, cafes, attractions, shopping, etc.). This provides accurate distances, travel times, ratings, hours, price levels, and structured information. ALWAYS use this for location queries instead of google_search.
2. google_search: Use this tool ONLY for general information, current events, or questions that are NOT about nearby places. For restaurants, attractions, and local businesses, use search_nearby_places instead.
3. get_current_time: Use this function when guests ask about the current time, date, or when you need to provide time-sensitive information. This will give you the accurate current time in the property's timezone.

MULTI-TOOL USAGE FOR CONTEXT-AWARE RECOMMENDATIONS:
When making activity or dining recommendations, you can call multiple tools in a single response to provide more relevant suggestions:
- Use get_current_time to check season, date, day of week, and current time
- Use google_search with temporal context (e.g., "winter activities near [location]", "restaurants open Sunday evening [location]")
- Consider seasonal availability, operating hours, weather-appropriate activities, and current events

When using the search_nearby_places tool:
- This tool provides structured data with accurate distances, travel times, ratings, hours, and price levels
- Present the information naturally: "Here are two great options: [Place Name] is a 10-minute walk away with 4.5 stars..."
- Include walkability information: "within walking distance" for places under 1 mile
- Mention open hours if available: "currently open until 9pm" or "opens at 8am"
- If search results are empty, acknowledge and suggest alternative search terms or broader categories

When using the google_search tool:
- Use ONLY for general information, not for nearby places/restaurants/attractions
- After receiving the search results, provide a concise and helpful summary
- If the search results don't provide relevant information, acknowledge this and offer alternative suggestions
- NEVER leave a guest hanging - always provide some form of helpful response even if search results are limited

When using the get_current_time function:
- This function automatically detects the property's timezone based on location
- Use it whenever a guest asks "what time is it" or similar time-related questions
- The function will return the current date, time, and timezone information

 WEB SEARCH USAGE POLICY:
 - Purpose: Use web search to help with general, location-based information around the property and other non-private topics.
 - Do NOT use web search to obtain private, property-specific details.
 - If a guest asks for a property-specific detail that is not present above, REPLY that you don’t have that information and suggest contacting the host or checking their Airbnb itinerary/House Manual.
 
 ALLOWED WEB SEARCH EXAMPLES (OK to search):
 - Nearby and best-rated: coffee shops, restaurants, grocery stores, pharmacies, ATMs
 - Transportation: closest public transit stops, route options, schedules near the property address (without sharing private access info)
 - Landmarks, attractions, parks, museums near the area; directions and hours
 - Weather forecast, local events, neighborhood safety resources from public authorities
 - Appliance usage/troubleshooting IF the brand and model are provided in the property data (e.g., "Bosch Series 6 model XYZ123 dishwasher – how to run quick wash")
 - Clearly public building facts when broadly published by public sources (e.g., number of floors, year built) — only if unambiguous; if unsure, say you don’t know
 
 DISALLOWED WEB SEARCH EXAMPLES (DO NOT search; must come from property details/knowledge items or admit you don’t have it):
 - Check-in or check-out time or procedures for this property
 - WiFi network name or password
 - Door/lock codes, gate codes, smart lock access or key locations
 - Parking instructions specific to the property (permits, spot numbers, garage access)
 - Unit numbers, floor plans, or how to access the unit/complex
 - Appliance locations or property-specific manuals and instructions
 - Fees, deposits, add-on services, house rules, or policies for this property
 - Emergency access details, lock boxes, or equipment locations

STRICT NON-HALLUCINATION POLICY:
- NEVER invent or guess property-specific details (e.g., check-in/out times, WiFi, door codes, appliances, fees, parking rules, gate instructions, or checkout procedures) that are not explicitly provided in the property context or knowledge items above.
- If a guest asks for something that is not present in the provided details, clearly say you don't have that information and offer to connect them with their host or suggest where it might normally be found.
- If knowledge items are empty or do not mention a topic (e.g., checkout), DO NOT assume defaults. Say you don’t have that detail and suggest next steps.
- When summarizing or combining knowledge items, preserve the original meaning; do not add missing steps or details.
- If information appears contradictory, ask a clarifying question rather than guessing.

Respond to the guest's queries to help them have a great stay.`;
    
    console.log("createSharedSystemPrompt: Created system prompt with length:", systemPrompt.length);
    return systemPrompt;
}

// Function to determine if test property IDs should be allowed
function shouldAllowTestProperties() {
    // Check for development mode or debugging flag
    const isDevMode = window.location.hostname === 'localhost' ||
                      window.location.hostname === '127.0.0.1' ||
                      window.location.search.includes('allow_test=true');

    // Allow test properties in development mode
    return isDevMode;
}

// Function to update guest name from reservation data
function updateGuestNameFromReservation(reservation) {
    if (!reservation) return false;

    // Check if we already have a high-priority name (user-profile) - don't override it
    const currentSource = dashboardState.guestNameSource;
    const currentPriority = {
        'template': 1,
        'url': 2,
        'reservation': 3,
        'firebase': 4,
        'additional-contact': 5,
        'additional-contact-last4-match': 6,
        'additional-contact-exact-match': 7,
        'guest-phone-last4-match': 6,
        'reservation-primary': 4,
        'user-profile': 7
    }[currentSource] || 0;

    // If we already have a user-profile name (highest priority), don't override with reservation data
    if (currentSource === 'user-profile') {
        console.log("Skipping reservation name update - user profile name already set:", dashboardState.guestName);
        return false;
    }

    // Log the reservation for debugging
    console.log("Attempting to update guest name from reservation:", reservation);

    const userPhone = dashboardState.phoneNumber || window.PHONE_NUMBER;
    console.log("User phone for comparison:", userPhone);

    // First check if user is an additional contact on this reservation
    if (userPhone) {
        // Handle different possible formats of additional contacts
        const additionalContacts =
            (reservation.additionalContacts && Array.isArray(reservation.additionalContacts)) ? reservation.additionalContacts :
            (reservation.AdditionalContacts && Array.isArray(reservation.AdditionalContacts)) ? reservation.AdditionalContacts :
            (reservation.additional_contacts && Array.isArray(reservation.additional_contacts)) ? reservation.additional_contacts : [];

        if (additionalContacts && additionalContacts.length > 0) {
            console.log("Checking", additionalContacts.length, "additional contacts for phone match:", additionalContacts);

            // Look for exact phone match first
            const exactMatch = additionalContacts.find(contact => {
                const contactPhone = contact.phone || contact.phoneNumber || '';
                console.log(`Comparing contact phone ${contactPhone} with user phone ${userPhone}`);
                return contactPhone === userPhone;
            });

            if (exactMatch && exactMatch.name) {
                console.log("Found exact phone match in additional contacts:", exactMatch.name);
                updateGuestName(exactMatch.name, 'additional-contact-exact-match');
                return true;
            }

            // Then try last 4 digits match
            if (userPhone.length >= 4) {
                const last4Match = additionalContacts.find(contact => {
                    const contactPhone = contact.phone || contact.phoneNumber || '';
                    return contactPhone.length >= 4 &&
                           contactPhone.slice(-4) === userPhone.slice(-4);
                });

                if (last4Match && last4Match.name) {
                    console.log("Found last 4 digits match in additional contacts:", last4Match.name);
                    updateGuestName(last4Match.name, 'additional-contact-last4-match');
                    return true;
                }
            }
        }

        // Check if the last 4 digits of the user's phone match the guestPhoneLast4
        if (userPhone.length >= 4 && reservation.guestPhoneLast4) {
            if (userPhone.slice(-4) === reservation.guestPhoneLast4) {
                const guestName = reservation.guestName || reservation.GuestName;
                if (guestName && guestName !== 'Guest') {
                    console.log("Found match with guestPhoneLast4, using guest name:", guestName);
                    updateGuestName(guestName, 'guest-phone-last4-match');
                    return true;
                }
            }
        }
    }

    // If no match found in contacts, use the reservation's guest name if available
    const guestName = reservation.guestName || reservation.GuestName;
    if (guestName && guestName !== 'Guest') {
        console.log("Using reservation's primary guest name:", guestName);
        updateGuestName(guestName, 'reservation-primary');
        return true;
    }

    return false;
}

// Function to update guest name with source tracking
function updateGuestName(name, source = 'unknown') {
    console.log(`updateGuestName called with name=${name}, source=${source}`);
    
    // Get the global dashboard state
    const globalDashboardState = window.dashboardState || dashboardState;
    
    // Define priority levels for different sources
    const sourcePriority = {
        'template': 1,
        'url': 2,
        'reservation': 3,
        'firebase': 4,
        'additional-contact': 5,
        'additional-contact-last4-match': 6,
        'additional-contact-exact-match': 7,
        'guest-phone-last4-match': 6,
        'reservation-primary': 4,
        'user-profile': 7,
        'magic_link': 3,
        'socket-update': 8,
        'profile-update': 8
    };

    const currentPriority = sourcePriority[globalDashboardState.guestNameSource] || 0;
    const newPriority = sourcePriority[source] || 0;

    // Only update if the new source has higher or equal priority
    if (newPriority >= currentPriority) {
        console.log(`Updating guest name to "${name}" from source: ${source}`);
        
        // Update the global dashboard state
        globalDashboardState.guestName = name;
        globalDashboardState.guestNameSource = source;
        
        // Also update window.GUEST_NAME for backward compatibility
        window.GUEST_NAME = name;
        
        // Update DOM elements directly
        const guestNameElement = document.getElementById('guest-name');
        if (guestNameElement) {
            guestNameElement.textContent = name;
            console.log(`Directly updated DOM element guest-name to "${name}"`);
        }
        
        // Dispatch custom event for other modules
        const event = new CustomEvent('guestNameUpdated', {
            detail: { name, source }
        });
        document.dispatchEvent(event);
        
        console.log(`Guest name updated successfully to "${name}" from source: ${source}`);
    } else {
        console.log(`Skipping guest name update to "${name}" from source: ${source} (lower priority than current source: ${globalDashboardState.guestNameSource})`);
    }
}

// Function to initialize dashboard state from template data
function initializeDashboardState() {
    console.log("Initializing dashboard state from template data");
    
    // Get the global dashboard state
    const globalDashboardState = window.dashboardState || dashboardState;
    
    // Initialize with template data
    if (window.reservations && Array.isArray(window.reservations)) {
        globalDashboardState.reservations = window.reservations;
        globalDashboardState.reservationsCount = window.reservations.length;
        
        // Set initial guest name from template if available
        if (window.GUEST_NAME && !globalDashboardState.guestName) {
            globalDashboardState.guestName = window.GUEST_NAME;
            globalDashboardState.guestNameSource = 'template';
        }
        
        // Set phone number from template if available
        if (window.PHONE_NUMBER && !globalDashboardState.phoneNumber) {
            globalDashboardState.phoneNumber = window.PHONE_NUMBER;
        }
        
        // Set property ID from template if available
        if (window.PROPERTY_ID && !globalDashboardState.propertyId) {
            globalDashboardState.propertyId = window.PROPERTY_ID;
        }
        
        console.log("Initialized dashboard state with reservations from template");
        console.log("Dashboard state initialized:", {
            propertyId: globalDashboardState.propertyId,
            guestName: globalDashboardState.guestName,
            phoneNumber: globalDashboardState.phoneNumber,
            reservationsCount: globalDashboardState.reservationsCount
        });
    }
}

// Helper function to select the best reservation based on dates
function selectBestReservation() {
    const reservations = dashboardState.reservations;
    if (!reservations || reservations.length === 0) {
        console.log("No reservations available for selection");
        return;
    }

    console.log("Selecting best reservation from", reservations.length, "reservations");

    const now = new Date();
    let selectedReservation = null;

    // First priority: Find active reservations (current stay)
    const activeReservations = reservations.filter(res => {
        const startDateStr = res.startDate || res.StartDate || res.checkInDate || res.CheckInDate;
        const endDateStr = res.endDate || res.EndDate || res.checkOutDate || res.CheckOutDate;
        return window.DateUtils.isReservationActive(startDateStr, endDateStr);
    });

    if (activeReservations.length > 0) {
        console.log("Found active reservations (current stay):", activeReservations.length);
        // If multiple active reservations, use the one with the latest end date
        activeReservations.sort((a, b) => {
            const aEndDateStr = a.endDate || a.EndDate || a.checkOutDate || a.CheckOutDate;
            const bEndDateStr = b.endDate || b.EndDate || b.checkOutDate || b.CheckOutDate;
            const aEndDate = window.DateUtils.parseDateSafely(aEndDateStr);
            const bEndDate = window.DateUtils.parseDateSafely(bEndDateStr);
            if (!aEndDate || !bEndDate) return 0;
            return bEndDate - aEndDate;
        });
        selectedReservation = activeReservations[0];
    } else {
        // Second priority: Find upcoming reservations
        const upcomingReservations = reservations.filter(res => {
            const startDateStr = res.startDate || res.StartDate || res.checkInDate || res.CheckInDate;
            return window.DateUtils.isReservationUpcoming(startDateStr);
        });

        if (upcomingReservations.length > 0) {
            console.log("Found upcoming reservations:", upcomingReservations.length);
            // Sort by start date to find the earliest upcoming one
            upcomingReservations.sort((a, b) => {
                const aStartDateStr = a.startDate || a.StartDate || a.checkInDate || a.CheckInDate;
                const bStartDateStr = b.startDate || b.StartDate || b.checkInDate || b.CheckInDate;
                const aStartDate = window.DateUtils.parseDateSafely(aStartDateStr);
                const bStartDate = window.DateUtils.parseDateSafely(bStartDateStr);
                if (!aStartDate || !bStartDate) return 0;
                return aStartDate - bStartDate;
            });
            selectedReservation = upcomingReservations[0];
        } else {
            // Last resort: Use the most recent past reservation
            console.log("No active or upcoming reservations found, using most recent past reservation");
            const pastReservations = [...reservations]; // Create a copy
            pastReservations.sort((a, b) => {
                const aEndDateStr = a.endDate || a.EndDate || a.checkOutDate || a.CheckOutDate;
                const bEndDateStr = b.endDate || b.EndDate || b.checkOutDate || b.CheckOutDate;
                const aEndDate = window.DateUtils.parseDateSafely(aEndDateStr);
                const bEndDate = window.DateUtils.parseDateSafely(bEndDateStr);
                if (!aEndDate || !bEndDate) return 0;
                return bEndDate - aEndDate;
            });
            selectedReservation = pastReservations[0];
        }
    }

    if (selectedReservation) {
        // Extract property ID
        const propertyId = selectedReservation.propertyId || selectedReservation.PropertyId || selectedReservation.property_id;

        if (propertyId) {
            console.log("Selected best reservation with property ID:", propertyId);

            // Set as current reservation
            dashboardState.currentReservation = selectedReservation;
            window.currentReservation = selectedReservation; // For backward compatibility

            // Set the property ID
            setConfirmedPropertyId(propertyId);

            // Check for guest name in the selected reservation
            updateGuestNameFromReservation(selectedReservation);
        } else {
            console.warn("Selected reservation has no property ID");
        }
    } else {
        console.warn("Failed to select a reservation");
    }
}

// Export functions and variables for use in other modules
export {
    dashboardState,
    getConfirmedPropertyId as confirmedPropertyId, // For backward compatibility
    getConfirmedPropertyId,
    setConfirmedPropertyId,
    updateGuestName,
    updateGuestNameFromReservation,
    initializeDashboardState,
    selectBestReservation,
    addMessageToChat,
    fetchPropertyDetails,
    fetchPropertyKnowledgeItems,
    createSharedSystemPrompt,
    shouldAllowTestProperties
};
