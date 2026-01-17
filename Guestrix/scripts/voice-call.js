/*
 * Voice Call functionality for Guestrix Landing Page
 */

// Constants for audio processing
const GEMINI_OUTPUT_SAMPLE_RATE = 24000;  // Gemini audio is 24kHz
const MIC_BUFFER_SIZE = 4096;  // Size of microphone audio buffer
const GEMINI_LIVE_MODEL = "gemini-2.0-flash-live-001";  // Model ID for live voice calls
const GEMINI_API_VERSION = "v1beta"; // The API version required for Live API
const GEMINI_VOICES = ["Aoede", "Chorister", "Dawnsmell", "Hearth", "Joyishness", "Jurai", "Patzelt", "Shiralish"];
const GEMINI_DEFAULT_VOICE = "Aoede";  // Default voice to use
const MAX_AUDIO_QUEUE_LENGTH = 60;  // Maximum number of chunks to keep in the audio queue
const AUDIO_INITIAL_BUFFER_COUNT = 3;  // Number of chunks to buffer before playing

// Voice Call Globals
let currentCallState = 'idle'; // idle, starting, active, stopping
let microphoneStream = null;
let audioProcessorNode = null;
let geminiWebSocket = null;

// Audio playback variables
let audioQueue = [];
let isAudioPlaying = false;
let audioContext = null;
let mainAudioBuffer = null;
let audioBuffering = true;
let nextChunkStartTime = 0;
let audioSourceNode = null;
let activeAudioSources = []; // Track all active audio sources
let audioTimeouts = []; // Track all audio-related timeouts

// Call timeout management
const CALL_TIMEOUT_MINUTES = 10; // Maximum call duration in minutes
const WARNING_SECONDS = 30; // Warn user 30 seconds before timeout
let callStartTime = null;
let callTimeoutId = null;
let warningTimeoutId = null;

// Current voice - use stored preference or default
let currentGeminiVoice = localStorage.getItem('geminiVoicePreference') || "Aoede";

// Function to initialize voice call system
function initializeVoiceCall() {
    const voiceCallButton = document.getElementById('voice-call-button');

    // Ensure the voice call button exists
    if (voiceCallButton) {
        voiceCallButton.addEventListener('click', async function() {
            if (currentCallState === 'idle') {
                try {
                    await handleVoiceCallStart();
                } catch (error) {
                    console.error("Error starting call:", error);
                    updateButtonState('idle');
                }
            } else if (currentCallState === 'active') {
                stopVoiceCall("User ended call");
            }
        });
    }

    console.log("Voice call system initialized");
}

// Function to update button state
function updateButtonState(state) {
    const voiceCallButton = document.getElementById('voice-call-button');
    if (!voiceCallButton) return;

    const btnText = voiceCallButton.querySelector('.btn-text');
    const icon = voiceCallButton.querySelector('i');

    voiceCallButton.setAttribute('data-status', state);

    switch (state) {
        case 'idle':
            btnText.textContent = 'Talk to Staycee';
            icon.className = 'fas fa-microphone';
            voiceCallButton.disabled = false;
            break;
        case 'connecting':
            btnText.textContent = 'Connecting...';
            icon.className = 'fas fa-spinner fa-spin';
            voiceCallButton.disabled = true;
            break;
        case 'active':
            btnText.textContent = 'End Call';
            icon.className = 'fas fa-phone-slash';
            voiceCallButton.disabled = false;
            break;
    }
}

// Handler for voice call start
async function handleVoiceCallStart() {
    // Only start if we're idle
    if (currentCallState !== 'idle') {
        console.log("Call already in progress, state:", currentCallState);
        return;
    }

    // Update state
    currentCallState = 'starting';
    updateButtonState('connecting');

    try {
        // 1. Get API Key from server
        const config = await fetchGeminiConfig();
        const apiKey = config.apiKey;

        if (!apiKey) {
            throw new Error("No API key available. Please contact support.");
        }

        // 2. Request microphone access
        try {
            microphoneStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            console.log("Microphone access granted");

            // 3. Start the Gemini voice call
            await startGeminiVoiceCall(apiKey);

        } catch (micError) {
            console.error("Microphone access denied:", micError);
            throw new Error("Microphone access required for voice call");
        }

    } catch (error) {
        console.error("Error starting voice call:", error);
        updateButtonState('idle');
        currentCallState = 'idle';
    }
}

