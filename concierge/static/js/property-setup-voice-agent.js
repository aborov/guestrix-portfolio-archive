/*
 * Voice Agent functionality for Property Setup Wizard
 * Helps hosts complete their property knowledge base through conversational AI
 */

// Voice call utilities - updated to match guest_dashboard_voice_call.js
const GEMINI_OUTPUT_SAMPLE_RATE = 24000;  // Gemini audio is 24kHz
const GEMINI_LIVE_MODEL = "gemini-live-2.5-flash-preview"; 
const GEMINI_API_VERSION = "v1beta"; // The API version required for Live API
const GEMINI_VOICES = ["Aoede", "Chorister", "Dawnsmell", "Hearth", "Joyishness", "Jurai", "Patzelt", "Shiralish", "Orus"];
const GEMINI_DEFAULT_VOICE = "Orus";  // Default voice to use
const MAX_AUDIO_QUEUE_LENGTH = 60;  // Maximum number of chunks to keep in the audio queue (increased from 30)
const AUDIO_INITIAL_BUFFER_COUNT = 3;  // Number of chunks to buffer before playing (reduced from 5 for quicker start)

// Voice Agent Constants
const VOICE_AGENT_MODEL = "gemini-live-2.5-flash-preview"; 
const VOICE_AGENT_VOICE = "Orus"; // Friendly voice for host conversations
const MIC_BUFFER_SIZE = 4096;
const SEND_INTERVAL_MS = 100;
const TRANSCRIPTION_TIMEOUT = 3000; // Shorter timeout for more responsive chat

// Session timeout management - UPDATED with actual Gemini Live API limits
const VOICE_SESSION_TIMEOUT_MINUTES = 14; // Use 14 minutes (1 minute buffer from 15-minute limit)
const VOICE_SESSION_WARNING_SECONDS = 60; // Warn user 1 minute before timeout

// Voice Agent State
let voiceAgentState = 'idle'; // idle, starting, active, stopping
let voiceAgentWebSocket = null;
let voiceAgentMicStream = null;
let voiceAgentAudioProcessor = null;
let voiceAgentAudioContext = null;
let voiceAgentAudioQueue = [];
let voiceAgentIsPlaying = false;
let voiceAgentNextStartTime = 0;
let voiceAgentActiveSources = [];
let voiceAgentTimeouts = [];
let voiceAgentAudioBuffering = true;

// Transcription state
let voiceAgentAITranscription = "";
let voiceAgentUserTranscription = "";
let voiceAgentAITimeout = null;
let voiceAgentUserTimeout = null;

// Session management
let voiceAgentSessionId = null;
let voiceAgentProgressKey = null;
let voiceAgentKnowledgeGaps = [];
let voiceAgentCurrentQuestionIndex = 0;
let voiceAgentCollectedData = {}; // For tracking current session data
let voiceAgentCurrentSession = null; // NEW: Track current session data

// Session timeout management
let voiceSessionStartTime = null;
let voiceSessionTimeoutId = null;
let voiceSessionWarningTimeoutId = null;

// Onboarding questions categorized by type
const ONBOARDING_QUESTIONS = {
    emergency: [
        "Where is the water main shut off?",
        "Where is the water heater?", 
        "Where is the electrical panel?",
        "Is there a fire extinguisher and what brand/model?",
        "What should guests do if a pipe has burst?",
        "What should guests do if the toilet is overflowing?",
        "What should guests do if the power goes off?",
        "What should guests do if the heating/cooling stops working?",
        "What should guests do if someone is injured?",
        "What should guests do in case of broken glass?",
        "What should guests do for weather related property damage?",
        "Is there a first-aid kit? Where is it?"
    ],
    appliances: [
        "What's the brand and model of the coffeemaker?",
        "What's the brand and model of the stove?",
        "What's the brand and model of the fridge?",
        "What's the brand and model of the dishwasher?",
        "What's the brand and model of the smart lock?",
        "What's the brand and model of the whirlpool/hot tub?",
        "What's the brand and model of the gas grill?",
        "What's the brand and model of the hairdryer?",
        "What's the brand and model of the iron?",
        "What's the brand and model of the washing machine and dryer?",
        "What's the brand and model of the microwave?",
        "What's the brand and model of the toaster/toaster oven?",
        "What's the brand and model of the HVAC system?",
        "What's the brand and model of the television and entertainment systems?",
        "Are there any other appliances like split or window AC units that guests may have trouble operating?"
    ],
    basics: [
        "What time is check-in/check-out?",
        "Where do guests park?",
        "Where are the extra towels/linens?",
        "Where are extra blankets/linens/comforters?",
        "Where do guests put the trash/recycling? When is trash pickup?",
        "Do you provide toiletries/basic supplies like toilet paper, paper towels, dish soap?",
        "Where's the dishwasher detergent?",
        "Is there a grill? How do guests use it?",
        "What's the best way to get around - public transport, taxis, ride-sharing?",
        "Do you have a crib/pack-n-play or high chair available?",
        "What's the bedding configuration in each room?",
        "Is there a specific checkout procedure like strip beds, start laundry?",
        "Where are the cleaning supplies/broom/vacuum?",
        "What's the noise level like in the area?",
        "Are there sports channels on the TV?",
        "Is there a cell phone signal?",
        "Are there any stairs in the property?",
        "What is the maximum occupancy?",
        "Is there a fireplace/fire pit? How do guests use it?"
    ],
    local: [
        "What local numbers/recommendations do you want to share?",
        "Can you recommend local restaurants/cafes?",
        "What are some popular local attractions/things to do nearby?",
        "Is there a grocery store nearby?",
        "Where is the nearest pharmacy/hospital?",
        "What sort of wild animals might guests see?",
        "Can guests use the water from the taps for drinking/cooking?",
        "What's the closest gas station?"
    ],
    house_rules: [
        "Are pets allowed? What are the rules for pets?",
        "What are your house rules, especially regarding noise, parties, smoking?",
        "Are there any things guests should be careful about?"
    ]
};

