/*
New Host Dashboard JavaScript
Handles three-screen navigation and all host dashboard functionality
*/

// --- Global Variables ---
let currentScreen = 'properties';
let properties = [];
let reservations = [];
let conversations = [];
let calendarView = 'list'; // 'list' or 'timeline'

// Progress tracking state for property import
let progressState = {
    currentProperty: 0,
    totalProperties: 0,
    currentStep: '',
    activityIconIndex: 0,
    activityIconInterval: null
};

// --- Utility Functions ---
// iCal URL validation function
function validateICalUrl(url) {
    if (!url || !url.trim()) {
        return { valid: false, message: "iCal URL is required for reservation management." };
    }

    const trimmedUrl = url.trim();

    // Check if it's a valid URL format
    try {
        const urlObj = new URL(trimmedUrl);

        // Check if it's HTTPS (most calendar services use HTTPS)
        if (urlObj.protocol !== 'https:' && urlObj.protocol !== 'http:') {
            return {
                valid: false,
                message: "iCal URL must be a valid HTTP or HTTPS URL."
            };
        }

        // Check if URL ends with .ics (iCal format)
        const pathname = urlObj.pathname.toLowerCase();
        if (!pathname.endsWith('.ics')) {
            return {
                valid: false,
                message: "iCal URL must end with '.ics' extension. Please make sure you're using the calendar export link, not the regular property page URL."
            };
        }

        // Check for common calendar service patterns
        const hostname = urlObj.hostname.toLowerCase();
        const validHosts = [
            'airbnb.com', 'www.airbnb.com',
            'vrbo.com', 'www.vrbo.com',
            'booking.com', 'www.booking.com',
            'calendar.google.com',
            'outlook.live.com', 'outlook.office365.com',
            'ical.mac.com'
        ];

        const isKnownService = validHosts.some(host => hostname.includes(host)) ||
                             hostname.includes('calendar') ||
                             hostname.includes('ical');

        if (!isKnownService) {
            console.warn('Unknown calendar service:', hostname);
            // Don't block unknown services, just warn
        }

        // Additional check for Airbnb format (most common)
        if (hostname.includes('airbnb.com')) {
            if (!pathname.includes('/calendar/ical/') || !urlObj.search.includes('s=')) {
                return {
                    valid: false,
                    message: "This appears to be an Airbnb URL but not the correct calendar export link. Please go to your Airbnb calendar, click 'Export Calendar', and copy the iCal link that ends with '.ics'."
                };
            }
        }

        return { valid: true, message: "" };

    } catch (error) {
        return {
            valid: false,
            message: "Please enter a valid URL. Example: https://www.airbnb.com/calendar/ical/1234567890.ics?s=abc123"
        };
    }
}

// --- Initialize Dashboard ---
document.addEventListener('DOMContentLoaded', function() {
    console.log('Host Dashboard loaded');
    
    // Initialize the dashboard
    initializeDashboard();
    
    // Set active tab styling
    updateTabStyling();
    
    // Load initial data
    loadProperties();
});

// --- Dashboard Initialization ---
function initializeDashboard() {
    // Set up tab button styles
    const tabButtons = document.querySelectorAll('.tab-button');
    tabButtons.forEach(button => {
        button.classList.add('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
    });
    
    // Set active tab (Properties by default)
    showScreen('properties');
}

// --- Tab Navigation ---
function showScreen(screenName) {
    // Hide all screens
    const screens = document.querySelectorAll('.tab-content');
    screens.forEach(screen => screen.classList.remove('active'));
    
    // Show selected screen
    const selectedScreen = document.getElementById(screenName + '-screen');
    if (selectedScreen) {
        selectedScreen.classList.add('active');
        currentScreen = screenName;
    }
    
    // Update tab button styling
    updateTabStyling();
    
    // Load screen-specific data
    loadScreenData(screenName);
}

function updateTabStyling() {
    const tabButtons = document.querySelectorAll('.tab-button');
    
    tabButtons.forEach(button => {
        button.classList.remove('border-persian-green', 'text-persian-green');
        button.classList.add('border-transparent', 'text-gray-500');
    });
    
    // Set active tab styling
    const activeTab = document.getElementById(currentScreen + '-tab');
    if (activeTab) {
        activeTab.classList.remove('border-transparent', 'text-gray-500');
        activeTab.classList.add('border-persian-green', 'text-persian-green');
    }
}

function loadScreenData(screenName) {
    switch(screenName) {
        case 'properties':
            loadProperties();
            break;
        case 'calendar':
            loadCalendarData();
            break;
        case 'support':
            loadSupportData();
            break;
    }
}

// --- Properties Screen Functions ---
function loadProperties() {
    console.log('Loading properties for host from session user');
    const propertiesGrid = document.getElementById('properties-grid');
    
    if (!propertiesGrid) {
        console.error('Properties grid not found');
        return;
    }
    
    // Show loading state
    propertiesGrid.innerHTML = `
        <div class="col-span-full text-center py-8">
            <div class="loading-spinner mx-auto mb-4"></div>
            <p class="text-gray-600">Loading properties...</p>
        </div>
    `;
    
    // Fetch properties from the API endpoint using session auth
    fetch('/api/user-properties', {
        credentials: 'same-origin'
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => {
                throw new Error(err.error || `HTTP error! status: ${response.status}`);
            }).catch(() => {
                throw new Error(`HTTP error! status: ${response.status}`);
            });
        }
        return response.json();
    })
    .then(data => {
        console.log('API Response:', data); // Debug API response
        if (data.success) {
            console.log('Properties from API:', data.properties); // Debug properties array
            properties = data.properties;
            // Expose properties for Support Center filters and listing
            window.propertiesData = Array.isArray(properties) ? properties : [];
            renderProperties(data.properties);
        } else {
            throw new Error(data.error || 'Failed to load properties');
        }
    })
    .catch(error => {
        console.error('Error loading properties:', error);
        propertiesGrid.innerHTML = `
            <div class="col-span-full">
                <div class="bg-white rounded-lg shadow-md p-6 text-center">
                    <i class="fas fa-exclamation-triangle text-4xl text-red-400 mb-4"></i>
                    <p class="text-red-600 mb-2">Error loading properties</p>
                    <p class="text-gray-600">${error.message}</p>
                    <button onclick="loadProperties()" class="mt-4 bg-persian-green hover:bg-green-600 text-white px-4 py-2 rounded-lg transition-colors">
                        <i class="fas fa-refresh mr-2"></i>Retry
                    </button>
                </div>
            </div>
        `;
    });
}

function renderProperties(propertiesData) {
    const propertiesGrid = document.getElementById('properties-grid');
    
    if (!propertiesData || propertiesData.length === 0) {
        propertiesGrid.innerHTML = `
            <div class="col-span-full text-center py-12">
                <i class="fas fa-home text-6xl text-gray-400 mb-4"></i>
                <h3 class="text-xl font-semibold text-gray-600 mb-2">No Properties Yet</h3>
                <p class="text-gray-500 mb-6">Get started by adding your first property</p>
                <button onclick="addNewProperty()" class="bg-persian-green hover:bg-green-600 text-white px-6 py-2 rounded-lg font-medium transition-colors">
                    <i class="fas fa-plus mr-2"></i><span class="add-property-text">Add Your First Property</span>
                </button>
            </div>
        `;
        return;
    }
    
    propertiesGrid.innerHTML = propertiesData.map(property => createPropertyCard(property)).join('');
}

function createPropertyCard(property) {
    // Debug property data
    console.log('Creating property card for:', property.id);
    console.log('Property data:', property);
    console.log('Property.new value:', property.new, 'Type:', typeof property.new);

    // Normalize status - handle undefined, null, empty string
    const normalizedStatus = property.status || 'active';
    const isActive = normalizedStatus === 'active';
    const statusClass = isActive ? 'status-badge-active' : 'status-badge-inactive';
    const statusText = isActive ? 'Active' : 'Inactive';
    
    try {
        const cardHtml = `
            <div class="bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow property-card" data-property-id="${property.id}">
                <div class="p-6">
                    <!-- Property Header -->
                    <div class="property-card-header mb-4">
                        <div class="property-card-title-row">
                            <div class="flex-1">
                                <h3 class="property-name text-xl font-semibold text-dark-purple mb-2">${property.name || 'Unnamed Property'}</h3>
                                <p class="property-address text-gray-600 text-sm">${property.address || 'No address provided'}</p>
                            </div>
                        </div>
                        <div class="property-card-toggle-row">
                            <span class="status-badge px-3 py-1 rounded-full text-sm font-medium ${statusClass}">${statusText}</span>
                            <div class="flex items-center gap-2">
                                <label class="toggle-switch">
                                    <input type="checkbox" ${isActive ? 'checked' : ''} onchange="togglePropertyStatus('${property.id}', this.checked)">
                                    <span class="toggle-slider"></span>
                                </label>
                                <button onclick="copyPropertyMagicLinkFromCard('${property.id}', this)"
                                        class="bg-persian-green hover:bg-green-600 text-white px-2 py-1 rounded text-xs font-medium transition-colors"
                                        title="Copy guest access link">
                                    <i class="fas fa-copy"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                
                <!-- Property Details -->
                <div class="space-y-2 mb-4">
                    ${property.description ? `<p class="property-description text-gray-700 text-sm">${property.description}</p>` : '<p class="property-description text-gray-500 text-sm italic" style="display: none;"></p>'}
                    ${property.wifi_details ? `
                        <div class="flex items-center text-sm text-gray-600">
                            <i class="fas fa-wifi mr-2"></i>
                            WiFi: ${property.wifi_details.network || 'Not configured'}
                        </div>
                    ` : ''}
                    ${property.check_in_time ? `
                        <div class="flex items-center text-sm text-gray-600">
                            <i class="fas fa-clock mr-2"></i>
                            Check-in: ${property.check_in_time} | Check-out: ${property.check_out_time || 'Not set'}
                        </div>
                    ` : ''}
                </div>
                
                <!-- Property Actions -->
                <div class="flex flex-wrap gap-2">
                    ${property.new === true ? `
                        <!-- New Property Setup and Delete Buttons -->
                        <div class="flex gap-2 w-full">
                            <button onclick="startPropertySetup('${property.id}')"
                                    class="flex-1 bg-saffron hover:bg-yellow-500 text-dark-purple px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                                <i class="fas fa-magic mr-2"></i>Complete Setup
                            </button>
                            <button onclick="deleteNewProperty('${property.id}', '${(property.name || 'Imported Property').replace(/'/g, "\\'")}')"
                                    class="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                                    style="min-width: 2.5rem; display: flex; align-items: center; justify-content: center;"
                                    title="Delete this property">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                        <p class="w-full text-xs text-gray-500 text-center mt-1">
                            <i class="fas fa-info-circle mr-1"></i>
                            Complete setup to activate this property
                        </p>
                    ` : `
                        <!-- Normal Property Buttons -->
                        <button onclick="manageKnowledge('${property.id}')"
                                class="flex-1 bg-persian-green hover:bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                            <i class="fas fa-cog mr-2"></i>Manage
                        </button>
                        <button onclick="viewReservations('${property.id}')"
                                class="flex-1 bg-saffron hover:bg-yellow-500 text-dark-purple px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                            <i class="fas fa-calendar mr-2"></i>Reservations
                        </button>
                        <!-- COMMENTED OUT FOR TESTING - Conversations leads to unimplemented Support Center -->
                        <!-- Only show for new properties that haven't been set up yet -->
                        ${property.new ? `
                        <button onclick="viewConversations('${property.id}')"
                                class="flex-1 bg-gray-500 hover:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                            <i class="fas fa-comments mr-2"></i>Conversations
                        </button>
                        ` : ''}
                    `}
                </div>
            </div>
        </div>
        `;

        return cardHtml;

    } catch (error) {
        console.error('Error creating property card for', property.name, ':', error);
        return `<div class="bg-red-100 p-4 rounded">Error creating card for ${property.name}</div>`;
    }
}

function addNewProperty() {
    console.log('addNewProperty() called');
    try {
        openPropertyImportModal();
    } catch (error) {
        console.error('Error in addNewProperty():', error);
        alert('Error opening Property Import modal: ' + error.message);
    }
}

function openPropertyImportModal() {
    console.log('openPropertyImportModal() called');

    // Remove existing modal if any
    const existingModal = document.getElementById('property-import-modal');
    if (existingModal) {
        console.log('Removing existing modal');
        existingModal.remove();
    }

    // Create the modal
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-black bg-opacity-75 z-[80] flex items-center justify-center p-4';
    modal.id = 'property-import-modal';

    console.log('Modal element created');

    modal.innerHTML = `
        <div class="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto" onclick="event.stopPropagation()">
            <div class="bg-persian-green text-white p-6 rounded-t-lg">
                <div class="flex items-center justify-between">
                    <h3 class="text-xl font-semibold">
                        <i class="fas fa-download mr-2"></i>Property Import
                    </h3>
                    <button onclick="closePropertyImportModal()" class="text-white hover:text-gray-200">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
            <div class="p-6" id="property-import-content">
                <!-- Content will be loaded here -->
            </div>
        </div>
    `;

    // Add to page
    document.body.appendChild(modal);
    document.body.style.overflow = 'hidden';

    console.log('Modal added to DOM');

    // Load initial content
    try {
        loadPropertyImportStep();
        console.log('loadPropertyImportStep() called successfully');
    } catch (error) {
        console.error('Error in loadPropertyImportStep():', error);
    }

    // Disable closing on outside click to prevent accidental dismissals
}

function closePropertyImportModal() {
    const modal = document.getElementById('property-import-modal');
    if (modal) {
        // Attempt to cancel any in-flight import fetch and notify backend to cancel job
        try {
            if (window.propertyImportCancel) {
                // Abort client-side fetch
                if (window.propertyImportCancel.controller) {
                    window.propertyImportCancel.controller.abort();
                }
                // Best-effort server-side cancel
                if (window.propertyImportCancel.jobId) {
                    fetch('/api/property-setup/import-properties/cancel', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'same-origin',
                        body: JSON.stringify({ job_id: window.propertyImportCancel.jobId })
                    }).catch(() => {});
                }
            }
        } catch (e) {
            console.warn('Property import cancel on close failed:', e);
        }
        modal.remove();
        document.body.style.overflow = 'auto';
    }
}

function checkForDuplicateListings(listings, userUrl) {
    const content = document.getElementById('property-import-content');

    // Extract listing URLs
    const listingUrls = listings.map(listing => listing.url);

    // Show checking state
    content.innerHTML = `
        <div class="text-center py-12">
            <i class="fas fa-search fa-spin text-4xl text-persian-green mb-4"></i>
            <h4 class="text-xl font-semibold text-dark-purple mb-2">Checking for Duplicates</h4>
            <p class="text-gray-600">Verifying that these properties haven't been imported already...</p>
        </div>
    `;

    // Check for duplicates
    fetch('/api/property-setup/check-duplicates', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        credentials: 'same-origin',
        body: JSON.stringify({ listing_urls: listingUrls })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show listings with duplicate warnings
            showListingsSelection(listings, userUrl, data.duplicates);
        } else {
            throw new Error(data.error || 'Failed to check for duplicates');
        }
    })
    .catch(error => {
        console.error('Error checking duplicates:', error);
        // Show listings anyway but with a warning
        showListingsSelection(listings, userUrl, []);
    });
}
function loadPropertyImportStep() {
    console.log('loadPropertyImportStep() called');
    const content = document.getElementById('property-import-content');

    if (!content) {
        console.error('property-import-content element not found!');
        return;
    }

    console.log('Content element found, checking user profile...');

    // Check if user has airbnbUserLink saved
    fetch('/api/user/profile', {
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        console.log('User profile data:', data);
        if (data.success && data.user && data.user.airbnbUserLink) {
            // User has saved Airbnb link, go directly to listings
            console.log('Found saved Airbnb link:', data.user.airbnbUserLink);
            loadAirbnbListings(data.user.airbnbUserLink);
        } else {
            // Show URL input step
            console.log('No saved Airbnb link found, showing URL input');
            showUrlInputStep();
        }
    })
    .catch(error => {
        console.error('Error checking user profile:', error);
        showUrlInputStep();
    });
}

function showUrlInputStep() {
    const content = document.getElementById('property-import-content');
    content.innerHTML = `
        <div class="text-center">
            <div class="mb-6">
                <i class="fas fa-link text-4xl text-persian-green mb-4"></i>
                <h4 class="text-xl font-semibold text-dark-purple mb-2">Connect Your Airbnb Account</h4>
                <p class="text-gray-600">Enter your Airbnb listing or user profile link to import your properties</p>
            </div>

            <form id="url-input-form" class="max-w-2xl mx-auto" novalidate>
                <div class="mb-4">
                    <input type="url"
                           id="airbnb-url"
                           name="airbnb_url"
                           required
                           class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                           aria-label="Airbnb URL"
                           placeholder="https://www.airbnb.com/...">
                </div>

                <div class="mt-2 text-left">
                    <div class="bg-blue-50 border border-blue-200 rounded-lg p-4 max-w-full overflow-hidden">
                        <div class="flex items-start space-x-3 w-full">
                            <i class="fas fa-info-circle text-blue-500 mt-0.5 shrink-0"></i>
                            <div class="text-xs text-blue-800 flex-1 min-w-0 break-words">
                                <div class="font-semibold mb-1">Supported links</div>
                                <ul class="list-disc pl-4 space-y-1 break-words">
                                    <li>
                                        Listing URL: <code class="bg-white px-1 py-0.5 rounded border break-all">https://www.airbnb.com/rooms/123456789</code>
                                    </li>
                                    <li>
                                        Host profile URL: <code class="bg-white px-1 py-0.5 rounded border break-all">https://www.airbnb.com/users/show/12345</code>
                                    </li>
                                    <li>
                                        Custom host link: <code class="bg-white px-1 py-0.5 rounded border break-all">https://www.airbnb.com/h/mycustomlink</code>
                                    </li>
                                </ul>
                                <div class="mt-2">
                                    <div class="font-semibold">Where to find these</div>
                                    <ul class="list-disc pl-4 mt-1 space-y-1 break-words">
                                        <li>Listing URL: open the listing on Airbnb and copy the address bar URL.</li>
                                        <li>Host profile URL: click your profile on Airbnb and copy the profile page URL.</li>
                                        <li>Custom host link: copy your Airbnb "h/" sharing link (it redirects to your listing).</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>



                <!-- Consent Checkbox -->
                <div class="mb-6">
                    <div class="bg-amber-50 border border-amber-200 rounded-lg p-4">
                        <div class="flex items-start space-x-3">
                            <input type="checkbox"
                                   id="consent-checkbox"
                                   required
                                   class="mt-1 w-4 h-4 text-persian-green border-gray-300 rounded focus:ring-persian-green">
                            <label for="consent-checkbox" class="text-sm text-gray-700 leading-relaxed">
                                <span class="font-medium text-gray-900">Data Access Consent:</span>
                                I confirm that the provided URL is related to my Airbnb listings and I authorize Guestrix to retrieve publicly available listing data from Airbnb for the purpose of importing my properties into this dashboard. This includes property details, host information, and listing descriptions that are publicly visible on Airbnb.
                            </label>
                        </div>
                        <div class="mt-2 ml-7 text-xs text-gray-500">
                            <i class="fas fa-shield-alt mr-1"></i>
                            We only access publicly available information and never store your Airbnb login credentials.
                        </div>
                    </div>
                </div>

                <div class="flex justify-center space-x-3">
                    <button type="button" onclick="closePropertyImportModal()"
                            class="px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                        Cancel
                    </button>
                    <button type="submit"
                            class="px-6 py-3 bg-persian-green hover:bg-green-600 text-white rounded-lg font-medium transition-colors">
                        <i class="fas fa-search mr-2"></i>Find Properties
                    </button>
                </div>
            </form>
        </div>
    `;

    // Handle form submission
    const formEl = document.getElementById('url-input-form');
    formEl.addEventListener('submit', function(e) {
        e.preventDefault();
        processAirbnbUrl();
    });
    // Also process when pressing Enter in the URL field to ensure our normalization runs before native validation
    const urlEl = document.getElementById('airbnb-url');
    urlEl.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            processAirbnbUrl();
        }
    });
}

function showUrlError(message) {
    // Remove any existing error message
    clearUrlError();

    // Create error message element
    const errorDiv = document.createElement('div');
    errorDiv.id = 'url-error-message';
    errorDiv.className = 'mt-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800';
    errorDiv.innerHTML = `
        <div class="flex items-start">
            <i class="fas fa-exclamation-triangle mt-0.5 mr-2"></i>
            <span>${message}</span>
        </div>
    `;

    // Insert after the URL input
    const urlInput = document.getElementById('airbnb-url');
    urlInput.parentNode.insertBefore(errorDiv, urlInput.nextSibling);

    // Add error styling to input
    urlInput.classList.add('border-red-300', 'focus:ring-red-500', 'focus:border-red-500');
    urlInput.classList.remove('border-gray-300', 'focus:ring-persian-green');
}

function clearUrlError() {
    // Remove error message
    const errorMessage = document.getElementById('url-error-message');
    if (errorMessage) {
        errorMessage.remove();
    }

    // Remove error styling from input
    const urlInput = document.getElementById('airbnb-url');
    if (urlInput) {
        urlInput.classList.remove('border-red-300', 'focus:ring-red-500', 'focus:border-red-500');
        urlInput.classList.add('border-gray-300', 'focus:ring-persian-green');
    }
}

function processAirbnbUrl() {
    const urlInput = document.getElementById('airbnb-url');
    const consentCheckbox = document.getElementById('consent-checkbox');
    const submitBtn = document.querySelector('#url-input-form button[type="submit"]');
    let url = urlInput.value.trim();
    
    // Clear native validation before we normalize
    urlInput.setCustomValidity('');
    
    // Add https:// if user enters URL without scheme
    if (url && !/^https?:\/\//i.test(url) && /^(www\.)?airbnb\.com/i.test(url)) {
        url = 'https://' + url.replace(/^\/+/, '');
    }

    if (!url) {
        showUrlError('Please enter an Airbnb URL');
        urlInput.reportValidity && urlInput.reportValidity();
        urlInput.focus();
        return;
    }

    // Basic URL validation
    if (!url.includes('airbnb.com')) {
        showUrlError('Please enter an Airbnb URL (should contain "airbnb.com")');
        urlInput.reportValidity && urlInput.reportValidity();
        urlInput.focus();
        return;
    }

    // Check for supported URL formats
    const isListingUrl = url.includes('/rooms/') || url.includes('/hosting/listings/') || url.includes('/h/');
    const isProfileUrl = url.includes('/users/show/');

    if (!isListingUrl && !isProfileUrl) {
        showUrlError('Please check if the URL is correct. We support listing pages and user profiles.');
        urlInput.focus();
        return;
    }

    if (!consentCheckbox.checked) {
        showUrlError('Please confirm that you authorize Guestrix to retrieve your listing data by checking the consent checkbox.');
        consentCheckbox.focus();
        return;
    }

    // Clear any previous error messages
    clearUrlError();

    // Show loading state
    const originalText = submitBtn.innerHTML;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Processing...';
    submitBtn.disabled = true;
    urlInput.disabled = true;

    // Process the URL with consent information
    fetch('/api/property-setup/process-url', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        credentials: 'same-origin',
        body: JSON.stringify({
            url: url,
            consent_given: consentCheckbox.checked,
            consent_timestamp: new Date().toISOString()
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // URL processed successfully, now get listings
            console.log('URL processed successfully, loading listings...');
            loadAirbnbListings(data.user_url);
        } else {
            throw new Error(data.error || 'Failed to process URL');
        }
    })
    .catch(error => {
        console.error('Error processing URL:', error);

        // Restore form state
        submitBtn.innerHTML = originalText;
        submitBtn.disabled = false;
        urlInput.disabled = false;

        // Show error message
        alert(error.message || 'Error processing URL. Please check the URL and try again.');
    });
}

function loadAirbnbListings(userUrl) {
    const content = document.getElementById('property-import-content');

    // Show loading state with user guidance
    content.innerHTML = `
        <div class="text-center py-12">
            <i class="fas fa-spinner fa-spin text-4xl text-persian-green mb-4"></i>
            <h4 class="text-xl font-semibold text-dark-purple mb-2">Loading Your Properties</h4>
            <p class="text-gray-600 mb-4">Fetching your Airbnb listings...</p>

            <!-- Enhanced user guidance note -->
            <div class="bg-blue-50 border-2 border-blue-200 rounded-xl p-6 max-w-lg mx-auto">
                <div class="flex items-center justify-center mb-3">
                    <i class="fas fa-info-circle text-blue-500 text-xl mr-3"></i>
                    <h3 class="text-lg font-bold text-blue-800">Fetching Your Listings</h3>
                </div>
                <p class="text-sm text-blue-700 mb-3">
                    We're scanning your Airbnb profile to find all your properties. This may take a moment depending on how many listings you have.
                </p>
                <div class="flex items-center justify-center space-x-4 text-xs text-blue-600">
                    <div class="flex items-center space-x-1">
                        <i class="fas fa-search text-blue-600"></i>
                        <span>Scanning properties</span>
                    </div>
                    <div class="flex items-center space-x-1">
                        <i class="fas fa-list text-green-600"></i>
                        <span>Organizing listings</span>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Fetch listings
    fetch('/api/property-setup/get-listings', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        credentials: 'same-origin',
        body: JSON.stringify({ user_url: userUrl })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Listings fetched successfully - this is when host name extraction happens
            console.log('Listings fetched successfully, refreshing user profile for navbar update...');

            // Refresh user profile to update navbar with extracted host name
            setTimeout(() => {
                refreshUserProfile();
            }, 100);

            // Check for duplicates before showing selection
            checkForDuplicateListings(data.listings, data.user_url);
        } else {
            throw new Error(data.error || 'Failed to fetch listings');
        }
    })
    .catch(error => {
        console.error('Error fetching listings:', error);

        content.innerHTML = `
            <div class="text-center py-12">
                <i class="fas fa-exclamation-triangle text-4xl text-red-500 mb-4"></i>
                <h4 class="text-xl font-semibold text-dark-purple mb-2">Error Loading Properties</h4>
                <p class="text-gray-600 mb-6">${error.message || 'Failed to fetch your Airbnb listings'}</p>
                <button onclick="showUrlInputStep()"
                        class="px-6 py-3 bg-persian-green hover:bg-green-600 text-white rounded-lg font-medium transition-colors">
                    <i class="fas fa-arrow-left mr-2"></i>Try Again
                </button>
            </div>
        `;
    });
}

function showListingsSelection(listings, userUrl, duplicates = []) {
    const content = document.getElementById('property-import-content');

    content.innerHTML = `
        <div>
            <div class="mb-6 text-center">
                <i class="fas fa-home text-4xl text-persian-green mb-4"></i>
                <h4 class="text-xl font-semibold text-dark-purple mb-2">Select Properties to Import</h4>
                <p class="text-gray-600">Choose which Airbnb listings you'd like to add to your dashboard</p>
            </div>

            <div class="mb-6">
                ${duplicates.length > 0 ? `
                    <div class="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                        <div class="flex items-center">
                            <i class="fas fa-info-circle text-yellow-600 mr-2"></i>
                            <span class="text-sm text-yellow-800">
                                ${duplicates.length} of ${listings.length} listing${duplicates.length !== 1 ? 's have' : ' has'} already been imported and cannot be selected again.
                            </span>
                        </div>
                    </div>
                ` : ''}
                <div class="flex items-center justify-between mb-4">
                    <span class="text-sm text-gray-600">Found ${listings.length} listing${listings.length !== 1 ? 's' : ''} (${listings.length - duplicates.length} available for import)</span>
                    <div class="flex space-x-2">
                        <button onclick="selectAllListings(true)"
                                class="text-sm px-3 py-1 bg-persian-green/10 text-persian-green rounded hover:bg-persian-green/20 transition-colors">
                            Select All
                        </button>
                        <button onclick="selectAllListings(false)"
                                class="text-sm px-3 py-1 bg-gray-100 text-gray-600 rounded hover:bg-gray-200 transition-colors">
                            Select None
                        </button>
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 max-h-96 overflow-y-auto">
                    ${listings.map(listing => createListingCard(listing, duplicates)).join('')}
                </div>
            </div>

            <div class="flex justify-center space-x-3 pt-4 border-t">
                <button onclick="showUrlInputStep()"
                        class="px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                    <i class="fas fa-arrow-left mr-2"></i>Back
                </button>
                <button onclick="importSelectedProperties('${userUrl}')"
                        class="px-6 py-3 bg-persian-green hover:bg-green-600 text-white rounded-lg font-medium transition-colors">
                    <i class="fas fa-download mr-2"></i>Import Selected
                </button>
            </div>
        </div>
    `;
}

function createListingCard(listing, duplicates = []) {
    const isDuplicate = duplicates.some(dup => dup.url === listing.url);
    const cardClass = isDuplicate
        ? "listing-card border border-red-300 bg-red-50 rounded-lg p-4 opacity-75 cursor-not-allowed"
        : "listing-card border border-gray-200 rounded-lg p-4 hover:border-persian-green transition-colors cursor-pointer";
    const clickHandler = isDuplicate ? "" : `onclick="toggleListingSelection('${listing.url}')"`;

    return `
        <div class="${cardClass}" ${clickHandler}>
            <div class="flex items-start space-x-3">
                <div class="flex-shrink-0" onclick="event.stopPropagation()">
                    <input type="checkbox"
                           class="listing-checkbox w-4 h-4 text-persian-green border-gray-300 rounded focus:ring-persian-green"
                           data-url="${listing.url}"
                           ${isDuplicate ? 'disabled' : ''}
                           onchange="handleCheckboxChange(event, '${listing.url}')">
                </div>
                <div class="flex-1 min-w-0">
                    ${listing.image ? `
                        <img src="${listing.image}"
                             alt="${listing.title}"
                             class="w-full h-32 object-cover rounded-lg mb-3"
                             onerror="this.style.display='none'">
                    ` : ''}
                    <h5 class="font-medium text-dark-purple mb-1 truncate">${listing.title}</h5>
                    <p class="text-sm text-gray-600 mb-2">${listing.location}</p>
                    ${listing.property_type ? `<p class="text-xs text-gray-500 mb-1">${listing.property_type}</p>` : ''}
                    ${listing.rating ? `
                        <div class="flex items-center text-xs text-gray-500">
                            <i class="fas fa-star text-yellow-400 mr-1"></i>
                            <span>${listing.rating}</span>
                            ${listing.review_count ? `<span class="ml-1">(${listing.review_count} reviews)</span>` : ''}
                        </div>
                    ` : ''}
                </div>
            </div>
        </div>
    `;
}

function handleCheckboxChange(event, url) {
    // The checkbox state has been updated by the browser at this point
    const checkbox = event.target;

    // Update the visual styling
    updateListingCardStyle(checkbox);
    console.log('Checkbox changed:', url, 'checked:', checkbox.checked);
}

function toggleListingSelection(url) {
    const checkbox = document.querySelector(`input[data-url="${url}"]`);
    if (checkbox) {
        checkbox.checked = !checkbox.checked;
        updateListingCardStyle(checkbox);
    }
}

function updateListingCardStyle(checkbox) {
    const card = checkbox.closest('.listing-card');
    if (checkbox.checked) {
        card.classList.add('border-persian-green', 'bg-persian-green/5');
    } else {
        card.classList.remove('border-persian-green', 'bg-persian-green/5');
    }
}

function selectAllListings(select) {
    const checkboxes = document.querySelectorAll('.listing-checkbox:not(:disabled)');
    checkboxes.forEach(checkbox => {
        checkbox.checked = select;
        updateListingCardStyle(checkbox);
    });
}
function importSelectedProperties(userUrl) {
    const selectedCheckboxes = document.querySelectorAll('.listing-checkbox:checked:not(:disabled)');
    const selectedListings = Array.from(selectedCheckboxes).map(cb => cb.dataset.url);

    if (selectedListings.length === 0) {
        alert('Please select at least one property to import (duplicates cannot be imported)');
        return;
    }

    const importBtn = document.querySelector('button[onclick*="importSelectedProperties"]');
    const originalText = importBtn.innerHTML;

    // Show loading state with user guidance
    importBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Importing...';
    importBtn.disabled = true;

    // Show detailed loading message in the content area
    const content = document.getElementById('property-import-content');
    const originalContent = content.innerHTML;

    content.innerHTML = `
        <div class="text-center py-8">
            <i class="fas fa-spinner fa-spin text-4xl text-persian-green mb-4"></i>
            <h4 class="text-xl font-semibold text-dark-purple mb-2">Importing Your Properties</h4>

            <!-- Enhanced warning message -->
            <div class="bg-red-50 border-2 border-red-200 rounded-xl p-6 max-w-lg mx-auto mb-6">
                <div class="flex items-center justify-center mb-3">
                    <i class="fas fa-exclamation-triangle text-red-500 text-2xl mr-3"></i>
                    <h3 class="text-lg font-bold text-red-800">CAUTION! Don't Close This Window</h3>
                </div>
                <p class="text-sm text-red-700 mb-3">
                    We're extracting detailed information from your properties. This process takes time because we're gathering amenities, house rules, descriptions, and more.
                </p>
                <div class="flex items-center justify-center space-x-4 text-xs text-red-600">
                    <div class="flex items-center space-x-1">
                        <i id="activity-icon-1" class="fas fa-coffee text-amber-600"></i>
                        <span>Grab some coffee</span>
                    </div>
                    <div class="flex items-center space-x-1">
                        <i id="activity-icon-2" class="fas fa-dumbbell text-blue-600"></i>
                        <span>Do a quick stretch</span>
                    </div>
                    <div class="flex items-center space-x-1">
                        <i id="activity-icon-3" class="fas fa-heart text-pink-600"></i>
                        <span>Pet your furry friend</span>
                    </div>
                </div>
            </div>

            <!-- Dynamic progress status -->
            <div class="mb-4">
                <p id="progress-status" class="text-gray-600 font-medium">Preparing to import ${selectedListings.length} ${selectedListings.length === 1 ? 'property' : 'properties'}...</p>
                <p id="progress-detail" class="text-sm text-gray-500 mt-1">Initializing extraction process...</p>
            </div>

            <!-- Enhanced progress indicator -->
            <div class="mt-6 max-w-md mx-auto">
                <div class="flex justify-between text-xs text-gray-500 mb-2">
                    <span id="progress-current">0</span>
                    <span id="progress-total">${selectedListings.length} properties</span>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-3 shadow-inner">
                    <div id="progress-bar" class="h-3 rounded-full transition-all duration-500 ease-out" style="width: 0%; background: linear-gradient(to right, #00a693, #10b981);"></div>
                </div>
                <div class="text-xs text-gray-400 mt-1 text-center">
                    <span id="progress-percentage">0%</span> complete
                </div>
            </div>
        </div>
    `;

    // Start rotating activity icons
    startActivityIconRotation();

    // Initialize progress tracking
    initializeProgressTracking(selectedListings.length);

    // Start progress simulation
    startProgressSimulation(selectedListings.length);

    // Prepare cancelation support
    const jobId = `import_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const controller = new AbortController();
    window.propertyImportCancel = { jobId, controller };

    // Import properties
    const parseJsonSafely = async (response) => {
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            return response.json();
        }
        const text = await response.text().catch(() => '');
        const snippet = (text || '').slice(0, 200);
        const status = `${response.status} ${response.statusText}`;
        throw new Error(`Server returned ${status} with non-JSON body: ${snippet}`);
    };

    fetch('/api/property-setup/import-properties', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        credentials: 'same-origin',
        signal: controller.signal,
        body: JSON.stringify({
            selected_listings: selectedListings,
            user_url: userUrl,
            job_id: jobId
        })
    })
    .then(async response => {
        if (!response.ok) {
            // Try to surface useful details even if body is not JSON
            return parseJsonSafely(response);
        }
        return parseJsonSafely(response);
    })
    .then(data => {
        // Stop activity icon rotation
        stopActivityIconRotation();

        // Clear cancel handle after completion
        window.propertyImportCancel = null;

        if (data.success) {
            // Update progress to completion
            updateImportProgress('Import completed successfully!', selectedListings.length);
            setTimeout(() => {
                showImportSuccess(data.created_properties, data.total_imported);
            }, 1000);
        } else {
            throw new Error(data.error || 'Failed to import properties');
        }
    })
    .catch(error => {
        console.error('Error importing properties:', error);

        // Stop activity icon rotation
        stopActivityIconRotation();

        // Clear cancel handle on error
        window.propertyImportCancel = null;

        // Restore button state
        importBtn.innerHTML = originalText;
        importBtn.disabled = false;

        if (error.name === 'AbortError') {
            // Silent if user closed modal
            console.log('Property import aborted by user');
        } else {
            alert((error && error.message) || 'Error importing properties. Please try again.');
        }
    });
}