// Start a voice call with Gemini API
async function startGeminiVoiceCall(apiKey) {
    try {
        // 1. Set up audio context for processing microphone input
        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 16000 // Use 16kHz for input to match Gemini's expected input format
        });
        const micSource = audioContext.createMediaStreamSource(microphoneStream);

        // Create processor node for capturing audio
        audioProcessorNode = audioContext.createScriptProcessor(MIC_BUFFER_SIZE, 1, 1);
        micSource.connect(audioProcessorNode);
        audioProcessorNode.connect(audioContext.destination);

        // Buffer for collecting audio chunks
        let audioChunks = [];
        let lastSendTime = 0;
        const SEND_INTERVAL_MS = 100; // Send audio every 100ms

        // 2. Create WebSocket connection to Gemini API
        // Close any existing WebSocket connection
        if (geminiWebSocket) {
            try {
                geminiWebSocket.close();
            } catch (e) {
                console.warn("Error closing existing WebSocket:", e);
            }
        }

        // Construct WebSocket URL
        const wsUrl = `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=${apiKey}&alt=json`;

        // Create WebSocket connection
        geminiWebSocket = new WebSocket(wsUrl);

        // Reset audio processing state for new connection
        audioChunks = [];
        audioQueue = [];
        isAudioPlaying = false;
        audioBuffering = true;
        nextChunkStartTime = 0;

        // Handle connection open
        geminiWebSocket.onopen = () => {
            // Create initial configuration for Gemini Live API
            const initialConfig = {
                setup: {
                    model: `models/${GEMINI_LIVE_MODEL}`,
                    generationConfig: {
                        responseModalities: ["AUDIO"],
                        speechConfig: {
                            voiceConfig: {
                                prebuiltVoiceConfig: {
                                    voiceName: currentGeminiVoice
                                }
                            },
                            languageCode: "en-US"
                        }
                    },
                    tools: [
                        {
                            google_search: {}
                        },
                        {
                            function_declarations: [
                                {
                                    name: "end_call",
                                    description: "End the voice call when the conversation has reached a natural conclusion or when the user indicates they want to end the call. Use this when the conversation is complete.",
                                    parameters: {
                                        type: "object",
                                        properties: {
                                            reason: {
                                                type: "string",
                                                description: "Brief reason for ending the call (e.g., 'conversation complete', 'user request', 'natural conclusion')"
                                            }
                                        },
                                        required: ["reason"]
                                    }
                                }
                            ]
                        }
                    ],
                    systemInstruction: {
                        parts: [
                            {
                                text: createVoiceSystemPrompt()
                            }
                        ]
                    },
                    // Added configuration for realtime input to handle interruptions better
                    realtimeInputConfig: {
                        // Configure voice activity detection for better sensitivity
                        automaticActivityDetection: {
                            disabled: false, // Enable automatic activity detection
                            startOfSpeechSensitivity: "START_SENSITIVITY_HIGH", // Detect speech start more quickly
                            endOfSpeechSensitivity: "END_SENSITIVITY_LOW", // Don't end speech detection too quickly
                            prefixPaddingMs: 50, // Even lower value for faster speech detection
                            silenceDurationMs: 500 // Shorter silence duration for more responsive interruptions
                        },
                        // Make sure the model is interrupted when user starts speaking
                        activityHandling: "START_OF_ACTIVITY_INTERRUPTS", // This enables barge-in functionality
                        // Include all input in the user's turn
                        turnCoverage: "TURN_INCLUDES_ALL_INPUT"
                    }
                }
            };

            geminiWebSocket.send(JSON.stringify(initialConfig));

            // Send an initial greeting message to get the AI started
            setTimeout(() => {
                if (geminiWebSocket && geminiWebSocket.readyState === WebSocket.OPEN) {
                    const initialMessage = {
                        client_content: {
                            turn_complete: true,
                            turns: [{
                                role: "user",
                                parts: [{ text: "Hello, could you introduce yourself as Staycee, my Guestrix concierge assistant?" }]
                            }]
                        }
                    };

                    geminiWebSocket.send(JSON.stringify(initialMessage));
                }
            }, 1000); // Small delay to ensure configuration is processed first

            // Update UI to show active call state
            currentCallState = 'active';
            updateButtonState('active');

            // Start call timeout management
            startCallTimeout();
        };

        // Handle incoming messages from Gemini (audio chunks or text)
        geminiWebSocket.onmessage = (event) => {
            try {
                // Check message type
                if (typeof event.data === 'string') {
                    // Parse JSON response
                    try {
                        const jsonMessage = JSON.parse(event.data);

                        // Check specifically for interruption message
                        if (jsonMessage.serverContent && jsonMessage.serverContent.interrupted === true) {
                            console.log("User interrupted - clearing audio queue");
                            // Stop active playback immediately and aggressively
                            stopAllAudioPlayback();
                            updateCallStatus("Listening...");
                            return; // Exit early to prevent any further audio processing
                        }
                        // Check for turn_complete message which means model is done speaking
                        else if (jsonMessage.serverContent && jsonMessage.serverContent.turnComplete === true) {
                            console.log("Model turn complete");
                            updateCallStatus("Listening...");
                        }
                        // Otherwise process normally for content
                        else {
                            // Process the JSON message to extract content
                            processGeminiJsonMessage(jsonMessage);
                        }

                    } catch (parseError) {
                        console.error("Error parsing JSON message:", parseError);
                    }
                } else if (event.data instanceof Blob) {
                    // Handle binary data (likely audio)
                    const blob = event.data;

                    // Convert Blob to ArrayBuffer for processing
                    blob.arrayBuffer().then(arrayBuffer => {
                        // First check if this is a JSON message wrapped in a blob
                        const decoder = new TextDecoder('utf-8');
                        try {
                            // Try to decode as UTF-8 text
                            const text = decoder.decode(arrayBuffer);
                            // Check if this looks like JSON
                            if (text.trim().startsWith('{') && text.trim().endsWith('}')) {
                                try {
                                    const jsonMessage = JSON.parse(text);

                                    // Process the JSON message
                                    processGeminiJsonMessage(jsonMessage);
                                    return;
                                } catch (e) {
                                    // Not valid JSON, continue with binary processing
                                }
                            }
                        } catch (textError) {
                            // Not valid text, treat as binary data
                        }

                        // Process as binary audio data
                        if (arrayBuffer.byteLength > 0) {
                            queueAudioForPlayback(arrayBuffer);
                        }
                    }).catch(error => {
                        console.error("Error processing blob data:", error);
                    });
                } else {
                    console.warn("Received unknown data type from WebSocket");
                }
            } catch (error) {
                console.error("Error in WebSocket message handler:", error);
            }
        };

        // Handle WebSocket errors
        geminiWebSocket.onerror = (error) => {
            console.error("WebSocket error:", error);
            stopVoiceCall("Connection error");
            updateCallStatus("Error with connection. Please try again.");
        };

        // Handle WebSocket closure with enhanced reconnection logic
        geminiWebSocket.onclose = (event) => {
            console.log(`WebSocket closed. Code: ${event.code}, Reason: ${event.reason}`);

            // Handle normal closure vs unexpected closure
            if (event.code === 1000) {
                // Normal closure
                if (currentCallState === 'active') {
                    stopVoiceCall(`Connection closed normally`);
                }
            } else {
                // Unexpected closure - attempt to reconnect if call should still be active
                console.warn(`WebSocket closed unexpectedly with code ${event.code}. Attempting to reconnect...`);
                if (currentCallState === 'active') {
                    // Update UI to show reconnection attempt
                    updateCallStatus("Connection interruption. Attempting to reconnect...");

                    // Attempt to reconnect in 2 seconds
                    setTimeout(() => {
                        if (currentCallState === 'active') {
                            try {
                                console.log("Attempting to reconnect voice call...");
                                // Get API key for reconnection
                                let apiKey = '';
                                const localStorageApiKey = localStorage.getItem('GEMINI_API_KEY');
                                if (localStorageApiKey) {
                                    apiKey = localStorageApiKey;
                                } else if (window.GEMINI_API_KEY) {
                                    apiKey = window.GEMINI_API_KEY;
                                }

                                if (apiKey) {
                                    startGeminiVoiceCall(apiKey).catch(error => {
                                        console.error("Reconnection failed:", error);
                                        updateCallStatus("Reconnection failed. Please try again.");
                                        stopVoiceCall("Reconnection failed");
                                    });
                                } else {
                                    console.error("Cannot reconnect - no API key available");
                                    updateCallStatus("Cannot reconnect - please restart call.");
                                    stopVoiceCall("Cannot reconnect - missing API key");
                                }
                            } catch (error) {
                                console.error("Error during reconnection attempt:", error);
                                updateCallStatus("Reconnection error. Please try again.");
                                stopVoiceCall("Reconnection error");
                            }
                        }
                    }, 2000);
                }
            }
        };

        // Set up audio processor to handle microphone input
        audioProcessorNode.onaudioprocess = (e) => {
            // Check if we have an active connection
            if (geminiWebSocket && geminiWebSocket.readyState === WebSocket.OPEN && currentCallState === 'active') {
                // Get the audio data
                const inputData = e.inputBuffer.getChannelData(0);

                // Convert to 16-bit PCM for Gemini
                const pcmData = new Int16Array(inputData.length);
                for (let i = 0; i < inputData.length; i++) {
                    // Convert float [-1.0, 1.0] to int16 [-32768, 32767]
                    pcmData[i] = Math.max(-1, Math.min(1, inputData[i])) * 0x7FFF;
                }

                // Add to audio chunks
                audioChunks.push(pcmData.buffer);

                // Send audio on a regular interval
                const now = Date.now();
                if (now - lastSendTime >= SEND_INTERVAL_MS) {
                    // Combine chunks into a single buffer
                    const combinedLength = audioChunks.reduce((acc, chunk) => acc + chunk.byteLength, 0);
                    if (combinedLength > 0) {
                        const combinedBuffer = new Uint8Array(combinedLength);

                        let offset = 0;
                        for (const chunk of audioChunks) {
                            combinedBuffer.set(new Uint8Array(chunk), offset);
                            offset += chunk.byteLength;
                        }

                        // Convert to base64 for Gemini
                        const base64Audio = arrayBufferToBase64(combinedBuffer.buffer);

                        // Send to Gemini using the LiveAPI format
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
                            // Only log audio sending occasionally to reduce console noise
                            if (Math.random() < 0.1) {
                                console.log(`Sent ${combinedLength} bytes of audio to Gemini`);
                            }
                            // Clear chunks after sending
                            audioChunks = [];
                            lastSendTime = now;
                        } catch (err) {
                            console.error("Error sending audio to Gemini:", err);
                        }
                    }
                }
            }
        };

        console.log("Voice call successfully started");
    } catch (error) {
        console.error("Error setting up voice call:", error);
        stopVoiceCall(`Setup error: ${error.message}`);
        throw error;
    }
}

