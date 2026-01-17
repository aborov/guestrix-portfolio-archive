/*
 * Secure Voice Call functionality for Guestrix Landing Page
 * This version connects to our secure WebSocket proxy instead of directly to Gemini Live API
 */

// Constants for audio processing
const GEMINI_OUTPUT_SAMPLE_RATE = 24000;  // Gemini audio is 24kHz
const MIC_BUFFER_SIZE = 4096;  // Size of microphone audio buffer
const GEMINI_LIVE_MODEL = "gemini-2.0-flash-live-001";  // Model ID for live voice calls
const GEMINI_VOICES = ["Aoede", "Chorister", "Dawnsmell", "Hearth", "Joyishness", "Jurai", "Patzelt", "Shiralish"];
const GEMINI_DEFAULT_VOICE = "Aoede";  // Default voice to use
const MAX_AUDIO_QUEUE_LENGTH = 60;  // Maximum number of chunks to keep in the audio queue
const AUDIO_INITIAL_BUFFER_COUNT = 3;  // Number of chunks to buffer before playing

// Secure WebSocket proxy configuration
const PROXY_SERVER_URL = window.location.hostname === 'localhost' 
    ? 'ws://localhost:8081/gemini-voice-proxy'
    : `wss://${window.location.hostname}:8081/gemini-voice-proxy`;

// Voice Call Globals
let currentCallState = 'idle'; // idle, starting, active, stopping
let microphoneStream = null;
let audioProcessorNode = null;
let proxyWebSocket = null; // Connection to our secure proxy
let clientId = null;

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

// Initialize voice call functionality when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    const voiceCallButton = document.getElementById('voice-call-button');
    if (voiceCallButton) {
        voiceCallButton.addEventListener('click', handleVoiceCallClick);
        console.log("Secure voice call functionality initialized");
    }
});

// Handle voice call button click
async function handleVoiceCallClick() {
    const button = document.getElementById('voice-call-button');
    if (!button) return;

    const currentStatus = button.dataset.status || 'idle';

    if (currentStatus === 'idle') {
        await startSecureVoiceCall();
    } else if (currentStatus === 'active') {
        await stopVoiceCall("User ended call");
    }
}

// Start a secure voice call through our proxy
async function startSecureVoiceCall() {
    console.log("Starting secure voice call through proxy...");
    
    // Update state
    currentCallState = 'starting';
    updateButtonState('connecting');

    try {
        // 1. Request microphone access first
        try {
            microphoneStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            console.log("Microphone access granted");
        } catch (micError) {
            console.error("Microphone access denied:", micError);
            throw new Error("Microphone access required for voice call.");
        }

        // 2. Connect to our secure proxy
        await connectToProxy();

        // 3. Set up audio processing
        await setupAudioProcessing();

        // 4. Start Gemini session through proxy
        await startGeminiSessionThroughProxy();

    } catch (error) {
        console.error("Error starting secure voice call:", error);
        updateButtonState('idle');
        currentCallState = 'idle';
        showError(`Failed to start voice call: ${error.message}`);
    }
}

// Connect to our secure WebSocket proxy
async function connectToProxy() {
    return new Promise((resolve, reject) => {
        console.log(`Connecting to secure proxy: ${PROXY_SERVER_URL}`);
        
        proxyWebSocket = new WebSocket(PROXY_SERVER_URL);
        
        proxyWebSocket.onopen = () => {
            console.log("Connected to secure proxy");
            resolve();
        };

        proxyWebSocket.onmessage = (event) => {
            handleProxyMessage(event);
        };

        proxyWebSocket.onclose = (event) => {
            console.log("Proxy connection closed:", event.code, event.reason);
            if (currentCallState === 'active') {
                stopVoiceCall("Proxy connection lost");
            }
        };

        proxyWebSocket.onerror = (error) => {
            console.error("Proxy WebSocket error:", error);
            reject(new Error("Failed to connect to voice service"));
        };

        // Timeout for connection
        setTimeout(() => {
            if (proxyWebSocket.readyState !== WebSocket.OPEN) {
                proxyWebSocket.close();
                reject(new Error("Connection timeout"));
            }
        }, 10000);
    });
}

