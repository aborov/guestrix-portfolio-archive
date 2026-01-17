// Dashboard functionality for Guestrix

// Global state variables related to voice call
let isVoiceCallActive = false;
let isAudioStreaming = false;
let audioContext;
let micStream;
let scriptProcessor;
let mediaStreamSource; // Renamed from sourceNode for consistency?
let socket = null;

// Global state variable for dictation (mic button in text input)
let isRecording = false;

const BUFFER_SIZE = 4096;
const TARGET_SAMPLE_RATE = 16000;

// ---- Web Speech API Setup ----
let recognition = null;
try {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        console.log("Web Speech API supported.");
    } else {
        console.warn("Web Speech API not supported in this browser.");
        // Optionally disable the record button if API is not supported
        const recordButton = document.getElementById('record-message');
        if(recordButton) recordButton.disabled = true;
    }
} catch (e) {
    console.error("Error initializing SpeechRecognition:", e);
}

if (recognition) {
    recognition.continuous = false; // Process speech after user stops talking
    recognition.lang = 'en-US'; // Set language
    recognition.interimResults = false; // Get final result only
    recognition.maxAlternatives = 1;
}
// -----------------------------

// Sample reservation data (in a real app, this would come from an API)
const sampleReservations = [
    {
        id: "res123456",
        hotelName: "Grand Hotel",
        checkIn: "2025-04-15",
        checkOut: "2025-04-20",
        roomType: "Deluxe King",
        guests: 2,
        status: "confirmed",
        totalPrice: "$1,250.00"
    },
    {
        id: "res789012",
        hotelName: "Seaside Resort",
        checkIn: "2025-05-10",
        checkOut: "2025-05-15",
        roomType: "Ocean View Suite",
        guests: 3,
        status: "pending",
        totalPrice: "$1,800.00"
    }
];

// Function to load reservations (for guests)
function loadReservations(userId) {
    console.log('Loading reservations...');
    const reservationsContainer = document.getElementById('reservations-container');
    const loadingDiv = document.getElementById('loading-reservations');
    const noReservationsDiv = document.getElementById('no-reservations');
    const reservationsListDiv = document.getElementById('reservations-list');

    // Only proceed if the reservations container exists (i.e., on guest dashboard)
    if (!reservationsContainer) {
        console.log('Reservations container not found, likely on host dashboard. Skipping loadReservations.');
        return; 
    }

    loadingDiv.style.display = 'block';
    noReservationsDiv.style.display = 'none';
    reservationsListDiv.style.display = 'none';

    // Get the user's phone number and ID for API call
    const phoneNumber = window.PHONE_NUMBER || '';
    const userId = window.CURRENT_USER_ID || '';

    // Determine API URL - prefer user ID if available
    let apiUrl;
    if (userId) {
        apiUrl = `/api/reservations/${userId}`;
        console.log("Using user ID for reservation lookup:", userId);
    } else {
        apiUrl = `/api/reservations?phone=${encodeURIComponent(phoneNumber)}`;
        console.log("Using phone number for reservation lookup:", phoneNumber);
    }

    console.log("Calling reservations API endpoint:", apiUrl);

    // Fetch reservations from the backend using session authentication
    fetch(apiUrl)
        .then(response => {
            if (!response.ok) {
                // Try to parse error message from backend if available
                return response.text().then(text => { 
                    try {
                        const errData = JSON.parse(text);
                        throw new Error(errData.error || `HTTP error! status: ${response.status}`);
                    } catch (e) {
                        throw new Error(text || `HTTP error! status: ${response.status}`);
                    }
                });
            }
            return response.json();
        })
        .then(data => {
            loadingDiv.style.display = 'none';

            // Expecting backend to return { success: true, reservations: [...] } or { success: false, error: '...' }
            if (data.success && data.reservations) {
                if (data.reservations.length === 0) {
                    noReservationsDiv.style.display = 'block';
                } else {
                    reservationsListDiv.style.display = 'block';
                    // Use the correct render function - assuming guest_dashboard.js has one?
                    // For now, using the existing renderReservations from this file
                    renderReservations(data.reservations); 
                }
            } else {
                // Handle cases where backend returns success: false or unexpected format
                throw new Error(data.error || 'Invalid data format received from server.');
            }
        })
        .catch(error => {
            console.error('Error loading reservations:', error);
            loadingDiv.style.display = 'none';
            reservationsListDiv.innerHTML = `
                <div class="alert alert-danger">
                    <p>Error loading reservations. Please try again later.</p>
                    <p class="small">${error.message}</p>
                </div>
            `;
            reservationsListDiv.style.display = 'block';
        });
}