// Function to stop the voice call
function stopVoiceCall(reason = "User ended call") {
    console.log("Stopping voice call. Reason:", reason);

    // Add cleanup for the WebSocket connection
    if (geminiWebSocket) {
        // Send a message to the server to indicate the call is ending
        if (geminiWebSocket.readyState === WebSocket.OPEN) {
            try {
                // Send activity_end message to Gemini Live API
                geminiWebSocket.send(JSON.stringify({
                    realtime_input: {
                        activity_end: {}
                    }
                }));

                // Send audio_stream_end to flush any cached audio
                geminiWebSocket.send(JSON.stringify({
                    realtime_input: {
                        audio_stream_end: true
                    }
                }));
            } catch (error) {
                console.error("Error sending end session message:", error);
            }
        }

        // Close the WebSocket connection
        try {
            geminiWebSocket.close(1000, reason);
        } catch (error) {
            console.error("Error closing WebSocket:", error);
        }
        geminiWebSocket = null;
    }

    // Stop and clean up the microphone stream
    if (microphoneStream) {
        try {
            microphoneStream.getTracks().forEach(track => track.stop());
            console.log("Microphone stream stopped.");
        } catch (error) {
            console.error("Error stopping microphone stream:", error);
        }
        microphoneStream = null;
    }

    // Clean up audio processor node
    if (audioProcessorNode) {
        try {
            audioProcessorNode.disconnect();
        } catch (error) {
            console.error("Error disconnecting audio processor node:", error);
        }
        audioProcessorNode = null;
    }

    // Clean up audio context
    if (audioContext) {
        try {
            if (audioContext.state !== 'closed') {
                audioContext.close();
            }
        } catch (error) {
            console.error("Error closing audio context:", error);
        }
        audioContext = null;
    }

    // Stop any remaining audio playback
    stopAllAudioPlayback();

    // Stop audio visualization
    stopAudioVisualization();

    // Clear call timeout management
    clearCallTimeouts();

    // Update UI state
    currentCallState = 'idle';
    updateButtonState('idle');
}