// Handle messages from our secure proxy
function handleProxyMessage(event) {
    try {
        // Handle binary data (audio)
        if (event.data instanceof Blob) {
            event.data.arrayBuffer().then(arrayBuffer => {
                if (arrayBuffer.byteLength > 0) {
                    queueAudioForPlayback(arrayBuffer);
                }
            });
            return;
        }

        // Handle text/JSON messages
        const message = JSON.parse(event.data);
        
        switch (message.type) {
            case 'proxy_connected':
                clientId = message.clientId;
                console.log(`Assigned client ID: ${clientId}`);
                break;

            case 'session_started':
                console.log("Gemini session started through proxy");
                currentCallState = 'active';
                updateButtonState('active');
                startCallTimer();
                break;

            case 'session_ended':
                console.log("Gemini session ended:", message.reason);
                stopVoiceCall(`Session ended: ${message.reason}`);
                break;

            case 'gemini_response':
                handleGeminiResponse(message.data);
                break;

            case 'error':
                console.error("Proxy error:", message.message);
                showError(message.message);
                break;

            default:
                console.log("Unknown proxy message type:", message.type);
        }
    } catch (error) {
        console.error("Error handling proxy message:", error);
    }
}

// Set up audio processing for microphone input
async function setupAudioProcessing() {
    // Set up audio context for processing microphone input
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

    // Set up audio processor to handle microphone input
    audioProcessorNode.onaudioprocess = (e) => {
        // Check if we have an active connection
        if (proxyWebSocket && proxyWebSocket.readyState === WebSocket.OPEN && currentCallState === 'active') {
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

                    // Convert to base64 for transmission
                    const base64Audio = arrayBufferToBase64(combinedBuffer.buffer);

                    // Send to Gemini through our proxy
                    const message = {
                        type: 'gemini_message',
                        data: {
                            realtime_input: {
                                media_chunks: [
                                    {
                                        data: base64Audio,
                                        mime_type: "audio/pcm"
                                    }
                                ]
                            }
                        }
                    };

                    try {
                        proxyWebSocket.send(JSON.stringify(message));
                        // Clear chunks after sending
                        audioChunks = [];
                        lastSendTime = now;
                    } catch (err) {
                        console.error("Error sending audio through proxy:", err);
                    }
                }
            }
        }
    };

    console.log("Audio processing setup complete");
}

// Start Gemini session through our secure proxy
async function startGeminiSessionThroughProxy() {
    const config = {
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
            realtimeInputConfig: {
                automaticActivityDetection: {
                    enable: true,
                    voiceActivityTimeout: 2000,
                    speechStartTimeout: 1000,
                    speechEndTimeout: 1000
                },
                interruptionSettings: {
                    enable: true,
                    maxInterruptionResponseTime: 1000
                }
            }
        }
    };

    // Send session start request to proxy
    const message = {
        type: 'start_session',
        config: config
    };

    try {
        proxyWebSocket.send(JSON.stringify(message));
        console.log("Gemini session start request sent through proxy");
    } catch (error) {
        throw new Error(`Failed to start session through proxy: ${error.message}`);
    }
}

// Handle Gemini responses from proxy
function handleGeminiResponse(data) {
    // Process the Gemini response data
    // This is similar to your existing processGeminiJsonMessage function
    if (data.serverContent && data.serverContent.modelTurn) {
        const modelTurn = data.serverContent.modelTurn;
        
        if (modelTurn.parts) {
            for (const part of modelTurn.parts) {
                if (part.functionCall && part.functionCall.name === "end_call") {
                    console.log("Gemini requested call end:", part.functionCall.args);
                    stopVoiceCall("AI ended call");
                    return;
                }
            }
        }
    }

    // Handle other response types as needed
    console.log("Received Gemini response through proxy:", data);
}