function showImportSuccess(createdProperties, totalImported) {
    const content = document.getElementById('property-import-content');

    // Automatically refresh the properties list in the background
    loadProperties();

    content.innerHTML = `
        <div class="py-8">
            <div class="text-center mb-6">
                <i class="fas fa-check-circle text-5xl text-green-500 mb-6"></i>
                <h4 class="text-2xl font-semibold text-dark-purple mb-4">Properties Imported Successfully!</h4>
                <p class="text-gray-600 mb-6">
                    ${totalImported} propert${totalImported !== 1 ? 'ies' : 'y'} ${totalImported !== 1 ? 'have' : 'has'} been added to your dashboard
                </p>
            </div>

            ${createdProperties.length > 0 ? `
                <div class="bg-green-50 border border-green-200 rounded-lg p-4 mb-6 max-w-2xl mx-auto">
                    <h5 class="font-medium text-center text-green-800 mb-3">Imported Properties:</h5>
                    <ul class="text-sm text-green-700 space-y-1">
                        ${createdProperties.map(prop => `
                            <li class="flex items-start">
                                <i class="fas fa-home mr-2 mt-0.5 flex-shrink-0"></i>
                                <div class="flex-1 min-w-0">
                                    <div class="font-medium">${prop.name}</div>
                                    ${prop.address ? `<div class="text-green-600">- ${prop.address}</div>` : ''}
                                </div>
                            </li>
                        `).join('')}
                    </ul>
                </div>
            ` : ''}

            <div class="text-center space-y-3">
                <button onclick="closePropertyImportModal(); loadProperties();"
                        class="px-8 py-3 bg-persian-green hover:bg-green-600 text-white rounded-lg font-medium transition-colors">
                    <i class="fas fa-eye mr-2"></i>View Properties
                </button>
            </div>
        </div>
    `;
}

// Test function to debug navbar update
function testNavbarUpdate() {
    console.log('Testing navbar update...');

    // Test selectors
    const selector1 = 'span.text-dark-purple.font-medium.hidden.md\\:inline';
    const selector2 = 'span.text-dark-purple.font-medium';
    const selector3 = 'span';

    const span1 = document.querySelector(selector1);
    const span2 = document.querySelector(selector2);
    const allSpans = document.querySelectorAll(selector3);

    console.log('Selector 1 result:', span1);
    console.log('Selector 2 result:', span2);
    console.log('All spans count:', allSpans.length);

    // Find spans with "Welcome" text
    const welcomeSpans = Array.from(allSpans).filter(span =>
        span.textContent && span.textContent.includes('Welcome')
    );
    console.log('Welcome spans:', welcomeSpans);

    if (welcomeSpans.length > 0) {
        console.log('First welcome span text:', welcomeSpans[0].textContent);
        console.log('First welcome span classes:', welcomeSpans[0].className);
    }
}

function refreshUserProfile() {
    console.log('refreshUserProfile() called');
    // Refresh the user profile to update display name in navbar
    fetch('/api/user/profile', {
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        console.log('User profile response:', data);
        if (data.success && data.user) {
            // Update the welcome greeting in navbar
            let welcomeSpan = document.querySelector('span.text-dark-purple.font-medium.hidden.md\\:inline');
            console.log('First selector found:', !!welcomeSpan);

            // Try a simpler selector if the first one fails
            if (!welcomeSpan) {
                welcomeSpan = document.querySelector('span.text-dark-purple.font-medium');
                console.log('Simpler selector found:', !!welcomeSpan);
            }

            // Fallback: try to find span containing "Welcome" text
            if (!welcomeSpan) {
                const spans = document.querySelectorAll('span');
                welcomeSpan = Array.from(spans).find(span =>
                    span.textContent && span.textContent.includes('Welcome')
                );
                console.log('Fallback selector found:', !!welcomeSpan);
                if (welcomeSpan) {
                    console.log('Found welcome span with text:', welcomeSpan.textContent);
                }
            }

            if (welcomeSpan && data.user.displayName) {
                welcomeSpan.innerHTML = `Welcome, ${data.user.displayName}!`;
                console.log('Updated navbar greeting to:', `Welcome, ${data.user.displayName}!`);
            } else {
                console.log('Welcome span not found or no displayName:', {
                    welcomeSpan: !!welcomeSpan,
                    displayName: data.user.displayName,
                    allSpans: document.querySelectorAll('span').length
                });
            }

            // Update settings modal if it's open
            const displayNameInput = document.getElementById('display-name');
            if (displayNameInput && data.user.displayName) {
                displayNameInput.value = data.user.displayName;
            }

            // Update airbnb link field if it exists
            const airbnbLinkInput = document.getElementById('airbnb-user-link');
            if (airbnbLinkInput && data.user.airbnbUserLink) {
                airbnbLinkInput.value = data.user.airbnbUserLink;
            }
        }
    })
    .catch(error => {
        console.error('Error refreshing user profile:', error);
    });
}

function viewConversations(propertyId) {
    console.log('View conversations clicked:', propertyId);

    // Switch to Support Center tab
    showScreen('support');

    // Set property filter if specific property was clicked
    if (propertyId) {
        setTimeout(() => {
            const propertyFilter = document.getElementById('property-filter');
            if (propertyFilter) {
                propertyFilter.value = propertyId;
                applyConversationFilters();
            }
        }, 100);
    }
}

function manageKnowledge(propertyId) {
    console.log('Manage knowledge clicked:', propertyId);

    // Fetch fresh property data to ensure we have the latest information
    fetch(`/api/property/${propertyId}`, {
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        console.log('API response for property:', data);

        if (data.success && data.property) {
            console.log('Fresh property data loaded:', data.property);
            openKnowledgeModal(data.property);
        } else if (data.success && data.id) {
            // Handle case where property data is directly in the response
            console.log('Fresh property data loaded (direct format):', data);
            openKnowledgeModal(data);
        } else {
            // Fallback to cached data
            const property = properties.find(p => p.id === propertyId);
            if (!property) {
                console.error('Property not found:', propertyId);
                return;
            }
            console.log('Using cached property data:', property);
            openKnowledgeModal(property);
        }
    })
    .catch(error => {
        console.error('Error fetching fresh property data:', error);
        // Fallback to cached data
        const property = properties.find(p => p.id === propertyId);
        if (!property) {
            console.error('Property not found:', propertyId);
            return;
        }
        console.log('Using cached property data due to error:', property);
        openKnowledgeModal(property);
    });
}

function viewReservations(propertyId) {
    // Switch to calendar screen and filter by property
    console.log('View reservations clicked:', propertyId);
    
    // Switch to calendar screen
    showScreen('calendar');
    
    // Set property filter after a short delay to ensure the calendar is loaded
    setTimeout(() => {
        const propertyFilter = document.getElementById('property-filter');
        if (propertyFilter) {
            propertyFilter.value = propertyId;
            filterCalendarByProperty();
        }
    }, 100);
}

function togglePropertyStatus(propertyId, isActive) {
    console.log('Toggle property status:', propertyId, isActive);

    // If activating a property, check if it's a new property that needs setup
    if (isActive) {
        checkIfNewPropertyNeedsSetup(propertyId);
        return;
    }

    const status = isActive ? 'active' : 'inactive';

    // API call to update property status using the new endpoint
    fetch(`/api/properties/${propertyId}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ status: status })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('Property status updated successfully');
            // Update the local property data
            const property = properties.find(p => p.id === propertyId);
            if (property) {
                property.status = status;
                console.log('Updated local property status to:', status);
                // Update the property card with the updated property object
                updatePropertyCard(property);
            }
        } else {
            console.error('Error updating property status:', data.error);
            // Revert the toggle
            const toggle = document.querySelector(`input[onchange*="${propertyId}"]`);
            if (toggle) {
                toggle.checked = !isActive;
            }
            alert('Error updating property status: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error updating property status:', error);
        // Revert the toggle
        const toggle = document.querySelector(`input[onchange*="${propertyId}"]`);
        if (toggle) {
            toggle.checked = !isActive;
        }
        alert('Error updating property status: ' + error.message);
    });
}

function startPropertySetup(propertyId) {
    console.log('Starting property setup for:', propertyId);

    // Fetch the latest property data from the server to ensure we have the most recent setup progress
    fetch(`/api/properties/${propertyId}`, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        },
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(result => {
        if (result.success && result.property) {
            console.log('Fetched latest property data for setup:', result.property);

            // If this is a new property, show sync warning modal before allowing edits
            if (result.property.new === true) {
                showSyncListingWarningModal(propertyId, result.property);
            } else {
                openPropertySetupModal(propertyId, result.property);
            }
        } else {
            console.error('Failed to fetch property data:', result.error);
            alert('Failed to load property data. Please refresh the page and try again.');
        }
    })
    .catch(error => {
        console.error('Error fetching property data for setup:', error);
        alert('Error loading property data. Please refresh the page and try again.');
    });
}

function openPropertySetupModal(propertyId, property) {
    // Open the property setup modal with the latest data
    if (typeof window.propertySetupModal !== 'undefined') {
        window.propertySetupModal.open(propertyId, property);
    } else {
        console.error('PropertySetupModal not available');
        alert('Property setup is not available. Please refresh the page and try again.');
    }
}
// Modal shown before editing a newly imported property to keep data in sync with live listing
function showSyncListingWarningModal(propertyId, property) {
    const existing = document.getElementById('sync-warning-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'sync-warning-modal';
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';

    modal.innerHTML = `
        <div class="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
            <div class="p-6">
                <div class="flex items-start mb-3">
                    <i class="fas fa-exclamation-triangle text-yellow-500 text-xl mr-2 mt-0.5"></i>
                    <div>
                        <h3 class="text-lg font-semibold text-gray-900">Keep Your Listing in Sync</h3>
                    </div>
                </div>
                <div class="text-sm text-gray-700 space-y-3">
                    <p><strong>Warning:</strong> Information for this property was imported directly from your live Airbnb listing. Any changes made here will not update your official listing.</p>
                    <p>To prevent guest confusion and ensure seamless experience, it is critical that this information remains consistent with what your guests see on Airbnb. Mismatches can lead to misunderstandings and affect your guest's stay.</p>
                </div>
                <div class="mt-6 flex justify-end">
                    <button id="sync-warning-continue"
                            class="px-6 py-2 bg-persian-green hover:bg-green-600 text-white rounded-lg font-medium transition-colors">
                        I Understand & Continue
                    </button>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    document.body.style.overflow = 'hidden';

    const continueBtn = modal.querySelector('#sync-warning-continue');
    continueBtn.addEventListener('click', () => {
        closeSyncListingWarningModal();
        openPropertySetupModal(propertyId, property);
    });
}

function closeSyncListingWarningModal() {
    const modal = document.getElementById('sync-warning-modal');
    if (modal) {
        modal.remove();
        document.body.style.overflow = 'auto';
    }
}

function checkIfNewPropertyNeedsSetup(propertyId) {
    // Get property details to check if it's new
    fetch(`/api/properties/${propertyId}`, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        },
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success && data.property) {
            const property = data.property;

            // Check if this is a new property that needs setup
            if (property.new === true) {
                // Revert the toggle since we're opening setup instead
                const toggle = document.querySelector(`input[onchange*="${propertyId}"]`);
                if (toggle) {
                    toggle.checked = false;
                }

                // Open Property Setup modal
                startPropertySetup(propertyId);
            } else {
                // Regular activation - proceed normally
                activatePropertyDirectly(propertyId);
            }
        } else {
            console.error('Failed to get property details');
            showErrorMessage('Failed to get property details');
        }
    })
    .catch(error => {
        console.error('Error checking property status:', error);
        showErrorMessage('Error checking property status');
    });
}

function activatePropertyDirectly(propertyId) {
    // First check for pending knowledge items
    fetch(`/api/properties/${propertyId}/knowledge/pending-count`, {
        method: 'GET',
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success && data.has_pending_items) {
            // Revert the toggle since activation is blocked
            const toggle = document.querySelector(`input[onchange*="${propertyId}"]`);
            if (toggle) {
                toggle.checked = false;
            }

            // Show warning modal about pending items
            showPendingItemsWarningModal(propertyId, data.pending_count);
            return;
        }

        // No pending items, proceed with activation
        proceedWithPropertyActivation(propertyId);
    })
    .catch(error => {
        console.error('Error checking pending items:', error);
        // If check fails, revert toggle and show error
        const toggle = document.querySelector(`input[onchange*="${propertyId}"]`);
        if (toggle) {
            toggle.checked = false;
        }
        showErrorMessage('Error checking pending items. Please try again.');
    });
}

function proceedWithPropertyActivation(propertyId) {
    // Regular property activation without setup
    fetch(`/api/properties/${propertyId}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({
            status: 'active'
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('Property activated successfully');
            loadProperties();
            showSuccessMessage('Property activated successfully');
        } else {
            console.error('Failed to activate property:', data.error);
            showErrorMessage(data.error || 'Failed to activate property');
        }
    })
    .catch(error => {
        console.error('Error activating property:', error);
        showErrorMessage('Error activating property');
    });
}

function showPendingItemsWarningModal(propertyId, pendingCount) {
    // Create modal HTML
    const modalHTML = `
        <div id="pending-items-warning-modal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div class="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
                <div class="p-6">
                    <div class="flex items-center mb-4">
                        <div class="flex-shrink-0">
                            <i class="fas fa-exclamation-triangle text-yellow-500 text-2xl"></i>
                        </div>
                        <div class="ml-3">
                            <h3 class="text-lg font-medium text-gray-900">
                                Pending Knowledge Items
                            </h3>
                        </div>
                    </div>

                    <div class="mb-6">
                        <p class="text-sm text-gray-600">
                            This property has <strong>${pendingCount}</strong> pending knowledge item${pendingCount > 1 ? 's' : ''}
                            that need${pendingCount > 1 ? '' : 's'} to be reviewed and approved before the property can be activated.
                        </p>
                        <p class="text-sm text-gray-600 mt-2">
                            Please review these items in the Knowledge Base to ensure your guests receive accurate information.
                        </p>
                    </div>

                    <div class="flex flex-col sm:flex-row gap-3">
                        <button onclick="openKnowledgeBaseFromWarning('${propertyId}')"
                                class="flex-1 bg-persian-green hover:bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                            <i class="fas fa-book mr-2"></i>Review Knowledge Base
                        </button>
                        <button onclick="closePendingItemsWarningModal()"
                                class="flex-1 bg-gray-300 hover:bg-gray-400 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                            Close
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Add modal to page
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    document.body.style.overflow = 'hidden';

    // Do not close on outside click
}

function closePendingItemsWarningModal() {
    const modal = document.getElementById('pending-items-warning-modal');
    if (modal) {
        modal.remove();
        document.body.style.overflow = 'auto';
    }
}

function openKnowledgeBaseFromWarning(propertyId) {
    // Close the warning modal first
    closePendingItemsWarningModal();

    // Set flag to skip pending items check when opening knowledge modal
    window.skipPendingItemsCheck = true;

    // Try to find the property in the local properties array first
    let property = properties ? properties.find(p => p.id === propertyId) : null;

    if (property) {
        // Property found locally, open modal immediately
        openKnowledgeModal(property);
        showPropertyTab('knowledge');

        // Reset the skip flag after modal is opened
        setTimeout(() => {
            window.skipPendingItemsCheck = false;
        }, 1000);
    } else {
        // Property not found locally, fetch it from the API
        console.log('Property not found locally, fetching from API...');
        fetch(`/api/properties/${propertyId}`, {
            method: 'GET',
            credentials: 'same-origin'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success && data.property) {
                openKnowledgeModal(data.property);
                showPropertyTab('knowledge');
            } else {
                console.error('Failed to fetch property data:', data.error);
                showErrorMessage('Failed to open Knowledge Base. Please try again.');
            }

            // Reset the skip flag
            setTimeout(() => {
                window.skipPendingItemsCheck = false;
            }, 1000);
        })
        .catch(error => {
            console.error('Error fetching property:', error);
            showErrorMessage('Error opening Knowledge Base. Please try again.');

            // Reset the skip flag
            setTimeout(() => {
                window.skipPendingItemsCheck = false;
            }, 1000);
        });
    }
}

async function copyPropertyMagicLinkFromCard(propertyId, buttonElement) {
    try {
        // Find the property to check its status
        const property = properties.find(p => p.id === propertyId);
        if (!property) {
            showErrorMessage('Property not found');
            return;
        }

        // Check if property is active
        const isActive = (property.status || 'active') === 'active';
        if (!isActive) {
            // Show warning about inactive property
            if (confirm('This property is currently inactive. The magic link will not work for guests until you activate the property.\n\nDo you still want to copy the link?')) {
                // User confirmed, proceed with copying
            } else {
                return; // User cancelled
            }
        }

        // Show loading state
        const originalContent = buttonElement.innerHTML;
        buttonElement.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        buttonElement.disabled = true;

        // Get the magic link
        const response = await fetch(`/api/properties/${propertyId}/magic-link`, {
            method: 'GET',
            credentials: 'same-origin'
        });

        const result = await response.json();

        if (result.success) {
            // Copy to clipboard with fallback
            const copySuccess = await copyToClipboardWithFallback(result.magicLinkUrl);

            if (copySuccess) {
                // Show success feedback
                buttonElement.innerHTML = '<i class="fas fa-check"></i>';
                buttonElement.classList.remove('bg-persian-green', 'hover:bg-green-600');
                buttonElement.classList.add('bg-green-500');

                // Reset button after 2 seconds
                setTimeout(() => {
                    buttonElement.innerHTML = originalContent;
                    buttonElement.classList.remove('bg-green-500');
                    buttonElement.classList.add('bg-persian-green', 'hover:bg-green-600');
                    buttonElement.disabled = false;
                }, 2000);

                showSuccessMessage('Magic link copied to clipboard!');
            } else {
                // Fallback: Show modal with selectable text
                showMagicLinkModal(result.magicLinkUrl);

                // Reset button
                buttonElement.innerHTML = originalContent;
                buttonElement.disabled = false;
            }
        } else {
            throw new Error(result.error || 'Failed to get magic link');
        }

    } catch (error) {
        console.error('Error copying magic link:', error);
        showErrorMessage('Failed to copy magic link: ' + error.message);

        // Reset button
        buttonElement.innerHTML = '<i class="fas fa-copy"></i>';
        buttonElement.disabled = false;
    }
}

// Property Management Modal
function openKnowledgeModal(property) {
    console.log('openKnowledgeModal called with property:', property);
    const modal = document.getElementById('knowledge-modal');

    if (!modal) {
        console.error('Knowledge modal not found in DOM');
        return;
    }

    // Store current property globally
    window.currentProperty = property;
    console.log('Current property set to:', window.currentProperty);

    // Show modal
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    console.log('Modal shown and body overflow set to hidden');

    // Load property details section
    loadPropertyDetailsSection(property);

    // Load initial tab content (knowledge by default)
    showPropertyTab('knowledge');
    console.log('Property tab switched to knowledge');
}

function closeKnowledgeModal() {
    // Check for pending knowledge items before closing
    const property = window.currentProperty;
    if (property && !window.skipPendingItemsCheck) {
        checkPendingItemsBeforeModalClose(property.id, () => {
            // Proceed with closing the modal
            const modal = document.getElementById('knowledge-modal');
            if (modal) {
                modal.classList.add('hidden');
                document.body.style.overflow = 'auto';
                // Clear current property
                window.currentProperty = null;
                // Reset the skip flag
                window.skipPendingItemsCheck = false;
            }
        });
    } else {
        // No property context or skip check, just close the modal
        const modal = document.getElementById('knowledge-modal');
        if (modal) {
            modal.classList.add('hidden');
            document.body.style.overflow = 'auto';
            // Clear current property
            window.currentProperty = null;
            // Reset the skip flag
            window.skipPendingItemsCheck = false;
        }
    }
}

function checkPendingItemsBeforeModalClose(propertyId, onProceed) {
    // Check for pending knowledge items
    fetch(`/api/properties/${propertyId}/knowledge/pending-count`, {
        method: 'GET',
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success && data.has_pending_items) {
            // Show warning modal about pending items
            showPendingItemsModalCloseWarning(propertyId, data.pending_count, onProceed);
        } else {
            // No pending items, proceed with closing
            onProceed();
        }
    })
    .catch(error => {
        console.error('Error checking pending items:', error);
        // If check fails, proceed with closing (don't block on this check)
        onProceed();
    });
}

function showPendingItemsModalCloseWarning(propertyId, pendingCount, onProceed) {
    // Create modal HTML
    const modalHTML = `
        <div id="pending-items-close-warning-modal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div class="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
                <div class="p-6">
                    <div class="flex items-center mb-4">
                        <div class="flex-shrink-0">
                            <i class="fas fa-exclamation-triangle text-yellow-500 text-2xl"></i>
                        </div>
                        <div class="ml-3">
                            <h3 class="text-lg font-medium text-gray-900">
                                Pending Knowledge Items
                            </h3>
                        </div>
                    </div>

                    <div class="mb-6">
                        <p class="text-sm text-gray-600">
                            This property has <strong>${pendingCount}</strong> pending knowledge item${pendingCount > 1 ? 's' : ''}
                            that need${pendingCount > 1 ? '' : 's'} to be reviewed and approved.
                        </p>
                        <p class="text-sm text-gray-600 mt-2">
                            Would you like to review them now before closing?
                        </p>
                    </div>

                    <div class="flex flex-col sm:flex-row gap-3">
                        <button onclick="reviewPendingItemsFromCloseWarning('${propertyId}')"
                                class="flex-1 bg-persian-green hover:bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                            <i class="fas fa-book mr-2"></i>Review Items
                        </button>
                        <button onclick="closePendingItemsCloseWarningModal(true)"
                                class="flex-1 bg-gray-300 hover:bg-gray-400 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                            Close Anyway
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Store the proceed callback for later use
    window.pendingItemsModalCloseProceed = onProceed;

    // Add modal to page
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    document.body.style.overflow = 'hidden';

    // Close on outside click
    const modal = document.getElementById('pending-items-close-warning-modal');
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closePendingItemsCloseWarningModal(false);
        }
    });
}

function closePendingItemsCloseWarningModal(shouldProceed) {
    const modal = document.getElementById('pending-items-close-warning-modal');
    if (modal) {
        modal.remove();
        document.body.style.overflow = 'auto';
    }

    // If user chose to close anyway, proceed with the original action
    if (shouldProceed && window.pendingItemsModalCloseProceed) {
        window.pendingItemsModalCloseProceed();
        window.pendingItemsModalCloseProceed = null;
    }
}
function reviewPendingItemsFromCloseWarning(propertyId) {
    console.log('reviewPendingItemsFromCloseWarning called for property:', propertyId);

    // Close only the warning modal, NOT the Property Management modal
    const warningModal = document.getElementById('pending-items-close-warning-modal');
    if (warningModal) {
        warningModal.remove();
        console.log('Warning modal removed');
    }

    // Clear the proceed callback since we're not proceeding with closing
    window.pendingItemsModalCloseProceed = null;
    console.log('Proceed callback cleared');

    // Ensure the Property Management modal stays open
    const knowledgeModal = document.getElementById('knowledge-modal');
    if (knowledgeModal) {
        knowledgeModal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        console.log('Knowledge modal ensured to be open');
    }

    // Set flag to skip pending items check when modal operations happen
    window.skipPendingItemsCheck = true;

    // Switch to knowledge tab to show pending items (Property Management modal stays open)
    console.log('Switching to knowledge tab');
    showPropertyTab('knowledge');

    // Reset the skip flag after a short delay to allow tab switching
    setTimeout(() => {
        window.skipPendingItemsCheck = false;
        console.log('Skip flag reset');
    }, 1000);
}

function loadPropertyDetailsSection(property) {
    const section = document.getElementById('property-details-section');
    if (!section) return;

    // Debug: Log complete property structure
    console.log('=== PROPERTY DATA DEBUG ===');
    console.log('Full property object:', property);
    console.log('Property status:', property.status);
    console.log('Property wifiDetails:', property.wifiDetails);
    console.log('Property icalUrl:', property.icalUrl);
    console.log('Property checkInTime:', property.checkInTime);
    console.log('Property checkOutTime:', property.checkOutTime);
    console.log('=== END DEBUG ===');

    section.innerHTML = createPropertyDetailsHTML(property);

    // Initialize editable fields
    initializeEditableFields();
}

function createPropertyDetailsHTML(property) {
    // Debug status in header
    console.log('Creating property details header - Status:', property.status);

    // Normalize status - handle undefined, null, empty string
    const normalizedStatus = property.status || 'active';
    const isActive = normalizedStatus === 'active';
    const statusText = isActive ? 'Active' : 'Inactive';
    const statusClass = isActive ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800';

    console.log('Header normalized status:', normalizedStatus, 'isActive:', isActive, 'statusText:', statusText);

    return `
        <div class="flex items-center justify-between">
            <div>
                <h4 class="font-semibold text-gray-900">${property.name || 'Unnamed Property'}</h4>
                <p class="text-sm text-gray-600">${property.address || 'No address provided'}</p>
            </div>
            <div class="text-right">
                <span class="px-2 py-1 rounded-full text-xs font-medium ${statusClass}">
                    ${statusText}
                </span>
            </div>
        </div>
    `;
}

// Property tab management
function showPropertyTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.property-tab-content').forEach(tab => {
        tab.classList.add('hidden');
    });

    // Remove active class from all tab buttons
    document.querySelectorAll('.property-tab-btn').forEach(btn => {
        btn.classList.remove('active', 'border-persian-green', 'text-persian-green');
        btn.classList.add('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
    });

    // Show selected tab content
    const selectedTab = document.getElementById(`property-${tabName}-tab`);
    if (selectedTab) {
        selectedTab.classList.remove('hidden');
    }

    // Add active class to selected tab button
    const selectedBtn = document.querySelector(`[data-tab="${tabName}"]`);
    if (selectedBtn) {
        selectedBtn.classList.add('active', 'border-persian-green', 'text-persian-green');
        selectedBtn.classList.remove('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
    }

    // Load tab content
    loadTabContent(tabName);
}

function loadTabContent(tabName) {
    const property = window.currentProperty;
    if (!property) return;

    switch (tabName) {
        case 'knowledge':
            loadKnowledgeTabContent(property);
            break;
        case 'configuration':
            loadConfigurationTabContent(property);
            break;
        // Analytics case commented out since Analytics tab is disabled
        /*
        case 'analytics':
            loadAnalyticsTabContent(property);
            break;
        */
    }
}

// Editable fields functionality
function initializeEditableFields() {
    document.querySelectorAll('.editable-field').forEach(field => {
        field.addEventListener('click', function() {
            if (!this.classList.contains('editing')) {
                makeFieldEditable(this);
            }
        });
    });
}

function makeFieldEditable(field) {
    const currentValue = field.textContent.trim();
    const fieldType = field.dataset.type || 'text';
    const fieldName = field.dataset.field;

    field.classList.add('editing');

    let inputHTML = '';

    switch (fieldType) {
        case 'textarea':
            inputHTML = `<textarea class="w-full resize-none" rows="3">${currentValue}</textarea>`;
            break;
        case 'select':
            const options = field.dataset.options.split(',');
            const optionsHTML = options.map(opt =>
                `<option value="${opt}" ${opt === currentValue ? 'selected' : ''}>${opt}</option>`
            ).join('');
            inputHTML = `<select class="w-full">${optionsHTML}</select>`;
            break;
        case 'time':
            inputHTML = `<input type="time" class="w-full" value="${currentValue}">`;
            break;
        case 'password':
            const displayValue = currentValue === 'Not configured' ? '' : currentValue;
            inputHTML = `<input type="text" class="w-full" value="${displayValue}" placeholder="Enter password">`;
            break;
        default:
            const displayValue2 = currentValue === 'No address provided' || currentValue === 'No description provided' || currentValue === 'Unnamed Property' || currentValue === 'Not configured' ? '' : currentValue;
            inputHTML = `<input type="text" class="w-full" value="${displayValue2}">`;
    }

    field.innerHTML = inputHTML;

    const input = field.querySelector('input, textarea, select');
    if (input) {
        input.focus();
        if (input.type === 'text' || input.tagName === 'TEXTAREA') {
            input.select();
        }

        // Save on Enter or blur
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && this.tagName !== 'TEXTAREA') {
                e.preventDefault();
                saveFieldValue(field, fieldName, this.value);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                cancelFieldEdit(field, currentValue);
            }
        });

        input.addEventListener('blur', function() {
            // Add a small delay to prevent DOM conflicts
            setTimeout(() => {
                if (field.classList.contains('editing')) {
                    saveFieldValue(field, fieldName, this.value);
                }
            }, 10);
        });
    }
}

function saveFieldValue(field, fieldName, newValue) {
    const property = window.currentProperty;
    if (!property) return;

    // Show loading state
    field.innerHTML = '<i class="fas fa-spinner fa-spin text-persian-green"></i>';

    // Validate iCal URL if that's what we're updating
    if (fieldName === 'icalUrl') {
        const validation = validateICalUrl(newValue);
        if (!validation.valid) {
            // Show error and revert field
            field.innerHTML = property[fieldName] || getDefaultDisplayValue(fieldName);
            field.classList.remove('editing');
            alert('Invalid iCal URL:\n\n' + validation.message);
            return;
        }
    }

    // Prepare update data
    const updateData = {};

    // Handle nested fields
    if (fieldName.includes('.')) {
        const [parentField, childField] = fieldName.split('.');
        if (parentField === 'wifiDetails') {
            updateData.wifiDetails = {
                ...(property.wifiDetails || {}),
                [childField]: newValue
            };
        }
    } else {
        updateData[fieldName] = newValue;
    }

    // Send update request
    fetch(`/api/properties/${property.id}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify(updateData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update local property data
            if (fieldName.includes('.')) {
                const [parentField, childField] = fieldName.split('.');
                if (parentField === 'wifiDetails') {
                    if (!property.wifiDetails) property.wifiDetails = {};
                    property.wifiDetails[childField] = newValue;
                }
            } else {
                property[fieldName] = newValue;
            }

            // Update field display
            const displayValue = newValue || getDefaultDisplayValue(fieldName);
            field.textContent = displayValue;
            field.classList.remove('editing');

            // Show success feedback
            field.style.backgroundColor = '#d1fae5';
            setTimeout(() => {
                field.style.backgroundColor = '';
            }, 1000);

            // Update the global properties array
            const propertyIndex = properties.findIndex(p => p.id === property.id);
            if (propertyIndex !== -1) {
                properties[propertyIndex] = { ...properties[propertyIndex], ...property };
            }

            // Update property cards if name, address, status, or description changed
            if (['name', 'address', 'status', 'description'].includes(fieldName)) {
                updatePropertyCard(property);
            }

            // Update property details header if name, address, or status changed
            if (['name', 'address', 'status'].includes(fieldName)) {
                updatePropertyDetailsHeader(property);
            }
        } else {
            throw new Error(data.error || 'Failed to update property');
        }
    })
    .catch(error => {
        console.error('Error updating property:', error);
        // Restore original value
        const originalValue = getOriginalFieldValue(property, fieldName);
        field.textContent = originalValue;
        field.classList.remove('editing');

        // Show error feedback
        field.style.backgroundColor = '#fee2e2';
        setTimeout(() => {
            field.style.backgroundColor = '';
        }, 2000);

        alert('Error updating property: ' + error.message);
    });
}