// Update call status text
function updateCallStatus(message) {
    const callStatus = document.querySelector('.call-status');
    if (callStatus) {
        callStatus.textContent = message;
    }
}

// Update call buttons state
function updateCallButtons(startDisabled, endEnabled) {
    const startButtonContainer = document.getElementById('startButtonContainer');
    const endButtonContainer = document.getElementById('endButtonContainer');

    if (startButtonContainer && endButtonContainer) {
        if (endEnabled) {
            // Active call - show End button, hide Start button
            startButtonContainer.style.display = 'none';
            endButtonContainer.style.display = 'block';
        } else {
            // No active call - show Start button, hide End button
            startButtonContainer.style.display = 'block';
            endButtonContainer.style.display = 'none';
        }
    }

    // When call is active, display a hint about interruption capability
    const callStatus = document.querySelector('.call-status');
    if (callStatus && endEnabled) {
        // Add a small hint below the status
        let interruptHint = document.getElementById('interrupt-hint');
        if (!interruptHint) {
            interruptHint = document.createElement('div');
            interruptHint.id = 'interrupt-hint';
            interruptHint.style.fontSize = '12px';
            interruptHint.style.opacity = '0.8';
            interruptHint.style.marginTop = '5px';
            interruptHint.style.fontStyle = 'italic';
            callStatus.parentNode.appendChild(interruptHint);
        }
        interruptHint.textContent = "You can interrupt Staycee anytime by speaking";
    } else {
        // Remove the hint when call is not active
        const interruptHint = document.getElementById('interrupt-hint');
        if (interruptHint) {
            interruptHint.remove();
        }
    }
}

// Call timeout management functions
function startCallTimeout() {
    callStartTime = Date.now();

    // Set warning timeout (30 seconds before end)
    const warningTime = (CALL_TIMEOUT_MINUTES * 60 - WARNING_SECONDS) * 1000;
    warningTimeoutId = setTimeout(() => {
        if (currentCallState === 'active') {
            console.log("Call timeout warning triggered");
            sendTimeoutWarning();
        }
    }, warningTime);

    // Set final timeout
    const timeoutTime = CALL_TIMEOUT_MINUTES * 60 * 1000;
    callTimeoutId = setTimeout(() => {
        if (currentCallState === 'active') {
            console.log("Call timeout reached, ending call");
            stopVoiceCall("Call timeout reached (10 minutes)");
        }
    }, timeoutTime);

    console.log(`Call timeout set for ${CALL_TIMEOUT_MINUTES} minutes`);
}

function sendTimeoutWarning() {
    if (geminiWebSocket && geminiWebSocket.readyState === WebSocket.OPEN) {
        const warningMessage = {
            client_content: {
                turn_complete: true,
                turns: [{
                    role: "user",
                    parts: [{
                        text: `SYSTEM: This call will automatically end in ${WARNING_SECONDS} seconds due to time limit. Please wrap up the conversation.`
                    }]
                }]
            }
        };

        try {
            geminiWebSocket.send(JSON.stringify(warningMessage));
            updateCallStatus(`Call ending in ${WARNING_SECONDS} seconds...`);
        } catch (error) {
            console.error("Error sending timeout warning:", error);
        }
    }
}

function clearCallTimeouts() {
    if (callTimeoutId) {
        clearTimeout(callTimeoutId);
        callTimeoutId = null;
    }
    if (warningTimeoutId) {
        clearTimeout(warningTimeoutId);
        warningTimeoutId = null;
    }
    callStartTime = null;
}

function getRemainingCallTime() {
    if (!callStartTime) return null;

    const elapsed = Date.now() - callStartTime;
    const remaining = (CALL_TIMEOUT_MINUTES * 60 * 1000) - elapsed;
    return Math.max(0, Math.floor(remaining / 1000)); // Return seconds remaining
}

