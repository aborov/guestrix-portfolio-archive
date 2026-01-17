/*
 * Main functionality for the guest dashboard
 */

import {
    dashboardState,
    getConfirmedPropertyId,
    setConfirmedPropertyId,
    addMessageToChat,
    fetchPropertyDetails,
    fetchPropertyKnowledgeItems,
    shouldAllowTestProperties,
    initializeDashboardState
} from './guest_dashboard_utils.js';

import {
    initializeSocketIOProcess,
    checkAndEnableChatButton,
    initializeChat,
    enableChatControls,
    sendTextMessage,
    socket,
    isSocketConnected
} from './guest_dashboard_text_chat.js';

import {
    initializeVoiceCall,
    handleVoiceCallClick,
    stopVoiceCall,
    GEMINI_VOICES,
    currentGeminiVoice,
    currentCallState,
    checkVoiceCallReadiness
} from './guest_dashboard_voice_call.js';

import {
    loadReservations,
    loadPropertyDetails,
    selectProperty,
    findReservationsByPhone,
    currentReservations,
    currentPropertyIndex,
    storedPropertyDetails
} from './guest_dashboard_reservations.js';

// Global variables
let initialPropertyId = null;
let microphoneStream = null;
let audioContext = null;
let audioProcessorNode = null;
let geminiWebSocket = null;
let geminiOutputAudioContext = null;
let audioPlayerQueue = [];
let isGeminiAudioPlaying = false;

// Helper function to update voice call button state
function updateVoiceCallButton(isActive, isDisabled = false, statusText = null) {
    const voiceCallButton = document.getElementById('voice-call-button');
    const voiceTextDesktop = document.querySelector('#voice-call-button .voice-text-desktop');
    const voiceTextMobile = document.querySelector('#voice-call-button .voice-text-mobile');

    if (!voiceCallButton) {
        console.warn("Voice call button not found, cannot update state");
        return;
    }

    // Determine text based on state
    let desktopText, mobileText;
    if (isDisabled) {
        desktopText = statusText || 'Call Unavailable';
        mobileText = 'Unavailable';
    } else if (isActive) {
        desktopText = statusText || 'End Call';
        mobileText = 'End Call';
    } else {
        desktopText = statusText || 'Call Staycee';
        mobileText = 'Call';
    }

    // Update the span text content for both desktop and mobile versions
    if (voiceTextDesktop) {
        voiceTextDesktop.textContent = desktopText;
    }
    if (voiceTextMobile) {
        voiceTextMobile.textContent = mobileText;
    }

    // Update button state
    voiceCallButton.disabled = isDisabled;

    // Update button classes
    if (isDisabled) {
        voiceCallButton.classList.add('disabled');
        voiceCallButton.classList.remove('active');
    } else if (isActive) {
        voiceCallButton.classList.add('active');
        voiceCallButton.classList.remove('disabled');
    } else {
        voiceCallButton.classList.remove('active', 'disabled');
    }
}

// const INACTIVITY_TIMEOUT_MS = 2 * 60 * 1000; // Moved to text_chat.js

// NOTE: handleVoiceCallClick is imported from guest_dashboard_voice_call.js module
// The imported function handles voice call initiation and termination

// Function to create a consistent system prompt for voice interactions
function createVoiceSystemPrompt() {
    console.log("Creating voice system prompt...");

    const systemPrompt =
        "You are Staycee, a helpful concierge assistant for Airbnb guests.\n" +
        "Your goal is to provide direct, polite, accurate, and helpful responses to guest inquiries.\n" +
        "IMPORTANT: You are NOT helping a host respond to guests; you ARE the assistant talking directly to guests.\n" +
        "Only provide information that you are confident is correct.\n" +
        "CRITICAL: When a guest asks about WiFi information, ALWAYS provide the complete WiFi network name and password.\n" +
        "IMPORTANT: You MUST share the property address when asked. The guest is already staying at this property and has the right to know the address.\n" +
        "IMPORTANT: Always use the actual host's name when referring to the host, not generic terms like 'your host'.\n" +
        "Answer in first person as if you're directly communicating with the guest.\n" +
        "Keep your voice responses conversational, concise, and direct.\n\n" +
        "TOOLS USAGE INSTRUCTIONS:\n" +
        "You have access to the following tools to help answer guest questions:\n" +
        "1. google_search: Use this tool to search for general information like local attractions, restaurants, or services near the property.\n" +
        "2. get_current_time: Use this function when guests ask about the current time, date, or when you need to provide time-sensitive information. This will give you the accurate current time in the property's timezone.\n\n" +
        "CRITICAL INSTRUCTIONS FOR USING TOOLS:\n" +
        "- When a guest asks about local attractions, restaurants, or services, use the google_search tool.\n" +
        "- When a guest asks about the current time or date, use the get_current_time function.\n" +
        "- NEVER make up information about the property. If you don't know and can't find the information with tools, say so.\n" +
        "- IMPORTANT: Do not include any technical terms like 'tool_outputs' or function names in your responses to guests.\n" +
        "- CRITICAL: When providing recommendations for activities, restaurants, or places to visit, provide EXACTLY 1 or 2 options only - NEVER more than 2.";

    // Enhanced property context
    let propertyContext = "";
    const propertyId = dashboardState.propertyId || getConfirmedPropertyId();

    if (propertyId) {
        // Get property details from our centralized state or fallback to window object
        const propertyData = dashboardState.propertyDetails || window.propertyDetails || {};

        // Verify we have the correct property details
        if (propertyData.PropertyId === propertyId ||
            propertyData.propertyId === propertyId ||
            (propertyData.PK && propertyData.PK.replace('PROPERTY#', '') === propertyId)) {

            console.log("Using verified property details for voice system prompt");
        } else {
            console.warn("Property details may not match the current property ID. Using available data.");
        }

        // Use the correct property name field (capitalized in API response)
        const propertyName = propertyData.Name || propertyData.name ||
                           dashboardState.propertyName || window.confirmedPropertyName ||
                           "this property";

        // Use the correct host name field (from API with host profile lookup)
        const hostName = propertyData.hostName || propertyData.HostName || "your host";

        // Use the correct address field (capitalized in API response)
        const propertyAddress = propertyData.Address || propertyData.address ||
                              dashboardState.propertyAddress || window.confirmedPropertyAddress ||
                              "the property";

        // Build comprehensive property context
        let propertyContextParts = [
            "PROPERTY INFORMATION:",
            `Property Name: ${propertyName}`,
            `Property ID: ${propertyId}`,
            `Host: ${hostName}`,
            `Address: ${propertyAddress}`
        ];

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

        propertyContextParts.push("\nYou are assisting the guest with this specific property. The guest is verified and has the right to know all property details including the address.");

        propertyContext = "\n\n" + propertyContextParts.join('\n');

        console.log("Added detailed property context to voice system prompt for property:", propertyName);
    } else {
        console.log("No property ID available for voice system prompt");
    }

    const fullPrompt = `${systemPrompt}${propertyContext}`;
    console.log("Enhanced voice system prompt created");
    return fullPrompt;
}