function cancelFieldEdit(field, originalValue) {
    field.textContent = originalValue;
    field.classList.remove('editing');
}

function getDefaultDisplayValue(fieldName) {
    const defaults = {
        'name': 'Unnamed Property',
        'address': 'No address provided',
        'description': 'No description provided',
        'wifiDetails.network': 'Not configured',
        'wifiDetails.password': 'Not configured',
        'status': 'active',
        'checkInTime': '15:00',
        'checkOutTime': '11:00',
        'icalUrl': 'Not configured'
    };
    return defaults[fieldName] || 'Not set';
}

function getOriginalFieldValue(property, fieldName) {
    if (fieldName.includes('.')) {
        const [parentField, childField] = fieldName.split('.');
        if (parentField === 'wifiDetails') {
            return property.wifiDetails?.[childField] || getDefaultDisplayValue(fieldName);
        }
    }
    return property[fieldName] || getDefaultDisplayValue(fieldName);
}

function updatePropertyCard(property) {
    // Find the property card and update its content
    const propertyCard = document.querySelector(`[data-property-id="${property.id}"]`);
    if (!propertyCard) return;

    // Update property name
    const nameElement = propertyCard.querySelector('.property-name');
    if (nameElement) {
        nameElement.textContent = property.name || 'Unnamed Property';
    }

    // Update property address
    const addressElement = propertyCard.querySelector('.property-address');
    if (addressElement) {
        addressElement.textContent = property.address || 'No address provided';
    }

    // Update property description
    const descriptionElement = propertyCard.querySelector('.property-description');
    if (descriptionElement) {
        if (property.description) {
            descriptionElement.textContent = property.description;
            descriptionElement.style.display = '';
            descriptionElement.className = 'property-description text-gray-700 text-sm';
        } else {
            descriptionElement.style.display = 'none';
        }
    }

    // Normalize status once for consistency
    const normalizedStatus = property.status || 'active';
    const isActive = normalizedStatus === 'active';
    console.log('Updating property card - property.status:', property.status, 'normalized:', normalizedStatus, 'isActive:', isActive);

    // Update status badge
    const statusBadge = propertyCard.querySelector('.status-badge');
    if (statusBadge) {
        // Remove old classes and add new ones
        statusBadge.className = `status-badge px-3 py-1 rounded-full text-sm font-medium ${
            isActive ? 'status-badge-active' : 'status-badge-inactive'
        }`;
        statusBadge.textContent = isActive ? 'Active' : 'Inactive';
        console.log('Updated status badge:', statusBadge.textContent, statusBadge.className);
    }

    // Update toggle switch
    const toggle = propertyCard.querySelector('input[type="checkbox"]');
    if (toggle) {
        toggle.checked = isActive;
        console.log('Updated toggle checked:', toggle.checked);
    }
}

// Listen for property updates from other modules (e.g., Setup modal) and refresh the card/header
window.addEventListener('propertyUpdated', (event) => {
    try {
        const { propertyId, property } = event.detail || {};
        if (!property || !propertyId) return;

        // Update the global properties array
        const idx = properties.findIndex(p => p.id === propertyId);
        if (idx !== -1) {
            properties[idx] = { ...properties[idx], ...property };
        }

        // Update property card and details header
        updatePropertyCard(property);
        updatePropertyDetailsHeader(property);
    } catch (e) {
        console.warn('Failed to process propertyUpdated event:', e);
    }
});

function updatePropertyDetailsHeader(property) {
    // Update the property details header in the modal
    const detailsSection = document.getElementById('property-details-section');
    if (detailsSection) {
        detailsSection.innerHTML = createPropertyDetailsHTML(property);
    }
}

// Download property QR Code image via backend endpoint
async function downloadPropertyQRCode(propertyId) {
    try {
        const response = await fetch(`/api/properties/${propertyId}/magic-link/qr`, {
            method: 'GET',
            credentials: 'same-origin'
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        // Try to extract filename from Content-Disposition; fallback
        const cd = response.headers.get('Content-Disposition') || response.headers.get('content-disposition') || '';
        const match = cd.match(/filename="?([^";]+)"?/i);
        a.download = match ? match[1] : 'property_qr_code.png';
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    } catch (err) {
        console.error('Failed to download QR code:', err);
        alert('Failed to generate or download the QR code. Please try again.');
    }
}

function loadKnowledgeTabContent(property) {
    const content = document.getElementById('knowledge-modal-content');
    if (!content) return;

    // Show loading state
    content.innerHTML = `
        <div class="text-center py-8">
            <i class="fas fa-spinner fa-spin text-2xl text-persian-green mb-4"></i>
            <p class="text-gray-600">Loading knowledge items...</p>
        </div>
    `;

    // Load knowledge items for this property
    fetch(`/api/knowledge-items?propertyId=${property.id}`, {
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            renderKnowledgeTabContent(property, data.items || []);
        } else {
            renderKnowledgeError(data.error || 'Failed to load knowledge items');
        }
    })
    .catch(error => {
        console.error('Error loading knowledge items:', error);
        renderKnowledgeError('Error loading knowledge items: ' + error.message);
    });
}
function loadConfigurationTabContent(property) {
    const content = document.getElementById('configuration-content');
    if (!content) return;

    // Debug WiFi and iCal data
    console.log('=== CONFIGURATION TAB DEBUG ===');
    console.log('Property wifiDetails:', property.wifiDetails);
    console.log('Property icalUrl:', property.icalUrl);
    console.log('WiFi network:', property.wifiDetails?.network);
    console.log('WiFi password:', property.wifiDetails?.password);
    console.log('=== END CONFIGURATION DEBUG ===');

    content.innerHTML = `
        <div class="space-y-6">
            <!-- Basic Property Information -->
            <div class="bg-white border border-gray-200 rounded-lg p-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">Basic Information</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Property Name</label>
                            <span class="editable-field font-medium" data-field="name" data-type="text">
                                ${property.name || 'Unnamed Property'}
                            </span>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Address</label>
                            <span class="editable-field" data-field="address" data-type="text">
                                ${property.address || 'No address provided'}
                            </span>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Status</label>
                            <span class="editable-field" data-field="status" data-type="select" data-options="active,inactive">
                                ${(property.status || 'active')}
                            </span>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Guest Access Link</label>
                            <div class="flex items-center gap-2">
                                <button onclick="copyPropertyMagicLink('${property.id}')"
                                        class="bg-persian-green hover:bg-green-600 text-white px-3 py-1 rounded text-sm font-medium transition-colors">
                                    <i class="fas fa-copy mr-1"></i>Copy Link
                                </button>
                                <button onclick="downloadPropertyQRCode('${property.id}')"
                                        class="bg-saffron hover:bg-yellow-500 text-dark-purple px-3 py-1 rounded text-sm font-medium transition-colors">
                                    <i class="fas fa-qrcode mr-1"></i>Download QR Code
                                </button>
                            </div>
                            <p class="text-xs text-gray-500 mt-1">Share this link with guests to access property information</p>
                        </div>
                    </div>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Default Check-in Time</label>
                            <span class="editable-field" data-field="checkInTime" data-type="time">
                                ${property.checkInTime || '15:00'}
                            </span>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Default Check-out Time</label>
                            <span class="editable-field" data-field="checkOutTime" data-type="time">
                                ${property.checkOutTime || '11:00'}
                            </span>
                        </div>
                    </div>
                </div>
                <div class="mt-4">
                    <label class="block text-sm font-medium text-gray-700 mb-1">Description</label>
                    <span class="editable-field" data-field="description" data-type="textarea">
                        ${property.description || 'No description provided'}
                    </span>
                </div>
            </div>

            <!-- WiFi Configuration -->
            <div class="bg-white border border-gray-200 rounded-lg p-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">WiFi Configuration</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Network Name</label>
                        <span class="editable-field" data-field="wifiDetails.network" data-type="text">
                            ${property.wifiDetails?.network || 'Not configured'}
                        </span>
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                        <span class="editable-field" data-field="wifiDetails.password" data-type="password">
                            ${property.wifiDetails?.password || 'Not configured'}
                        </span>
                    </div>
                </div>
            </div>

            <!-- Email Templates - commented out as requested
            <div class="bg-white border border-gray-200 rounded-lg p-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">Email Templates</h3>
                <div class="text-center py-8">
                    <i class="fas fa-envelope text-4xl text-gray-400 mb-4"></i>
                    <p class="text-gray-600 mb-2">Email Template Management</p>
                    <p class="text-sm text-gray-500">Coming soon - Customize welcome, reminder, and review emails</p>
                </div>
            </div>
            -->

            <!-- Integrations -->
            <div class="bg-white border border-gray-200 rounded-lg p-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">Platform Integrations</h3>

                <!-- Calendar Integration -->
                <div class="mb-6">
                    <h4 class="text-md font-medium text-gray-800 mb-3">Calendar Integration</h4>
                    <div class="grid grid-cols-1 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Airbnb iCal URL</label>
                            <span class="editable-field" data-field="icalUrl" data-type="text">
                                ${property.icalUrl || 'Not configured'}
                            </span>
                            <p class="text-xs text-gray-500 mt-1">Updates your reservations from Airbnb</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Danger Zone -->
            <div class="bg-red-50 border border-red-200 rounded-lg p-6">
                <h3 class="text-lg font-semibold text-red-900 mb-4">Danger Zone</h3>
                <div class="flex items-center justify-between">
                    <div>
                        <h4 class="text-sm font-medium text-red-900">Delete Property</h4>
                        <p class="text-sm text-red-700">Permanently delete this property and all associated data. This action cannot be undone.</p>
                    </div>
                    <button onclick="deleteProperty('${property.id}')"
                            class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg font-medium transition-colors">
                        <i class="fas fa-trash mr-2"></i>Delete Property
                    </button>
                </div>
            </div>
        </div>
    `;

    // Initialize editable fields for this tab
    setTimeout(() => {
        initializeEditableFields();
    }, 100);
}

// loadAnalyticsTabContent function - commented out as requested since Analytics tab is disabled
/*
function loadAnalyticsTabContent(property) {
    const content = document.getElementById('analytics-content');
    if (!content) return;

    content.innerHTML = `
        <div class="space-y-6">
            <div class="text-center py-8">
                <i class="fas fa-chart-bar text-4xl text-gray-400 mb-4"></i>
                <p class="text-gray-600 mb-2">Property Analytics</p>
                <p class="text-sm text-gray-500">Coming soon - Booking trends, guest insights, and performance metrics</p>
            </div>
        </div>
    `;
}
*/

function renderKnowledgeTabContent(property, knowledgeItems) {
    const content = document.getElementById('knowledge-modal-content');
    if (!content) return;

    // Store items globally for filtering
    window.currentKnowledgeItems = knowledgeItems;

    content.innerHTML = createComprehensiveKnowledgeHTML(property, knowledgeItems);

    // Initialize filtering and pagination
    initializeKnowledgeFiltering();

    // Render initial items
    renderFilteredKnowledgeItems();

    // Render amenities and appliances
    renderBasicAmenities(property);
    renderAppliances(property);
}

function renderKnowledgeError(errorMessage) {
    const content = document.getElementById('knowledge-modal-content');
    if (!content) return;

    content.innerHTML = `
        <div class="text-center py-8">
            <i class="fas fa-exclamation-triangle text-4xl text-red-500 mb-4"></i>
            <p class="text-red-600 mb-2">Error Loading Knowledge</p>
            <p class="text-sm text-gray-500 mb-4">${errorMessage}</p>
            <button onclick="loadKnowledgeContent()" class="bg-persian-green hover:bg-green-600 text-white px-4 py-2 rounded-lg">
                <i class="fas fa-redo mr-2"></i>Try Again
            </button>
        </div>
    `;
}

function createComprehensiveKnowledgeHTML(property, knowledgeItems) {
    const approvedItems = knowledgeItems.filter(item => item.status === 'approved');
    const pendingItems = knowledgeItems.filter(item => item.status !== 'approved');

    return `
        <div class="space-y-6">
            <!-- Knowledge Overview Stats -->
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div class="bg-green-50 border border-green-200 rounded-lg p-4">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <i class="fas fa-check-circle text-green-600 text-xl"></i>
                        </div>
                        <div class="ml-3">
                            <p class="text-sm font-medium text-green-800">Approved</p>
                            <p class="text-2xl font-bold text-green-900" id="approved-count">${approvedItems.length}</p>
                        </div>
                    </div>
                </div>

                <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <i class="fas fa-clock text-yellow-600 text-xl"></i>
                        </div>
                        <div class="ml-3">
                            <p class="text-sm font-medium text-yellow-800">Pending</p>
                            <p class="text-2xl font-bold text-yellow-900" id="pending-count">${pendingItems.length}</p>
                        </div>
                    </div>
                </div>

                <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <i class="fas fa-times-circle text-red-600 text-xl"></i>
                        </div>
                        <div class="ml-3">
                            <p class="text-sm font-medium text-red-800">Rejected</p>
                            <p class="text-2xl font-bold text-red-900" id="rejected-count">${knowledgeItems.filter(item => item.status === 'rejected').length}</p>
                        </div>
                    </div>
                </div>

                <div class="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <div class="flex items-center">
                        <div class="flex-shrink-0">
                            <i class="fas fa-database text-blue-600 text-xl"></i>
                        </div>
                        <div class="ml-3">
                            <p class="text-sm font-medium text-blue-800">Total</p>
                            <p class="text-2xl font-bold text-blue-900" id="total-count">${knowledgeItems.length}</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Action Buttons -->
            <div class="flex flex-wrap gap-3">
                <button onclick="addKnowledgeItem('${property.id}')"
                        class="bg-persian-green hover:bg-green-600 text-white px-4 py-2 rounded-lg font-medium transition-colors">
                    <i class="fas fa-plus mr-2"></i>Add Knowledge
                </button>
                <button onclick="event.preventDefault(); event.stopPropagation(); refreshKnowledgeItems('${property.id}')"
                        class="bg-gray-500 hover:bg-gray-600 text-white px-4 py-2 rounded-lg font-medium transition-colors">
                    <i class="fas fa-sync-alt mr-2"></i>Refresh
                </button>

            </div>

            <!-- Filters and Search -->
            <div class="bg-white border border-gray-200 rounded-lg p-4">
                <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Search</label>
                        <input type="text" id="knowledge-search" placeholder="Search knowledge items..."
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Type</label>
                        <select id="knowledge-type-filter"
                                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green">
                            <option value="">All Types</option>
                            <option value="information">Information</option>
                            <option value="rule">Rules</option>
                            <option value="instruction">Instructions</option>
                            <option value="amenity">Amenities</option>
                            <option value="places">Places</option>
                            <option value="basic_info">Basic Info</option>
                            <option value="house_rule">House Rules</option>
                            <option value="emergency">Emergency</option>
                            <option value="local_recommendation">Local Recommendations</option>
                            <option value="property_fact">Property Facts</option>
                            <option value="other">Other</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Status</label>
                        <select id="knowledge-status-filter"
                                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green">
                            <option value="">All Status</option>
                            <option value="approved">Approved</option>
                            <option value="pending">Pending</option>
                            <option value="rejected">Rejected</option>
                            <option value="error">Error</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Sort By</label>
                        <select id="knowledge-sort"
                                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green">
                            <option value="pending_first" selected>Pending First (default)</option>
                            <option value="created_desc">Newest First</option>
                            <option value="created_asc">Oldest First</option>
                            <option value="type">Type</option>
                            <option value="status">Status</option>
                        </select>
                    </div>
                </div>
            </div>

            <!-- Knowledge Items List -->
            <div class="bg-white border border-gray-200 rounded-lg">
                <div class="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                    <h4 class="text-lg font-semibold text-gray-900">Knowledge Items</h4>
                    <div class="text-sm text-gray-500">
                        Showing <span id="items-showing">0</span> of <span id="items-total">${knowledgeItems.length}</span> items
                    </div>
                </div>
                <div id="knowledge-items-container" class="p-4">
                    <!-- Items will be rendered here -->
                </div>
                <div id="knowledge-pagination" class="px-4 py-3 border-t border-gray-200">
                    <!-- Pagination will be rendered here -->
                </div>
            </div>

            <!-- Amenities Section -->
            <div class="bg-white border border-gray-200 rounded-lg">
                <div class="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                    <h4 class="text-lg font-semibold text-gray-900">
                        <i class="fas fa-swimming-pool mr-2 text-persian-green"></i>Basic Amenities
                    </h4>
                    <button onclick="addBasicAmenity('${property.id}')"
                            class="bg-persian-green hover:bg-green-600 text-white px-3 py-1 rounded text-sm font-medium transition-colors">
                        <i class="fas fa-plus mr-1"></i>Add Amenity
                    </button>
                </div>
                <div id="basic-amenities-container" class="p-4">
                    <!-- Basic amenities will be rendered here -->
                </div>
            </div>

            <!-- Appliances Section -->
            <div class="bg-white border border-gray-200 rounded-lg">
                <div class="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                    <h4 class="text-lg font-semibold text-gray-900">
                        <i class="fas fa-blender mr-2 text-persian-green"></i>Appliances
                    </h4>
                    <button onclick="addAppliance('${property.id}')"
                            class="bg-persian-green hover:bg-green-600 text-white px-3 py-1 rounded text-sm font-medium transition-colors">
                        <i class="fas fa-plus mr-1"></i>Add Appliance
                    </button>
                </div>
                <div id="appliances-container" class="p-4">
                    <!-- Appliances will be rendered here -->
                </div>
            </div>
        </div>
    `;
}

// Knowledge filtering and rendering
function initializeKnowledgeFiltering() {
    // Add event listeners for filters
    const searchInput = document.getElementById('knowledge-search');
    const typeFilter = document.getElementById('knowledge-type-filter');
    const statusFilter = document.getElementById('knowledge-status-filter');
    const sortSelect = document.getElementById('knowledge-sort');

    if (searchInput) {
        searchInput.addEventListener('input', debounce(renderFilteredKnowledgeItems, 300));
    }

    if (typeFilter) {
        typeFilter.addEventListener('change', renderFilteredKnowledgeItems);
    }

    if (statusFilter) {
        statusFilter.addEventListener('change', renderFilteredKnowledgeItems);
    }

    if (sortSelect) {
        sortSelect.addEventListener('change', renderFilteredKnowledgeItems);
    }
}

function renderFilteredKnowledgeItems() {
    const items = window.currentKnowledgeItems || [];
    const container = document.getElementById('knowledge-items-container');
    const showingSpan = document.getElementById('items-showing');
    const totalSpan = document.getElementById('items-total');

    if (!container) return;

    // Get filter values
    const searchTerm = document.getElementById('knowledge-search')?.value.toLowerCase() || '';
    const typeFilter = document.getElementById('knowledge-type-filter')?.value || '';
    const statusFilter = document.getElementById('knowledge-status-filter')?.value || '';
    const sortBy = document.getElementById('knowledge-sort')?.value || 'pending_first';

    // Filter items
    let filteredItems = items.filter(item => {
        // Search filter
        if (searchTerm) {
            const content = (item.content || '').toLowerCase();
            const tags = (item.tags || []).join(' ').toLowerCase();
            const type = (item.type || '').toLowerCase();

            if (!content.includes(searchTerm) && !tags.includes(searchTerm) && !type.includes(searchTerm)) {
                return false;
            }
        }

        // Type filter
        if (typeFilter && item.type !== typeFilter) {
            return false;
        }

        // Status filter
        if (statusFilter && item.status !== statusFilter) {
            return false;
        }

        return true;
    });

    // Sort items
    filteredItems.sort((a, b) => {
        switch (sortBy) {
            case 'pending_first': {
                const aPending = (a.status !== 'approved') ? 0 : 1;
                const bPending = (b.status !== 'approved') ? 0 : 1;
                if (aPending !== bPending) return aPending - bPending;
                // Tie-breaker: newest first within each group
                return new Date(b.created_at || 0) - new Date(a.created_at || 0);
            }
            case 'created_asc':
                return new Date(a.created_at || 0) - new Date(b.created_at || 0);
            case 'created_desc':
                return new Date(b.created_at || 0) - new Date(a.created_at || 0);
            case 'type':
                return (a.type || '').localeCompare(b.type || '');
            case 'status':
                return (a.status || '').localeCompare(b.status || '');
            default:
                return 0;
        }
    });

    // Update counts
    if (showingSpan) showingSpan.textContent = filteredItems.length;
    if (totalSpan) totalSpan.textContent = items.length;

    // Render items
    if (filteredItems.length === 0) {
        container.innerHTML = `
            <div class="text-center py-8">
                <i class="fas fa-search text-4xl text-gray-400 mb-4"></i>
                <p class="text-gray-600 mb-2">No items found</p>
                <p class="text-sm text-gray-500">Try adjusting your filters or search terms</p>
            </div>
        `;
    } else {
        container.innerHTML = `
            <div class="space-y-3">
                ${filteredItems.map(item => createDetailedKnowledgeItem(item)).join('')}
            </div>
        `;
    }
}
function createDetailedKnowledgeItem(item) {
    const typeIcons = {
        'information': 'fas fa-info-circle',
        'rule': 'fas fa-gavel',
        'instruction': 'fas fa-list-ol',
        'amenity': 'fas fa-swimming-pool',
        'places': 'fas fa-map-marker-alt',
        'basic_info': 'fas fa-home',
        'house_rule': 'fas fa-exclamation-triangle',
        'emergency': 'fas fa-phone',
        'local_recommendation': 'fas fa-star',
        'property_fact': 'fas fa-building',
        'other': 'fas fa-file-text'
    };

    const typeColors = {
        'information': 'type-information',
        'rule': 'type-rule',
        'instruction': 'type-instruction',
        'amenity': 'type-amenity',
        'places': 'type-places',
        'basic_info': 'type-basic-info',
        'house_rule': 'type-house-rule',
        'emergency': 'type-emergency',
        'local_recommendation': 'type-local-recommendation',
        'property_fact': 'type-property-fact',
        'other': 'type-other'
    };

    const statusIcons = {
        'approved': 'fas fa-check-circle text-green-600',
        'pending': 'fas fa-clock text-yellow-600',
        'rejected': 'fas fa-times-circle text-red-600',
        'error': 'fas fa-exclamation-triangle text-red-600'
    };

    const typeIcon = typeIcons[item.type] || 'fas fa-file-text';
    const typeColor = typeColors[item.type] || 'type-general';
    const statusIcon = statusIcons[item.status] || 'fas fa-question-circle text-gray-600';
    const tags = item.tags ? (Array.isArray(item.tags) ? item.tags : item.tags.split(',')) : [];
    const content = item.content || '';
    const truncatedContent = content.length > 200 ? content.substring(0, 200) + '...' : content;

    return `
        <div class="knowledge-item ${item.status} border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
            <div class="flex items-start justify-between">
                <div class="flex-1">
                    <!-- Header -->
                    <div class="flex items-center space-x-3 mb-3">
                        <i class="${typeIcon} text-gray-600"></i>
                        <span class="type-badge ${typeColor}">
                            ${item.type || 'General'}
                        </span>
                        <div class="flex items-center space-x-1">
                            <i class="${statusIcon}"></i>
                            <span class="text-sm font-medium capitalize">${item.status || 'unknown'}</span>
                        </div>
                        ${item.created_at ? `
                            <span class="text-xs text-gray-500">
                                ${new Date(item.created_at).toLocaleDateString()}
                            </span>
                        ` : ''}
                    </div>

                    <!-- Tags -->
                    ${tags.length > 0 ? `
                        <div class="flex flex-wrap gap-1 mb-3">
                            ${tags.map(tag => `
                                <span class="bg-gray-100 text-gray-700 px-2 py-1 rounded text-xs">${tag.trim()}</span>
                            `).join('')}
                        </div>
                    ` : ''}

                    <!-- Content -->
                    <div class="text-sm text-gray-700 mb-3">
                        ${truncatedContent}
                        ${content.length > 200 ? `
                            <button onclick="expandKnowledgeItem('${item.id}')"
                                    class="text-persian-green hover:text-green-600 ml-2">
                                Show more
                            </button>
                        ` : ''}
                    </div>
                </div>

                <!-- Actions -->
                <div class="flex items-center space-x-2 ml-4">
                    ${item.status === 'pending' ? `
                        <button onclick="event.preventDefault(); event.stopPropagation(); approveKnowledgeItem('${item.id}', this)"
                                class="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded text-xs font-medium transition-colors">
                            <i class="fas fa-check mr-1"></i>Approve
                        </button>
                        <button onclick="event.preventDefault(); event.stopPropagation(); rejectKnowledgeItem('${item.id}', this)"
                                class="bg-red-500 hover:bg-red-600 text-white px-3 py-1 rounded text-xs font-medium transition-colors">
                            <i class="fas fa-times mr-1"></i>Reject
                        </button>
                    ` : item.status === 'rejected' ? `
                        <button onclick="event.preventDefault(); event.stopPropagation(); approveKnowledgeItem('${item.id}', this)"
                                class="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded text-xs font-medium transition-colors">
                            <i class="fas fa-check mr-1"></i>Approve
                        </button>
                    ` : item.status === 'approved' ? `
                        <button onclick="event.preventDefault(); event.stopPropagation(); disapproveKnowledgeItem('${item.id}', this)"
                                class="bg-yellow-500 hover:bg-yellow-600 text-white px-3 py-1 rounded text-xs font-medium transition-colors">
                            <i class="fas fa-pause mr-1"></i>Disapprove
                        </button>
                    ` : ''}
                    <button onclick="event.preventDefault(); event.stopPropagation(); editKnowledgeItem('${item.id}')"
                            class="text-gray-500 hover:text-gray-700 p-1">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button onclick="event.preventDefault(); event.stopPropagation(); deleteKnowledgeItem('${item.id}', this)"
                            class="text-red-500 hover:text-red-700 p-1">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        </div>
    `;
}

// Utility function for debouncing
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function createKnowledgeItemPreview(item, isPending) {
    const typeIcons = {
        'QnA': 'fas fa-question-circle',
        'Places': 'fas fa-map-marker-alt',
        'Instructions': 'fas fa-list-ol',
        'Policies': 'fas fa-gavel',
        'General': 'fas fa-info-circle'
    };

    const typeIcon = typeIcons[item.type] || 'fas fa-file-text';
    const tags = item.tags ? (Array.isArray(item.tags) ? item.tags : item.tags.split(',')) : [];
    const content = item.content || '';
    const truncatedContent = content.length > 150 ? content.substring(0, 150) + '...' : content;

    return `
        <div class="border border-gray-200 rounded-lg p-3 ${isPending ? 'bg-yellow-50' : 'bg-gray-50'}">
            <div class="flex items-start justify-between">
                <div class="flex-1">
                    <div class="flex items-center space-x-2 mb-2">
                        <i class="${typeIcon} text-gray-600"></i>
                        <span class="font-medium text-gray-900">${item.type || 'General'}</span>
                        ${isPending ? '<span class="bg-yellow-200 text-yellow-800 px-2 py-1 rounded-full text-xs font-medium">Pending</span>' : ''}
                    </div>

                    ${tags.length > 0 ? `
                        <div class="flex flex-wrap gap-1 mb-2">
                            ${tags.slice(0, 3).map(tag => `
                                <span class="bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs">${tag.trim()}</span>
                            `).join('')}
                            ${tags.length > 3 ? `<span class="text-xs text-gray-500">+${tags.length - 3} more</span>` : ''}
                        </div>
                    ` : ''}

                    <p class="text-sm text-gray-700">${truncatedContent}</p>
                </div>

                <div class="flex items-center space-x-2 ml-4">
                    ${isPending ? `
                        <button onclick="approveKnowledgeItem('${item.id}', this)"
                                class="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded text-xs font-medium transition-colors">
                            Approve
                        </button>
                    ` : ''}
                    <button onclick="editKnowledgeItem('${item.id}')"
                            class="text-gray-500 hover:text-gray-700">
                        <i class="fas fa-edit"></i>
                    </button>
                </div>
            </div>
        </div>
    `;
}

// Knowledge management action functions
function addKnowledgeItem(propertyId) {
    openAddKnowledgeModal(propertyId);
}

function openAddKnowledgeModal(propertyId) {
    // Create the modal
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-black bg-opacity-75 z-[70] flex items-center justify-center p-4';
    modal.id = 'add-knowledge-modal';

    modal.innerHTML = `
        <div class="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[80vh] overflow-y-auto" onclick="event.stopPropagation()">
            <div class="bg-persian-green text-white p-4 rounded-t-lg">
                <div class="flex items-center justify-between">
                    <h3 class="text-lg font-semibold">
                        <i class="fas fa-plus mr-2"></i>Add Knowledge
                    </h3>
                    <button onclick="closeAddKnowledgeModal()" class="text-white hover:text-gray-200">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
            <div class="p-6">
                <form id="add-knowledge-form">
                    <div class="mb-4">
                        <label for="knowledge-text" class="block text-sm font-medium text-gray-700 mb-2">
                            Knowledge Content
                        </label>
                        <textarea
                            id="knowledge-text"
                            name="knowledge_text"
                            rows="12"
                            required
                            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green resize-vertical"
                            placeholder="Enter your knowledge content here...

Examples:
• House rules and policies
• Check-in/check-out instructions
• WiFi information and passwords
• Local recommendations and attractions
• Emergency contacts and procedures
• Appliance instructions and troubleshooting

The AI will automatically organize this into searchable knowledge items with appropriate tags and categories."></textarea>
                    </div>

                    <div class="flex justify-end space-x-3">
                        <button type="button" onclick="closeAddKnowledgeModal()"
                                class="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                            Cancel
                        </button>
                        <button type="submit"
                                class="px-6 py-2 bg-persian-green hover:bg-green-600 text-white rounded-lg font-medium transition-colors">
                            <i class="fas fa-magic mr-2"></i>Process with AI
                        </button>
                    </div>
                </form>
            </div>
        </div>
    `;

    // Add to page
    document.body.appendChild(modal);
    document.body.style.overflow = 'hidden';

    // Focus on textarea
    setTimeout(() => {
        document.getElementById('knowledge-text').focus();
    }, 100);

    // Handle form submission
    document.getElementById('add-knowledge-form').addEventListener('submit', function(e) {
        e.preventDefault();
        submitKnowledgeText(propertyId);
    });

    // Close on outside click
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeAddKnowledgeModal();
        }
    });
}

function closeAddKnowledgeModal() {
    const modal = document.getElementById('add-knowledge-modal');
    if (modal) {
        modal.remove();
        document.body.style.overflow = 'auto';
    }
}

function submitKnowledgeText(propertyId) {
    const textarea = document.getElementById('knowledge-text');
    const submitBtn = document.querySelector('#add-knowledge-form button[type="submit"]');
    const knowledgeText = textarea.value.trim();

    if (!knowledgeText) {
        alert('Please enter some knowledge content.');
        textarea.focus();
        return;
    }

    // Show loading state
    const originalText = submitBtn.innerHTML;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Processing...';
    submitBtn.disabled = true;
    textarea.disabled = true;

    // Prepare form data
    const formData = new FormData();
    formData.append('knowledge_text', knowledgeText);

    // Submit to the existing knowledge_add_text endpoint
    fetch(`/properties/${propertyId}/knowledge/add_text`, {
        method: 'POST',
        credentials: 'same-origin',
        body: formData
    })
    .then(response => {
        if (response.redirected) {
            // The endpoint redirects on success, so we need to handle this differently
            // Close modal and refresh knowledge items
            closeAddKnowledgeModal();

            // Show success message
            showKnowledgeMessage('Knowledge content processed successfully! New items may take a moment to appear.', 'success');

            // Refresh the knowledge items after a short delay
            setTimeout(() => {
                if (window.currentProperty) {
                    refreshKnowledgeItems(window.currentProperty.id);
                }
            }, 2000);

            return;
        }
        return response.text();
    })
    .then(data => {
        if (data) {
            // If we get here, there might have been an error
            console.error('Unexpected response:', data);
            throw new Error('Unexpected response from server');
        }
    })
    .catch(error => {
        console.error('Error submitting knowledge text:', error);

        // Restore form state
        submitBtn.innerHTML = originalText;
        submitBtn.disabled = false;
        textarea.disabled = false;

        // Show error message
        alert('Error processing knowledge content. Please try again.');
    });
}

