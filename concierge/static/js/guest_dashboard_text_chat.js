/*
 * Text chat functionality for the guest dashboard
 */

import { dashboardState, addMessageToChat, createSharedSystemPrompt } from './guest_dashboard_utils.js';

// --- Socket.IO Initialization (For Text Chat) ---
let socket = null;
let isSocketConnected = false;
let lastActivityTimestamp = 0;
let inactivityTimeout = null;
let isChatEnabled = false;
let intentionalDisconnect = false; // Track intentional disconnects

const INACTIVITY_TIMEOUT_MS = 2 * 60 * 1000; // 2 minutes in milliseconds

// --- Speech Recognition Variables ---
let recognition = null;
let isRecording = false;

// --- Conversation History Variables ---
let conversationHistory = [];

// Function to get conversation history for context
async function getConversationHistory(propertyId, userId) {
    try {
        const response = await fetch(`/api/conversation-history/${userId}/${propertyId}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            },
            credentials: 'same-origin'
        });

        if (response.ok) {
            const data = await response.json();
            console.log("Retrieved conversation history:", data);
            return data.messages || [];
        } else {
            console.warn("Could not retrieve conversation history:", response.status);
            return [];
        }
    } catch (error) {
        console.error("Error retrieving conversation history:", error);
        return [];
    }
}

// Function to load and display recent conversation history
window.loadRecentConversationHistory = async function loadRecentConversationHistory() {
    // Try to get the user ID from multiple sources
    const userId = dashboardState.userId || window.CURRENT_USER_ID || document.getElementById('template-data')?.dataset.userId;
    const propertyId = dashboardState.propertyId || getConfirmedPropertyId();

    if (!propertyId || !userId) {
        console.log("Property ID or User ID not available yet for conversation history", {propertyId, userId});
        return;
    }

    // Update dashboard state with the user ID if not already set
    if (!dashboardState.userId && userId) {
        dashboardState.userId = userId;
    }

    try {
        const recentMessages = await getConversationHistory(dashboardState.propertyId, dashboardState.userId);

        if (recentMessages && recentMessages.length > 0) {
            console.log(`Loading ${recentMessages.length} recent messages`);

            // Clear any existing greeting to replace with history
            const chatMessages = document.getElementById('chat-messages');
            chatMessages.innerHTML = '';

            // Add a system message to indicate this is recent history
            const historyIndicator = document.createElement('div');
            historyIndicator.className = 'system-message mb-4';
            historyIndicator.innerHTML = `
                <div class="flex items-center gap-2 text-persian-green text-sm">
                    <i class="fas fa-history"></i>
                    <span>Recent conversation history from the last 24 hours</span>
                </div>
            `;
            chatMessages.appendChild(historyIndicator);

            // Display recent messages with their original timestamps
            recentMessages.forEach(message => {
                displayChatMessage(message.role, message.text, message.timestamp, false, message);
            });

            // Add current greeting after history
            generateGreeting();

            // Mark that we've loaded history
            window.conversationHistoryLoaded = true;
        } else {
            // No recent history, just show greeting
            generateGreeting();
        }
    } catch (error) {
        console.error("Error loading recent conversation history:", error);
        // Fallback to greeting if history loading fails
        generateGreeting();
    }
}

// Function to display a chat message with proper formatting
window.displayChatMessage = function displayChatMessage(role, text, timestamp, skipScroll = false, messageData = {}) {
    // Preprocess transcript for masking if function is available (e.g., for voice call messages)
    if (typeof window.preprocessTranscript === 'function') {
        const lang = messageData.language || window.currentGeminiLanguage || localStorage.getItem('geminiLanguagePreference') || 'en-US';
        try {
            text = window.preprocessTranscript(text, lang);
        } catch (err) {
            console.warn('Transcript preprocessing failed:', err);
        }
    }
    const chatMessages = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');

    // Format timestamp
    const msgTime = timestamp ? new Date(timestamp) : new Date();
    const timeString = msgTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // Store the full timestamp as a data attribute for date separation logic
    messageDiv.setAttribute('data-timestamp', msgTime.toISOString());

    // Check if this is a voice call message
    const isVoiceMessage = messageData.channel === 'voice_call' || messageData.conversation_id?.includes('voice');

    if (role === 'user') {
        const userName = window.GUEST_NAME || 'You';
        console.log("displayChatMessage: Using guest name for user message:", userName, "(window.GUEST_NAME =", window.GUEST_NAME, ")");
        const voiceIcon = isVoiceMessage ? '<i class="fas fa-microphone text-xs text-persian-green ml-2" title="Voice message"></i>' : '';
        messageDiv.className = 'chat-message-wrapper flex gap-3 mb-4 justify-end';
        messageDiv.innerHTML = `
            <div class="flex flex-1 flex-col gap-2 max-w-[80%]">
                <div class="flex flex-col gap-1">
                    <div class="flex flex-wrap items-center gap-3 justify-end">
                        <p class="chat-message-time text-persian-green text-sm font-normal leading-normal">${timeString}</p>
                        <p class="chat-message-name text-dark-purple text-base font-bold leading-tight">${userName}${voiceIcon}</p>
                    </div>
                    <div class="user-message rounded-xl p-3">
                        <p class="chat-message-content text-dark-purple text-base font-normal leading-normal">${text}</p>
                    </div>
                </div>
            </div>
            <div class="chat-avatar bg-saffron rounded-full size-10 flex items-center justify-center text-dark-purple font-bold">
                ${userName[0]}
            </div>
        `;
    } else if (role === 'assistant') {
        const voiceIcon = isVoiceMessage ? '<i class="fas fa-microphone text-xs text-persian-green ml-2" title="Voice message"></i>' : '';
        messageDiv.className = 'chat-message-wrapper flex gap-3 mb-4';
        messageDiv.innerHTML = `
            <div class="chat-avatar bg-persian-green rounded-full size-10 flex items-center justify-center text-white font-bold">
                S
            </div>
            <div class="flex flex-1 flex-col gap-2">
                <div class="flex flex-col gap-1">
                    <div class="flex flex-wrap items-center gap-3">
                        <p class="chat-message-name text-dark-purple text-base font-bold leading-tight">Staycee${voiceIcon}</p>
                        <p class="chat-message-time text-persian-green text-sm font-normal leading-normal">${timeString}</p>
                    </div>
                    <div class="ai-message rounded-xl p-3">
                        <p class="chat-message-content text-dark-purple text-base font-normal leading-normal">${text}</p>
                    </div>
                </div>
            </div>
        `;
    } else if (role === 'system') {
        messageDiv.className = 'system-message mb-4';
        messageDiv.innerHTML = `
            <div class="flex items-center gap-2 text-dark-purple/70 text-sm">
                <i class="fas fa-info-circle"></i>
                <span>${text}</span>
                <span class="chat-message-time text-xs text-dark-purple/50 ml-auto">${timeString}</span>
            </div>
        `;
    }

    chatMessages.appendChild(messageDiv);

    // Add date separator if needed for the new message (with slight delay to ensure DOM is ready)
    setTimeout(() => {
        if (typeof window.addDateSeparatorIfNeeded === 'function') {
            console.log('Adding date separator for message:', role, timeString);
            window.addDateSeparatorIfNeeded(messageDiv);
        } else {
            console.log('addDateSeparatorIfNeeded function not available');
        }
    }, 50);

    // Scroll to bottom unless explicitly skipped
    if (!skipScroll) {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

// --- Speech Recognition Initialization ---
function initializeSpeechRecognition() {
    try {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.lang = 'en-US';

            console.log("Web Speech API supported and initialized.");
            return true;
        } else {
            console.warn("Web Speech API not supported in this browser.");
            return false;
        }
    } catch (e) {
        console.error("Error initializing SpeechRecognition:", e);
        return false;
    }
}

// --- Speech Recognition Control Functions ---
function toggleRecording() {
    if (!recognition) {
        console.warn("Speech recognition not available");
        return;
    }

    const recordButton = document.getElementById('record-message');
    const chatInput = document.getElementById('chat-input');

    if (!recordButton || !chatInput) {
        console.error("Required elements not found for speech recognition");
        return;
    }

    if (isRecording) {
        recognition.stop();
        // Visuals are handled by onend/onerror
    } else {
        try {
            recognition.start();
            console.log('Speech recognition started.');
            isRecording = true;
            recordButton.classList.add('btn-danger');
            recordButton.classList.remove('btn-secondary');
            recordButton.innerHTML = '<i class="fas fa-stop"></i>';
            recordButton.title = "Stop Recording";
            chatInput.placeholder = "Listening...";
        } catch (error) {
            console.error("Error starting speech recognition:", error);
            isRecording = false;
        }
    }
}

function stopRecordingVisuals(recordButton, chatInput) {
    isRecording = false;
    recordButton.classList.remove('btn-danger');
    recordButton.classList.add('btn-secondary');
    recordButton.innerHTML = '<i class="fas fa-microphone"></i>';
    recordButton.title = "Record Message";
    chatInput.placeholder = "Type your message here...";
}

function setupSpeechRecognitionEvents() {
    if (!recognition) return;

    const recordButton = document.getElementById('record-message');
    const chatInput = document.getElementById('chat-input');

    recognition.onresult = (event) => {
        const transcript = event.results[event.results.length - 1][0].transcript.trim();
        console.log('Speech recognized:', transcript);
        chatInput.value = transcript;
        stopRecordingVisuals(recordButton, chatInput);
    };

    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        stopRecordingVisuals(recordButton, chatInput);
    };

    recognition.onend = () => {
        console.log('Speech recognition ended.');
        stopRecordingVisuals(recordButton, chatInput);
    };
}

// Function to initialize Socket.IO connection PROCESS
function initializeSocketIOProcess() {
    console.log("initializeSocketIOProcess called");

    // Check if this is a temporary user (magic link access)
    if (window.isTemporaryUser && window.tempIdToken) {
        console.log("Temporary user detected, using temporary ID token");
        console.log("Temporary user token available:", window.tempIdToken ? "Yes" : "No");
        console.log("Temporary user flag:", window.isTemporaryUser);

        // Store the temporary token in our centralized state
        dashboardState.idToken = window.tempIdToken;
        window.storedIdToken = window.tempIdToken; // For backward compatibility

        console.log("Stored temporary token in dashboardState and window.storedIdToken");

        // Enable chat button since we have the token
        checkAndEnableChatButton();
        return;
    } else {
        console.log("Not a temporary user or missing tempIdToken");
        console.log("window.isTemporaryUser:", window.isTemporaryUser);
        console.log("window.tempIdToken available:", window.tempIdToken ? "Yes" : "No");
    }

    // Regular Firebase authentication for normal users
    if (typeof firebase === 'undefined' || !firebase.auth) {
        console.log("Firebase not available, checking for temporary user token");
        checkAndEnableChatButton();
        return;
    }

    // Ensure firebase is initialized and auth state is checked - WAIT for secure init
    async function setupSocketIOAuth() {
        try {
            // Wait for Firebase to be securely initialized
            if (typeof window.initializeFirebaseSecurely === 'function') {
                await window.initializeFirebaseSecurely();
            }
            
            firebase.auth().onAuthStateChanged(user => {
        if (user) {
            console.log("User is logged in, getting ID token");

            // Update user name from Firebase auth if available
            if (user.displayName) {
                // Import the updateGuestName function
                import('./guest_dashboard_utils.js').then(module => {
                    const { updateGuestName } = module;
                    updateGuestName(user.displayName, 'firebase-auth-in-socket');
                    console.log("Updated guest name from Firebase auth:", user.displayName);
                }).catch(error => {
                    console.error("Error importing updateGuestName:", error);

                    // Fallback to direct update if import fails
                    window.GUEST_NAME = user.displayName;
                    const guestNameElement = document.getElementById('guest-name');
                    if (guestNameElement) {
                        guestNameElement.textContent = user.displayName;
                        console.log("Updated guest name from Firebase auth (fallback):", user.displayName);
                    }
                });
            } else {
                console.log("User has no display name in Firebase auth");
            }

            user.getIdToken().then(idToken => {
                console.log("Got ID token, ready for connection when property ID is confirmed.");

                // Store token in our centralized state
                dashboardState.idToken = idToken;

                // For backward compatibility
                window.storedIdToken = idToken;

                // Do NOT connect yet. Enable button only after property ID is confirmed.
                checkAndEnableChatButton(); // Check if we can enable button now
            }).catch(error => {
                console.error("Error getting ID token:", error);
            });
        } else {
            console.log("User not logged in.");
            const startTextChatButton = document.getElementById('start-text-chat');
            if(startTextChatButton) {
                startTextChatButton.disabled = true;
                startTextChatButton.textContent = "Login Required";
            }
            enableChatControls(false);
        }
    });
    
    } catch (error) {
        console.error("Error setting up Socket.IO auth:", error);
    }
}

// Call the async function to setup Socket.IO auth
setupSocketIOAuth();
}

// Function to check if both token and property ID are ready
function checkAndEnableChatButton() {
    console.log("checkAndEnableChatButton called");
    console.log("- idToken:", dashboardState.idToken ? "Present (hidden)" : "Missing");
    console.log("- propertyId:", dashboardState.propertyId || "Missing");
    console.log("- window.storedIdToken:", window.storedIdToken ? "Present (hidden)" : "Missing");
    console.log("- window.confirmedPropertyId:", window.confirmedPropertyId || "Missing");
    console.log("- window.isTemporaryUser:", window.isTemporaryUser);
    console.log("- window.tempIdToken:", window.tempIdToken ? "Present (hidden)" : "Missing");

    // Check if we have both token and property ID
    const idToken = dashboardState.idToken || window.storedIdToken;
    const propertyId = dashboardState.propertyId || window.confirmedPropertyId;

    if (idToken && propertyId) {
        console.log("Both token and property ID are ready, chat can auto-start when needed");
        // Chat will auto-start when user sends a message
    } else {
        console.log("Missing required data for chat:");
        if (!idToken) console.log("- Missing ID token");
        if (!propertyId) console.log("- Missing property ID");
    }
}

// Initialize Socket
function initSocket(url, token, propertyIdToSend) {
    console.log("initSocket called with:", {
        url: url,
        token: token ? "Present (hidden)" : "Missing",
        propertyIdToSend: propertyIdToSend
    });

    return new Promise((resolve, reject) => { // Wrap in a Promise
        // --- Add parameter checks ---
        if (!url || url === "Not defined" || url === "") {
            console.error("Socket.IO URL not available for connection");
            return reject(new Error("Socket.IO URL missing")); // Reject promise
        }
        if (!token) {
            console.error("Cannot connect: Auth token missing.");
            return reject(new Error("Auth token missing")); // Reject promise
        }
        if (!propertyIdToSend) {
            console.error("Cannot connect: Property ID missing.");
            return reject(new Error("Property ID missing")); // Reject promise
        }

        // Ensure we have the latest property details AND knowledge items before connecting
        import('./guest_dashboard_utils.js').then(module => {
            // First fetch property details
            module.fetchPropertyDetails(propertyIdToSend)
                .then(propertyDetails => {
                    if (propertyDetails) {
                        console.log("Verified property details before socket connection:", propertyDetails);
                        // Property details are already stored in dashboardState by fetchPropertyDetails
                        
                        // Now fetch knowledge items for the property (similar to voice call)
                        console.log("Fetching knowledge items for text chat...");
                        return module.fetchPropertyKnowledgeItems(propertyIdToSend);
                    } else {
                        throw new Error("Property details verification failed");
                    }
                })
                .then(() => {
                    console.log("Knowledge items fetched successfully for text chat");
                    // Now proceed with socket connection
                    connectToSocketIO(url, token, propertyIdToSend, resolve, reject);
                })
                .catch(error => {
                    console.error("Error fetching property data before socket connection:", error);
                    return reject(new Error("Property data fetch error"));
                });
        });
    });
}

// Helper function to actually connect to the socket after property verification
function connectToSocketIO(url, token, propertyIdToSend, resolve, reject) {
    console.log(`Socket.IO connection strategy: Using URL ${url}`);
    console.log(`Using auth token: ${token ? token.substring(0, 10) + '...' : 'No Token'}`);
    console.log(`Using property ID: ${propertyIdToSend}`);

    try {
        // Safety check for Socket.IO availability
        if (typeof io === 'undefined') {
            console.error("Socket.IO is not available. Make sure the Socket.IO client library is loaded.");
            reject(new Error("Socket.IO not available"));
            return;
        }

        // Get the guest name from our centralized state
        // Always use the most current guest name (in case it was updated after initial load)
        const currentGuestName = window.dashboardState?.guestName || window.GUEST_NAME || dashboardState.guestName || "";
        console.log("Guest name for Socket.IO auth:", currentGuestName || "Not available");

        // Extract user ID from token
        let userId = null;
        try {
            // Parse the JWT token to get the user ID
            const tokenParts = token.split('.');
            if (tokenParts.length === 3) {
                const payload = JSON.parse(atob(tokenParts[1]));
                userId = payload.user_id;
                console.log("Extracted user ID from token:", userId);
            }
        } catch (error) {
            console.error("Error extracting user ID from token:", error);
        }

        // Ensure URL is properly formatted for Socket.IO
        // Socket.IO expects a base URL without protocol prefixes for transports
        let socketUrl = url;

        // For local development, use the current origin
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            socketUrl = window.location.origin;
            console.log("Using current origin for Socket.IO in local development:", socketUrl);
        }
        // For production, ensure we have a properly formatted URL
        else if (socketUrl.startsWith('ws://') || socketUrl.startsWith('wss://') ||
                 socketUrl.startsWith('http://') || socketUrl.startsWith('https://')) {

            // Convert WebSocket URL to HTTP/HTTPS for Socket.IO
            socketUrl = socketUrl.replace('ws://', 'http://').replace('wss://', 'https://');
            console.log("Converted WebSocket URL to HTTP/HTTPS for Socket.IO:", socketUrl);
        }

        // Create Socket.IO connection with user ID in query params
        const socketIO = io(socketUrl, {
            query: {
                user_id: userId,
                property_id: propertyIdToSend,
                guest_name: currentGuestName
            },
            transports: ['websocket'],
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
            forceNew: true, // Create a new connection each time
            timeout: 10000, // 10 seconds timeout
            autoConnect: true // Connect automatically
        });

        // Track if connection timed out
        let connectionTimedOut = false;

        // Set connection timeout (10 seconds)
        const connectionTimeoutId = setTimeout(() => {
            connectionTimedOut = true;
            console.error("Socket.IO connection timed out");
            socketIO.disconnect();
            reject(new Error("Connection timeout")); // Reject promise
        }, 10000);

        // Handle connection
        socketIO.on('connect', () => {
            clearTimeout(connectionTimeoutId); // Clear the timeout
            console.log("Socket.IO connection OPENED");
            isSocketConnected = true;

            // Update the chat button state to "End Chat"
            updateChatButtonState();

            // Reset feedback counters for a new text chat session
            import('./guest_dashboard_feedback.js').then(module => {
                if (module.resetForNewSession) {
                    module.resetForNewSession();
                }
            }).catch(() => {});

            // Create a system prompt for text chat using the shared function
            // This is done after knowledge items are fetched to ensure they're included
            const systemPrompt = createSharedSystemPrompt ? createSharedSystemPrompt() :
                "You are a helpful concierge assistant for this property. Please help the guest with their questions.";

            // Get reservation ID from the current active reservation
            let reservationId = null;

            // First try to get the current active reservation from dashboard state
            if (dashboardState.currentReservation) {
                const reservation = dashboardState.currentReservation;
                reservationId = reservation.id || reservation.reservationId || reservation.ReservationId;
                console.log("Found reservation ID from current reservation:", reservationId);
            }
            // Fallback to window.currentReservation for backward compatibility
            else if (window.currentReservation) {
                const reservation = window.currentReservation;
                reservationId = reservation.id || reservation.reservationId || reservation.ReservationId;
                console.log("Found reservation ID from window.currentReservation:", reservationId);
            }
            // Last resort: use the first reservation (old behavior)
            else if (window.reservations && Array.isArray(window.reservations) && window.reservations.length > 0) {
                const reservation = window.reservations[0];
                reservationId = reservation.id || reservation.reservationId || reservation.ReservationId;
                console.log("Found reservation ID from first reservation (fallback):", reservationId);
            }

            // Get phone number from window object (set from template)
            const phoneNumber = window.PHONE_NUMBER || "";
            console.log("Phone number for auth:", phoneNumber || "Not available");

            // Get conversation history for context
            getConversationHistory(propertyIdToSend, userId).then(history => {
                // Send authentication message with user ID, property ID, guest name, reservation ID, phone number, and conversation history
                socketIO.emit('auth', {
                    user_id: userId,
                    property_id: propertyIdToSend,
                    guest_name: currentGuestName,
                    reservation_id: reservationId, // Include reservation ID if found
                    phone_number: phoneNumber, // Include phone number if available
                    system_prompt: systemPrompt, // Include the system prompt in auth
                    conversation_history: history, // Include previous conversation summaries
                    current_conversation: conversationHistory // Include current conversation for continuity
                });

                console.log("Sent auth message with conversation history:", history.length, "previous conversations and", conversationHistory.length, "current messages");
            }).catch(error => {
                console.error("Error getting conversation history, proceeding without it:", error);
                // Send authentication without history if there's an error
                socketIO.emit('auth', {
                    user_id: userId,
                    property_id: propertyIdToSend,
                    guest_name: currentGuestName,
                    reservation_id: reservationId,
                    phone_number: phoneNumber,
                    system_prompt: systemPrompt,
                    current_conversation: conversationHistory // Still include current conversation
                });
            });

            console.log("Sent auth message with user_id, property_id, and reservation_id:", reservationId);

            // Configure tools for the AI (disable RAG for text chat)
            socketIO.emit('configure_tools', {
                property_id: propertyIdToSend,
                enable_rag: false,
                enable_google_search: true
            });

            console.log("Sent configure_tools message");

            checkAndEnableChatButton();
            enableChatControls(true);
            startInactivityTimer();
        });

        // Handle connection success response
        socketIO.on('connection_success', (data) => {
            console.log("Socket.IO connection successful:", data);
        });

        // Handle authentication success
        socketIO.on('auth_success', (data) => {
            console.log("Authentication successful:", data);

            // Don't send a greeting since we already have the initial greeting
            // Just resolve the promise to indicate successful connection
            resolve(socketIO); // Resolve the promise with the socket on success

            // Ensure feedback is reset on authenticated session
            import('./guest_dashboard_feedback.js').then(module => {
                if (module.resetForNewSession) {
                    module.resetForNewSession();
                }
            }).catch(() => {});
        });

        // Handle tools configuration response
        socketIO.on('tools_configured', (data) => {
            console.log("Tools configuration response:", data);
        });

        // Handle connection error
        socketIO.on('connect_error', (error) => {
            clearTimeout(connectionTimeoutId);
            if (connectionTimedOut) return; // Don't reject if already timed out
            console.error("Socket.IO connection ERROR:", error);
            isSocketConnected = false;

            // Update the chat button state to "Start Text Chat"
            updateChatButtonState();

            checkAndEnableChatButton();
            enableChatControls(false);
            // Don't show connection error messages to user
            reject(new Error("Socket.IO connection error")); // Reject promise
        });

        // Handle disconnection
        socketIO.on('disconnect', (reason) => {
            clearTimeout(connectionTimeoutId);
            console.log("Socket.IO connection CLOSED. Reason:", reason);
            isSocketConnected = false;
            clearInactivityTimer();

            // Update the chat button state to "Start Text Chat"
            updateChatButtonState();

            checkAndEnableChatButton();
            enableChatControls(false);

            // Check if this was an intentional disconnect initiated by the client
            if (intentionalDisconnect) {
                console.log("This was an intentional disconnect, not showing reconnection message");
                // Reset the flag
                intentionalDisconnect = false;
            } else {
                // Don't show disconnection messages to user - chat will auto-restart when needed
                console.log("Connection closed unexpectedly, but not showing message to user");
            }

            // Ensure socket is properly cleaned up
            if (socket) {
                try {
                    // Close any remaining connections
                    if (socket.connected) {
                        socket.close();
                    }
                } catch (err) {
                    console.error("Error closing socket during disconnect handler:", err);
                } finally {
                    // Nullify the socket reference
                    socket = null;
                }
            }
        });

        // Handle server errors
        socketIO.on('error', (data) => {
            console.error("Error from Socket.IO server:", data);
            // Don't show server errors to user - they'll just see no response
        });

        // Handle AI messages
        socketIO.on('text_message_from_ai', (data) => {
            console.log("Text message from AI via Socket.IO:", data);
            if (data && data.message) {
                addMessageToChat(data.message, 'ai', 'staycee');
                updateLastActivity();

                // Store in conversation history for potential restart
                conversationHistory.push({
                    role: 'assistant',
                    content: data.message,
                    timestamp: new Date().toISOString()
                });
            }
        });

        // Capture conversation id from server when created (if server emits it)
        socketIO.on('conversation_started', (data) => {
            if (data && data.conversation_id) {
                window.currentTextConversationId = data.conversation_id;
                console.log('Captured conversation_id from server:', window.currentTextConversationId);
            }
        });

        // Handle guest name updates from server
        socketIO.on('guest_name_updated', (data) => {
            console.log("Guest name updated via Socket.IO:", data);
            if (data && data.success && data.guest_name) {
                console.log("guest_name_updated: Updating global variable from", window.GUEST_NAME, "to", data.guest_name);
                
                // Update the global variable
                window.GUEST_NAME = data.guest_name;
                console.log("guest_name_updated: Updated window.GUEST_NAME to:", window.GUEST_NAME);
                
                // Update dashboard state if available - ensure it exists first
                if (!window.dashboardState) {
                    window.dashboardState = {};
                    console.log("guest_name_updated: Created dashboardState object");
                }
                window.dashboardState.guestName = data.guest_name;
                window.dashboardState.guestNameSource = 'socket-update';
                console.log("guest_name_updated: Updated dashboardState.guestName to:", window.dashboardState.guestName);
                
                // Force refresh the system prompt with the new guest name
                if (data.refresh_system_prompt && typeof createSharedSystemPrompt === 'function') {
                    try {
                        // Ensure we have the latest guest name before creating the system prompt
                        const currentGuestName = window.dashboardState.guestName || window.GUEST_NAME || data.guest_name;
                        console.log("guest_name_updated: Creating system prompt with guest name:", currentGuestName);
                        
                        const updatedSystemPrompt = createSharedSystemPrompt();
                        console.log("guest_name_updated: Sending updated system prompt with new guest name to server");
                        socketIO.emit('update_system_prompt', {
                            system_prompt: updatedSystemPrompt
                        });
                    } catch (error) {
                        console.error("guest_name_updated: Error creating updated system prompt:", error);
                    }
                }
                
                console.log("guest_name_updated: Successfully updated guest name in text chat to:", data.guest_name);
            } else {
                console.warn("guest_name_updated: Invalid data received:", data);
            }
        });

        // Handle guest name update errors
        socketIO.on('guest_name_update_error', (data) => {
            console.error("Guest name update error:", data);
        });

        // Handle system prompt update confirmations
        socketIO.on('system_prompt_updated', (data) => {
            console.log("System prompt updated via Socket.IO:", data);
        });

        // Store the socket
        socket = socketIO;
    } catch (error) {
        console.error("Error creating Socket.IO connection:", error);
        checkAndEnableChatButton();
        reject(error); // Reject promise on creation error
    }
}

// --- Inactivity Timer Functions ---
function updateLastActivity() {
    lastActivityTimestamp = Date.now();
    console.log("Updated last activity timestamp");

    // Clear any existing timeout and start a new one
    clearInactivityTimer();
    startInactivityTimer();
}

// Start the inactivity timer
function startInactivityTimer() {
    // Clear any existing timeout first to avoid multiple timers
    clearInactivityTimer();

    inactivityTimeout = setTimeout(() => {
        if (isSocketConnected && socket) {
            console.log(`Inactive for ${INACTIVITY_TIMEOUT_MS/60000} minutes, closing WebSocket connection silently.`);

            // First update local state before any network operations
            // Set a flag to prevent the disconnect event from triggering unwanted messages
            intentionalDisconnect = true;

            // Update UI state immediately
            isSocketConnected = false;
            // Don't disable chat controls - keep them enabled for auto-restart
            updateChatButtonState();

            try {
                // Send a custom event to the server to signal an intentional disconnect
                if (socket.connected) {
                    socket.emit('user_disconnect', {
                        reason: 'Inactivity timeout',
                        timestamp: Date.now(),
                        inactivity_duration_ms: INACTIVITY_TIMEOUT_MS
                    });
                    console.log("Sent inactivity disconnect notification to server");
                }

                // Small delay to allow server to process the disconnect notification
                setTimeout(() => {
                    try {
                        // Only disconnect if socket is still connected
                        if (socket && socket.connected) {
                            socket.disconnect();
                            console.log("Socket.IO connection disconnected due to inactivity");
                        } else {
                            console.log("Socket already disconnected");
                        }
                    } catch (err) {
                        console.error("Error disconnecting socket:", err);
                    }

                    // Nullify the socket reference to prevent any further usage
                    socket = null;
                }, 300); // 300ms delay should be enough for server to process
            } catch (error) {
                console.error("Error during inactivity disconnect sequence:", error);
                // Nullify the socket reference to prevent any further usage
                socket = null;
            }
        }
    }, INACTIVITY_TIMEOUT_MS);
}

// Clear the inactivity timer
function clearInactivityTimer() {
    if (inactivityTimeout) {
        clearTimeout(inactivityTimeout);
        inactivityTimeout = null;
    }
}

// Enable or disable chat controls
function enableChatControls(enable) {
    isChatEnabled = enable;

    // Check if UI elements exist before trying to access them
    const chatInput = document.getElementById('chat-input');
    const sendMessageButton = document.getElementById('send-message');
    const recordButton = document.getElementById('record-message');

    if (chatInput) {
        // Always enable the input since chat will auto-start
        chatInput.disabled = false;
        chatInput.placeholder = "Type your message...";
        if (!enable) {
            chatInput.value = '';
        }
    }

    if (sendMessageButton) {
        // Always enable the send button since chat will auto-start
        sendMessageButton.disabled = false;
    }

    // Enable/disable microphone button based on speech recognition support
    if (recordButton) {
        if (recognition) {
            recordButton.disabled = false;
            recordButton.title = "Record Message";
        } else {
            recordButton.disabled = true;
            recordButton.title = "Speech Recognition not supported";
        }

        // If we're disabling and currently recording, stop recording
        if (!enable && isRecording) {
            recognition.stop();
        }
    }

    // Update the chat button state
    updateChatButtonState();
}

// Send a text message
function sendTextMessage() {
    const chatInput = document.getElementById('chat-input');
    const messageText = chatInput.value.trim();

    if (!messageText) {
        console.warn("Cannot send empty message.");
        return;
    }

    // If chat is not connected, start it automatically
    if (!isChatEnabled || !isSocketConnected) {
        console.log("Chat not connected, starting automatically...");

        // Get token and property ID from our centralized state
        const idToken = dashboardState.idToken || window.storedIdToken;
        const propertyId = dashboardState.propertyId || window.confirmedPropertyId;

        if (!idToken || !propertyId) {
            console.error("Cannot start chat: Token or property ID is missing");
            console.log("- idToken:", idToken ? "Present (hidden)" : "Missing");
            console.log("- propertyId:", propertyId || "Missing");
            // Don't show error messages to user - they'll just see no response
            return;
        }

        // Store the message to send after connection
        const pendingMessage = messageText;
        chatInput.value = '';

        // Add the user message to chat immediately
        addMessageToChat(pendingMessage, 'user');

        // Store in conversation history for potential restart
        conversationHistory.push({
            role: 'user',
            content: pendingMessage,
            timestamp: new Date().toISOString()
        });

        // Get the Socket.IO URL
        let url = document.body.dataset.websocketApiUrl || (window['WEBSOCKET_API_URL'] || "");

        // If API Gateway URL is not available, fall back to the general URL
        if (!url || url === "" || url === "Not defined") {
            console.warn("API Gateway URL not available, falling back to general URL");
            url = document.body.dataset.websocketUrl || (window['WEBSOCKET_URL'] || "");
        }

        // If still no URL, use current location as fallback
        if (!url || url === "" || url === "Not defined") {
            console.warn("No URL found in any source, using current location as fallback");
            url = window.location.origin;
        }

        console.log("Auto-starting chat with URL:", url);

        // Start the connection and send the message once connected
        initSocket(url, idToken, propertyId)
            .then(() => {
                console.log("Chat auto-started successfully, sending pending message");

                // Send the pending message
                if (socket && isSocketConnected) {
                    socket.emit('text_message_from_user', {
                        message: pendingMessage,
                        property_id: propertyId
                    });
                    console.log(`Sent pending message via Socket.IO: ${pendingMessage} for property: ${propertyId}`);
                    updateLastActivity();
                } else {
                    console.error("Socket not ready after connection attempt");
                    // Don't show error messages to user
                }
            })
            .catch(err => {
                console.error("Failed to auto-start chat:", err);
                // Don't show error messages to user
            });

        return;
    }

    // Chat is already connected, send message normally
    if (messageText && socket) {
        addMessageToChat(messageText, 'user');

        // Store in conversation history for potential restart
        conversationHistory.push({
            role: 'user',
            content: messageText,
            timestamp: new Date().toISOString()
        });

        // Get property ID from our centralized state
        const propertyId = dashboardState.propertyId || window.confirmedPropertyId;

        // Use Socket.IO emit instead of WebSocket send
        socket.emit('text_message_from_user', {
            message: messageText,
            property_id: propertyId // Include property ID in the message
        });

        console.log(`Sent text message via Socket.IO: ${messageText} for property: ${propertyId}`);
        chatInput.value = '';
        updateLastActivity(); // Make sure we reset the inactivity timer when the user sends a message
    }
}

// Update the chat button state based on connection status
function updateChatButtonState() {
    // Since we removed the start text chat button and chat auto-starts,
    // we can just log the connection status for debugging
    console.log("Chat connection status:", isSocketConnected ? "Connected" : "Disconnected");

    // Update send button state based on connection
    const sendMessageButton = document.getElementById('send-message');
    if (sendMessageButton) {
        // Send button is always enabled since chat will auto-start when needed
        sendMessageButton.disabled = false;
    }
}

// Function to end the chat session
function endChatSession() {
    console.log("Ending chat session manually");

    if (socket && isSocketConnected) {
        // Don't show system messages to user

        // First update local state before any network operations
        // Set a flag to prevent the disconnect event from triggering unwanted messages
        intentionalDisconnect = true;

        // Update UI state immediately
        isSocketConnected = false;
        clearInactivityTimer();
        enableChatControls(false);
        updateChatButtonState();

        try {
            // Send a custom event to the server to signal an intentional disconnect
            if (socket.connected) {
                socket.emit('user_disconnect', {
                    reason: 'User ended chat',
                    timestamp: Date.now()
                });
                console.log("Sent disconnect notification to server");
            }

            // Small delay to allow server to process the disconnect notification
            setTimeout(() => {
                try {
                    // Only disconnect if socket is still connected
                    if (socket && socket.connected) {
                        socket.disconnect();
                        console.log("Socket.IO connection disconnected by user");
                    } else {
                        console.log("Socket already disconnected");
                    }
                } catch (err) {
                    console.error("Error disconnecting socket:", err);
                }

                // Nullify the socket reference to prevent any further usage
                socket = null;
            }, 300); // 300ms delay should be enough for server to process
        } catch (error) {
            console.error("Error during disconnect sequence:", error);
            // Nullify the socket reference to prevent any further usage
            socket = null;
        }
    } else {
        console.log("No active socket connection to end");
        // Reset UI state just in case
        isSocketConnected = false;
        clearInactivityTimer();
        enableChatControls(false);
        updateChatButtonState();
    }
}

// Initialize chat UI
function initializeChat() {
    console.log("initializeChat called");

    const chatInput = document.getElementById('chat-input');
    const sendMessageButton = document.getElementById('send-message');

    if (!chatInput || !sendMessageButton) {
        console.error("Chat UI elements not found!");
        return;
    }

    console.log("Chat UI elements found:");
    console.log("- chatInput:", chatInput ? "Found" : "Missing");
    console.log("- sendMessageButton:", sendMessageButton ? "Found" : "Missing");

    // Enable chat controls by default since chat will auto-start
    enableChatControls(true);
    checkAndEnableChatButton();

    // No need for start text chat button since chat auto-starts with first message

    sendMessageButton.addEventListener('click', sendTextMessage);
    chatInput.addEventListener('keypress', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendTextMessage();
        }
    });

    // Initialize speech recognition
    const recordButton = document.getElementById('record-message');
    if (recordButton) {
        console.log("Setting up speech recognition...");
        const speechSupported = initializeSpeechRecognition();

        if (speechSupported) {
            setupSpeechRecognitionEvents();
            recordButton.addEventListener('click', toggleRecording);
            recordButton.disabled = false;
            recordButton.title = "Record Message";
            console.log("Speech recognition enabled");
        } else {
            recordButton.disabled = true;
            recordButton.title = "Speech Recognition not supported";
            console.log("Speech recognition not supported");
        }
    } else {
        console.warn("Record button not found in DOM");
    }
}

// Listen for property changes and re-check chat button state
document.addEventListener('propertyIdChanged', (event) => {
    const { propertyId, previousPropertyId } = event.detail;
    console.log(`Text chat: Property ID changed from ${previousPropertyId || 'unset'} to ${propertyId}`);
    
    // Re-check if chat button should be enabled with new property
    setTimeout(() => {
        checkAndEnableChatButton();
    }, 100);
});

// Make updateSocketGuestName available globally for profile updates
window.updateSocketGuestName = function(newGuestName) {
    console.log("updateSocketGuestName called with:", newGuestName);
    
    // Update global variable
    window.GUEST_NAME = newGuestName;
    console.log("updateSocketGuestName: Updated window.GUEST_NAME to:", window.GUEST_NAME);
    
    // Update dashboard state - ensure it exists first
    if (!window.dashboardState) {
        window.dashboardState = {};
        console.log("updateSocketGuestName: Created dashboardState object");
    }
    window.dashboardState.guestName = newGuestName;
    window.dashboardState.guestNameSource = 'profile-update';
    console.log("updateSocketGuestName: Updated dashboardState.guestName to:", window.dashboardState.guestName);
    
    // If socket is connected, emit the update to server
    if (socket && socket.connected) {
        console.log('updateSocketGuestName: Emitting guest name update to server via socket:', newGuestName);
        socket.emit('update_guest_name', {
            guest_name: newGuestName
        });
    } else {
        console.log('updateSocketGuestName: Socket not connected, guest name will be updated when socket connects');
    }
    
    console.log("updateSocketGuestName: Function completed successfully");
};

// Export functions for use in other modules
export {
    initializeSocketIOProcess,
    checkAndEnableChatButton,
    initializeChat,
    enableChatControls,
    sendTextMessage,
    socket,
    isSocketConnected,
    endChatSession  // Export the new function
};