// Function to set up audio processing for Gemini Live (Sends via WebSocket)
function setupGeminiAudioProcessing(micSourceNode, processorNode) {
    // Buffer for audio data
    let audioChunks = []; // Keep this local to the processing setup
    const SEND_INTERVAL = 100; // Send audio every 100ms

    // Function to send buffered audio
    const sendAudioBuffer = () => {
        if (audioChunks.length > 0 && geminiWebSocket && geminiWebSocket.readyState === WebSocket.OPEN && currentCallState === 'active') {
            // Combine all chunks into a single ArrayBuffer
            const combinedLength = audioChunks.reduce((acc, chunk) => acc + chunk.byteLength, 0);
            const combinedBuffer = new Uint8Array(combinedLength);

            let offset = 0;
            for (const chunk of audioChunks) {
                combinedBuffer.set(new Uint8Array(chunk), offset);
                offset += chunk.byteLength;
            }

            // Format audio data according to the Python example
            const base64Audio = btoa(String.fromCharCode.apply(null, new Uint8Array(combinedBuffer.buffer)));

            // Send to Gemini using the format from the Python example
            const message = {
                realtime_input: {
                    media_chunks: [
                        {
                            data: base64Audio,
                            mime_type: "audio/pcm"
                        }
                    ]
                }
            };

            try {
                geminiWebSocket.send(JSON.stringify(message));
            } catch (err) {
                console.error("Error sending audio via WebSocket:", err);
            }

            // Clear buffer
            audioChunks = [];
        }
    };

    // Set up audio processing function
    if (processorNode instanceof AudioWorkletNode) {
        // For AudioWorkletNode
        processorNode.port.onmessage = (event) => {
            if (event.data.audioData) {
                audioChunks.push(event.data.audioData);
            }
        };
    } else {
        // For ScriptProcessorNode
        processorNode.onaudioprocess = (e) => {
            const inputData = e.inputBuffer.getChannelData(0);
            const pcmData = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
                pcmData[i] = Math.max(-32768, Math.min(32767, Math.floor(inputData[i] * 32767)));
            }
            audioChunks.push(pcmData.buffer);
        };
    }

    // Connect audio nodes
    micSourceNode.connect(processorNode);
    if (!(processorNode instanceof AudioWorkletNode)) {
        processorNode.connect(audioContext.destination);
    }

    // Set up interval to send audio data to Gemini
    const sendIntervalId = setInterval(sendAudioBuffer, SEND_INTERVAL);

    // Store interval ID for cleanup
    window.geminiAudioInterval = sendIntervalId;
}

// --- REMOVED: Speech Recognition Functions ---
// initializeSpeechRecognition, stopSpeechRecognition

// --- REMOVED: Old Audio Handling Functions ---
// stopAudioCapture (logic integrated into stopVoiceCall)
// playAudioQueue (replaced by queueGeminiAudio/playNextGeminiAudioChunk)
// handleAudioFromServer


// --- Reservations Logic --- (Legacy function, use loadReservations from guest_dashboard_reservations.js instead)
function mainLoadReservations(userId) {
    console.log("=== MAIN LOAD RESERVATIONS CALLED (LEGACY) ===");
    console.log("This function is deprecated. Use loadReservations() from guest_dashboard_reservations.js instead.");
    console.log("Redirecting to the new loadReservations function...");

    // Call the new function instead
    loadReservations();
    return;
}

// Update Guest and Property Info
// --- REMOVED LEGACY FUNCTION ---

// Property selector has been removed in favor of the switch buttons on reservation cards

// Function to switch to a different property
function switchProperty(propertyId, reservation) {
    // Import the necessary functions from utils
    import('./guest_dashboard_utils.js').then(module => {
        const { dashboardState, setConfirmedPropertyId, fetchPropertyDetails } = module;

        if (propertyId === dashboardState.propertyId) {
            console.log("Already using property", propertyId);
            return;
        }

        console.log("Switching to property:", propertyId);

        // Store the previous property ID for potential "switch back" functionality
        dashboardState.previousPropertyId = dashboardState.propertyId;
        dashboardState.previousReservation = dashboardState.currentReservation;

        // For backward compatibility
        window.previousPropertyId = dashboardState.previousPropertyId;
        window.previousReservation = dashboardState.previousReservation;

        // Update the property ID using setter
        setConfirmedPropertyId(propertyId);

        // Update reservation in our state
        dashboardState.currentReservation = reservation;

        // For backward compatibility
        window.currentReservation = reservation;

        // Clear any existing property details
        dashboardState.propertyDetails = null;
        dashboardState.propertyName = null;
        dashboardState.propertyAddress = null;
        dashboardState.knowledgeItems = null;

        // For backward compatibility
        window.propertyDetails = null;
        window.propertyKnowledgeItems = null;
        window.confirmedPropertyName = null;
        window.confirmedPropertyAddress = null;

        // Fetch the new property details
        fetchPropertyDetails(propertyId)
            .then(propertyDetails => {
                if (propertyDetails) {
                    console.log("Fetched details for new property:", propertyDetails);

                    // Update all reservation cards to show the correct switch buttons
                    updateReservationCards();

                    // If a voice call is active, end it
                    if (currentCallState === 'active' || currentCallState === 'starting') {
                        stopVoiceCall("Property changed - call ended");
                        addMessageToChat("Property changed. Please start a new voice call for the selected property.", "ai");
                    }

                    // If a text chat is active, close it
                    if (isSocketConnected && socket) {
                        socket.close(1000, "Property changed");
                        addMessageToChat("Property changed. Please start a new text chat for the selected property.", "ai");
                    }

                    // Re-enable the chat button
                    if (typeof checkAndEnableChatButton === 'function') {
                        checkAndEnableChatButton();
                    }

                    // The property ID change event will automatically update the voice call button
                }
            })
            .catch(error => {
                console.error("Error fetching details for new property:", error);
                addMessageToChat("Error loading property details. Please try again.", "ai");
            });
    }).catch(error => {
        console.error("Error importing utils for switchProperty:", error);
    });
}

// Function to fetch user data by phone number
async function fetchUserByPhone(phoneNumber) {
    if (!phoneNumber) {
        console.error("Cannot fetch user data: Phone number is missing");
        return null;
    }

    console.log("Fetching user data for phone number:", phoneNumber);
    const endpoint = `/api/users/by-phone/${encodeURIComponent(phoneNumber)}`;
    console.log("Calling endpoint:", endpoint);

    try {
        const response = await fetch(endpoint);
        console.log("User API response status:", response.status);

        if (!response.ok) {
            // If the endpoint doesn't exist or returns an error, don't throw
            // Just log and return null
            console.warn(`Could not fetch user by phone: HTTP status ${response.status}`);
            return null;
        }

        const data = await response.json();
        console.log("User API response data:", data);

        if (data.success && data.user) {
            console.log("Found user data by phone:", data.user);
            return data.user;
        } else {
            console.warn("No user found with phone number:", phoneNumber);
            return null;
        }
    } catch (error) {
        console.error("Error fetching user by phone:", error);
        return null;
    }
}

// Function to update all reservation cards after property switch
function updateReservationCards() {
    // Import the necessary functions from utils
    import('./guest_dashboard_utils.js').then(module => {
        const { dashboardState } = module;

        // Get all reservation cards
        const cards = document.querySelectorAll('.reservation-card');

        cards.forEach(card => {
            const cardPropertyId = card.dataset.propertyId;

            // Update card styling based on whether it's the selected property
            if (cardPropertyId === dashboardState.propertyId) {
                card.classList.add('border-primary');
                card.classList.add('border-2');

                // Scroll to the selected card
                card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

                // Update or remove switch button if it exists
                let switchBtn = card.querySelector('.switch-property-btn');
                if (switchBtn) {
                    // If this is the current property, remove the switch button
                    switchBtn.parentElement.remove();
                }
            } else {
                card.classList.remove('border-primary');
                card.classList.remove('border-2');

                // Check if this card already has a switch button
                let switchBtnContainer = card.querySelector('.switch-property-btn')?.parentElement;

                // If no switch button container exists, create one
                if (!switchBtnContainer) {
                    switchBtnContainer = document.createElement('div');
                    switchBtnContainer.className = 'mt-2';
                    card.querySelector('.card-body').appendChild(switchBtnContainer);

                    // Create the switch button
                    const switchBtn = document.createElement('button');
                    switchBtn.className = 'btn btn-sm btn-outline-primary switch-property-btn';
                    switchBtn.dataset.propertyId = cardPropertyId;

                    // Find the reservation index for this property
                    const reservations = dashboardState.reservations.length > 0 ?
                                        dashboardState.reservations : window.allReservations;

                    const reservationIndex = reservations?.findIndex(res => {
                        const resPropertyId = res.PropertyId || res.propertyId || res.property_id ||
                            (res.PK && res.PK.startsWith('PROPERTY#') ? res.PK.replace('PROPERTY#', '') : null);
                        return resPropertyId === cardPropertyId;
                    });

                    if (reservationIndex !== undefined && reservationIndex >= 0) {
                        switchBtn.dataset.reservationIndex = reservationIndex;

                        // Add event listener
                        switchBtn.addEventListener('click', function() {
                            const propertyId = this.dataset.propertyId;
                            const reservationIndex = parseInt(this.dataset.reservationIndex);
                            const reservation = reservations[reservationIndex];

                            if (propertyId && reservation) {
                                switchProperty(propertyId, reservation);
                            }
                        });

                        // Set button text
                        switchBtn.textContent = 'Switch to this property';

                        // Add the button to the container
                        switchBtnContainer.appendChild(switchBtn);
                    }
                }
            }
        });
    }).catch(error => {
        console.error("Error importing utils for updateReservationCards:", error);
    });
}