// Create voice system prompt
function createVoiceSystemPrompt() {
    return `
    You are Staycee, a helpful AI concierge assistant for Guestrix.
    You are speaking with a potential guest who is interested in your services.
    Your goal is to assist the guest with any questions they have about Guestrix's services and this property.
    Be conversational, friendly, and helpful.

    IMPORTANT CONVERSATION GUIDELINES:
    1. Keep your responses concise and to the point - aim for 1-3 sentences at a time
    2. Pause naturally between thoughts to allow the user to interject
    3. When you sense the user wants to speak, stop immediately and listen
    4. If interrupted, acknowledge it and address the user's new question
    5. Be responsive to verbal cues from the user
    6. NEVER say words like "pause", "wait", "hold on", or similar filler words during your responses
    7. Speak naturally and continuously without announcing pauses or breaks
    8. This call has a ${CALL_TIMEOUT_MINUTES}-minute time limit for demo purposes
    9. When the conversation reaches a natural conclusion, use the end_call tool to gracefully end the call

    As Staycee, your primary purpose is to eliminate the need for guests to contact their host directly.
    When guests have requests or issues:
    1. For questions you can answer (amenities, wifi, checkout procedures, etc.) - provide the information directly
    2. For maintenance issues - tell guests you'll notify the host immediately (don't provide contact info)
    3. For booking changes - offer to relay the request to the host
    4. For emergencies - advise calling 911 first, then tell them you'll alert the host

    NEVER give out the host's direct contact information. Always position yourself as the intermediary
    who will handle communication with the host. Use phrases like "I'll let Michael know right away"
    or "I'll make sure this gets addressed promptly."

    CRITICAL INFRASTRUCTURE PROTECTION:
    If a guest asks about the location of critical infrastructure elements such as water shutoff valves, electrical panels, fuse boxes, circuit breakers, gas shutoff valves, HVAC system controls, air handler units, ventilation system access, sump pumps, water heaters, or other mechanical systems, you MUST first ask the guest to explain the specific reason they need this information. Only provide access details if there is a genuine emergency situation such as fire, smoke, electrical hazards, water leaks, flooding, pipe bursts, gas leaks, HVAC system failures causing dangerous temperatures, or any situation where immediate access would prevent property damage or ensure guest safety. For non-emergency requests, politely explain that this information is restricted for safety and security reasons, and suggest they contact the host directly.

    About Guestrix:
    - Guestrix is an AI-powered guest management solution for short-term rentals
    - Staycee (you) handles guest communications, provides recommendations, and helps with property details
    - Guestrix helps property hosts save time and provide better guest experiences

    Today's date is ${new Date().toLocaleDateString()}.

    ## Property Information for Pine Haven Cottage:

    ### Address and Access:
    - Address: 158 Woodland Lane, Lake Tahoe, CA 96150
    - Check-in: Anytime after 4:00 PM (self check-in with keypad)
    - Check-out: By 11:00 AM
    - Door code: 3817# (I'll send the code again on your check-in day)
    - Parking: Park in the driveway - it fits 2 cars. Additional street parking is available but not overnight during winter (Nov-Apr) due to snow plowing
    - Heating: Thermostat is in the living room next to the kitchen entrance. Please keep between 68-74°F and turn down to 65°F when leaving for more than 4 hours

    ### WiFi and Entertainment:
    - WiFi name: PineHaven_Guest
    - WiFi password: Pinecone2024!
    - Smart TV in living room (Netflix and Disney+ logged in)
    - Roku TV in master bedroom (use your own accounts)
    - Board games in the cabinet under the window seat
    - Extra HDMI cables in the drawer under the TV

    ### Kitchen:
    - Coffee maker: On the counter with filters in the drawer below
    - Mugs: Cabinet above coffee maker
    - Dishes and glasses: Upper cabinets to the right of the sink
    - Pots and pans: Lower cabinet left of the stove
    - Utensils: Top drawer next to the dishwasher
    - Trash bags: Under the sink
    - Spices: In the rack next to the stove (please feel free to use)
    - Dishwasher: Please rinse dishes first and start it before check-out

    ### Bedrooms:
    - Master bedroom (king bed): Extra blankets in the chest at the foot of the bed, hangers in the closet
    - Second bedroom (queen bed): Extra pillow in the closet
    - Third bedroom (two twins): Pack-n-play under the bed if needed for children
    - All bedrooms have USB charging ports on the bedside lamps

    ### Bathrooms:
    - Master bathroom: Hair dryer under the sink, extra toilet paper in the cabinet
    - Main bathroom: Shampoo, conditioner, and body wash provided in the shower
    - Extra towels: In the linen closet in the hallway
    - Please hang wet towels on the hooks or towel racks (not on the beds or furniture)

    ### House Rules:
    - No smoking anywhere on the property (subject to $350 cleaning fee)
    - No parties or events
    - Quiet hours: 10:00 PM to 8:00 AM (neighbors are close)
    - No shoes in the house please (mudroom has a rack for shoes)
    - No pets (I have allergies, sorry!)
    - Maximum 6 guests total (including children)

    ### Amenities:
    - Washer/dryer in the laundry room (detergent provided)
    - Deck with patio furniture and propane grill (propane tank should be full, spare in the shed)
    - Fireplace in living room (gas - switch is on the right side)
    - Hot water can take 1-2 minutes to reach upstairs bathrooms
    - Hiking trails map on the bulletin board in the entryway

    ### Local Information:
    - Nearest grocery store: Safeway (10 min drive, open until 11 PM)
    - Good coffee: Mountain Brew (walkable, 3 blocks north)
    - Our favorite restaurants:
      • The Lodge (upscale, reservations recommended)
      • Lakeside Grill (casual, great sunset views)
      • Romano's (best pizza delivery, menu in kitchen drawer)
    - Lake access: Community beach is 5-minute walk (gate code: 5291#)
    - Ski shuttle stop: Corner of Pine and Cedar Street (2 blocks)

    ### Emergency & Support:
    - For urgent property issues: Just ask Staycee and I'll notify Michael (your host) immediately
    - For maintenance requests: Tell Staycee what needs fixing and I'll make sure it's addressed
    - For extending your stay or special requests: Ask Staycee and I'll coordinate with your host
    - Medical emergency: Call 911 directly (property address is 158 Woodland Lane)
    - Hospital: Barton Memorial (15 min drive, 2170 South Ave)
    - Remember: No need to contact the host directly - that's why I'm here!

    ### Departure Instructions:
    - Please leave keys on the kitchen counter
    - Lock all doors and windows
    - Turn thermostat to 65°F (55°F in winter)
    - Place used towels on the bathroom floors
    - Take out trash and recycling to bins by the side of the garage
    - Dishes can be left clean in the dishwasher

    You have access to the following tools:
    1. google_search: Use this tool to search for information about local attractions, restaurants, services, or any other information that would be helpful to the guest.
    2. end_call: Use this tool to gracefully end the call when the conversation has reached a natural conclusion or when the user indicates they want to end the call.

    When using the google_search tool:
    - First tell the guest "Let me search for that information for you"
    - After receiving the search results, provide a concise and helpful summary

    When using the end_call tool:
    - Use it when the conversation has naturally concluded
    - Use it if the user says goodbye or indicates they want to end the call
    - Use it if you've answered all their questions and there's nothing more to discuss
    - Provide a brief reason for ending the call

    Respond to the guest's voice queries to help them understand how Guestrix can assist with their rental property, providing property-specific information when relevant.
    `;
}