// Function to render reservations
function renderReservations(reservations) {
    const container = document.getElementById('reservations-list');
    container.innerHTML = '';
    
    reservations.forEach(reservation => {
        const checkInDate = new Date(reservation.checkIn);
        const checkOutDate = new Date(reservation.checkOut);
        const formattedCheckIn = checkInDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
        const formattedCheckOut = checkOutDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
        
        const nights = Math.round((checkOutDate - checkInDate) / (1000 * 60 * 60 * 24));
        
        const reservationCard = document.createElement('div');
        reservationCard.className = 'card reservation-card mb-3';
        reservationCard.innerHTML = `
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <h5 class="card-title mb-0">${reservation.hotelName}</h5>
                    <span class="reservation-status status-${reservation.status}">${reservation.status}</span>
                </div>
                <p class="card-text"><strong>Confirmation:</strong> ${reservation.id}</p>
                <p class="card-text"><strong>Room:</strong> ${reservation.roomType} (${reservation.guests} guests)</p>
                <p class="card-text"><strong>Check-in:</strong> ${formattedCheckIn}</p>
                <p class="card-text"><strong>Check-out:</strong> ${formattedCheckOut} (${nights} nights)</p>
                <p class="card-text"><strong>Total:</strong> ${reservation.totalPrice}</p>
                <button class="btn btn-sm btn-outline-primary view-details-btn" data-reservation-id="${reservation.id}">View Details</button>
            </div>
        `;
        
        container.appendChild(reservationCard);
    });
    
    // Add event listeners to the view details buttons
    document.querySelectorAll('.view-details-btn').forEach(button => {
        button.addEventListener('click', function() {
            const reservationId = this.getAttribute('data-reservation-id');
            viewReservationDetails(reservationId);
        });
    });
}

// Function to view reservation details
function viewReservationDetails(reservationId) {
    // In a real app, you would fetch detailed information about this reservation
    // For now, we'll just add a message to the chat
    const reservation = sampleReservations.find(res => res.id === reservationId);
    if (reservation) {
        addMessage(`I'd like more information about my reservation at ${reservation.hotelName} (${reservationId})`, 'user');
        
        // Simulate AI response
        setTimeout(() => {
            addMessage(`I found your reservation at ${reservation.hotelName}. You're checking in on ${reservation.checkIn} and checking out on ${reservation.checkOut}. Your room type is ${reservation.roomType} for ${reservation.guests} guests. The total price is ${reservation.totalPrice}. How can I help you with this reservation?`, 'ai');
        }, 1000);
    }
}

// Initialize chat functionality
function initializeChat() {
    const chatInput = document.getElementById('chat-input');
    const sendButton = document.getElementById('send-message');
    const recordButton = document.getElementById('record-message'); // Get Mic button
    
    // Send message when button is clicked
    sendButton.addEventListener('click', sendMessage);
    
    // Send message when Enter key is pressed
    chatInput.addEventListener('keypress', function(event) {
        if (event.key === 'Enter') {
            sendMessage();
        }
    });
    
    // --- Speech Recognition Event Setup ---
    if (recognition && recordButton) {
        recordButton.addEventListener('click', toggleRecording);

        recognition.onresult = (event) => {
            const transcript = event.results[event.results.length - 1][0].transcript.trim();
            console.log('Speech recognized:', transcript);
            chatInput.value = transcript; // Put recognized text in input box
            // Optionally, send message immediately after recognition:
            // sendMessage(); 
        };

        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            addMessage(`Speech recognition error: ${event.error}`, 'system');
            stopRecordingVisuals(recordButton, chatInput);
        };

        recognition.onend = () => {
            console.log('Speech recognition ended.');
            stopRecordingVisuals(recordButton, chatInput);
        };
        
        recordButton.disabled = false; // Enable button if API is supported
    } else if (recordButton) {
        console.warn("Speech Recognition not supported by this browser.");
        recordButton.disabled = true;
        recordButton.title = "Speech Recognition not supported";
    }
    // ------------------------------------
}