function showKnowledgeMessage(message, type) {
    // Remove any existing messages
    const existingMessages = document.querySelectorAll('.knowledge-message');
    existingMessages.forEach(msg => msg.remove());

    // Create message element
    const messageEl = document.createElement('div');
    messageEl.className = `knowledge-message fixed top-4 right-4 z-[80] px-4 py-3 rounded-lg shadow-lg max-w-md ${
        type === 'success' ? 'bg-green-100 border border-green-400 text-green-700' :
        type === 'error' ? 'bg-red-100 border border-red-400 text-red-700' :
        'bg-blue-100 border border-blue-400 text-blue-700'
    }`;

    messageEl.innerHTML = `
        <div class="flex items-center">
            <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle'} mr-2"></i>
            <span>${message}</span>
            <button onclick="this.parentElement.parentElement.remove()" class="ml-3 text-gray-500 hover:text-gray-700">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;

    document.body.appendChild(messageEl);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (messageEl.parentNode) {
            messageEl.remove();
        }
    }, 5000);
}

function openFullKnowledgeManager(propertyId) {
    // Open the full knowledge management page in a new tab
    window.open(`/properties/${propertyId}/knowledge`, '_blank');
}

function refreshKnowledgeItems(propertyId) {
    // Use current property from modal context instead of searching
    const property = window.currentProperty;
    if (property && property.id === propertyId) {
        // Show loading state in the knowledge content area
        const content = document.getElementById('knowledge-modal-content');
        if (content) {
            content.innerHTML = `
                <div class="text-center py-8">
                    <i class="fas fa-spinner fa-spin text-2xl text-persian-green mb-4"></i>
                    <p class="text-gray-600">Refreshing knowledge items...</p>
                </div>
            `;
        }

        // Reload knowledge content
        loadKnowledgeTabContent(property);
    } else {
        console.error('Property not found or modal not open');
    }
}

// Note: Emergency Information and Property Facts sections have been removed from Configuration tab
// This data is now managed exclusively through Knowledge Items after property setup completion

// Amenities and Appliances Management Functions
function renderBasicAmenities(property) {
    const container = document.getElementById('basic-amenities-container');
    if (!container) return;

    const amenities = property.amenities?.basic || [];

    if (amenities.length === 0) {
        container.innerHTML = `
            <div class="text-center py-8 text-gray-500">
                <i class="fas fa-swimming-pool text-4xl mb-4"></i>
                <p>No basic amenities added yet</p>
                <p class="text-sm">Click "Add Amenity" to get started</p>
            </div>
        `;
        return;
    }

    container.innerHTML = `
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            ${amenities.map((amenity, index) => `
                <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg border">
                    <span class="font-medium text-gray-900 flex-1"
                          contenteditable="true"
                          onblur="updateBasicAmenity('${property.id}', ${index}, this.textContent.trim())"
                          onkeydown="if(event.key==='Enter'){this.blur();}">${amenity}</span>
                    <button onclick="removeBasicAmenity('${property.id}', ${index})"
                            class="text-red-500 hover:text-red-700 p-1 ml-2">
                        <i class="fas fa-trash text-sm"></i>
                    </button>
                </div>
            `).join('')}
        </div>
    `;
}
function renderAppliances(property) {
    const container = document.getElementById('appliances-container');
    if (!container) return;

    const appliances = property.amenities?.appliances || [];

    if (appliances.length === 0) {
        container.innerHTML = `
            <div class="text-center py-8 text-gray-500">
                <i class="fas fa-blender text-4xl mb-4"></i>
                <p>No appliances added yet</p>
                <p class="text-sm">Click "Add Appliance" to get started</p>
            </div>
        `;
        return;
    }

    container.innerHTML = `
        <div class="space-y-3">
            ${appliances.map((appliance, index) => {
                // Ensure appliance is an object
                const applianceObj = typeof appliance === 'object' ? appliance : { name: appliance || '', location: '', brand: '', model: '' };
                return `
                <div class="p-4 bg-gray-50 rounded-lg border">
                    <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Name</label>
                            <input type="text" value="${applianceObj.name || ''}" placeholder="Appliance name"
                                   class="w-full px-2 py-1 border rounded text-sm"
                                   onblur="updateApplianceField('${property.id}', ${index}, 'name', this.value)">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Location</label>
                            <input type="text" value="${applianceObj.location || ''}" placeholder="Location"
                                   class="w-full px-2 py-1 border rounded text-sm"
                                   onblur="updateApplianceField('${property.id}', ${index}, 'location', this.value)">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Brand</label>
                            <input type="text" value="${applianceObj.brand || ''}" placeholder="Brand"
                                   class="w-full px-2 py-1 border rounded text-sm"
                                   onblur="updateApplianceField('${property.id}', ${index}, 'brand', this.value)">
                        </div>
                        <div class="flex items-end space-x-2">
                            <div class="flex-1">
                                <label class="block text-xs font-medium text-gray-700 mb-1">Model</label>
                                <input type="text" value="${applianceObj.model || ''}" placeholder="Model"
                                       class="w-full px-2 py-1 border rounded text-sm"
                                       onblur="updateApplianceField('${property.id}', ${index}, 'model', this.value)">
                            </div>
                            <button onclick="removeAppliance('${property.id}', ${index})"
                                    class="text-red-500 hover:text-red-700 p-2">
                                <i class="fas fa-trash text-sm"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `;}).join('')}
        </div>
    `;
}

// Amenities and Appliances Action Functions
function addBasicAmenity(propertyId) {
    const container = document.getElementById('basic-amenities-container');
    if (!container) return;

    // Check if there's already an input field
    if (container.querySelector('.new-amenity-input')) return;

    const property = window.currentProperty;
    if (!property) return;

    // Initialize amenities structure if needed
    if (!property.amenities) property.amenities = {};
    if (!property.amenities.basic) property.amenities.basic = [];

    // Add input field at the end
    const inputHtml = `
        <div class="new-amenity-input mt-3 p-3 bg-blue-50 rounded-lg border-2 border-blue-200">
            <div class="flex items-center space-x-2">
                <input type="text"
                       id="new-amenity-name"
                       placeholder="Enter amenity name..."
                       class="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                       onkeydown="if(event.key==='Enter'){saveNewBasicAmenity('${propertyId}');} else if(event.key==='Escape'){cancelNewBasicAmenity();}">
                <button onclick="saveNewBasicAmenity('${propertyId}')"
                        class="bg-persian-green hover:bg-green-600 text-white px-3 py-2 rounded-lg text-sm font-medium transition-colors">
                    <i class="fas fa-check mr-1"></i>Add
                </button>
                <button onclick="cancelNewBasicAmenity()"
                        class="bg-gray-500 hover:bg-gray-600 text-white px-3 py-2 rounded-lg text-sm font-medium transition-colors">
                    <i class="fas fa-times mr-1"></i>Cancel
                </button>
            </div>
            <p class="text-xs text-gray-600 mt-1">Press Enter to add, Escape to cancel</p>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', inputHtml);

    // Focus the input field
    const input = document.getElementById('new-amenity-name');
    if (input) input.focus();
}

function saveNewBasicAmenity(propertyId) {
    const input = document.getElementById('new-amenity-name');
    if (!input) return;

    const amenityName = input.value.trim();
    if (!amenityName) {
        input.focus();
        return;
    }

    const property = window.currentProperty;
    if (!property) return;

    // Add the new amenity
    property.amenities.basic.push(amenityName);

    // Save to server
    savePropertyAmenities(propertyId, property.amenities)
        .then(() => {
            // Re-render amenities (this will remove the input field)
            renderBasicAmenities(property);
        })
        .catch(error => {
            console.error('Error adding amenity:', error);
            alert('Failed to add amenity: ' + error.message);
            // Remove from local array on error
            property.amenities.basic.pop();
            input.focus();
        });
}

function cancelNewBasicAmenity() {
    const inputContainer = document.querySelector('.new-amenity-input');
    if (inputContainer) {
        inputContainer.remove();
    }
}

function updateBasicAmenity(propertyId, index, newValue) {
    if (!newValue.trim()) return;

    const property = window.currentProperty;
    if (!property || !property.amenities?.basic) return;

    const oldValue = property.amenities.basic[index];
    property.amenities.basic[index] = newValue.trim();

    // Save to server
    savePropertyAmenities(propertyId, property.amenities)
        .catch(error => {
            console.error('Error updating amenity:', error);
            alert('Failed to update amenity: ' + error.message);
            // Revert on error
            property.amenities.basic[index] = oldValue;
            renderBasicAmenities(property);
        });
}

function removeBasicAmenity(propertyId, index) {
    if (!confirm('Are you sure you want to remove this amenity?')) return;

    const property = window.currentProperty;
    if (!property || !property.amenities?.basic) return;

    const removedAmenity = property.amenities.basic.splice(index, 1)[0];

    // Save to server
    savePropertyAmenities(propertyId, property.amenities)
        .then(() => {
            // Re-render amenities
            renderBasicAmenities(property);
        })
        .catch(error => {
            console.error('Error removing amenity:', error);
            alert('Failed to remove amenity: ' + error.message);
            // Restore on error
            property.amenities.basic.splice(index, 0, removedAmenity);
            renderBasicAmenities(property);
        });
}

function addAppliance(propertyId) {
    const container = document.getElementById('appliances-container');
    if (!container) return;

    // Check if there's already an input field
    if (container.querySelector('.new-appliance-input')) return;

    const property = window.currentProperty;
    if (!property) return;

    // Initialize amenities structure if needed
    if (!property.amenities) property.amenities = {};
    if (!property.amenities.appliances) property.amenities.appliances = [];

    // Add input field at the end
    const inputHtml = `
        <div class="new-appliance-input mt-3 p-4 bg-blue-50 rounded-lg border-2 border-blue-200">
            <div class="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
                <div>
                    <label class="block text-xs font-medium text-gray-700 mb-1">Name *</label>
                    <input type="text"
                           id="new-appliance-name"
                           placeholder="Appliance name"
                           class="w-full px-2 py-1 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-persian-green"
                           onkeydown="if(event.key==='Enter'){saveNewAppliance('${propertyId}');} else if(event.key==='Escape'){cancelNewAppliance();}">
                </div>
                <div>
                    <label class="block text-xs font-medium text-gray-700 mb-1">Location</label>
                    <input type="text"
                           id="new-appliance-location"
                           placeholder="Location"
                           class="w-full px-2 py-1 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-persian-green">
                </div>
                <div>
                    <label class="block text-xs font-medium text-gray-700 mb-1">Brand</label>
                    <input type="text"
                           id="new-appliance-brand"
                           placeholder="Brand"
                           class="w-full px-2 py-1 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-persian-green">
                </div>
                <div>
                    <label class="block text-xs font-medium text-gray-700 mb-1">Model</label>
                    <input type="text"
                           id="new-appliance-model"
                           placeholder="Model"
                           class="w-full px-2 py-1 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-persian-green">
                </div>
            </div>
            <div class="flex items-center space-x-2">
                <button onclick="saveNewAppliance('${propertyId}')"
                        class="bg-persian-green hover:bg-green-600 text-white px-3 py-2 rounded-lg text-sm font-medium transition-colors">
                    <i class="fas fa-check mr-1"></i>Add Appliance
                </button>
                <button onclick="cancelNewAppliance()"
                        class="bg-gray-500 hover:bg-gray-600 text-white px-3 py-2 rounded-lg text-sm font-medium transition-colors">
                    <i class="fas fa-times mr-1"></i>Cancel
                </button>
            </div>
            <p class="text-xs text-gray-600 mt-1">Press Enter to add, Escape to cancel</p>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', inputHtml);

    // Focus the name input field
    const input = document.getElementById('new-appliance-name');
    if (input) input.focus();
}

function saveNewAppliance(propertyId) {
    const nameInput = document.getElementById('new-appliance-name');
    const locationInput = document.getElementById('new-appliance-location');
    const brandInput = document.getElementById('new-appliance-brand');
    const modelInput = document.getElementById('new-appliance-model');

    if (!nameInput) return;

    const applianceName = nameInput.value.trim();
    if (!applianceName) {
        nameInput.focus();
        return;
    }

    const property = window.currentProperty;
    if (!property) return;

    // Create new appliance object
    const newAppliance = {
        name: applianceName,
        location: locationInput ? locationInput.value.trim() : '',
        brand: brandInput ? brandInput.value.trim() : '',
        model: modelInput ? modelInput.value.trim() : ''
    };

    // Add the new appliance
    property.amenities.appliances.push(newAppliance);

    // Save to server
    savePropertyAmenities(propertyId, property.amenities)
        .then(() => {
            // Re-render appliances (this will remove the input field)
            renderAppliances(property);
        })
        .catch(error => {
            console.error('Error adding appliance:', error);
            alert('Failed to add appliance: ' + error.message);
            // Remove from local array on error
            property.amenities.appliances.pop();
            nameInput.focus();
        });
}

function cancelNewAppliance() {
    const inputContainer = document.querySelector('.new-appliance-input');
    if (inputContainer) {
        inputContainer.remove();
    }
}

function updateApplianceField(propertyId, index, field, newValue) {
    const property = window.currentProperty;
    if (!property || !property.amenities?.appliances) return;

    const appliance = property.amenities.appliances[index];
    if (!appliance) return;

    const oldValue = appliance[field];
    appliance[field] = newValue.trim();

    // Save to server
    savePropertyAmenities(propertyId, property.amenities)
        .catch(error => {
            console.error('Error updating appliance:', error);
            alert('Failed to update appliance: ' + error.message);
            // Revert on error
            appliance[field] = oldValue;
            renderAppliances(property);
        });
}

function removeAppliance(propertyId, index) {
    if (!confirm('Are you sure you want to remove this appliance?')) return;

    const property = window.currentProperty;
    if (!property || !property.amenities?.appliances) return;

    const removedAppliance = property.amenities.appliances.splice(index, 1)[0];

    // Save to server
    savePropertyAmenities(propertyId, property.amenities)
        .then(() => {
            // Re-render appliances
            renderAppliances(property);
        })
        .catch(error => {
            console.error('Error removing appliance:', error);
            alert('Failed to remove appliance: ' + error.message);
            // Restore on error
            property.amenities.appliances.splice(index, 0, removedAppliance);
            renderAppliances(property);
        });
}

async function savePropertyAmenities(propertyId, amenities) {
    const response = await fetch(`/api/properties/${propertyId}/amenities`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ amenities })
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to save amenities');
    }

    return response.json();
}

// Additional knowledge management functions
function expandKnowledgeItem(itemId) {
    // Find the item and show full content
    const items = window.currentKnowledgeItems || [];
    const item = items.find(i => i.id === itemId);
    if (!item) return;

    // Create modal for full content
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4';
    modal.innerHTML = `
        <div class="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[80vh] overflow-y-auto">
            <div class="bg-persian-green text-white p-4 rounded-t-lg">
                <div class="flex items-center justify-between">
                    <h3 class="text-lg font-semibold">Knowledge Item Details</h3>
                    <button onclick="this.closest('.fixed').remove()" class="text-white hover:text-gray-200">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
            <div class="p-6">
                <div class="space-y-4">
                    <div>
                        <span class="type-badge ${getTypeColorClass(item.type)}">
                            ${item.type || 'General'}
                        </span>
                    </div>
                    ${item.tags && item.tags.length > 0 ? `
                        <div>
                            <h4 class="font-medium text-gray-900 mb-2">Tags</h4>
                            <div class="flex flex-wrap gap-1">
                                ${(Array.isArray(item.tags) ? item.tags : item.tags.split(',')).map(tag => `
                                    <span class="bg-gray-100 text-gray-700 px-2 py-1 rounded text-sm">${tag.trim()}</span>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                    <div>
                        <h4 class="font-medium text-gray-900 mb-2">Content</h4>
                        <div class="text-gray-700 whitespace-pre-wrap">${item.content || 'No content'}</div>
                    </div>
                    <div class="text-sm text-gray-500">
                        Status: <span class="capitalize font-medium">${item.status || 'unknown'}</span>
                        ${item.created_at ? ` • Created: ${new Date(item.created_at).toLocaleDateString()}` : ''}
                    </div>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    document.body.style.overflow = 'hidden';

    // Do not close on outside click
}

function rejectKnowledgeItem(itemId, buttonElement) {
    if (!confirm('Reject this knowledge item? It will not be available to your guests.')) {
        return;
    }

    // Show loading state
    const button = buttonElement;
    const originalText = button ? button.innerHTML : '';
    if (button) {
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        button.disabled = true;
    }

    // Send rejection request
    fetch(`/api/knowledge-items/${itemId}/reject`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Refresh the knowledge content
            const property = window.currentProperty;
            if (property) {
                loadKnowledgeTabContent(property);
            }
        } else {
            alert('Error rejecting knowledge item: ' + (data.error || 'Unknown error'));
            // Restore button state
            if (button) {
                button.innerHTML = originalText;
                button.disabled = false;
            }
        }
    })
    .catch(error => {
        console.error('Error rejecting knowledge item:', error);
        alert('Error rejecting knowledge item: ' + error.message);
        // Restore button state
        if (button) {
            button.innerHTML = originalText;
            button.disabled = false;
        }
    });
}
function disapproveKnowledgeItem(itemId, buttonElement) {
    if (!confirm('Disapprove this knowledge item? It will be marked as pending and require re-approval.')) {
        return;
    }

    // Show loading state
    const button = buttonElement;
    const originalText = button ? button.innerHTML : '';
    if (button) {
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        button.disabled = true;
    }

    // Send disapproval request (change status to pending)
    fetch(`/api/knowledge-items/${itemId}/disapprove`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Refresh the knowledge content
            const property = window.currentProperty;
            if (property) {
                loadKnowledgeTabContent(property);
            }
        } else {
            alert('Error disapproving knowledge item: ' + (data.error || 'Unknown error'));
            // Restore button state
            if (button) {
                button.innerHTML = originalText;
                button.disabled = false;
            }
        }
    })
    .catch(error => {
        console.error('Error disapproving knowledge item:', error);
        alert('Error disapproving knowledge item: ' + error.message);
        // Restore button state
        if (button) {
            button.innerHTML = originalText;
            button.disabled = false;
        }
    });
}

function deleteKnowledgeItem(itemId, buttonElement) {
    if (!confirm('Delete this knowledge item permanently? This action cannot be undone.')) {
        return;
    }

    // Show loading state
    const button = buttonElement;
    const originalText = button ? button.innerHTML : '';
    if (button) {
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        button.disabled = true;
    }

    // Send delete request
    fetch(`/api/knowledge-items/${itemId}`, {
        method: 'DELETE',
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Refresh the knowledge content
            const property = window.currentProperty;
            if (property) {
                loadKnowledgeTabContent(property);
            }
        } else {
            alert('Error deleting knowledge item: ' + (data.error || 'Unknown error'));
            // Restore button state
            if (button) {
                button.innerHTML = originalText;
                button.disabled = false;
            }
        }
    })
    .catch(error => {
        console.error('Error deleting knowledge item:', error);
        alert('Error deleting knowledge item: ' + error.message);
        // Restore button state
        if (button) {
            button.innerHTML = originalText;
            button.disabled = false;
        }
    });
}


function getTypeColorClass(type) {
    const typeColors = {
        'QnA': 'type-qna',
        'Places': 'type-places',
        'Instructions': 'type-instructions',
        'Policies': 'type-policies',
        'Amenities': 'type-amenities',
        'General': 'type-general'
    };
    return typeColors[type] || 'type-general';
}

function deleteNewProperty(propertyId, propertyName) {
    // Simplified deletion for new properties (no reservations/conversations yet)
    if (!confirm(`Are you sure you want to delete "${propertyName}"?\n\nThis will permanently delete:\n• All property data\n• All knowledge items\n\nThis action cannot be undone.`)) {
        return;
    }

    // Show loading state on the delete button
    const deleteButton = document.querySelector(`button[onclick*="deleteNewProperty('${propertyId}'"]`);
    if (deleteButton) {
        deleteButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        deleteButton.disabled = true;
    }

    // Send delete request
    fetch(`/api/property/${propertyId}`, {
        method: 'DELETE',
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showSuccessMessage('Property deleted successfully.');
            // Refresh properties list
            loadProperties();
        } else {
            alert('Error deleting property: ' + (data.error || 'Unknown error'));
            // Restore button state
            if (deleteButton) {
                deleteButton.innerHTML = '<i class="fas fa-trash"></i>';
                deleteButton.disabled = false;
            }
        }
    })
    .catch(error => {
        console.error('Error deleting property:', error);
        alert('Error deleting property. Please try again.');
        // Restore button state
        if (deleteButton) {
            deleteButton.innerHTML = '<i class="fas fa-trash"></i>';
            deleteButton.disabled = false;
        }
    });
}

function deleteProperty(propertyId) {
    const property = window.currentProperty;
    if (!property) return;

    const propertyName = property.name || 'this property';

    if (!confirm(`Are you sure you want to delete "${propertyName}"?\n\nThis will permanently delete:\n• All property data\n• All knowledge items\n• All reservation history\n• All conversation history\n\nThis action cannot be undone.`)) {
        return;
    }

    // Second confirmation
    const confirmText = prompt(`To confirm deletion, please type the property name: "${propertyName}"`);
    if (confirmText !== propertyName) {
        alert('Property name does not match. Deletion cancelled.');
        return;
    }

    // Show loading state
    const deleteButton = document.querySelector(`button[onclick*="deleteProperty('${propertyId}')"]`);
    if (deleteButton) {
        deleteButton.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Deleting...';
        deleteButton.disabled = true;
    }

    // Send delete request
    fetch(`/api/property/${propertyId}`, {
        method: 'DELETE',
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Property deleted successfully.');
            // Close modal and refresh properties
            closeKnowledgeModal();
            loadProperties();
        } else {
            alert('Error deleting property: ' + (data.error || 'Unknown error'));
            // Restore button state
            if (deleteButton) {
                deleteButton.innerHTML = '<i class="fas fa-trash mr-2"></i>Delete Property';
                deleteButton.disabled = false;
            }
        }
    })
    .catch(error => {
        console.error('Error deleting property:', error);
        alert('Error deleting property: ' + error.message);
        // Restore button state
        if (deleteButton) {
            deleteButton.innerHTML = '<i class="fas fa-trash mr-2"></i>Delete Property';
            deleteButton.disabled = false;
        }
    });
}

function approveKnowledgeItem(itemId, buttonElement) {
    if (!confirm('Approve this knowledge item? It will be available to your guests.')) {
        return;
    }

    // Show loading state
    const button = buttonElement;
    const originalText = button ? button.innerHTML : '';
    if (button) {
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        button.disabled = true;
    }

    // Send approval request
    fetch(`/api/knowledge-items/${itemId}/approve`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Refresh the knowledge content
            const property = window.currentProperty;
            if (property) {
                loadKnowledgeTabContent(property);
            }
        } else {
            alert('Error approving knowledge item: ' + (data.error || 'Unknown error'));
            // Restore button state
            if (button) {
                button.innerHTML = originalText;
                button.disabled = false;
            }
        }
    })
    .catch(error => {
        console.error('Error approving knowledge item:', error);
        alert('Error approving knowledge item: ' + error.message);
        // Restore button state
        if (button) {
            button.innerHTML = originalText;
            button.disabled = false;
        }
    });
}

function editKnowledgeItem(itemId) {
    const items = window.currentKnowledgeItems || [];
    const item = items.find(i => i.id === itemId);
    if (!item) return;

    // Create editing modal with higher z-index
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-black bg-opacity-75 z-[60] flex items-center justify-center p-4';
    modal.innerHTML = `
        <div class="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[80vh] overflow-y-auto" onclick="event.stopPropagation()">
            <div class="bg-persian-green text-white p-4 rounded-t-lg">
                <div class="flex items-center justify-between">
                    <h3 class="text-lg font-semibold">Edit Knowledge Item</h3>
                    <button onclick="closeEditModal(this.closest('.fixed'))" class="text-white hover:text-gray-200">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
            <div class="p-6">
                <form id="edit-knowledge-form">
                    <div class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Type</label>
                            <select name="type" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green">
                                <option value="information" ${item.type === 'information' ? 'selected' : ''}>Information</option>
                                <option value="rule" ${item.type === 'rule' ? 'selected' : ''}>Rules</option>
                                <option value="instruction" ${item.type === 'instruction' ? 'selected' : ''}>Instructions</option>
                                <option value="amenity" ${item.type === 'amenity' ? 'selected' : ''}>Amenities</option>
                                <option value="places" ${item.type === 'places' ? 'selected' : ''}>Places</option>
                                <option value="basic_info" ${item.type === 'basic_info' ? 'selected' : ''}>Basic Info</option>
                                <option value="house_rule" ${item.type === 'house_rule' ? 'selected' : ''}>House Rules</option>
                                <option value="emergency" ${item.type === 'emergency' ? 'selected' : ''}>Emergency</option>
                                <option value="local_recommendation" ${item.type === 'local_recommendation' ? 'selected' : ''}>Local Recommendations</option>
                                <option value="property_fact" ${item.type === 'property_fact' ? 'selected' : ''}>Property Facts</option>
                                <option value="other" ${item.type === 'other' ? 'selected' : ''}>Other</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Tags (comma-separated)</label>
                            <input type="text" name="tags" value="${Array.isArray(item.tags) ? item.tags.join(', ') : (item.tags || '')}"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                   placeholder="tag1, tag2, tag3">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Content</label>
                            <textarea name="content" rows="6"
                                      class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                      placeholder="Enter the knowledge item content...">${item.content || ''}</textarea>
                        </div>
                    </div>
                    <div class="flex justify-end space-x-3 mt-6">
                        <button type="button" onclick="closeEditModal(this.closest('.fixed'))"
                                class="px-4 py-2 text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50">
                            Cancel
                        </button>
                        <button type="submit" class="px-4 py-2 bg-persian-green text-white rounded-lg hover:bg-green-600">
                            Save Changes
                        </button>
                    </div>
                </form>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Blur the parent modal and disable its close behavior
    const parentModal = document.getElementById('knowledge-modal');
    if (parentModal) {
        parentModal.style.filter = 'blur(2px)';
        parentModal.style.pointerEvents = 'none';
        // Add a flag to prevent parent modal from closing
        parentModal.setAttribute('data-edit-modal-open', 'true');
    }

    // Handle form submission
    const form = modal.querySelector('#edit-knowledge-form');
    form.addEventListener('submit', function(e) {
        e.preventDefault();

        const formData = new FormData(form);
        const updateData = {
            type: formData.get('type'),
            tags: formData.get('tags').split(',').map(tag => tag.trim()).filter(tag => tag),
            content: formData.get('content')
        };

        // Show loading state
        const submitBtn = form.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Saving...';
        submitBtn.disabled = true;

        // Send update request
        fetch(`/api/knowledge-items/${itemId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin',
            body: JSON.stringify(updateData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Close modal and refresh knowledge items
                closeEditModal(modal);

                // Refresh the knowledge content
                const property = window.currentProperty;
                if (property) {
                    loadKnowledgeTabContent(property);
                }
            } else {
                alert('Error updating knowledge item: ' + (data.error || 'Unknown error'));
                // Restore button state
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
            }
        })
        .catch(error => {
            console.error('Error updating knowledge item:', error);
            alert('Error updating knowledge item: ' + error.message);
            // Restore button state
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        });
    });

    // Do not close on outside click
}

function closeEditModal(modal) {
    // Restore parent modal
    const parentModal = document.getElementById('knowledge-modal');
    if (parentModal) {
        parentModal.style.filter = '';
        parentModal.style.pointerEvents = '';
        // Remove the flag that prevents parent modal from closing
        parentModal.removeAttribute('data-edit-modal-open');
    }

    // Remove edit modal
    modal.remove();

    // Prevent any event bubbling that might close the parent modal
    setTimeout(() => {
        if (parentModal && !parentModal.classList.contains('hidden')) {
            // Ensure parent modal stays open
            parentModal.style.display = 'flex';
        }
    }, 10);
}

function getCurrentModalPropertyId() {
    // Extract property ID from the modal context
    // This is a helper function to get the current property ID from the modal
    const propertyInfo = document.getElementById('knowledge-property-info');
    if (propertyInfo && propertyInfo.innerHTML) {
        // Try to extract property ID from the displayed property info
        // For now, we'll use a simple approach - store it in a data attribute
        return propertyInfo.dataset.propertyId;
    }
    return null;
}

function updateKnowledgeStats(knowledgeItems) {
    // Update the stats in the knowledge modal
    const approvedCount = document.getElementById('approved-count');
    const pendingCount = document.getElementById('pending-count');
    const totalCount = document.getElementById('total-count');

    if (approvedCount && pendingCount && totalCount) {
        const approved = knowledgeItems.filter(item => item.status === 'approved').length;
        const pending = knowledgeItems.filter(item => item.status !== 'approved').length;

        approvedCount.textContent = approved;
        pendingCount.textContent = pending;
        totalCount.textContent = approved + pending;
    }
}

function updatePropertyStatusBadge(propertyId, isActive) {
    // Find the property card and update the status badge
    const propertyCard = document.querySelector(`input[onchange*="${propertyId}"]`).closest('.property-card');
    const statusBadge = propertyCard.querySelector('.status-badge-active, .status-badge-inactive');
    
    if (statusBadge) {
        statusBadge.className = `px-3 py-1 rounded-full text-sm font-medium ${isActive ? 'status-badge-active' : 'status-badge-inactive'}`;
        statusBadge.textContent = isActive ? 'Active' : 'Inactive';
    }
}
// --- Property Magic Link Functions ---

async function copyPropertyMagicLink(propertyId, buttonElement) {
    try {
        // Get button element - either passed as parameter or from event
        const button = buttonElement || event.target.closest('button');

        // Find the property to check its status
        const property = window.currentProperty || properties.find(p => p.id === propertyId);
        if (!property) {
            showErrorMessage('Property not found');
            return;
        }

        // Check if property is active
        const isActive = (property.status || 'active') === 'active';
        if (!isActive) {
            // Show warning about inactive property
            if (confirm('This property is currently inactive. The magic link will not work for guests until you activate the property.\n\nDo you still want to copy the link?')) {
                // User confirmed, proceed with copying
            } else {
                return; // User cancelled
            }
        }

        // Show loading state
        const originalContent = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>Loading...';
        button.disabled = true;

        // Get the magic link
        const response = await fetch(`/api/properties/${propertyId}/magic-link`, {
            method: 'GET',
            credentials: 'same-origin'
        });

        const result = await response.json();

        if (result.success) {
            // Copy to clipboard with fallback
            const copySuccess = await copyToClipboardWithFallback(result.magicLinkUrl);

            if (copySuccess) {
                // Show success feedback
                button.innerHTML = '<i class="fas fa-check mr-1"></i>Copied!';
                button.classList.remove('bg-persian-green', 'hover:bg-green-600');
                button.classList.add('bg-green-500');

                // Reset button after 2 seconds
                setTimeout(() => {
                    button.innerHTML = originalContent;
                    button.classList.remove('bg-green-500');
                    button.classList.add('bg-persian-green', 'hover:bg-green-600');
                    button.disabled = false;
                }, 2000);

                showSuccessMessage('Magic link copied to clipboard!');
            } else {
                // Fallback: Show modal with selectable text
                showMagicLinkModal(result.magicLinkUrl);

                // Reset button
                button.innerHTML = originalContent;
                button.disabled = false;
            }
        } else {
            throw new Error(result.error || 'Failed to get magic link');
        }
    } catch (error) {
        console.error('Error copying magic link:', error);
        showErrorMessage('Failed to copy magic link: ' + error.message);

        // Reset button if available
        const button = buttonElement || (typeof event !== 'undefined' ? event.target.closest('button') : null);
        if (button) {
            button.innerHTML = '<i class="fas fa-copy mr-1"></i>Copy Link';
            button.disabled = false;
        }
    }
}

// Robust clipboard copying with fallbacks
async function copyToClipboardWithFallback(text) {
    // First, try the modern Clipboard API
    if (navigator.clipboard && window.isSecureContext) {
        try {
            await navigator.clipboard.writeText(text);
            console.log('Copied using modern Clipboard API');
            return true;
        } catch (err) {
            console.warn('Modern Clipboard API failed:', err);
        }
    }

    // Fallback 1: Try the older execCommand method
    try {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        textArea.style.top = '-999999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        const successful = document.execCommand('copy');
        document.body.removeChild(textArea);
        
        if (successful) {
            console.log('Copied using execCommand fallback');
            return true;
        }
    } catch (err) {
        console.warn('execCommand fallback failed:', err);
    }

    // If all clipboard methods fail, return false
    console.warn('All clipboard methods failed');
    return false;
}