// Function to fetch Gemini API Key from server or use localStorage in development
async function fetchGeminiConfig() {
    // Always fetch from server for security - no client-side API key exposure
    
    // Determine the correct API endpoint based on environment
    const isLocalDev = window.location.hostname === 'localhost' ||
                      window.location.hostname === '127.0.0.1';
    
    // Check if we're in production or staging
    const isProduction = window.location.hostname.includes('main.') || 
                        window.location.hostname.includes('production') ||
                        window.location.hostname === 'guestrix.ai';
    
    let apiEndpoint;
    if (isLocalDev) {
        apiEndpoint = '/api/gemini-config'; // Local development server
    } else if (isProduction) {
        apiEndpoint = 'https://s7t5zf07zj.execute-api.us-east-2.amazonaws.com/prod/waitlist/gemini-config'; // Production API
    } else {
        apiEndpoint = 'https://fx6ti5wvm9.execute-api.us-east-2.amazonaws.com/dev/waitlist/gemini-config'; // Staging API
    }
    
    try {
        const response = await fetch(apiEndpoint, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const config = await response.json();
        if (!config.apiKey) {
            throw new Error("API key not found in server response");
        }

        console.log("API key fetched from server");
        return config;
    } catch (error) {
        console.error("Error fetching Gemini config:", error);
        
        // Only for local development - fallback to localStorage or prompt
        if (isLocalDev) {
            const localStorageKey = localStorage.getItem('GEMINI_API_KEY');
            if (localStorageKey) {
                console.log("Using API key from localStorage (dev mode)");
                return { apiKey: localStorageKey };
            }
            
            // Prompt for key in development
            const apiKey = prompt("Enter your Gemini API key for development:");
            if (apiKey && apiKey.length > 10) {
                localStorage.setItem('GEMINI_API_KEY', apiKey);
                console.log("API key saved to localStorage for development");
                return { apiKey };
            }
        }
        
        throw error;
    }
}

// Audio visualization functions
function startAudioVisualization() {
    const audioBars = document.querySelectorAll('.audio-bar');
    if (audioBars.length > 0) {
        audioBars.forEach(bar => {
            bar.classList.add('active');
        });
    }
}

function stopAudioVisualization() {
    const audioBars = document.querySelectorAll('.audio-bar');
    if (audioBars.length > 0) {
        audioBars.forEach(bar => {
            bar.classList.remove('active');
        });
    }
}

// Utility function to convert ArrayBuffer to Base64
function arrayBufferToBase64(buffer) {
    const binary = [];
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < bytes.byteLength; i++) {
        binary.push(String.fromCharCode(bytes[i]));
    }
    return btoa(binary.join(''));
}

// Queue audio for playback
function queueAudioForPlayback(audioBuffer) {
    if (!audioBuffer || audioBuffer.byteLength === 0) {
        console.warn("Received empty audio buffer, not queueing for playback");
        return;
    }

    // Don't queue audio if we're not in an active call state
    if (currentCallState !== 'active') {
        console.log("Ignoring audio buffer - call not active");
        return;
    }

    // Sample count for diagnostics
    const sampleCount = Math.floor(audioBuffer.byteLength / 2);

    // Quick validation of audio data
    if (audioBuffer.byteLength < 256) {
        return;
    }

    // Create audio context if needed
    if (!window.audioPlayerContext) {
        try {
            window.audioPlayerContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: GEMINI_OUTPUT_SAMPLE_RATE,
                latencyHint: 'interactive'
            });
        } catch (error) {
            console.error("Failed to create audio context:", error);
            return;
        }
    }

    // Ensure context is running
    if (window.audioPlayerContext && window.audioPlayerContext.state === 'suspended') {
        window.audioPlayerContext.resume().catch(error => {
            console.error("Error resuming audio context:", error);
        });
    }

    // Add to queue and track if queue was empty
    const wasQueueEmpty = audioQueue.length === 0;
    audioQueue.push(audioBuffer);

    // Keep queue from growing too large
    while (audioQueue.length > MAX_AUDIO_QUEUE_LENGTH) {
        audioQueue.shift();
        console.warn("Audio queue too large, dropping oldest chunk");
    }

    // Start playback if we're not already playing
    if (wasQueueEmpty && !isAudioPlaying) {
        startContinuousPlayback();
    }
}