// --- Speech Recognition Control Functions ---
function toggleRecording() {
    if (!recognition) return;
    
    const recordButton = document.getElementById('record-message');
    const chatInput = document.getElementById('chat-input');

    if (isRecording) {
        recognition.stop();
        // Visuals are handled by onend/onerror
    } else {
        try {
            recognition.start();
            console.log('Speech recognition started.');
            isRecording = true;
            recordButton.classList.add('btn-danger'); // Change color to red
            recordButton.classList.remove('btn-secondary');
            recordButton.innerHTML = '<i class="fas fa-stop"></i>'; // Change icon to stop
            recordButton.title = "Stop Recording";
            chatInput.placeholder = "Listening...";
            chatInput.disabled = true; // Disable text input while listening
        } catch (error) {
            console.error("Error starting speech recognition:", error);
            addMessage("Could not start voice recording. Please check microphone permissions.", 'system');
            isRecording = false; // Reset state
        }
    }
}

function stopRecordingVisuals(recordButton, chatInput) {
    isRecording = false;
    if (recordButton) {
        recordButton.classList.remove('btn-danger');
        recordButton.classList.add('btn-secondary');
        recordButton.innerHTML = '<i class="fas fa-microphone"></i>';
         recordButton.title = "Record Message";
    }
    if (chatInput) {
        chatInput.placeholder = "Type your message here...";
        chatInput.disabled = false;
    }
}
// -----------------------------------------

// Function to send message
function sendMessage() {
    const chatInput = document.getElementById('chat-input');
    const message = chatInput.value.trim();
    
    if (message) {
        // Add user message to chat
        addMessage(message, 'user');
        
        // Clear input field
        chatInput.value = '';
        
        // Show typing indicator
        const typingIndicator = document.createElement('div');
        typingIndicator.className = 'chat-message ai-message typing-indicator';
        typingIndicator.innerHTML = '<p><em>Guestrix is typing...</em></p>';
        document.getElementById('chat-messages').appendChild(typingIndicator);
        
        // Get the user's ID token for authentication
        firebase.auth().currentUser.getIdToken(true)
            .then(idToken => {
                // Send message to backend with authentication
                return fetch('/api/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${idToken}`
                    },
                    body: JSON.stringify({ message: message }),
                });
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to get response from Guestrix');
                }
                return response.json();
            })
            .then(data => {
                // Remove typing indicator
                document.getElementById('chat-messages').removeChild(typingIndicator);
                
                // Add AI response to chat and speak it
                addMessage(data.response, 'ai');
                
                // If there are suggested actions, display them
                if (data.suggestedActions && data.suggestedActions.length > 0) {
                    addSuggestedActions(data.suggestedActions);
                }
                
                // Temporarily commented out text-to-speech for text chat to fix ReferenceError
                /*
                // Speak the AI response if API is available
                if (synthesis && data.response) {
                    speakText(data.response);
                }
                */
            })
            .catch(error => {
                console.error('Error:', error);
                // Remove typing indicator
                if (typingIndicator.parentNode) {
                    document.getElementById('chat-messages').removeChild(typingIndicator);
                }
                addMessage('Sorry, I encountered an error processing your request: ' + error.message, 'ai');
            });
    }
}