// Initialize voice agent
function initializeVoiceAgent() {
    console.log("🎙️ Initializing Property Setup Voice Agent...");
    
    // Generate unique session ID for this voice session
    voiceAgentSessionId = `voice_session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    console.log(`🆔 Voice session ID: ${voiceAgentSessionId}`);
    
    // Initialize current session tracking
    voiceAgentCurrentSession = {
        sessionId: voiceAgentSessionId,
        startTime: new Date().toISOString(),
        conversations: [],
        extractedAnswers: {},
        sessionSummary: {}
    };
    
    // Get the current wizard progress key
    voiceAgentProgressKey = `wizard_progress_${window.CURRENT_USER_ID}_${Date.now()}`;
    
    // Set up event listeners for voice agent controls
    setupVoiceAgentControls();
    
    // Ensure window.voiceAgent is available immediately
    window.voiceAgent = {
        initializeVoiceAgent,
        handleVoiceChatStart,
        stopVoiceAgent,
        voiceAgentState,
        createVoiceAgentSystemPrompt,
        analyzeKnowledgeGaps,
        ONBOARDING_QUESTIONS
    };
    
    console.log("✅ Voice Agent initialized and exposed to window");
}

// Set up voice agent UI controls
function setupVoiceAgentControls() {
    // Add event listener to the voice chat button in step 6
    const voiceChatButton = document.getElementById('start-voice-chat');
    if (voiceChatButton) {
        // Remove any existing event listeners to prevent duplicates
        voiceChatButton.removeEventListener('click', handleVoiceChatStart);
        voiceChatButton.addEventListener('click', handleVoiceChatStart);
        console.log("✅ Voice chat button bound successfully");
    } else {
        console.warn("⚠️ Voice chat button not found");
    }
}

// Handle voice chat start
async function handleVoiceChatStart() {
    console.log("🎙️ Starting voice chat for property setup...");
    
    // Prevent multiple simultaneous calls
    if (voiceAgentState === 'starting') {
        console.log("⚠️ Voice agent already starting, skipping...");
        return;
    }
    
    if (voiceAgentState === 'idle') {
        try {
            voiceAgentState = 'starting';
            updateVoiceChatButton(true, true, "Connecting...");
            
            // CRITICAL: Always fetch fresh wizard data from Firestore before starting
            console.log("🔄 Fetching fresh wizard data from Firestore...");
            const freshWizardData = await loadFreshWizardData();
            
            if (!freshWizardData) {
                throw new Error("No wizard data found. Please complete the previous steps first.");
            }
            
            console.log(`📊 Loaded fresh wizard data with ${Object.keys(freshWizardData).length} sections`);
            
            // Analyze data gaps with fresh data
            voiceAgentKnowledgeGaps = analyzeKnowledgeGaps(freshWizardData);
            console.log(`📋 Knowledge gaps identified: (${voiceAgentKnowledgeGaps.length})`, voiceAgentKnowledgeGaps);
            
            // Get authentication token
            const authToken = await fetchAuthToken();
            
            // Start the voice agent session with fresh data
            await startVoiceAgentSession(authToken, freshWizardData);
            
        } catch (error) {
            console.error("❌ Error starting voice chat:", error);
            voiceAgentState = 'idle';
            updateVoiceChatButton(false, false, "Start Voice Chat");
            displayVoiceMessage("Error starting voice chat: " + error.message, 'ai');
        }
    } else if (voiceAgentState === 'active') {
        // End the current session
        stopVoiceAgent("User ended session");
    }
}

// NEW: Load fresh wizard data specifically from Firestore
async function loadFreshWizardData() {
    try {
        console.log("📡 Loading fresh wizard data from Firestore...");
        
        const response = await fetch('/setup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'load_progress' })
        });
        
        if (response.ok) {
            const result = await response.json();
            const freshData = result.data || {};
            
            console.log(`✅ Fresh data loaded with ${Object.keys(freshData).length} sections`);
            
            // Log voice session summary for debugging
            if (freshData.voice_sessions) {
                console.log(`🎙️ Found ${freshData.voice_sessions.length} previous voice sessions:`);
                freshData.voice_sessions.forEach((session, index) => {
                    console.log(`  Session ${index + 1}: ${session.sessionId} - ${session.answersExtracted || 0} answers, ${session.totalConversations || 0} conversations`);
                });
            }
            
            // Update main wizard instance with fresh data
            if (window.wizardInstance) {
                window.wizardInstance.wizardData = freshData;
                console.log("🔄 Updated main wizard instance with fresh data");
            }
            
            return freshData;
        } else {
            console.error("❌ Failed to load fresh wizard data:", response.status);
            return null;
        }
        
    } catch (error) {
        console.error("❌ Error loading fresh wizard data:", error);
        return null;
    }
}

// Analyze knowledge gaps in wizard data - ENHANCED for voice sessions
function analyzeKnowledgeGaps(wizardData) {
    const gaps = [];
    
    // ENHANCED: Process voice sessions and extracted answers
    const voiceSessions = wizardData.voice_sessions || [];
    const previouslyAskedTopics = new Set();
    const collectedAnswers = new Map();
    
    console.log(`🔍 Analyzing ${voiceSessions.length} voice sessions for knowledge gaps`);
    
    // Process voice sessions and extracted answers
    voiceSessions.forEach((session, sessionIndex) => {
        console.log(`🎙️ Processing session ${sessionIndex + 1}: ${session.sessionId}`);
        
        if (session.extractedAnswers) {
            Object.keys(session.extractedAnswers).forEach(topic => {
                const answer = session.extractedAnswers[topic];
                previouslyAskedTopics.add(topic);
                collectedAnswers.set(`${topic}_${session.sessionId}`, {
                    ...answer,
                    sessionId: session.sessionId,
                    sessionIndex: sessionIndex + 1
                });
                
                console.log(`  ✅ Found ${topic} answer: ${JSON.stringify(answer).substring(0, 100)}...`);
            });
        }
    });
    
    // BACKWARD COMPATIBILITY: Also check old clarifiedResponses format
    const clarifiedResponses = wizardData.clarifiedResponses || [];
    clarifiedResponses.forEach(clarification => {
        const topic = clarification.topic;
        previouslyAskedTopics.add(topic);
        collectedAnswers.set(`clarified_${topic}`, {
            text: clarification.clarified,
            topic: topic,
            timestamp: clarification.timestamp,
            source: 'clarified_legacy'
        });
        console.log(`  📋 Found legacy clarified response for ${topic}`);
    });
    
    // Check existing data fields for completeness
    if (wizardData.parkingInfo && wizardData.parkingInfo.length > 0) {
        previouslyAskedTopics.add('parking');
        console.log(`✅ Found ${wizardData.parkingInfo.length} parking instructions`);
    }
    
    if (wizardData.emergencyDetails && wizardData.emergencyDetails.length > 0) {
        previouslyAskedTopics.add('emergency');
        console.log(`✅ Found ${wizardData.emergencyDetails.length} emergency details`);
    }
    
    if (wizardData.basicInfo?.wifiNetwork && wizardData.basicInfo?.wifiPassword) {
        previouslyAskedTopics.add('wifi');
        console.log(`✅ Found WiFi information`);
    }
    
    console.log(`📊 Topics covered: ${Array.from(previouslyAskedTopics).join(', ')}`);
    console.log(`📋 Total collected answers: ${collectedAnswers.size} items`);
    
    // Only add gaps for topics that haven't been covered
    
    // WiFi information - HIGH PRIORITY if missing
    if (!previouslyAskedTopics.has('wifi')) {
        const wifiNetwork = wizardData.basicInfo?.wifi_network || wizardData.basicInfo?.wifiNetwork;
        const wifiPassword = wizardData.basicInfo?.wifi_password || wizardData.basicInfo?.wifiPassword;
        
        if (!wifiNetwork || !wifiPassword) {
            gaps.push({
                category: 'WiFi Information', 
                questions: ["What's the WiFi network name and password for guests?"],
                priority: 'high',
                reason: 'WiFi information is missing and essential for guests'
            });
        }
    }
    
    // Parking information - HIGH PRIORITY if missing
    if (!previouslyAskedTopics.has('parking')) {
        gaps.push({
            category: 'Parking Instructions',
            questions: ["Where should guests park? Are there any parking restrictions or special instructions?"],
            priority: 'high',
            reason: 'Parking information is essential for guest arrival'
        });
    }
    
    // Emergency information - HIGH PRIORITY if minimal
    if (!previouslyAskedTopics.has('emergency') || collectedAnswers.size < 2) {
        const emergencyGaps = [];
        const existingEmergencies = wizardData.emergencies?.scenarios || [];
        const existingEmergencyTexts = existingEmergencies.map(e => e.scenario?.toLowerCase() || '').join(' ');
        
        const priorityEmergencyQuestions = [
            "Where is the fire extinguisher located?",
            "Where is the water main shut off?",
            "Where is the electrical panel?",
            "Is there a first-aid kit? Where is it?"
        ];
        
        priorityEmergencyQuestions.forEach(question => {
            const keywords = question.toLowerCase().split(' ').slice(2, 4); // Get key words
            const isAlreadyCovered = keywords.some(keyword => 
                existingEmergencyTexts.includes(keyword) || 
                Array.from(collectedAnswers.values()).some(answer => 
                    answer.text && answer.text.toLowerCase().includes(keyword)
                )
            );
            
            if (!isAlreadyCovered) {
                emergencyGaps.push(question);
            }
        });
        
        if (emergencyGaps.length > 0) {
            gaps.push({
                category: 'Emergency Information',
                questions: emergencyGaps.slice(0, 2), // Limit to 2 most important
                priority: 'high',
                reason: `Missing ${emergencyGaps.length} essential emergency details`
            });
        }
    }
    
    // Appliance information - MEDIUM PRIORITY
    if (!previouslyAskedTopics.has('appliances') || collectedAnswers.size < 3) {
        const existingFacts = wizardData.propertyFacts?.extractedText || '';
        const manualEntries = wizardData.manualEntry?.rooms || [];
        
        const priorityAppliances = ['coffeemaker', 'dishwasher', 'washing machine'];
        const applianceGaps = [];
        
        priorityAppliances.forEach(appliance => {
            const isInFacts = existingFacts.toLowerCase().includes(appliance.toLowerCase());
            const isInManual = manualEntries.some(room => 
                room.amenities?.some(amenity => 
                    amenity.toLowerCase().includes(appliance.toLowerCase())
                )
            );
            const isInVoiceData = Array.from(collectedAnswers.values()).some(answer => 
                JSON.stringify(answer).toLowerCase().includes(appliance.toLowerCase())
            );
            
            if (!isInFacts && !isInManual && !isInVoiceData) {
                const question = ONBOARDING_QUESTIONS.appliances.find(q => 
                    q.toLowerCase().includes(appliance)
                );
                if (question) applianceGaps.push(question);
            }
        });
        
        if (applianceGaps.length > 0) {
            gaps.push({
                category: 'Appliance Information',
                questions: applianceGaps.slice(0, 2), // Limit to 2 most important
                priority: 'medium',
                reason: `Missing ${applianceGaps.length} common appliance details`
            });
        }
    }
    
    // Sort by priority
    gaps.sort((a, b) => {
        const priorityOrder = { 'high': 0, 'medium': 1, 'low': 2 };
        return priorityOrder[a.priority] - priorityOrder[b.priority];
    });
    
    console.log(`🎯 Final knowledge gaps: ${gaps.length} categories, ${gaps.reduce((sum, gap) => sum + gap.questions.length, 0)} total questions`);
    
    return gaps;
}

// Start voice agent session
async function startVoiceAgentSession(authToken, wizardData) {
    console.log("🎙️ Starting voice agent session...");
    
    try {
        // Request microphone access
        voiceAgentMicStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log("🎤 Microphone access granted");
        
        // Set up audio context for microphone input
        voiceAgentAudioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 16000,  // Use 16kHz for input to match Gemini's expected input format
            latencyHint: 'interactive'
        });
        
        const micSource = voiceAgentAudioContext.createMediaStreamSource(voiceAgentMicStream);
        voiceAgentAudioProcessor = voiceAgentAudioContext.createScriptProcessor(MIC_BUFFER_SIZE, 1, 1);
        micSource.connect(voiceAgentAudioProcessor);
        voiceAgentAudioProcessor.connect(voiceAgentAudioContext.destination);
        
        // Set up WebSocket connection
        const wsUrl = `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=${authToken}&alt=json`;
        console.log("🔌 Connecting to Gemini Live API...");
        
        voiceAgentWebSocket = new WebSocket(wsUrl);
        
        // Handle WebSocket events
        setupVoiceAgentWebSocket(wizardData);
        
        // Handle audio processing
        setupVoiceAgentAudioProcessing();
        
    } catch (error) {
        console.error("❌ Error setting up voice agent session:", error);
        throw error;
    }
}

// Set up WebSocket event handlers
function setupVoiceAgentWebSocket(wizardData) {
    voiceAgentWebSocket.onopen = () => {
        console.log("✅ Voice Agent WebSocket connected");
        
        // Send initial configuration
        const config = {
            setup: {
                model: `models/${VOICE_AGENT_MODEL}`,
                generationConfig: {
                    responseModalities: ["AUDIO"],
                    speechConfig: {
                        voiceConfig: {
                            prebuiltVoiceConfig: {
                                voiceName: VOICE_AGENT_VOICE
                            }
                        },
                        languageCode: "en-US"
                    }
                },
                systemInstruction: {
                    parts: [{ text: createVoiceAgentSystemPrompt(wizardData) }]
                },
                // Add transcription configurations (top-level, not under generationConfig)
                output_audio_transcription: {},
                input_audio_transcription: {},
                // Optimized configuration for realtime input based on Gemini Live API defaults
                realtimeInputConfig: {
                    // Configure voice activity detection with better sensitivity for property interviews
                    automaticActivityDetection: {
                        disabled: false, // Enable automatic activity detection
                        startOfSpeechSensitivity: "START_SENSITIVITY_HIGH", // Detect speech start more quickly
                        endOfSpeechSensitivity: "END_SENSITIVITY_LOW", // Don't end speech detection too quickly
                        prefixPaddingMs: 50, // Lower value for faster speech detection
                        silenceDurationMs: 500 // Shorter silence duration for more responsive interruptions
                    },
                    // Enable smooth interruptions - this is key for proper barge-in
                    activityHandling: "START_OF_ACTIVITY_INTERRUPTS", // This enables barge-in functionality
                    // Include all input in the user's turn
                    turnCoverage: "TURN_INCLUDES_ALL_INPUT"
                }
            }
        };
        
        voiceAgentWebSocket.send(JSON.stringify(config));
        
        // Update UI state
        voiceAgentState = 'active';
        updateVoiceChatButton(true, false, "End Voice Chat");
        displayVoiceMessage("Voice chat connected! I'll help you complete your property information. Let's start with a few questions.", 'ai');
        
        // Start session timeout management
        startVoiceSessionTimeout();
        
        // Send initial greeting as a system instruction to start the conversation
        setTimeout(() => {
            if (voiceAgentWebSocket && voiceAgentWebSocket.readyState === WebSocket.OPEN) {
                const greeting = createInitialGreeting(wizardData);
                const initialMessage = {
                    client_content: {
                        turn_complete: true,
                        turns: [{
                            role: "user",
                            parts: [{ text: "Hi! I'm ready to start the property information conversation. Please introduce yourself as Leo and explain how this interview will work." }]
                        }]
                    }
                };
                voiceAgentWebSocket.send(JSON.stringify(initialMessage));
            }
        }, 1000);
    };
    
    voiceAgentWebSocket.onmessage = (event) => {
        handleVoiceAgentMessage(event);
    };
    
    voiceAgentWebSocket.onerror = (error) => {
        console.error("❌ Voice Agent WebSocket error:", error);
        stopVoiceAgent("Connection error");
    };
    
    voiceAgentWebSocket.onclose = (event) => {
        console.log("🔌 Voice Agent WebSocket closed:", event.code, event.reason);
        if (voiceAgentState === 'active') {
            stopVoiceAgent("Connection closed");
        }
    };
}

// Set up audio processing
function setupVoiceAgentAudioProcessing() {
    let audioChunks = [];
    let lastSendTime = 0;
    
    voiceAgentAudioProcessor.onaudioprocess = (e) => {
        if (voiceAgentWebSocket && voiceAgentWebSocket.readyState === WebSocket.OPEN && voiceAgentState === 'active') {
            const inputData = e.inputBuffer.getChannelData(0);
            
            // Convert to 16-bit PCM
            const pcmData = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
                pcmData[i] = Math.max(-1, Math.min(1, inputData[i])) * 0x7FFF;
            }
            
            audioChunks.push(pcmData.buffer);
            
            // Send audio periodically
            const now = Date.now();
            if (now - lastSendTime >= SEND_INTERVAL_MS) {
                const combinedLength = audioChunks.reduce((acc, chunk) => acc + chunk.byteLength, 0);
                if (combinedLength > 0) {
                    const combinedBuffer = new Uint8Array(combinedLength);
                    let offset = 0;
                    for (const chunk of audioChunks) {
                        combinedBuffer.set(new Uint8Array(chunk), offset);
                        offset += chunk.byteLength;
                    }
                    
                    const base64Audio = arrayBufferToBase64(combinedBuffer.buffer);
                    const message = {
                        realtime_input: {
                            media_chunks: [{
                                data: base64Audio,
                                mime_type: "audio/pcm;rate=16000"  // Specify sample rate for proper processing
                            }]
                        }
                    };
                    
                    try {
                        voiceAgentWebSocket.send(JSON.stringify(message));
                        audioChunks = [];
                        lastSendTime = now;
                    } catch (err) {
                        console.error("❌ Error sending audio:", err);
                    }
                }
            }
        }
    };
}

// Handle incoming WebSocket messages
function handleVoiceAgentMessage(event) {
    try {
        if (typeof event.data === 'string') {
            const jsonMessage = JSON.parse(event.data);
            
            // Handle interruption with proper audio cleanup - KEY FIX
            if (jsonMessage.serverContent && jsonMessage.serverContent.interrupted === true) {
                console.log("🚫 User interrupted - clearing audio queue immediately");
                stopVoiceAgentAudio(); // Stop all current audio playback
                
                // Clear any pending transcription timeouts to avoid stale transcriptions
                if (voiceAgentAITimeout) {
                    clearTimeout(voiceAgentAITimeout);
                    voiceAgentAITimeout = null;
                    voiceAgentAITranscription = ""; // Clear partial transcription
                }
                
                return; // Don't process any other content in this message
            }
            
            // Process transcriptions
            processVoiceAgentTranscriptions(jsonMessage);
            
            // Process audio content
            processVoiceAgentAudio(jsonMessage);
            
        } else if (event.data instanceof Blob) {
            event.data.arrayBuffer().then(arrayBuffer => {
                // Try to decode as text first
                const decoder = new TextDecoder('utf-8');
                try {
                    const text = decoder.decode(arrayBuffer);
                    if (text.trim().startsWith('{')) {
                        const jsonMessage = JSON.parse(text);
                        
                        // Check for interruption in blob data too
                        if (jsonMessage.serverContent && jsonMessage.serverContent.interrupted === true) {
                            console.log("🚫 User interrupted (blob data) - clearing audio");
                            stopVoiceAgentAudio();
                            return;
                        }
                        
                        processVoiceAgentTranscriptions(jsonMessage);
                        processVoiceAgentAudio(jsonMessage);
                        return;
                    }
                } catch (e) {
                    // Not text, process as audio
                }
                
                if (arrayBuffer.byteLength > 0) {
                    queueVoiceAgentAudio(arrayBuffer);
                }
            });
        }
    } catch (error) {
        console.error("❌ Error handling voice agent message:", error);
    }
}

// Process transcriptions from voice agent
function processVoiceAgentTranscriptions(jsonMessage) {
    // Handle AI transcriptions
    if (jsonMessage.serverContent && jsonMessage.serverContent.outputTranscription) {
        handleVoiceAgentTranscriptionFragment(jsonMessage.serverContent.outputTranscription.text, 'ai');
    } else if (jsonMessage.outputTranscription) {
        handleVoiceAgentTranscriptionFragment(jsonMessage.outputTranscription.text, 'ai');
    }
    
    // Handle user transcriptions
    if (jsonMessage.serverContent && jsonMessage.serverContent.inputTranscription) {
        handleVoiceAgentTranscriptionFragment(jsonMessage.serverContent.inputTranscription.text, 'user');
    } else if (jsonMessage.inputTranscription) {
        handleVoiceAgentTranscriptionFragment(jsonMessage.inputTranscription.text, 'user');
    }
}

// Handle transcription fragments
function handleVoiceAgentTranscriptionFragment(fragment, type) {
    if (!fragment || typeof fragment !== 'string') return;
    
    if (type === 'ai') {
        voiceAgentAITranscription += fragment;
        
        if (voiceAgentAITimeout) {
            clearTimeout(voiceAgentAITimeout);
        }
        
        voiceAgentAITimeout = setTimeout(() => {
            if (voiceAgentAITranscription.trim()) {
                handleCompleteVoiceAgentTranscription('ai', voiceAgentAITranscription.trim());
                voiceAgentAITranscription = "";
            }
        }, TRANSCRIPTION_TIMEOUT);
        
    } else if (type === 'user') {
        voiceAgentUserTranscription += fragment;
        
        if (voiceAgentUserTimeout) {
            clearTimeout(voiceAgentUserTimeout);
        }
        
        voiceAgentUserTimeout = setTimeout(() => {
            if (voiceAgentUserTranscription.trim()) {
                handleCompleteVoiceAgentTranscription('user', voiceAgentUserTranscription.trim());
                voiceAgentUserTranscription = "";
            }
        }, TRANSCRIPTION_TIMEOUT);
    }
}

// Handle complete transcriptions
async function handleCompleteVoiceAgentTranscription(role, text) {
    console.log(`📝 ${role === 'user' ? 'Host' : 'Agent'}:`, text);
    
    // Display in chat
    displayVoiceMessage(text, role);
    
    // ENHANCED: Store all conversations in current session
    const conversationEntry = {
        role: role,
        text: text,
        timestamp: new Date().toISOString(),
        sessionId: voiceAgentSessionId
    };
    
    voiceAgentCurrentSession.conversations.push(conversationEntry);
    
    // Process based on role
    if (role === 'user') {
        // Store user response for context
        voiceAgentCollectedData.lastUserResponse = conversationEntry;
        console.log("👤 Stored user response for processing");
        
    } else if (role === 'ai') {
        // CRITICAL: Look for AI responses that contain structured information
        await processAIResponseForStructuredData(text, conversationEntry);
    }
}

// NEW: Enhanced AI response processing for structured data extraction
async function processAIResponseForStructuredData(responseText, conversationEntry) {
    try {
        const textLower = responseText.toLowerCase();
        
        // Look for confirmation/clarification patterns with better extraction
        const structuredData = extractStructuredInformation(responseText, textLower);
        
        if (structuredData) {
            console.log("✅ Extracted structured data from AI response:", structuredData);
            
            // Store in current session
            voiceAgentCurrentSession.extractedAnswers[structuredData.topic] = {
                ...structuredData,
                conversationContext: {
                    userInput: voiceAgentCollectedData.lastUserResponse?.text || '',
                    aiResponse: responseText,
                    timestamp: conversationEntry.timestamp,
                    sessionId: voiceAgentSessionId
                }
            };
            
            // Save to Firestore immediately
            await saveSessionDataToFirestore();
        }
        
    } catch (error) {
        console.error("❌ Error processing AI response for structured data:", error);
    }
}

// FIXED: Enhanced structured information extraction with better patterns and validation
function extractStructuredInformation(responseText, textLower) {
    let structuredData = null;
    
    // CRITICAL: Validate this is actually a confirmation/clarification response
    const isConfirmationResponse = 
        textLower.includes('let me confirm') ||
        textLower.includes('let me repeat') ||
        textLower.includes('so to confirm') ||
        textLower.includes('got it') ||
        textLower.includes('okay, so') ||
        textLower.includes('perfect') ||
        textLower.includes('to clarify');
    
    // Skip extraction if this is generic AI intro/transition text
    const isGenericAIText = 
        textLower.includes('hi there') ||
        textLower.includes("i'm leo") ||
        textLower.includes('help you') ||
        textLower.includes('let\'s talk about') ||
        textLower.includes('moving on') ||
        textLower.includes('that sounds') ||
        (textLower.includes('will help') && textLower.includes('guests')) ||
        responseText.length < 20; // Too short to be meaningful data
    
    if (isGenericAIText && !isConfirmationResponse) {
        console.log(`🚫 Skipping generic AI text: "${responseText.substring(0, 50)}..."`);
        return null;
    }
    
    // WiFi Information Pattern - FIXED with better parsing
    const wifiPatterns = [
        // Pattern for: "network is 'welcome home 123' and password is '321 neighborhood 123!'"
        /(?:network|wifi).*?(?:is|called)\s*['"]([^'"]+)['"].*?password.*?(?:is)\s*['"]([^'"]+)['"]?/i,
        // Pattern for: "network is welcome home 123 and the password is 321 neighborhood 123"
        /(?:network|wifi).*?(?:is|called)\s+([a-zA-Z0-9][a-zA-Z0-9\s]{2,25}?)(?:\s+and).*?password.*?(?:is)\s+([a-zA-Z0-9!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?][a-zA-Z0-9\s!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]*)/i,
        // Pattern for quoted strings: "wifi network 'name' password 'pass'"
        /wifi.*?['"]([^'"]+)['"].*?password.*?['"]([^'"]+)['"]?/i
    ];
    
    for (const pattern of wifiPatterns) {
        const match = responseText.match(pattern);
        if (match && match[1] && match[2]) {
            const networkName = match[1].trim();
            const password = match[2].trim();
            
            // Validate extracted data quality
            if (networkName.length >= 3 && password.length >= 3 && 
                !networkName.includes('help') && !password.includes('help')) {
                structuredData = {
                    topic: 'wifi',
                    networkName: networkName,
                    password: password,
                    fullResponse: responseText,
                    extractionMethod: 'ai_confirmation',
                    quality: 'high'
                };
                console.log(`✅ WiFi extracted: Network="${networkName}", Password="${password}"`);
                break;
            }
        }
    }
    
    // Parking Information Pattern - FIXED with complete instruction capture
    if (!structuredData && isConfirmationResponse && (textLower.includes('park') || textLower.includes('street'))) {
        const parkingPatterns = [
            // Capture complete parking instructions including restrictions
            /(?:park|parking).*?(?:on|in|at)\s+([^.!?]*?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|street|driveway|garage)[^.!?]*?)(?:\.|!|\?|$)/i,
            // Capture street parking with time restrictions
            /(?:street|park).*?((?:avoid|can't|don't|except|but)[^.!?]*?(?:monday|tuesday|wednesday|thursday|friday)[^.!?]*?)(?:\.|!|\?|$)/i,
            // General parking instruction
            /(?:guests can park|parking.*?available)\s+([^.!?]{10,})(?:\.|!|\?|$)/i
        ];
        
        for (const pattern of parkingPatterns) {
            const match = responseText.match(pattern);
            if (match && match[1] && match[1].trim().length > 15) {
                const instruction = match[1].trim();
                
                // Validate it's not generic text
                if (!instruction.includes('help guests') && !instruction.includes('will be')) {
                    structuredData = {
                        topic: 'parking',
                        instruction: instruction,
                        fullResponse: responseText,
                        extractionMethod: 'ai_confirmation',
                        quality: instruction.length > 30 ? 'high' : 'medium'
                    };
                    console.log(`✅ Parking extracted: "${instruction}"`);
                    break;
                }
            }
        }
    }
    
    // Emergency Information Pattern - FIXED to capture actual safety details
    if (!structuredData && isConfirmationResponse && 
        (textLower.includes('fire extinguisher') || textLower.includes('emergency exits') || 
         textLower.includes('first aid') || textLower.includes('safety'))) {
        
        const emergencyPatterns = [
            // Fire extinguisher location
            /fire extinguisher.*?(?:is|located|in|at|outside)\s+([^.!?]+?)(?:\.|!|\?|$)/i,
            // Emergency exits
            /emergency exits?.*?(?:are|is)\s+([^.!?]+?)(?:\.|!|\?|$)/i,
            // General emergency location info
            /(?:exits?|extinguisher|first aid).*?(?:in|at|outside|near)\s+([^.!?]+?)(?:\.|!|\?|$)/i,
            // Front/back door references
            /(?:front|back).*?door.*?(?:and|or)\s+([^.!?]+?)(?:\.|!|\?|$)/i
        ];
        
        for (const pattern of emergencyPatterns) {
            const match = responseText.match(pattern);
            if (match && match[1] && match[1].trim().length > 5) {
                const detail = match[1].trim();
                
                // Validate it's actual location/safety info
                if (!detail.includes('help') && !detail.includes('guest') && 
                    (detail.includes('door') || detail.includes('hallway') || 
                     detail.includes('outside') || detail.includes('kitchen') ||
                     detail.includes('front') || detail.includes('back'))) {
                    
                    structuredData = {
                        topic: 'emergency',
                        detail: detail,
                        fullResponse: responseText,
                        extractionMethod: 'ai_confirmation',
                        quality: 'high'
                    };
                    console.log(`✅ Emergency extracted: "${detail}"`);
                    break;
                }
            }
        }
    }
    
    // Appliance Information Pattern - FIXED to capture actual brand/model info
    if (!structuredData && isConfirmationResponse && 
        (textLower.includes('brand') || textLower.includes('model') || textLower.includes('general electric'))) {
        
        const appliancePatterns = [
            // Brand and model together: "General Electric GE Profile"
            /(?:brand|model).*?(?:is|are)\s+([A-Z][a-zA-Z\s]{2,20}(?:GE|General Electric|Whirlpool|Samsung|LG|Maytag|KitchenAid)[a-zA-Z0-9\s]*)/i,
            // Just brand: "all General Electric brands"
            /(?:all|the)?\s*([A-Z][a-zA-Z\s]{2,15})\s+brands?/i,
            // Model numbers: "model ABC123"
            /model\s+([A-Z0-9\-]{3,15})/i
        ];
        
        for (const pattern of appliancePatterns) {
            const match = responseText.match(pattern);
            if (match && match[1] && match[1].trim().length > 2) {
                const brandModel = match[1].trim();
                
                // Validate it's actually appliance info
                if (!brandModel.includes('help') && !brandModel.includes('good') && 
                    !brandModel.includes('start') && brandModel.length > 3) {
                    
                    structuredData = {
                        topic: 'appliances',
                        brandModel: brandModel,
                        fullResponse: responseText,
                        extractionMethod: 'ai_confirmation',
                        quality: brandModel.length > 10 ? 'high' : 'medium'
                    };
                    console.log(`✅ Appliance extracted: "${brandModel}"`);
                    break;
                }
            }
        }
    }
    
    return structuredData;
}

// NEW: Save session data to Firestore with proper structure
async function saveSessionDataToFirestore() {
    try {
        // CRITICAL: Always fetch fresh data from Firestore first
        console.log("🔄 Fetching fresh wizard data from Firestore before saving...");
        
        const response = await fetch('/setup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'load_progress' })
        });
        
        let currentData = {};
        if (response.ok) {
            const result = await response.json();
            currentData = result.data || {};
        }
        
        // Initialize voice sessions array structure
        if (!currentData.voice_sessions) {
            currentData.voice_sessions = [];
        }
        
        // Check if current session already exists, if so update it
        const existingSessionIndex = currentData.voice_sessions.findIndex(
            session => session.sessionId === voiceAgentSessionId
        );
        
        const sessionData = {
            sessionId: voiceAgentSessionId,
            startTime: voiceAgentCurrentSession.startTime,
            lastUpdated: new Date().toISOString(),
            conversations: voiceAgentCurrentSession.conversations,
            extractedAnswers: voiceAgentCurrentSession.extractedAnswers,
            status: 'active',
            totalConversations: voiceAgentCurrentSession.conversations.length,
            answersExtracted: Object.keys(voiceAgentCurrentSession.extractedAnswers).length
        };
        
        if (existingSessionIndex >= 0) {
            // Update existing session
            currentData.voice_sessions[existingSessionIndex] = sessionData;
            console.log(`🔄 Updated existing session ${voiceAgentSessionId}`);
        } else {
            // Add new session
            currentData.voice_sessions.push(sessionData);
            console.log(`✨ Added new session ${voiceAgentSessionId}`);
        }
        
        // ENHANCED: Update structured fields for easier access with correct field names
        Object.keys(voiceAgentCurrentSession.extractedAnswers).forEach(topic => {
            const answer = voiceAgentCurrentSession.extractedAnswers[topic];
            
            switch (topic) {
                case 'wifi':
                    // FIXED: Use correct field names that match wizard structure
                    if (!currentData.basic_info) currentData.basic_info = {};
                    currentData.basic_info.wifi_network = answer.networkName;
                    currentData.basic_info.wifi_password = answer.password;

                    // Also support legacy field names for compatibility
                    currentData.basic_info.wifiNetwork = answer.networkName;
                    currentData.basic_info.wifiPassword = answer.password;

                    // UNIFIED: Map to consistent property schema field name
                    if (!currentData.basic_info.wifiDetails) currentData.basic_info.wifiDetails = {};
                    currentData.basic_info.wifiDetails.network = answer.networkName;
                    currentData.basic_info.wifiDetails.password = answer.password;

                    console.log(`🔗 Integrated WiFi into basic_info: ${answer.networkName} / ${answer.password}`);
                    break;
                    
                case 'parking':
                    if (!currentData.parkingInfo) currentData.parkingInfo = [];
                    const parkingEntry = {
                        instruction: answer.instruction,
                        source: 'voice_session',
                        sessionId: voiceAgentSessionId,
                        timestamp: answer.conversationContext?.timestamp || new Date().toISOString(),
                        quality: answer.quality || 'medium'
                    };
                    currentData.parkingInfo.push(parkingEntry);
                    console.log(`🔗 Integrated parking info: ${answer.instruction.substring(0, 50)}...`);
                    break;
                    
                case 'emergency':
                    if (!currentData.emergencyDetails) currentData.emergencyDetails = [];
                    const emergencyEntry = {
                        detail: answer.detail,
                        source: 'voice_session',
                        sessionId: voiceAgentSessionId,
                        timestamp: answer.conversationContext?.timestamp || new Date().toISOString(),
                        quality: answer.quality || 'medium'
                    };
                    currentData.emergencyDetails.push(emergencyEntry);
                    console.log(`🔗 Integrated emergency info: ${answer.detail.substring(0, 50)}...`);
                    break;
                    
                case 'appliances':
                    if (!currentData.applianceInfo) currentData.applianceInfo = [];
                    const applianceEntry = {
                        brandModel: answer.brandModel,
                        type: 'general',
                        source: 'voice_session',
                        sessionId: voiceAgentSessionId,
                        timestamp: answer.conversationContext?.timestamp || new Date().toISOString(),
                        quality: answer.quality || 'medium'
                    };
                    currentData.applianceInfo.push(applianceEntry);
                    console.log(`🔗 Integrated appliance info: ${answer.brandModel}`);
                    break;
            }
        });
        
        console.log(`💾 Saving session data: ${Object.keys(voiceAgentCurrentSession.extractedAnswers).length} answers extracted`);
        
        // Save to Firestore
        const currentStep = window.wizardInstance ? window.wizardInstance.currentStep : 6;
        const saveResponse = await fetch('/setup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'save_progress',
                step: currentStep,
                data: currentData
            })
        });
        
        if (saveResponse.ok) {
            console.log("✅ Session data saved to Firestore successfully");
            
            // Update main wizard instance
            if (window.wizardInstance) {
                window.wizardInstance.wizardData = currentData;
                console.log("🔄 Updated main wizard instance with session data");
            }
            
            return true;
        } else {
            console.error("❌ Failed to save session data to Firestore");
            return false;
        }
        
    } catch (error) {
        console.error("❌ Error saving session data:", error);
        return false;
    }
}

// Process audio content from voice agent
function processVoiceAgentAudio(jsonMessage) {
    // Extract audio from various possible locations in the message
    let audioFound = false;
    
    if (jsonMessage.serverContent && jsonMessage.serverContent.modelTurn && jsonMessage.serverContent.modelTurn.parts) {
        for (const part of jsonMessage.serverContent.modelTurn.parts) {
            if (part.inlineData && part.inlineData.mimeType && part.inlineData.mimeType.startsWith('audio/')) {
                if (part.inlineData.data) {
                    const audioData = base64ToArrayBuffer(part.inlineData.data);
                    queueVoiceAgentAudio(audioData);
                    audioFound = true;
                }
            }
        }
    }
    
    return audioFound;
}

// Queue audio for playback
function queueVoiceAgentAudio(audioBuffer) {
    // Don't queue audio if call is not active
    if (voiceAgentState !== 'active') {
        console.log("🚫 Ignoring audio - call not active");
        return;
    }

    if (!audioBuffer || audioBuffer.byteLength === 0) {
        console.warn("Received empty audio buffer, not queueing for playback");
        return;
    }

    // Sample count for diagnostics
    const sampleCount = Math.floor(audioBuffer.byteLength / 2);
    // Only log queueing occasionally to reduce console noise
    if (Math.random() < 0.1) {
        console.log(`Queueing audio for playback (${audioBuffer.byteLength} bytes, ~${sampleCount} samples, ~${(sampleCount/GEMINI_OUTPUT_SAMPLE_RATE).toFixed(2)}s duration)`);
    }

    // Quick validation of audio data
    if (audioBuffer.byteLength < 256) {
        console.log(`Ignoring small ArrayBuffer (${audioBuffer.byteLength} bytes) - likely not audio.`);
        return;
    }

    // Create audio context if needed
    if (!window.voiceAgentPlaybackContext) {
        try {
            window.voiceAgentPlaybackContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: GEMINI_OUTPUT_SAMPLE_RATE,
                latencyHint: 'interactive'
            });
            console.log(`Created audio context with sample rate: ${GEMINI_OUTPUT_SAMPLE_RATE}Hz`);
        } catch (error) {
            console.error("Failed to create audio context:", error);
            return;
        }
    }

    // Ensure context is running
    if (window.voiceAgentPlaybackContext && window.voiceAgentPlaybackContext.state === 'suspended') {
        window.voiceAgentPlaybackContext.resume().catch(error => {
            console.error("Error resuming audio context:", error);
        });
    }

    // Add to queue and track if queue was empty
    const wasQueueEmpty = voiceAgentAudioQueue.length === 0;
    voiceAgentAudioQueue.push(audioBuffer);
    
    // Limit queue size to prevent memory issues
    if (voiceAgentAudioQueue.length > MAX_AUDIO_QUEUE_LENGTH) {
        voiceAgentAudioQueue.shift();
        console.warn("Audio queue overflow, dropping oldest chunk");
    }

    // Start playback if we're not already playing
    if (wasQueueEmpty && !voiceAgentIsPlaying) {
        startVoiceAgentContinuousPlayback();
    }
}

// Start continuous audio playback
function startVoiceAgentContinuousPlayback() {
    // Check if we have audio to play
    if (voiceAgentAudioQueue.length === 0) {
        voiceAgentIsPlaying = false;
        return;
    }

    voiceAgentIsPlaying = true;
    // Create a loop that continuously processes and plays audio
    processVoiceAgentAudioContinuously();
}

// Process audio continuously from the queue
function processVoiceAgentAudioContinuously() {
    if (voiceAgentAudioQueue.length === 0) {
        const timeoutId = setTimeout(() => {
            if (voiceAgentAudioQueue.length > 0) {
                processVoiceAgentAudioContinuously();
            } else {
                voiceAgentIsPlaying = false;
            }
        }, 100);

        // Track this timeout too
        voiceAgentTimeouts.push(timeoutId);
        return;
    }

    const audioCtx = window.voiceAgentPlaybackContext;

    try {
        // Get the next chunk of audio from the queue
        const audioData = voiceAgentAudioQueue.shift();

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

        // Track this source in our active sources array
        voiceAgentActiveSources.push(source);

        // Calculate start time for this buffer
        const currentTime = audioCtx.currentTime;
        let startTime;

        if (voiceAgentNextStartTime <= currentTime) {
            // If next chunk start time is in the past or current, start immediately with a small offset
            startTime = currentTime + 0.01;
        } else {
            // Otherwise use the scheduled time
            startTime = voiceAgentNextStartTime;
        }

        // Start the audio playback
        source.start(startTime);

        // Only log scheduling occasionally to reduce console noise
        if (Math.random() < 0.05) {
            console.log(`Scheduled audio chunk (${audioBuffer.duration.toFixed(3)}s) to play at ${startTime.toFixed(3)}, queue length: ${voiceAgentAudioQueue.length}`);
        }

        // Update the next chunk start time
        voiceAgentNextStartTime = startTime + audioBuffer.duration;

        // When this chunk ends, schedule the next one
        source.onended = () => {
            // Remove this source from active sources array
            const sourceIndex = voiceAgentActiveSources.indexOf(source);
            if (sourceIndex > -1) {
                voiceAgentActiveSources.splice(sourceIndex, 1);
            }

            // Only log occasionally to reduce console noise
            if (Math.random() < 0.1) {
                console.log("Audio chunk playback complete");
            }
            // Process the next chunk immediately to ensure continuous playback
            processVoiceAgentAudioContinuously();
        };

        // Set a safety timeout in case the onended event doesn't fire
        const timeoutId = setTimeout(() => {
            if (voiceAgentAudioQueue.length > 0 && voiceAgentIsPlaying) {
                processVoiceAgentAudioContinuously();
            }
        }, audioBuffer.duration * 1000 + 100);

        // Track this timeout so we can clear it if needed
        voiceAgentTimeouts.push(timeoutId);

    } catch (error) {
        console.error("Error processing voice agent audio:", error);
        // Try to continue with the next chunk
        const timeoutId = setTimeout(() => {
            if (voiceAgentAudioQueue.length > 0) {
                processVoiceAgentAudioContinuously();
            } else {
                voiceAgentIsPlaying = false;
            }
        }, 100);

        // Track this timeout too
        voiceAgentTimeouts.push(timeoutId);
    }
}

// Stop voice agent audio
function stopVoiceAgentAudio() {
    console.log("🔇 Stopping all voice agent audio playback immediately");

    // Stop ALL active audio sources that might be scheduled or playing
    voiceAgentActiveSources.forEach((source, index) => {
        try {
            if (source && typeof source.stop === 'function') {
                source.stop();
                source.disconnect();
            }
        } catch (e) {
            console.warn(`Error stopping audio source ${index}:`, e);
        }
    });
    voiceAgentActiveSources = []; // Clear the array

    // Clear all audio-related timeouts
    voiceAgentTimeouts.forEach(timeoutId => {
        try {
            clearTimeout(timeoutId);
        } catch (e) {
            console.warn("Error clearing timeout:", e);
        }
    });
    voiceAgentTimeouts = []; // Clear the array

    // Clear the audio queue to stop upcoming audio
    const droppedChunks = voiceAgentAudioQueue.length;
    voiceAgentAudioQueue = [];

    // Reset audio playback state
    voiceAgentIsPlaying = false;
    voiceAgentAudioBuffering = true;
    voiceAgentNextStartTime = 0;

    // Reset timing for clean restart
    if (window.voiceAgentPlaybackContext) {
        voiceAgentNextStartTime = window.voiceAgentPlaybackContext.currentTime;
    }

    if (droppedChunks > 0) {
        console.log(`🗑️ Dropped ${droppedChunks} audio chunks`);
    }

    console.log("✅ All voice agent audio playback stopped successfully");
}

// Stop voice agent
function stopVoiceAgent(reason = "Session ended") {
    console.log("🛑 Stopping voice agent:", reason);
    
    voiceAgentState = 'stopping';
    
    // Close WebSocket
    if (voiceAgentWebSocket) {
        try {
            voiceAgentWebSocket.close(1000, reason);
        } catch (error) {
            console.error("Error closing WebSocket:", error);
        }
        voiceAgentWebSocket = null;
    }
    
    // Stop microphone
    if (voiceAgentMicStream) {
        try {
            voiceAgentMicStream.getTracks().forEach(track => track.stop());
        } catch (error) {
            console.error("Error stopping microphone:", error);
        }
        voiceAgentMicStream = null;
    }
    
    // Clean up audio
    if (voiceAgentAudioProcessor) {
        try {
            voiceAgentAudioProcessor.disconnect();
        } catch (error) {
            console.error("Error disconnecting audio processor:", error);
        }
        voiceAgentAudioProcessor = null;
    }
    
    if (voiceAgentAudioContext) {
        try {
            if (voiceAgentAudioContext.state !== 'closed') {
                voiceAgentAudioContext.close();
            }
        } catch (error) {
            console.error("Error closing audio context:", error);
        }
        voiceAgentAudioContext = null;
    }
    
    // Stop audio playback
    stopVoiceAgentAudio();
    
    // Clear timeouts
    voiceAgentTimeouts.forEach(timeoutId => {
        try {
            clearTimeout(timeoutId);
        } catch (e) {
            console.warn("Error clearing timeout:", e);
        }
    });
    voiceAgentTimeouts = [];
    
    // Clear session timeouts
    clearVoiceSessionTimeouts();
    
    // Clean up transcription timeouts
    if (voiceAgentAITimeout) {
        clearTimeout(voiceAgentAITimeout);
        voiceAgentAITimeout = null;
    }
    if (voiceAgentUserTimeout) {
        clearTimeout(voiceAgentUserTimeout);
        voiceAgentUserTimeout = null;
    }
    
    // Update UI
    voiceAgentState = 'idle';
    updateVoiceChatButton(false, false, "Start Voice Chat");
    displayVoiceMessage(`Voice chat ended: ${reason}`, 'ai');
}

// Create system prompt for voice agent
function createVoiceAgentSystemPrompt(wizardData) {
    const propertyName = wizardData.basicInfo?.propertyName || wizardData.basic_info?.propertyName || "this property";
    const propertyAddress = wizardData.basicInfo?.propertyAddress || wizardData.basic_info?.propertyAddress || "";
    const hostName = wizardData.hostName || "the host";
    
    // Analyze existing data to determine what's missing
    const gaps = analyzeKnowledgeGaps(wizardData);
    const gapSummary = gaps.map(gap => `- ${gap.category}: ${gap.questions.length} questions (${gap.reason})`).join('\n');
    
    // ENHANCED: Build context about voice sessions and extracted answers
    const voiceSessions = wizardData.voice_sessions || [];
    const clarifiedResponses = wizardData.clarifiedResponses || []; // Legacy support
    
    let previousSessionContext = '';
    let confirmedInfoSummary = [];
    
    if (voiceSessions.length > 0) {
        const sessionSummary = voiceSessions.map((session, index) => {
            const answers = Object.keys(session.extractedAnswers || {});
            return `Session ${index + 1} (${session.sessionId?.slice(-8) || 'unknown'}): ${answers.length} answers extracted - Topics: ${answers.join(', ')}`;
        }).join('\n');
        
        previousSessionContext = `\nPREVIOUS VOICE SESSIONS (${voiceSessions.length} sessions):
${sessionSummary}

EXTRACTED ANSWERS FROM PREVIOUS SESSIONS:`;
        
        // Build detailed confirmed information from voice sessions
        voiceSessions.forEach((session, sessionIndex) => {
            if (session.extractedAnswers) {
                Object.keys(session.extractedAnswers).forEach(topic => {
                    const answer = session.extractedAnswers[topic];
                    
                    switch (topic) {
                        case 'wifi':
                            if (answer.networkName && answer.password) {
                                confirmedInfoSummary.push(`✅ WIFI (Session ${sessionIndex + 1}): Network="${answer.networkName}", Password="${answer.password}"`);
                            }
                            break;
                        case 'parking':
                            if (answer.instruction) {
                                confirmedInfoSummary.push(`✅ PARKING (Session ${sessionIndex + 1}): ${answer.instruction}`);
                            }
                            break;
                        case 'emergency':
                            if (answer.detail) {
                                confirmedInfoSummary.push(`✅ EMERGENCY (Session ${sessionIndex + 1}): ${answer.detail}`);
                            }
                            break;
                        case 'appliances':
                            if (answer.brandModel) {
                                confirmedInfoSummary.push(`✅ APPLIANCE (Session ${sessionIndex + 1}): ${answer.brandModel}`);
                            }
                            break;
                    }
                });
            }
        });
    }
    
    // LEGACY: Also check old clarifiedResponses format
    if (clarifiedResponses.length > 0 && voiceSessions.length === 0) {
        previousSessionContext = `\nPREVIOUS CLARIFIED RESPONSES (${clarifiedResponses.length} legacy responses):
${clarifiedResponses.map((clarification, index) => {
    return `${index + 1}. ${clarification.topic.toUpperCase()}: "${clarification.clarified}"`;
}).join('\n')}

CRITICAL: These are confirmed answers from previous sessions. DO NOT repeat these questions.`;
    }
    
    // Build existing data summary for context
    const existingDataSummary = [];
    const basicInfo = wizardData.basicInfo || wizardData.basic_info || {};
    if (basicInfo.propertyName) existingDataSummary.push(`Property: ${basicInfo.propertyName}`);
    if (basicInfo.propertyAddress) existingDataSummary.push(`Address: ${basicInfo.propertyAddress}`);
    if (basicInfo.checkinTime || basicInfo.checkin_time) existingDataSummary.push(`Check-in: ${basicInfo.checkinTime || basicInfo.checkin_time}`);
    if (basicInfo.checkoutTime || basicInfo.checkout_time) existingDataSummary.push(`Check-out: ${basicInfo.checkoutTime || basicInfo.checkout_time}`);
    
    const houseRules = wizardData.houseRules || wizardData.house_rules || {};
    if (houseRules.rules?.length > 0) existingDataSummary.push(`House rules: ${houseRules.rules.length} defined`);
    
    const emergencies = wizardData.emergencies || wizardData.emergency_info || {};
    if (emergencies.scenarios?.length > 0) existingDataSummary.push(`Emergency info: ${emergencies.scenarios.length} scenarios`);
    
    const localRecs = wizardData.localRecommendations || wizardData.local_recommendations || {};
    if (localRecs.selectedPlaces?.length > 0) existingDataSummary.push(`Local places: ${localRecs.selectedPlaces.length} selected`);
    
    // If no previous sessions, indicate this is first session
    if (previousSessionContext === '') {
        previousSessionContext = '\nThis is your first voice session with this host.';
    }
    
    return `You are Leo, a friendly AI assistant helping ${hostName} complete the knowledge base for their property "${propertyName}" at ${propertyAddress}.

You are conducting a conversational interview to gather comprehensive property information that will help future guests have an amazing stay.

EXISTING PROPERTY DATA:
${existingDataSummary.join('\n')}
${previousSessionContext}

${confirmedInfoSummary.length > 0 ? `\nCONFIRMED INFORMATION FROM PREVIOUS SESSIONS:
${confirmedInfoSummary.join('\n')}

IMPORTANT: The above information has been confirmed and structured from previous conversations. Reference it when relevant but do not re-ask these questions unless you need updates or clarification.` : ''}

REMAINING KNOWLEDGE GAPS TO ADDRESS:
${gapSummary}

YOUR ROLE & APPROACH:
- You are a professional and friendly property assistant
- ALWAYS acknowledge what information you already have from previous sessions
- Focus ONLY on the knowledge gaps identified above
- When you receive an answer, REPEAT IT BACK in clear, organized language for confirmation
- Ask one focused question at a time in a conversational manner
- Listen carefully and extract specific, actionable information
- Follow up with clarifying questions when needed
- Be encouraging and acknowledge when the host provides good information

CONVERSATION STRATEGY:
1. Start by briefly acknowledging any previous sessions and what you've already learned
2. Explain that you want to fill in the remaining gaps to complete their property knowledge base
3. Focus on the highest priority gaps first (WiFi, parking, emergency info)
4. For each topic, ask specific, practical questions that guests would want to know
5. Extract exact details: network names, passwords, locations, step-by-step procedures
6. When you get good information, ALWAYS repeat it back clearly and ask for confirmation
7. Keep the conversation efficient and focused - don't repeat covered topics

INFORMATION TO COLLECT:
- WiFi network names and passwords (exact details for guest instructions)
- Parking instructions and any restrictions
- Emergency procedures and safety information (exact locations, clear instructions)
- Appliance brands, models, and operating instructions for common items  

CONVERSATION STYLE:
- Be conversational and natural - this is a helpful consultation, not an interrogation
- Show that you're building on what you already know
- Ask practical, specific questions that guests actually need answers to
- Get exact details: network names, passwords, brand names, and step-by-step procedures
- If something is unclear, ask follow-up questions immediately
- When the host gives you information, ALWAYS repeat it back in organized, clear language
- Say things like: "Let me confirm what I understood..." or "So to clarify..."
- Wait for confirmation before moving to the next topic

SESSION GOAL:
Your goal is to efficiently fill the identified knowledge gaps so that guests will have all the information they need for a great stay. When you repeat information back, organize it clearly and wait for the host to confirm it's correct. Focus on extracting structured, actionable information that can be easily used by guests.

Start by greeting the host warmly, acknowledging any previous work together, and explaining what specific gaps you'd like to fill in this session.`;
}