// Helper functions fetchPropertyDetails and fetchPropertyKnowledgeItems are imported from guest_dashboard_utils.js

// Render Reservations
function renderReservations(reservations, container) {
    console.log("Using legacy renderReservations function. Delegating to module implementation.");

    // Import the renderReservationCards function from reservations module
    import('./guest_dashboard_reservations.js').then(module => {
        if (module.renderReservationCards) {
            // Call the modular implementation
            module.renderReservationCards(reservations);
            } else {
            console.error("renderReservationCards not found in guest_dashboard_reservations.js");
        }
    }).catch(error => {
        console.error("Error importing renderReservationCards:", error);
    });
}

// --- Initialization --- (Updated to use centralized state management)
document.addEventListener('DOMContentLoaded', async function() {
    console.log("=== GUEST DASHBOARD INITIALIZATION ===");
    console.log("DOM Content Loaded at:", new Date().toISOString());

    // Initialize voiceCallButton reference
    const voiceCallButton = document.getElementById('voice-call-button');
    window.voiceCallButton = voiceCallButton;

    // Firebase will be initialized later in the initialization flow

    // Initialize dashboard state
    initializeDashboardState();

    // Immediate update to guest name from reservations in template data
    if (window.reservations && Array.isArray(window.reservations) && window.reservations.length > 0) {
        console.log("Found reservations in template data, checking for guest info:", window.reservations.length);

        // Check each reservation for potential guest name
        for (const reservation of window.reservations) {
            // First normalize the reservation to ensure consistent field access
            const normalizedReservation = {
                ...reservation,
                additionalContacts: reservation.additionalContacts ||
                                    reservation.AdditionalContacts ||
                                    reservation.additional_contacts || []
            };

            // Check if this reservation has additional contacts matching user phone
            const phoneNumber = window.PHONE_NUMBER;
            if (phoneNumber && normalizedReservation.additionalContacts.length > 0) {
                console.log(`Checking ${normalizedReservation.additionalContacts.length} contacts for match with ${phoneNumber}`);
                console.log("Additional contacts:", normalizedReservation.additionalContacts);

                // Find contact with matching phone
                const matchingContact = normalizedReservation.additionalContacts.find(contact =>
                    (contact.phone === phoneNumber) ||
                    (phoneNumber.length >= 4 && contact.phone && contact.phone.length >= 4 &&
                     contact.phone.slice(-4) === phoneNumber.slice(-4))
                );

                if (matchingContact && matchingContact.name) {
                    console.log("★★★ Found matching contact with name:", matchingContact.name);
                    // Update guest name with high priority source
                    if (typeof updateGuestName === 'function') {
                        updateGuestName(matchingContact.name, 'additional-contact-exact-match');
                    } else {
                        // Direct update as fallback
                        dashboardState.guestName = matchingContact.name;
                        window.GUEST_NAME = matchingContact.name;
                        // Force DOM update
                        const guestNameElement = document.getElementById('guest-name');
                        if (guestNameElement) {
                            guestNameElement.textContent = matchingContact.name;
                        }
                    }
                    break; // Found a match, no need to check other reservations
                }
            }
        }
    }

    // Get the property ID and user info from the template data
    const templateData = document.getElementById('template-data');
    if (templateData) {
        // Get URL parameter for property ID (highest priority)
        const urlParams = new URLSearchParams(window.location.search);
        const urlPropertyId = urlParams.get('property_id') || urlParams.get('propertyId');

        // Store URL property ID if available, but don't set it as confirmed yet
        // We'll let the reservation selection logic handle that
        if (urlPropertyId) {
            initialPropertyId = urlPropertyId;
            console.log("Found property ID in URL parameters:", urlPropertyId);
        }

        // Get user information
        const userId = templateData.dataset.userId || null;
        const guestName = templateData.dataset.guestName || "Guest";
        const guestNameSource = templateData.dataset.guestNameSource || 'template';
        const phoneNumber = templateData.dataset.phoneNumber || null;

        // Store user info in both dashboardState and window (for backward compatibility)
        dashboardState.userId = userId;
        dashboardState.phoneNumber = phoneNumber;

        // Use the proper priority system for guest name initialization
        // Import and use updateGuestName to ensure proper priority handling
        import('./guest_dashboard_utils.js').then(module => {
            const { updateGuestName } = module;
            updateGuestName(guestName, guestNameSource);
            console.log(`Initialized guest name: "${guestName}" from source: ${guestNameSource}`);

            // Force update of all UI elements after initialization
            setTimeout(() => {
                if (typeof updateGuestNameDisplay === 'function') {
                    updateGuestNameDisplay();
                }
            }, 100);
        }).catch(error => {
            console.error("Error importing updateGuestName during initialization:", error);
            // Fallback to direct assignment
            dashboardState.guestName = guestName;
            dashboardState.guestNameSource = guestNameSource;
            window.GUEST_NAME = guestName;

            // Force update of all UI elements after fallback initialization
            setTimeout(() => {
                if (typeof updateGuestNameDisplay === 'function') {
                    updateGuestNameDisplay();
                }
            }, 100);
        });

        window.CURRENT_USER_ID = userId;
        window.PHONE_NUMBER = phoneNumber;

        console.log("User ID:", userId);
        console.log("Guest name:", dashboardState.guestName);
        console.log("Phone number:", phoneNumber ? "Available" : "Not available");
    } else {
        console.error("Template data element not found - critical initialization error");
        // Show error message
        const mainContainer = document.querySelector('.container');
        if (mainContainer) {
            mainContainer.innerHTML = `
            <div class="alert alert-danger mt-4">
                <h4>Initialization Error</h4>
                <p>Could not load dashboard data. Please refresh the page or try again later.</p>
            </div>`;
        }
        return;
    }

    // Make sure updateGuestNameDisplay is defined and accessible
    if (typeof updateGuestNameDisplay !== 'function') {
        console.error("updateGuestNameDisplay function is not defined. This will cause errors!");
    } else {
        console.log("updateGuestNameDisplay function is properly defined");
    }

    // Set initial guest name
    updateGuestNameDisplay();

    // Wait for Firebase to be securely initialized before proceeding
    try {
        console.log('Waiting for Firebase to initialize securely...');
        await window.initializeFirebaseSecurely();
        console.log('Firebase initialized successfully');
        window.firebaseReady = true;
    } catch (error) {
        console.error('Firebase initialization failed:', error);
        window.firebaseReady = false;
        
        // Show user-friendly error message
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-warning mt-3';
        errorDiv.innerHTML = `
            <strong>Notice:</strong> Some features may be limited due to initialization issues. 
            If you experience problems, please refresh the page.
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        const container = document.querySelector('.container');
        if (container) {
            container.insertBefore(errorDiv, container.firstChild);
        }
    }

    // Add an auth state listener to load reservations on successful auth
    async function setupAuthStateListener() {
        try {
            // Initialize Firebase first using our async initialization
            const firebaseInitialized = await initializeFirebase();
            if (!firebaseInitialized) {
                console.warn('Firebase initialization failed, skipping auth state listener setup');
                return;
            }
            
            // Check if Firebase is ready before setting up auth listener
            if (!window.firebaseReady && typeof firebase !== 'undefined' && firebase.apps && firebase.apps.length > 0) {
                window.firebaseReady = true;
            }
            
            if (!window.firebaseReady) {
                console.warn('Firebase not ready, skipping auth state listener setup');
                return;
            }
            
            // Now safely access firebase.auth()
            firebase.auth().onAuthStateChanged(function(user) {
        console.log("=== AUTH STATE CHANGED ===");
        if (user) {
            console.log("User is signed in:", user.uid);

            // Update user ID in both dashboardState and window
            dashboardState.userId = user.uid;
            window.CURRENT_USER_ID = user.uid;

            // Update user name if available
            if (user.displayName) {
                dashboardState.guestName = user.displayName;
                window.GUEST_NAME = user.displayName;
                console.log("Updated guest name from Firebase auth:", user.displayName);

                // Update the UI
                updateGuestNameDisplay();
            }

            // Update user phone if available
            if (user.phoneNumber) {
                dashboardState.phoneNumber = user.phoneNumber;
                window.PHONE_NUMBER = user.phoneNumber;
                console.log("Updated phone number from Firebase auth:", user.phoneNumber);
            }

            // Check if we should load reservations
            console.log("Checking if reservations should be loaded after auth...");
            if (!window.reservationsLoaded && !window.isLoadingReservations) {
                console.log("Loading reservations after auth state change");
                window.reservationsLoaded = true;

                // Use the imported function from guest_dashboard_reservations.js
                loadReservations();
            } else {
                console.log("Reservations already loaded or in progress after auth");
            }

            // Run a check on the voice call button to see if it can be enabled now
            if (typeof checkVoiceCallReadiness === 'function') {
                console.log("Running voice call readiness check after auth...");
                checkVoiceCallReadiness();
            } else {
                console.log("checkVoiceCallReadiness not defined yet");
                // If the function isn't defined yet, wait a bit and try again
                setTimeout(() => {
                    if (typeof checkVoiceCallReadiness === 'function') {
                        console.log("Running delayed voice call readiness check");
                        checkVoiceCallReadiness();
                    }
                }, 1000);
            }

            // Enable chat button if property ID is available
            const confirmedId = getConfirmedPropertyId();
            if (typeof checkAndEnableChatButton === 'function' && confirmedId) {
                console.log("Running chat button check after auth...");
                checkAndEnableChatButton();
            }
        } else {
            console.log("User is signed out");
        }
    });
    
    } catch (error) {
        console.error("Error setting up auth state listener:", error);
    }
}

// Call the async function to setup auth state listener
setupAuthStateListener();

    // Initialize Socket.IO process for text chat
    initializeSocketIOProcess();

    // Initialize chat UI listeners
    initializeChat();

    // Initialize voice call button listener (if element exists)
    if (voiceCallButton) {
        // Initial state - disabled until property ID and user ID are confirmed
        updateVoiceCallButton(false, true, "Loading...");
        voiceCallButton.addEventListener('click', handleVoiceCallClick);

        // Initialize voice selector dropdown
        try {
            if (typeof initializeVoiceSelector === 'function') {
            initializeVoiceSelector();
            } else {
                // Define the missing function for voice selector initialization
                window.initializeVoiceSelector = function() {
                    const voiceSelector = document.getElementById('voice-selector');
                    if (!voiceSelector) {
                        console.log("Voice selector not found in the DOM");
                        return;
                    }

                    // Get available voices (you might need to adjust this based on your actual implementation)
                    const availableVoices = ['Aoede', 'Calliope', 'Thalia', 'Default'];

                    // Populate the selector
                    availableVoices.forEach(voice => {
                        const option = document.createElement('option');
                        option.value = voice;
                        option.textContent = voice;
                        voiceSelector.appendChild(option);
                    });

                    // Set default voice
                    const defaultVoice = 'Aoede';
                    voiceSelector.value = defaultVoice;
                    window.selectedVoice = defaultVoice;

                    // Add change listener
                    voiceSelector.addEventListener('change', function() {
                        window.selectedVoice = this.value;
                        console.log(`Voice changed to: ${window.selectedVoice}`);
                    });

                    console.log(`Using Gemini voice: ${window.selectedVoice}`);
                };

                // Execute the newly defined function
                window.initializeVoiceSelector();
            }
        } catch (e) {
            console.error("Error initializing voice selector:", e);
        }

        // Use the imported checkVoiceCallReadiness function
        window.checkVoiceCallReadiness = checkVoiceCallReadiness;

        // Do an initial check
        setTimeout(() => {
            try {
                checkVoiceCallReadiness();
            } catch (e) {
                console.error("Error in initial voice call readiness check:", e);
            }
        }, 500);

    } else {
        console.warn("Voice call button not found.");
    }

    // Check if we've already attempted to load reservations to prevent duplicate calls
    console.log("=== CHECKING RESERVATION LOADING CONDITION ===");
    console.log("reservationsLoaded:", window.reservationsLoaded);
    console.log("isLoadingReservations:", window.isLoadingReservations);
    console.log("CURRENT_USER_ID:", window.CURRENT_USER_ID);

    // Load reservations if we have a user ID or phone number
    const userId = dashboardState.userId || window.CURRENT_USER_ID;
    const phoneNumber = dashboardState.phoneNumber || window.PHONE_NUMBER;

    if (!window.reservationsLoaded && !window.isLoadingReservations) {
        window.reservationsLoaded = true;
        console.log("First time loading reservations");

        // Show loading indicator
        const loadingDiv = document.getElementById('loading-reservations');
        if (loadingDiv) {
            loadingDiv.style.display = 'block';
        }

        if (userId || phoneNumber) {
            console.log("Loading reservations using imported function");
            // Use the imported function from guest_dashboard_reservations.js
            loadReservations();
        } else {
            console.error('No user ID or phone number found. Cannot load reservations.');
            const loadingDiv = document.getElementById('loading-reservations');
            const noReservationsDiv = document.getElementById('no-reservations');
            const reservationsListDiv = document.getElementById('reservations-list');
            if(loadingDiv) loadingDiv.style.display = 'none';
            if(reservationsListDiv) reservationsListDiv.style.display = 'none';
            if(noReservationsDiv) {
                noReservationsDiv.style.display = 'block';
                noReservationsDiv.innerHTML = '<p class="text-danger">Could not identify user. Reservations cannot be loaded.</p>';
            }

            // Even if user ID is missing, try to use the initial property ID from the template
            if (initialPropertyId) {
                console.log("No user ID found, but using initial property ID:", initialPropertyId);

                // Set the confirmed property ID using the setter function
                setConfirmedPropertyId(initialPropertyId);

                // Fetch property details
                fetchPropertyDetails(initialPropertyId)
                    .then(propertyDetails => {
                        if (propertyDetails) {
                            console.log("Fetched property details:", propertyDetails);

                            // Enable chat button
                            if (typeof checkAndEnableChatButton === 'function') {
                                checkAndEnableChatButton();
                            }
                        }
                    })
                    .catch(error => {
                        console.error("Error fetching property details:", error);
                    });
            }

            // Update UI elements
            const startTextChatButton = document.getElementById('start-text-chat');
            if(startTextChatButton && !initialPropertyId) {
                startTextChatButton.disabled = true;
                startTextChatButton.textContent = "Login Error";
            }
        }
    } else {
        console.log("Reservations already loaded or in progress, not loading again");
    }

    // Initialize voice call
    initializeVoiceCall();

    // Check if text chat button can be enabled based on current state
    checkAndEnableChatButton();

    // Expose functions for modal access
    window.selectProperty = selectProperty;
    window.loadReservations = loadReservations;

    console.log("Guest dashboard initialization complete");
});

// Helper function to initialize Firebase
async function initializeFirebase() {
    // If Firebase is already initialized, return early
    if (typeof firebase !== 'undefined' && firebase.apps && firebase.apps.length > 0) {
        console.log("Firebase already initialized, using existing instance");
        return true;
    }

    if (typeof firebase === 'undefined') {
        console.error("Firebase SDK not loaded");
        return false;
    }

    // First try to use the global secure initialization function from the template
    if (typeof window.initializeFirebaseSecurely === 'function') {
        try {
            console.log("Using secure Firebase initialization from template...");
            await window.initializeFirebaseSecurely();
            console.log("Firebase initialized securely via template");
            return true;
        } catch (error) {
            console.error("Secure Firebase initialization failed:", error);
            // Fall back to other methods
        }
    }

    // Try to initialize with config data
    if (window.firebaseConfigData) {
        try {
            console.log("Initializing Firebase with config data:", window.firebaseConfigData);
            firebase.initializeApp(window.firebaseConfigData);
            console.log("Firebase initialized successfully");
            return true;
        } catch (error) {
            if (error.code === 'app/duplicate-app') {
                console.log("Firebase already initialized (duplicate app error)");
                return true;
            } else {
                console.error("Firebase initialization error:", error);
                return false;
            }
        }
    } else {
        // Try to find Firebase config data in script tags
        try {
            const scripts = document.querySelectorAll('script');
            for (let i = 0; i < scripts.length; i++) {
                const scriptContent = scripts[i].textContent;
                if (scriptContent && scriptContent.includes('firebase.initializeApp') && scriptContent.includes('firebaseConfigData')) {
                    // Extract the config
                    const configMatch = scriptContent.match(/JSON\.parse\('(.+?)'\)/);
                    if (configMatch && configMatch[1]) {
                        window.firebaseConfigData = JSON.parse(configMatch[1]);
                        console.log("Extracted Firebase config from script tag");

                        // Initialize Firebase with the extracted config
                        try {
                            firebase.initializeApp(window.firebaseConfigData);
                            console.log("Firebase initialized with extracted config");
                            return true;
                        } catch (initError) {
                            if (initError.code === 'app/duplicate-app') {
                                console.log("Firebase already initialized (duplicate app error after extraction)");
                                return true;
                            } else {
                                console.error("Firebase initialization error after extraction:", initError);
                            }
                        }
                        break;
                    }
                }
            }
        } catch (error) {
            console.error("Error extracting Firebase config from script tag:", error);
        }
    }

    console.warn("Firebase config data not available, Firebase may not work correctly");
    return false;
}

// --- Logout Function --- (Updated to handle magic link sessions)
function logout() {
    console.log("Attempting logout...");
    
    // Determine which logout endpoint to use based on context
    const magicToken = document.body.dataset.magicLinkToken || 
                      (typeof window.MAGIC_LINK_TOKEN !== 'undefined' ? window.MAGIC_LINK_TOKEN : null) ||
                      (document.querySelector('input[name="magic_link_token"]') ? document.querySelector('input[name="magic_link_token"]').value : null);
                      
    let logoutUrl = '/auth/logout'; // Default logout
    
    if (magicToken && magicToken !== '' && magicToken !== 'None') {
        logoutUrl = '/magic/logout'; // Use magic link specific logout
        console.log("Using magic link logout endpoint");
    } else {
        console.log("Using regular logout endpoint");
    }
    
    // First clear the server-side session (both regular and magic link)
    fetch(logoutUrl, { 
        method: 'GET', 
        headers: {
            'Content-Type': 'application/json'
        },
        credentials: 'same-origin' // Include cookies in the request
    })
    .then(response => {
        console.log('Server logout response:', response.status);
        // Then sign out from Firebase if available
        if (typeof firebase !== 'undefined' && firebase.auth) {
            return firebase.auth().signOut();
        } else {
            return Promise.resolve();
        }
    })
    .then(() => {
        console.log('User signed out successfully from both server and Firebase');
        window.location.href = '/';
    })
    .catch((error) => {
        console.error('Error during logout process:', error);
        // Try to redirect anyway
        window.location.href = '/';
    });
}

// Helper function to set up the voice simulation with a chat session
function setupVoiceSimulation(chat) {
    console.log("Setting up simulated live voice session...");
    geminiLiveSession = {
        chat: chat,
        sendAudio: async function(audioData) {
            try {
                addMessageToChat("(Your voice would be processed here in a real implementation)", "user");
                await new Promise(resolve => setTimeout(resolve, 500));
                const result = await chat.sendMessage("How can I help you with your stay today?");
                const response = result.response;
                console.log("Gemini response:", response.text());
                addMessageToChat(response.text(), "ai");
                return response.text();
            } catch (err) {
                console.error("Error in simulated audio processing:", err);
                return null;
            }
        }
    };

    // Set up the audio processor (only if we have the node ready)
    if (audioProcessorNode) {
        audioProcessorNode.onaudioprocess = (audioProcessingEvent) => {
            // Only needed to keep the audio context running
        };
        micSourceNode.connect(audioProcessorNode);
        audioProcessorNode.connect(audioContext.destination);
    }

    // Set up a simple interaction - when the user clicks the chat area, simulate sending audio
    chatMessages.addEventListener('click', async () => {
        if (currentCallState === 'active' && geminiLiveSession) {
            addMessageToChat("(You clicked to simulate speaking...)", "user");
            await geminiLiveSession.sendAudio(null);
        }
    });

    // Explain to the user that this is a limited implementation
    addMessageToChat("Voice call connected to AI assistant. Note: This is a simplified implementation without real voice processing.", "ai");

    // Simulate an initial greeting
    setTimeout(() => {
        addMessageToChat("Hello! I'm Staycee, your concierge for this property. How can I help you today?", "ai");
    }, 1000);

    // Update State and UI
    currentCallState = 'active';
    updateVoiceCallButton(true);
}

// Helper function to set up a fallback experience without the Gemini SDK
function setupFallbackExperience() {
    console.log("Setting up complete fallback experience with pre-defined responses");

    // Create a completely simulated experience with predefined responses
    geminiLiveSession = {
        sendAudio: async function(audioData) {
            try {
                addMessageToChat("(Your voice would be processed here in a real implementation)", "user");

                // Wait a bit to simulate processing
                await new Promise(resolve => setTimeout(resolve, 800));

                // Get a predefined response
                const responses = [
                    "I'd be happy to help with that! What specific information do you need about your stay?",
                    "Of course! I can assist with local recommendations, property amenities, or any questions about your reservation.",
                    "I understand. Is there anything specific about the property you'd like to know?",
                    "I can help with that. Would you like me to provide more details?",
                    "That's a great question. Let me tell you about the local attractions near your property."
                ];

                // Select a random response
                const randomResponse = responses[Math.floor(Math.random() * responses.length)];
                addMessageToChat(randomResponse, "ai");
                return randomResponse;
            } catch (err) {
                console.error("Error in fallback experience:", err);
                return null;
            }
        }
    };

    // Set up click interaction for fallback with visual feedback
    chatMessages.addEventListener('click', async () => {
        if (currentCallState === 'active' && geminiLiveSession) {
            // Make it very clear that clicking activates a simulated response
            const clickArea = document.createElement('div');
            clickArea.className = 'chat-message user-message';
            clickArea.textContent = "👆 You clicked to simulate speaking...";
            clickArea.style.backgroundColor = "#ffe8cc"; // Highlight color
            chatMessages.appendChild(clickArea);
            chatMessages.scrollTop = chatMessages.scrollHeight;

            // Show typing indicator
            const typingIndicator = document.createElement('div');
            typingIndicator.className = 'chat-message ai-message';
            typingIndicator.textContent = "AI is thinking...";
            typingIndicator.style.fontStyle = "italic";
            chatMessages.appendChild(typingIndicator);
            chatMessages.scrollTop = chatMessages.scrollHeight;

            // Process the simulated audio after a delay
            await new Promise(resolve => setTimeout(resolve, 800));

            // Remove typing indicator
            chatMessages.removeChild(typingIndicator);

            // Get response
            await geminiLiveSession.sendAudio(null);
        }
    });

    // Initial messages with clear indication this is a fallback
    addMessageToChat("Voice call connected in FALLBACK MODE. Gemini Live API could not be initialized.", "ai");

    // Show instructions with a delay
        setTimeout(() => {
        addMessageToChat("Hello! I'm your AI assistant for this property. Click anywhere in this chat area to simulate speaking to me.", "ai");
        }, 1000);

    // Automatic follow-up message to make the experience more interactive without requiring user action
    setTimeout(() => {
        addMessageToChat("I can help with information about your reservation, local attractions, or property amenities. What would you like to know?", "ai");
    }, 3000);

    // After a longer delay, prompt the user more directly to interact
    setTimeout(() => {
        const helpMsg = document.createElement('div');
        helpMsg.className = 'chat-message ai-message';
        helpMsg.textContent = "👉 Reminder: Click anywhere in this chat area to simulate speaking. I'll respond with pre-defined answers.";
        helpMsg.style.backgroundColor = "#e6f7ff"; // Light blue background
        helpMsg.style.fontWeight = "bold";
        chatMessages.appendChild(helpMsg);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }, 6000);

    // Update State and UI
    currentCallState = 'active';
    updateVoiceCallButton(true, false, "End Fallback Call");
}

// DEBUG: Function to analyze audio data
function analyzeAudioData(audioDataArrayBuffer) {
    // Convert to Int16Array for analysis (signed 16-bit PCM)
    // Creating a direct view so we can properly see the values
    const view = new DataView(audioDataArrayBuffer);
    const samples = Math.floor(audioDataArrayBuffer.byteLength / 2);

    // For diagnostics, collect both signed and unsigned interpretations
    const signedValues = [];
    const unsignedValues = [];

    for (let i = 0; i < Math.min(samples, 2000); i++) { // Cap at 2000 samples to avoid excessive processing
        signedValues.push(view.getInt16(i * 2, true));
        unsignedValues.push(view.getUint16(i * 2, true));
    }

    // Calculate statistics for signed interpretation
    let signedMin = signedValues[0] || 0;
    let signedMax = signedValues[0] || 0;
    let signedSum = 0;
    let zeroCount = 0;
    let closeToMaxCount = 0;
    let closeToMinCount = 0;

    for (let i = 0; i < signedValues.length; i++) {
        const value = signedValues[i];
        if (value < signedMin) signedMin = value;
        if (value > signedMax) signedMax = value;
        signedSum += value;

        if (value === 0) zeroCount++;
        if (value > 30000) closeToMaxCount++;
        if (value < -30000) closeToMinCount++;
    }

    const signedAvg = signedSum / signedValues.length;

    // Calculate statistics for unsigned interpretation
    let unsignedMin = unsignedValues[0] || 0;
    let unsignedMax = unsignedValues[0] || 0;
    let unsignedSum = 0;

    for (let i = 0; i < unsignedValues.length; i++) {
        const value = unsignedValues[i];
        if (value < unsignedMin) unsignedMin = value;
        if (value > unsignedMax) unsignedMax = value;
        unsignedSum += value;
    }

    const unsignedAvg = unsignedSum / unsignedValues.length;

    // Log detailed diagnostics with both interpretations
    console.log(`Audio data analysis (${audioDataArrayBuffer.byteLength} bytes):`);
    console.log(`- Total samples: ${samples}`);
    console.log("SIGNED INTERPRETATION (getInt16):");
    console.log(`- Min value: ${signedMin}`);
    console.log(`- Max value: ${signedMax}`);
    console.log(`- Average value: ${signedAvg.toFixed(2)}`);
    console.log(`- Zero values: ${zeroCount} (${(zeroCount/signedValues.length*100).toFixed(2)}%)`);
    console.log(`- Near max (+30000): ${closeToMaxCount} (${(closeToMaxCount/signedValues.length*100).toFixed(2)}%)`);
    console.log(`- Near min (-30000): ${closeToMinCount} (${(closeToMinCount/signedValues.length*100).toFixed(2)}%)`);

    console.log("UNSIGNED INTERPRETATION (getUint16):");
    console.log(`- Min value: ${unsignedMin}`);
    console.log(`- Max value: ${unsignedMax}`);
    console.log(`- Average value: ${unsignedAvg.toFixed(2)}`);

    // First few bytes as hex for debugging headers or patterns
    let firstBytes = '';
    for (let i = 0; i < Math.min(32, audioDataArrayBuffer.byteLength); i++) {
        const byte = new Uint8Array(audioDataArrayBuffer)[i];
        firstBytes += byte.toString(16).padStart(2, '0') + ' ';
    }
    console.log(`- First bytes (hex): ${firstBytes}`);

    // Check DC offset in signed interpretation
    if (Math.abs(signedAvg) > 1000) {
        console.warn(`Audio data has a significant DC offset (signed): ${signedAvg.toFixed(2)}`);
    }

    // Look for potential clipping
    if (closeToMaxCount + closeToMinCount > signedValues.length * 0.05) {
        console.warn(`Potential clipping detected in ${(closeToMaxCount + closeToMinCount)} samples (${((closeToMaxCount + closeToMinCount)/signedValues.length*100).toFixed(2)}%)`);
    }

    // Look for empty data
    if (signedMax - signedMin < 100) {
        console.warn("Very low dynamic range - possibly silence or encrypted/compressed data");
    }
}

// --- Update queueGeminiAudio ---
function queueGeminiAudio(audioDataArrayBuffer) {
    if (!(audioDataArrayBuffer instanceof ArrayBuffer)) {
         console.error("queueGeminiAudio received non-ArrayBuffer data:", audioDataArrayBuffer);
        return;
    }

    // If the buffer is too small, ignore it
    if (audioDataArrayBuffer.byteLength < 256) {
        console.log(`Ignoring small ArrayBuffer (${audioDataArrayBuffer.byteLength} bytes).`);
        return;
    }

    // Diagnostic info about the buffer size and sample count
    const sampleCount = Math.floor(audioDataArrayBuffer.byteLength / 2);
    console.log(`Queuing audio: ${audioDataArrayBuffer.byteLength} bytes, ~${sampleCount} samples, ~${(sampleCount/GEMINI_OUTPUT_SAMPLE_RATE).toFixed(2)}s duration`);

    // DEBUG: Analyze the audio data (but only for every 3rd chunk to reduce log noise)
    if (Math.random() < 0.33) { // Only analyze ~33% of chunks
        analyzeAudioData(audioDataArrayBuffer);
    }

    // Create a new audio context with the correct sample rate if it doesn't exist
    if (!geminiOutputAudioContext) {
        geminiOutputAudioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: GEMINI_OUTPUT_SAMPLE_RATE,
            latencyHint: 'interactive' // Use interactive for potentially lower latency
        });
        console.log(`Created audio context with sample rate: ${geminiOutputAudioContext.sampleRate}`);
        // Reset next chunk start time when context is created/recreated
        nextChunkStartTime = 0;
    }

    // Ensure context is running
    if (geminiOutputAudioContext.state === 'suspended') {
        geminiOutputAudioContext.resume();
    }

    // Add to queue
    const wasQueueEmpty = audioPlayerQueue.length === 0;
    audioPlayerQueue.push(audioDataArrayBuffer);

    // If queue is getting too long, remove oldest chunks
    const MAX_QUEUE_SIZE = 20; // Increased queue size slightly
    if (audioPlayerQueue.length > MAX_QUEUE_SIZE) {
        const removed = audioPlayerQueue.splice(0, audioPlayerQueue.length - MAX_QUEUE_SIZE);
        console.log(`Queue too long - removed ${removed.length} old audio chunks`);
    }

    // Start playback ONLY if the queue was empty before adding this chunk
    if (wasQueueEmpty) {
        playNextGeminiAudioChunk();
    }
}

// --- Update playNextGeminiAudioChunk (Revert decode, keep scheduling) ---

// Keep track of the scheduled end time of the last played chunk
let nextChunkStartTime = 0;

async function playNextGeminiAudioChunk() {
    if (audioPlayerQueue.length === 0 || !geminiOutputAudioContext) {
        console.log("Audio queue empty or context not ready.");
        return;
    }

    // Get the next chunk from the queue
    const audioDataArrayBuffer = audioPlayerQueue.shift();

    try {
        // --- REVERTED PART: Manually create buffer and fill channel data ---
        const numSamples = Math.floor(audioDataArrayBuffer.byteLength / 2);
        if (numSamples === 0) {
            console.log("Skipping empty audio chunk.");
             // Schedule the next chunk immediately if available
            if (audioPlayerQueue.length > 0) {
                setTimeout(playNextGeminiAudioChunk, 5);
            }
            return;
        }

        const audioBuffer = geminiOutputAudioContext.createBuffer(
            1, // mono
            numSamples,
            GEMINI_OUTPUT_SAMPLE_RATE
        );
        const channelData = audioBuffer.getChannelData(0);
        const view = new DataView(audioDataArrayBuffer);

        for (let i = 0; i < numSamples; i++) {
            const int16Sample = view.getInt16(i * 2, true); // little-endian
            channelData[i] = int16Sample / 32768.0; // Convert to float [-1.0, 1.0]
        }
        // --- END REVERTED PART ---

        // --- KEEP Scheduling logic ---
        const source = geminiOutputAudioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(geminiOutputAudioContext.destination);

        const currentTime = geminiOutputAudioContext.currentTime;
        // Ensure playAtTime is not in the past, add a tiny buffer if needed
        const playAtTime = Math.max(currentTime + 0.005, nextChunkStartTime);

        source.start(playAtTime);
        console.log(`Scheduled audio chunk (${audioBuffer.duration.toFixed(2)}s) to play at ${playAtTime.toFixed(2)} (context time: ${currentTime.toFixed(2)})`);

        // Update the start time for the *next* chunk
        nextChunkStartTime = playAtTime + audioBuffer.duration;
        // --- END Scheduling logic ---

        source.onended = () => {
            console.log(`Audio chunk playback finished.`);
            // The check for the next chunk is now done after scheduling.
        };

    } catch (error) {
        console.error("Error creating buffer or playing audio chunk:", error);
        // Reset nextChunkStartTime on error to prevent runaway scheduling?
        nextChunkStartTime = geminiOutputAudioContext ? geminiOutputAudioContext.currentTime : 0;
    }

    // --- KEEP Proactive queue check ---
    if (audioPlayerQueue.length > 0) {
        setTimeout(playNextGeminiAudioChunk, 5);
    }
    // --- END Proactive queue check ---
}

// Helper function to convert base64 to ArrayBuffer with better error handling
function base64ToArrayBuffer(base64) {
    if (!base64 || typeof base64 !== 'string') {
        console.warn("Invalid base64 input:", base64);
        return new ArrayBuffer(0); // Return empty buffer
    }

    try {
        // Clean up the base64 string first
        let cleanBase64 = base64;

        // Check for and remove data URI prefix if present
        if (base64.startsWith('data:')) {
            const commaIndex = base64.indexOf(',');
            if (commaIndex !== -1) {
                cleanBase64 = base64.substring(commaIndex + 1);
                console.log("Removed data URI prefix from base64 string");
            }
        }

        // Remove any whitespace
        cleanBase64 = cleanBase64.replace(/\s/g, '');

        // Add padding if needed
        while (cleanBase64.length % 4 !== 0) {
            cleanBase64 += '=';
        }

        // Log the first and last few characters for debugging
        const previewLength = 20;
        const startPreview = cleanBase64.substring(0, previewLength);
        const endPreview = cleanBase64.length > previewLength * 2 ?
                        cleanBase64.substring(cleanBase64.length - previewLength) : '';
        console.log(`Converting base64 to ArrayBuffer (length: ${cleanBase64.length}) - Start: ${startPreview}... End: ...${endPreview}`);

        // Convert base64 to binary string
        const binaryString = window.atob(cleanBase64);
        console.log(`Binary string length: ${binaryString.length} bytes`);

        // Create ArrayBuffer and Uint8Array
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        return bytes.buffer;
    } catch (error) {
        console.error("Error converting base64 to ArrayBuffer:", error);
        console.log("Failed base64 string (first 100 chars):", base64.substring(0, 100));
        return new ArrayBuffer(0); // Return empty buffer on error
    }
}

// Helper function to recursively search for audio data in a JSON object
function findAudioDataInJson(jsonObj, path = '') {
    // Base case: null or undefined
    if (jsonObj === null || jsonObj === undefined) {
        return [];
    }

    // Base case: primitive value
    if (typeof jsonObj !== 'object') {
        // Check if this is a base64 string that looks like audio data
        if (typeof jsonObj === 'string' &&
            jsonObj.length > 100 &&
            /^[A-Za-z0-9+/=]+$/.test(jsonObj)) {

            console.log(`Potential base64 audio data found at ${path}`);
            return [{path, data: jsonObj, type: 'base64'}];
        }
        return [];
    }

    // Handle arrays
    if (Array.isArray(jsonObj)) {
        let results = [];
        for (let i = 0; i < jsonObj.length; i++) {
            const newPath = path ? `${path}[${i}]` : `[${i}]`;
            results = results.concat(findAudioDataInJson(jsonObj[i], newPath));
        }
        return results;
    }

    // Handle objects
    let results = [];

    // Check if this object has keys that suggest it's audio data
    const audioKeys = ['audio', 'audioData', 'sound', 'media', 'data'];
    const hasAudioKey = Object.keys(jsonObj).some(key => audioKeys.includes(key.toLowerCase()));

    if (hasAudioKey) {
        console.log(`Object with potential audio keys found at ${path}`, jsonObj);
    }

    // Check for specific patterns in the JSON structure

    // Pattern 1: Check for audio in inlineData (common Gemini pattern)
    if (jsonObj.inlineData && jsonObj.inlineData.mimeType &&
        jsonObj.inlineData.mimeType.includes('audio') &&
        jsonObj.inlineData.data) {

        console.log(`Found inline audio data at ${path}.inlineData`);
        results.push({
            path: `${path}.inlineData.data`,
            data: jsonObj.inlineData.data,
            type: 'base64',
            mimeType: jsonObj.inlineData.mimeType
        });
    }

    // Pattern 2: Check for raw audio data in Gemini Live format
    if (path.includes('parts') && jsonObj.audioContent) {
        console.log(`Found audioContent in ${path}`);
        results.push({
            path: `${path}.audioContent`,
            data: jsonObj.audioContent,
            type: 'base64'
        });
    }

    // Pattern 3: Check for candidate format
    if (jsonObj.candidates &&
        Array.isArray(jsonObj.candidates) &&
        jsonObj.candidates.length > 0 &&
        jsonObj.candidates[0].content) {

        const candidate = jsonObj.candidates[0];
        if (candidate.content.parts &&
            Array.isArray(candidate.content.parts) &&
            candidate.content.parts.length > 0) {

            const part = candidate.content.parts[0];
            if (part.audioContent) {
                console.log(`Found audioContent in candidate at ${path}`);
                results.push({
                    path: `${path}.candidates[0].content.parts[0].audioContent`,
                    data: part.audioContent,
                    type: 'base64'
                });
            }
        }
    }

    // Pattern 4: Check inside serverContent for audio in parts
    if (jsonObj.serverContent && jsonObj.serverContent.modelTurn) {
        const modelTurn = jsonObj.serverContent.modelTurn;
        if (modelTurn.parts && Array.isArray(modelTurn.parts)) {
            modelTurn.parts.forEach((part, i) => {
                // Check for audio properties in each part
                if (part.audioContent) {
                    console.log(`Found audioContent in serverContent.modelTurn.parts[${i}]`);
                    results.push({
                        path: `${path}.serverContent.modelTurn.parts[${i}].audioContent`,
                        data: part.audioContent,
                        type: 'base64'
                    });
                }

                // Check for raw audio
                if (part.rawAudio) {
                    console.log(`Found rawAudio in serverContent.modelTurn.parts[${i}]`);
                    results.push({
                        path: `${path}.serverContent.modelTurn.parts[${i}].rawAudio`,
                        data: part.rawAudio,
                        type: part.rawAudio instanceof ArrayBuffer ? 'binary' : 'base64'
                    });
                }
            });
        }
    }

    // Pattern 5: Check for audio chunks array
    if (jsonObj.audio_chunks && Array.isArray(jsonObj.audio_chunks)) {
        jsonObj.audio_chunks.forEach((chunk, i) => {
            console.log(`Found audio_chunk at ${path}.audio_chunks[${i}]`);
            if (typeof chunk === 'string') {
                results.push({
                    path: `${path}.audio_chunks[${i}]`,
                    data: chunk,
                    type: 'base64'
                });
            } else if (chunk instanceof ArrayBuffer) {
                results.push({
                    path: `${path}.audio_chunks[${i}]`,
                    data: chunk,
                    type: 'binary'
                });
            }
        });
    }

    // Pattern 6: Check for raw content property (might be audio data)
    if (jsonObj.content && typeof jsonObj.content === 'string' &&
        jsonObj.mimeType && jsonObj.mimeType.includes('audio')) {

        console.log(`Found audio content with mimeType at ${path}`);
        results.push({
            path: `${path}.content`,
            data: jsonObj.content,
            type: 'base64',
            mimeType: jsonObj.mimeType
        });
    }

    // Check if this is a raw audio buffer
    if (jsonObj instanceof ArrayBuffer ||
        (jsonObj.constructor && jsonObj.constructor.name === 'ArrayBuffer')) {
        console.log(`Found ArrayBuffer at ${path}`);
        results.push({path, data: jsonObj, type: 'binary'});
    }

    // Recursively check all properties
    for (const key in jsonObj) {
        if (jsonObj.hasOwnProperty(key)) {
            const newPath = path ? `${path}.${key}` : key;
            results = results.concat(findAudioDataInJson(jsonObj[key], newPath));
        }
    }

    return results;
}

// --- Now modify the JSON processing logic to use this helper ---
function processJsonMessage(jsonMessage) {
    // First handle text content
    if (jsonMessage.text) {
        console.log("Received text response:", jsonMessage.text);
        addMessageToChat(jsonMessage.text, 'ai');
    }

    // Handle turn completion for stream management
    if (jsonMessage.serverContent && jsonMessage.serverContent.turnComplete) {
        console.log("Turn complete received - handling end of response");
        // Optional: might want to clear the queue when the turn completes
        // audioPlayerQueue = [];
    }

    // Handle text in various Gemini response formats
    if (jsonMessage.serverContent &&
        jsonMessage.serverContent.modelTurn &&
        jsonMessage.serverContent.modelTurn.parts) {

        // Look for text in parts
        jsonMessage.serverContent.modelTurn.parts.forEach(part => {
            if (part.text) {
                console.log("Received text in part:", part.text);
                addMessageToChat(part.text, 'ai');
            }
        });
    }

    // Special handling for different Gemini response formats

    // Direct media format
    if (jsonMessage.media && Array.isArray(jsonMessage.media)) {
        jsonMessage.media.forEach((mediaItem, index) => {
            if (mediaItem.type && mediaItem.type.includes('audio')) {
                console.log(`Processing direct media[${index}] audio`);
                const audioData = base64ToArrayBuffer(mediaItem.data);
                queueGeminiAudio(audioData);
                return true;
            }
        });
    }

    // Handle direct audio in response
    if (jsonMessage.audio && typeof jsonMessage.audio === 'string') {
        console.log("Found direct audio property in response");
        const audioData = base64ToArrayBuffer(jsonMessage.audio);
        queueGeminiAudio(audioData);
        return true;
    }

    // Handle direct binary audio chunks
    if (jsonMessage.audio_chunk) {
        console.log("Found direct audio_chunk in response");
        if (typeof jsonMessage.audio_chunk === 'string') {
            const audioData = base64ToArrayBuffer(jsonMessage.audio_chunk);
            queueGeminiAudio(audioData);
            return true;
        } else if (jsonMessage.audio_chunk instanceof ArrayBuffer) {
            queueGeminiAudio(jsonMessage.audio_chunk);
            return true;
        }
    }

    // Use our helper to find ALL possible audio data
    const audioDataResults = findAudioDataInJson(jsonMessage);
    console.log("Found audio data at these paths:", audioDataResults);

    // --- MODIFICATION: Process only the FIRST valid audio result ---
    let audioDataFound = false;
    for (const result of audioDataResults) {
        try {
            console.log(`Attempting to process audio data from ${result.path} (${result.type})`);
            if (result.type === 'base64') {
                const audioData = base64ToArrayBuffer(result.data);
                if (audioData && audioData.byteLength > 0) { // Check if conversion was successful
                    queueGeminiAudio(audioData);
                    audioDataFound = true;
                    console.log("Successfully queued first found base64 audio data.");
                    break; // Exit loop after processing the first valid audio chunk
                } else {
                    console.warn(`Failed to convert or got empty buffer from base64 at ${result.path}`);
                }
            } else if (result.type === 'binary') {
                if (result.data && result.data.byteLength > 0) {
                    queueGeminiAudio(result.data);
                    audioDataFound = true;
                    console.log("Successfully queued first found binary audio data.");
                    break; // Exit loop after processing the first valid audio chunk
                } else {
                    console.warn(`Received empty binary audio data at ${result.path}`);
                }
            }
        } catch (e) {
            console.warn(`Error processing audio data from ${result.path}:`, e);
        }
    }

    // If we've processed audio, but did not find text, check for structured content that might contain text
    if (audioDataFound && !jsonMessage.text) {
        // Try to extract text from common patterns in Gemini responses

        // Pattern: Check parts in candidates
        if (jsonMessage.candidates && jsonMessage.candidates.length > 0) {
            const candidate = jsonMessage.candidates[0];
            if (candidate.content && candidate.content.parts) {
                candidate.content.parts.forEach(part => {
                    if (part.text) {
                        console.log("Found text in candidate part:", part.text);
                        addMessageToChat(part.text, 'ai');
                    }
                });
            }
        }

        // Pattern: Check for markdown content in LLM format
        if (jsonMessage.response && jsonMessage.response.candidates) {
            jsonMessage.response.candidates.forEach(candidate => {
                if (candidate.content && candidate.content.parts) {
                    candidate.content.parts.forEach(part => {
                        if (part.text) {
                            console.log("Found text in response candidate part:", part.text);
                            addMessageToChat(part.text, 'ai');
                        }
                    });
                }
            });
        }
    }

    return audioDataFound;
}

// Export for use in voice call module
export { processJsonMessage, updateGuestNameDisplay };

// Function to update the guest name display in the UI
function updateGuestNameDisplay() {
    console.log("Updating guest name display...");

    // Use the centralized dashboard state as the source of truth
    // The dashboard state should already have the correct name with proper priority
    let guestName = dashboardState?.guestName;

    // If dashboard state doesn't have a name, fall back to window variable
    if (!guestName || guestName === "Guest") {
        guestName = window.GUEST_NAME;
    }

    // Final fallback
    if (!guestName) {
        guestName = "Guest";
    }

    console.log(`Using guest name from dashboard state: "${guestName}" (source: ${dashboardState?.guestNameSource || 'unknown'})`);

    // Don't override the centralized state - it should already have the correct priority
    // The updateGuestName() function in guest_dashboard_utils.js handles all priority logic

    // Ensure state is consistent and centralized
    if (dashboardState.guestName !== guestName) {
        console.log(`Updating dashboardState.guestName from "${dashboardState.guestName}" to "${guestName}"`);
        dashboardState.guestName = guestName;
    }

    if (window.GUEST_NAME !== guestName) {
        console.log(`Updating window.GUEST_NAME from "${window.GUEST_NAME}" to "${guestName}"`);
        window.GUEST_NAME = guestName;
    }

    // Update all DOM elements that display the guest name
    const guestNameElements = document.querySelectorAll('#guest-name, .guest-name-display, #profile-modal-name');
    guestNameElements.forEach(element => {
        if (element && element.textContent !== guestName) {
            console.log(`Updating guest name element from "${element.textContent}" to "${guestName}"`);
            element.textContent = guestName;
        }
    });

    // Update avatar initials (including profile modal avatar)
    const avatarElements = document.querySelectorAll('.bg-saffron, #profile-modal-avatar');
    avatarElements.forEach(avatar => {
        if (avatar && avatar.textContent.length === 1) { // Only update single letter avatars
            const newInitial = guestName[0].toUpperCase();
            if (avatar.textContent !== newInitial) {
                console.log(`Updating avatar initial from "${avatar.textContent}" to "${newInitial}"`);
                avatar.textContent = newInitial;
            }
        }
    });

    if (guestNameElements.length === 0) {
        console.warn("No guest name elements found in DOM");
    }

    return guestName;
}