// Function to add suggested actions to the chat
function addSuggestedActions(actions) {
    const actionsContainer = document.createElement('div');
    actionsContainer.className = 'suggested-actions';
    
    actions.forEach(action => {
        const actionButton = document.createElement('button');
        actionButton.className = 'btn btn-sm btn-outline-primary me-2 mb-2';
        actionButton.textContent = action;
        actionButton.addEventListener('click', () => {
            // When clicked, send this as a message
            document.getElementById('chat-input').value = action;
            sendMessage();
        });
        actionsContainer.appendChild(actionButton);
    });
    
    const chatMessages = document.getElementById('chat-messages');
    chatMessages.appendChild(actionsContainer);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Function to add message to chat
function addMessage(message, sender) {
    const chatMessages = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${sender}-message`;
    
    const messageText = document.createElement('p');
    messageText.textContent = message;
    
    messageDiv.appendChild(messageText);
    chatMessages.appendChild(messageDiv);
    
    // --- Speak AI messages --- 
    // Note: We trigger speech from sendMessage after receiving the response,
    // ensuring it speaks only the final AI message.
    // if (sender === 'ai' && synthesis && message) {
    //     speakText(message);
    // } 
    // ------------------------

    // Scroll to bottom of chat
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// --- Text-to-Speech Function ---
function speakText(text) {
    if (!synthesis || !text) {
        console.warn('Speech synthesis not available or text is empty.');
        return;
    }
    // Cancel any previous speech
    synthesis.cancel(); 
    
    const utterance = new SpeechSynthesisUtterance(text);
    // Optional: configure voice, rate, pitch
    // utterance.voice = synthesis.getVoices().find(voice => voice.lang === 'en-US'); 
    // utterance.rate = 1; 
    // utterance.pitch = 1; 

    utterance.onerror = (event) => {
        console.error('Speech synthesis error:', event.error);
        addMessage(`Speech synthesis error: ${event.error}`, 'system');
    };
    
    synthesis.speak(utterance);
}
// -----------------------------

// --- Voice Call Functions ---

function initSocketIO() {
    // Connect to the Socket.IO server
    // The server URL will be the same origin by default
    socket = io({ autoConnect: false }); // Don't connect automatically

    socket.on('connect', () => {
        console.log('Socket.IO connected successfully:', socket.id);
        // Update UI or state to reflect connection
        updateVoiceCallStatus("Connected, ready.");
    });

    socket.on('disconnect', (reason) => {
        console.log('Socket.IO disconnected:', reason);
        updateVoiceCallStatus("Disconnected.");
        // Handle disconnection, maybe attempt reconnection or clean up
        if (isVoiceCallActive) {
            stopVoiceCall(false); // Stop call if active, don't emit stop_stream again
        }
    });

    socket.on('connect_error', (error) => {
        console.error('Socket.IO connection error:', error);
        updateVoiceCallStatus("Connection Error.");
        // Handle connection error, maybe show an error message to the user
    });

    socket.on('auth_error', (data) => {
        console.error('Socket.IO authentication error:', data.message);
        updateVoiceCallStatus("Authentication Failed.");
        alert("Voice call authentication failed. Please ensure you are logged in.");
        // Prevent further voice call attempts until re-authenticated?
    });

    socket.on('connection_success', (data) => {
        console.log("Backend confirmation:", data.message);
    });

    // --- Stream Lifecycle Events ---
    socket.on('stream_started', (data) => {
        console.log('Voice stream started:', data.message);
        updateVoiceCallStatus("Streaming audio...");
        isVoiceCallActive = true;
        // Update button text/state
        const voiceCallButton = document.getElementById('start-voice-call');
        if(voiceCallButton) {
            voiceCallButton.textContent = 'Stop Voice Call';
            voiceCallButton.classList.remove('btn-success');
            voiceCallButton.classList.add('btn-danger');
        }
    });

    socket.on('stream_stopping', (data) => {
        console.log('Voice stream stopping:', data.message);
        updateVoiceCallStatus("Stopping stream...");
    });

    socket.on('stream_ended', (data) => {
        console.log('Voice stream ended:', data.message);
        updateVoiceCallStatus("Call ended.");
        stopVoiceCall(false); // Ensure cleanup on client side
    });

    socket.on('stream_error', (data) => {
        console.error('Voice stream error:', data.message);
        updateVoiceCallStatus(`Error: ${data.message}`);
        stopVoiceCall(false); // Stop call on error
        alert(`Voice Call Error: ${data.message}`);
    });

    // --- Dialogflow Interaction Events ---
    socket.on('speech_recognized', (data) => {
        console.log('Speech Recognized:', data);
        // Display the transcript (interim or final)
        displayVoiceTranscript(data.transcript, data.is_final);
    });

    socket.on('agent_response', (data) => {
        console.log('Agent Response:', data);
        // Display the agent's text response in the chat or a dedicated area
        appendMessage(data.text, 'ai-message'); // Reuse chat display for now
        // Optionally speak the response using Text-to-Speech
        // speakText(data.text);
    });

    // Connect now that handlers are set up
    socket.connect();
}

async function startVoiceCall() {
    if (isVoiceCallActive) {
        console.log("Call already active, stopping...");
        stopVoiceCall(true); // Request server to stop
        return;
    }

    if (!socket || !socket.connected) {
        console.error("Socket not connected. Cannot start voice call.");
        updateVoiceCallStatus("Not Connected.");
        alert("Connection error. Please wait or try refreshing the page.");
        return;
    }

    console.log("Attempting to start voice call...");
    updateVoiceCallStatus("Starting call...");

    try {
        // 1. Get Microphone Access
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        console.log("Microphone access granted.");

        // 2. Create AudioContext if it doesn't exist
        if (!audioContext) {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            console.log("AudioContext created.");
        }

        // Ensure AudioContext is running (might start suspended)
        if (audioContext.state === 'suspended') {
            console.log("AudioContext is suspended, attempting to resume...");
            await audioContext.resume();
            console.log("AudioContext state after resume:", audioContext.state);
        }
        if (audioContext.state !== 'running') {
            console.error("AudioContext could not be started or resumed. State:", audioContext.state);
            updateVoiceCallStatus("Error: Audio context issue");
            stopVoiceCall(); // Clean up
            return;
        }

        console.log("AudioContext sample rate:", audioContext.sampleRate);

        mediaStreamSource = audioContext.createMediaStreamSource(micStream);
        console.log("Created MediaStreamSource node.");

        // Use a buffer size that's a power of 2 (e.g., 4096)
        const bufferSize = 4096;
        // Deprecated, but necessary for wider browser compatibility for now
        scriptProcessor = audioContext.createScriptProcessor(bufferSize, 1, 1); 
        console.log("Created ScriptProcessorNode.");

        scriptProcessor.onaudioprocess = processAudio;
        console.log("Assigned processAudio to onaudioprocess.");

        mediaStreamSource.connect(scriptProcessor);
        console.log("Connected sourceNode to scriptProcessorNode.");

        // DO NOT connect scriptProcessorNode to destination - we only want to process, not playback
        // scriptProcessorNode.connect(audioContext.destination);
        // console.log("Connected scriptProcessorNode to destination."); // Removed this line

        console.log("Audio processing pipeline set up.");

        // 4. Inform server to start the stream
        socket.emit('start_stream', { audio: { sampleRateHertz: TARGET_SAMPLE_RATE } });
        console.log("'start_stream' event emitted.");

    } catch (error) {
        console.error("Error starting voice call:", error);
        updateVoiceCallStatus("Mic/Setup Error.");
        if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
            alert("Microphone access denied. Please allow microphone access in your browser settings.");
        } else {
            alert(`Error starting voice call: ${error.message}`);
        }
        // Clean up any partial setup
        stopVoiceCall(false);
    }
}

function stopVoiceCall(emitStopToServer) {
    console.log(`Stopping voice call. Emit to server: ${emitStopToServer}`);
    isVoiceCallActive = false;

    // 1. Stop microphone track
    if (micStream) {
        micStream.getTracks().forEach(track => track.stop());
        micStream = null;
        console.log("Microphone stream stopped.");
    }

    // 2. Disconnect audio nodes
    if (mediaStreamSource) {
        mediaStreamSource.disconnect();
        mediaStreamSource = null;
    }
    if (scriptProcessor) {
        scriptProcessor.disconnect();
        scriptProcessor.onaudioprocess = null; // Remove handler
        scriptProcessor = null;
    }

    // 3. Close AudioContext
    if (audioContext && audioContext.state !== 'closed') {
        audioContext.close().then(() => console.log("AudioContext closed."));
        audioContext = null;
    }

    // 4. Clear audio buffer
    audioBuffer = [];

    // 5. Tell server to stop (if initiated by user action)
    if (emitStopToServer && socket && socket.connected) {
        socket.emit('stop_stream');
        console.log("'stop_stream' event emitted.");
    }

    // 6. Update UI
    updateVoiceCallStatus("Call ended.");
    const voiceCallButton = document.getElementById('start-voice-call');
    if(voiceCallButton) {
        voiceCallButton.textContent = 'Start Voice Call';
        voiceCallButton.classList.remove('btn-danger');
        voiceCallButton.classList.add('btn-success');
    }
    clearVoiceTranscriptDisplay(); // Clear any lingering transcript
}

// Audio Processing Function
function processAudio(audioProcessingEvent) {
    if (!isVoiceCallActive || !socket || !socket.connected) {
        return; // Don't process if call is not active or socket disconnected
    }

    const inputBuffer = audioProcessingEvent.inputBuffer;
    const inputData = inputBuffer.getChannelData(0); // Get data from the first channel
    const sourceSampleRate = audioContext.sampleRate;

    // Downsample audio data
    const downsampledData = downsampleBuffer(inputData, sourceSampleRate, TARGET_SAMPLE_RATE);

    // Convert Float32Array to Int16Array (LINEAR16)
    const outputData = convertFloat32ToInt16(downsampledData);

    // Send the Int16Array buffer directly
    // Socket.IO automatically handles ArrayBuffer/TypedArray transmission
    if (outputData.length > 0) {
       // console.log(`Sending audio chunk, size: ${outputData.byteLength}`); // Verbose
        socket.emit('audio_chunk', outputData.buffer);
    }
}

// --- Helper Functions ---

// Basic downsampling (linear interpolation)
function downsampleBuffer(buffer, inputSampleRate, outputSampleRate) {
    if (inputSampleRate === outputSampleRate) {
        return buffer;
    }
    const sampleRateRatio = inputSampleRate / outputSampleRate;
    const newLength = Math.round(buffer.length / sampleRateRatio);
    const result = new Float32Array(newLength);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < result.length) {
        const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
        let accum = 0, count = 0;
        for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
            accum += buffer[i];
            count++;
        }
        result[offsetResult] = accum / count;
        offsetResult++;
        offsetBuffer = nextOffsetBuffer;
    }
    return result;
}

// Convert Float32 range [-1.0, 1.0] to Int16 range [-32768, 32767]
function convertFloat32ToInt16(buffer) {
    let l = buffer.length;
    const buf = new Int16Array(l);
    while (l--) {
        buf[l] = Math.min(1, buffer[l]); // Clamp max
        buf[l] = Math.max(-1, buf[l]); // Clamp min
        buf[l] = buf[l] < 0 ? buf[l] * 0x8000 : buf[l] * 0x7FFF;
    }
    return buf;
}

function updateVoiceCallStatus(message) {
    // TODO: Find a place in the HTML to display this status
    // Example: document.getElementById('voice-status').textContent = message;
    console.log("Voice Status:", message); // Log status for now
    // For simplicity, adding a temporary status display below the button
    let statusEl = document.getElementById('voice-call-status-display');
    const voiceButton = document.getElementById('start-voice-call');
    if (!statusEl && voiceButton) {
        statusEl = document.createElement('div');
        statusEl.id = 'voice-call-status-display';
        statusEl.className = 'text-muted mt-1 small';
        voiceButton.parentNode.insertBefore(statusEl, voiceButton.nextSibling);
    }
    if (statusEl) {
        statusEl.textContent = message;
    }
}

function displayVoiceTranscript(transcript, isFinal) {
    // TODO: Find a place to display the transcript (interim/final)
    // Example: document.getElementById('voice-transcript').textContent = transcript;
    console.log(`Transcript (${isFinal ? 'Final' : 'Interim'}): ${transcript}`);
    // Using the chat input field temporarily for transcript display
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
         chatInput.value = transcript; // Overwrite input field with transcript
         // Could also display in a dedicated area above or below the chat
    }
     // Maybe add to chat window if final?
     // if (isFinal && transcript.trim()) {
     //     appendMessage(transcript, 'user-message');
     // }
}

function clearVoiceTranscriptDisplay() {
     const chatInput = document.getElementById('chat-input');
    if (chatInput) {
         chatInput.value = '';
    }
    // Clear any other dedicated transcript area if used
}

// Optional: Text-to-speech function
/*
function speakText(text) {
    if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        // Configure voice, pitch, rate if needed
        // utterance.voice = speechSynthesis.getVoices().find(voice => voice.lang === 'en-US');
        speechSynthesis.speak(utterance);
    } else {
        console.warn("Browser does not support Speech Synthesis.");
    }
}
*/

// -----------------------------

// Initialize when the DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log("Dashboard DOM loaded");

    // Call initialization functions
    initializeChat();
    
    // We will call loadReservations or loadProperties based on user role later
    // For now, loadReservations is called within the auth listener if needed
});

// Modify the auth state listener to call the appropriate function
firebase.auth().onAuthStateChanged(user => {
    if (user) {
        console.log('User authenticated in dashboard.js, initializing dashboard features');
        user.getIdToken().then(idToken => {
            // Store token if needed, maybe for subsequent API calls
            sessionStorage.setItem('firebaseIdToken', idToken);
            // Determine if we are on host or guest dashboard and call relevant load function
            if (document.getElementById('reservations-container')) {
                loadReservations(user.uid); // Load reservations if guest elements are present
            } else if (document.getElementById('properties-list-container')) {
                // TODO: Call a function to load properties for the host dashboard
                console.log('Need to implement loadProperties for host dashboard.');
            }
        });
    } else {
        console.log('User not authenticated in dashboard.js');
        // Handle unauthenticated state if needed, though @login_required should prevent this page view
    }
});

// Only add event listener if the button exists
const startVoiceCallButton = document.getElementById('start-voice-call');
if (startVoiceCallButton) {
    startVoiceCallButton.addEventListener('click', () => {
        console.log('Start voice call button clicked');
        // Add logic to initiate the voice call
        // This might involve signaling the backend via Socket.IO
        alert('Voice call feature not yet implemented.');
    });
} else {
    console.log('Voice call button not found');
}