// Create initial greeting
function createInitialGreeting(wizardData) {
    const propertyName = wizardData.basicInfo?.propertyName || "your property";
    const gaps = analyzeKnowledgeGaps(wizardData);
    
    return `Hello! I'm Leo, your AI property consultant. I'm here to help you complete the knowledge base for ${propertyName}. 

I can see you've already provided some great information through the setup wizard. Now I'd like to have a conversation with you to fill in some important details that will help your guests have an amazing stay.

I have about ${gaps.length} categories of questions to cover, focusing on practical information that guests commonly ask about. We'll go through this conversationally - just like having a friendly chat about your property.

Are you ready to get started? I'll ask you one question at a time, and please feel free to give me as much detail as you'd like!`;
}

// Helper function to extract appliance type from question
function extractApplianceType(question) {
    const applianceTypes = [
        'coffeemaker', 'stove', 'fridge', 'dishwasher', 'smart lock', 
        'whirlpool', 'hot tub', 'grill', 'hairdryer', 'iron', 
        'washing machine', 'dryer', 'microwave', 'toaster', 'hvac',
        'television', 'tv', 'ac unit'
    ];
    
    const questionLower = question.toLowerCase();
    for (const type of applianceTypes) {
        if (questionLower.includes(type)) {
            return type;
        }
    }
    return 'appliance';
}