// Start continuous audio playback
function startContinuousPlayback() {
    // Check if we have audio to play
    if (audioQueue.length === 0) {
        isAudioPlaying = false;
        return;
    }

    isAudioPlaying = true;

    // Process audio continuously from the queue
    processAudioContinuously();
}

// Process audio continuously from the queue (enhanced from guest dashboard)
function processAudioContinuously() {
    // Check if we have an active call and if playback should continue
    if (currentCallState !== 'active') {
        isAudioPlaying = false;
        audioQueue = [];
        return;
    }

    // Additional check: if we're not supposed to be playing, stop immediately
    if (!isAudioPlaying) {
        audioQueue = [];
        return;
    }

    if (audioQueue.length === 0) {
        const timeoutId = setTimeout(() => {
            // Double-check that we should still be playing before continuing
            if (audioQueue.length > 0 && isAudioPlaying && currentCallState === 'active') {
                processAudioContinuously();
            } else {
                isAudioPlaying = false;
            }
        }, 100);

        // Track this timeout so we can clear it if needed
        audioTimeouts.push(timeoutId);
        return;
    }

    const audioCtx = window.audioPlayerContext;

    try {
        // Get the next chunk of audio from the queue
        const audioData = audioQueue.shift();

        // Process the PCM data into a Web Audio buffer
        const numSamples = audioData.byteLength / 2; // 16-bit = 2 bytes per sample
        const audioBuffer = audioCtx.createBuffer(1, numSamples, GEMINI_OUTPUT_SAMPLE_RATE);
        const channelData = audioBuffer.getChannelData(0);

        // Use DataView for correct byte interpretation
        const view = new DataView(audioData);

        // Convert Int16 data to Float32Array (Web Audio API format)
        for (let i = 0; i < numSamples; i++) {
            // Use DataView's getInt16 to correctly interpret the bytes as signed 16-bit integers
            const int16Sample = view.getInt16(i * 2, true); // true = little-endian

            // Convert Int16 [-32768, 32767] to Float32 [-1.0, 1.0]
            channelData[i] = int16Sample / 32768.0;
        }

        // Create a source node for this buffer
        const source = audioCtx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioCtx.destination);

        // Save reference to current source node to be able to stop it if interrupted
        audioSourceNode = source;

        // Track this source in our active sources array
        activeAudioSources.push(source);

        // Calculate start time for this buffer
        const currentTime = audioCtx.currentTime;
        let startTime;

        if (nextChunkStartTime <= currentTime) {
            // If next chunk start time is in the past or current, start immediately with a small offset
            startTime = currentTime + 0.01;
        } else {
            // Otherwise use the scheduled time
            startTime = nextChunkStartTime;
        }

        // Start the audio playback
        source.start(startTime);

        // Update the next chunk start time
        nextChunkStartTime = startTime + audioBuffer.duration;

        // When this chunk ends, schedule the next one
        source.onended = () => {
            // Remove this source from active sources array
            const sourceIndex = activeAudioSources.indexOf(source);
            if (sourceIndex > -1) {
                activeAudioSources.splice(sourceIndex, 1);
            }

            // Clear the reference if this was the current source
            if (audioSourceNode === source) {
                audioSourceNode = null;
            }

            // Only continue if call is still active
            if (currentCallState === 'active' && isAudioPlaying) {
                processAudioContinuously();
            }
        };

        // Set a safety timeout in case the onended event doesn't fire
        const timeoutId = setTimeout(() => {
            // Only continue if call is still active
            if (audioQueue.length > 0 && isAudioPlaying && currentCallState === 'active') {
                processAudioContinuously();
            }
        }, audioBuffer.duration * 1000 + 100);

        // Track this timeout so we can clear it if needed
        audioTimeouts.push(timeoutId);

    } catch (error) {
        console.error("Error processing audio:", error);
        // Try to continue with the next chunk only if call is still active
        const timeoutId = setTimeout(() => {
            if (audioQueue.length > 0 && currentCallState === 'active') {
                processAudioContinuously();
            } else {
                isAudioPlaying = false;
            }
        }, 100);

        // Track this timeout too
        audioTimeouts.push(timeoutId);
    }
}

// Function to stop all audio playback immediately (enhanced from guest dashboard)
function stopAllAudioPlayback() {
    console.log("🔇 Stopping all active audio playback immediately");

    // Stop the current audio source node
    if (audioSourceNode) {
        try {
            audioSourceNode.stop();
            audioSourceNode.disconnect();
            audioSourceNode = null;
        } catch (e) {
            console.warn("Error stopping current audio source:", e);
        }
    }

    // Stop ALL active audio sources that might be scheduled or playing
    activeAudioSources.forEach((source, index) => {
        try {
            if (source && typeof source.stop === 'function') {
                source.stop();
                source.disconnect();
            }
        } catch (e) {
            console.warn(`Error stopping audio source ${index}:`, e);
        }
    });
    activeAudioSources = []; // Clear the array

    // Clear all audio-related timeouts
    audioTimeouts.forEach(timeoutId => {
        try {
            clearTimeout(timeoutId);
        } catch (e) {
            console.warn("Error clearing timeout:", e);
        }
    });
    audioTimeouts = []; // Clear the array

    // Clear audio queue completely
    const droppedChunks = audioQueue.length;
    audioQueue = [];
    isAudioPlaying = false;
    nextChunkStartTime = 0;
    audioBuffering = true;

    if (droppedChunks > 0) {
        console.log(`🗑️ Dropped ${droppedChunks} queued audio chunks`);
    }

    // Reset audio context timing
    if (window.audioPlayerContext) {
        nextChunkStartTime = window.audioPlayerContext.currentTime;
    }

    console.log("✅ All audio playback stopped successfully");
}