// Function to stop the voice call
async function stopVoiceCall(reason = "User ended call") {
    console.log("Stopping secure voice call. Reason:", reason);

    // Update state immediately
    currentCallState = 'stopping';
    updateButtonState('ending');

    // Clear call timer
    if (callTimeoutId) {
        clearTimeout(callTimeoutId);
        callTimeoutId = null;
    }
    if (warningTimeoutId) {
        clearTimeout(warningTimeoutId);
        warningTimeoutId = null;
    }

    // Stop audio processing
    if (audioProcessorNode) {
        try {
            audioProcessorNode.disconnect();
            audioProcessorNode = null;
        } catch (error) {
            console.error("Error disconnecting audio processor:", error);
        }
    }

    // Stop microphone stream
    if (microphoneStream) {
        microphoneStream.getTracks().forEach(track => track.stop());
        microphoneStream = null;
    }

    // Close audio context
    if (audioContext) {
        try {
            await audioContext.close();
            audioContext = null;
        } catch (error) {
            console.error("Error closing audio context:", error);
        }
    }

    // Stop audio playback
    stopAllAudio();

    // End session through proxy
    if (proxyWebSocket && proxyWebSocket.readyState === WebSocket.OPEN) {
        try {
            proxyWebSocket.send(JSON.stringify({
                type: 'end_session'
            }));
        } catch (error) {
            console.error("Error sending end session to proxy:", error);
        }
    }

    // Close proxy connection
    if (proxyWebSocket) {
        try {
            proxyWebSocket.close(1000, reason);
        } catch (error) {
            console.error("Error closing proxy WebSocket:", error);
        }
        proxyWebSocket = null;
    }

    // Reset state
    currentCallState = 'idle';
    clientId = null;
    audioQueue = [];
    isAudioPlaying = false;
    audioBuffering = true;
    nextChunkStartTime = 0;

    // Update UI
    updateButtonState('idle');
    console.log("Voice call stopped successfully");
}

// Call timer functions
function startCallTimer() {
    callStartTime = Date.now();
    
    // Set warning timeout
    warningTimeoutId = setTimeout(() => {
        console.warn(`Call will end in ${WARNING_SECONDS} seconds`);
        // You could show a warning to the user here
    }, (CALL_TIMEOUT_MINUTES * 60 - WARNING_SECONDS) * 1000);
    
    // Set call timeout
    callTimeoutId = setTimeout(() => {
        console.log("Call timed out");
        stopVoiceCall("Call timeout");
    }, CALL_TIMEOUT_MINUTES * 60 * 1000);
}

// Update button state
function updateButtonState(state) {
    const button = document.getElementById('voice-call-button');
    if (!button) return;

    const btnText = button.querySelector('.btn-text');
    const icon = button.querySelector('i');

    button.dataset.status = state;

    switch (state) {
        case 'idle':
            btnText.textContent = 'Talk to Staycee';
            icon.className = 'fas fa-microphone';
            button.disabled = false;
            button.classList.remove('connecting', 'active', 'ending');
            break;

        case 'connecting':
            btnText.textContent = 'Connecting...';
            icon.className = 'fas fa-spinner fa-spin';
            button.disabled = true;
            button.classList.add('connecting');
            break;

        case 'active':
            btnText.textContent = 'End Call';
            icon.className = 'fas fa-phone-slash';
            button.disabled = false;
            button.classList.remove('connecting');
            button.classList.add('active');
            break;

        case 'ending':
            btnText.textContent = 'Ending...';
            icon.className = 'fas fa-spinner fa-spin';
            button.disabled = true;
            button.classList.add('ending');
            break;
    }
}

// Show error message
function showError(message) {
    console.error("Voice call error:", message);
    // You could show a user-friendly error message here
    // For example, update a status element or show a modal
    
    const errorElement = document.getElementById('voice-call-error');
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.style.display = 'block';
        setTimeout(() => {
            errorElement.style.display = 'none';
        }, 5000);
    }
}