// Helper function to extract rule type from question
function extractRuleType(question) {
    if (question.includes('pets')) return 'pets';
    if (question.includes('noise') || question.includes('parties')) return 'noise';
    if (question.includes('smoking')) return 'smoking';
    return 'general';
}

// Process host response and extract information
async function processHostResponse(responseText) {
    try {
        console.log("📝 Processing host response:", responseText);
        
        // Extract structured information from the response
        const extractedInfo = await extractInformationFromResponse(responseText);
        
        if (extractedInfo && Object.keys(extractedInfo).length > 0) {
            // Store the extracted information
            await updateWizardWithVoiceData(extractedInfo);
            console.log("✅ Information extracted and stored:", extractedInfo);
        }
        
    } catch (error) {
        console.error("❌ Error processing host response:", error);
    }
}

// Extract structured information from natural language response
async function extractInformationFromResponse(responseText) {
    // This would ideally use AI to extract structured data
    // For now, we'll use simple keyword matching and patterns
    
    const extractedInfo = {};
    const textLower = responseText.toLowerCase();
    
    // Extract brand and model information
    const brandModelRegex = /(?:brand|model|make)\s+(?:is|:)?\s*([a-zA-Z0-9\s\-]+?)(?:[,\.]|$)/gi;
    let match;
    while ((match = brandModelRegex.exec(responseText)) !== null) {
        if (!extractedInfo.appliances) extractedInfo.appliances = [];
        extractedInfo.appliances.push({
            type: 'unknown',
            brand: match[1].trim(),
            context: responseText
        });
    }
    
    // Extract location information
    if (textLower.includes('located') || textLower.includes('in the') || textLower.includes('near the')) {
        const locationRegex = /(?:located|in the|near the)\s+([a-zA-Z0-9\s]+?)(?:[,\.]|$)/gi;
        while ((match = locationRegex.exec(responseText)) !== null) {
            if (!extractedInfo.locations) extractedInfo.locations = [];
            extractedInfo.locations.push({
                item: 'unknown',
                location: match[1].trim(),
                context: responseText
            });
        }
    }
    
    // Extract procedures and instructions
    if (textLower.includes('should') || textLower.includes('need to') || textLower.includes('have to')) {
        if (!extractedInfo.procedures) extractedInfo.procedures = [];
        extractedInfo.procedures.push({
            procedure: responseText,
            category: 'general'
        });
    }
    
    // Extract contact information
    const phoneRegex = /(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})/g;
    while ((match = phoneRegex.exec(responseText)) !== null) {
        if (!extractedInfo.contacts) extractedInfo.contacts = [];
        extractedInfo.contacts.push({
            type: 'phone',
            value: match[1],
            context: responseText
        });
    }
    
    return extractedInfo;
}

