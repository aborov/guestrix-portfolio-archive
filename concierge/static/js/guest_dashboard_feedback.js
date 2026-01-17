/*
 * Feedback modal functionality for the guest dashboard
 */

// Feedback state management
let feedbackState = {
    messageCount: 0,
    enjoymentRating: null,
    accuracyRating: null,
    sessionId: null,
    isModalVisible: false,
    hasSubmittedFeedback: false,
    isVoiceCallActive: false,
    currentSessionFeedbackShown: false,
    lastVoiceFeedbackSessionId: null
};

// Initialize feedback system
export function initializeFeedback() {
    console.log("Initializing feedback system...");
    
    // Set up event listeners
    setupFeedbackEventListeners();
    setupAutoDismissListeners();
    setupVoiceCallEndListener();
    
    // Reset feedback state
    resetFeedbackState();
    
    console.log("Feedback system initialized");
}

// Reset feedback state for new session
export function resetFeedbackState() {
    feedbackState.messageCount = 0;
    feedbackState.enjoymentRating = null;
    feedbackState.accuracyRating = null;
    feedbackState.sessionId = null;
    feedbackState.isModalVisible = false;
    feedbackState.hasSubmittedFeedback = false;
    feedbackState.isVoiceCallActive = false;
    feedbackState.currentSessionFeedbackShown = false;
    
    // Reset modal UI
    resetFeedbackModalUI();
}

// Set up all event listeners for feedback functionality
function setupFeedbackEventListeners() {
    // Close modal button
    const closeBtn = document.getElementById('close-feedback-modal');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeFeedbackModal);
    }

    // Emoji buttons for enjoyment rating
    const emojiButtons = document.querySelectorAll('.feedback-emoji-btn');
    emojiButtons.forEach(btn => {
        btn.addEventListener('click', handleEmojiSelection);
    });

    // Star buttons for accuracy rating
    const starButtons = document.querySelectorAll('.feedback-star-btn');
    starButtons.forEach(btn => {
        btn.addEventListener('click', handleStarSelection);
    });

    // Submit button
    const submitBtn = document.getElementById('submit-feedback-btn');
    if (submitBtn) {
        submitBtn.addEventListener('click', handleFeedbackSubmission);
    }

    // Auto-dismiss triggers
    setupAutoDismissListeners();

    // Voice call end trigger
    setupVoiceCallEndListener();
}

// Handle emoji selection for enjoyment rating
function handleEmojiSelection(event) {
    const value = parseInt(event.currentTarget.dataset.value);
    feedbackState.enjoymentRating = value;
    
    // Update UI - remove selected class from all emoji buttons
    document.querySelectorAll('.feedback-emoji-btn').forEach(btn => {
        btn.classList.remove('selected');
    });
    
    // Add selected class to clicked button
    event.currentTarget.classList.add('selected');
    
    // Check if we can enable submit button
    updateSubmitButtonState();
}

// Handle star selection for accuracy rating
function handleStarSelection(event) {
    const value = parseInt(event.currentTarget.dataset.value);
    feedbackState.accuracyRating = value;
    
    // Update UI - highlight stars up to selected value
    const starButtons = document.querySelectorAll('.feedback-star-btn');
    starButtons.forEach((btn, index) => {
        if (index < value) {
            btn.classList.add('selected');
        } else {
            btn.classList.remove('selected');
        }
    });
    
    // Check if we can enable submit button
    updateSubmitButtonState();
}

// Update submit button state based on selections
function updateSubmitButtonState() {
    const submitBtn = document.getElementById('submit-feedback-btn');
    if (submitBtn) {
        // Allow submit if at least one of the two ratings is provided
        const hasEnjoyment = feedbackState.enjoymentRating !== null && feedbackState.enjoymentRating !== undefined;
        const hasAccuracy = feedbackState.accuracyRating !== null && feedbackState.accuracyRating !== undefined;
        const canSubmit = hasEnjoyment || hasAccuracy;
        submitBtn.disabled = !canSubmit;
    }
}

