/*
 * Voice Call functionality for the guest dashboard
 */

import {
    confirmedPropertyId,
    getConfirmedPropertyId,
    addMessageToChat,
    fetchPropertyDetails,
    fetchPropertyKnowledgeItems,
    createSharedSystemPrompt,
    dashboardState
} from './guest_dashboard_utils.js';

import { processJsonMessage } from './guest_dashboard_main.js';

// Constants for audio processing
const GEMINI_OUTPUT_SAMPLE_RATE = 24000;  // Gemini audio is 24kHz
const MIC_BUFFER_SIZE = 4096;  // Size of microphone audio buffer
const GEMINI_MODEL = "gemini-2.5-flash"; // The model to use for text chat
const GEMINI_LIVE_MODEL = "gemini-live-2.5-flash-preview"; 
const GEMINI_API_VERSION = "v1beta"; // The API version required for Live API
const GEMINI_VOICES = ["Aoede", "Chorister", "Dawnsmell", "Hearth", "Joyishness", "Jurai", "Patzelt", "Shiralish", "Orus"];
const GEMINI_DEFAULT_VOICE = "Aoede";  // Default voice to use
const MAX_AUDIO_QUEUE_LENGTH = 60;  // Maximum number of chunks to keep in the audio queue (increased from 30)
const AUDIO_INITIAL_BUFFER_COUNT = 3;  // Number of chunks to buffer before playing (reduced from 5 for quicker start)

// Noise management constants
const NOISE_LEVEL_THRESHOLD = 0.15;  // Threshold for detecting noisy environment
const NOISE_SAMPLES_COUNT = 10;  // Number of samples to analyze for noise level
const INTERRUPTION_THRESHOLD = 3;  // Number of interruptions before suggesting text chat
const NOISE_ANALYSIS_INTERVAL = 2000;  // Analyze noise every 2 seconds

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

// Noise management variables
let noiseLevels = [];
let currentNoiseLevel = 0;
let interruptionCount = 0;
let isNoisyEnvironment = false;
let noiseAnalysisTimer = null;
let hasOfferedTextChat = false;
let lastNoiseWarning = 0;

// Connection quality monitoring variables
let isPoorConnection = false;
let connectionMonitorTimer = null;
let lastConnectionWarningTime = 0;

function isConnectionSufficientForVoice() {
    return !isPoorConnection;
}

async function evaluateConnectionQuality() {
    try {
        const navConn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
        const effectiveType = navConn?.effectiveType || 'unknown';
        const rtt = typeof navConn?.rtt === 'number' ? navConn.rtt : null;
        const downlink = typeof navConn?.downlink === 'number' ? navConn.downlink : null; // Mbps

        // Optional: active latency probe via diagnostics helper
        let probeLatencyMs = null;
        if (window.VoiceCallDiagnostics && typeof window.VoiceCallDiagnostics.assessNetworkQuality === 'function') {
            try {
                const probe = await window.VoiceCallDiagnostics.assessNetworkQuality();
                if (probe && typeof probe.latency === 'number') {
                    probeLatencyMs = probe.latency;
                }
            } catch (e) {
                // ignore probe failures
            }
        }

        // Heuristics for poor connection
        const poorByType = effectiveType === 'slow-2g' || effectiveType === '2g';
        const poorByRtt = rtt !== null && rtt >= 1000; // 1s+
        const poorByDownlink = downlink !== null && downlink < 0.15; // < 0.15 Mbps
        const poorByProbe = probeLatencyMs !== null && probeLatencyMs >= 1500; // 1.5s+

        const wasPoor = isPoorConnection;
        isPoorConnection = !!(poorByType || poorByRtt || poorByDownlink || poorByProbe);

        if (wasPoor !== isPoorConnection) {
            console.log(`[VoiceCall] Connection quality changed: poor=${isPoorConnection} (type=${effectiveType}, rtt=${rtt}, downlink=${downlink}, probe=${probeLatencyMs})`);
            // Update button readiness immediately
            try { checkVoiceCallReadiness(); } catch (e) {}

            // Notify user and suggest text chat when it becomes poor
            if (isPoorConnection) {
                const now = Date.now();
                if (now - lastConnectionWarningTime > 60000) { // rate-limit warnings to 60s
                    addMessageToChat("Your internet connection looks unstable. For a smoother experience, please use text chat below.", "ai");
                    lastConnectionWarningTime = now;
                }
            }
        }
    } catch (e) {
        console.warn('[VoiceCall] Failed to evaluate connection quality:', e);
    }
}

function startConnectionMonitoring() {
    if (connectionMonitorTimer) return;
    // Initial evaluation
    evaluateConnectionQuality();
    // Periodic checks
    connectionMonitorTimer = setInterval(evaluateConnectionQuality, 7000);
    // React to browser-reported changes
    const navConn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (navConn && typeof navConn.addEventListener === 'function') {
        navConn.addEventListener('change', evaluateConnectionQuality);
    }
    console.log('[VoiceCall] Started connection quality monitoring');
}

function stopConnectionMonitoring() {
    if (connectionMonitorTimer) {
        clearInterval(connectionMonitorTimer);
        connectionMonitorTimer = null;
    }
    const navConn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (navConn && typeof navConn.removeEventListener === 'function') {
        try { navConn.removeEventListener('change', evaluateConnectionQuality); } catch (_) {}
    }
}

// === Microphone mute control ===
let isMicMuted = false;

function setMicrophoneMuted(shouldMute) {
    isMicMuted = !!shouldMute;
    try {
        if (microphoneStream && microphoneStream.getAudioTracks) {
            microphoneStream.getAudioTracks().forEach(track => {
                track.enabled = !isMicMuted;
            });
        }
    } catch (e) {
        console.warn('Failed to toggle mic track enabled state:', e);
    }

    // Update UI state
    const muteBtn = document.getElementById('mute-mic-button');
    if (muteBtn) {
        muteBtn.setAttribute('aria-pressed', String(isMicMuted));
        const iconOn = muteBtn.querySelector('.icon-mic');
        const iconOff = muteBtn.querySelector('.icon-mic-off');
        const textSpan = muteBtn.querySelector('.mute-text');
        if (iconOn && iconOff && textSpan) {
            if (isMicMuted) {
                iconOn.classList.add('hidden');
                iconOff.classList.remove('hidden');
                textSpan.textContent = 'Unmute';
                muteBtn.classList.add('bg-bittersweet');
                muteBtn.classList.remove('bg-dark-purple');
                muteBtn.title = 'Unmute microphone';
            } else {
                iconOn.classList.remove('hidden');
                iconOff.classList.add('hidden');
                textSpan.textContent = 'Mute';
                muteBtn.classList.add('bg-dark-purple');
                muteBtn.classList.remove('bg-bittersweet');
                muteBtn.title = 'Mute microphone';
            }
        }
    }
}

function toggleMuteMicrophone() {
    setMicrophoneMuted(!isMicMuted);
}

// Keep window.GUEST_NAME in sync when profile updates without reload
window.addEventListener('guest-name-updated', (e) => {
    if (e && e.detail && e.detail.name) {
        window.GUEST_NAME = e.detail.name;
        console.log('[voice_call] GUEST_NAME updated via event:', e.detail.name);
    }
});

// Current voice and language - use stored preference or default
let currentGeminiVoice = localStorage.getItem('geminiVoicePreference') || "Aoede";
let currentGeminiLanguage = localStorage.getItem('geminiLanguagePreference') || "en-US";

// Function to get language-appropriate greeting message, now personalized
function getGreetingMessage(language = currentGeminiLanguage) {
    const guestName = window.GUEST_NAME || 'the guest'; // Fallback name
    
    // Don't provide the name if it's generic - let the system prompt handle asking for it
    const isGenericName = guestName === 'Guest' || guestName === 'the guest';
    
    const greetings = {
        'en-US': isGenericName ? `Hello! Please greet me briefly.` : `Hello, my name is ${guestName}. Please greet me by name very briefly!`,
        'es-US': isGenericName ? `¡Hola! Por favor, salúdame brevemente.` : `¡Hola, mi nombre es ${guestName}. Por favor, salúdame por mi nombre muy brevemente!`,
        'es-ES': isGenericName ? `¡Hola! Por favor, salúdame brevemente.` : `¡Hola, mi nombre es ${guestName}. Por favor, salúdame por mi nombre muy brevemente!`,
        'fr-FR': isGenericName ? `Bonjour ! S'il vous plaît, saluez-moi brièvement.` : `Bonjour, je m'appelle ${guestName}. S'il vous plaît, saluez-moi par mon nom très brièvement !`,
        'fr-CA': isGenericName ? `Bonjour ! S'il vous plaît, saluez-moi brièvement.` : `Bonjour, je m'appelle ${guestName}. S'il vous plaît, saluez-moi par mon nom très brièvement !`,
        'de-DE': isGenericName ? `Hallo! Bitte begrüßen Sie mich kurz.` : `Hallo, mein Name ist ${guestName}. Bitte begrüßen Sie mich sehr kurz mit meinem Namen!`,
        'it-IT': isGenericName ? `Ciao! Per favore, salutami brevemente.` : `Ciao, il mio nome è ${guestName}. Per favore, salutami per nome molto brevemente!`,
        'pt-BR': isGenericName ? `Olá! Por favor, cumprimente-me brevemente.` : `Olá, meu nome é ${guestName}. Por favor, cumprimente-me pelo nome de forma muito breve!`,
        'nl-NL': isGenericName ? `Hallo! Begroet me alsjeblieft kort.` : `Hallo, mijn naam is ${guestName}. Begroet me alsjeblieft heel kort bij naam!`,
        'pl-PL': isGenericName ? `Cześć! Proszę, przywitaj się ze mną krótko.` : `Cześć, mam na imię ${guestName}. Proszę, przywitaj się ze mną po imieniu bardzo krótko!`,
        'ru-RU': isGenericName ? `Привет! Пожалуйста, поздоровайся со мной кратко.` : `Привет, меня зовут ${guestName}. Пожалуйста, поздоровайся со мной по имени очень кратко!`,
        'ja-JP': isGenericName ? `こんにちは！簡潔に挨拶してください。` : `こんにちは、私の名前は${guestName}です。私の名前で簡潔に挨拶してください！`,
        'ko-KR': isGenericName ? `안녕하세요! 간단하게 인사해 주세요.` : `안녕하세요, 제 이름은 ${guestName}입니다. 제 이름으로 아주 간단하게 인사해 주세요!`,
        'cmn-CN': isGenericName ? `你好！请简短地向我问好。` : `你好，我的名字是${guestName}。请用我的名字非常简短地向我问好！`,
        'ar-XA': isGenericName ? `مرحباً! من فضلك، رحب بي باختصار.` : `مرحباً، اسمي ${guestName}. من فضلك، رحب بي باسمي باختصار شديد!`,
        'hi-IN': isGenericName ? `नमस्ते! कृपया संक्षेप में अभिवादन करें।` : `नमस्ते, मेरा नाम ${guestName} है। कृपया मेरे नाम से बहुत संक्षेप में अभिवादन करें!`,
        'th-TH': isGenericName ? `สวัสดีครับ/ค่ะ! กรุณาทักทายสั้นๆ` : `สวัสดีครับ/ค่ะ ผม/ดิฉันชื่อ ${guestName} ครับ/ค่ะ กรุณาทักทายผม/ดิฉันด้วยชื่อสั้นๆ!`,
        'vi-VN': isGenericName ? `Xin chào! Vui lòng chào một cách ngắn gọn.` : `Xin chào, tôi tên là ${guestName}. Vui lòng chào tôi bằng tên một cách rất ngắn gọn!`,
        'id-ID': isGenericName ? `Halo! Tolong sapa saya dengan singkat.` : `Halo, nama saya ${guestName}. Tolong sapa saya dengan nama saya dengan sangat singkat!`,
        'tr-TR': isGenericName ? `Merhaba! Lütfen beni kısa bir şekilde selamlayın.` : `Merhaba, benim adım ${guestName}. Lütfen beni ismimle çok kısa bir şekilde selamlayın!`
    };
    
    const selectedGreeting = greetings[language] || greetings['en-US'];
    console.log(`[GREETING DEBUG] Guest name: '${guestName}', isGeneric: ${isGenericName}, language: ${language}`);
    console.log(`[GREETING DEBUG] Selected greeting: '${selectedGreeting}'`);
    
    return selectedGreeting;
}