// Show modal with selectable text as final fallback
function showMagicLinkModal(magicLinkUrl) {
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50';
    modal.id = 'magic-link-modal';
    
    const modalContent = document.createElement('div');
    modalContent.className = 'relative top-20 mx-auto p-5 border w-96 shadow-lg rounded-md bg-white';
    
    modalContent.innerHTML = `
        <div class="mt-3">
            <div class="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-blue-100">
                <i class="fas fa-link text-blue-600 text-xl"></i>
            </div>
            <div class="mt-3 text-center">
                <h3 class="text-lg leading-6 font-medium text-gray-900">Magic Link Ready</h3>
                <div class="mt-4">
                    <p class="text-sm text-gray-500 mb-3">
                        Please select and copy the link below:
                    </p>
                    <textarea 
                        class="w-full p-2 border border-gray-300 rounded-md text-sm"
                        rows="3"
                        readonly
                        id="magic-link-text"
                    >${magicLinkUrl}</textarea>
                    <div class="mt-3 flex justify-center space-x-2">
                        <button 
                            id="copy-button"
                            class="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 text-sm"
                        >
                            <i class="fas fa-copy"></i> Copy
                        </button>
                        <button 
                            id="close-button"
                            class="px-4 py-2 bg-gray-500 text-white rounded-md hover:bg-gray-600 text-sm"
                        >
                            Close
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    modal.appendChild(modalContent);
    document.body.appendChild(modal);
    
    // Auto-select the text
    const textArea = document.getElementById('magic-link-text');
    setTimeout(() => {
        textArea.select();
        textArea.focus();
    }, 100);
    
    // Add event listeners
    const copyButton = document.getElementById('copy-button');
    const closeButton = document.getElementById('close-button');
    
    copyButton.addEventListener('click', () => {
        textArea.select();
        try {
            const successful = document.execCommand('copy');
            if (successful) {
                copyButton.innerHTML = '<i class="fas fa-check"></i> Copied!';
                copyButton.classList.remove('bg-blue-500', 'hover:bg-blue-600');
                copyButton.classList.add('bg-green-500');
                
                setTimeout(() => {
                    copyButton.innerHTML = '<i class="fas fa-copy"></i> Copy';
                    copyButton.classList.remove('bg-green-500');
                    copyButton.classList.add('bg-blue-500', 'hover:bg-blue-600');
                }, 2000);
            } else {
                alert('Please use Ctrl+C (or Cmd+C on Mac) to copy the selected text.');
            }
        } catch (err) {
            alert('Please use Ctrl+C (or Cmd+C on Mac) to copy the selected text.');
        }
    });
    
    closeButton.addEventListener('click', () => {
        document.body.removeChild(modal);
    });
    
    // Close modal when clicking outside
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            document.body.removeChild(modal);
        }
    });
    
    // Close modal with Escape key
    const handleEscape = (e) => {
        if (e.key === 'Escape') {
            document.body.removeChild(modal);
            document.removeEventListener('keydown', handleEscape);
        }
    };
    document.addEventListener('keydown', handleEscape);
}

function copyToClipboard(text) {
    copyToClipboardWithFallback(text).then(success => {
        if (success) {
            console.log('Copied to clipboard:', text);
        } else {
            console.error('Failed to copy to clipboard');
        }
    });
}

// --- Calendar Screen Functions ---
let filteredReservations = [];

function loadCalendarData() {
    console.log('Loading calendar data');
    
    // Show loading state
    showCalendarState('loading');
    
    // First get all properties for the host
    fetch('/api/user-properties', {
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        const propertiesData = data.success ? data.properties : [];
        console.log('Fetched properties for calendar:', propertiesData);
        
        if (!propertiesData || propertiesData.length === 0) {
            reservations = [];
            filteredReservations = [];
            showCalendarState('empty');
            return Promise.resolve([]);
        }

        // Filter to only active properties
        const activeProperties = propertiesData.filter(property => {
            const status = property.status || 'active';
            return status === 'active';
        });

        console.log(`Found ${activeProperties.length} active properties out of ${propertiesData.length} total properties`);

        if (activeProperties.length === 0) {
            reservations = [];
            filteredReservations = [];
            showCalendarState('empty');
            return Promise.resolve([]);
        }

        // Get reservations for active properties only
        const reservationPromises = activeProperties.map(property => {
            return fetch(`/api/property/${property.id}/reservations`, {
                credentials: 'same-origin'
            })
            .then(response => response.json())
            .then(data => {
                console.log(`Reservation data for property ${property.id}:`, data);
                if (data.success && data.reservations) {
                    // Add property info to each reservation
                    const enrichedReservations = data.reservations.map(reservation => ({
                        ...reservation,
                        property_id: property.id,
                        property_name: property.name || 'Unknown Property'
                    }));
                    console.log(`Enriched reservations for property ${property.id}:`, enrichedReservations);
                    return enrichedReservations;
                } else {
                    console.warn(`No reservations found for property ${property.id}:`, data);
                    return [];
                }
            })
            .catch(error => {
                console.error(`Error fetching reservations for property ${property.id}:`, error);
                return [];
            });
        });
        
        // Wait for all reservation requests to complete
        return Promise.all(reservationPromises);
    })
    .then(allReservations => {
        // Flatten the array of arrays
        const flattenedReservations = allReservations.flat();
        
        reservations = flattenedReservations;
        filteredReservations = reservations;
        
        console.log('Loaded reservations for calendar:', reservations);
        
        // Populate property filter
        populatePropertyFilter();
        
        // Show appropriate view
        if (reservations.length === 0) {
            showCalendarState('empty');
        } else {
            showCalendarState('content');
            renderCalendarView();
        }
    })
    .catch(error => {
        console.error('Error loading calendar data:', error);
        showCalendarState('error');
    });
}

function showCalendarState(state) {
    const loadingEl = document.getElementById('calendar-loading');
    const errorEl = document.getElementById('calendar-error');
    const emptyEl = document.getElementById('calendar-empty');
    const listViewEl = document.getElementById('calendar-list-view');
    const timelineViewEl = document.getElementById('calendar-timeline-view');
    
    // Hide all states
    [loadingEl, errorEl, emptyEl, listViewEl, timelineViewEl].forEach(el => {
        if (el) el.classList.add('hidden');
    });
    
    // Show appropriate state
    switch (state) {
        case 'loading':
            if (loadingEl) loadingEl.classList.remove('hidden');
            break;
        case 'error':
            if (errorEl) errorEl.classList.remove('hidden');
            break;
        case 'empty':
            if (emptyEl) emptyEl.classList.remove('hidden');
            break;
        case 'content':
            if (calendarView === 'list') {
                if (listViewEl) listViewEl.classList.remove('hidden');
            } else {
                if (timelineViewEl) timelineViewEl.classList.remove('hidden');
            }
            break;
    }
}

function populatePropertyFilter() {
    const filterSelect = document.getElementById('property-filter');
    if (!filterSelect) return;
    
    // Clear existing options except "All Properties"
    const firstOption = filterSelect.firstElementChild;
    filterSelect.innerHTML = '';
    filterSelect.appendChild(firstOption);
    
    // Get unique properties from reservations
    const uniqueProperties = new Map();
    reservations.forEach(reservation => {
        const propertyId = reservation.property_id;
        const propertyName = reservation.property_name || 'Unknown Property';
        if (propertyId && !uniqueProperties.has(propertyId)) {
            uniqueProperties.set(propertyId, propertyName);
        }
    });
    
    // Add property options
    uniqueProperties.forEach((name, id) => {
        const option = document.createElement('option');
        option.value = id;
        option.textContent = name;
        filterSelect.appendChild(option);
    });
}

function filterCalendarByProperty() {
    const filterSelect = document.getElementById('property-filter');
    const selectedPropertyId = filterSelect.value;
    
    if (selectedPropertyId === '') {
        filteredReservations = reservations;
    } else {
        filteredReservations = reservations.filter(reservation => 
            reservation.property_id === selectedPropertyId
        );
    }
    
    if (filteredReservations.length === 0) {
        showCalendarState('empty');
    } else {
        showCalendarState('content');
        renderCalendarView();
    }
}

function toggleCalendarView() {
    const button = document.getElementById('calendar-view-toggle');
    if (calendarView === 'list') {
        calendarView = 'timeline';
        button.innerHTML = '<i class="fas fa-list sm:mr-2"></i><span class="hidden sm:inline">List View</span>';
    } else {
        calendarView = 'list';
        button.innerHTML = '<i class="fas fa-calendar-alt sm:mr-2"></i><span class="hidden sm:inline">Calendar View</span>';
    }

    // Update view
    if (filteredReservations.length > 0) {
        showCalendarState('content');
        renderCalendarView();
    }
}

// --- Guest Name Display Functions ---

function getDisplayGuestName(reservation) {
    /**
     * Get the display name for a guest, showing "Guest" with last 4 digits
     * of phone number instead of "Unknown Guest"
     */

    // First check if we have a real guest name (not empty, not "Guest", not "Unknown Guest")
    const guestName = reservation.guestName || reservation.guest_name || '';

    if (guestName &&
        guestName.trim() !== '' &&
        guestName.trim() !== 'Guest' &&
        guestName.trim() !== 'Unknown Guest') {
        return guestName.trim();
    }

    // No real guest name, so create one with phone digits
    const phoneDigits = getPhoneDigitsFromReservation(reservation);

    if (phoneDigits) {
        return `Guest ${phoneDigits}`;
    }

    // Final fallback
    return 'Guest';
}

function getPhoneDigitsFromReservation(reservation) {
    /**
     * Extract the last 4 digits of phone number from reservation data
     */

    // Check guestPhoneLast4 field first (from iCal)
    const phoneLast4 = reservation.guestPhoneLast4;
    if (phoneLast4 && phoneLast4.length === 4 && /^\d{4}$/.test(phoneLast4)) {
        return phoneLast4;
    }

    // Check full phone number fields
    const phoneFields = [
        'guestPhoneNumber',
        'GuestPhoneNumber',
        'guest_phone_number',
        'guest_phone'
    ];

    for (const field of phoneFields) {
        const phoneNumber = reservation[field];
        if (phoneNumber && typeof phoneNumber === 'string') {
            // Extract digits only
            const digits = phoneNumber.replace(/\D/g, '');
            if (digits.length >= 4) {
                return digits.slice(-4);
            }
        }
    }

    return null;
}

function renderCalendarView() {
    if (calendarView === 'list') {
        renderListView();
    } else {
        renderTimelineView();
    }
}
function renderListView() {
    const listContainer = document.getElementById('reservations-list');
    if (!listContainer) return;
    
    listContainer.innerHTML = '';
    
    // Sort reservations by start date
    const sortedReservations = [...filteredReservations].sort((a, b) => 
        new Date(a.startDate || a.check_in_date) - new Date(b.startDate || b.check_in_date)
    );
    
    sortedReservations.forEach(reservation => {
        const reservationCard = createReservationCard(reservation);
        listContainer.appendChild(reservationCard);
        

    });
}

function renderTimelineView() {
    const timelineEl = document.getElementById('calendar-timeline-view');
    if (!timelineEl) return;

    // Clear existing content
    timelineEl.innerHTML = '';

    // Create calendar container
    const calendarContainer = document.createElement('div');
    calendarContainer.className = 'bg-white rounded-lg shadow-md p-6';

    // Create calendar header with navigation
    const calendarHeader = createCalendarHeader();
    calendarContainer.appendChild(calendarHeader);

    // Create calendar grid
    const calendarGrid = createCalendarGrid();
    calendarContainer.appendChild(calendarGrid);

    timelineEl.appendChild(calendarContainer);

    // Show timeline view
    timelineEl.classList.remove('hidden');
}

function createCalendarHeader() {
    const header = document.createElement('div');
    header.className = 'flex items-center justify-between mb-6';

    // Get current date for navigation
    const currentDate = window.calendarCurrentDate || new Date();
    const monthNames = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ];

    header.innerHTML = `
        <div class="flex items-center space-x-4">
            <button onclick="navigateCalendar(-1)" class="p-2 hover:bg-gray-100 rounded-lg transition-colors">
                <i class="fas fa-chevron-left text-gray-600"></i>
            </button>
            <h3 class="text-xl font-semibold text-dark-purple">
                ${monthNames[currentDate.getMonth()]} ${currentDate.getFullYear()}
            </h3>
            <button onclick="navigateCalendar(1)" class="p-2 hover:bg-gray-100 rounded-lg transition-colors">
                <i class="fas fa-chevron-right text-gray-600"></i>
            </button>
        </div>
        <div class="flex items-center space-x-2">
            <button onclick="goToToday()" class="bg-persian-green hover:bg-green-600 text-white px-3 py-1 rounded text-sm transition-colors">
                Today
            </button>
        </div>
    `;

    return header;
}

function createCalendarGrid() {
    const grid = document.createElement('div');
    grid.className = 'calendar-grid';
    grid.id = 'calendar-grid';

    // Get current date for calendar generation
    const currentDate = window.calendarCurrentDate || new Date();
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();

    // Create calendar structure
    const calendarHTML = generateCalendarHTML(year, month);
    grid.innerHTML = calendarHTML;

    // Add reservations to calendar after DOM is ready
    setTimeout(() => {
        addReservationsToCalendar(year, month);
    }, 0);

    return grid;
}

function generateCalendarHTML(year, month) {
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startDate = new Date(firstDay);
    startDate.setDate(startDate.getDate() - firstDay.getDay()); // Start from Sunday

    const endDate = new Date(lastDay);
    endDate.setDate(endDate.getDate() + (6 - lastDay.getDay())); // End on Saturday

    let html = `
        <div class="calendar-header grid grid-cols-7 gap-1 mb-2">
            <div class="text-center font-medium text-gray-600 py-2">Sun</div>
            <div class="text-center font-medium text-gray-600 py-2">Mon</div>
            <div class="text-center font-medium text-gray-600 py-2">Tue</div>
            <div class="text-center font-medium text-gray-600 py-2">Wed</div>
            <div class="text-center font-medium text-gray-600 py-2">Thu</div>
            <div class="text-center font-medium text-gray-600 py-2">Fri</div>
            <div class="text-center font-medium text-gray-600 py-2">Sat</div>
        </div>
        <div class="calendar-body grid grid-cols-7 gap-1">
    `;

    const currentDate = new Date(startDate);
    while (currentDate <= endDate) {
        const isCurrentMonth = currentDate.getMonth() === month;
        const isToday = isDateToday(currentDate);
        const dateStr = formatDateForCalendar(currentDate);

        const dayClass = `
            calendar-day min-h-[120px] border border-gray-200 p-1 relative
            ${isCurrentMonth ? 'bg-white' : 'bg-gray-50'}
            ${isToday ? 'ring-2 ring-persian-green' : ''}
        `;

        html += `
            <div class="${dayClass}" data-date="${dateStr}">
                <div class="text-sm font-medium text-gray-700 mb-1">
                    ${currentDate.getDate()}
                </div>
                <div class="reservations-container space-y-1" id="reservations-${dateStr}">
                    <!-- Reservations will be added here -->
                </div>
            </div>
        `;

        currentDate.setDate(currentDate.getDate() + 1);
    }

    html += '</div>';
    return html;
}

function addReservationsToCalendar(year, month) {
    // Clear existing reservations
    document.querySelectorAll('.reservation-bar').forEach(el => el.remove());

    // Filter reservations for the current month view (including adjacent days)
    const monthStart = new Date(year, month, 1);
    const monthEnd = new Date(year, month + 1, 0);

    // Extend range to include partial weeks
    const viewStart = new Date(monthStart);
    viewStart.setDate(viewStart.getDate() - monthStart.getDay());
    const viewEnd = new Date(monthEnd);
    viewEnd.setDate(viewEnd.getDate() + (6 - monthEnd.getDay()));

    const visibleReservations = filteredReservations.filter(reservation => {
        const startDate = parseDateOnly(reservation.startDate || reservation.check_in_date);
        const endDate = parseDateOnly(reservation.endDate || reservation.check_out_date);

        // Treat check-out as exclusive when rendering bars
        const displayEnd = new Date(endDate);
        displayEnd.setDate(displayEnd.getDate() - 1);

        // Show reservation if it overlaps with the visible calendar period
        return startDate <= viewEnd && displayEnd >= viewStart;
    });

    // Add each reservation to the calendar
    visibleReservations.forEach(reservation => {
        addReservationToCalendar(reservation);
    });
}

function addReservationToCalendar(reservation) {
    const startDate = parseDateOnly(reservation.startDate || reservation.check_in_date);
    const endDate = parseDateOnly(reservation.endDate || reservation.check_out_date);

    // Treat check-out as exclusive; last rendered day is the day before check-out
    const displayEnd = new Date(endDate);
    displayEnd.setDate(displayEnd.getDate() - 1);

    // Calculate the span of the reservation
    const currentDate = new Date(startDate);

    while (currentDate <= displayEnd) {
        const dateStr = formatDateForCalendar(currentDate);
        const dayElement = document.getElementById(`reservations-${dateStr}`);

        if (dayElement) {
            // Create a reservation bar for each day
            const reservationBar = createReservationBarForDay(reservation, currentDate, startDate, displayEnd);
            dayElement.appendChild(reservationBar);
        }

        currentDate.setDate(currentDate.getDate() + 1);
    }
}

function createReservationBarForDay(reservation, currentDay, startDate, endDate) {
    const bar = document.createElement('div');
    const guestName = getDisplayGuestName(reservation);
    const propertyName = reservation.property_name || 'Property';
    const platform = detectPlatform(reservation);
    const platformIcon = getPlatformIcon(platform);
    const platformColor = getPlatformColor(platform);

    // Determine if this is the first, middle, or last day of the reservation (compare by date-only key)
    const isFirstDay = formatDateForCalendar(currentDay) === formatDateForCalendar(startDate);
    const isLastDay = formatDateForCalendar(currentDay) === formatDateForCalendar(endDate);
    const isSingleDay = isFirstDay && isLastDay;

    // Set appropriate styling based on position in reservation
    let roundedClass = 'rounded';
    if (!isSingleDay) {
        if (isFirstDay) {
            roundedClass = 'rounded-l';
        } else if (isLastDay) {
            roundedClass = 'rounded-r';
        } else {
            roundedClass = ''; // No rounding for middle days
        }
    }

    const barClass = `
        reservation-bar text-xs text-white p-1 cursor-pointer relative
        transition-colors duration-200 hover:brightness-110
        ${roundedClass}
    `;

    bar.className = barClass;
    bar.style.backgroundColor = platformColor;

    // Show content only on first day or single day reservations
    if (isFirstDay || isSingleDay) {
        bar.innerHTML = `
            <div class="flex items-center space-x-1">
                ${platformIcon}
                <span class="font-medium truncate">${guestName}</span>
            </div>
            <div class="text-xs opacity-90 truncate">
                ${formatDateRange(reservation.startDate || reservation.check_in_date, reservation.endDate || reservation.check_out_date)}
            </div>
        `;
    } else {
        // For continuation days, just show a colored bar
        bar.innerHTML = `<div class="h-full"></div>`;
        bar.style.minHeight = '20px';
    }

    // Add click handler for reservation details
    bar.addEventListener('click', (e) => {
        e.stopPropagation();
        showReservationDetails(reservation);
    });

    // Create tooltip content
    const tooltipContent = createTooltipContent(reservation, guestName, propertyName);

    // Add tooltip functionality
    addTooltip(bar, tooltipContent);

    return bar;
}

function createTooltipContent(reservation, guestName, propertyName) {
    const startDate = parseDateOnly(reservation.startDate || reservation.check_in_date);
    const endDate = parseDateOnly(reservation.endDate || reservation.check_out_date);
    const platform = detectPlatform(reservation);
    const phoneNumber = reservation.guestPhoneNumber || reservation.guest_phone_number || 'Not provided';
    const summary = reservation.summary || reservation.Summary || '';

    // Calculate number of nights (end exclusive)
    const timeDiff = endDate.getTime() - startDate.getTime();
    const nights = Math.round(timeDiff / (1000 * 3600 * 24));

    return `
        <div class="text-sm">
            <div class="font-semibold text-dark-purple mb-2">${guestName}</div>
            <div class="space-y-1 text-gray-700">
                <div><strong>Property:</strong> ${propertyName}</div>
                <div><strong>Platform:</strong> ${platform.charAt(0).toUpperCase() + platform.slice(1)}</div>
                <div><strong>Check-in:</strong> ${startDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}</div>
                <div><strong>Check-out:</strong> ${endDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}</div>
                <div><strong>Nights:</strong> ${nights}</div>
                ${phoneNumber !== 'Not provided' ? `<div><strong>Phone:</strong> ${phoneNumber}</div>` : ''}
                ${summary ? `<div><strong>Notes:</strong> ${summary}</div>` : ''}
            </div>
        </div>
    `;
}

function addTooltip(element, content) {
    let tooltip = null;

    element.addEventListener('mouseenter', (e) => {
        // Disable tooltips on small screens (under 480px width)
        if (window.innerWidth < 480) {
            return;
        }

        // Remove any existing tooltip
        removeTooltip();

        // Create tooltip
        tooltip = document.createElement('div');
        tooltip.className = 'reservation-tooltip absolute z-50 bg-white border border-gray-300 rounded-lg shadow-lg p-3 max-w-xs';
        tooltip.innerHTML = content;

        // Add to body
        document.body.appendChild(tooltip);

        // Position tooltip
        positionTooltip(tooltip, e);

        // Store reference for cleanup
        element._tooltip = tooltip;
    });

    element.addEventListener('mouseleave', () => {
        removeTooltip();
    });

    element.addEventListener('mousemove', (e) => {
        // Only move tooltip if screen is wide enough and tooltip exists
        if (tooltip && window.innerWidth >= 480) {
            positionTooltip(tooltip, e);
        }
    });
}

function positionTooltip(tooltip, event) {
    const rect = tooltip.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let left = event.pageX + 10;
    let top = event.pageY + 10;

    // Adjust if tooltip would go off screen
    if (left + rect.width > viewportWidth) {
        left = event.pageX - rect.width - 10;
    }

    if (top + rect.height > viewportHeight) {
        top = event.pageY - rect.height - 10;
    }

    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
}

function removeTooltip() {
    const existingTooltips = document.querySelectorAll('.reservation-tooltip');
    existingTooltips.forEach(tooltip => tooltip.remove());
}

// Handle window resize for responsive tooltip behavior
window.addEventListener('resize', () => {
    // Remove any existing tooltips when screen size changes to small
    if (window.innerWidth < 480) {
        removeTooltip();
    }
});

// Calendar utility functions
function detectPlatform(reservation) {
    const summary = (reservation.summary || reservation.Summary || '').toLowerCase();
    const description = (reservation.description || reservation.Description || '').toLowerCase();

    if (summary.includes('airbnb') || description.includes('airbnb')) {
        return 'airbnb';
    } else if (summary.includes('booking') || description.includes('booking.com')) {
        return 'booking';
    } else if (summary.includes('vrbo') || description.includes('vrbo')) {
        return 'vrbo';
    } else if (summary.includes('expedia') || description.includes('expedia')) {
        return 'expedia';
    }
    return 'direct';
}

function getPlatformIcon(platform) {
    const icons = {
        'airbnb': '<i class="fab fa-airbnb"></i>',
        'booking': '<span class="font-bold text-xs">B.</span>',
        'vrbo': '<span class="font-bold text-xs">V</span>',
        'expedia': '<span class="font-bold text-xs">E</span>',
        'direct': '<i class="fas fa-user"></i>'
    };
    return icons[platform] || icons['direct'];
}

function getPlatformColor(platform) {
    const colors = {
        'airbnb': '#FF5A5F',
        'booking': '#003580',
        'vrbo': '#0066CC',
        'expedia': '#FFC72C',
        'direct': '#2a9d8f'
    };
    return colors[platform] || colors['direct'];
}

function formatDateForCalendar(date) {
    // Always format as local date-only string to avoid timezone shifts
    const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function isDateToday(date) {
    const today = new Date();
    return date.toDateString() === today.toDateString();
}

// Parse any date-like input into a local date at midnight (date-only)
function parseDateOnly(input) {
    if (!input) return new Date(NaN);
    if (input instanceof Date) {
        return new Date(input.getFullYear(), input.getMonth(), input.getDate());
    }
    // Expect strings like YYYY-MM-DD or ISO strings; take date part only
    const str = String(input);
    const datePart = str.includes('T') ? str.split('T')[0] : str;
    const [y, m, d] = datePart.split('-').map(Number);
    return new Date(y, (m || 1) - 1, d || 1);
}

function formatDateRange(startDate, endDate) {
    const start = parseDateOnly(startDate);
    const end = parseDateOnly(endDate);
    const startStr = start.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const endStr = end.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    return `${startStr} - ${endStr}`;
}

// Calendar navigation functions
function navigateCalendar(direction) {
    const currentDate = window.calendarCurrentDate || new Date();
    currentDate.setMonth(currentDate.getMonth() + direction);
    window.calendarCurrentDate = currentDate;

    // Re-render the calendar
    if (calendarView === 'timeline') {
        renderTimelineView();
    }
}

function goToToday() {
    window.calendarCurrentDate = new Date();

    // Re-render the calendar
    if (calendarView === 'timeline') {
        renderTimelineView();
    }
}

// Reservation details modal
function showReservationDetails(reservation) {
    const modal = document.getElementById('reservation-details-modal');
    const content = document.getElementById('reservation-details-content');

    if (!modal || !content) return;

    // Generate modal content
    content.innerHTML = createReservationDetailsContent(reservation);

    // Show modal
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';


}

function closeReservationDetailsModal() {
    const modal = document.getElementById('reservation-details-modal');
    if (modal) {
        modal.classList.add('hidden');
        document.body.style.overflow = 'auto';
    }
}
function createReservationDetailsContent(reservation) {
    const guestName = getDisplayGuestName(reservation);
    const propertyName = reservation.property_name || 'Property';
    const startDate = parseDateOnly(reservation.startDate || reservation.check_in_date);
    const endDate = parseDateOnly(reservation.endDate || reservation.check_out_date);
    const platform = detectPlatform(reservation);
    const platformIcon = getPlatformIcon(platform);
    const platformColor = getPlatformColor(platform);
    const phoneNumber = reservation.guestPhoneNumber || reservation.guest_phone_number || '';
    const summary = reservation.summary || reservation.Summary || '';
    const description = reservation.description || reservation.Description || '';

    // Calculate number of nights (end exclusive)
    const timeDiff = endDate.getTime() - startDate.getTime();
    const nights = Math.round(timeDiff / (1000 * 3600 * 24));

    return `
        <div class="grid grid-cols-1 gap-6">
            <!-- Single Column Layout: All Info -->
            <div class="space-y-6">
                <!-- Guest Information -->
                <div class="bg-gray-50 rounded-lg p-4">
                    <h4 class="text-lg font-semibold text-dark-purple mb-4">
                        <i class="fas fa-user mr-2"></i>Guest Information
                    </h4>
                    <div class="space-y-3">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Guest Name</label>
                            <input type="text" value="${guestName}"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                   id="modal-guest-name">
                        </div>
                        <!-- Phone Number field - commented out as requested
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Phone Number</label>
                            <input type="tel" value="${phoneNumber}"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                   id="modal-guest-phone" placeholder="(555) 123-4567">
                        </div>
                        -->
                    </div>
                </div>

                <!-- Reservation Details -->
                <div class="bg-gray-50 rounded-lg p-4">
                    <h4 class="text-lg font-semibold text-dark-purple mb-4">
                        <i class="fas fa-calendar-alt mr-2"></i>Reservation Details
                    </h4>
                    <div class="space-y-3">
                        <div class="flex items-center space-x-2">
                            <div style="background-color: ${platformColor};" class="text-white px-2 py-1 rounded text-sm flex items-center space-x-1">
                                ${platformIcon}
                                <span>${platform.charAt(0).toUpperCase() + platform.slice(1)}</span>
                            </div>
                        </div>
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Check-in Date</label>
                                <input type="date" value="${formatDateForCalendar(startDate)}"
                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                       id="modal-checkin-date">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Check-out Date</label>
                                <input type="date" value="${formatDateForCalendar(endDate)}"
                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                       id="modal-checkout-date">
                            </div>
                        </div>
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Check-in Time</label>
                                <input type="time" value="15:00"
                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                       id="modal-checkin-time">
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Check-out Time</label>
                                <input type="time" value="11:00"
                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                       id="modal-checkout-time">
                            </div>
                        </div>
                        <div>
                            <span class="text-sm text-gray-600">Duration: ${nights} night${nights !== 1 ? 's' : ''}</span>
                        </div>
                    </div>
                </div>

                <!-- Notes -->
                <div class="bg-gray-50 rounded-lg p-4">
                    <h4 class="text-lg font-semibold text-dark-purple mb-4">
                        <i class="fas fa-sticky-note mr-2"></i>Notes
                    </h4>
                    <div class="space-y-3">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Reservation Summary</label>
                            <textarea rows="2"
                                      class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                      id="modal-summary">${summary}</textarea>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Host Notes</label>
                            <textarea rows="3" placeholder="Add private notes about this reservation..."
                                      class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                      id="modal-host-notes"></textarea>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Right column removed - no meaningful content after commenting out contacts and email sections -->
        </div>

        <!-- Action Buttons -->
        <div class="flex justify-end space-x-4 mt-6 pt-6 border-t border-gray-200">
            <button onclick="closeReservationDetailsModal()"
                    class="px-6 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                Cancel
            </button>
            <button onclick="saveReservationDetails('${reservation.id || reservation.reservationId}')"
                    class="px-6 py-2 bg-persian-green hover:bg-green-600 text-white rounded-lg font-medium transition-colors">
                <i class="fas fa-save mr-2"></i>Save Changes
            </button>
        </div>
    `;
}

// Modal contact functions - commented out as requested, stub functions provided for compatibility
function renderAdditionalContactsForModal(reservation) {
    // Stub function - returns empty string since Additional Contacts section is commented out
    return '';
}

function addContactFieldToModal() {
    // Stub function - no-op since Additional Contacts section is commented out
    return;
}

function removeContactFromModal(button) {
    // Stub function - no-op since Additional Contacts section is commented out
    return;
}

/*
// Original functions commented out:
function renderAdditionalContactsForModal(reservation) {
    const contacts = reservation.additional_contacts || reservation.AdditionalContacts || [];

    if (contacts.length === 0) {
        return '<p class="text-sm text-gray-500">No additional contacts</p>';
    }

    return contacts.map((contact, index) => `
        <div class="flex items-center gap-2 contact-entry">
            <input type="text" class="flex-1 px-2 py-1 border border-gray-300 rounded text-sm contact-name"
                   placeholder="Name" value="${contact.name || ''}">
            <input type="tel" class="flex-1 px-2 py-1 border border-gray-300 rounded text-sm contact-phone"
                   placeholder="(555) 123-4567" value="${contact.phone || ''}">
            <button onclick="removeContactFromModal(this)" class="text-red-500 hover:text-red-700">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `).join('');
}

function addContactFieldToModal() {
    const container = document.getElementById('modal-additional-contacts');
    if (!container) return;

    const entryDiv = document.createElement('div');
    entryDiv.className = 'flex items-center gap-2 contact-entry';

    entryDiv.innerHTML = `
        <input type="text" class="flex-1 px-2 py-1 border border-gray-300 rounded text-sm contact-name"
               placeholder="Name">
        <input type="tel" class="flex-1 px-2 py-1 border border-gray-300 rounded text-sm contact-phone"
               placeholder="(555) 123-4567">
        <button onclick="removeContactFromModal(this)" class="text-red-500 hover:text-red-700">
            <i class="fas fa-times"></i>
        </button>
    `;

    container.appendChild(entryDiv);
}

function removeContactFromModal(button) {
    const entryDiv = button.parentElement;
    entryDiv.remove();
}
*/





function saveReservationDetails(reservationId) {
    console.log('Saving reservation details for:', reservationId);

    // Find the reservation to get property ID
    const reservation = reservations.find(r => (r.id || r.reservationId) === reservationId);
    if (!reservation) {
        console.error('Reservation not found:', reservationId);
        showReservationMessage('Reservation not found', 'error');
        return;
    }

    const propertyId = reservation.property_id;

    // Get form values
    const guestName = document.getElementById('modal-guest-name')?.value;
    const guestPhone = document.getElementById('modal-guest-phone')?.value;
    const checkinDate = document.getElementById('modal-checkin-date')?.value;
    const checkoutDate = document.getElementById('modal-checkout-date')?.value;
    const checkinTime = document.getElementById('modal-checkin-time')?.value;
    const checkoutTime = document.getElementById('modal-checkout-time')?.value;
    const summary = document.getElementById('modal-summary')?.value;
    const hostNotes = document.getElementById('modal-host-notes')?.value;

    // Collect additional contacts
    const contactEntries = document.querySelectorAll('#modal-additional-contacts .contact-entry');
    const additionalContacts = Array.from(contactEntries).map(entry => {
        const nameInput = entry.querySelector('.contact-name');
        const phoneInput = entry.querySelector('.contact-phone');
        return {
            name: nameInput ? nameInput.value.trim() : '',
            phone: phoneInput ? phoneInput.value.trim() : ''
        };
    }).filter(contact => contact.name && contact.phone);

    // Prepare update data
    const updateData = {
        guestName: guestName,
        guestPhoneNumber: guestPhone,
        startDate: checkinDate,
        endDate: checkoutDate,
        checkinTime: checkinTime,
        checkoutTime: checkoutTime,
        summary: summary,
        hostNotes: hostNotes,
        additionalContacts: additionalContacts
    };

    console.log('Sending update data:', updateData);

    // Show loading state
    const saveBtn = document.querySelector('button[onclick*="saveReservationDetails"]');
    const originalText = saveBtn ? saveBtn.innerHTML : '';
    if (saveBtn) {
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Saving...';
        saveBtn.disabled = true;
    }

    // Send to backend API
    fetch(`/api/property/${propertyId}/reservations/${reservationId}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify(updateData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showReservationMessage('Reservation updated successfully!', 'success');

            // Update the reservation in the local data
            updateLocalReservationData(reservationId, updateData);

            // Refresh the calendar view if we're on it
            if (calendarView === 'timeline') {
                setTimeout(() => {
                    renderTimelineView();
                }, 1000);
            } else if (calendarView === 'list') {
                setTimeout(() => {
                    renderListView();
                }, 1000);
            }

            // Close modal after a short delay
            setTimeout(() => {
                closeReservationDetailsModal();
            }, 2000);
        } else {
            showReservationMessage(data.error || 'Failed to update reservation', 'error');
        }
    })
    .catch(error => {
        console.error('Error updating reservation:', error);
        showReservationMessage('Error updating reservation: ' + error.message, 'error');
    })
    .finally(() => {
        // Restore button state
        if (saveBtn) {
            saveBtn.innerHTML = originalText;
            saveBtn.disabled = false;
        }
    });
}