// Backward compatibility alias
function stopActiveAudioPlayback() {
    stopAllAudioPlayback();
}

// Function to process JSON messages from Gemini
function processGeminiJsonMessage(jsonMessage) {
    // Check for setup completion confirmation
    if (jsonMessage.setupComplete) {
        return;
    }

    // Check for interruption event
    if (jsonMessage.serverContent && jsonMessage.serverContent.interrupted) {
        console.log("User interrupted - stopping audio playback");
        // Stop any active audio playback immediately
        stopAllAudioPlayback();
        updateCallStatus("Listening...");
        return; // Exit immediately to prevent processing any audio in this message
    }

    // Check for audio data
    let audioDataFound = false;

    // Direct audio in base64 format
    if (jsonMessage.audio && typeof jsonMessage.audio === 'string') {
        const audioData = base64ToArrayBuffer(jsonMessage.audio);
        queueAudioForPlayback(audioData);
        audioDataFound = true;
    }

    // Check serverContent format (common in Gemini Live)
    if (jsonMessage.serverContent &&
        jsonMessage.serverContent.modelTurn &&
        jsonMessage.serverContent.modelTurn.parts) {

        // Extract audio from parts
        const parts = jsonMessage.serverContent.modelTurn.parts;
        for (const part of parts) {
            // Case 1: Audio in inlineData
            if (part.inlineData && part.inlineData.mimeType &&
                (part.inlineData.mimeType.startsWith('audio/') ||
                 part.inlineData.mimeType.includes('octet-stream'))) {

                if (part.inlineData.data) {
                    const audioData = base64ToArrayBuffer(part.inlineData.data);
                    queueAudioForPlayback(audioData);
                    audioDataFound = true;
                }
            }

            // Case 2: Audio data within speech field
            if (part.speech && part.speech.audioData) {
                const audioData = base64ToArrayBuffer(part.speech.audioData);
                queueAudioForPlayback(audioData);
                audioDataFound = true;
            }

            // Case 3: Text in part
            if (part.text) {
                updateCallStatus("Staycee is responding...");
            }
        }
    }

    // Handle function calls
    if (jsonMessage.serverContent &&
        jsonMessage.serverContent.modelTurn &&
        jsonMessage.serverContent.modelTurn.parts) {

        const parts = jsonMessage.serverContent.modelTurn.parts;
        for (const part of parts) {
            if (part.functionCall) {
                handleFunctionCall(part.functionCall);
            }
        }
    }
}

// Handle function calls from Gemini
function handleFunctionCall(functionCall) {
    console.log("Received function call:", functionCall);

    switch (functionCall.name) {
        case 'end_call':
            const reason = functionCall.args?.reason || 'AI requested end';
            console.log(`AI requested to end call: ${reason}`);

            // Send a brief goodbye message before ending
            if (geminiWebSocket && geminiWebSocket.readyState === WebSocket.OPEN) {
                const goodbyeMessage = {
                    client_content: {
                        turn_complete: true,
                        turns: [{
                            role: "user",
                            parts: [{ text: "Thank you for using Guestrix! Have a great day!" }]
                        }]
                    }
                };

                try {
                    geminiWebSocket.send(JSON.stringify(goodbyeMessage));
                } catch (error) {
                    console.error("Error sending goodbye message:", error);
                }
            }

            // End the call after a brief delay to allow the goodbye message
            setTimeout(() => {
                stopVoiceCall(`Call ended by AI: ${reason}`);
            }, 2000);
            break;

        default:
            console.warn(`Unknown function call: ${functionCall.name}`);
            break;
    }
}

// Helper function to convert base64 to ArrayBuffer
function base64ToArrayBuffer(base64) {
    if (!base64 || typeof base64 !== 'string') {
        console.warn("Invalid base64 input:", typeof base64);
        return new ArrayBuffer(0);
    }

    try {
        // Clean up the base64 string first
        let cleanBase64 = base64;

        // Remove data URI prefix if present
        if (base64.includes('base64,')) {
            cleanBase64 = base64.split('base64,')[1];
        }

        // Remove any whitespace
        cleanBase64 = cleanBase64.replace(/\s/g, '');

        // Add padding if needed
        while (cleanBase64.length % 4 !== 0) {
            cleanBase64 += '=';
        }

        // Convert base64 to binary string
        const binaryString = window.atob(cleanBase64);

        // Create arraybuffer and view
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        return bytes.buffer;
    } catch (error) {
        console.error("Error converting base64 to ArrayBuffer:", error);
        return new ArrayBuffer(0);
    }
}

// Initialize voice call on page load
document.addEventListener('DOMContentLoaded', initializeVoiceCall);

// CSS for audio visualization - Add if not already in styles.css
/*
.audio-bar.active {
    animation: audio-wave 1.2s ease-in-out infinite;
}

@keyframes audio-wave {
    0%, 100% { height: 5px; }
    50% { height: 30px; }
}

.audio-bar:nth-child(1) { animation-delay: -1.2s; }
.audio-bar:nth-child(2) { animation-delay: -1.0s; }
.audio-bar:nth-child(3) { animation-delay: -0.8s; }
.audio-bar:nth-child(4) { animation-delay: -0.6s; }
.audio-bar:nth-child(5) { animation-delay: -0.4s; }
.audio-bar:nth-child(6) { animation-delay: -0.2s; }
.audio-bar:nth-child(7) { animation-delay: 0s; }
*/