// Transcription accumulation variables
let currentAITranscription = "";
let currentUserTranscription = "";
let aiTranscriptionTimeout = null;
let userTranscriptionTimeout = null;
const TRANSCRIPTION_TIMEOUT = 5000; // 5 seconds to accumulate fragments

// Voice conversation management
let voiceConversationId = null;
let voiceSessionActive = false;
// Session resumption handle provided by Gemini Live API
let sessionResumptionHandle = null;

// Voice call diagnostics
let voiceCallDiagnostics = null;

// Make sure the voice selector dropdown is initialized
window.addEventListener('DOMContentLoaded', () => {
    // Expose our voice preference
    window.GEMINI_VOICE = currentGeminiVoice;
    console.log(`Using Gemini voice: ${currentGeminiVoice}`);
    console.log(`Using Gemini language: ${currentGeminiLanguage}`);
    
    // Load user's language preference from profile
    loadUserLanguagePreference();
});

// Function to load user's language preference from their profile
async function loadUserLanguagePreference() {
    try {
        const response = await fetch('/api/user/profile', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        if (response.ok) {
            const data = await response.json();
            if (data.success && data.user && data.user.language) {
                let userLanguage = data.user.language;
                
                // Handle backward compatibility for old language codes
                if (userLanguage === 'zh-CN') {
                    userLanguage = 'cmn-CN';
                    console.log('Updated user language preference from zh-CN to cmn-CN for Live API compatibility');
                }
                
                currentGeminiLanguage = userLanguage;
                localStorage.setItem('geminiLanguagePreference', currentGeminiLanguage);
                console.log(`Updated language preference from user profile: ${currentGeminiLanguage}`);
            }
        }
    } catch (error) {
        console.warn('Failed to load language preference from profile:', error);
        // Keep the default or localStorage value
    }
}

// Function to update voice language preference (called from profile modal)
window.updateVoiceLanguagePreference = function(newLanguage) {
    console.log('Updating voice language preference from profile change:', newLanguage);
    
    // Handle backward compatibility for old language codes
    if (newLanguage === 'zh-CN') {
        newLanguage = 'cmn-CN';
        console.log('Updated language preference from zh-CN to cmn-CN for Live API compatibility');
    }
    
    currentGeminiLanguage = newLanguage;
    localStorage.setItem('geminiLanguagePreference', currentGeminiLanguage);
    
    console.log('Voice call system language updated to:', currentGeminiLanguage);
    
    // If there's an active voice call, we might want to inform the user that the language change will take effect on the next call
    if (currentCallState === 'active') {
        console.log('Note: Language change will take effect on the next voice call session');
    }
};

// Function to update voice guest name (called from profile modal)
window.updateVoiceGuestName = function(newGuestName) {
    console.log('Updating voice guest name from profile change:', newGuestName);
    
    // Update the window variable that's used in system prompts
    window.GUEST_NAME = newGuestName;
    
    // Update dashboard state if available
    if (window.dashboardState) {
        window.dashboardState.guestName = newGuestName;
        window.dashboardState.guestNameSource = 'user-profile';
    }
    
    console.log('Voice call system guest name updated to:', newGuestName);
    
    // If there's an active voice call, we might want to inform the user that the name change will take effect on the next call
    if (currentCallState === 'active') {
        console.log('Note: Guest name change will take effect on the next voice call session');
    }
};

// Function to pre-process transcript text for foreign language symbols
function preprocessTranscript(text, targetLanguage = currentGeminiLanguage) {
        // Handle backward compatibility for old language codes FIRST
    let normalizedLanguage = targetLanguage === 'zh-CN' ? 'cmn-CN' : targetLanguage;

    // Languages where prior filtering led to excessive masking – skip regex entirely
    const bypassLanguages = ['pt-BR', 'ja-JP', 'ko-KR', 'cmn-CN', 'th-TH'];

    if (bypassLanguages.includes(normalizedLanguage)) {
        return text;
    }
    if (!text || typeof text !== 'string') {
        return text;
    }

    // Do not process text that looks like a model-inserted tag
    if (text.startsWith('<') && text.endsWith('>')) {
        return text;
    }

    // Define character sets for different languages with expanded punctuation
    // Added common symbols: / % ^ @ # * & _ = + [ ] { } | \ ~ $ ` €
    const languageCharacterSets = {
        // English
        'en-US': /[a-zA-Z0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'en-GB': /[a-zA-Z0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'en-CA': /[a-zA-Z0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'en-AU': /[a-zA-Z0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        
        // Spanish variants
        'es-ES': /[a-zA-ZñÑáéíóúüÁÉÍÓÚÜ0-9\s.,!?;:'"()\-–—¿¡<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'es-US': /[a-zA-ZñÑáéíóúüÁÉÍÓÚÜ0-9\s.,!?;:'"()\-–—¿¡<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        
        // French variants
        'fr-FR': /[a-zA-ZàâäéèêëïîôùûüÿçÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'fr-CA': /[a-zA-ZàâäéèêëïîôùûüÿçÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        
        // Other European languages
        'de-DE': /[a-zA-ZäöüßÄÖÜ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'it-IT': /[a-zA-ZàèéìîïòóùúÀÈÉÌÎÏÒÓÙÚ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'pt-BR': /[a-zA-ZàáâãéêíîóôõúçÀÁÂÃÉÊÍÎÓÔÕÚÇ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'nl-NL': /[a-zA-Z0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'pl-PL': /[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'ru-RU': /[a-zA-ZёЁ0-9\s.,!?;:'"()\-–—\u0400-\u04ff<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        
        // Asian languages
        'ja-JP': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf\uff65-\uff9f<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'ko-KR': /[a-zA-Z0-9\s.,!?;:'"()\-–—\uac00-\ud7af\u1100-\u11ff\u3130-\u318f<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'cmn-CN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u4e00-\u9fff\u3400-\u4dbf\u20000-\u2a6df\u2a700-\u2b73f\u2b740-\u2b81f\u2b820-\u2ceaf\uf900-\ufaff\u2f800-\u2fa1f<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        
        // Middle Eastern and South Asian languages
        'ar-XA': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'hi-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0900-\u097f<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        
        // Indian languages
        'bn-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0980-\u09ff<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,  // Bengali
        'gu-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0a80-\u0aff<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,  // Gujarati
        'kn-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0c80-\u0cff<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,  // Kannada
        'mr-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0900-\u097f<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,  // Marathi (uses Devanagari like Hindi)
        'ml-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0d00-\u0d7f<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,  // Malayalam
        'ta-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0b80-\u0bff<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,  // Tamil
        'te-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0c00-\u0c7f<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,  // Telugu
        
        // Southeast Asian languages
        'th-TH': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0e00-\u0e7f<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'vi-VN': /[a-zA-ZàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'id-ID': /[a-zA-Z0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'tr-TR': /[a-zA-ZçğıöşüÇĞIİÖŞÜ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&\_\=\+\[\]\{\}\|\\\~\$\`€]/g
    };

    // Get the character set for the target language (default to English if not found)
    const targetCharacterSet = languageCharacterSets[normalizedLanguage] || languageCharacterSets['en-US'];
    
    // Replace characters not in the allowed set
    // Reset lastIndex to avoid stateful "g" regex alternating true/false results
    let masked = text.replace(/./g, (char) => {
        // Ensure regex test starts from beginning each iteration
        targetCharacterSet.lastIndex = 0;
        return targetCharacterSet.test(char) ? char : '[...]';
    });
    // Normalize any sequence of masking patterns to a single token
    masked = masked.replace(/(?:\s*\[\.\.\.\]\s*)+/gi, ' [...] ').trim();

    return masked.trim();
}

// Make available to other modules
window.preprocessTranscript = preprocessTranscript;

// Function to initialize voice call system
function initializeVoiceCall() {
    console.log("Initializing voice call system...");

    // Try to get stored voice preference
    const storedVoice = localStorage.getItem('geminiVoicePreference');
    if (storedVoice) {
        currentGeminiVoice = storedVoice;
        console.log("Using stored voice preference:", currentGeminiVoice);
    }

    // Try to get stored language preference
    const storedLanguage = localStorage.getItem('geminiLanguagePreference');
    if (storedLanguage) {
        // Handle backward compatibility for old language codes
        if (storedLanguage === 'zh-CN') {
            currentGeminiLanguage = 'cmn-CN';
            localStorage.setItem('geminiLanguagePreference', 'cmn-CN');
            console.log("Updated stored language preference from zh-CN to cmn-CN for Live API compatibility");
        } else {
            currentGeminiLanguage = storedLanguage;
        }
        console.log("Using stored language preference:", currentGeminiLanguage);
    }

    // Initialize voice selector
    initializeVoiceSelector();

    // Start monitoring connection quality on dashboard load
    startConnectionMonitoring();

    // Wire up mute button if present
    const muteBtn = document.getElementById('mute-mic-button');
    if (muteBtn) {
        muteBtn.addEventListener('click', toggleMuteMicrophone);
    }

    // Preload property details and knowledge items if possible
    setTimeout(() => {
        const propId = getConfirmedPropertyId();
        if (propId && !window.propertyDetails) {
            console.log("Preloading property details for voice call...");
            fetchPropertyDetails(propId)
                .then(details => {
                    if (details) {
                        console.log("Preloaded property details for voice call:", details);

                        // Also preload knowledge items
                        return fetchPropertyKnowledgeItems(propId);
                    }
                })
                .then(knowledgeItems => {
                    if (knowledgeItems) {
                        console.log("Preloaded knowledge items for voice call:", knowledgeItems.length, "items");
                    }
                })
                .catch(error => {
                    console.error("Error preloading property data:", error);
                });
        }
    }, 2000);
}

// Function to handle voice call button click
async function handleVoiceCallClick() {
    console.log("Voice call button clicked, current state:", currentCallState);

    // Debug info
    console.log("=== PROPERTY ID DEBUG INFO ===");
    console.log("confirmedPropertyId (imported):", getConfirmedPropertyId());
    console.log("window.PROPERTY_ID:", window.PROPERTY_ID);
    console.log("document.body.dataset.propertyId:", document.body.dataset.propertyId);
    console.log("window.propertyDetails:", window.propertyDetails ? "Available" : "Not available");

    if (currentCallState === 'idle') {
        // Block start if connection is poor
        if (!isConnectionSufficientForVoice()) {
            addMessageToChat("Your connection seems too weak for a call. Please use text chat below for now.", "ai");
            updateVoiceCallButton(false, true, "Poor Connection");
            return;
        }
        // --- START CALL ---
        currentCallState = 'starting';
        updateVoiceCallButton(true, true, "Connecting..."); // Disable button while starting
        addMessageToChat("Starting voice call...", "ai");

        // Mark voice call as active in feedback system
        import('./guest_dashboard_feedback.js').then(module => {
            if (module.setVoiceCallActive) {
                module.setVoiceCallActive(true);
            }
        }).catch(error => {
            console.warn("Could not load feedback module:", error);
        });

        // Get property ID from available sources
        const propertyId = getConfirmedPropertyId() || window.PROPERTY_ID || document.body.dataset.propertyId;

        // Initialize diagnostics system (with fallback if not available)
        if (window.VoiceCallDiagnostics && !voiceCallDiagnostics) {
            try {
                voiceCallDiagnostics = new window.VoiceCallDiagnostics(
                    voiceConversationId || 'temp-' + Date.now(),
                    propertyId,
                    window.CURRENT_USER_ID
                );

                // Set global reference for error handling
                window.activeVoiceCallDiagnostics = voiceCallDiagnostics;

                // Initialize the diagnostics session
                voiceCallDiagnostics.initializeSession(
                    window.GUEST_NAME,
                    window.RESERVATION_ID
                ).then(success => {
                    if (success) {
                        console.log('[VoiceCall] Diagnostics session initialized successfully');
                    } else {
                        console.warn('[VoiceCall] Diagnostics session initialization failed, but continuing in fallback mode');
                    }
                }).catch(error => {
                    console.error('Failed to initialize diagnostics session:', error);
                    voiceCallDiagnostics.logEvent('INITIALIZATION_EXCEPTION', {
                        error: error.message,
                        stack: error.stack
                    }, error);
                });

                console.log('[VoiceCall] Diagnostics system initialized successfully');
            } catch (error) {
                console.error('[VoiceCall] Failed to initialize diagnostics system:', error);
                voiceCallDiagnostics = null;
            }
        } else if (!window.VoiceCallDiagnostics) {
            console.warn('[VoiceCall] VoiceCallDiagnostics not available - diagnostics will be disabled');
            voiceCallDiagnostics = null;
        }

        try {
            // 1. Get ephemeral token (secure approach like marketing website)
            let authToken = '';
            
            try {
                console.log("Requesting ephemeral token for voice call...");
                const tokenResponse = await fetchEphemeralToken();
                authToken = tokenResponse.token;
                console.log("Ephemeral token obtained successfully");
            } catch (tokenError) {
                console.error("Failed to fetch ephemeral token:", tokenError);
                // Fallback to direct API key fetch for backwards compatibility
                console.log("Falling back to direct API key fetch...");
                try {
                    const config = await fetchGeminiConfig();
                    authToken = config.apiKey;
                    console.log("Fallback API key obtained successfully");
                } catch (apiError) {
                    console.error("Failed to fetch API key:", apiError);
                    throw new Error(`Failed to get authentication credentials: ${apiError.message}`);
                }
            }
            
            if (!authToken) {
                throw new Error("No authentication token available");
            }
            
            console.log("Using authentication token:", authToken ? "Present (hidden)" : "Missing");

            // 2. Get property ID - Check multiple sources
            // Get property ID from window or dataset (most reliable)
            const propertyId = window.PROPERTY_ID || document.body.dataset.propertyId;

            if (!propertyId) {
                throw new Error("Property ID not available. Cannot start call.");
            }
            console.log("Final property ID for voice call:", propertyId);

            // 3. Request microphone access
            try {
                microphoneStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                console.log("Microphone access granted.");

                // 4. Start the Gemini voice call
                await startGeminiVoiceCall(authToken, propertyId);

            } catch (micError) {
                console.error("Microphone access denied:", micError);

                // Log microphone error
                if (voiceCallDiagnostics && voiceCallDiagnostics.logEvent) {
                    voiceCallDiagnostics.logEvent('MICROPHONE_ACCESS_DENIED', {
                        error_name: micError.name,
                        error_message: micError.message
                    }, {
                        name: micError.name,
                        message: micError.message,
                        stack: micError.stack
                    });
                }

                throw new Error("Microphone access required for voice call.");
            }

        } catch (error) {
            console.error("Error starting voice call:", error);
            updateVoiceCallButton(false, false, "Call Staycee"); // Reset button
            addMessageToChat(`Error: ${error.message}`, "ai");
            currentCallState = 'idle';
        }
    } else if (currentCallState === 'active') {
        // --- END CALL ---
        console.log("User initiated call end.");
        stopVoiceCall("User ended call");
    }
}

// Start a voice call with Gemini API
async function startGeminiVoiceCall(apiKey, propertyId, resumptionHandle = null, skipGreeting = false) {
    console.log("Starting Gemini voice call for property:", propertyId);

    try {
        // 1. Get property details from window object
        if (!window.propertyDetails) {
            console.log("Property details not found in window object, fetching from server...");
            const propertyDetails = await fetchPropertyDetails(propertyId);
            if (!propertyDetails) {
                throw new Error("Failed to fetch property details.");
            }
        }

        // 2. Fetch knowledge items for the property
        try {
            console.log("Fetching knowledge items for voice call...");
            await fetchPropertyKnowledgeItems(propertyId);
            console.log("Knowledge items fetched successfully for voice call");
        } catch (knowledgeError) {
            console.warn(`Error fetching knowledge items for voice call: ${knowledgeError.message}`);
            // Non-critical error, continue with voice call
        }

        console.log("Using property details:", window.propertyDetails ? "Available" : "Missing");
        console.log("Property name:", window.confirmedPropertyName || "Unknown");
        console.log("Property address:", window.confirmedPropertyAddress || "Unknown");

        // 2. Set up audio context for processing microphone input
        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 16000 // Use 16kHz for input to match Gemini's expected input format
        });
        const micSource = audioContext.createMediaStreamSource(microphoneStream);

        // Create processor node for capturing audio
        let useAudioWorklet = false;
        try {
            // Check if AudioWorklet is supported
            if (audioContext.audioWorklet) {
                // For future implementation - currently fallback to ScriptProcessor
                useAudioWorklet = false; // Set to true when worklet code is implemented
            }
        } catch (e) {
            console.log("AudioWorklet not supported, using ScriptProcessor");
        }

        // Fallback to ScriptProcessor (deprecated but works everywhere)
        audioProcessorNode = audioContext.createScriptProcessor(MIC_BUFFER_SIZE, 1, 1);
        micSource.connect(audioProcessorNode);
        audioProcessorNode.connect(audioContext.destination);

        // Buffer for collecting audio chunks
        let audioChunks = [];
        let lastSendTime = 0;
        const SEND_INTERVAL_MS = 100; // Send audio every 100ms

        // 3. Create WebSocket connection to Gemini API
        const userId = window.CURRENT_USER_ID;
        if (!userId) {
            throw new Error("User ID not available. Please log in again.");
        }

        // Close any existing WebSocket connection
        if (geminiWebSocket) {
            console.log("Closing existing WebSocket connection before creating a new one");
            try {
                geminiWebSocket.close();
            } catch (e) {
                console.warn("Error closing existing WebSocket:", e);
            }
        }

        // Check if we have an ephemeral token (starts with 'auth_tokens/') or API key
        let wsUrl;
        
        if (apiKey.startsWith('auth_tokens/')) {
            // For now, fall back to API key method since ephemeral tokens seem to have issues with WebSocket
            console.log(`Ephemeral token received but falling back to API key method for WebSocket connection`);
            // Get the API key from the fallback method
            const config = await fetchGeminiConfig();
            const fallbackApiKey = config.apiKey;
            wsUrl = `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=${fallbackApiKey}&alt=json`;
            console.log(`Attempting WebSocket connection to Gemini Live API with API key: ${wsUrl.replace(fallbackApiKey, "REDACTED_KEY")}`);
        } else {
            // Fallback to API key format
            wsUrl = `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=${apiKey}&alt=json`;
            console.log(`Attempting WebSocket connection to Gemini Live API with API key: ${wsUrl.replace(apiKey, "REDACTED_KEY")}`);
        }
        console.log(`Using model: ${GEMINI_LIVE_MODEL}`);

        // Create WebSocket connection
        console.log("Creating WebSocket connection...");
        geminiWebSocket = new WebSocket(wsUrl);

        // Reset audio processing state for new connection
        audioChunks = [];
        audioQueue = [];
        isAudioPlaying = false;
        audioBuffering = true;
        nextChunkStartTime = 0;

        // Handle connection open
        geminiWebSocket.onopen = () => {
            console.log("WebSocket connection established with Gemini voice API");

            // Log WebSocket connection success
            if (voiceCallDiagnostics && voiceCallDiagnostics.logEvent) {
                voiceCallDiagnostics.logEvent('WEBSOCKET_CONNECTED', {
                    url: wsUrl.replace(/(key=)[^&]+/, '$1REDACTED'),
                    model: GEMINI_LIVE_MODEL,
                    voice: currentGeminiVoice,
                    language: currentGeminiLanguage
                });
            }

            // Voice transcripts will be stored directly in the diagnostics session
            // Set up the session for transcript storage
            if (voiceCallDiagnostics && voiceCallDiagnostics.sessionId) {
                voiceConversationId = voiceCallDiagnostics.sessionId;
                voiceSessionActive = true;
                console.log("Voice transcripts will be stored in diagnostics session:", voiceConversationId);
                // Add a message to inform user that voice transcriptions will appear
                addMessageToChat("Voice transcriptions will appear in this chat.", "ai");

                // Persist technical config (language, voice, model, ws url) for host UI
                try {
                    const sanitizedUrl = wsUrl.replace(/(key=)[^&]+/, '$1REDACTED');
                    const languageCode = currentGeminiLanguage || 'en-US';
                    const configUpdate = {
                        TechnicalConfig: {
                            LanguageCode: languageCode,
                            GeminiModel: GEMINI_LIVE_MODEL,
                            WebSocketUrl: sanitizedUrl,
                            VoiceSettings: {
                                voiceName: currentGeminiVoice,
                                languageCode: languageCode
                            }
                        }
                    };
                    fetch('/api/voice-call/config/update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'same-origin',
                        body: JSON.stringify({ session_id: voiceConversationId, config: configUpdate })
                    }).catch(() => {});
                } catch (_) {}
            } else {
                console.warn("Diagnostics session not available, transcriptions won't be stored");
            }

            // Create initial configuration in the format expected by Gemini Live API
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
                            languageCode: currentGeminiLanguage
                        }
                    },
                    tools: [
                        {
                            google_search: {}
                        },
                        {
                            function_declarations: [
                                {
                                    name: "get_current_time",
                                    description: "Get the current date and time. Use this when the guest asks about the current time, date, or when you need to provide time-sensitive information.",
                                    parameters: {
                                        type: "object",
                                        properties: {
                                            property_context: {
                                                type: "object",
                                                description: "Property context for timezone detection (optional)"
                                            }
                                        },
                                        required: []
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
                    // Enable context window compression to extend session duration
                    sessionResumption: resumptionHandle ? { handle: resumptionHandle } : {},
                    contextWindowCompression: {
                        triggerTokens: 2048, // Compress when context exceeds 2k tokens
                        slidingWindow: {}
                    },
                    // Add transcription configurations (top-level, not under generationConfig)
                    output_audio_transcription: {},
                    input_audio_transcription: {},
                    // Added configuration for realtime input to handle interruptions better
                    realtimeInputConfig: {
                        // Configure voice activity detection for better sensitivity
                        automaticActivityDetection: {
                            disabled: false, // Enable automatic activity detection
                            startOfSpeechSensitivity: "START_SENSITIVITY_HIGH", // Detect speech start more quickly
                            endOfSpeechSensitivity: "END_SENSITIVITY_LOW", // Don't end speech detection too quickly
                            prefixPaddingMs: 50, // Lower value for faster speech detection
                            silenceDurationMs: 500 // Shorter silence duration for more responsive interruptions
                        },
                        // Make sure the model is interrupted when user starts speaking
                        activityHandling: "START_OF_ACTIVITY_INTERRUPTS", // This enables barge-in functionality
                        // Include all input in the user's turn
                        turnCoverage: "TURN_INCLUDES_ALL_INPUT"
                    }
                }
            };

// --- Send initial configuration ---
            console.log("Sending initial configuration to Gemini voice API");
            console.log(`Using language: ${currentGeminiLanguage} for voice call`);
            
            // Debug: Log the initial configuration being sent
            console.log("🔧 Initial configuration being sent:");
            console.log(JSON.stringify(initialConfig, null, 2));
            
            // Debug: Specifically log the function declarations
            const functionDeclarations = initialConfig.setup.tools.find(tool => tool.function_declarations);
            if (functionDeclarations) {
                console.log("🔧 Function declarations being sent:", functionDeclarations.function_declarations);
            } else {
                console.log("❌ No function declarations found in tools array");
            }
            
            geminiWebSocket.send(JSON.stringify(initialConfig));

            // Optionally send a user greeting to kick off the first turn (only on brand-new sessions)
            if (!skipGreeting) {
                setTimeout(() => {
                    if (geminiWebSocket && geminiWebSocket.readyState === WebSocket.OPEN) {
                        const initialMessage = {
                            client_content: {
                                turn_complete: true,
                                turns: [{
                                    role: "user",
                                    parts: [{ text: getGreetingMessage() }]
                                }]
                            }
                        };
                        console.log("Sending initial greeting message (new session)");
                        console.log(`Greeting message: ${getGreetingMessage()}`);
                        geminiWebSocket.send(JSON.stringify(initialMessage));
                    }
                }, 1000); // Small delay to ensure configuration is processed first
            }

            // Update UI to show active call state
            currentCallState = 'active';
            updateVoiceCallButton(true, false, "End Call");
            addMessageToChat("Voice call connected. Start speaking.", "ai");

            // Show mute button when call becomes active
            const muteBtn = document.getElementById('mute-mic-button');
            if (muteBtn) {
                muteBtn.classList.remove('hidden');
            }

            // Add a hint about interruption capability
            addMessageToChat("You can interrupt me anytime by speaking", "ai");

            // Log call started event
            if (voiceCallDiagnostics && voiceCallDiagnostics.logEvent) {
                voiceCallDiagnostics.logEvent('CALL_STARTED', {
                    model: GEMINI_LIVE_MODEL,
                    voice: currentGeminiVoice,
                    language: currentGeminiLanguage,
                    websocket_url: wsUrl.replace(/(key=)[^&]+/, '$1REDACTED')
                });

                // Start WebSocket health monitoring
                if (voiceCallDiagnostics.monitorWebSocketHealth) {
                    voiceCallDiagnostics.webSocketHealthInterval = setInterval(() => {
                        if (geminiWebSocket) {
                            const healthMetrics = voiceCallDiagnostics.monitorWebSocketHealth(geminiWebSocket);
                            if (healthMetrics) {
                                voiceCallDiagnostics.metrics.webSocketEvents.push(healthMetrics);

                                // Keep only last 20 health checks
                                if (voiceCallDiagnostics.metrics.webSocketEvents.length > 20) {
                                    voiceCallDiagnostics.metrics.webSocketEvents.shift();
                                }
                            }
                        }
                    }, 15000); // Check every 15 seconds (reduced frequency)
                }
            }

            // Start noise monitoring
            startNoiseMonitoring();
        };

        // Handle incoming messages from Gemini (audio chunks)
        geminiWebSocket.onmessage = (event) => {
            try {
                // Check message type
                if (typeof event.data === 'string') {
                    // Parse JSON response
                    try {
                        const jsonMessage = JSON.parse(event.data);
                        console.log("Received JSON message from Gemini");

                        // Check specifically for interruption message
                        if (jsonMessage.serverContent && jsonMessage.serverContent.interrupted === true) {
                            console.log("User interrupted - clearing audio queue");

                            // Log user interruption
                            if (voiceCallDiagnostics && voiceCallDiagnostics.logEvent) {
                                voiceCallDiagnostics.metrics.interruptionCount++;
                                voiceCallDiagnostics.logEvent('USER_INTERRUPTION', {
                                    interruption_count: voiceCallDiagnostics.metrics.interruptionCount,
                                    audio_queue_length: audioQueue.length,
                                    is_audio_playing: isAudioPlaying
                                });
                            }

                            // Handle interruption for noise management
                            handleInterruption();
                            // Stop active playback immediately and aggressively
                            stopAllAudioPlayback();
                            addMessageToChat("Listening...", "ai", "system");
                        } else {
                            // Process the JSON message to extract content
                            processGeminiJsonMessage(jsonMessage);
                        }
                    } catch (parseError) {
                        console.error("Error parsing JSON message:", parseError);
                    }
                } else if (event.data instanceof Blob) {
                    // Handle binary data (likely audio)
                    const blob = event.data;
                    console.log(`Received Blob data from Gemini (size: ${blob.size})`);
                    console.log(`Blob MIME type: ${blob.type || 'unknown'}`);

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
                                    console.log("Parsed JSON from Blob:", jsonMessage);

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

            // Log WebSocket error
            if (voiceCallDiagnostics && voiceCallDiagnostics.logEvent) {
                voiceCallDiagnostics.logEvent('WEBSOCKET_ERROR', {
                    error_type: 'connection_error',
                    ready_state: geminiWebSocket.readyState,
                    buffered_amount: geminiWebSocket.bufferedAmount
                }, {
                    message: 'WebSocket connection error',
                    timestamp: new Date().toISOString()
                });
            }

            stopVoiceCall("Connection error");
            addMessageToChat("Error with voice call connection. Please try again later.", "ai");
        };

        // Handle WebSocket closure
        geminiWebSocket.onclose = (event) => {
            console.log(`WebSocket closed. Code: ${event.code}, Reason: ${event.reason}`);

            // Log WebSocket closure
            if (voiceCallDiagnostics && voiceCallDiagnostics.logEvent) {
                const isNormalClosure = event.code === 1000;
                voiceCallDiagnostics.logEvent(
                    isNormalClosure ? 'WEBSOCKET_CLOSED_NORMAL' : 'WEBSOCKET_CLOSED_UNEXPECTED',
                    {
                        code: event.code,
                        reason: event.reason,
                        was_clean: event.wasClean,
                        call_state: currentCallState
                    },
                    isNormalClosure ? null : {
                        message: `WebSocket closed unexpectedly with code ${event.code}`,
                        code: event.code,
                        reason: event.reason
                    }
                );
            }

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
                    // Add a message to let the user know
                    addMessageToChat("Connection interruption. Attempting to reconnect...", "ai");

                    // Attempt to reconnect in 2 seconds
                    setTimeout(() => {
                        if (currentCallState === 'active') {
                            try {
                                // Log reconnection attempt
                                if (voiceCallDiagnostics && voiceCallDiagnostics.logEvent) {
                                    voiceCallDiagnostics.metrics.reconnectionCount++;
                                    voiceCallDiagnostics.logEvent('RECONNECTION_ATTEMPT', {
                                        attempt_number: voiceCallDiagnostics.metrics.reconnectionCount,
                                        close_code: event.code,
                                        close_reason: event.reason
                                    });
                                }

                                // Get the property ID from previous setup
                                const propertyId = window.PROPERTY_ID || document.body.dataset.propertyId;
                                const apiKey = window.GEMINI_API_KEY;
                                if (propertyId && apiKey) {
                                    console.log("Attempting to reconnect voice call...");
                                    startGeminiVoiceCall(apiKey, propertyId, sessionResumptionHandle, true).catch(error => {
                                        console.error("Reconnection failed:", error);

                                        // Log reconnection failure
                                        if (voiceCallDiagnostics && voiceCallDiagnostics.logEvent) {
                                            voiceCallDiagnostics.logEvent('RECONNECTION_FAILED', {
                                                attempt_number: voiceCallDiagnostics.metrics.reconnectionCount,
                                                error_message: error.message
                                            }, {
                                                name: error.name,
                                                message: error.message,
                                                stack: error.stack
                                            });
                                        }

                                        stopVoiceCall("Reconnection failed");
                                    });
                                } else {
                                    // Log missing credentials
                                    if (voiceCallDiagnostics && voiceCallDiagnostics.logEvent) {
                                        voiceCallDiagnostics.logEvent('RECONNECTION_FAILED', {
                                            reason: 'missing_credentials',
                                            has_property_id: !!propertyId,
                                            has_api_key: !!apiKey
                                        }, {
                                            message: 'Cannot reconnect - missing property ID or API key'
                                        });
                                    }

                                    stopVoiceCall("Cannot reconnect - missing property ID or API key");
                                }
                            } catch (error) {
                                console.error("Error during reconnection attempt:", error);

                                // Log reconnection error
                                if (voiceCallDiagnostics && voiceCallDiagnostics.logEvent) {
                                    voiceCallDiagnostics.logEvent('RECONNECTION_ERROR', {
                                        attempt_number: voiceCallDiagnostics.metrics.reconnectionCount,
                                        error_message: error.message
                                    }, {
                                        name: error.name,
                                        message: error.message,
                                        stack: error.stack
                                    });
                                }

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

                // Assess audio quality periodically (reduced frequency to save API calls)
                if (voiceCallDiagnostics && voiceCallDiagnostics.assessAudioQuality && Math.random() < 0.002) { // 0.2% of chunks
                    const audioQuality = voiceCallDiagnostics.assessAudioQuality(pcmData.buffer);
                    if (audioQuality) {
                        voiceCallDiagnostics.metrics.audioQualityIssues.push(audioQuality);

                        // Keep only last 20 quality assessments
                        if (voiceCallDiagnostics.metrics.audioQualityIssues.length > 20) {
                            voiceCallDiagnostics.metrics.audioQualityIssues.shift();
                        }
                    }
                }

                // Detect noise level for environment analysis
                const noiseLevel = detectNoiseLevel(pcmData.buffer);
                if (noiseLevel > 0) {
                    noiseLevels.push(noiseLevel);
                    // Keep only recent samples
                    if (noiseLevels.length > NOISE_SAMPLES_COUNT) {
                        noiseLevels.shift();
                    }
                }

                // Add to audio chunks
                audioChunks.push(pcmData.buffer);

                // Send audio on a regular interval instead of based on chunk count
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

                        // Send to Gemini using the format from the working implementation
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

        console.log("Voice call successfully started.");
    } catch (error) {
        console.error("Error setting up voice call:", error);
        stopVoiceCall(`Setup error: ${error.message}`);
        throw error;
    }
}

// Function to stop the voice call
function stopVoiceCall(reason = "User ended call") {
    console.log("Stopping voice call. Reason:", reason);

    // Log call ending event
    if (voiceCallDiagnostics && voiceCallDiagnostics.logEvent) {
        voiceCallDiagnostics.logEvent('CALL_ENDING', {
            reason: reason,
            call_state: currentCallState,
            session_duration: Date.now() - voiceCallDiagnostics.startTime
        });
    }

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

    // Stop any ongoing audio playback immediately
    stopAllAudioPlayback();

    // Clean up audio playback state
    audioQueue = [];
    isAudioPlaying = false;
    audioBuffering = true;
    nextChunkStartTime = 0;
    audioSourceNode = null;

    // Stop noise monitoring
    stopNoiseMonitoring();

    // Hide mute button and reset state
    const muteBtn = document.getElementById('mute-mic-button');
    if (muteBtn) {
        muteBtn.classList.add('hidden');
        muteBtn.setAttribute('aria-pressed', 'false');
        const iconOn = muteBtn.querySelector('.icon-mic');
        const iconOff = muteBtn.querySelector('.icon-mic-off');
        const textSpan = muteBtn.querySelector('.mute-text');
        if (iconOn && iconOff && textSpan) {
            iconOn.classList.remove('hidden');
            iconOff.classList.add('hidden');
            textSpan.textContent = 'Mute';
        }
        // Ensure tracks unmuted on cleanup
        try { setMicrophoneMuted(false); } catch (_) {}
    }

    // Voice activity detection is now handled server-side
    // No need to reset client-side VAD state

    // Update UI state
    currentCallState = 'idle';
    updateVoiceCallButton(false, false, "Call Staycee");

    // Clean up transcription state
    if (aiTranscriptionTimeout) {
        clearTimeout(aiTranscriptionTimeout);
        aiTranscriptionTimeout = null;
    }
    if (userTranscriptionTimeout) {
        clearTimeout(userTranscriptionTimeout);
        userTranscriptionTimeout = null;
    }

    // Display any remaining transcriptions before clearing
    if (currentAITranscription.trim()) {
        console.log("🎤 AI Complete (final):", currentAITranscription.trim());
        handleCompleteVoiceTranscription('assistant', currentAITranscription.trim());
    }
    if (currentUserTranscription.trim()) {
        console.log("👤 User Complete (final):", currentUserTranscription.trim());
        handleCompleteVoiceTranscription('user', currentUserTranscription.trim());
    }

    // Clear transcription buffers
    currentAITranscription = "";
    currentUserTranscription = "";

    // Add a message to the chat about call ending
    addMessageToChat(`Voice call ended: ${reason}`, "ai");

    // Trigger feedback modal after voice call ends
    const sessionId = voiceCallDiagnostics?.sessionId || Date.now().toString();
    import('./guest_dashboard_feedback.js').then(module => {
        if (module.triggerFeedbackAfterVoiceCall) {
            module.triggerFeedbackAfterVoiceCall(sessionId);
        }
        // Also reset the text-chat feedback counters so the 5-message rule applies per session
        if (module.resetForNewSession) {
            module.resetForNewSession();
        }
    }).catch(error => {
        console.warn("Could not load feedback module:", error);
    });

    // Dispatch custom event for voice call end
    const voiceCallEndEvent = new CustomEvent('voiceCallEnded', {
        detail: { sessionId: sessionId, reason: reason }
    });
    document.dispatchEvent(voiceCallEndEvent);

    // Finalize diagnostics session
    if (voiceCallDiagnostics) {
        // Stop WebSocket health monitoring
        if (voiceCallDiagnostics.webSocketHealthInterval) {
            clearInterval(voiceCallDiagnostics.webSocketHealthInterval);
            voiceCallDiagnostics.webSocketHealthInterval = null;
        }

        const finalMetrics = {
            total_events: voiceCallDiagnostics.eventTimeline.length,
            total_errors: voiceCallDiagnostics.errors.length,
            total_warnings: voiceCallDiagnostics.warnings.length,
            interruption_count: voiceCallDiagnostics.metrics.interruptionCount,
            reconnection_count: voiceCallDiagnostics.metrics.reconnectionCount,
            audio_dropouts: voiceCallDiagnostics.metrics.audioDropouts,
            websocket_health_checks: voiceCallDiagnostics.metrics.webSocketEvents.length,
            audio_quality_assessments: voiceCallDiagnostics.metrics.audioQualityIssues.length
        };

        if (voiceCallDiagnostics.finalizeSession) {
            // Capture a stable reference to avoid null errors if the global is cleared before async callbacks run
            const diagnosticsRef = voiceCallDiagnostics;
            try {
                voiceCallDiagnostics.finalizeSession(reason, finalMetrics).then(() => {
                    console.log('[VoiceCall] Diagnostics session finalized successfully');

                    // Dump diagnostic info for debugging (guard against cleared global)
                    if (diagnosticsRef && typeof diagnosticsRef.dumpDiagnosticInfo === 'function') {
                        diagnosticsRef.dumpDiagnosticInfo();
                    }

                }).catch(error => {
                    console.error('Failed to finalize diagnostics session:', error);

                    // Still dump diagnostic info even if finalization failed (guarded)
                    if (diagnosticsRef && typeof diagnosticsRef.dumpDiagnosticInfo === 'function') {
                        diagnosticsRef.dumpDiagnosticInfo();
                    }
                });
            } catch (error) {
                console.error('[VoiceCall] Error during diagnostics finalization:', error);
            }
        }

        // Clear global reference
        if (window.activeVoiceCallDiagnostics === voiceCallDiagnostics) {
            window.activeVoiceCallDiagnostics = null;
        }

        voiceCallDiagnostics = null;
    }

    // Clean up voice conversation session
    cleanupVoiceConversationSession();
}

// Function to stop all audio playback immediately
function stopAllAudioPlayback() {
    console.log("🔇 Stopping all audio playback immediately");

    // Stop the current audio source node
    if (audioSourceNode) {
        try {
            audioSourceNode.stop();
            audioSourceNode.disconnect();
            audioSourceNode = null;
        } catch (error) {
            console.warn("Error stopping current audio source:", error);
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

    // Clear the audio queue to stop upcoming audio
    const droppedChunks = audioQueue.length;
    audioQueue = [];

    // Reset audio playback state
    isAudioPlaying = false;
    audioBuffering = true;
    nextChunkStartTime = 0;

    // Reset timing for clean restart
    if (window.audioPlayerContext) {
        nextChunkStartTime = window.audioPlayerContext.currentTime;
    }

    if (droppedChunks > 0) {
        console.log(`🗑️ Dropped ${droppedChunks} audio chunks`);
    }

    console.log("✅ All audio playback stopped successfully");
}

// Helper function to update button state
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

// Function to create voice selector dropdown
function initializeVoiceSelector() {
    const voiceSelector = document.getElementById('gemini-voice-selector');

    if (!voiceSelector) {
        console.log("Voice selector not found in the DOM");
        return;
    }

    // Clear existing options
    voiceSelector.innerHTML = '';

    // Add all available Gemini voices
    GEMINI_VOICES.forEach(voice => {
        const option = document.createElement('option');
        option.value = voice;
        option.textContent = voice;
        voiceSelector.appendChild(option);
    });

    // Get the default/saved voice preference
    let currentVoice = localStorage.getItem('gemini_voice') || GEMINI_DEFAULT_VOICE;

    // Set the selected voice
    if (voiceSelector.querySelector(`option[value="${currentVoice}"]`)) {
        voiceSelector.value = currentVoice;
    } else {
        // If saved voice is not in the options, use the default
        voiceSelector.value = GEMINI_DEFAULT_VOICE;
        localStorage.setItem('gemini_voice', GEMINI_DEFAULT_VOICE);
    }

    // Event listener for voice changes
    voiceSelector.addEventListener('change', () => {
        const selectedVoice = voiceSelector.value;
        localStorage.setItem('gemini_voice', selectedVoice);
        console.log(`Gemini voice changed to: ${selectedVoice}`);
    });

    console.log(`Voice selector initialized with ${GEMINI_VOICES.length} voices, current voice: ${voiceSelector.value}`);
}

// Function to fetch Gemini API Key from backend (secure endpoint)
async function fetchGeminiConfig() {
    // Use cached key if available
    if (window.GEMINI_API_KEY) {
        console.log("Using cached Gemini API key");
        return { apiKey: window.GEMINI_API_KEY };
    }

    console.log("Fetching Gemini API key from secure endpoint...");
    try {
        // Use proper endpoint from the API routes
        const response = await fetch('/api/gemini-voice-config', {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            },
            credentials: 'same-origin' // Include cookies for authentication
        });

        if (!response.ok) {
            const errorText = await response.text();
            let errorMessage;
            try {
                const errorData = JSON.parse(errorText);
                errorMessage = errorData.error || `HTTP error! status: ${response.status}`;
            } catch {
                errorMessage = `HTTP error! status: ${response.status}`;
            }
            console.error("Error fetching Gemini config:", errorMessage);
            throw new Error(errorMessage);
        }

        const config = await response.json();
        if (!config.apiKey) {
            throw new Error("API key not found in server response.");
        }

        // Store the key for future use
        window.GEMINI_API_KEY = config.apiKey;
        console.log("Fetched Gemini API Key successfully from secure endpoint.");
        return config;
    } catch (error) {
        console.error("Error fetching Gemini config:", error);
        throw error; // Re-throw to allow caller to handle the error
    }
}

// Function to fetch ephemeral token (similar to marketing website implementation)
async function fetchEphemeralToken() {
    try {
        console.log("Requesting ephemeral token from server...");
        
        const response = await fetch('/api/ephemeral-token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            credentials: 'same-origin'
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(`HTTP error! status: ${response.status}, message: ${errorData.message || 'Unknown error'}`);
        }

        const tokenData = await response.json();
        
        if (!tokenData.success || !tokenData.token) {
            throw new Error("Ephemeral token not found in server response");
        }

        console.log("Ephemeral token received successfully");
        return tokenData;
    } catch (error) {
        console.error("Error fetching ephemeral token:", error);
        throw error;
    }
}

// Function to create system prompt for voice call
function createVoiceSystemPrompt() {
    // Use the imported shared system prompt function
    try {
        // Debug: Check current guest name
        const currentGuestName = window.dashboardState?.guestName || window.GUEST_NAME || "Guest";
        console.log("[VOICE DEBUG] Current guest name:", currentGuestName);
        console.log("[VOICE DEBUG] createSharedSystemPrompt available:", typeof createSharedSystemPrompt);
        
        // createSharedSystemPrompt is imported at the top of this file
        if (createSharedSystemPrompt && typeof createSharedSystemPrompt === 'function') {
            console.log("[VOICE DEBUG] Using shared system prompt function for voice call");
            const prompt = createSharedSystemPrompt();
            console.log("[VOICE DEBUG] Generated prompt length:", prompt.length);
            console.log("[VOICE DEBUG] Prompt contains guest name handling:", prompt.includes('ask for their name'));
            return prompt;
        } else {
            console.warn("[VOICE DEBUG] createSharedSystemPrompt not available, using fallback");
            const fallbackPrompt = createFallbackSystemPrompt();
            console.log("[VOICE DEBUG] Using fallback prompt, length:", fallbackPrompt.length);
            return fallbackPrompt;
        }
    } catch (error) {
        console.error("[VOICE DEBUG] Error using shared system prompt:", error);
        return createFallbackSystemPrompt();
    }
}

// Fallback function in case the shared one is not available
function createFallbackSystemPrompt() {
    // Base prompt parts
    const propertyName = window.confirmedPropertyName || "this property";
    const propertyAddress = window.confirmedPropertyAddress || "";
    const guestName = window.GUEST_NAME || "Guest";
    const hostName = window.propertyDetails?.hostName || "your host";

    console.log("Creating voice system prompt for property:", propertyName);
    console.log("Property details available:", window.propertyDetails ? "Yes" : "No");
    console.log("Window propertyKnowledgeItems available:", window.propertyKnowledgeItems ? "Yes" : "No");
    if (window.propertyKnowledgeItems) {
        console.log("First 200 chars of propertyKnowledgeItems:", window.propertyKnowledgeItems.substring(0, 200));
    }
    if (window.propertyDetails && window.propertyDetails.knowledgeItems) {
        console.log("PropertyDetails.knowledgeItems available, count:", window.propertyDetails.knowledgeItems.length);
    }

    // Gather additional context from property details
    let additionalContext = "";
    if (window.propertyDetails) {
        // Add check-in/check-out times if available
        if (window.propertyDetails.checkInTime) {
            additionalContext += `Check-in time is ${window.propertyDetails.checkInTime}. `;
        }
        if (window.propertyDetails.checkOutTime) {
            additionalContext += `Check-out time is ${window.propertyDetails.checkOutTime}. `;
        }

        // Add property description if available
        if (window.propertyDetails.description) {
            additionalContext += `Property description: ${window.propertyDetails.description} `;
        }

        // Add WiFi details if available
        if (window.propertyDetails.wifiNetwork && window.propertyDetails.wifiPassword) {
            additionalContext += `\nWiFi Network: ${window.propertyDetails.wifiNetwork}\nWiFi Password: ${window.propertyDetails.wifiPassword} `;
        }
    }

    // Add property knowledge items if available - check both possible locations
    // First check window.propertyKnowledgeItems (stored by fetchPropertyKnowledgeItems)
    if (window.propertyKnowledgeItems) {
        console.log("Using propertyKnowledgeItems from window object");
        additionalContext += "\n\nAdditional property information:\n";
        additionalContext += window.propertyKnowledgeItems;
    }
    // If not found, check if they're stored directly in propertyDetails
    else if (window.propertyDetails && window.propertyDetails.knowledgeItems && window.propertyDetails.knowledgeItems.length > 0) {
        console.log("Using knowledgeItems from propertyDetails object");
        additionalContext += "\n\nAdditional property information:\n";
        window.propertyDetails.knowledgeItems.forEach(item => {
            if (item.content) {
                const typePrefix = item.type ? `[${item.type.toUpperCase()}] ` : '';
                additionalContext += `${typePrefix}${item.content}\n\n`;
            }
        });
    } else {
        console.log("No knowledge items found in either location");
    }

    // Create the system prompt
    const systemPrompt = `
    You are Staycee, a helpful AI concierge assistant for "${propertyName}" located at "${propertyAddress}".
    You are speaking with ${guestName}, a guest at this property. IMPORTANT: If the guest name is generic, like "Guest", don't use it when addressing the guest. Instead, when appropriate during the conversation (such as during initial greetings or when it feels natural), politely ask for their name so you can address them personally. Once they provide their name, use it throughout the conversation to create a more personalized experience.
    The host for this property is ${hostName}.
    Your goal is to assist the guest with any questions or needs they have regarding their stay.
    Be conversational, friendly, and helpful.
    
    TRAVEL GUIDE CAPABILITIES:
    When guests ask about attractions, activities, restaurants, or places to visit beyond the property, act as a knowledgeable travel guide. To provide the most relevant recommendations, ask clarifying questions about:
    - The nature of their stay (celebration, family vacation, romantic getaway, business trip, casual leisure)
    - For family stays: ages and composition of travelers (young children, teenagers, adults, seniors)
    - Interests and preferences (outdoor activities, cultural attractions, dining preferences, etc.)
    - Special occasions or events they're celebrating
    Once you understand their context, retain this information throughout the conversation and incorporate it into all recommendations. Tailor suggestions for restaurants, activities, timing, and experiences based on their stay purpose and group composition. Don't repeatedly ask for the same context information - use what you've learned to provide increasingly personalized suggestions.
    
    STRATEGIC RECOMMENDATION APPROACH:
    When providing travel guide recommendations, be strategic and concise:
    - Offer 1-2 top options first based on distance from property or context of user's trip intent
    - Ask if the guest would like additional alternatives or more information about the suggested options
    - If they decline the initial suggestions, provide a few of the next best available options
    - Consider current time of day and weather conditions when relevant to enhance recommendation usefulness
    - Keep responses focused and avoid overwhelming guests with too many options at once
    
    ${additionalContext}
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

    IMPORTANT VOICE CALL GUIDELINES:
    - If you detect background noise or environmental sounds that may interfere with our conversation, politely acknowledge it
    - If there are repeated interruptions due to background noise, suggest the guest might prefer text chat
    - Be patient with audio quality issues and don't interrupt the guest unnecessarily
    - If the guest seems to be in a noisy environment (traffic, crowds, etc.), offer to help via text chat instead

    You have access to the following tools:
    1. search_nearby_places: Use this tool for ANY location-based queries about nearby places (restaurants, cafes, attractions, shopping, etc.). This provides accurate distances, travel times, ratings, hours, price levels, and structured information. ALWAYS use this for location queries instead of google_search.
    2. google_search: Use this tool ONLY for general information, current events, or questions that are NOT about nearby places. For restaurants, attractions, and local businesses, use search_nearby_places instead.
    3. get_current_time: Use this function when guests ask about the current time, date, or when you need to provide time-sensitive information. This will give you the accurate current time in the property's timezone.

    When using the search_nearby_places tool:
    - This tool provides structured data with accurate distances, travel times, ratings, hours, and price levels
    - Present the information naturally and conversationally
    - Include walkability information and travel times
    - Mention open hours if available
    
    When using the google_search tool:
    - Use ONLY for general information, not for nearby places/restaurants/attractions
    - After receiving the search results, provide a concise and helpful summary
    - If the search results don't provide relevant information, let the guest know

    When using the get_current_time function:
    - This function automatically detects the property's timezone based on location
    - Use it whenever a guest asks "what time is it" or similar time-related questions
    - The function will return the current date, time, and timezone information

    Respond to the guest's voice queries to help them have a great stay.
    `;

    console.log("Created voice system prompt using fallback function");
    console.log("Prompt length:", systemPrompt.length);
    return systemPrompt;
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

// Helper function to convert base64 to ArrayBuffer
function base64ToArrayBuffer(base64) {
    if (!base64 || typeof base64 !== 'string') {
        console.warn("Invalid base64 input:", typeof base64);
        return new ArrayBuffer(0);
    }

    try {
        // Clean up the base64 string first
        let cleanBase64 = base64;

        // Remove data URI prefix if present (e.g. "data:audio/wav;base64,")
        if (base64.includes('base64,')) {
            cleanBase64 = base64.split('base64,')[1];
            console.log("Removed data URI prefix from base64 string");
        }

        // Remove any whitespace
        cleanBase64 = cleanBase64.replace(/\s/g, '');

        // Add padding if needed
        while (cleanBase64.length % 4 !== 0) {
            cleanBase64 += '=';
        }

        // Log diagnostic info occasionally
        if (Math.random() < 0.05) { // Reduced from 0.1
            console.log(`Converting base64 to ArrayBuffer (length: ${cleanBase64.length})`);
        }

        // Convert base64 to binary string
        const binaryString = window.atob(cleanBase64);

        // Create arraybuffer and view
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        // Check for any issues with the data
        let hasNonZeroData = false;
        for (let i = 0; i < Math.min(bytes.length, 1000); i++) {
            if (bytes[i] !== 0) {
                hasNonZeroData = true;
                break;
            }
        }

        if (!hasNonZeroData && bytes.length > 100) {
            console.warn("Warning: Converted base64 data contains all zeros in the first 1000 bytes");
        }

        // Only log successful conversion occasionally
        if (Math.random() < 0.05) { // Reduced from 0.1
            console.log(`Converted base64 to ArrayBuffer: ${bytes.length} bytes`);
        }
        return bytes.buffer;
    } catch (error) {
        console.error("Error converting base64 to ArrayBuffer:", error);
        console.error("Failed base64 string (first 20 chars):", base64.substring(0, 20));
        return new ArrayBuffer(0);
    }
}

// Queue audio for playback
function queueAudioForPlayback(audioBuffer) {
    // Don't queue audio if call is not active
    if (currentCallState !== 'active') {
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

    // Periodically log basic audio stats for debugging (but only ~33% of chunks to reduce log noise)
    if (Math.random() < 0.33) {
        analyzeAudioData(audioBuffer);
    }

    // Create audio context if needed
    if (!window.audioPlayerContext) {
        try {
            window.audioPlayerContext = new (window.AudioContext || window.webkitAudioContext)({
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
    if (window.audioPlayerContext && window.audioPlayerContext.state === 'suspended') {
        window.audioPlayerContext.resume().catch(error => {
            console.error("Error resuming audio context:", error);
        });
    }

    // Add to queue and track if queue was empty
    const wasQueueEmpty = audioQueue.length === 0;
    audioQueue.push(audioBuffer);

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
    const audioCtx = window.audioPlayerContext;

    // Create a loop that continuously processes and plays audio
    processAudioContinuously();
}

// Process audio continuously from the queue
function processAudioContinuously() {
    if (audioQueue.length === 0) {
        const timeoutId = setTimeout(() => {
            if (audioQueue.length > 0) {
                processAudioContinuously();
            } else {
                isAudioPlaying = false;
            }
        }, 100);

        // Track this timeout too
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

        // Only log scheduling occasionally to reduce console noise
        if (Math.random() < 0.05) { // Reduced from 0.1 to further minimize logging
            console.log(`Scheduled audio chunk (${audioBuffer.duration.toFixed(3)}s) to play at ${startTime.toFixed(3)}, queue length: ${audioQueue.length}`);
        }

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

            // Only log occasionally to reduce console noise
            if (Math.random() < 0.1) {
                console.log("Audio chunk playback complete");
            }
            // Process the next chunk immediately to ensure continuous playback
            processAudioContinuously();
        };

        // Set a safety timeout in case the onended event doesn't fire
        const timeoutId = setTimeout(() => {
            if (audioQueue.length > 0 && isAudioPlaying) {
                processAudioContinuously();
            }
        }, audioBuffer.duration * 1000 + 100);

        // Track this timeout so we can clear it if needed
        audioTimeouts.push(timeoutId);

    } catch (error) {
        console.error("Error processing audio:", error);
        // Try to continue with the next chunk
        const timeoutId = setTimeout(() => {
            if (audioQueue.length > 0) {
                processAudioContinuously();
            } else {
                isAudioPlaying = false;
            }
        }, 100);

        // Track this timeout too
        audioTimeouts.push(timeoutId);
    }
}

// Analyze audio data for debugging
function analyzeAudioData(audioBuffer) {
    try {
        // Skip tiny buffers
        if (audioBuffer.byteLength < 256) return;

        // Basic stats - only run this occasionally to save performance
        if (Math.random() > 0.02) return; // Only 2% of chunks get analyzed

        const numSamples = Math.floor(audioBuffer.byteLength / 2);
        const view = new DataView(audioBuffer);

        // Calculate min, max and average values (sample fewer points)
        let min = 0, max = 0, sum = 0;
        let zeroCount = 0;

        // Sample every 20th sample to save processing time
        const stride = Math.max(20, Math.floor(numSamples / 100));
        let sampleCount = 0;

        for (let i = 0; i < numSamples; i += stride) {
            const sample = view.getInt16(i * 2, true);
            min = Math.min(min, sample);
            max = Math.max(max, sample);
            sum += sample;
            if (sample === 0) zeroCount++;
            sampleCount++;
        }

        const avg = sum / sampleCount;

        console.log(`Audio data analysis (${audioBuffer.byteLength} bytes, ${numSamples} samples):`);
        console.log(`- Min: ${min}, Max: ${max}, Avg: ${avg.toFixed(2)}`);
        console.log(`- Zero samples: ${zeroCount} (${(zeroCount/sampleCount*100).toFixed(2)}%)`);

        // Check for potential issues
        if (Math.abs(avg) > 1000) {
            console.warn("Warning: Large DC offset detected in audio data");
        }
        if (max - min < 1000) {
            console.warn("Warning: Low dynamic range in audio - might be silence or very quiet");
        }
    } catch (e) {
        console.error("Error analyzing audio data:", e);
    }
}

// Noise detection and management functions
function detectNoiseLevel(audioBuffer) {
    try {
        if (audioBuffer.byteLength < 256) return 0;

        const numSamples = Math.floor(audioBuffer.byteLength / 2);
        const view = new DataView(audioBuffer);
        
        // Calculate RMS (Root Mean Square) for noise level
        let sumSquares = 0;
        let count = 0;
        
        // Sample every 10th sample for efficiency
        for (let i = 0; i < numSamples; i += 10) {
            const sample = view.getInt16(i * 2, true) / 32768.0; // Normalize to [-1, 1]
            sumSquares += sample * sample;
            count++;
        }
        
        const rms = Math.sqrt(sumSquares / count);
        return rms;
    } catch (e) {
        console.error("Error detecting noise level:", e);
        return 0;
    }
}

function analyzeEnvironmentNoise() {
    if (noiseLevels.length === 0) return;
    
    // Calculate average noise level
    const avgNoise = noiseLevels.reduce((a, b) => a + b, 0) / noiseLevels.length;
    currentNoiseLevel = avgNoise;
    
    // Determine if environment is noisy
    const wasNoisy = isNoisyEnvironment;
    isNoisyEnvironment = avgNoise > NOISE_LEVEL_THRESHOLD;
    
    console.log(`🔊 Noise analysis: avg=${avgNoise.toFixed(4)}, threshold=${NOISE_LEVEL_THRESHOLD}, noisy=${isNoisyEnvironment}`);
    
    // If environment changed from quiet to noisy, adjust VAD settings
    if (!wasNoisy && isNoisyEnvironment) {
        console.log("🔊 Noisy environment detected, adjusting VAD settings");
        adjustVADForNoisy();
        showNoiseWarning();
    } else if (wasNoisy && !isNoisyEnvironment) {
        console.log("🔇 Environment is now quieter, resetting VAD settings");
        adjustVADForQuiet();
        hideNoiseWarning();
    }
    
    // Clear old samples to prevent memory buildup
    if (noiseLevels.length > NOISE_SAMPLES_COUNT * 2) {
        noiseLevels = noiseLevels.slice(-NOISE_SAMPLES_COUNT);
    }
}

function adjustVADForNoisy() {
    if (!geminiWebSocket || geminiWebSocket.readyState !== WebSocket.OPEN) return;
    
    const vadConfig = {
        setup: {
            model: GEMINI_LIVE_MODEL,
            generation_config: {
                response_modalities: ["AUDIO"],
                speech_config: {
                    voice_config: {
                        prebuilt_voice_config: {
                            voice_name: currentGeminiVoice
                        }
                    }
                },
                system_instruction: {
                    parts: [
                        {
                            text: createVoiceSystemPrompt()
                        }
                    ]
                },
                output_audio_transcription: {},
                input_audio_transcription: {},
                realtimeInputConfig: {
                    automaticActivityDetection: {
                        disabled: false,
                        startOfSpeechSensitivity: "START_SENSITIVITY_MEDIUM", // Reduced from HIGH
                        endOfSpeechSensitivity: "END_SENSITIVITY_MEDIUM",     // Increased from LOW
                        prefixPaddingMs: 200,  // Increased from 50
                        silenceDurationMs: 1000 // Increased from 500
                    },
                    activityHandling: "START_OF_ACTIVITY_INTERRUPTS",
                    turnCoverage: "TURN_INCLUDES_ALL_INPUT"
                }
            }
        }
    };
    
    console.log("🔧 Sending adjusted VAD config for noisy environment");
    geminiWebSocket.send(JSON.stringify(vadConfig));
}

function adjustVADForQuiet() {
    if (!geminiWebSocket || geminiWebSocket.readyState !== WebSocket.OPEN) return;
    
    const vadConfig = {
        setup: {
            model: GEMINI_LIVE_MODEL,
            generation_config: {
                response_modalities: ["AUDIO"],
                speech_config: {
                    voice_config: {
                        prebuilt_voice_config: {
                            voice_name: currentGeminiVoice
                        }
                    }
                },
                system_instruction: {
                    parts: [
                        {
                            text: createVoiceSystemPrompt()
                        }
                    ]
                },
                output_audio_transcription: {},
                input_audio_transcription: {},
                realtimeInputConfig: {
                    automaticActivityDetection: {
                        disabled: false,
                        startOfSpeechSensitivity: "START_SENSITIVITY_HIGH", // Back to HIGH
                        endOfSpeechSensitivity: "END_SENSITIVITY_LOW",      // Back to LOW
                        prefixPaddingMs: 50,   // Back to 50
                        silenceDurationMs: 500  // Back to 500
                    },
                    activityHandling: "START_OF_ACTIVITY_INTERRUPTS",
                    turnCoverage: "TURN_INCLUDES_ALL_INPUT"
                }
            }
        }
    };
    
    console.log("🔧 Sending adjusted VAD config for quiet environment");
    geminiWebSocket.send(JSON.stringify(vadConfig));
}

function showNoiseWarning() {
    const now = Date.now();
    // Don't show warning more than once per minute
    if (now - lastNoiseWarning < 60000) return;
    
    lastNoiseWarning = now;
    addMessageToChat("🔊 I notice there's background noise. For better conversation quality, consider finding a quieter location or switching to text chat.", "ai");
}

function hideNoiseWarning() {
    // Could add logic to remove the warning message if needed
}

function handleInterruption() {
    interruptionCount++;
    console.log(`🚫 Interruption detected (count: ${interruptionCount})`);
    
    // If we're in a noisy environment and have multiple interruptions, suggest text chat
    if (isNoisyEnvironment && interruptionCount >= INTERRUPTION_THRESHOLD && !hasOfferedTextChat) {
        hasOfferedTextChat = true;
        setTimeout(() => {
            addMessageToChat(
                "🔄 I'm having trouble with the audio quality due to background noise. " +
                "Would you like to switch to text chat for a better experience? " +
                "You can end this voice call and use the text chat below.",
                "ai"
            );
        }, 1000);
    }
}

function startNoiseMonitoring() {
    if (noiseAnalysisTimer) {
        clearInterval(noiseAnalysisTimer);
    }
    
    noiseAnalysisTimer = setInterval(() => {
        if (currentCallState === 'active') {
            analyzeEnvironmentNoise();
        }
    }, NOISE_ANALYSIS_INTERVAL);
    
    console.log("🔊 Started noise monitoring");
}

function stopNoiseMonitoring() {
    if (noiseAnalysisTimer) {
        clearInterval(noiseAnalysisTimer);
        noiseAnalysisTimer = null;
    }
    
    // Reset noise management state
    noiseLevels = [];
    currentNoiseLevel = 0;
    interruptionCount = 0;
    isNoisyEnvironment = false;
    hasOfferedTextChat = false;
    
    console.log("🔇 Stopped noise monitoring and reset state");
}

// Helper function to process JSON messages and extract audio
function processJsonMessageForAudio(jsonMessage) {
    let audioDataFound = false;

    // Direct audio in base64 format
    if (jsonMessage.audio && typeof jsonMessage.audio === 'string') {
        console.log("Found direct audio property in response");
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

                console.log("Found inlineData in serverContent.modelTurn.parts");
                if (part.inlineData.data) {
                    const audioData = base64ToArrayBuffer(part.inlineData.data);
                    queueAudioForPlayback(audioData);
                    audioDataFound = true;
                }
            }

            // Case 2: Audio data within speech field
            if (part.speech && part.speech.audioData) {
                console.log("Found audio data in speech field");
                const audioData = base64ToArrayBuffer(part.speech.audioData);
                queueAudioForPlayback(audioData);
                audioDataFound = true;
            }

            // Case 3: Audio in generic data field
            if (part.data) {
                console.log("Found data field in part, checking for audio");
                // First attempt: Direct audio data
                if (part.data.audioData || part.data.audio) {
                    const audioDataField = part.data.audioData || part.data.audio;
                    if (typeof audioDataField === 'string' && audioDataField.length > 100) {
                        console.log("Found audio data in part.data.audioData or part.data.audio");
                        const audioData = base64ToArrayBuffer(audioDataField);
                        queueAudioForPlayback(audioData);
                        audioDataFound = true;
                    }
                }

                // Second attempt: Data within a content field
                if (part.data.content) {
                    // Check if there's a meaningful content object
                    if (typeof part.data.content === 'object') {
                        // Try to find audio in fields
                        const content = part.data.content;
                        if (content.audioData || content.audio) {
                            const contentAudio = content.audioData || content.audio;
                            if (typeof contentAudio === 'string' && contentAudio.length > 100) {
                                console.log("Found audio in part.data.content.audioData/audio");
                                const audioData = base64ToArrayBuffer(contentAudio);
                                queueAudioForPlayback(audioData);
                                audioDataFound = true;
                            }
                        }
                    }
                }
            }
        }
    }

    return audioDataFound;
}

// Function to handle tool calls from the model
async function handleToolCalls(functionCalls) {
    if (!functionCalls || !Array.isArray(functionCalls) || functionCalls.length === 0) {
        return;
    }


    for (const functionCall of functionCalls) {
        try {
            const functionName = functionCall.name;
            const functionArgs = functionCall.args || {};

            if (functionName === "process_query_with_rag") {
                await handleRagSearch(functionArgs, functionCall.id);
            } else if (functionName === "get_current_time") {
                await handleGetCurrentTime(functionArgs, functionCall.id);
            } else if (functionName === "google_search") {
                // For Google Search, we let Gemini's native search handle it

                addMessageToChat(`I'm searching for information about "${functionArgs.query || 'your question'}"...`, 'ai');

                // Send an acknowledgment back
                if (geminiWebSocket && geminiWebSocket.readyState === WebSocket.OPEN) {
                    const searchResponse = {
                        tool_response: {
                            function_responses: [{
                                name: "google_search",
                                id: functionCall.id,
                                response: {
                                    status: "searching",
                                    query: functionArgs.query || ""
                                }
                            }]
                        }
                    };

                    geminiWebSocket.send(JSON.stringify(searchResponse));
                }
            } else {
                console.warn(`Unknown function call: ${functionName}`);
            }
        } catch (error) {
            console.error("Error handling function call:", error);
            addMessageToChat("I'm sorry, I encountered an error while processing your request. Could you please try asking again?", "ai");
        }
    }
}

// Function to handle get_current_time function calls
async function handleGetCurrentTime(args, functionCallId) {
    
    try {
        // Get property context for timezone detection
        const propertyContext = window.propertyDetails || {};
        
        // Call the server-side get_current_time function
        const response = await fetch('/api/voice-call/get-current-time', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                property_context: propertyContext
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const timeResult = await response.json();
        
        // Send the time result back to Gemini as a function response
        const functionResponse = {
            tool_response: {
                function_responses: [{
                    name: "get_current_time",
                    id: functionCallId,
                    response: timeResult
                }]
            }
        };
        
        if (geminiWebSocket && geminiWebSocket.readyState === WebSocket.OPEN) {
            geminiWebSocket.send(JSON.stringify(functionResponse));
        } else {
            console.error("WebSocket not ready for function response");
        }
        
    } catch (error) {
        console.error("Error handling get_current_time:", error);
        
        // Send error message to Gemini
        const errorResponse = {
            tool_response: {
                function_responses: [{
                    name: "get_current_time",
                    id: functionCallId,
                    response: {
                        error: error.message,
                        message: "Unable to retrieve current time"
                    }
                }]
            }
        };
        
        geminiWebSocket.send(JSON.stringify(errorResponse));
    }
}

// Handle RAG search using process_query_with_rag tool
async function handleRagSearch(args, functionCallId) {

    try {
        const queryText = args.query_text;
        const propertyId = args.property_id || getConfirmedPropertyId();

        if (!queryText) {
            console.error("No query text provided for RAG search");
            addMessageToChat("I'm sorry, I couldn't process your question properly. Could you please ask again?", "ai");
            return;
        }

        if (!propertyId) {
            console.error("No property ID provided for RAG search");
            addMessageToChat("I'm sorry, I couldn't determine which property you're asking about. Please try again.", "ai");
            return;
        }

        // Show a loading message
        addMessageToChat(`I'm looking up information about "${queryText}" for this property...`, "ai");

        // In a full implementation, we would call a backend API to perform the RAG search
        // For now, just return some information from the property details we have
        let response = "";

        if (window.propertyDetails) {
            if (queryText.toLowerCase().includes("wifi")) {
                response = `The WiFi network name is ${window.propertyDetails.wifiNetwork || "not specified"} and the password is ${window.propertyDetails.wifiPassword || "not specified"}.`;
            } else if (queryText.toLowerCase().includes("check")) {
                response = `Check-in time is ${window.propertyDetails.checkInTime || "flexible"} and check-out time is ${window.propertyDetails.checkOutTime || "flexible"}.`;
            } else if (queryText.toLowerCase().includes("address")) {
                response = `The property address is ${window.confirmedPropertyAddress || window.propertyDetails.address || "not specified"}.`;
            } else {
                response = `I don't have specific information about "${queryText}" for this property. Is there something else I can help you with?`;
            }
        } else {
            response = "I don't have detailed information about this property yet. Is there something else I can help you with?";
        }

        // Send response back to Gemini
        if (geminiWebSocket && geminiWebSocket.readyState === WebSocket.OPEN) {
            const ragResponse = {
                tool_response: {
                    function_responses: [{
                        name: "process_query_with_rag",
                        id: functionCallId,
                        response: {
                            response: response,
                            has_context: true
                        }
                    }]
                }
            };

            geminiWebSocket.send(JSON.stringify(ragResponse));
        } else {
            console.error("WebSocket not available to send RAG response");
            addMessageToChat(response, "ai");
        }
    } catch (error) {
        console.error("Error in RAG Search:", error);
        addMessageToChat("I'm sorry, I encountered an error while searching for property information. Could you please try asking again?", "ai");
    }
}

// Function to process JSON messages from Gemini
function processGeminiJsonMessage(jsonMessage) {
    // Debug: Log the entire message structure to understand what we're receiving (only for function calls)
    if (jsonMessage.toolCall?.functionCalls || jsonMessage.serverContent?.modelTurn?.functionCalls) {
        console.log("🔍 Full JSON message from Gemini:", JSON.stringify(jsonMessage, null, 2));
    }
    
    // Check for setup completion confirmation
    if (jsonMessage.setupComplete) {
        console.log("Gemini setup complete:", jsonMessage.setupComplete);
        return;
    }

    // Check for interruption event
    if (jsonMessage.serverContent && jsonMessage.serverContent.interrupted === true) {
        console.log("User interrupted - clearing audio queue");
        // Handle interruption for noise management
        handleInterruption();
        // Stop active playback immediately and aggressively
        stopAllAudioPlayback();
        addMessageToChat("Listening...", "ai", "system");
        return; // Exit immediately to prevent processing any audio in this message
    }

    // Capture session resumption handle updates from server
    if (jsonMessage.sessionResumptionUpdate && (jsonMessage.sessionResumptionUpdate.newHandle || jsonMessage.sessionResumptionUpdate.token || jsonMessage.sessionResumptionUpdate.handle)) {
        sessionResumptionHandle = jsonMessage.sessionResumptionUpdate.newHandle || jsonMessage.sessionResumptionUpdate.token || jsonMessage.sessionResumptionUpdate.handle;
        console.log("Received session resumption handle:", sessionResumptionHandle);
    }

    // Detect model turn completion to prompt listening state
    if (jsonMessage.serverContent && (jsonMessage.serverContent.turnComplete === true || jsonMessage.serverContent.turn_complete === true)) {
        console.log("Model turn complete");
        addMessageToChat("Listening...", "ai", "system");
    }

    // Handle transcriptions
    if (jsonMessage.serverContent) {
        // Check for output transcription (AI speech transcription)
        if (jsonMessage.serverContent.outputTranscription) {
            handleTranscriptionFragment(jsonMessage.serverContent.outputTranscription.text, 'ai');
        }
        // Alternative property name check
        if (jsonMessage.serverContent.output_transcription) {
            handleTranscriptionFragment(jsonMessage.serverContent.output_transcription.text, 'ai');
        }

        // Check for input transcription (user speech transcription)
        if (jsonMessage.serverContent.inputTranscription) {
            handleTranscriptionFragment(jsonMessage.serverContent.inputTranscription.text, 'user');
        }
        // Alternative property name check
        if (jsonMessage.serverContent.input_transcription) {
            handleTranscriptionFragment(jsonMessage.serverContent.input_transcription.text, 'user');
        }
    }

    // Also check for transcriptions at the top level of the message
    if (jsonMessage.outputTranscription) {
        handleTranscriptionFragment(jsonMessage.outputTranscription.text, 'ai');
    }
    if (jsonMessage.output_transcription) {
        handleTranscriptionFragment(jsonMessage.output_transcription.text, 'ai');
    }
    if (jsonMessage.inputTranscription) {
        handleTranscriptionFragment(jsonMessage.inputTranscription.text, 'user');
    }
    if (jsonMessage.input_transcription) {
        handleTranscriptionFragment(jsonMessage.input_transcription.text, 'user');
    }

    // Extract and handle text content (for display in chat)
    let textExtracted = false;

    // Check for direct text property
    if (jsonMessage.text) {
        console.log("Received text response:", jsonMessage.text);
        addMessageToChat(jsonMessage.text, 'ai');
        textExtracted = true;
    }

    // Check common serverContent format
    if (jsonMessage.serverContent && jsonMessage.serverContent.modelTurn) {
        const modelTurn = jsonMessage.serverContent.modelTurn;

        // Check for text in parts
        if (modelTurn.parts && Array.isArray(modelTurn.parts)) {
            for (const part of modelTurn.parts) {
                // Check for text in part
                if (part.text) {
                    console.log("Found text in modelTurn.parts:", part.text);
                    addMessageToChat(part.text, 'ai');
                    textExtracted = true;
                }

                // Check for finalized text in part.transitions
                if (part.transitions && part.transitions.finalizedText) {
                    console.log("Found finalized text:", part.transitions.finalizedText);
                    addMessageToChat(part.transitions.finalizedText, 'ai');
                    textExtracted = true;
                }
            }
        }

        // Check for candidates array
        if (modelTurn.candidates && Array.isArray(modelTurn.candidates)) {
            for (const candidate of modelTurn.candidates) {
                if (candidate.content && candidate.content.parts) {
                    for (const part of candidate.content.parts) {
                        if (part.text) {
                            console.log("Found text in candidates:", part.text);
                            addMessageToChat(part.text, 'ai');
                            textExtracted = true;
                        }
                    }
                }
            }
        }
    }

    // Check for function calls - debug all possible locations
    console.log("🔍 Checking for function calls in message structure...");
    console.log("  - jsonMessage.serverContent:", jsonMessage.serverContent);
    console.log("  - jsonMessage.serverContent?.modelTurn:", jsonMessage.serverContent?.modelTurn);
    console.log("  - jsonMessage.serverContent?.modelTurn?.functionCalls:", jsonMessage.serverContent?.modelTurn?.functionCalls);
    console.log("  - jsonMessage.toolCall:", jsonMessage.toolCall);
    
    // Check multiple possible locations for function calls
    let functionCalls = null;
    
    // Location 1: toolCall.functionCalls (ACTUAL LOCATION BASED ON LOGS)
    if (jsonMessage.toolCall?.functionCalls) {
        functionCalls = jsonMessage.toolCall.functionCalls;
        console.log("✅ Function calls found in toolCall.functionCalls:", functionCalls);
    }
    // Location 2: serverContent.modelTurn.functionCalls
    else if (jsonMessage.serverContent?.modelTurn?.functionCalls) {
        functionCalls = jsonMessage.serverContent.modelTurn.functionCalls;
        console.log("✅ Function calls found in serverContent.modelTurn.functionCalls:", functionCalls);
    }
    // Location 3: serverContent.functionCalls
    else if (jsonMessage.serverContent?.functionCalls) {
        functionCalls = jsonMessage.serverContent.functionCalls;
        console.log("✅ Function calls found in serverContent.functionCalls:", functionCalls);
    }
    // Location 4: modelTurn.functionCalls
    else if (jsonMessage.modelTurn?.functionCalls) {
        functionCalls = jsonMessage.modelTurn.functionCalls;
        console.log("✅ Function calls found in modelTurn.functionCalls:", functionCalls);
    }
    // Location 5: functionCalls at root level
    else if (jsonMessage.functionCalls) {
        functionCalls = jsonMessage.functionCalls;
        console.log("✅ Function calls found in root functionCalls:", functionCalls);
    }
    // Location 6: Check for function calls in parts
    else if (jsonMessage.serverContent?.modelTurn?.parts) {
        for (const part of jsonMessage.serverContent.modelTurn.parts) {
            if (part.functionCall) {
                if (!functionCalls) functionCalls = [];
                functionCalls.push(part.functionCall);
                console.log("✅ Function call found in parts:", part.functionCall);
            }
        }
    }
    
    if (functionCalls) {
        console.log("🎯 Function calls detected in response:", functionCalls);
        // Handle tool calls if present
        handleToolCalls(functionCalls);
    } else {
        console.log("❌ No function calls found in any expected location");
        // Additional debug: Check if there are any function-related fields at all
        const allKeys = Object.keys(jsonMessage);
        console.log("🔍 All top-level keys in message:", allKeys);
        if (jsonMessage.serverContent) {
            const serverKeys = Object.keys(jsonMessage.serverContent);
            console.log("🔍 All serverContent keys:", serverKeys);
        }
    }

    // Extract audio data from the message
    processJsonMessageForAudio(jsonMessage);
}

// Helper function to handle transcription fragments and accumulate them into complete sentences
function handleTranscriptionFragment(fragment, type) {
    if (!fragment || typeof fragment !== 'string') {
        return;
    }

    // Clean up the fragment (but don't trim - preserve any spaces Gemini includes)
    const cleanFragment = fragment;
    if (!cleanFragment) {
        return;
    }

    // Only log fragments occasionally to reduce console noise (every 3rd fragment)
    if (Math.random() < 0.33) {
        console.log(`📝 Fragment (${type}):`, JSON.stringify(cleanFragment));
    }

    if (type === 'ai') {
        // Accumulate AI transcription without adding any spaces - just concatenate
        currentAITranscription += cleanFragment;

        // Clear existing timeout
        if (aiTranscriptionTimeout) {
            clearTimeout(aiTranscriptionTimeout);
        }

        // Set timeout to handle complete transcription
        aiTranscriptionTimeout = setTimeout(() => {
            if (currentAITranscription.trim()) {
                // Handle the complete AI transcription
                handleCompleteVoiceTranscription('assistant', currentAITranscription.trim());
                currentAITranscription = "";
            }
        }, TRANSCRIPTION_TIMEOUT);

    } else if (type === 'user') {
        // Accumulate user transcription without adding any spaces - just concatenate
        currentUserTranscription += cleanFragment;

        // Clear existing timeout
        if (userTranscriptionTimeout) {
            clearTimeout(userTranscriptionTimeout);
        }

        // Set timeout to handle complete transcription
        userTranscriptionTimeout = setTimeout(() => {
            if (currentUserTranscription.trim()) {
                // Handle the complete user transcription
                handleCompleteVoiceTranscription('user', currentUserTranscription.trim());
                currentUserTranscription = "";
            }
        }, TRANSCRIPTION_TIMEOUT);
    }
}

// Function to check if voice call is ready
function checkVoiceCallReadiness() {
    // We need both a property ID and a user ID to enable voice calls
    const propertyId = getConfirmedPropertyId();
    const userId = window.CURRENT_USER_ID;

    console.log("=== CHECK VOICE CALL READINESS ===");
    console.log(`propertyReady: ${!!propertyId}, propertyId: ${propertyId}`);
    console.log(`userIdReady: ${!!userId}, userId: ${userId}`);
    console.log(`currentCallState: ${currentCallState}`);

    // If a call is in any non-idle state, keep the button enabled as "End Call"
    if (currentCallState !== 'idle') {
        updateVoiceCallButton(true, false, "End Call");
        return true;
    }

    // Only enable the button (to start a call) if we have both IDs and connection is sufficient
    if (propertyId && userId && isConnectionSufficientForVoice()) {
        console.log("Voice call is ready, enabling button");
        updateVoiceCallButton(false, false, "Call Staycee");
        return true;
    } else {
        // Update button text based on what's missing
        let statusText = "Loading...";
        if (!userId) statusText = "Login Required";
        else if (!propertyId) statusText = "Loading Property...";
        else if (!isConnectionSufficientForVoice()) statusText = "Poor Connection";

        console.log(`Voice call not ready: ${statusText}`);
        updateVoiceCallButton(false, true, statusText);
        return false;
    }
}

// Listen for property ID changes
document.addEventListener('propertyIdChanged', (event) => {
    const { propertyId, previousPropertyId } = event.detail;
    console.log(`Property ID changed event received in voice call module: ${previousPropertyId || 'unset'} -> ${propertyId}`);

    // Check if voice call button needs to be updated
    checkVoiceCallReadiness();
});

// Export functions for use in other modules
export {
    initializeVoiceCall,
    handleVoiceCallClick,
    stopVoiceCall,
    updateVoiceCallButton,
    currentCallState,
    GEMINI_VOICES,
    currentGeminiVoice,
    initializeVoiceSelector,
    createVoiceSystemPrompt,
    handleToolCalls,
    processJsonMessageForAudio,
    checkVoiceCallReadiness
};

// === Voice Conversation Management Functions ===

/**
 * Create a voice conversation session in DynamoDB
 */
async function createVoiceConversationSession() {
    try {
        const propertyId = getConfirmedPropertyId();
        const userId = window.CURRENT_USER_ID;
        const guestName = window.GUEST_NAME;

        if (!propertyId || !userId) {
            console.error("Cannot create voice conversation session: missing property ID or user ID");
            return null;
        }

        console.log("Creating voice conversation session...");

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
        console.log("Phone number for voice conversation:", phoneNumber || "Not available");

        const requestBody = {
            property_id: propertyId,
            user_id: userId,
            guest_name: guestName,
            channel: 'voice_call'
        };

        // Include reservation ID if found
        if (reservationId) {
            requestBody.reservation_id = reservationId;
            console.log("Including reservation ID in voice conversation:", reservationId);
        }

        // Include phone number if available
        if (phoneNumber) {
            requestBody.phone_number = phoneNumber;
            console.log("Including phone number in voice conversation:", phoneNumber);
        }

        const response = await fetch('/api/conversations/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin',
            body: JSON.stringify(requestBody)
        });

        if (response.ok) {
            const data = await response.json();
            if (data.success && data.conversation_id) {
                voiceConversationId = data.conversation_id;
                voiceSessionActive = true;
                console.log("Voice conversation session created:", voiceConversationId);
                return voiceConversationId;
            }
        }

        console.error("Failed to create voice conversation session:", response.status);
        return null;
    } catch (error) {
        console.error("Error creating voice conversation session:", error);
        return null;
    }
}

/**
 * Store a voice transcription message to DynamoDB (consolidated with diagnostics)
 */
async function storeVoiceMessage(role, text) {
    if (!voiceConversationId || !voiceSessionActive) {
        console.warn("No active voice conversation session, cannot store message");
        return false;
    }

    try {
        console.log(`Storing ${role} voice transcript:`, text.substring(0, 50) + (text.length > 50 ? '...' : ''));

        const messageData = {
            session_id: voiceConversationId,
            role: role,
            text: text,
            timestamp: new Date().toISOString()
        };

        const response = await fetch('/api/voice-call/transcript', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin',
            body: JSON.stringify(messageData)
        });

        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                console.log(`✅ Successfully stored ${role} voice transcript to diagnostics session`);
                return true;
            } else {
                console.error("API returned failure:", data);
                return false;
            }
        } else {
            const errorText = await response.text();
            console.error("Failed to store voice transcript:", response.status, response.statusText, errorText);
            return false;
        }
    } catch (error) {
        console.error("Error storing voice transcript:", error);
        return false;
    }
}

/**
 * Display a voice transcription in the chat UI
 */
function displayVoiceTranscription(role, text) {
    // Pre-process the text to filter out foreign characters based on current language
    const filteredText = preprocessTranscript(text, currentGeminiLanguage);
    
    // Use the existing displayChatMessage function if available
    if (typeof window.displayChatMessage === 'function') {
        // Create message data that indicates this is a voice message
        const messageData = {
            channel: 'voice_call',
            conversation_id: voiceConversationId
        };

        // Display the message with voice indicator
        window.displayChatMessage(role, filteredText, null, false, messageData);
        console.log(`🎯 Displayed ${role} voice transcription in chat UI`);
    } else {
        // Fallback: use addMessageToChat if displayChatMessage is not available
        if (typeof addMessageToChat === 'function') {
            addMessageToChat(filteredText, role === 'user' ? 'user' : 'ai');
            console.log(`🎯 Displayed ${role} voice transcription in chat (fallback method)`);
        } else {
            console.warn("❌ No chat display function available for voice transcription");
        }
    }
}

/**
 * Handle complete voice transcription - store and display
 */
async function handleCompleteVoiceTranscription(role, text) {
    if (!text || !text.trim()) {
        return;
    }

    const cleanText = text.trim();
    console.log(`📝 ${role === 'user' ? 'User' : 'AI'} Voice Complete:`, cleanText);

    // Store the transcription in DynamoDB
    await storeVoiceMessage(role, cleanText);

    // Display the transcription in the chat UI
    displayVoiceTranscription(role, cleanText);
}

/**
 * Clean up voice conversation session
 */
function cleanupVoiceConversationSession() {
    if (voiceConversationId) {
        console.log("Cleaning up voice conversation session:", voiceConversationId);
        voiceConversationId = null;
    }
    voiceSessionActive = false;
}