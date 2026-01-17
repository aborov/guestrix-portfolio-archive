
// Import config
import config from './config.js';

// Debug logging
console.log('Script loaded');
console.log('Config loaded');

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded');

    // Initialize lazy loading enhancement
    initializeLazyLoading();

    // Get all waitlist buttons
    const waitlistButtons = [
        document.getElementById('joinWaitlistButton'),
        document.getElementById('joinWaitlistButton1'),
        document.getElementById('joinWaitlistButton2')
    ].filter(button => button); // Filter out null buttons

    const waitlistModal = document.getElementById('waitlistModal');
    const closeButton = document.querySelector('.modal-close');
    const waitlistForm = document.getElementById('waitlistForm');

    // Only set up modal functionality if modal exists
    if (waitlistModal && closeButton) {
        // Show modal for all waitlist buttons
        waitlistButtons.forEach(button => {
            button.addEventListener('click', () => {
                waitlistModal.style.display = 'flex';
            });
        });

        // Close modal
        closeButton.addEventListener('click', () => {
            waitlistModal.style.display = 'none';
        });

        // Close modal when clicking outside
        window.addEventListener('click', (event) => {
            if (event.target === waitlistModal) {
                waitlistModal.style.display = 'none';
            }
        });
    }

    // Handle form submission
    if (waitlistForm) {
        waitlistForm.addEventListener('submit', async (event) => {
            event.preventDefault();

            const firstName = document.getElementById('firstName').value;
            const lastName = document.getElementById('lastName').value;
            const email = document.getElementById('waitlistEmail').value;
            const message = document.getElementById('message').value || '';

            console.log('Form data being sent:', { firstName, lastName, email, message });

            try {
                // Using Amplify API endpoint to add to waitlist
                const response = await fetch(`${config.api.endpoint}/waitlist`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ firstName, lastName, email, message })
                });

                console.log('Response status:', response.status);
                const data = await response.json();
                console.log('Response data:', data);

                if (response.ok) {
                    showSuccessModal();
                    // Only hide modal if it exists
                    if (waitlistModal) {
                        waitlistModal.style.display = 'none';
                    }
                    waitlistForm.reset();
                } else {
                    alert(data.message || 'Failed to submit. Please try again.');
                }
            } catch (error) {
                console.error('Error:', error);
                alert('An error occurred. Please try again later.');
            }
        });
    }
});

// Waitlist Modal functionality
const waitlistModal = document.getElementById('waitlistModal');
const waitlistForm = document.getElementById('waitlistForm');

// Make these functions globally accessible
window.showWaitlistModal = function() {
    waitlistModal.style.display = 'flex';
}

window.closeWaitlistModal = function() {
    waitlistModal.style.display = 'none';
}

// Validation functions
function validateName(name, fieldName) {
    if (!name || name.trim().length < 2) {
        return `${fieldName} must be at least 2 characters long`;
    }
    if (name.length > 50) {
        return `${fieldName} must be less than 50 characters`;
    }
    if (!/^[A-Za-z\s\-]+$/.test(name)) {
        return `${fieldName} can only contain letters, spaces, and hyphens`;
    }
    return null;
}

function validateEmail(email) {
    if (!email) {
        return 'Email is required';
    }
    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    if (!emailRegex.test(email)) {
        return 'Please enter a valid email address';
    }
    return null;
}

// Success Modal Functions
function showSuccessModal() {
    const successModal = document.getElementById('successModal');
    if (successModal) {
        successModal.style.display = 'block';
    }
}

function closeSuccessModal() {
    const successModal = document.getElementById('successModal');
    if (successModal) {
        successModal.style.display = 'none';
    }
}

// Make functions globally accessible
window.showSuccessModal = showSuccessModal;
window.closeSuccessModal = closeSuccessModal;

// Close modal when clicking outside
window.addEventListener('click', (event) => {
    const successModal = document.getElementById('successModal');
    if (event.target === successModal) {
        closeSuccessModal();
    }
});

// Lazy Loading Enhancement
function initializeLazyLoading() {
    const lazyImages = document.querySelectorAll('img[loading="lazy"]');

    // Add intersection observer for smooth loading
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.addEventListener('load', () => {
                        img.classList.add('loaded');
                    });
                    // If image is already loaded
                    if (img.complete) {
                        img.classList.add('loaded');
                    }
                    observer.unobserve(img);
                }
            });
        });

        lazyImages.forEach(img => {
            imageObserver.observe(img);
        });
    } else {
        // Fallback for browsers without IntersectionObserver
        lazyImages.forEach(img => {
            img.classList.add('loaded');
        });
    }
}

// FAQ Interaction
document.addEventListener('DOMContentLoaded', function() {
    const faqItems = document.querySelectorAll('.faq-item');
    
    faqItems.forEach(item => {
        const question = item.querySelector('.faq-question');
        
        question.addEventListener('click', () => {
            const isActive = item.classList.contains('active');
            
            // Close all other items
            faqItems.forEach(otherItem => {
                otherItem.classList.remove('active');
            });
            
            // Toggle current item
            if (!isActive) {
                item.classList.add('active');
            }
        });
    });
});