// Handle feedback submission
async function handleFeedbackSubmission() {
    // Require at least one rating
    const hasEnjoyment = feedbackState.enjoymentRating !== null && feedbackState.enjoymentRating !== undefined;
    const hasAccuracy = feedbackState.accuracyRating !== null && feedbackState.accuracyRating !== undefined;
    if (!hasEnjoyment && !hasAccuracy) {
        console.warn("Cannot submit feedback - missing ratings");
        return;
    }

    const submitBtn = document.getElementById('submit-feedback-btn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';
    }

    try {
        const resolvedPropertyId = (window.dashboardState && window.dashboardState.propertyId)
            || window.PROPERTY_ID
            || (document.body && document.body.dataset && document.body.dataset.propertyId)
            || (typeof getConfirmedPropertyId === 'function' ? getConfirmedPropertyId() : undefined);

        const payload = {
            sessionId: feedbackState.sessionId,
            userId: window.CURRENT_USER_ID,
            propertyId: resolvedPropertyId
        };
        if (hasEnjoyment) payload.enjoyment = feedbackState.enjoymentRating;
        if (hasAccuracy) payload.accuracy = feedbackState.accuracyRating;

        // Include text conversationId if available globally
        if (window.currentTextConversationId) {
            payload.conversationId = window.currentTextConversationId;
        }

        const success = await submitFeedback(payload);

        if (success) {
            feedbackState.hasSubmittedFeedback = true;
            showFeedbackSuccess();
            setTimeout(() => {
                closeFeedbackModal();
            }, 2000);
        } else {
            showFeedbackError();
        }
    } catch (error) {
        console.error("Error submitting feedback:", error);
        showFeedbackError();
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<span>Let\'s chat again</span><span>👋</span>';
        }
    }
}