// Update wizard data with voice-collected information
async function updateWizardWithVoiceData(extractedInfo) {
    try {
        // CRITICAL FIX: Load complete wizard data from both sources
        let currentData = null;
        
        // Priority 1: Get data from main wizard instance (most current)
        if (window.wizardInstance && window.wizardInstance.wizardData) {
            console.log("📋 Loading complete wizard data from main instance");
            window.wizardInstance.collectFormData(); // Ensure it's completely up to date
            currentData = { ...window.wizardInstance.wizardData }; // Deep copy to avoid mutations
        }
        
        // Priority 2: Fallback to Firestore if main instance unavailable
        if (!currentData || Object.keys(currentData).length === 0) {
            console.log("📋 Fallback: Loading wizard data from Firestore");
            const response = await fetch('/setup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    action: 'load_progress'
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                currentData = result.data || {};
            }
        }
        
        if (!currentData || Object.keys(currentData).length === 0) {
            console.error("❌ No wizard data found to update - cannot save voice data");
            return;
        }
        
        console.log(`📊 Current wizard data has ${Object.keys(currentData).length} main sections`);
        
        // IMPROVED: Better voice data accumulation
        if (!currentData.voiceCollectedData) {
            currentData.voiceCollectedData = [];
        }
        
        // Create new voice session entry with better structure
        const newVoiceEntry = {
            timestamp: new Date().toISOString(),
            sessionId: voiceAgentSessionId || `session_${Date.now()}`,
            extractedInfo: extractedInfo,
            // Add summary for easier analysis
            summary: {
                totalItems: Object.keys(extractedInfo).reduce((count, key) => count + (extractedInfo[key]?.length || 0), 0),
                categories: Object.keys(extractedInfo).filter(key => extractedInfo[key]?.length > 0)
            }
        };
        
        // Add to accumulated voice data
        currentData.voiceCollectedData.push(newVoiceEntry);
        
        // IMPROVED: Also update the main wizard structure with voice data
        // This makes the data more accessible and searchable
        if (extractedInfo.appliances) {
            if (!currentData.applianceInfo) currentData.applianceInfo = [];
            extractedInfo.appliances.forEach(appliance => {
                // Avoid duplicates by checking existing entries
                const exists = currentData.applianceInfo.some(existing => 
                    existing.type === appliance.type && existing.brand === appliance.brand
                );
                if (!exists) {
                    currentData.applianceInfo.push({
                        ...appliance,
                        source: 'voice',
                        addedAt: new Date().toISOString()
                    });
                }
            });
        }
        
        if (extractedInfo.procedures) {
            if (!currentData.procedureInfo) currentData.procedureInfo = [];
            extractedInfo.procedures.forEach(procedure => {
                currentData.procedureInfo.push({
                    ...procedure,
                    source: 'voice',
                    addedAt: new Date().toISOString()
                });
            });
        }
        
        if (extractedInfo.locations) {
            if (!currentData.locationInfo) currentData.locationInfo = [];
            extractedInfo.locations.forEach(location => {
                currentData.locationInfo.push({
                    ...location,
                    source: 'voice',
                    addedAt: new Date().toISOString()
                });
            });
        }
        
        if (extractedInfo.contacts) {
            if (!currentData.contactInfo) currentData.contactInfo = [];
            extractedInfo.contacts.forEach(contact => {
                const exists = currentData.contactInfo.some(existing => 
                    existing.type === contact.type && existing.value === contact.value
                );
                if (!exists) {
                    currentData.contactInfo.push({
                        ...contact,
                        source: 'voice',
                        addedAt: new Date().toISOString()
                    });
                }
            });
        }
        
        console.log(`💾 Saving wizard data with ${currentData.voiceCollectedData.length} voice entries`);
        console.log(`📈 Voice data summary: ${newVoiceEntry.summary.totalItems} items in categories: ${newVoiceEntry.summary.categories.join(', ')}`);
        
        // Save updated data - PRESERVE the current step from main wizard
        const currentStep = window.wizardInstance ? window.wizardInstance.currentStep : 6;
        const success = await saveWizardProgress(currentData, currentStep);
        
        if (success) {
            console.log("✅ Wizard data updated with voice information without data loss");
            
            // Also update the main wizard instance if available
            if (window.wizardInstance) {
                window.wizardInstance.wizardData = currentData;
                console.log("🔄 Updated main wizard instance with voice data");
            }
        } else {
            console.error("❌ Failed to save updated wizard data");
        }
        
    } catch (error) {
        console.error("❌ Error updating wizard data:", error);
    }
}