function showReservationMessage(message, type) {
    // Remove any existing messages
    const existingMessages = document.querySelectorAll('.reservation-message');
    existingMessages.forEach(msg => msg.remove());

    // Create message element
    const messageDiv = document.createElement('div');
    const bgColor = type === 'success' ? 'bg-green-100 border-green-400 text-green-700' : 'bg-red-100 border-red-400 text-red-700';
    const icon = type === 'success' ? 'fas fa-check-circle' : 'fas fa-exclamation-triangle';

    messageDiv.className = `reservation-message border-l-4 p-4 mb-4 ${bgColor}`;
    messageDiv.innerHTML = `
        <div class="flex">
            <div class="flex-shrink-0">
                <i class="${icon}"></i>
            </div>
            <div class="ml-3">
                <p class="text-sm">${message}</p>
            </div>
        </div>
    `;

    // Insert at the top of the modal content
    const modalContent = document.getElementById('reservation-details-content');
    if (modalContent) {
        modalContent.insertBefore(messageDiv, modalContent.firstChild);

        // Auto-remove after 5 seconds for success messages
        if (type === 'success') {
            setTimeout(() => {
                messageDiv.remove();
            }, 5000);
        }
    }
}

function updateLocalReservationData(reservationId, updateData) {
    // Update the reservation in the global reservations array
    const reservationIndex = reservations.findIndex(r => (r.id || r.reservationId) === reservationId);
    if (reservationIndex !== -1) {
        // Update the reservation with new data
        Object.assign(reservations[reservationIndex], updateData);

        // Also update filtered reservations if they exist
        const filteredIndex = filteredReservations.findIndex(r => (r.id || r.reservationId) === reservationId);
        if (filteredIndex !== -1) {
            Object.assign(filteredReservations[filteredIndex], updateData);
        }

        console.log('Updated local reservation data for:', reservationId);
    }
}

function copyToClipboard(text) {
    copyToClipboardWithFallback(text).then(success => {
        if (success) {
            console.log('Copied to clipboard:', text);
        } else {
            console.error('Failed to copy to clipboard');
        }
    });
}

function createReservationCard(reservation) {
    const card = document.createElement('div');
    card.className = 'bg-white rounded-lg shadow-md p-6 space-y-4';
    
    const startDate = reservation.startDate || reservation.check_in_date || '';
    const endDate = reservation.endDate || reservation.check_out_date || '';
    const guestName = getDisplayGuestName(reservation);
    const propertyName = reservation.property_name || 'Unknown Property';
    const summary = reservation.summary || reservation.Summary || '';
    
    card.innerHTML = `
        <div class="flex justify-between items-start">
            <div class="flex-1">
                <h3 class="text-lg font-semibold text-dark-purple">${propertyName}</h3>
                <p class="text-sm text-gray-600">${guestName}</p>
                <p class="text-sm text-gray-500">${summary}</p>
            </div>
            <div class="text-right">
                <div class="text-sm text-gray-600">
                    <i class="fas fa-calendar-plus mr-1"></i>${DateUtils.formatDate(startDate)}
                </div>
                <div class="text-sm text-gray-600">
                    <i class="fas fa-calendar-minus mr-1"></i>${DateUtils.formatDate(endDate)}
                </div>
            </div>
        </div>
        
        <!-- Guest Contacts section - commented out as requested
        <div class="border-t pt-4">
            <div class="flex justify-between items-center">
                <div class="flex-1">
                    <h4 class="font-medium text-dark-purple mb-2">Guest Contacts</h4>
                    <div id="contacts-container-${reservation.id}" class="space-y-2">
                        ${renderContactFields(reservation)}
                    </div>
                    <div class="mt-2 flex gap-2">
                        <button onclick="addContactField('${reservation.id}')" 
                                class="bg-persian-green hover:bg-green-600 text-white px-3 py-1 rounded text-sm">
                            <i class="fas fa-plus mr-1"></i>Add Contact
                        </button>
                        <button onclick="saveContacts('${reservation.property_id}', '${reservation.id}')" 
                                class="bg-saffron hover:bg-yellow-500 text-dark-purple px-3 py-1 rounded text-sm">
                            Save Contacts
                        </button>
                    </div>
                </div>

            </div>
        </div>
        -->
    `;
    
    return card;
}

// renderContactFields function - commented out as requested, stub function provided for compatibility
function renderContactFields(reservation) {
    // Stub function - returns empty string since Guest Contacts section is commented out
    return '';
}

/*
// Original function commented out:
function renderContactFields(reservation) {
    const contacts = reservation.additional_contacts || reservation.AdditionalContacts || [];
    
    if (contacts.length === 0) {
        return '<p class="text-sm text-gray-500">No additional contacts</p>';
    }
    
    return contacts.map(contact => `
        <div class="flex items-center gap-2 contact-entry">
            <input type="text" class="flex-1 px-2 py-1 border border-gray-300 rounded text-sm contact-name" 
                   placeholder="Name" value="${contact.name || ''}">
            <input type="tel" class="flex-1 px-2 py-1 border border-gray-300 rounded text-sm contact-phone" 
                   placeholder="+1xxxxxxxxxx" value="${contact.phone || ''}">
            <button onclick="removeContact(this)" class="text-red-500 hover:text-red-700">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `).join('');
}
*/

function refreshReservations() {
    console.log('Refreshing reservations from iCal and database');
    
    // Show loading state immediately
    showCalendarState('loading');
    
    // First get all properties for the host to check which ones have iCal URLs
    fetch('/api/user-properties', {
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        const propertiesData = data.success ? data.properties : [];
        console.log('Fetched properties for iCal refresh:', propertiesData);
        
        // Filter properties that have iCal URLs and are active
        const propertiesWithICal = propertiesData.filter(property => {
            const isActive = (property.status || 'active') === 'active';
            const hasIcal = property.icalUrl && property.icalUrl.trim();
            return isActive && hasIcal;
        });
        
        console.log(`Found ${propertiesWithICal.length} properties with iCal URLs out of ${propertiesData.length} total properties`);
        
        if (propertiesWithICal.length === 0) {
            // No properties have iCal URLs, just load from database
            console.log('No properties with iCal URLs found, loading from database only');
            loadCalendarData();
            return Promise.resolve([]);
        }
        
        // Create refresh promises for all properties with iCal URLs
        const refreshPromises = propertiesWithICal.map(property => {
            console.log(`Triggering iCal refresh for property: ${property.name} (${property.id})`);
            
            return fetch(`/api/property/${property.id}/reservations/refresh`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin'
            })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(errData => {
                        throw new Error(`${property.name}: ${errData.error || `HTTP error ${response.status}`}`);
                    }).catch(() => {
                        throw new Error(`${property.name}: HTTP error ${response.status} - ${response.statusText}`);
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    console.log(`✅ Successfully refreshed iCal for ${property.name}:`, data.stats);
                    return { property: property.name, success: true, stats: data.stats };
                } else {
                    throw new Error(`${property.name}: ${data.error}`);
                }
            })
            .catch(error => {
                console.error(`❌ Failed to refresh iCal for ${property.name}:`, error);
                return { property: property.name, success: false, error: error.message };
            });
        });
        
        // Wait for all iCal refresh requests to complete
        return Promise.all(refreshPromises);
    })
    .then(refreshResults => {
        // Log results of iCal refreshes
        if (refreshResults && refreshResults.length > 0) {
            const successful = refreshResults.filter(result => result.success);
            const failed = refreshResults.filter(result => !result.success);
            
            console.log(`iCal refresh completed: ${successful.length} successful, ${failed.length} failed`);
            
            // Log detailed results
            successful.forEach(result => {
                const stats = result.stats;
                console.log(`✅ ${result.property}: ${stats.total_events} events, ${stats.updated} updated, ${stats.added} added`);
            });
            
            failed.forEach(result => {
                console.error(`❌ ${result.property}: ${result.error}`);
            });
        }
        
        // Always load calendar data after iCal refresh attempts (successful or not)
        console.log('iCal refresh phase complete, loading updated calendar data');
        loadCalendarData();
    })
    .catch(error => {
        // If there's an error getting properties, still try to load calendar data
        console.error('Error during iCal refresh phase:', error);
        console.log('Falling back to loading calendar data from database');
        loadCalendarData();
    });
}

// --- Contact Management Functions - commented out as requested, stub functions provided for compatibility ---
function addContactField(reservationId) {
    // Stub function - no-op since Guest Contacts section is commented out
    return;
}

function removeContact(button) {
    // Stub function - no-op since Guest Contacts section is commented out
    return;
}

function saveContacts(propertyId, reservationId) {
    // Stub function - no-op since Guest Contacts section is commented out
    console.log('saveContacts called but disabled - Guest Contacts functionality is commented out');
    return;
}

/*
// Original functions commented out:
function addContactField(reservationId) {
    const container = document.getElementById(`contacts-container-${reservationId}`);
    if (!container) return;
    
    const entryDiv = document.createElement('div');
    entryDiv.className = 'flex items-center gap-2 contact-entry';
    
    entryDiv.innerHTML = `
        <input type="text" class="flex-1 px-2 py-1 border border-gray-300 rounded text-sm contact-name" 
               placeholder="Name">
        <input type="tel" class="flex-1 px-2 py-1 border border-gray-300 rounded text-sm contact-phone" 
               placeholder="+1xxxxxxxxxx">
        <button onclick="removeContact(this)" class="text-red-500 hover:text-red-700">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    container.appendChild(entryDiv);
}

function removeContact(button) {
    const entryDiv = button.parentElement;
    entryDiv.remove();
}

function saveContacts(propertyId, reservationId) {
    const container = document.getElementById(`contacts-container-${reservationId}`);
    if (!container) return;
    
    const contactEntries = container.querySelectorAll('.contact-entry');
    
    const contacts = Array.from(contactEntries).map(entry => {
        const nameInput = entry.querySelector('.contact-name');
        const phoneInput = entry.querySelector('.contact-phone');
        return {
            name: nameInput ? nameInput.value.trim() : '',
            phone: phoneInput ? phoneInput.value.trim() : ''
        };
    }).filter(contact => contact.name && contact.phone);
    
    console.log(`Saving ${contacts.length} contacts for reservation ${reservationId}`);
    
    // Send to backend
    fetch(`/api/property/${propertyId}/reservations/${reservationId}/contacts`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ contacts: contacts })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('Contacts saved successfully');
            // TODO: Show success message
        } else {
            console.error('Error saving contacts:', data.error);
            alert('Error saving contact information: ' + (data.error || 'Unknown server error'));
        }
    })
    .catch(error => {
        console.error('Error saving contacts:', error);
        alert('An error occurred while saving the contact information: ' + error.message);
    });
}
*/



// --- Support Center Screen Functions - COMMENTED OUT FOR FUTURE DEVELOPMENT ---
/*
function loadSupportData() {
    console.log('Loading support data');

    // TODO: Load conversations and tasks
    const conversationsFeed = document.getElementById('conversations-feed');
    const taskBoard = document.getElementById('task-board');
    const alertsZone = document.getElementById('alerts-zone');

    // For now, show placeholders
    if (conversationsFeed) {
        conversationsFeed.innerHTML = `
            <div class="text-center py-8">
                <i class="fas fa-comment-dots text-4xl text-gray-400 mb-4"></i>
                <p class="text-gray-600">Conversations feed coming soon</p>
            </div>
        `;
    }

    if (taskBoard) {
        taskBoard.innerHTML = `
            <div class="text-center py-8">
                <i class="fas fa-clipboard-list text-4xl text-gray-400 mb-4"></i>
                <p class="text-gray-600">Task board coming soon</p>
            </div>
        `;
    }

    if (alertsZone) {
        alertsZone.innerHTML = `
            <div class="text-center py-8">
                <i class="fas fa-bell text-4xl text-gray-400 mb-4"></i>
                <p class="text-gray-600">Alert system coming soon</p>
            </div>
        `;
    }
}

*/
// === SUPPORT CENTER FUNCTIONALITY ===

let conversationsData = [];
let conversationsOffset = 0;
let conversationsLimit = 20;
let hasMoreConversations = true;
let currentFilters = {};

function loadSupportData() {
    console.log('Loading Support Center data');

    // Load conversations
    loadConversations();

    // Populate property filter
    populatePropertyFilter();

    // After initial load, check for items missing summaries and trigger bulk generation
    setTimeout(triggerBulkSummariesIfNeeded, 400);
}

function loadConversations(reset = true) {
    if (reset) {
        conversationsOffset = 0;
        conversationsData = [];
        hasMoreConversations = true;
    }

    // Show loading state
    const loadingEl = document.getElementById('conversations-loading');
    const listEl = document.getElementById('conversations-list');
    const emptyEl = document.getElementById('conversations-empty');

    if (reset) {
        loadingEl.classList.remove('hidden');
        listEl.innerHTML = '';
        emptyEl.classList.add('hidden');
    }

    // Get all properties for the user
    const properties = window.propertiesData || [];
    if (properties.length === 0) {
        loadingEl.classList.add('hidden');
        emptyEl.classList.remove('hidden');
        updateConversationsCount(0);
        return;
    }

    // Load conversations for all properties
    Promise.all(properties.map(property => loadPropertyConversations(property.id)))
        .then(results => {
            // Flatten and combine all conversations
            const allConversations = results.flat();

            // Sort by date (most recent first)
            allConversations.sort((a, b) => new Date(b.start_time) - new Date(a.start_time));

            if (reset) {
                conversationsData = allConversations;
            } else {
                conversationsData = conversationsData.concat(allConversations);
            }

            // Apply filters
            const filteredConversations = applyFiltersToData(conversationsData);

            // Update UI
            displayConversations(filteredConversations, reset);
            updateConversationsCount(filteredConversations.length);

            loadingEl.classList.add('hidden');

            if (filteredConversations.length === 0) {
                emptyEl.classList.remove('hidden');
            }
        })
        .catch(error => {
            console.error('Error loading conversations:', error);
            loadingEl.classList.add('hidden');
            emptyEl.classList.remove('hidden');
            updateConversationsCount(0);
        });
}

function loadPropertyConversations(propertyId) {
    const params = new URLSearchParams({
        limit: conversationsLimit,
        offset: conversationsOffset,
        ...currentFilters
    });

    return fetch(`/api/conversations/property/${propertyId}?${params}`, {
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            return data.conversations.map(conv => ({
                ...conv,
                property_id: propertyId,
                property_name: getPropertyName(propertyId)
            }));
        }
        return [];
    })
    .catch(error => {
        console.error(`Error loading conversations for property ${propertyId}:`, error);
        return [];
    });
}

function displayConversations(conversations, reset = true) {
    const listEl = document.getElementById('conversations-list');

    if (reset) {
        listEl.innerHTML = '';
    }

    conversations.forEach(conversation => {
        const conversationEl = createConversationElement(conversation);
        listEl.appendChild(conversationEl);
    });

    // Update load more button
    const loadMoreContainer = document.getElementById('load-more-container');
    if (hasMoreConversations && conversations.length >= conversationsLimit) {
        loadMoreContainer.classList.remove('hidden');
    } else {
        loadMoreContainer.classList.add('hidden');
    }
}

function triggerBulkSummariesIfNeeded() {
    try {
        const listEl = document.getElementById('conversations-list');
        if (!listEl) return;

        // Collect conversations that lack an AI summary
        const missing = conversationsData.filter(c => !c.summary || c.summary.trim().length === 0);
        if (missing.length === 0) return;

        // Group by property for efficient backend calls if needed later
        const payload = missing.map(c => ({
            id: c.id,
            type: c.type,
            property_id: c.property_id
        }));

        fetch('/api/conversations/summaries/bulk-generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ conversations: payload })
        })
        .then(r => r.json())
        .then(res => {
            // Best-effort: refresh list after a short delay to pick up new summaries
            setTimeout(() => loadConversations(true), 1200);
        })
        .catch(err => console.warn('Bulk summary generation failed:', err));
    } catch (e) {
        console.warn('Error in triggerBulkSummariesIfNeeded:', e);
    }
}
function createConversationElement(conversation) {
    const div = document.createElement('div');
    div.className = 'p-4 hover:bg-gray-50 cursor-pointer transition-colors';
    div.onclick = () => openConversationModal(conversation);

    const channelIcon = conversation.channel === 'voice_call' ? 'fa-phone' : 'fa-comment';
    const channelColor = conversation.channel === 'voice_call' ? 'text-green-600' : 'text-blue-600';
    const statusColor = getStatusColor(conversation.status);

    const startTime = new Date(conversation.start_time);
    const timeAgo = getTimeAgo(startTime);
    const formattedTime = startTime.toLocaleString();

    div.innerHTML = `
        <div class="flex items-start space-x-4">
            <!-- Channel Icon -->
            <div class="flex-shrink-0">
                <div class="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center">
                    <i class="fas ${channelIcon} ${channelColor}"></i>
                </div>
            </div>

            <!-- Conversation Info -->
            <div class="flex-1 min-w-0">
                <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-2">
                        <h4 class="text-sm font-semibold text-gray-900 truncate">
                            ${conversation.guest_name}
                        </h4>
                        <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${statusColor}">
                            ${conversation.status}
                        </span>
                    </div>
                    <div class="text-xs text-gray-500">
                        ${timeAgo}
                    </div>
                </div>

                <div class="mt-1 flex items-center space-x-4 text-xs text-gray-500">
                    <span>
                        <i class="fas fa-home mr-1"></i>
                        ${conversation.property_name || 'Unknown Property'}
                    </span>
                    <span>
                        <i class="fas ${channelIcon} mr-1"></i>
                        ${conversation.channel === 'voice_call' ? 'Voice Call' : 'Text Chat'}
                    </span>
                    <span>
                        <i class="fas fa-comments mr-1"></i>
                        ${conversation.message_count} messages
                    </span>
                    ${conversation.duration ? `
                        <span>
                            <i class="fas fa-clock mr-1"></i>
                            ${formatDuration(conversation.duration)}
                        </span>
                    ` : ''}
                </div>

                <p class="mt-2 text-sm text-gray-600 line-clamp-2">
                    ${conversation.summary || 'No summary available'}
                </p>
            </div>
        </div>
    `;

    return div;
}
function openConversationModal(conversation) {
    console.log('Opening conversation modal:', conversation);

    const modal = document.getElementById('conversation-modal');
    const title = document.getElementById('conversation-modal-title');
    const info = document.getElementById('conversation-info');
    const loading = document.getElementById('conversation-modal-loading');
    const content = document.getElementById('conversation-content');

    // Show modal
    modal.classList.remove('hidden');

    // Set title
    title.textContent = `${conversation.guest_name} - ${conversation.channel === 'voice_call' ? 'Voice Call' : 'Text Chat'}`;

    // Set basic info
    const startTime = new Date(conversation.start_time);
    info.innerHTML = `
        <div>
            <span class="text-gray-500">Guest:</span>
            <span class="font-medium">${conversation.guest_name}</span>
        </div>
        <div>
            <span class="text-gray-500">Property:</span>
            <span class="font-medium">${conversation.property_name}</span>
        </div>
        <div>
            <span class="text-gray-500">Date:</span>
            <span class="font-medium">${startTime.toLocaleDateString()}</span>
        </div>
        <div>
            <span class="text-gray-500">Time:</span>
            <span class="font-medium">${startTime.toLocaleTimeString()}</span>
        </div>
    `;

    // Show loading
    loading.classList.remove('hidden');
    content.classList.add('hidden');

    // Load detailed conversation data
    const conversationType = conversation.type === 'voice_call' ? 'voice_diagnostics' : 'conversation';
    const params = new URLSearchParams({
        property_id: conversation.property_id,
        type: conversationType
    });

    fetch(`/api/conversations/details/${conversation.id}?${params}`, {
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Set summary text if available
            const summaryEl = document.getElementById('conversation-summary');
            if (summaryEl) {
                const fallback = conversation.summary || '';
                const detailedSummary = data.conversation.summary || fallback || 'No summary available yet.';
                summaryEl.textContent = detailedSummary;
            }
            displayConversationDetails(data.conversation);
        } else {
            console.error('Error loading conversation details:', data.error);
            alert('Error loading conversation details');
        }
    })
    .catch(error => {
        console.error('Error loading conversation details:', error);
        alert('Error loading conversation details');
    })
    .finally(() => {
        loading.classList.add('hidden');
        content.classList.remove('hidden');
    });
}

function displayConversationDetails(conversation) {
    const textContent = document.getElementById('text-chat-content');
    const voiceContent = document.getElementById('voice-call-content');

    if (conversation.type === 'voice_call') {
        // Show voice call content
        textContent.classList.add('hidden');
        voiceContent.classList.remove('hidden');

        displayVoiceCallDetails(conversation);
    } else {
        // Show text chat content
        voiceContent.classList.add('hidden');
        textContent.classList.remove('hidden');

        displayTextChatDetails(conversation);
    }
}

// Helper: derive language code from conversation diagnostics/config
function getConversationLanguage(conversation) {
    try {
        const tc = conversation.technical_config || conversation.TechnicalConfig || {};
        if (tc.LanguageCode) return tc.LanguageCode;
        if (tc.languageCode) return tc.languageCode;
        if (tc.VoiceSettings && tc.VoiceSettings.languageCode) return tc.VoiceSettings.languageCode;
    } catch (_) {}
    return 'en-US';
}