// Submit feedback to API
async function submitFeedback(feedbackData) {
    try {
        const response = await fetch('/api/feedback/submit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            credentials: 'same-origin',
            body: JSON.stringify(feedbackData)
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        console.log("Feedback submitted successfully:", result);
        return result.success;
    } catch (error) {
        console.error("Error submitting feedback:", error);
        return false;
    }
}

// Show feedback success message
function showFeedbackSuccess() {
    const submitBtn = document.getElementById('submit-feedback-btn');
    if (submitBtn) {
        submitBtn.innerHTML = '<i class="fas fa-check text-green-500"></i> Thank you!';
        submitBtn.classList.add('bg-green-500');
        submitBtn.classList.remove('bg-persian-green');
    }
}

// Show feedback error message
function showFeedbackError() {
    const submitBtn = document.getElementById('submit-feedback-btn');
    if (submitBtn) {
        submitBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Try again';
        submitBtn.classList.add('bg-red-500');
        submitBtn.classList.remove('bg-persian-green');
        
        setTimeout(() => {
            submitBtn.innerHTML = '<span>Let\'s chat again</span><span>👋</span>';
            submitBtn.classList.remove('bg-red-500');
            submitBtn.classList.add('bg-persian-green');
        }, 3000);
    }
}

// Track message count for text chat
export function incrementMessageCount() {
    // Don't count messages during voice calls
    if (feedbackState.isVoiceCallActive) {
        console.log("Skipping message count - voice call active");
        return;
    }
    
    feedbackState.messageCount++;
    console.log(`Message count: ${feedbackState.messageCount}`);
    
    // Show feedback modal after 5 AI responses (only if not already shown for this session)
    if (feedbackState.messageCount >= 5 && 
        !feedbackState.isModalVisible && 
        !feedbackState.hasSubmittedFeedback && 
        !feedbackState.currentSessionFeedbackShown) {
        console.log("Triggering feedback modal after 5 messages");
        feedbackState.currentSessionFeedbackShown = true;
        showFeedbackModal('text_chat_5_messages');
    }
}

// Trigger feedback modal after voice call ends
export function triggerFeedbackAfterVoiceCall(sessionId) {
    console.log("Voice call ended, checking feedback conditions");
    
    // Set voice call as inactive
    feedbackState.isVoiceCallActive = false;
    
    // Show feedback after EVERY voice call end, but de-duplicate per sessionId
    if (!feedbackState.isModalVisible && feedbackState.lastVoiceFeedbackSessionId !== sessionId) {
        console.log("Triggering feedback modal after voice call end");
        feedbackState.sessionId = sessionId;
        feedbackState.lastVoiceFeedbackSessionId = sessionId;
        showFeedbackModal('voice_call_end');
    } else {
        console.log("Feedback modal not shown - already shown for this voice session or modal visible");
    }
}

// Show feedback modal
function showFeedbackModal(trigger) {
    console.log(`Showing feedback modal (trigger: ${trigger})`);
    
    const modal = document.getElementById('feedback-modal');
    if (modal) {
        feedbackState.isModalVisible = true;
        modal.classList.remove('hidden');
        
        // Reset modal state
        resetFeedbackModalUI();
        
        // Focus on modal for accessibility
        const firstButton = modal.querySelector('.feedback-emoji-btn');
        if (firstButton) {
            firstButton.focus();
        }
    }
}

// Close feedback modal
function closeFeedbackModal() {
    console.log("Closing feedback modal");
    
    const modal = document.getElementById('feedback-modal');
    if (modal) {
        modal.classList.add('hidden');
        feedbackState.isModalVisible = false;
    }
}

// Reset feedback modal UI
function resetFeedbackModalUI() {
    // Clear emoji selections
    document.querySelectorAll('.feedback-emoji-btn').forEach(btn => {
        btn.classList.remove('selected');
    });
    
    // Clear star selections
    document.querySelectorAll('.feedback-star-btn').forEach(btn => {
        btn.classList.remove('selected');
    });
    
    // Reset submit button
    const submitBtn = document.getElementById('submit-feedback-btn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span>Let\'s chat again</span><span>👋</span>';
        submitBtn.classList.remove('bg-green-500', 'bg-red-500');
        submitBtn.classList.add('bg-persian-green');
    }
    
    // Reset feedback state ratings
    feedbackState.enjoymentRating = null;
    feedbackState.accuracyRating = null;
}

// Set up auto-dismiss listeners
function setupAutoDismissListeners() {
    // Auto-dismiss when user starts typing in chat input
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('focus', () => {
            if (feedbackState.isModalVisible) {
                console.log("Auto-dismissing feedback modal - user started typing");
                closeFeedbackModal();
            }
        });
        
        chatInput.addEventListener('input', () => {
            if (feedbackState.isModalVisible) {
                console.log("Auto-dismissing feedback modal - user typing");
                closeFeedbackModal();
            }
        });
    }

    // Auto-dismiss when user clicks "Call Staycee" button
    const voiceCallButton = document.getElementById('voice-call-button');
    if (voiceCallButton) {
        voiceCallButton.addEventListener('click', () => {
            console.log("Voice call button clicked");
            feedbackState.isVoiceCallActive = true;
            
            if (feedbackState.isModalVisible) {
                console.log("Auto-dismissing feedback modal - user starting voice call");
                closeFeedbackModal();
            }
        });
    }
}

// Set up voice call end listener
function setupVoiceCallEndListener() {
    // Listen for voice call end events
    document.addEventListener('voiceCallEnded', (event) => {
        const sessionId = event.detail?.sessionId;
        if (sessionId) {
            triggerFeedbackAfterVoiceCall(sessionId);
        }
    });
}

// Export feedback state for debugging
export function getFeedbackState() {
    return { ...feedbackState };
}

// Mark voice call as active (called when voice call starts)
export function setVoiceCallActive(active = true) {
    feedbackState.isVoiceCallActive = active;
    console.log(`Voice call active: ${active}`);
}

// Reset feedback for new conversation session
export function resetForNewSession() {
    console.log("Resetting feedback for new session");
    feedbackState.messageCount = 0;
    feedbackState.currentSessionFeedbackShown = false;
    feedbackState.hasSubmittedFeedback = false;
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeFeedback);
} else {
    initializeFeedback();
}