// Display voice message in chat
function displayVoiceMessage(message, role) {
    const chatContainer = document.getElementById('voice-chat-messages');
    if (!chatContainer) {
        console.warn("⚠️ Voice chat container not found");
        return;
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `voice-message ${role === 'user' ? 'user-message' : 'ai-message'}`;
    
    const roleLabel = role === 'user' ? 'You' : 'Leo';
    const timestamp = new Date().toLocaleTimeString();
    
    messageDiv.innerHTML = `
        <div class="message-header">
            <span class="role-label">${roleLabel}</span>
            <span class="timestamp">${timestamp}</span>
        </div>
        <div class="message-content">${message}</div>
    `;
    
    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Update voice chat button
function updateVoiceChatButton(isActive, isDisabled = false, statusText = null) {
    const button = document.getElementById('start-voice-chat');
    if (!button) return;
    
    button.disabled = isDisabled;
    
    if (isDisabled) {
        button.classList.add('disabled');
        button.classList.remove('active');
    } else if (isActive) {
        button.classList.add('active');
        button.classList.remove('disabled');
    } else {
        button.classList.remove('active', 'disabled');
    }
    
    if (statusText) {
        button.textContent = statusText;
    }
}

// Load wizard progress from main wizard instance or Firestore
async function loadWizardProgress() {
    try {
        // First try to get data from the main wizard instance if available
        if (window.wizardInstance && window.wizardInstance.wizardData) {
            console.log("📋 Using wizard data from main instance");
            window.wizardInstance.collectFormData(); // Ensure it's up to date
            return window.wizardInstance.wizardData;
        }
        
        // Fallback to Firestore
        const userId = window.CURRENT_USER_ID;
        if (!userId) {
            console.error("❌ No user ID found");
            return null;
        }
        
        const response = await fetch('/setup', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                action: 'load_progress'
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            return data.data || null;
        } else {
            console.error("❌ Failed to load wizard progress:", response.status);
            return null;
        }
        
    } catch (error) {
        console.error("❌ Error loading wizard progress:", error);
        return null;
    }
}

// Save wizard progress to Firestore
async function saveWizardProgress(wizardData, step = 6) {
    try {
        const userId = window.CURRENT_USER_ID;
        if (!userId) {
            console.error("❌ No user ID found");
            return false;
        }
        
        const response = await fetch('/setup', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                action: 'save_progress',
                step: step,
                data: wizardData
            })
        });
        
        return response.ok;
        
    } catch (error) {
        console.error("❌ Error saving wizard progress:", error);
        return false;
    }
}