// Audio playback functions (reuse existing ones with minor modifications)
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

    // Add to queue
    const wasQueueEmpty = audioQueue.length === 0;
    audioQueue.push(audioBuffer);

    // Keep queue from growing too large
    while (audioQueue.length > MAX_AUDIO_QUEUE_LENGTH) {
        audioQueue.shift();
        console.warn("Audio queue too large, dropping oldest chunk");
    }

    // Start playback if not already playing
    if (wasQueueEmpty && !isAudioPlaying) {
        startContinuousPlayback();
    }
}

function startContinuousPlayback() {
    if (audioQueue.length === 0) {
        isAudioPlaying = false;
        return;
    }

    isAudioPlaying = true;
    processAudioContinuously();
}

function processAudioContinuously() {
    // Check if we have an active call and if playback should continue
    if (currentCallState !== 'active') {
        isAudioPlaying = false;
        audioQueue = [];
        return;
    }

    if (!isAudioPlaying || audioQueue.length === 0) {
        isAudioPlaying = false;
        return;
    }

    // Process next audio chunk
    const audioBuffer = audioQueue.shift();
    
    try {
        // Decode and play the audio buffer
        window.audioPlayerContext.decodeAudioData(audioBuffer.slice())
            .then(decodedBuffer => {
                if (currentCallState === 'active') {
                    playAudioBuffer(decodedBuffer);
                }
                
                // Continue processing queue
                setTimeout(() => {
                    processAudioContinuously();
                }, 50);
            })
            .catch(error => {
                console.error("Error decoding audio:", error);
                // Continue processing queue even if one chunk fails
                setTimeout(() => {
                    processAudioContinuously();
                }, 50);
            });
    } catch (error) {
        console.error("Error processing audio chunk:", error);
        setTimeout(() => {
            processAudioContinuously();
        }, 50);
    }
}

function playAudioBuffer(audioBuffer) {
    if (!window.audioPlayerContext || currentCallState !== 'active') {
        return;
    }

    try {
        const source = window.audioPlayerContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(window.audioPlayerContext.destination);
        
        // Track active audio sources
        activeAudioSources.push(source);
        
        source.onended = () => {
            const index = activeAudioSources.indexOf(source);
            if (index > -1) {
                activeAudioSources.splice(index, 1);
            }
        };
        
        source.start();
    } catch (error) {
        console.error("Error playing audio buffer:", error);
    }
}

function stopAllAudio() {
    // Stop all active audio sources
    activeAudioSources.forEach(source => {
        try {
            source.stop();
        } catch (error) {
            // Ignore errors when stopping audio sources
        }
    });
    activeAudioSources = [];

    // Clear all audio timeouts
    audioTimeouts.forEach(timeout => clearTimeout(timeout));
    audioTimeouts = [];

    // Clear audio queue
    audioQueue = [];
    isAudioPlaying = false;
}

// Utility functions
function arrayBufferToBase64(buffer) {
    const binary = [];
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < bytes.byteLength; i++) {
        binary.push(String.fromCharCode(bytes[i]));
    }
    return btoa(binary.join(''));
}

function createVoiceSystemPrompt() {
    return `You are Staycee, an AI guest concierge for Guestrix. You are helping potential customers understand how Guestrix can help them with their short-term rental business.

Key points about Guestrix:
- Staycee is an AI guest concierge that helps short-term rental hosts by answering common guest questions
- Reduces daily messages from 20+ to just 3 on average
- Works with Airbnb and Vrbo
- Provides instant answers to guests 24/7
- Customized for each property with specific details
- Helps hosts reclaim their time while maintaining great guest service

Keep your responses concise and natural. This is a voice call, so speak conversationally. Focus on understanding what the caller needs and how Guestrix can help their hosting business.

If the conversation reaches a natural conclusion or the user indicates they want to end the call, use the end_call function.`;
} 