// Helper: preprocess transcript similar to guest dashboard masking (render-only)
function preprocessTranscriptForHost(text, targetLanguage = 'en-US') {
    let normalizedLanguage = targetLanguage === 'zh-CN' ? 'cmn-CN' : targetLanguage;
    const bypassLanguages = ['pt-BR', 'ja-JP', 'ko-KR', 'cmn-CN', 'th-TH'];
    if (!text || typeof text !== 'string') return text;
    if (text.startsWith('<') && text.endsWith('>')) return text;

    const languageCharacterSets = {
        'en-US': /[a-zA-Z0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'en-GB': /[a-zA-Z0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'en-CA': /[a-zA-Z0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'en-AU': /[a-zA-Z0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'es-ES': /[a-zA-ZñÑáéíóúüÁÉÍÓÚÜ0-9\s.,!?;:'"()\-–—¿¡<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'es-US': /[a-zA-ZñÑáéíóúüÁÉÍÓÚÜ0-9\s.,!?;:'"()\-–—¿¡<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'fr-FR': /[a-zA-ZàâäéèêëïîôùûüÿçÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'fr-CA': /[a-zA-ZàâäéèêëïîôùûüÿçÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'de-DE': /[a-zA-ZäöüßÄÖÜ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'it-IT': /[a-zA-ZàèéìîïòóùúÀÈÉÌÎÏÒÓÙÚ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'pt-BR': /[a-zA-ZàáâãéêíîóôõúçÀÁÂÃÉÊÍÎÓÔÕÚÇ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'nl-NL': /[a-zA-Z0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'pl-PL': /[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'ru-RU': /[a-zA-ZёЁ0-9\s.,!?;:'"()\-–—\u0400-\u04ff<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'ja-JP': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf\uff65-\uff9f<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'ko-KR': /[a-zA-Z0-9\s.,!?;:'"()\-–—\uac00-\ud7af\u1100-\u11ff\u3130-\u318f<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'cmn-CN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u4e00-\u9fff\u3400-\u4dbf\u20000-\u2a6df\u2a700-\u2b73f\u2b740-\u2b81f\u2b820-\u2ceaf\uf900-\ufaff\u2f800-\u2fa1f<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'ar-XA': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'hi-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0900-\u097f<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'bn-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0980-\u09ff<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'gu-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0a80-\u0aff<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'kn-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0c80-\u0cff<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'mr-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0900-\u097f<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'ml-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0d00-\u0d7f<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'ta-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0b80-\u0bff<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'te-IN': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0c00-\u0c7f<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'th-TH': /[a-zA-Z0-9\s.,!?;:'"()\-–—\u0e00-\u0e7f<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'vi-VN': /[a-zA-ZàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'id-ID': /[a-zA-Z0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g,
        'tr-TR': /[a-zA-ZçğıöşüÇĞIİÖŞÜ0-9\s.,!?;:'"()\-–—<>\/\%\^\@\#\*\&_\=\+\[\]\{\}\|\\\~\$\`€]/g
    };

    // Backward-compatibility heuristic
    const englishSet = languageCharacterSets['en-US'];
    let englishMatches = 0;
    let totalChars = 0;
    for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        if (ch === '\n') continue;
        totalChars++;
        englishSet.lastIndex = 0;
        if (englishSet.test(ch)) englishMatches++;
    }
    const englishRatio = totalChars > 0 ? englishMatches / totalChars : 1;
    if (bypassLanguages.includes(normalizedLanguage) && englishRatio >= 0.7) {
        normalizedLanguage = 'en-US';
    }

    const targetCharacterSet = languageCharacterSets[normalizedLanguage] || languageCharacterSets['en-US'];
    let masked = text.replace(/./g, (char) => {
        targetCharacterSet.lastIndex = 0;
        return targetCharacterSet.test(char) ? char : '[...]';
    });
    masked = masked.replace(/(?:\s*\[\.\.\.\]\s*)+/gi, ' [...] ').trim();
    return masked;
}

function displayVoiceCallDetails(conversation) {
    const transcriptEl = document.getElementById('voice-transcript');
    const metricsEl = document.getElementById('quality-metrics');

    // Display transcript
    transcriptEl.innerHTML = '';
    if (conversation.transcripts && conversation.transcripts.length > 0) {
        const languageCode = getConversationLanguage(conversation);
        conversation.transcripts.forEach(transcript => {
            const messageEl = document.createElement('div');
            messageEl.className = `flex ${transcript.role === 'user' ? 'justify-end' : 'justify-start'} mb-3`;

            const bubbleClass = transcript.role === 'user'
                ? 'bg-persian-green text-white'
                : 'bg-white border border-gray-200';

            const time = new Date(transcript.timestamp).toLocaleTimeString();
            const maskedText = preprocessTranscriptForHost(transcript.text, languageCode);

            messageEl.innerHTML = `
                <div class="max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${bubbleClass}">
                    <div class="text-sm">
                        <strong>${transcript.role === 'user' ? conversation.guest_name : 'Assistant'}:</strong>
                        ${maskedText}
                    </div>
                    <div class="text-xs opacity-75 mt-1">${time}</div>
                </div>
            `;

            transcriptEl.appendChild(messageEl);
        });
    } else {
        transcriptEl.innerHTML = '<p class="text-gray-500 text-center">No transcript available</p>';
    }

    // Session events removed for host-facing UI

    // Display metrics including feedback inline
    const metrics = conversation.quality_metrics || {};
    const feedback = conversation.feedback || {};
    const hasFb = (feedback && (feedback.enjoyment != null || feedback.accuracy != null));
    metricsEl.innerHTML = `
        <div class="grid grid-cols-2 gap-4 text-sm">
            <div>
                <span class="text-gray-500">Status:</span>
                <span class="font-medium ml-2">${conversation.status}</span>
            </div>
            <div>
                <span class="text-gray-500">Duration:</span>
                <span class="font-medium ml-2">${conversation.duration ? formatDuration(conversation.duration) : 'N/A'}</span>
            </div>
            <div>
                <span class="text-gray-500">Errors:</span>
                <span class="font-medium ml-2">${conversation.errors ? conversation.errors.length : 0}</span>
            </div>
            <div>
                <span class="text-gray-500">Warnings:</span>
                <span class="font-medium ml-2">${conversation.warnings ? conversation.warnings.length : 0}</span>
            </div>
            ${hasFb ? `
            <div>
                <span class="text-gray-500">Enjoyment (0-3):</span>
                <span class="font-medium ml-2">${feedback.enjoyment}</span>
            </div>
            <div>
                <span class="text-gray-500">Accuracy (1-5):</span>
                <span class="font-medium ml-2">${feedback.accuracy}</span>
            </div>
            <div class="col-span-2">
                <span class="text-gray-500">Feedback Submitted:</span>
                <span class="font-medium ml-2">${feedback.submitted_at ? new Date(feedback.submitted_at).toLocaleString() : '-'}</span>
            </div>
            ` : ''}
        </div>
    `;
}

function displayTextChatDetails(conversation) {
    const messagesEl = document.getElementById('text-messages');
    const metricsEl = document.getElementById('quality-metrics-text');

    messagesEl.innerHTML = '';
    if (conversation.messages && conversation.messages.length > 0) {
        const languageCode = getConversationLanguage(conversation);
        conversation.messages.forEach(message => {
            const messageEl = document.createElement('div');
            messageEl.className = `flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} mb-4`;

            const bubbleClass = message.role === 'user'
                ? 'bg-persian-green text-white'
                : 'bg-white border border-gray-200';

            const time = new Date(message.timestamp).toLocaleTimeString();
            const rawText = message.text || message.content || '';
            const maskedText = preprocessTranscriptForHost(rawText, languageCode);

            messageEl.innerHTML = `
                <div class="max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${bubbleClass}">
                    <div class="text-sm">
                        <strong>${message.role === 'user' ? conversation.guest_name : 'Assistant'}:</strong>
                        ${maskedText}
                    </div>
                    <div class="text-xs opacity-75 mt-1">${time}</div>
                </div>
            `;

            messagesEl.appendChild(messageEl);
        });
    } else {
        messagesEl.innerHTML = '<p class="text-gray-500 text-center">No messages available</p>';
    }

    // Render metrics box with feedback inline
    const feedback = conversation.feedback || {};
    const hasFb = (feedback && (feedback.enjoyment != null || feedback.accuracy != null));
    metricsEl.innerHTML = `
        <div class="grid grid-cols-2 gap-4 text-sm">
            <div class="col-span-2 text-gray-600">No technical metrics for text chat</div>
            ${hasFb ? `
            <div>
                <span class="text-gray-500">Enjoyment (0-3):</span>
                <span class="font-medium ml-2">${feedback.enjoyment}</span>
            </div>
            <div>
                <span class="text-gray-500">Accuracy (1-5):</span>
                <span class="font-medium ml-2">${feedback.accuracy}</span>
            </div>
            <div class="col-span-2">
                <span class="text-gray-500">Feedback Submitted:</span>
                <span class="font-medium ml-2">${feedback.submitted_at ? new Date(feedback.submitted_at).toLocaleString() : '-'}</span>
            </div>
            ` : ''}
        </div>
    `;
}

function closeConversationModal() {
    const modal = document.getElementById('conversation-modal');
    modal.classList.add('hidden');
}

function exportConversation() {
    try {
        const titleEl = document.getElementById('conversation-modal-title');
        const isVoice = titleEl && titleEl.textContent.includes('Voice Call');

        const transcriptContainer = isVoice ? document.getElementById('voice-transcript') : document.getElementById('text-messages');
        if (!transcriptContainer) {
            alert('Nothing to export.');
            return;
        }

        // Gather metadata
        const infoEl = document.getElementById('conversation-info');
        const meta = [];
        if (titleEl) meta.push(`Title: ${titleEl.textContent}`);
        if (infoEl) {
            const tmp = infoEl.cloneNode(true);
            // Convert HTML to plain text
            meta.push(tmp.innerText.replace(/\s+/g, ' ').trim());
        }

        // Collect messages as text lines
        const lines = [];
        transcriptContainer.querySelectorAll('div').forEach(div => {
            const text = div.innerText || '';
            const clean = text.replace(/\s+/g, ' ').trim();
            if (clean) lines.push(clean);
        });

        const content = [meta.join('\n'), '', ...lines].join('\n');

        // Download as text file
        const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        a.href = url;
        a.download = `conversation-${timestamp}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (e) {
        console.error('Export failed:', e);
        alert('Failed to export conversation.');
    }
}

// Filter functions
function showConversationFilters() {
    const filterBar = document.getElementById('filter-bar');
    filterBar.classList.toggle('hidden');
}

function applyConversationFilters() {
    const channelFilter = document.getElementById('channel-filter').value;
    const propertyFilter = document.getElementById('property-filter').value;
    const dateFromFilter = document.getElementById('date-from-filter').value;
    const dateToFilter = document.getElementById('date-to-filter').value;

    currentFilters = {};

    if (channelFilter) currentFilters.channel = channelFilter;
    if (propertyFilter) currentFilters.property_id = propertyFilter;
    if (dateFromFilter) currentFilters.date_from = dateFromFilter + 'T00:00:00Z';
    if (dateToFilter) currentFilters.date_to = dateToFilter + 'T23:59:59Z';

    // Update filter chips
    updateFilterChips();

    // Reload conversations with filters
    loadConversations(true);
}

function clearConversationFilters() {
    document.getElementById('channel-filter').value = '';
    document.getElementById('property-filter').value = '';
    document.getElementById('date-from-filter').value = '';
    document.getElementById('date-to-filter').value = '';

    currentFilters = {};
    updateFilterChips();
    loadConversations(true);
}

function updateFilterChips() {
    const chipsContainer = document.getElementById('filter-chips');
    chipsContainer.innerHTML = '';

    Object.entries(currentFilters).forEach(([key, value]) => {
        const chip = document.createElement('span');
        chip.className = 'inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-persian-green text-white';

        let label = key;
        if (key === 'channel') label = value === 'voice_call' ? 'Voice Call' : 'Text Chat';
        else if (key === 'property_id') label = getPropertyName(value);
        else if (key === 'date_from') label = `From: ${new Date(value).toLocaleDateString()}`;
        else if (key === 'date_to') label = `To: ${new Date(value).toLocaleDateString()}`;

        chip.textContent = label;
        chipsContainer.appendChild(chip);
    });
}

function refreshConversations() {
    loadConversations(true);
}

function loadMoreConversations() {
    conversationsOffset += conversationsLimit;
    loadConversations(false);
}

// Helper functions
function getPropertyName(propertyId) {
    const properties = window.propertiesData || [];
    const property = properties.find(p => p.id === propertyId);
    return property ? property.name : 'Unknown Property';
}

function populatePropertyFilter() {
    const propertyFilter = document.getElementById('property-filter');
    const properties = window.propertiesData || [];

    // Clear existing options (except "All Properties")
    while (propertyFilter.children.length > 1) {
        propertyFilter.removeChild(propertyFilter.lastChild);
    }

    // Add property options
    properties.forEach(property => {
        const option = document.createElement('option');
        option.value = property.id;
        option.textContent = property.name;
        propertyFilter.appendChild(option);
    });
}

function updateConversationsCount(count) {
    const countEl = document.getElementById('conversations-count');
    if (countEl) {
        countEl.textContent = count;
    }
}

function applyFiltersToData(conversations) {
    return conversations.filter(conversation => {
        // Apply channel filter
        if (currentFilters.channel && conversation.channel !== currentFilters.channel) {
            return false;
        }

        // Apply property filter
        if (currentFilters.property_id && conversation.property_id !== currentFilters.property_id) {
            return false;
        }

        // Apply date filters
        const conversationDate = new Date(conversation.start_time);

        if (currentFilters.date_from) {
            const fromDate = new Date(currentFilters.date_from);
            if (conversationDate < fromDate) return false;
        }

        if (currentFilters.date_to) {
            const toDate = new Date(currentFilters.date_to);
            if (conversationDate > toDate) return false;
        }

        return true;
    });
}

function getStatusColor(status) {
    switch (status?.toLowerCase()) {
        case 'completed':
        case 'active':
            return 'bg-green-100 text-green-800';
        case 'failed':
        case 'error':
            return 'bg-red-100 text-red-800';
        case 'initializing':
        case 'pending':
            return 'bg-yellow-100 text-yellow-800';
        default:
            return 'bg-gray-100 text-gray-800';
    }
}

function getTimeAgo(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
}

function formatDuration(seconds) {
    if (!seconds) return 'N/A';

    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;

    if (mins > 0) {
        return `${mins}m ${secs}s`;
    }
    return `${secs}s`;
}

// --- Settings Modal Functions ---
function openSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) {
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        
        // Load settings content
        loadSettingsContent();
    }
}

function closeSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (modal) {
        modal.classList.add('hidden');
        document.body.style.overflow = 'auto';
    }
}

function loadSettingsContent() {
    const settingsContent = document.getElementById('settings-content');
    if (!settingsContent) return;

    // Show loading state
    settingsContent.innerHTML = `
        <div class="text-center py-8">
            <i class="fas fa-spinner fa-spin text-2xl text-persian-green mb-4"></i>
            <p class="text-gray-600">Loading settings...</p>
        </div>
    `;

    // Load user profile data
    fetch('/api/user/profile', {
        method: 'GET',
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success && data.user) {
            renderSettingsContent(data.user);
        } else {
            renderSettingsError(data.error || 'Failed to load profile data');
        }
    })
    .catch(error => {
        console.error('Error loading profile:', error);
        renderSettingsError('Error loading profile data');
    });
}
function renderSettingsContent(userData) {
    const settingsContent = document.getElementById('settings-content');
    if (!settingsContent) return;

    settingsContent.innerHTML = createSettingsHTML(userData);

    // Set original values for change detection
    setTimeout(() => {
        const emailInput = document.getElementById('settings-email');
        const phoneInput = document.getElementById('settings-phone');
        
        if (emailInput) {
            emailInput.setAttribute('data-original-value', emailInput.value || '');
        }
        if (phoneInput) {
            // For phone, store the complete international format to match what saveProfileSettings uses
            let originalPhone = phoneInput.value || '';
            if (typeof getCompletePhoneNumber === 'function') {
                const completePhone = getCompletePhoneNumber('settings-phone');
                if (completePhone) {
                    originalPhone = completePhone;
                }
            }
            phoneInput.setAttribute('data-original-value', originalPhone);
        }
    }, 150); // Increased delay to ensure phone input is fully initialized

    // Initialize enhanced phone input and load account stats after content is rendered
    setTimeout(() => {
        // Initialize enhanced phone input
        if (typeof initializePhoneInput === 'function') {
            const phoneInput = document.getElementById('settings-phone');
            let currentPhone = phoneInput ? phoneInput.value : '';

            // Parse the phone number using the comprehensive parser
            let countryCode = 'US';
            let localNumber = '';

            if (currentPhone && typeof parsePhoneNumber === 'function') {
                const parsed = parsePhoneNumber(currentPhone);
                countryCode = parsed.countryCode;
                localNumber = parsed.localNumber;

                // Clear the input value so enhanced input can set it properly
                if (phoneInput) {
                    phoneInput.value = localNumber;
                }
            }

            initializePhoneInput('settings-phone', {
                defaultCountry: countryCode,
                placeholder: '(555) 123-4567',
                autoFormat: true
            });
        }

        loadAccountStats();
    }, 100);
}

function renderSettingsError(errorMessage) {
    const settingsContent = document.getElementById('settings-content');
    if (!settingsContent) return;

    settingsContent.innerHTML = `
        <div class="text-center py-8">
            <i class="fas fa-exclamation-triangle text-4xl text-red-500 mb-4"></i>
            <p class="text-red-600 mb-2">Error Loading Settings</p>
            <p class="text-sm text-gray-500 mb-4">${errorMessage}</p>
            <button onclick="loadSettingsContent()" class="bg-persian-green hover:bg-green-600 text-white px-4 py-2 rounded-lg">
                <i class="fas fa-redo mr-2"></i>Try Again
            </button>
        </div>
    `;
}

function createSettingsHTML(userData) {
    const displayName = userData.displayName || userData.DisplayName || '';
    const email = userData.email || userData.Email || '';
    const phoneNumber = userData.phoneNumber || userData.PhoneNumber || '';
    const airbnbUserLink = userData.airbnbUserLink || '';

    // Get system timezone as default
    const systemTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const userTimezone = userData.timezone || systemTimezone;

    return `
        <div class="max-w-4xl mx-auto">
            <!-- Settings Navigation Tabs -->
            <div class="border-b border-gray-200 mb-6">
                <nav class="flex space-x-8">
                    <button onclick="showSettingsTab('profile')"
                            class="settings-tab-btn py-2 px-1 border-b-2 font-medium text-sm active"
                            data-tab="profile">
                        <i class="fas fa-user mr-2"></i>Profile & Preferences
                    </button>
                    <!-- Notifications and Team Management tabs - disabled as requested
                    <button onclick="showSettingsTab('notifications')"
                            class="settings-tab-btn py-2 px-1 border-b-2 font-medium text-sm"
                            data-tab="notifications">
                        <i class="fas fa-bell mr-2"></i>Notifications
                    </button>
                    <button onclick="showSettingsTab('team')"
                            class="settings-tab-btn py-2 px-1 border-b-2 font-medium text-sm"
                            data-tab="team">
                        <i class="fas fa-users mr-2"></i>Team Management
                    </button>
                    -->
                </nav>
            </div>

            <!-- Profile Tab -->
            <div id="settings-profile-tab" class="settings-tab-content">
                <div class="grid grid-cols-1 gap-8">
                    <!-- Single Column: Basic Profile -->
                    <div class="space-y-6">
                        <div class="bg-gray-50 rounded-lg p-6">
                            <h3 class="text-lg font-semibold text-dark-purple mb-4">
                                <i class="fas fa-user-circle mr-2"></i>Basic Information
                            </h3>
                            <form id="profile-form" class="space-y-4">
                                <div>
                                    <label for="settings-display-name" class="block text-sm font-medium text-gray-700 mb-1">
                                        Display Name
                                    </label>
                                    <input type="text" id="settings-display-name" name="displayName"
                                           value="${displayName}"
                                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                           placeholder="Your display name">
                                    <p class="text-xs text-gray-500 mt-1">This name will be shown to your guests</p>
                                </div>

                                <div>
                                    <label for="settings-email" class="block text-sm font-medium text-gray-700 mb-1">
                                        Email Address
                                    </label>
                                    <input type="email" id="settings-email" name="email"
                                           value="${email}"
                                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                           placeholder="your@email.com">
                                    <p class="text-xs text-gray-500 mt-1">Used for account notifications and guest communications</p>
                                </div>

                                <div>
                                    <label for="settings-phone" class="block text-sm font-medium text-gray-700 mb-1">
                                        Phone Number
                                    </label>
                                    <input type="tel" id="settings-phone" name="phoneNumber"
                                           value="${phoneNumber}"
                                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                           placeholder="(555) 123-4567">
                                    <p class="text-xs text-gray-500 mt-1">Your contact phone number</p>
                                </div>

                                <div>
                                    <label for="settings-airbnb-link" class="block text-sm font-medium text-gray-700 mb-1">
                                        Airbnb User Profile Link
                                    </label>
                                    <input type="url" id="settings-airbnb-link" name="airbnbUserLink"
                                           value="${airbnbUserLink}"
                                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green"
                                           placeholder="https://www.airbnb.com/users/show/">
                                    <p class="text-xs text-gray-500 mt-1">Used to sync your Airbnb listings data</p>
                                </div>
                            </form>
                        </div>

                        <!-- Security Section - commented out as requested
                        <div class="bg-gray-50 rounded-lg p-6">
                            <h3 class="text-lg font-semibold text-dark-purple mb-4">
                                <i class="fas fa-shield-alt mr-2"></i>Security
                            </h3>
                            <div class="space-y-3">
                                <button onclick="changePIN()"
                                        class="w-full bg-saffron hover:bg-yellow-500 text-dark-purple px-4 py-2 rounded-lg font-medium transition-colors text-left">
                                    <i class="fas fa-key mr-2"></i>Change PIN
                                </button>
                                <p class="text-xs text-gray-500">Update your 4-digit PIN for secure access</p>
                            </div>
                        </div>
                        -->
                    </div>

                    <!-- Right Column: Preferences - Temporarily commented out
                    <div class="space-y-6">
                        <div class="bg-gray-50 rounded-lg p-6">
                            <h3 class="text-lg font-semibold text-dark-purple mb-4">
                                <i class="fas fa-cog mr-2"></i>Preferences
                            </h3>
                            <div class="space-y-4">
                                <div>
                                    <label class="block text-sm font-medium text-gray-700 mb-2">
                                        Default Check-in Time
                                    </label>
                                    <input type="time" id="settings-checkin-time" name="defaultCheckInTime"
                                           value="${userData.defaultCheckInTime || '15:00'}"
                                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green">
                                </div>

                                <div>
                                    <label class="block text-sm font-medium text-gray-700 mb-2">
                                        Default Check-out Time
                                    </label>
                                    <input type="time" id="settings-checkout-time" name="defaultCheckOutTime"
                                           value="${userData.defaultCheckOutTime || '11:00'}"
                                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green">
                                </div>

                                <div>
                                    <label class="block text-sm font-medium text-gray-700 mb-2">
                                        Time Zone
                                    </label>
                                    <select id="settings-timezone" name="timezone"
                                            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green">
                                        ${createTimezoneOptions(userTimezone)}
                                    </select>
                                    <p class="text-xs text-gray-500 mt-1">
                                        ${userTimezone === systemTimezone ? 'Using system timezone' : 'Custom timezone selected'}
                                    </p>
                                </div>
                            </div>
                        </div>

                        <!-- Quick Stats - Temporarily commented out
                        <div class="bg-gray-50 rounded-lg p-6">
                            <h3 class="text-lg font-semibold text-dark-purple mb-4">
                                <i class="fas fa-chart-bar mr-2"></i>Account Overview
                            </h3>
                            <div class="grid grid-cols-2 gap-4 text-center">
                                <div class="bg-white rounded-lg p-3">
                                    <div class="text-2xl font-bold text-persian-green" id="stats-properties">-</div>
                                    <div class="text-xs text-gray-600">Properties</div>
                                </div>
                                <div class="bg-white rounded-lg p-3">
                                    <div class="text-2xl font-bold text-saffron" id="stats-reservations">-</div>
                                    <div class="text-xs text-gray-600">Active Reservations</div>
                                </div>
                            </div>
                        </div>
                        -->
                    </div>

                </div>

                <!-- Action Buttons -->
                <div class="flex justify-end space-x-4 mt-8 pt-6 border-t border-gray-200">
                    <button onclick="saveProfileSettings()"
                            class="px-6 py-2 bg-persian-green hover:bg-green-600 text-white rounded-lg font-medium transition-colors">
                        <i class="fas fa-save mr-2"></i>Save Changes
                    </button>
                </div>
            </div>

            <!-- Notifications and Team Management tabs content - disabled as requested
            <div id="settings-notifications-tab" class="settings-tab-content hidden">
                <div class="bg-gray-50 rounded-lg p-6">
                    <h3 class="text-lg font-semibold text-dark-purple mb-4">
                        <i class="fas fa-bell mr-2"></i>Notification Preferences
                    </h3>
                    <div class="space-y-4">
                        <p class="text-gray-600 mb-6">Choose how you want to be notified about important events.</p>

                        <div class="text-center py-8">
                            <i class="fas fa-bell text-4xl text-gray-400 mb-4"></i>
                            <p class="text-gray-600 mb-2">Notification Settings</p>
                            <p class="text-sm text-gray-500">Coming soon - Configure email, SMS, and app notifications</p>
                        </div>
                    </div>
                </div>
            </div>

            <div id="settings-team-tab" class="settings-tab-content hidden">
                <div class="bg-gray-50 rounded-lg p-6">
                    <h3 class="text-lg font-semibold text-dark-purple mb-4">
                        <i class="fas fa-users mr-2"></i>Team & Access Management
                    </h3>
                    <div class="space-y-4">
                        <p class="text-gray-600 mb-6">Manage cleaning crew, maintenance team, and other staff access.</p>

                        <div class="text-center py-8">
                            <i class="fas fa-users text-4xl text-gray-400 mb-4"></i>
                            <p class="text-gray-600 mb-2">Team Management</p>
                            <p class="text-sm text-gray-500">Coming soon - Add team members, assign roles, and manage permissions</p>
                        </div>
                    </div>
                </div>
            </div>
            -->
        </div>
    `;
}

// Helper function to create timezone options
function createTimezoneOptions(selectedTimezone) {
    const systemTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

    const timezones = [
        // Add system timezone as first option
        { value: systemTimezone, label: `${systemTimezone.replace('_', ' ')} (System Default)` },
        // Common US timezones
        { value: 'America/New_York', label: 'Eastern Time (ET)' },
        { value: 'America/Chicago', label: 'Central Time (CT)' },
        { value: 'America/Denver', label: 'Mountain Time (MT)' },
        { value: 'America/Los_Angeles', label: 'Pacific Time (PT)' },
        { value: 'America/Phoenix', label: 'Arizona Time (MST)' },
        { value: 'America/Anchorage', label: 'Alaska Time (AKST)' },
        { value: 'Pacific/Honolulu', label: 'Hawaii Time (HST)' },
        // International timezones
        { value: 'America/Toronto', label: 'Toronto (ET)' },
        { value: 'America/Vancouver', label: 'Vancouver (PT)' },
        { value: 'Europe/London', label: 'London (GMT)' },
        { value: 'Europe/Paris', label: 'Paris (CET)' },
        { value: 'Europe/Berlin', label: 'Berlin (CET)' },
        { value: 'Asia/Tokyo', label: 'Tokyo (JST)' },
        { value: 'Asia/Shanghai', label: 'Shanghai (CST)' },
        { value: 'Australia/Sydney', label: 'Sydney (AEDT)' }
    ];

    // Remove duplicate if system timezone is already in the list
    const uniqueTimezones = timezones.filter((tz, index) =>
        index === 0 || tz.value !== systemTimezone
    );

    return uniqueTimezones.map(tz =>
        `<option value="${tz.value}" ${tz.value === selectedTimezone ? 'selected' : ''}>${tz.label}</option>`
    ).join('');
}

// Settings tab management
function showSettingsTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.settings-tab-content').forEach(tab => {
        tab.classList.add('hidden');
    });

    // Remove active class from all tab buttons
    document.querySelectorAll('.settings-tab-btn').forEach(btn => {
        btn.classList.remove('active', 'border-persian-green', 'text-persian-green');
        btn.classList.add('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
    });

    // Show selected tab content
    const selectedTab = document.getElementById(`settings-${tabName}-tab`);
    if (selectedTab) {
        selectedTab.classList.remove('hidden');
    }

    // Add active class to selected tab button
    const selectedBtn = document.querySelector(`[data-tab="${tabName}"]`);
    if (selectedBtn) {
        selectedBtn.classList.add('active', 'border-persian-green', 'text-persian-green');
        selectedBtn.classList.remove('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
    }
}

// Profile form management
function resetProfileForm() {
    if (confirm('Are you sure you want to reset all changes?')) {
        loadSettingsContent(); // Reload the original data
    }
}

function saveProfileSettings() {
    const form = document.getElementById('profile-form');
    if (!form) return;

    // Get form data
    const formData = new FormData(form);

    // Get complete phone number if enhanced input is used
    let phoneNumber = formData.get('phoneNumber');
    if (typeof getCompletePhoneNumber === 'function') {
        const completePhoneNumber = getCompletePhoneNumber('settings-phone');
        if (completePhoneNumber) {
            phoneNumber = completePhoneNumber;
        }
    }

    const profileData = {
        displayName: formData.get('displayName'),
        email: formData.get('email'),
        phoneNumber: phoneNumber,
        airbnbUserLink: formData.get('airbnbUserLink'),
        timezone: document.getElementById('settings-timezone')?.value,
        defaultCheckInTime: document.getElementById('settings-checkin-time')?.value,
        defaultCheckOutTime: document.getElementById('settings-checkout-time')?.value
    };

    // Show loading state
    const saveBtn = document.querySelector('button[onclick="saveProfileSettings()"]');
    const originalText = saveBtn ? saveBtn.innerHTML : '';
    if (saveBtn) {
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Saving...';
        saveBtn.disabled = true;
    }

    // Get current user data to compare changes
    const currentEmail = document.getElementById('settings-email').getAttribute('data-original-value') || '';
    const currentPhone = document.getElementById('settings-phone').getAttribute('data-original-value') || '';
    const newEmail = profileData.email;
    const newPhone = profileData.phoneNumber;

    // Check if email or phone changed - if so, they need verification
    const emailChanged = newEmail !== currentEmail;
    const phoneChanged = newPhone !== currentPhone;
    
    // Debug logging
    console.log('Change detection:', {
        currentEmail, newEmail, emailChanged,
        currentPhone, newPhone, phoneChanged
    });

    if (emailChanged && newEmail) {
        // Email changed - need to verify
        // Reset button state before showing verification modal
        if (saveBtn) {
            saveBtn.innerHTML = originalText;
            saveBtn.disabled = false;
        }
        showEmailVerificationModal(newEmail, profileData);
        return;
    }

    if (phoneChanged && newPhone) {
        // Phone changed - need to verify
        // Reset button state before showing verification modal
        if (saveBtn) {
            saveBtn.innerHTML = originalText;
            saveBtn.disabled = false;
        }
        showPhoneVerificationModal(newPhone, profileData);
        return;
    }

    // No credential changes, proceed with normal save
    saveProfileData(profileData);
}

function saveProfileData(profileData) {
    // Show loading state
    const saveBtn = document.querySelector('button[onclick="saveProfileSettings()"]');
    const originalText = saveBtn ? saveBtn.innerHTML : '';
    if (saveBtn) {
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Saving...';
        saveBtn.disabled = true;
    }

    // Send update request
    fetch('/api/profile/update', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify(profileData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show success message
            showSettingsMessage('Profile updated successfully!', 'success');

            // Update any displayed user info in the dashboard
            updateDisplayedUserInfo(profileData);

            // Reload settings to show updated verification status
            setTimeout(() => {
                loadSettingsContent();
            }, 1000);
        } else {
            showSettingsMessage(data.error || 'Failed to update profile', 'error');
        }
    })
    .catch(error => {
        console.error('Error updating profile:', error);
        showSettingsMessage('Error updating profile: ' + error.message, 'error');
    })
    .finally(() => {
        // Restore button state
        if (saveBtn) {
            saveBtn.innerHTML = originalText;
            saveBtn.disabled = false;
        }
    });
}
function showSettingsMessage(message, type) {
    // Remove any existing messages
    const existingMessages = document.querySelectorAll('.settings-message');
    existingMessages.forEach(msg => msg.remove());

    // Create message element
    const messageDiv = document.createElement('div');
    messageDiv.className = `settings-message alert ${type === 'success' ? 'alert-success' : 'alert-error'} mb-4`;

    const bgColor = type === 'success' ? 'bg-green-100 border-green-400 text-green-700' : 'bg-red-100 border-red-400 text-red-700';
    const icon = type === 'success' ? 'fas fa-check-circle' : 'fas fa-exclamation-triangle';

    messageDiv.className = `settings-message border-l-4 p-4 mb-4 ${bgColor}`;
    messageDiv.innerHTML = `
        <div class="flex">
            <div class="flex-shrink-0">
                <i class="${icon}"></i>
            </div>
            <div class="ml-3">
                <p class="text-sm">${message}</p>
            </div>
        </div>
    `;

    // Insert at the top of the settings content
    const settingsContent = document.getElementById('settings-content');
    if (settingsContent) {
        settingsContent.insertBefore(messageDiv, settingsContent.firstChild);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            messageDiv.remove();
        }, 5000);
    }
}

function updateDisplayedUserInfo(profileData) {
    // Update any user info displayed in the dashboard header or elsewhere
    // This is a placeholder for future implementation
    console.log('Updated user info:', profileData);
}

// changePIN function - commented out as requested since Security section is disabled
/*
function changePIN() {
    // Create PIN change modal
    const pinModal = createPINChangeModal();
    document.body.appendChild(pinModal);

    // Show the modal
    pinModal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}
*/

// createPINChangeModal function - commented out as requested since Security section is disabled
/*
function createPINChangeModal() {
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 pin-change-modal';
    modal.id = 'pin-change-modal';

    modal.innerHTML = `
        <div class="flex items-center justify-center min-h-screen p-4">
            <div class="bg-white rounded-lg shadow-xl max-w-md w-full">
                <div class="bg-persian-green text-white p-6 rounded-t-lg">
                    <div class="flex items-center justify-between">
                        <h3 class="text-xl font-semibold">
                            <i class="fas fa-key mr-2"></i>Change PIN
                        </h3>
                        <button onclick="closePINChangeModal()" class="text-white hover:text-gray-200">
                            <i class="fas fa-times text-xl"></i>
                        </button>
                    </div>
                </div>

                <div class="p-6">
                    <div id="pin-change-content">
                        <div class="mb-6">
                            <p class="text-gray-600 mb-4">Enter your new 4-digit PIN for secure access to your account.</p>

                            <div class="space-y-4">
                                <div>
                                    <label for="new-pin" class="block text-sm font-medium text-gray-700 mb-2">
                                        New PIN (4 digits)
                                    </label>
                                    <input type="password"
                                           id="new-pin"
                                           maxlength="4"
                                           pattern="[0-9]{4}"
                                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green text-center text-2xl tracking-widest"
                                           placeholder="••••"
                                           autocomplete="new-password">
                                    <p class="text-xs text-gray-500 mt-1">Enter exactly 4 digits</p>
                                </div>

                                <div>
                                    <label for="confirm-pin" class="block text-sm font-medium text-gray-700 mb-2">
                                        Confirm New PIN
                                    </label>
                                    <input type="password"
                                           id="confirm-pin"
                                           maxlength="4"
                                           pattern="[0-9]{4}"
                                           class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-persian-green text-center text-2xl tracking-widest"
                                           placeholder="••••"
                                           autocomplete="new-password">
                                    <p class="text-xs text-gray-500 mt-1">Re-enter the same 4 digits</p>
                                </div>
                            </div>

                            <div id="pin-error-message" class="hidden mt-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
                                <!-- Error message will be inserted here -->
                            </div>
                        </div>

                        <div class="flex justify-end space-x-4">
                            <button onclick="closePINChangeModal()"
                                    class="px-6 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                                Cancel
                            </button>
                            <button onclick="submitPINChange()"
                                    id="pin-submit-btn"
                                    class="px-6 py-2 bg-persian-green hover:bg-green-600 text-white rounded-lg font-medium transition-colors">
                                <i class="fas fa-save mr-2"></i>Change PIN
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Add event listeners for PIN input validation
    setTimeout(() => {
        const newPinInput = modal.querySelector('#new-pin');
        const confirmPinInput = modal.querySelector('#confirm-pin');

        // Only allow numeric input
        [newPinInput, confirmPinInput].forEach(input => {
            input.addEventListener('input', (e) => {
                e.target.value = e.target.value.replace(/[^0-9]/g, '');
                validatePINInputs();
            });

            input.addEventListener('keypress', (e) => {
                if (!/[0-9]/.test(e.key) && !['Backspace', 'Delete', 'Tab', 'Enter'].includes(e.key)) {
                    e.preventDefault();
                }

                if (e.key === 'Enter') {
                    submitPINChange();
                }
            });
        });

        // Focus on first input
        newPinInput.focus();
    }, 100);

    return modal;
}

function validatePINInputs() {
    const newPin = document.getElementById('new-pin')?.value;
    const confirmPin = document.getElementById('confirm-pin')?.value;
    const errorDiv = document.getElementById('pin-error-message');
    const submitBtn = document.getElementById('pin-submit-btn');

    // Clear previous errors
    errorDiv.classList.add('hidden');

    // Check if PINs match and are valid
    if (newPin && confirmPin) {
        if (newPin !== confirmPin) {
            showPINError('PINs do not match');
            return false;
        }

        if (newPin.length !== 4) {
            showPINError('PIN must be exactly 4 digits');
            return false;
        }
    }

    // Enable submit button if both fields are filled and valid
    if (submitBtn) {
        submitBtn.disabled = !(newPin.length === 4 && confirmPin.length === 4 && newPin === confirmPin);
    }

    return true;
}

function showPINError(message) {
    const errorDiv = document.getElementById('pin-error-message');
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.classList.remove('hidden');
    }
}

function submitPINChange() {
    const newPin = document.getElementById('new-pin')?.value;
    const confirmPin = document.getElementById('confirm-pin')?.value;

    // Validate inputs
    if (!newPin || !confirmPin) {
        showPINError('Please enter both PIN fields');
        return;
    }

    if (newPin.length !== 4 || confirmPin.length !== 4) {
        showPINError('PIN must be exactly 4 digits');
        return;
    }

    if (newPin !== confirmPin) {
        showPINError('PINs do not match');
        return;
    }

    // Show loading state
    const submitBtn = document.getElementById('pin-submit-btn');
    const originalText = submitBtn ? submitBtn.innerHTML : '';
    if (submitBtn) {
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Changing PIN...';
        submitBtn.disabled = true;
    }

    // Send PIN change request
    fetch('/api/change-pin', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({
            newPin: newPin
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show success message
            showPINSuccess('PIN changed successfully!');

            // Close modal after delay
            setTimeout(() => {
                closePINChangeModal();
            }, 2000);
        } else {
            showPINError(data.error || 'Failed to change PIN');
        }
    })
    .catch(error => {
        console.error('Error changing PIN:', error);
        showPINError('Error changing PIN: ' + error.message);
    })
    .finally(() => {
        // Restore button state
        if (submitBtn) {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        }
    });
}

function showPINSuccess(message) {
    const contentDiv = document.getElementById('pin-change-content');
    if (contentDiv) {
        contentDiv.innerHTML = `
            <div class="text-center py-8">
                <div class="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100 mb-4">
                    <i class="fas fa-check text-green-600 text-xl"></i>
                </div>
                <h3 class="text-lg font-medium text-gray-900 mb-2">PIN Changed Successfully</h3>
                <p class="text-sm text-gray-500">${message}</p>
                <p class="text-xs text-gray-400 mt-2">This modal will close automatically...</p>
            </div>
        `;
    }
}

function closePINChangeModal() {
    const modal = document.getElementById('pin-change-modal');
    if (modal) {
        modal.remove();
        document.body.style.overflow = 'auto';
    }
}
*/

// Email sending functionality - commented out as requested, stub function provided for compatibility
function sendReservationEmail(reservationId, emailType, buttonElement) {
    // Stub function - no-op since Email Communications section is commented out
    console.log('sendReservationEmail called but disabled - Email Communications functionality is commented out');
    return;
}

/*
// Original function commented out:
function sendReservationEmail(reservationId, emailType, buttonElement) {
    // Find the reservation to get property ID
    const reservation = reservations.find(r => (r.id || r.reservationId) === reservationId);
    if (!reservation) {
        console.error('Reservation not found:', reservationId);
        showReservationMessage('Reservation not found', 'error');
        return;
    }

    const propertyId = reservation.property_id;
    const guestName = getDisplayGuestName(reservation);

    // Email type descriptions
    const emailDescriptions = {
        'welcome': 'Welcome Email',
        'checkin_reminder': 'Check-in Reminder',
        'review_request': 'Review Request'
    };

    const emailDescription = emailDescriptions[emailType] || emailType;

    // Confirm before sending
    if (!confirm(`Send ${emailDescription} to ${guestName}?`)) {
        return;
    }

    // Show loading state on the button
    const button = buttonElement;
    const originalText = button ? button.innerHTML : '';
    if (button) {
        button.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Sending...';
        button.disabled = true;
    }

    // Send email request
    fetch(`/api/property/${propertyId}/reservations/${reservationId}/email/${emailType}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showReservationMessage(`${emailDescription} sent successfully to ${guestName}!`, 'success');
        } else {
            showReservationMessage(data.error || `Failed to send ${emailDescription}`, 'error');
        }
    })
    .catch(error => {
        console.error(`Error sending ${emailType} email:`, error);
        showReservationMessage(`Error sending ${emailDescription}: ` + error.message, 'error');
    })
    .finally(() => {
        // Restore button state
        if (button) {
            button.innerHTML = originalText;
            button.disabled = false;
        }
    });
}
*/

// Load account stats
function loadAccountStats() {
    // Load properties count
    if (typeof properties !== 'undefined' && properties && properties.length > 0) {
        const statsEl = document.getElementById('stats-properties');
        if (statsEl) statsEl.textContent = properties.length;
    }

    // Load active reservations count by fetching from API
    fetch('/api/active-reservations', {
        credentials: 'same-origin'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success && data.reservations) {
            // Filter for active reservations (end date is in the future)
            const activeReservations = data.reservations.filter(r => {
                const endDate = new Date(r.endDate || r.check_out_date || r.checkOutDate);
                return endDate >= new Date();
            });
            const statsEl = document.getElementById('stats-reservations');
            if (statsEl) statsEl.textContent = activeReservations.length;
        }
    })
    .catch(error => {
        console.error('Error loading reservation stats:', error);
        const statsEl = document.getElementById('stats-reservations');
        if (statsEl) statsEl.textContent = '0';
    });
}

// --- Utility Functions ---
function logout() {
    console.log("Attempting logout...");

    // Use the same logout logic as guest dashboard
    // First clear the server-side session
    fetch('/auth/logout', {
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

// Close modal when clicking outside
document.addEventListener('click', function(event) {
    const settingsModal = document.getElementById('settings-modal');

    const reservationModal = document.getElementById('reservation-details-modal');
    const knowledgeModal = document.getElementById('knowledge-modal');

    // Handle settings modal
    if (settingsModal && !settingsModal.classList.contains('hidden')) {
        const modalContent = settingsModal.querySelector('.bg-white');
        if (modalContent && !modalContent.contains(event.target) && !event.target.closest('[onclick*="openSettingsModal"]')) {
            closeSettingsModal();
        }
    }



    // Handle reservation details modal
    if (reservationModal && !reservationModal.classList.contains('hidden')) {
        const modalContent = reservationModal.querySelector('.bg-white');
        if (modalContent && !modalContent.contains(event.target) && !event.target.closest('.reservation-bar')) {
            closeReservationDetailsModal();
        }
    }

    // Knowledge modal should not close on outside click
});

// Handle escape key for modals
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        const settingsModal = document.getElementById('settings-modal');

        const reservationModal = document.getElementById('reservation-details-modal');
        const knowledgeModal = document.getElementById('knowledge-modal');

        if (knowledgeModal && !knowledgeModal.classList.contains('hidden')) {
            // Don't close if edit modal is open or if we're reviewing pending items
            if (knowledgeModal.getAttribute('data-edit-modal-open') !== 'true' && !window.skipPendingItemsCheck) {
                closeKnowledgeModal();
            }
        } else if (reservationModal && !reservationModal.classList.contains('hidden')) {
            closeReservationDetailsModal();
        } else if (settingsModal && !settingsModal.classList.contains('hidden')) {
            closeSettingsModal();

        }
    }
});

// --- Date Utilities (from existing code) ---
window.DateUtils = {
    isReservationActive: function(startDateStr, endDateStr) {
        const today = new Date();
        const startDate = parseDateOnly(startDateStr);
        const endDate = parseDateOnly(endDateStr);
        // Compare dates only (inclusive range)
        return formatDateForCalendar(startDate) <= formatDateForCalendar(today) 
            && formatDateForCalendar(today) <= formatDateForCalendar(endDate);
    },
    
    isReservationUpcoming: function(startDateStr) {
        const today = new Date();
        const startDate = parseDateOnly(startDateStr);
        return formatDateForCalendar(startDate) > formatDateForCalendar(today);
    },
    
    formatDate: function(dateStr) {
        const date = parseDateOnly(dateStr);
        return date.toLocaleDateString('en-US');
    }
};
// --- Export functions for external use ---
window.hostDashboard = {
    showScreen,
    loadProperties,
    addNewProperty,
    manageKnowledge,
    viewReservations,
    togglePropertyStatus,
    openSettingsModal,
    closeSettingsModal,
    logout
};

// Make essential functions globally available for onclick handlers
window.showScreen = showScreen;
window.addNewProperty = addNewProperty;
window.manageKnowledge = manageKnowledge;
window.viewReservations = viewReservations;
window.togglePropertyStatus = togglePropertyStatus;
window.openSettingsModal = openSettingsModal;
window.closeSettingsModal = closeSettingsModal;
window.logout = logout;
window.toggleCalendarView = toggleCalendarView;
window.refreshReservations = refreshReservations;
window.filterCalendarByProperty = filterCalendarByProperty;
// window.filterConversations = filterConversations; // Commented out - Support Center not implemented
// window.refreshSupport = refreshSupport; // Commented out - Support Center not implemented
window.addContactField = addContactField;
window.removeContact = removeContact;
window.saveContacts = saveContacts;

window.navigateCalendar = navigateCalendar;
window.goToToday = goToToday;
window.closeReservationDetailsModal = closeReservationDetailsModal;

// Make functions available for property setup modal
window.openKnowledgeModal = openKnowledgeModal;
window.addContactFieldToModal = addContactFieldToModal;
window.removeContactFromModal = removeContactFromModal;

window.saveReservationDetails = saveReservationDetails;
window.copyToClipboard = copyToClipboard;
window.logout = logout;
window.showSettingsTab = showSettingsTab;
window.resetProfileForm = resetProfileForm;
window.saveProfileSettings = saveProfileSettings;

// Profile Management Functions
window.openSettingsModal = openSettingsModal;
window.closeSettingsModal = closeSettingsModal;
window.saveProfileChanges = saveProfileChanges;
window.updateEmail = updateEmail;
window.updatePhone = updatePhone;
window.verifyEmail = verifyEmail;
window.verifyPhone = verifyPhone;
window.closeVerificationOverlay = closeVerificationOverlay;
window.resendEmailVerification = resendEmailVerification;
window.resendPhoneVerification = resendPhoneVerification;
window.showEmailVerificationModal = showEmailVerificationModal;
window.showPhoneVerificationModal = showPhoneVerificationModal;
window.sendEmailLinkForVerification = sendEmailLinkForVerification;
window.submitPhoneVerification = submitPhoneVerification;

// --- Profile Management Functions ---

// Settings Modal Management
function openSettingsModal() {
    document.getElementById('settings-modal').classList.remove('hidden');
    // Load settings content dynamically
    loadSettingsContent();
    // Add verification overlay to body if it doesn't exist
    if (!document.getElementById('verification-overlay')) {
        const overlay = document.createElement('div');
        overlay.id = 'verification-overlay';
        overlay.className = 'hidden fixed inset-0 bg-black bg-opacity-50 z-50';
        overlay.innerHTML = `
            <div class="flex items-center justify-center min-h-screen p-4" onclick="closeVerificationOverlay()">
                <div class="bg-white rounded-lg shadow-xl max-w-md w-full" onclick="event.stopPropagation()">
                    <div id="verification-content">
                        <!-- Verification content will be loaded here -->
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
    }
}

function closeSettingsModal() {
    document.getElementById('settings-modal').classList.add('hidden');
    closeVerificationOverlay();
}

function resetProfileForm() {
    // Reset form fields to original values from template
    const displayNameField = document.getElementById('profile-display-name');
    const emailField = document.getElementById('profile-email');
    const phoneField = document.getElementById('profile-phone');
    
    // These values come from the template
    if (displayNameField) displayNameField.value = displayNameField.defaultValue;
    if (emailField) emailField.value = emailField.defaultValue;
    if (phoneField) phoneField.value = phoneField.defaultValue;
}

// Profile Changes Management
function saveProfileChanges() {
    const displayName = document.getElementById('profile-display-name').value.trim();
    const email = document.getElementById('profile-email').value.trim();
    const phone = document.getElementById('profile-phone').value.trim();
    
    // Validate inputs
    if (!displayName) {
        showProfileMessage('Display name is required', 'error');
        return;
    }
    
    if (email && !isValidEmail(email)) {
        showProfileMessage('Please enter a valid email address', 'error');
        return;
    }
    
    if (phone && !isValidPhone(phone)) {
        showProfileMessage('Please enter a valid phone number', 'error');
        return;
    }
    
    // Show loading state
    const saveBtn = document.querySelector('button[onclick="saveProfileChanges()"]');
    const originalText = saveBtn.textContent;
    saveBtn.textContent = 'Saving...';
    saveBtn.disabled = true;
    
    // Prepare update data
    const updateData = {
        displayName: displayName
    };
    
    // Only include email/phone if they've changed and are verified
    const currentEmail = document.getElementById('profile-email').defaultValue;
    const currentPhone = document.getElementById('profile-phone').defaultValue;
    
    if (email !== currentEmail) {
        updateData.email = email;
        updateData.emailVerified = false; // New email needs verification
    }
    
    if (phone !== currentPhone) {
        updateData.phoneNumber = phone;
        updateData.phoneVerified = false; // New phone needs verification
    }
    
    // Send update to server
    fetch('/api/profile/update', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(updateData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showProfileMessage('Profile updated successfully', 'success');
            // Update verification statuses
            updateVerificationStatuses(data.user);
            // Update default values
            updateFormDefaults();
            // Refresh user profile in header
            refreshUserProfile();
        } else {
            throw new Error(data.error || 'Failed to update profile');
        }
    })
    .catch(error => {
        console.error('Profile update error:', error);
        showProfileMessage(error.message || 'Failed to update profile', 'error');
    })
    .finally(() => {
        saveBtn.textContent = originalText;
        saveBtn.disabled = false;
    });
}

// Email Management
function updateEmail() {
    const email = document.getElementById('profile-email').value.trim();
    
    if (!email) {
        showProfileMessage('Please enter an email address', 'error');
        return;
    }
    
    if (!isValidEmail(email)) {
        showProfileMessage('Please enter a valid email address', 'error');
        return;
    }
    
    // Show verification button
    document.getElementById('verify-email-btn').style.display = 'inline-block';
    showProfileMessage('Email updated. Please verify your new email address.', 'info');
}

function verifyEmail() {
    const email = document.getElementById('profile-email').value.trim();
    
    if (!email) {
        showProfileMessage('Please enter an email address first', 'error');
        return;
    }
    
    // Show email verification modal
    showVerificationModal('email', email);
}

// Phone Management
function updatePhone() {
    // Get the complete formatted phone number
    let phone;
    if (typeof getCompletePhoneNumber === 'function') {
        phone = getCompletePhoneNumber('settings-phone');
    } else {
        phone = document.getElementById('settings-phone').value.trim();
    }
    
    if (!phone) {
        showProfileMessage('Please enter a phone number', 'error');
        return;
    }
    
    if (!isValidPhone(phone)) {
        showProfileMessage('Please enter a valid phone number', 'error');
        return;
    }
    
    console.log('Updating phone number to:', phone);
    
    // Show verification button
    document.getElementById('verify-phone-btn').style.display = 'inline-block';
    showProfileMessage('Phone number updated. Please verify your new phone number.', 'info');
}

function verifyPhone() {
    // Get the complete formatted phone number
    let phone;
    if (typeof getCompletePhoneNumber === 'function') {
        phone = getCompletePhoneNumber('settings-phone');
    } else {
        phone = document.getElementById('settings-phone').value.trim();
    }
    
    if (!phone) {
        showProfileMessage('Please enter a phone number first', 'error');
        return;
    }
    
    console.log('Verifying phone number:', phone);
    
    // Show phone verification modal with proper SMS sending
    showPhoneVerificationModal(phone);
}

// Verification Modal Management
function showVerificationModal(type, value) {
    const overlay = document.getElementById('verification-overlay');
    const content = document.getElementById('verification-content');
    
    if (type === 'email') {
        content.innerHTML = createEmailVerificationContent(value);
    } else if (type === 'phone') {
        content.innerHTML = createPhoneVerificationContent(value);
    }
    
    overlay.classList.remove('hidden');
    
    // Focus the input field after a short delay to ensure modal is fully rendered
    setTimeout(() => {
        const inputField = type === 'phone' ? 
            document.getElementById('phone-verification-code') : 
            document.getElementById('email-verification-input');
        if (inputField) {
            inputField.focus();
        }
    }, 100);
}

// Wrapper functions for email and phone verification
function showEmailVerificationModal(email, profileData) {
    console.log('Checking email conflicts before verification:', email);
    
    // First check for conflicts before showing modal or sending email
    checkEmailConflict(email)
        .then(result => {
            if (!result.success) {
                showProfileMessage(result.error, 'error');
                // Reset Save button state when conflict detected
                resetSaveButton();
                return;
            }
            
            // No conflict, proceed with verification
            console.log('No conflicts found, proceeding with email verification for:', email);
            
            // First, mark the email as pending verification in the user's profile
            return fetch('/api/profile/verify-email-for-profile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email })
            });
        })
        .then(response => {
            if (!response) return; // Early return from conflict check
            return response.json();
        })
        .then(data => {
            if (!data) return; // Early return from conflict check
            if (data.success) {
                // Now send the email using client-side Firebase
                return sendEmailLinkForVerification(email);
            } else {
                throw new Error(data.error || 'Failed to initiate email verification');
            }
        })
        .then(result => {
            if (!result) return; // Early return from conflict check
            if (result.success) {
                // Show the modal after successfully sending email
                showVerificationModal('email', email);
                showProfileMessage('Verification email sent to ' + email, 'success');
            } else {
                throw new Error(result.error || 'Failed to send verification email');
            }
        })
        .catch(error => {
            console.error('Error in email verification flow:', error);
            showProfileMessage('Error sending verification email: ' + error.message, 'error');
            // Reset Save button state on error
            resetSaveButton();
        });
}

// Client-side email verification using Firebase (same approach as login page)
async function sendEmailLinkForVerification(email) {
    try {
        // Wait for Firebase initialization if needed
        if (typeof window.initializeFirebaseSecurely === 'function') {
            await window.initializeFirebaseSecurely();
        }
        
        // Make sure Firebase is available and initialized
        if (typeof firebase === 'undefined' || !firebase.auth) {
            console.error('Firebase auth not available');
            return { success: false, error: 'Firebase not available' };
        }

        const auth = firebase.auth();
        if (!auth) {
            console.error('Firebase auth not initialized');
            return { success: false, error: 'Firebase auth not initialized' };
        }

        const actionCodeSettings = {
            // URL you want to redirect back to
            url: window.location.origin + '/auth/email-link-signin',
            // This must be true for email link sign-in
            handleCodeInApp: true,
        };

        // Use client-side Firebase to send email (this actually sends emails!)
        await auth.sendSignInLinkToEmail(email, actionCodeSettings);

        // Save the email locally for verification
        window.localStorage.setItem('emailForSignIn', email);

        console.log('Email verification link sent successfully to:', email);
        return { success: true };
    } catch (error) {
        console.error('Error sending email verification link:', error);
        return { success: false, error: error.message };
    }
}

function showPhoneVerificationModal(phone) {
    console.log('Checking phone number conflicts before verification:', phone);
    
    // First check for conflicts before showing modal or sending SMS
    checkPhoneConflict(phone)
        .then(result => {
            if (!result.success) {
                showProfileMessage(result.error, 'error');
                // Reset Save button state when conflict detected
                resetSaveButton();
                return;
            }
            
            // No conflict, proceed with verification
            console.log('No conflicts found, proceeding with Firebase phone verification for:', phone);
            
            // Check if Firebase is available
            if (typeof firebase === 'undefined' || !firebase.auth) {
                showProfileMessage('Firebase not available. Using fallback verification.', 'error');
                return;
            }
            
            // Show the modal first so the reCAPTCHA container exists
            showVerificationModal('phone', phone);
            
            // Wait a moment for the modal to render, then initialize Firebase verification
            setTimeout(() => {
                initializeFirebasePhoneVerification(phone);
            }, 100);
        })
        .catch(error => {
            console.error('Error checking phone conflict:', error);
            showProfileMessage('Error checking phone number: ' + error.message, 'error');
            // Reset Save button state on error
            resetSaveButton();
        });
}

// Check for email address conflicts before verification
function checkEmailConflict(email) {
    return fetch('/api/profile/check-email-conflict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.error || `Server error: ${response.status}`);
            });
        }
        return response.json();
    });
}

// Check for phone number conflicts before verification
function checkPhoneConflict(phone) {
    return fetch('/api/profile/check-phone-conflict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phoneNumber: phone })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.error || `Server error: ${response.status}`);
            });
        }
        return response.json();
    });
}
function initializeFirebasePhoneVerification(phone) {
    console.log('Initializing Firebase phone verification for:', phone);
    
    try {
        // Clean up any existing verifier
        if (window.phoneVerificationRecaptcha) {
            window.phoneVerificationRecaptcha.clear();
            window.phoneVerificationRecaptcha = null;
        }
        
        // Create reCAPTCHA verifier (now that the container exists)
        window.phoneVerificationRecaptcha = new firebase.auth.RecaptchaVerifier('phone-recaptcha-container', {
            'size': 'invisible',
            'callback': function(response) {
                console.log('reCAPTCHA solved for phone verification');
            },
            'expired-callback': function() {
                console.log('reCAPTCHA expired for phone verification');
                showProfileMessage('Verification expired. Please try again.', 'error');
            }
        });
        
        // Send verification code using Firebase
        firebase.auth().signInWithPhoneNumber(phone, window.phoneVerificationRecaptcha)
            .then((confirmationResult) => {
                console.log('Firebase SMS sent successfully');
                // Store the confirmation result for later verification
                window.phoneConfirmationResult = confirmationResult;
                showProfileMessage('Verification code sent to ' + phone, 'success');
            })
            .catch((error) => {
                console.error('Firebase phone verification error:', error);
                showProfileMessage('Error sending verification code: ' + error.message, 'error');
                
                // Reset reCAPTCHA on error
                if (window.phoneVerificationRecaptcha) {
                    window.phoneVerificationRecaptcha.clear();
                    window.phoneVerificationRecaptcha = null;
                }
                
                // Close modal on error
                closeVerificationOverlay();
            });
    } catch (error) {
        console.error('Error initializing Firebase phone verification:', error);
        showProfileMessage('Error initializing verification: ' + error.message, 'error');
        closeVerificationOverlay();
    }
}

function closeVerificationOverlay() {
    document.getElementById('verification-overlay').classList.add('hidden');
}

// Verification Content Creators
function createEmailVerificationContent(email) {
    return `
        <div class="bg-persian-green text-white p-6 rounded-t-lg">
            <div class="flex items-center justify-between">
                <h3 class="text-xl font-semibold">Verify Email Address</h3>
                <button onclick="closeVerificationOverlay()" class="text-white hover:text-gray-200">
                    <i class="fas fa-times text-xl"></i>
                </button>
            </div>
        </div>
        <div class="p-6">
            <div class="text-center mb-6">
                <i class="fas fa-envelope text-4xl text-saffron mb-4"></i>
                <h4 class="text-lg font-semibold text-dark-purple mb-2">Check Your Email</h4>
                <p class="text-gray-600 mb-4">We've sent a verification link to:</p>
                <p class="font-semibold text-dark-purple">${email}</p>
            </div>
            <div class="space-y-4">
                <div class="bg-light-cyan rounded-lg p-4">
                    <p class="text-sm text-dark-purple">
                        <i class="fas fa-info-circle mr-2"></i>
                        Click the link in your email to verify your email address. The link will expire in 1 hour.
                    </p>
                </div>
                <div class="flex justify-between">
                    <button onclick="resendEmailVerification('${email}')" 
                            class="px-4 py-2 text-persian-green border border-persian-green rounded-lg hover:bg-persian-green hover:text-white transition-colors">
                        Resend Email
                    </button>
                    <button onclick="closeVerificationOverlay()" 
                            class="px-4 py-2 bg-persian-green text-white rounded-lg hover:bg-persian-green/90 transition-colors">
                        Done
                    </button>
                </div>
            </div>
        </div>
    `;
}

function createPhoneVerificationContent(phone) {
    return `
        <div class="bg-persian-green text-white p-6 rounded-t-lg">
            <div class="flex items-center justify-between">
                <h3 class="text-xl font-semibold">Verify Phone Number</h3>
                <button onclick="closeVerificationOverlay()" class="text-white hover:text-gray-200">
                    <i class="fas fa-times text-xl"></i>
                </button>
            </div>
        </div>
        <div class="p-6">
            <div class="text-center mb-6">
                <i class="fas fa-mobile-alt text-4xl text-saffron mb-4"></i>
                <h4 class="text-lg font-semibold text-dark-purple mb-2">Enter Verification Code</h4>
                <p class="text-gray-600 mb-4">We've sent a 6-digit code to:</p>
                <p class="font-semibold text-dark-purple">${phone}</p>
            </div>
            <div class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-dark-purple mb-2">Verification Code</label>
                    <input type="text" id="phone-verification-code" maxlength="6" 
                           class="w-full px-3 py-2 border border-gray-300 rounded-lg text-center text-lg font-mono focus:outline-none focus:ring-2 focus:ring-persian-green focus:border-transparent"
                           placeholder="000000">
                </div>
                <div class="flex justify-between">
                    <button onclick="resendPhoneVerification('${phone}')" 
                            class="px-4 py-2 text-persian-green border border-persian-green rounded-lg hover:bg-persian-green hover:text-white transition-colors">
                        Resend Code
                    </button>
                    <button onclick="submitPhoneVerification('${phone}')" 
                            class="px-4 py-2 bg-persian-green text-white rounded-lg hover:bg-persian-green/90 transition-colors">
                        Verify
                    </button>
                </div>
            </div>
            <!-- Hidden reCAPTCHA container for Firebase phone verification -->
            <div id="phone-recaptcha-container" style="display: none;"></div>
        </div>
    `;
}

// Verification Actions
function resendEmailVerification(email) {
    fetch('/api/profile/send-email-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showProfileMessage('Verification email sent', 'success');
        } else {
            throw new Error(data.error || 'Failed to send verification email');
        }
    })
    .catch(error => {
        showProfileMessage(error.message, 'error');
    });
}

function resendPhoneVerification(phone) {
    console.log('Resending Firebase phone verification for:', phone);
    
    // Check if Firebase is available
    if (typeof firebase === 'undefined' || !firebase.auth) {
        showProfileMessage('Firebase not available for resend.', 'error');
        return;
    }
    
    // Clear existing confirmation result
    window.phoneConfirmationResult = null;
    
    // Re-initialize Firebase verification (modal is already open)
    initializeFirebasePhoneVerification(phone);
}

function submitPhoneVerification(phone) {
    const code = document.getElementById('phone-verification-code').value.trim();
    
    if (!code || code.length !== 6) {
        showProfileMessage('Please enter a valid 6-digit code', 'error');
        return;
    }
    
    console.log('Submitting Firebase phone verification:', { phone, code });
    
    // Check if we have the confirmation result from Firebase
    if (!window.phoneConfirmationResult) {
        showProfileMessage('Verification session expired. Please try again.', 'error');
        closeVerificationOverlay();
        return;
    }
    
    // Verify the code with Firebase
    window.phoneConfirmationResult.confirm(code)
        .then((result) => {
            console.log('Firebase phone verification successful:', result.user.uid);
            
            // Get the ID token to verify with backend
            return result.user.getIdToken(true);
        })
        .then((idToken) => {
            console.log('Got Firebase ID token, updating profile...');
            
            // Update the user's profile with the verified phone number
            return fetch('/api/profile/update-verified-phone', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + idToken
                },
                body: JSON.stringify({ phoneNumber: phone })
            });
        })
        .then(response => {
            if (!response.ok) {
                // Handle HTTP error status codes
                return response.json().then(data => {
                    throw new Error(data.error || `Server error: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                showProfileMessage('Phone number verified successfully', 'success');
                updateVerificationStatuses(data.user);
                closeVerificationOverlay();
                
                // Clean up
                window.phoneConfirmationResult = null;
                if (window.phoneVerificationRecaptcha) {
                    window.phoneVerificationRecaptcha.clear();
                    window.phoneVerificationRecaptcha = null;
                }
                
                // Reset Save button state
                resetSaveButton();
            } else {
                throw new Error(data.error || 'Failed to update profile');
            }
        })
        .catch((error) => {
            console.error('Phone verification error:', error);
            showProfileMessage('Verification failed: ' + error.message, 'error');
            // Reset Save button state on error
            resetSaveButton();
        });
}

// Utility Functions
function resetSaveButton() {
    const saveBtn = document.querySelector('button[onclick="saveProfileSettings()"]');
    if (saveBtn) {
        saveBtn.innerHTML = '<i class="fas fa-save mr-2"></i>Save Changes';
        saveBtn.disabled = false;
    }
}

function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

function isValidPhone(phone) {
    // Basic phone validation - adjust as needed
    const phoneRegex = /^[\+]?[1-9][\d]{1,14}$/;
    return phoneRegex.test(phone.replace(/[\s\-\(\)]/g, ''));
}

function showProfileMessage(message, type) {
    // Create or update message element
    let messageEl = document.getElementById('profile-message');
    if (!messageEl) {
        messageEl = document.createElement('div');
        messageEl.id = 'profile-message';
        messageEl.className = 'mb-4 p-3 rounded-lg';
        document.getElementById('settings-content').insertBefore(messageEl, document.getElementById('settings-content').firstChild);
    }
    
    // Set message content and styling
    messageEl.textContent = message;
    messageEl.className = 'mb-4 p-3 rounded-lg ';
    
    if (type === 'success') {
        messageEl.className += 'bg-green-50 border border-green-200 text-green-700';
    } else if (type === 'error') {
        messageEl.className += 'bg-red-50 border border-red-200 text-red-700';
    } else {
        messageEl.className += 'bg-blue-50 border border-blue-200 text-blue-700';
    }
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        if (messageEl && messageEl.parentNode) {
            messageEl.parentNode.removeChild(messageEl);
        }
    }, 5000);
}

function updateVerificationStatuses(userData) {
    // Update email verification status
    const emailStatus = document.getElementById('email-verification-status');
    if (emailStatus) {
        if (userData.emailVerified) {
            emailStatus.innerHTML = `
                <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                    <i class="fas fa-check-circle mr-1"></i>
                    Verified
                </span>
            `;
        } else {
            emailStatus.innerHTML = `
                <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                    <i class="fas fa-exclamation-circle mr-1"></i>
                    Pending
                </span>
            `;
        }
    }
    
    // Update phone verification status
    const phoneStatus = document.getElementById('phone-verification-status');
    if (phoneStatus) {
        if (userData.phoneVerified) {
            phoneStatus.innerHTML = `
                <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                    <i class="fas fa-check-circle mr-1"></i>
                    Verified
                </span>
            `;
        } else {
            phoneStatus.innerHTML = `
                <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                    <i class="fas fa-exclamation-circle mr-1"></i>
                    Pending
                </span>
            `;
        }
    }
}

function updateFormDefaults() {
    // Update default values for form reset
    const displayNameField = document.getElementById('profile-display-name');
    const emailField = document.getElementById('profile-email');
    const phoneField = document.getElementById('profile-phone');
    
    if (displayNameField) displayNameField.defaultValue = displayNameField.value;
    if (emailField) emailField.defaultValue = emailField.value;
    if (phoneField) phoneField.defaultValue = phoneField.value;
}

// PIN functions are commented out - removed from window exports
// window.changePIN = changePIN;
// window.closePINChangeModal = closePINChangeModal;
// window.submitPINChange = submitPINChange;
window.sendReservationEmail = sendReservationEmail;
window.closeKnowledgeModal = closeKnowledgeModal;
window.addKnowledgeItem = addKnowledgeItem;
window.openFullKnowledgeManager = openFullKnowledgeManager;
window.refreshKnowledgeItems = refreshKnowledgeItems;
window.approveKnowledgeItem = approveKnowledgeItem;
window.editKnowledgeItem = editKnowledgeItem;
window.addBasicAmenity = addBasicAmenity;
window.saveNewBasicAmenity = saveNewBasicAmenity;
window.cancelNewBasicAmenity = cancelNewBasicAmenity;
window.updateBasicAmenity = updateBasicAmenity;
window.removeBasicAmenity = removeBasicAmenity;
window.addAppliance = addAppliance;
window.saveNewAppliance = saveNewAppliance;
window.cancelNewAppliance = cancelNewAppliance;
window.updateApplianceField = updateApplianceField;
window.removeAppliance = removeAppliance;
window.showPropertyTab = showPropertyTab;
window.expandKnowledgeItem = expandKnowledgeItem;
window.rejectKnowledgeItem = rejectKnowledgeItem;
window.deleteKnowledgeItem = deleteKnowledgeItem;
// Guard export for optional helper
if (typeof bulkApproveItems === 'function') {
    window.bulkApproveItems = bulkApproveItems;
} else {
    window.bulkApproveItems = function () {
        console.warn('bulkApproveItems is not available');
    };
}
window.viewConversations = viewConversations;
window.deleteProperty = deleteProperty;
window.deleteNewProperty = deleteNewProperty;
window.closeAddKnowledgeModal = closeAddKnowledgeModal;
window.openPropertyImportModal = openPropertyImportModal;
window.closePropertyImportModal = closePropertyImportModal;
window.loadPropertyImportStep = loadPropertyImportStep;
window.showUrlInputStep = showUrlInputStep;
window.showSuccessMessage = showSuccessMessage;
window.showErrorMessage = showErrorMessage;

function showSuccessMessage(message) {
    // Create and show success toast
    const toast = document.createElement('div');
    toast.className = 'fixed top-4 right-4 bg-green-500 text-white px-6 py-3 rounded-lg shadow-lg z-[100] transform translate-x-full transition-transform duration-300';
    toast.innerHTML = `
        <div class="flex items-center">
            <i class="fas fa-check-circle mr-2"></i>
            <span>${message}</span>
        </div>
    `;

    document.body.appendChild(toast);

    // Animate in
    setTimeout(() => {
        toast.classList.remove('translate-x-full');
    }, 100);

    // Remove after 3 seconds
    setTimeout(() => {
        toast.classList.add('translate-x-full');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, 3000);
}

function showErrorMessage(message) {
    // Create and show error toast
    const toast = document.createElement('div');
    toast.className = 'fixed top-4 right-4 bg-red-500 text-white px-6 py-3 rounded-lg shadow-lg z-[100] transform translate-x-full transition-transform duration-300';
    toast.innerHTML = `
        <div class="flex items-center">
            <i class="fas fa-exclamation-circle mr-2"></i>
            <span>${message}</span>
        </div>
    `;

    document.body.appendChild(toast);

    // Animate in
    setTimeout(() => {
        toast.classList.remove('translate-x-full');
    }, 100);

    // Remove after 5 seconds (longer for errors)
    setTimeout(() => {
        toast.classList.add('translate-x-full');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, 5000);
}
// Enhanced progress tracking functions

function startActivityIconRotation() {
    const icons = [
        { id: 'activity-icon-1', icon: 'fas fa-coffee', color: 'text-amber-600' },
        { id: 'activity-icon-2', icon: 'fas fa-dumbbell', color: 'text-blue-600' },
        { id: 'activity-icon-3', icon: 'fas fa-heart', color: 'text-pink-600' }
    ];

    progressState.activityIconInterval = setInterval(() => {
        // Reset all icons to default state
        icons.forEach(iconData => {
            const element = document.getElementById(iconData.id);
            if (element) {
                element.className = `${iconData.icon} ${iconData.color}`;
            }
        });

        // Highlight current icon
        const currentIcon = icons[progressState.activityIconIndex];
        const element = document.getElementById(currentIcon.id);
        if (element) {
            element.className = `${currentIcon.icon} ${currentIcon.color} animate-bounce text-lg`;
        }

        progressState.activityIconIndex = (progressState.activityIconIndex + 1) % icons.length;
    }, 2000);
}

function initializeProgressTracking(totalProperties) {
    progressState.totalProperties = totalProperties;
    progressState.currentProperty = 0;
    updateProgressDisplay();
}
function updateProgressDisplay() {
    const progressBar = document.getElementById('progress-bar');
    const progressPercentage = document.getElementById('progress-percentage');
    const progressCurrent = document.getElementById('progress-current');
    const progressStatus = document.getElementById('progress-status');
    const progressDetail = document.getElementById('progress-detail');

    if (!progressBar) return;

    const percentage = progressState.totalProperties > 0
        ? Math.round((progressState.currentProperty / progressState.totalProperties) * 100)
        : 0;

    progressBar.style.width = `${percentage}%`;

    if (progressPercentage) {
        progressPercentage.textContent = `${percentage}%`;
    }

    if (progressCurrent) {
        progressCurrent.textContent = `${progressState.currentProperty}`;
    }

    if (progressStatus) {
        if (progressState.currentProperty === 0) {
            progressStatus.textContent = `Preparing to import ${progressState.totalProperties} ${progressState.totalProperties === 1 ? 'property' : 'properties'}...`;
        } else if (progressState.currentProperty < progressState.totalProperties) {
            progressStatus.textContent = `Processing property ${progressState.currentProperty} of ${progressState.totalProperties}`;
        } else {
            progressStatus.textContent = `Finalizing import of ${progressState.totalProperties} ${progressState.totalProperties === 1 ? 'property' : 'properties'}...`;
        }
    }

    if (progressDetail) {
        progressDetail.textContent = progressState.currentStep || 'Initializing extraction process...';
    }
}

function updateImportProgress(step, propertyIndex = null) {
    if (propertyIndex !== null) {
        progressState.currentProperty = propertyIndex;
    }

    progressState.currentStep = step;
    updateProgressDisplay();
}

function stopActivityIconRotation() {
    if (progressState.activityIconInterval) {
        clearInterval(progressState.activityIconInterval);
        progressState.activityIconInterval = null;
    }
}

function startProgressSimulation(totalProperties) {
    // Simulate progress with realistic steps and timing (based on actual ~5 minutes per property)
    const steps = [
        { delay: 3000, step: 'Connecting to Airbnb and loading page...', progress: 0.05 },
        { delay: 8000, step: 'Parsing property structure and content...', progress: 0.15 },
        { delay: 45000, step: 'Extracting amenities with location grouping...', progress: 0.35 },
        { delay: 60000, step: 'Opening house rules modals and extracting details...', progress: 0.55 },
        { delay: 45000, step: 'Processing safety information and descriptions...', progress: 0.70 },
        { delay: 30000, step: 'Organizing data and creating knowledge items...', progress: 0.85 },
        { delay: 15000, step: 'Saving property to database...', progress: 0.95 }
    ];

    let currentStepIndex = 0;
    let currentPropertyIndex = 1;

    function simulateNextStep() {
        if (currentStepIndex < steps.length) {
            const step = steps[currentStepIndex];
            const propertyProgress = (currentPropertyIndex - 1) / totalProperties;
            const stepProgress = step.progress / totalProperties;
            const totalProgress = propertyProgress + stepProgress;

            // Update progress display
            progressState.currentProperty = Math.min(currentPropertyIndex, totalProperties);
            progressState.currentStep = totalProperties > 1
                ? `Property ${currentPropertyIndex}: ${step.step}`
                : step.step;

            updateProgressDisplay();

            // Update progress bar to reflect actual progress
            const progressBar = document.getElementById('progress-bar');
            if (progressBar) {
                const percentage = Math.min(Math.round(totalProgress * 100), 95);
                progressBar.style.width = `${percentage}%`;

                // Debug log for troubleshooting
                console.log(`Progress update: ${percentage}% (${currentPropertyIndex}/${totalProperties}, step ${currentStepIndex})`);

                const progressPercentage = document.getElementById('progress-percentage');
                if (progressPercentage) {
                    progressPercentage.textContent = `${percentage}%`;
                }
            }

            currentStepIndex++;

            // Move to next property after completing all steps
            if (currentStepIndex >= steps.length && currentPropertyIndex < totalProperties) {
                currentPropertyIndex++;
                currentStepIndex = 0;
            }

            // Continue simulation if not completed
            if (currentPropertyIndex <= totalProperties) {
                setTimeout(simulateNextStep, step.delay);
            }
        }
    }

    // Start simulation
    setTimeout(simulateNextStep, 500);
}

window.selectAllListings = selectAllListings;
window.handleCheckboxChange = handleCheckboxChange;
window.toggleListingSelection = toggleListingSelection;
window.importSelectedProperties = importSelectedProperties;
window.refreshUserProfile = refreshUserProfile;
window.updateImportProgress = updateImportProgress;
window.startProgressSimulation = startProgressSimulation;