// Fetch authentication token
async function fetchAuthToken() {
    try {
        const response = await fetch('/api/gemini-voice-config', {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            },
            credentials: 'same-origin'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const config = await response.json();
        if (!config.apiKey) {
            throw new Error("API key not found in server response");
        }
        
        return config.apiKey;
        
    } catch (error) {
        console.error("❌ Error fetching auth token:", error);
        throw error;
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

// Utility function to convert Base64 to ArrayBuffer
function base64ToArrayBuffer(base64) {
    if (!base64 || typeof base64 !== 'string') {
        return new ArrayBuffer(0);
    }
    
    try {
        let cleanBase64 = base64;
        if (base64.includes('base64,')) {
            cleanBase64 = base64.split('base64,')[1];
        }
        
        cleanBase64 = cleanBase64.replace(/\s/g, '');
        while (cleanBase64.length % 4 !== 0) {
            cleanBase64 += '=';
        }
        
        const binaryString = window.atob(cleanBase64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        
        return bytes.buffer;
    } catch (error) {
        console.error("❌ Error converting base64 to ArrayBuffer:", error);
        return new ArrayBuffer(0);
    }
}

// Expose voice agent functions to global window object immediately
window.voiceAgent = {
    initializeVoiceAgent,
    handleVoiceChatStart,
    stopVoiceAgent,
    voiceAgentState: () => voiceAgentState, // Use function to get current state
    createVoiceAgentSystemPrompt,
    analyzeKnowledgeGaps,
    ONBOARDING_QUESTIONS
};

// Make it available immediately
console.log("🎙️ Voice Agent functions exposed to window.voiceAgent");

// ES6 exports removed - using window.voiceAgent instead for browser compatibility

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname === '/setup') {
        // Small delay to ensure other scripts are loaded
        setTimeout(() => {
            initializeVoiceAgent();
        }, 500);
    }
});

// Session timeout management functions
function startVoiceSessionTimeout() {
    voiceSessionStartTime = Date.now();
    
    // Set warning timeout (30 seconds before end)
    const warningTime = (VOICE_SESSION_TIMEOUT_MINUTES * 60 - VOICE_SESSION_WARNING_SECONDS) * 1000;
    voiceSessionWarningTimeoutId = setTimeout(() => {
        console.log("🚨 Voice session timeout warning triggered");
        displayVoiceMessage(`⚠️ Your voice session will end in ${VOICE_SESSION_WARNING_SECONDS} seconds. The conversation will be saved automatically.`, 'ai');
    }, warningTime);
    
    // Set final timeout
    const timeoutTime = VOICE_SESSION_TIMEOUT_MINUTES * 60 * 1000;
    voiceSessionTimeoutId = setTimeout(() => {
        console.log("⏰ Voice session timeout reached, ending gracefully");
        displayVoiceMessage("Your voice session has reached the time limit. All information has been saved automatically. You can continue with other setup steps or start a new voice session if needed.", 'ai');
        stopVoiceAgent("Session timeout reached - information saved");
    }, timeoutTime);
    
    console.log(`🕒 Voice session timeout set for ${VOICE_SESSION_TIMEOUT_MINUTES} minutes`);
}

function clearVoiceSessionTimeouts() {
    if (voiceSessionTimeoutId) {
        clearTimeout(voiceSessionTimeoutId);
        voiceSessionTimeoutId = null;
    }
    if (voiceSessionWarningTimeoutId) {
        clearTimeout(voiceSessionWarningTimeoutId);
        voiceSessionWarningTimeoutId = null;
    }
} 