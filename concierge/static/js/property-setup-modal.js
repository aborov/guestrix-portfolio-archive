/**
 * Property Setup Modal JavaScript
 * Handles the 5-step property setup process for new imported properties
 */

class PropertySetupModal {
    constructor() {
        this.currentStep = 1;
        this.totalSteps = 5;
        this.propertyId = null;
        this.propertyData = {};
        this.isNavigating = false; // Prevent concurrent step navigation while async work is in flight
        this.categorizationApplied = false; // Flag to prevent duplicate categorization
        this.propertyFactsAutoSaveTimeout = null; // Timeout for property facts auto-save
        this.emergencyInfoAutoSaveTimeout = null; // Timeout for emergency info auto-save
        this.houseRulesAutoSaveTimeout = null; // Timeout for house rules auto-save
        this.setupData = {
            basicInfo: {},
            houseRules: [],
            emergencyInfo: [],
            propertyFacts: [],
            reviewData: {}
        };

        this.stepNames = [
            'Basic Information',
            'House Rules',
            'Emergency Information',
            'Other Information',
            'Review and Approve'
        ];

        this.stepIcons = [
            'fa-info-circle',
            'fa-gavel',
            'fa-exclamation-triangle',
            'fa-clipboard-list',
            'fa-check-circle'
        ];
    }

    // iCal URL validation function
    validateICalUrl(url) {
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

    open(propertyId, propertyData) {
        this.propertyId = propertyId;
        this.propertyData = propertyData;
        this.currentStep = 1;
        this.categorizationApplied = false; // Reset categorization flag for new property

        // Debug logging
        console.log('Opening Property Setup Modal');
        console.log('Property ID:', propertyId);
        console.log('Property Data:', propertyData);
        console.log('Property amenities:', propertyData?.amenities);

        this.createModal();

        // Load any existing setup progress
        this.loadSetupProgress().then(() => {
            this.loadStep(1);
        });
    }

    createModal() {
        // Remove existing modal if any
        const existingModal = document.getElementById('property-setup-modal');
        if (existingModal) {
            existingModal.remove();
        }

        // Create modal
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-75 z-[90] flex items-center justify-center p-4';
        modal.id = 'property-setup-modal';

        modal.innerHTML = `
            <div class="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[95vh] overflow-hidden">
                <!-- Header -->
                <div class="p-6 text-white" style="background: linear-gradient(to right, #2a9d8f, #e9c46a);">
                    <div class="flex items-center justify-between">
                        <div>
                            <h3 class="text-xl font-semibold text-white">
                                <i class="fas fa-cog mr-2"></i>Property Setup
                            </h3>
                            <p class="text-white opacity-90 text-sm mt-1">${this.propertyData.name || 'New Property'}</p>
                        </div>
                        <button onclick="propertySetupModal.close()" class="text-white hover:text-gray-200">
                            <i class="fas fa-times text-xl"></i>
                        </button>
                    </div>
                    
                    <!-- Progress Bar -->
                    <div class="mt-4">
                        <div class="flex items-center justify-between text-sm mb-2 text-white">
                            <span>Step ${this.currentStep} of ${this.totalSteps}</span>
                            <span>${Math.round((this.currentStep / this.totalSteps) * 100)}% Complete</span>
                        </div>
                        <div class="w-full bg-white/20 rounded-full h-2">
                            <div class="bg-white rounded-full h-2 transition-all duration-300" 
                                 style="width: ${(this.currentStep / this.totalSteps) * 100}%"></div>
                        </div>
                        <div class="flex justify-between text-xs mt-2 text-white">
                            ${this.stepNames.map((name, index) =>
                                `<span class="${index + 1 <= this.currentStep ? 'font-medium opacity-100' : 'opacity-80'}">
                                    <span class="step-progress-text" style="display: inline;">${name}</span>
                                    <i class="fas ${this.stepIcons[index]} step-progress-icon" style="display: none;" title="${name}"></i>
                                </span>`
                            ).join('')}
                        </div>
                        <style>
                            @media (max-width: 500px) {
                                #property-setup-modal .step-progress-text { display: none !important; }
                                #property-setup-modal .step-progress-icon { display: inline-block !important; }
                                #property-setup-modal .btn-text { display: none !important; }
                            }
                        </style>
                    </div>
                </div>

                <!-- Content -->
                <div class="p-6 overflow-y-auto" id="setup-step-content" style="max-height: calc(90vh - 220px);">
                    <!-- Content will be loaded here -->
                </div>

                <!-- Footer -->
                <div class="modal-footer bg-gray-50 px-6 py-3 flex justify-between items-center border-t">
                    <button onclick="propertySetupModal.previousStep()"
                            id="prev-btn"
                            class="px-3 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors ${this.currentStep === 1 ? 'opacity-50 cursor-not-allowed' : ''}"
                            ${this.currentStep === 1 ? 'disabled' : ''}>
                        <i class="fas fa-arrow-left mr-2"></i><span class="btn-text">Previous</span>
                    </button>

                    <div id="step-indicator" class="text-sm text-gray-600">
                        Step ${this.currentStep} of ${this.totalSteps}: ${this.stepNames[this.currentStep - 1]}
                    </div>

                    <button onclick="propertySetupModal.nextStep()"
                            id="next-btn"
                            class="px-3 py-2 bg-persian-green text-white rounded-lg hover:bg-persian-green/90 transition-colors">
                        <span class="btn-text">${this.currentStep === this.totalSteps ? 'Complete Setup' : 'Next'}</span>
                        <i class="fas ${this.currentStep === this.totalSteps ? 'fa-check' : 'fa-arrow-right'} ml-2"></i>
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        document.body.style.overflow = 'hidden';

        // Apply responsive behavior immediately
        this.applyResponsiveStyles();

        // Add resize listener for orientation changes
        this.resizeListener = () => this.applyResponsiveStyles();
        window.addEventListener('resize', this.resizeListener);

        // Do not close on outside click
    }

    applyResponsiveStyles() {
        // Force responsive behavior with JavaScript
        const isNarrowScreen = window.innerWidth <= 500;
        console.log('Screen width:', window.innerWidth, 'Is narrow:', isNarrowScreen);

        const stepTexts = document.querySelectorAll('#property-setup-modal .step-progress-text');
        const stepIcons = document.querySelectorAll('#property-setup-modal .step-progress-icon');
        const btnTexts = document.querySelectorAll('#property-setup-modal .btn-text');
        const stepIndicator = document.getElementById('step-indicator');

        if (isNarrowScreen) {
            // Hide text, show icons
            stepTexts.forEach(el => {
                el.style.display = 'none';
                el.style.visibility = 'hidden';
            });
            stepIcons.forEach(el => {
                el.style.display = 'inline-block';
                el.style.visibility = 'visible';
            });
            btnTexts.forEach(el => {
                el.style.display = 'none';
                el.style.visibility = 'hidden';
            });
            // Hide step indicator completely on narrow screens
            if (stepIndicator) {
                stepIndicator.style.display = 'none';
                stepIndicator.style.visibility = 'hidden';
            }
        } else {
            // Show text, hide icons
            stepTexts.forEach(el => {
                el.style.display = 'inline';
                el.style.visibility = 'visible';
            });
            stepIcons.forEach(el => {
                el.style.display = 'none';
                el.style.visibility = 'hidden';
            });
            btnTexts.forEach(el => {
                el.style.display = 'inline';
                el.style.visibility = 'visible';
            });
            // Show step indicator on wider screens
            if (stepIndicator) {
                stepIndicator.style.display = 'block';
                stepIndicator.style.visibility = 'visible';
            }
        }
    }

    async loadSetupProgress() {
        try {
            // First, try to fetch the latest property data from server to get any saved setup progress
            console.log('Loading setup progress from server...');

            const response = await fetch(`/api/properties/${this.propertyId}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'same-origin'
            });

            if (response.ok) {
                const result = await response.json();
                if (result.success && result.property) {
                    // Update property data with latest from server
                    this.propertyData = result.property;
                    console.log('✅ Loaded latest property data from server');
                }
            } else {
                console.warn('Failed to fetch latest property data, using cached data');
            }

            // Load setup progress from the (now updated) property data
            if (this.propertyData) {
                // Load basic information from property data
                this.setupData.basicInfo = {
                    name: this.propertyData.name || '',
                    address: this.propertyData.address || '',
                    description: this.propertyData.description || '',
                    icalUrl: this.propertyData.icalUrl || '',
                    checkInTime: this.propertyData.checkInTime || '15:00',
                    checkOutTime: this.propertyData.checkOutTime || '11:00',
                    wifiDetails: this.propertyData.wifiDetails || { network: '', password: '' },
                    amenities: this.propertyData.amenities || {}
                };

                // Load house rules from property data (including custom rules)
                if (this.propertyData.houseRules) {
                    this.setupData.houseRules = this.propertyData.houseRules;
                    console.log('✅ Loaded house rules from server:', this.setupData.houseRules.length);
                }

                // Load emergency info from property data (including custom items)
                if (this.propertyData.emergencyInfo) {
                    this.setupData.emergencyInfo = this.propertyData.emergencyInfo;
                    this.currentEmergencyInfo = this.propertyData.emergencyInfo;
                    console.log('✅ Loaded emergency info from server:', this.setupData.emergencyInfo.length);
                }

                // Load property facts from property data (including custom facts)
                if (this.propertyData.propertyFacts) {
                    this.setupData.propertyFacts = this.propertyData.propertyFacts;
                    console.log('✅ Loaded property facts from server:', this.setupData.propertyFacts.length);
                }

                console.log('📊 Loaded setup progress summary:', {
                    basicInfo: this.setupData.basicInfo ? 'loaded' : 'empty',
                    wifiNetwork: this.setupData.basicInfo?.wifiDetails?.network || 'none',
                    houseRules: this.setupData.houseRules?.length || 0,
                    emergencyInfo: this.setupData.emergencyInfo?.length || 0,
                    propertyFacts: this.setupData.propertyFacts?.length || 0
                });
            }
        } catch (error) {
            console.error('Error loading setup progress:', error);
            // Fallback to using cached property data if server fetch fails
            if (this.propertyData) {
                console.log('Using cached property data as fallback');
                this.setupData.basicInfo = {
                    name: this.propertyData.name || '',
                    address: this.propertyData.address || '',
                    description: this.propertyData.description || '',
                    icalUrl: this.propertyData.icalUrl || '',
                    checkInTime: this.propertyData.checkInTime || '15:00',
                    checkOutTime: this.propertyData.checkOutTime || '11:00',
                    wifiDetails: this.propertyData.wifiDetails || { network: '', password: '' },
                    amenities: this.propertyData.amenities || {}
                };
            }
        }
    }

    loadStep(stepNumber) {
        // Clamp to valid bounds to avoid overflow/underflow from rapid clicks
        const clampedStep = Math.max(1, Math.min(stepNumber, this.totalSteps));
        this.currentStep = clampedStep;
        const content = document.getElementById('setup-step-content');
        
        switch (stepNumber) {
            case 1:
                this.loadBasicInformationStep(content);
                break;
            case 2:
                this.loadHouseRulesStep(content);
                break;
            case 3:
                this.loadEmergencyInformationStep(content);
                break;
            case 4:
                this.loadPropertyFactsStep(content);
                break;
            case 5:
                this.loadReviewAndApproveStep(content);
                break;
        }
        
        this.updateProgressBar();
        this.updateNavigationButtons();
    }

    loadBasicInformationStep(content) {
		// Determine address value to display: prefer a valid typed/saved value, otherwise suppress neighborhood-like imports
		const typedCandidate = (this.setupData.basicInfo?.address || '').trim();
		const hasTypedValidAddress = !!typedCandidate && !this.isLikelyNeighborhoodOnly(typedCandidate);
		const savedAddress = (this.propertyData?.address || '').trim();
		const savedLooksLikeNeighborhood = !!savedAddress && this.isLikelyNeighborhoodOnly(savedAddress);
		const addressInputValue = hasTypedValidAddress
			? typedCandidate
			: (savedLooksLikeNeighborhood ? '' : savedAddress);
		const importedNeighborhoodLabel = (!hasTypedValidAddress && savedLooksLikeNeighborhood) ? savedAddress : '';

		content.innerHTML = `
            <div>
                <div class="mb-6">
                    <h4 class="text-lg font-semibold text-dark-purple mb-2">
                        <i class="fas fa-info-circle text-persian-green mr-2"></i>
                        Basic Property Information
                    </h4>
                    <p class="text-gray-600">Review and edit the basic information about your property. Please take your time doing it. Providing detailed and accurate information will help us provide better responses to your guests.</p>
                </div>

                <div class="space-y-6">
                    <!-- Property Name -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">
                            Property Name <span class="text-red-500">*</span>
                        </label>
                        <input type="text"
                               id="property-name"
                               value="${this.setupData.basicInfo?.name || this.propertyData.name || ''}"
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-persian-green focus:border-persian-green"
                               placeholder="Enter property name"
                               required>
                    </div>

                    <!-- Property Address -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">
                            Address <span class="text-red-500">*</span>
                            <span class="ml-2 text-xs text-blue-600 hover:underline cursor-pointer"
                                  data-tooltip="For legal reasons we only retrieve listing information that is publicly available"
                                  onclick="propertySetupModal.toggleLegalTooltip(this)">
                                Why is this not retrieved from my listing?
                            </span>
                        </label>
                        <input type="text"
                               id="property-address"
					       value="${addressInputValue}"
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-persian-green focus:border-persian-green"
					       placeholder="Enter street address"
                               required>
                        <p class="text-sm text-gray-500 mt-1">
                            <i class="fas fa-info-circle text-blue-500 mr-1"></i>
                            Providing an accurate address enables answers based on your property's location.
                            Examples: "What restaurants are nearby?" or "How do I get to downtown?"
                        </p>
						${importedNeighborhoodLabel ? `
							<div class="text-sm text-gray-600 mt-2">
								<span class="inline-flex items-center px-2 py-1 rounded bg-gray-100 text-gray-800">
									<i class="fas fa-map-marker-alt mr-1"></i>
									Imported location: ${importedNeighborhoodLabel}
								</span>
								<div class="text-xs text-gray-500 mt-1">This looks like a neighborhood from your listing. Please enter the full street address above.</div>
							</div>
						` : ''}
                    </div>

                    <!-- iCal URL -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">
                            iCal URL (Reservation Sync) <span class="text-red-500">*</span>
                            <span class="ml-2 text-xs text-blue-600 hover:underline cursor-pointer"
                                  data-tooltip="For legal reasons we only retrieve listing information that is publicly available"
                                  onclick="propertySetupModal.toggleLegalTooltip(this)">
                                Why is this not retrieved from my listing?
                            </span>
                        </label>
                        <input type="url"
                               id="ical-url"
                               value="${this.propertyData.icalUrl || ''}"
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-persian-green focus:border-persian-green"
                               placeholder="https://www.airbnb.com/calendar/ical/..."
                               required>
                        <p class="text-sm text-gray-500 mt-1">
                            <i class="fas fa-info-circle text-blue-500 mr-1"></i>
                            Add your Airbnb calendar export URL to automatically sync reservations.
                            Find this in your Airbnb listing → Availability → Find more availability settings like these in the calendar → Connect to another website → Copy the Airbnb calendar link.
                        </p>
                    </div>

                    <!-- Property Description -->
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Description</label>
                        <textarea id="property-description"
                                  rows="4"
                                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-persian-green focus:border-persian-green"
                                  placeholder="Describe your property">${this.propertyData.description || ''}</textarea>
                    </div>

                    <!-- Check-in/Check-out Times -->
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">Check-in Time</label>
                            <input type="time" 
                                   id="checkin-time"
                                   value="${this.propertyData.checkInTime || '15:00'}"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-persian-green focus:border-persian-green attention-pulse">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">Check-out Time</label>
                            <input type="time" 
                                   id="checkout-time"
                                   value="${this.propertyData.checkOutTime || '11:00'}"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-persian-green focus:border-persian-green attention-pulse">
                        </div>
                    </div>

                    <!-- WiFi Details -->
                    <div class="bg-gray-50 p-4 rounded-lg">
                        <h5 class="font-medium text-gray-900 mb-3">
                            WiFi Information <span class="text-red-500">*</span>
                            <span class="ml-2 text-xs text-blue-600 hover:underline cursor-pointer"
                                  data-tooltip="For legal reasons we only retrieve listing information that is publicly available"
                                  onclick="propertySetupModal.toggleLegalTooltip(this)">
                                Why is this not retrieved from my listing?
                            </span>
                        </h5>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">
                                    Network Name <span class="text-red-500">*</span>
                                </label>
                                <input type="text"
                                       id="wifi-network"
                                       value="${this.setupData.basicInfo?.wifiDetails?.network || this.propertyData.wifiDetails?.network || ''}"
                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-persian-green focus:border-persian-green"
                                       placeholder="WiFi network name"
                                       required>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-2">
                                    Password <span class="text-red-500">*</span>
                                </label>
                                <input type="text"
                                       id="wifi-password"
                                       value="${this.setupData.basicInfo?.wifiDetails?.password || this.propertyData.wifiDetails?.password || ''}"
                                       class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-persian-green focus:border-persian-green"
                                       placeholder="WiFi password"
                                       required>
                            </div>
                        </div>
                    </div>

                    <!-- Amenities Section -->
                    <div class="bg-gray-50 p-4 rounded-lg">
                        <h5 class="font-medium text-gray-900 mb-3">Amenities</h5>
                        <div id="amenities-section">
                            <!-- Amenities will be loaded here -->
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Load amenities
        this.loadAmenitiesSection();
        
        // Add auto-save listeners
        this.addAutoSaveListeners();
    }

    loadAmenitiesSection() {
        const amenitiesSection = document.getElementById('amenities-section');
        let amenities = this.propertyData.amenities || { basic: [], appliances: [] };

        // Enhanced appliance categorization - only run once to avoid duplicates
        if (!this.categorizationApplied) {
            amenities = this.enhanceApplianceCategorization(amenities);
            this.categorizationApplied = true;
        }

        // Debug logging
        console.log('Loading amenities section');
        console.log('Property data:', this.propertyData);
        console.log('Enhanced amenities data:', amenities);
        console.log('Basic amenities count:', amenities.basic?.length || 0);
        console.log('Appliances count:', amenities.appliances?.length || 0);
        
        amenitiesSection.innerHTML = `
            <div class="space-y-4">
                <!-- Basic Amenities -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">Basic Amenities</label>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-2" id="basic-amenities">
                        ${amenities.basic.map((amenity, index) => `
                            <div class="flex items-center space-x-2 p-2 bg-white rounded border">
                                <input type="checkbox" checked class="text-persian-green flex-shrink-0">
                                ${amenity.trim() === '' ? `
                                    <input type="text"
                                           value="${amenity}"
                                           placeholder="Enter amenity name"
                                           class="flex-1 px-2 py-1 border rounded text-sm"
                                           onchange="propertySetupModal.updateBasicAmenity(${index}, this.value)"
                                           onblur="propertySetupModal.updateBasicAmenity(${index}, this.value)">
                                ` : `
                                    <span class="text-sm flex-1">${amenity}</span>
                                `}
                                <button onclick="propertySetupModal.removeBasicAmenity(${index})"
                                        class="flex-shrink-0 text-red-500 hover:text-red-700">
                                    <i class="fas fa-times text-xs"></i>
                                </button>
                            </div>
                        `).join('')}
                    </div>
                    <button onclick="propertySetupModal.addBasicAmenity()"
                            class="mt-2 text-sm text-persian-green hover:text-persian-green/80">
                        <i class="fas fa-plus mr-1"></i>Add Amenity
                    </button>
                </div>

                <!-- Appliances -->
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-2">Appliances</label>
                    <div class="space-y-2" id="appliances-list">
                        ${amenities.appliances.map((appliance, index) => {
                            // Ensure appliance is an object with proper structure
                            const applianceObj = typeof appliance === 'object' ? appliance : { name: appliance || '', location: '', brand: '', model: '' };
                            return `
                            <div class="p-3 bg-white rounded border">
                                <div class="grid grid-cols-1 md:grid-cols-4 gap-2">
                                    <input type="text" value="${applianceObj.name || ''}" placeholder="Appliance name"
                                           class="px-2 py-1 border rounded text-sm"
                                           onchange="propertySetupModal.updateAppliance(${index}, 'name', this.value)">
                                    <input type="text" value="${applianceObj.location || ''}" placeholder="Location"
                                           class="px-2 py-1 border rounded text-sm"
                                           onchange="propertySetupModal.updateAppliance(${index}, 'location', this.value)">
                                    <input type="text" value="${applianceObj.brand || ''}" placeholder="Brand"
                                           class="px-2 py-1 border rounded text-sm"
                                           onchange="propertySetupModal.updateAppliance(${index}, 'brand', this.value)">
                                    <div class="flex items-center space-x-2">
                                        <input type="text" value="${applianceObj.model || ''}" placeholder="Model"
                                               class="px-2 py-1 border rounded text-sm flex-1"
                                               onchange="propertySetupModal.updateAppliance(${index}, 'model', this.value)">
                                        <button onclick="propertySetupModal.removeAppliance(${index})"
                                                class="text-red-500 hover:text-red-700">
                                            <i class="fas fa-trash text-xs"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        `;}).join('')}
                    </div>
                    <button onclick="propertySetupModal.addAppliance()" 
                            class="mt-2 text-sm text-persian-green hover:text-persian-green/80">
                        <i class="fas fa-plus mr-1"></i>Add Appliance
                    </button>
                </div>
            </div>
        `;
    }

    addAutoSaveListeners() {
        // Add event listeners for auto-saving
        const inputs = document.querySelectorAll('#setup-step-content input, #setup-step-content textarea');
        inputs.forEach(input => {
            input.addEventListener('change', () => {
                this.saveCurrentStepData();
            });
        });
    }

    async saveCurrentStepData(validateRequired = false) {
        // Save current step data
        switch (this.currentStep) {
            case 1:
                return await this.saveBasicInformation(validateRequired);
            case 2:
                return this.saveHouseRules();
            case 3:
                return this.saveEmergencyInformation();
            case 4:
                return this.savePropertyFacts();
            default:
                return true;
        }
    }

    async saveBasicInformation(validateRequired = false) {
        // Get field values
        const propertyName = document.getElementById('property-name')?.value?.trim() || '';
        const propertyAddress = document.getElementById('property-address')?.value?.trim() || '';
        const icalUrl = document.getElementById('ical-url')?.value?.trim() || '';
        const wifiNetwork = document.getElementById('wifi-network')?.value?.trim() || '';
        const wifiPassword = document.getElementById('wifi-password')?.value?.trim() || '';

        // Only validate required fields when explicitly requested (e.g., when clicking Next)
        if (validateRequired) {
            const validationErrors = [];

            if (!propertyName) {
                validationErrors.push('Property Name is required');
                this.highlightRequiredField('property-name');
            } else {
                this.clearFieldHighlight('property-name');
            }

            if (!propertyAddress) {
                const msg = 'Property Address is required';
                validationErrors.push(msg);
                this.lastAddressErrorMessage = msg;
                this.highlightRequiredField('property-address');
                this.showAddressInlineWarning('Please enter your full street address.');
            } else {
                // Additional validation: ensure address is a real street address, not a neighborhood placeholder
                const looksLikeNeighborhood = this.isLikelyNeighborhoodOnly(propertyAddress);
                if (looksLikeNeighborhood) {
                    const msg = 'Please enter a full street address (not just a neighborhood).';
                    validationErrors.push(msg);
                    this.lastAddressErrorMessage = msg;
                    this.highlightRequiredField('property-address');
                    this.showAddressInlineWarning('This looks like a general area (e.g., a city or neighborhood). Please provide the full street address so we can power location-based answers.');
                } else {
                    this.lastAddressErrorMessage = '';
                    this.clearFieldHighlight('property-address');
                    this.clearAddressInlineWarning();
                }
            }

            // Validate iCal URL with comprehensive validation
            const icalValidation = this.validateICalUrl(icalUrl);
            if (!icalValidation.valid) {
                // Show specific iCal error instead of adding to general validation errors
                this.showICalValidationError(icalValidation.message);
                this.highlightRequiredField('ical-url');
                return false;
            } else {
                this.clearFieldHighlight('ical-url');
                this.clearICalValidationError(); // Clear any previous iCal errors
            }

            if (!wifiNetwork || !wifiPassword) {
                validationErrors.push('WiFi Network Name and Password are required');
                if (!wifiNetwork) this.highlightRequiredField('wifi-network');
                if (!wifiPassword) this.highlightRequiredField('wifi-password');
            } else {
                this.clearFieldHighlight('wifi-network');
                this.clearFieldHighlight('wifi-password');
            }

            // Show validation errors if any
            if (validationErrors.length > 0) {
                // Prefer a specific address-related message if present
                if (this.lastAddressErrorMessage) {
                    this.showStepError(this.lastAddressErrorMessage);
                } else {
                    this.showValidationErrors(validationErrors);
                }
                return false;
            }
        }

        // Clear any previous validation errors
        this.clearValidationErrors();

        // Collect current amenities and appliances from the form
        const currentAmenities = this.collectCurrentAmenities();

        this.setupData.basicInfo = {
            name: propertyName,
            address: propertyAddress,
            description: document.getElementById('property-description')?.value || '',
            icalUrl: document.getElementById('ical-url')?.value || '',
            checkInTime: document.getElementById('checkin-time')?.value || '15:00',
            checkOutTime: document.getElementById('checkout-time')?.value || '11:00',
            wifiDetails: {
                network: wifiNetwork,
                password: wifiPassword
            },
            amenities: currentAmenities  // Include current amenities state
        };

        console.log('Saving basic information with amenities:', this.setupData.basicInfo);

        // Save to server and wait for completion
        const saved = await this.saveStepToServer(1, this.setupData.basicInfo);
        if (!saved) {
            console.error('Failed to save basic information');
        }
        
        // Proactively update property card and details header on the dashboard without reload
        try {
            if (typeof updatePropertyCard === 'function') {
                updatePropertyCard(this.propertyData);
            } else if (window && typeof window.updatePropertyCard === 'function') {
                window.updatePropertyCard(this.propertyData);
            }
        } catch (e) {
            console.warn('Could not update property card after basic info save:', e);
        }
        try {
            if (typeof updatePropertyDetailsHeader === 'function') {
                updatePropertyDetailsHeader(this.propertyData);
            } else if (window && typeof window.updatePropertyDetailsHeader === 'function') {
                window.updatePropertyDetailsHeader(this.propertyData);
            }
        } catch (e) {
            console.warn('Could not update property details header after basic info save:', e);
        }
        return saved;
    }

    // Heuristic: determine if the address looks like a neighborhood-only placeholder
    isLikelyNeighborhoodOnly(address) {
        const value = (address || '').trim();
        if (!value) return true;
        const lower = value.toLowerCase();
        // Common placeholders from imports
        const placeholderSignals = [
            'neighborhood',
            'district',
            'area',
            'vicinity',
            'near',
            'around',
            'close to',
            // overly generic country-only suffixes often present in scraped imports
            'united states'
        ];
        // If explicitly labeled as neighborhood-like
        if (placeholderSignals.some(sig => lower.includes(sig))) {
            // But if it still looks like a concrete street address (number + name), allow it
            if (/^\s*\d{1,6}\s+[A-Za-z0-9 .'-]+/.test(value)) return false;
            return true;
        }
        // Accept if it clearly starts with a street number and name (very lenient)
        if (/^\s*\d{1,6}\s+[A-Za-z0-9 .'-]{3,}/.test(value)) return false;

        // Otherwise, use classic heuristic: number + recognized street type
        const hasNumber = /\b\d{1,6}\b/.test(value);
        const streetTypes = [
            'st', 'str', 'street',
            'ave', 'avenue',
            'blvd', 'boulevard',
            'rd', 'road',
            'dr', 'drive',
            'ln', 'lane',
            'way', 'trail',
            'ct', 'court',
            'pkwy', 'parkway',
            'terrace', 'ter',
            'pl', 'place',
            'hwy', 'highway',
            'cir', 'circle'
        ];
        const hasStreetType = streetTypes.some(t => new RegExp(`\\b${t}\\b`, 'i').test(value));
        return !(hasNumber && hasStreetType);
    }

    // Inline help under Address field
    showAddressInlineWarning(message) {
        const input = document.getElementById('property-address');
        if (!input) return;
        // Remove existing
        this.clearAddressInlineWarning();
        // Insert message element
        const p = document.createElement('p');
        p.id = 'property-address-help';
        p.className = 'text-sm text-red-600 mt-1';
        p.innerHTML = `<i class="fas fa-exclamation-circle mr-1"></i>${message}`;
        input.insertAdjacentElement('afterend', p);
    }

    // Toggle small tooltip for legal notice near labels
    toggleLegalTooltip(anchorEl) {
        try {
            const existing = anchorEl.parentElement.querySelector('.legal-tooltip-pop');
            if (existing) {
                existing.remove();
                return;
            }
            const tip = document.createElement('div');
            tip.className = 'legal-tooltip-pop mt-1 text-xs bg-gray-50 border border-gray-200 text-gray-700 rounded px-2 py-1 inline-block';
            tip.textContent = anchorEl.getAttribute('data-tooltip') || 'For legal reasons we only retrieve listing information that is publicly available';
            anchorEl.parentElement.appendChild(tip);
            // Auto-hide after 5s
            setTimeout(() => { tip.remove(); }, 5000);
        } catch (e) {
            console.warn('Failed to show legal tooltip:', e);
        }
    }

    clearAddressInlineWarning() {
        const help = document.getElementById('property-address-help');
        if (help) help.remove();
    }

    highlightRequiredField(fieldId) {
        const field = document.getElementById(fieldId);
        if (field) {
            field.classList.add('border-red-500', 'border-2');
            field.classList.remove('border-gray-300');
        }
    }

    clearFieldHighlight(fieldId) {
        const field = document.getElementById(fieldId);
        if (field) {
            field.classList.remove('border-red-500', 'border-2');
            field.classList.add('border-gray-300');
        }
    }

    showValidationErrors(errors) {
        // Remove any existing error display
        this.clearValidationErrors();

        // Create error display
        const errorDiv = document.createElement('div');
        errorDiv.id = 'validation-errors';
        errorDiv.className = 'bg-red-50 border border-red-200 rounded-lg p-4 mb-4';
        errorDiv.innerHTML = `
            <div class="flex items-start space-x-3">
                <i class="fas fa-exclamation-triangle text-red-600 mt-1"></i>
                <div>
                    <h4 class="text-sm font-medium text-red-800 mb-1">Please fix the following errors:</h4>
                    <ul class="text-sm text-red-700 list-disc list-inside">
                        ${errors.map(error => `<li>${error}</li>`).join('')}
                    </ul>
                </div>
            </div>
        `;

        // Insert at the top of the step content
        const stepContent = document.getElementById('setup-step-content');
        if (stepContent) {
            stepContent.insertBefore(errorDiv, stepContent.firstChild);
        }

        // Scroll to top to ensure the error message is visible
        this.scrollToTop();
    }

    clearValidationErrors() {
        const errorDiv = document.getElementById('validation-errors');
        if (errorDiv) {
            errorDiv.remove();
        }
        // Also clear iCal validation errors
        this.clearICalValidationError();
    }

    showICalValidationError(message) {
        // Remove any existing iCal error display
        this.clearICalValidationError();

        // Create specific iCal error display with different styling
        const errorDiv = document.createElement('div');
        errorDiv.id = 'ical-validation-error';
        errorDiv.className = 'bg-orange-50 border border-orange-200 rounded-lg p-4 mb-4';
        errorDiv.innerHTML = `
            <div class="flex items-start space-x-3">
                <i class="fas fa-calendar-times text-orange-600 mt-1"></i>
                <div>
                    <h4 class="text-sm font-medium text-orange-800 mb-1">iCal URL Validation Error</h4>
                    <p class="text-sm text-orange-700">${message}</p>
                    <div class="mt-2 text-xs text-orange-600">
                        <strong>Need help?</strong> For Airbnb: Go to your listing → Calendar → "Availability settings" → "Sync calendar" → Copy the iCal export link.
                    </div>
                </div>
            </div>
        `;

        // Insert at the top of the step content
        const stepContent = document.getElementById('setup-step-content');
        if (stepContent) {
            stepContent.insertBefore(errorDiv, stepContent.firstChild);
        }

        // Scroll to top to ensure the error message is visible
        this.scrollToTop();
    }

    clearICalValidationError() {
        const errorDiv = document.getElementById('ical-validation-error');
        if (errorDiv) {
            errorDiv.remove();
        }
    }

    showStepError(message) {
        // Remove any existing general validation errors, but preserve specific iCal errors
        const generalErrorDiv = document.getElementById('validation-errors');
        if (generalErrorDiv) {
            generalErrorDiv.remove();
        }

        // Create error display
        const errorDiv = document.createElement('div');
        errorDiv.id = 'validation-errors';
        errorDiv.className = 'bg-red-50 border border-red-200 rounded-lg p-4 mb-4';
        errorDiv.innerHTML = `
            <div class="flex items-center">
                <i class="fas fa-exclamation-triangle text-red-500 mr-2"></i>
                <span class="text-red-700 font-medium">${message}</span>
            </div>
        `;

        // Insert at the top of the step content
        const stepContent = document.getElementById('setup-step-content');
        if (stepContent) {
            stepContent.insertBefore(errorDiv, stepContent.firstChild);
        }

        // Scroll to top to ensure the error message is visible
        this.scrollToTop();
    }

    scrollToTop() {
        // Primary target: the scrollable step content container
        const stepContent = document.getElementById('setup-step-content');
        if (stepContent) {
            stepContent.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
            console.log('Scrolled setup-step-content to top');
            return; // Exit early if successful
        }

        // Fallback 1: try the modal's inner content div
        const modalInner = document.querySelector('#property-setup-modal .bg-white.rounded-lg');
        if (modalInner) {
            modalInner.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
            console.log('Scrolled modal inner content to top');
            return;
        }

        // Fallback 2: scroll the entire modal
        const modal = document.getElementById('property-setup-modal');
        if (modal) {
            modal.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
            console.log('Scrolled entire modal to top');
        } else {
            console.warn('Could not find any scroll target for validation errors');
        }
    }

    enhanceApplianceCategorization(amenities) {
        // Items that should be moved from basic amenities to appliances
        const applianceKeywords = [
            'TV', 'Television', 'Smart TV', 'HDTV', 'Roku TV', 'Apple TV',
            'Toaster', 'Coffee maker', 'Coffee machine', 'Espresso machine',
            'Microwave', 'Dishwasher', 'Washing machine', 'Washer', 'Dryer',
            'Hair dryer', 'Refrigerator', 'Fridge', 'Oven', 'Stove', 'Cooktop',
            'Freezer', 'Blender', 'Food processor', 'Electric kettle',
            'Rice cooker', 'Slow cooker', 'Air fryer', 'Stand mixer',
            'Ice maker', 'Wine fridge', 'Range', 'Stovetop'
        ];

        // Items that should NOT be appliances (common false positives)
        const nonApplianceKeywords = [
            'Parking', 'Pillows', 'Blankets', 'Books', 'Reading material',
            'Security cameras', 'Cameras', 'Dishes', 'Silverware', 'Wine glasses',
            'Clothing storage', 'Exercise equipment', 'Noise monitors',
            'Decibel monitors', 'Beach access', 'WiFi', 'Internet',
            'Air conditioning', 'Patio', 'Balcony', 'Smart lock', 'Lock',
            'Heating', 'Pool', 'Hot tub', 'Jacuzzi', 'Fireplace', 'Deck',
            'Coffee'  // Coffee alone should be basic amenity, not appliance
        ];

        // Kitchen appliances that should have location pre-populated (comprehensive list)
        const kitchenAppliances = [
            'Microwave', 'Dishwasher', 'Refrigerator', 'Fridge', 'Oven',
            'Stove', 'Cooktop', 'Toaster', 'Coffee maker', 'Coffee machine',
            'Espresso machine', 'Freezer', 'Blender', 'Food processor',
            'Electric kettle', 'Rice cooker', 'Slow cooker', 'Air fryer',
            'Stand mixer', 'Ice maker', 'Wine fridge', 'Range', 'Stovetop',
            'Garbage disposal', 'Can opener', 'Mixer', 'Juicer'
        ];

        // Appliances that should NOT get kitchen location (even if they're appliances)
        const nonKitchenAppliances = [
            'Washer', 'Washing machine', 'Dryer', 'Hair dryer', 'TV', 'Television',
            'Air conditioning', 'Heating', 'Vacuum', 'Iron', 'Fan'
        ];

        const enhancedAmenities = {
            basic: [...amenities.basic],
            appliances: []
        };

        // Normalize existing appliances to proper object format
        (amenities.appliances || []).forEach(appliance => {
            if (typeof appliance === 'string') {
                // Convert string to proper appliance object
                const itemLower = appliance.toLowerCase();
                let isKitchenAppliance = false;
                let isNonKitchenAppliance = false;
                let specificLocation = '';

                // First check if it's explicitly a non-kitchen appliance
                // Use specific mappings in order of specificity (most specific first)
                const nonKitchenMappings = [
                    { keyword: 'hair dryer', location: 'Bathroom' },
                    { keyword: 'washing machine', location: 'Laundry' },
                    { keyword: 'smart tv', location: 'Living Room' },
                    { keyword: 'hdtv', location: 'Living Room' },
                    { keyword: 'tv', location: 'Living Room' },
                    { keyword: 'television', location: 'Living Room' },
                    { keyword: 'washer', location: 'Laundry' },
                    { keyword: 'dryer', location: 'Laundry' },
                    { keyword: 'vacuum', location: 'Storage' },
                    { keyword: 'iron', location: 'Bedroom' },
                    { keyword: 'fan', location: 'Bedroom' }
                    // Note: air conditioning and heating left without default location
                    // so hosts can specify the actual location (bedroom, living room, etc.)
                ];

                for (const mapping of nonKitchenMappings) {
                    if (itemLower.includes(mapping.keyword)) {
                        isNonKitchenAppliance = true;
                        specificLocation = mapping.location;
                        break;
                    }
                }

                // Then check if it's a kitchen appliance (only if not non-kitchen)
                if (!isNonKitchenAppliance) {
                    for (const keyword of kitchenAppliances) {
                        const keywordLower = keyword.toLowerCase();
                        if (itemLower.includes(keywordLower) ||
                            itemLower.split(' ').some(word => keywordLower.includes(word)) ||
                            keywordLower.split(' ').some(word => itemLower.includes(word))) {
                            isKitchenAppliance = true;
                            break;
                        }
                    }
                }

                enhancedAmenities.appliances.push({
                    name: appliance,
                    location: specificLocation || (isKitchenAppliance ? 'Kitchen' : ''),
                    brand: '',
                    model: ''
                });
                console.log(`Normalized string appliance "${appliance}" to object with location: "${specificLocation || (isKitchenAppliance ? 'Kitchen' : '')}"`);
            } else if (typeof appliance === 'object' && appliance.name) {
                // Keep existing object appliances as-is
                enhancedAmenities.appliances.push(appliance);
            }
        });

        // Move appliance-like items from basic to appliances with flexible matching
        const itemsToMove = [];
        enhancedAmenities.basic.forEach((item, index) => {
            const itemLower = item.toLowerCase();
            let isAppliance = false;
            let isNonAppliance = false;

            // Check for non-appliance keywords first
            for (const keyword of nonApplianceKeywords) {
                const keywordLower = keyword.toLowerCase();
                if (itemLower.includes(keywordLower)) {
                    isNonAppliance = true;
                    break;
                }
            }

            // Check for appliance keywords with precise matching (if not a non-appliance)
            if (!isNonAppliance) {
                for (const keyword of applianceKeywords) {
                    const keywordLower = keyword.toLowerCase();
                    // Use more precise matching to avoid false positives like "Coffee" matching "Coffee maker"
                    if (itemLower === keywordLower ||
                        itemLower.includes(keywordLower) ||
                        keywordLower.includes(itemLower)) {
                        isAppliance = true;
                        break;
                    }
                }
            }

            if (isAppliance && !isNonAppliance) {
                itemsToMove.push({ item, index });
            }
        });

        // Remove items from basic amenities (in reverse order to maintain indices)
        itemsToMove.reverse().forEach(({ item, index }) => {
            enhancedAmenities.basic.splice(index, 1);

            // Check if this appliance already exists in appliances array
            const existingAppliance = enhancedAmenities.appliances.find(app =>
                app.name && app.name.toLowerCase() === item.toLowerCase()
            );

            if (!existingAppliance) {
                // Determine if it's a kitchen appliance with flexible matching
                const itemLower = item.toLowerCase();
                let isKitchenAppliance = false;

                for (const keyword of kitchenAppliances) {
                    const keywordLower = keyword.toLowerCase();
                    if (itemLower.includes(keywordLower) ||
                        itemLower.split(' ').some(word => keywordLower.includes(word)) ||
                        keywordLower.split(' ').some(word => itemLower.includes(word))) {
                        isKitchenAppliance = true;
                        break;
                    }
                }

                enhancedAmenities.appliances.push({
                    name: item,
                    location: isKitchenAppliance ? 'Kitchen' : '',
                    brand: '',
                    model: ''
                });

                console.log(`Moved "${item}" to appliances with ${isKitchenAppliance ? 'Kitchen' : 'empty'} location`);
            }
        });

        // Post-process existing appliances to normalize locations
        enhancedAmenities.appliances.forEach(appliance => {
            if (typeof appliance === 'object' && appliance.name) {
                const itemLower = appliance.name.toLowerCase();
                let isKitchenAppliance = false;
                let isNonKitchenAppliance = false;
                let specificLocation = '';

                // Check if it's explicitly a non-kitchen appliance first
                // Use specific mappings in order of specificity (most specific first)
                const nonKitchenMappings = [
                    { keyword: 'hair dryer', location: 'Bathroom' },
                    { keyword: 'washing machine', location: 'Laundry' },
                    { keyword: 'smart tv', location: 'Living Room' },
                    { keyword: 'hdtv', location: 'Living Room' },
                    { keyword: 'tv', location: 'Living Room' },
                    { keyword: 'television', location: 'Living Room' },
                    { keyword: 'washer', location: 'Laundry' },
                    { keyword: 'dryer', location: 'Laundry' },
                    { keyword: 'vacuum', location: 'Storage' },
                    { keyword: 'iron', location: 'Bedroom' },
                    { keyword: 'fan', location: 'Bedroom' }
                    // Note: air conditioning and heating left without default location
                    // so hosts can specify the actual location (bedroom, living room, etc.)
                ];

                for (const mapping of nonKitchenMappings) {
                    if (itemLower.includes(mapping.keyword)) {
                        isNonKitchenAppliance = true;
                        specificLocation = mapping.location;
                        break;
                    }
                }

                // Check if it's a kitchen appliance (only if not non-kitchen)
                if (!isNonKitchenAppliance) {
                    for (const keyword of kitchenAppliances) {
                        const keywordLower = keyword.toLowerCase();
                        if (itemLower.includes(keywordLower) ||
                            itemLower.split(' ').some(word => keywordLower.includes(word)) ||
                            keywordLower.split(' ').some(word => itemLower.includes(word))) {
                            isKitchenAppliance = true;
                            break;
                        }
                    }
                }

                // Apply location normalization
                if (isNonKitchenAppliance && specificLocation) {
                    // Override location for non-kitchen appliances
                    appliance.location = specificLocation;
                    console.log(`Normalized "${appliance.name}" location to ${specificLocation} (was: "${appliance.location}")`);
                } else if (isKitchenAppliance && !isNonKitchenAppliance) {
                    // Normalize location for kitchen appliances
                    const currentLocation = (appliance.location || '').toLowerCase().trim();
                    const kitchenVariants = ['unit', 'in unit', 'kitchen', ''];

                    if (kitchenVariants.includes(currentLocation)) {
                        appliance.location = 'Kitchen';
                        console.log(`Normalized "${appliance.name}" location to Kitchen (was: "${currentLocation}")`);
                    } else {
                        // Debug: log when kitchen appliances don't get normalized
                        console.log(`⚠️ Kitchen appliance "${appliance.name}" has non-standard location: "${currentLocation}"`);
                    }
                }
            }
        });

        // Update the property data with enhanced categorization
        this.propertyData.amenities = enhancedAmenities;

        console.log('Enhanced categorization complete:', {
            basicCount: enhancedAmenities.basic.length,
            appliancesCount: enhancedAmenities.appliances.length,
            movedItems: itemsToMove.length
        });

        return enhancedAmenities;
    }

    collectCurrentAmenities() {
        // Collect current amenities and appliances from the form
        const amenities = {
            basic: [],
            appliances: []
        };

        console.log('🔍 Collecting current amenities...');

        // Collect basic amenities
        const basicAmenitiesContainer = document.getElementById('basic-amenities');
        console.log('Basic amenities container:', basicAmenitiesContainer);

        if (basicAmenitiesContainer) {
            const amenityElements = basicAmenitiesContainer.querySelectorAll('div.flex.items-center');
            console.log(`Found ${amenityElements.length} basic amenity elements`);

            amenityElements.forEach((element, index) => {
                const checkbox = element.querySelector('input[type="checkbox"]');
                const span = element.querySelector('span');
                if (checkbox && span) {
                    console.log(`Amenity ${index}: "${span.textContent.trim()}" - Checked: ${checkbox.checked}`);
                    if (checkbox.checked) {
                        amenities.basic.push(span.textContent.trim());
                    }
                }
            });
        } else {
            console.log('❌ Basic amenities container not found');
        }

        // Collect appliances
        const appliancesContainer = document.getElementById('appliances-list');
        console.log('Appliances container:', appliancesContainer);

        if (appliancesContainer) {
            const applianceElements = appliancesContainer.querySelectorAll('div.p-3');
            console.log(`Found ${applianceElements.length} appliance elements`);

            applianceElements.forEach((element, index) => {
                const inputs = element.querySelectorAll('input[type="text"]');
                console.log(`Appliance ${index}: Found ${inputs.length} input fields`);

                if (inputs.length >= 4) {
                    const name = inputs[0].value.trim();
                    const location = inputs[1].value.trim();
                    const brand = inputs[2].value.trim();
                    const model = inputs[3].value.trim();

                    console.log(`Appliance ${index} data: Name="${name}", Location="${location}", Brand="${brand}", Model="${model}"`);

                    if (name) { // Only include if name is provided
                        amenities.appliances.push({
                            name: name,
                            location: location,
                            brand: brand,
                            model: model
                        });
                    }
                }
            });
        } else {
            console.log('❌ Appliances container not found');
        }

        console.log('Collected current amenities:', amenities);
        return amenities;
    }

    saveStepToServer(step, data) {
        // Save step data to server
        return fetch(`/api/properties/${this.propertyId}/setup-progress`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                step: step,
                data: data
            })
        })
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                console.log(`Step ${step} saved successfully`);
                // Update local property data with saved changes
                this.updateLocalPropertyData(step, data);
                // Emit a custom event so other parts of the dashboard can refresh UI (e.g., property cards)
                try {
                    const updated = { ...this.propertyData };
                    const evt = new CustomEvent('propertyUpdated', { detail: { propertyId: this.propertyId, property: updated } });
                    window.dispatchEvent(evt);
                } catch (e) {
                    console.warn('Failed to dispatch propertyUpdated event:', e);
                }
                return true;
            } else {
                console.error(`Failed to save step ${step}:`, result.error);
                return false;
            }
        })
        .catch(error => {
            console.error('Error saving step data:', error);
            return false;
        });
    }

    updateLocalPropertyData(step, data) {
        // Update the local property data with the saved changes
        if (step === 1) { // Basic Information
            this.propertyData.name = data.name || this.propertyData.name;
            this.propertyData.address = data.address || this.propertyData.address;
            this.propertyData.description = data.description || this.propertyData.description;
            this.propertyData.icalUrl = data.icalUrl || this.propertyData.icalUrl;
            this.propertyData.checkInTime = data.checkInTime || this.propertyData.checkInTime;
            this.propertyData.checkOutTime = data.checkOutTime || this.propertyData.checkOutTime;
            this.propertyData.wifiDetails = data.wifiDetails || this.propertyData.wifiDetails;

            // Update amenities if provided
            if (data.amenities) {
                this.propertyData.amenities = data.amenities;
                console.log('Updated amenities in local property data:', data.amenities);
            }
        } else if (step === 2) {
            // Update house rules if provided
            if (data.houseRules) {
                this.propertyData.houseRules = data.houseRules;
                console.log('Updated house rules in local property data:', data.houseRules);
            }
        } else if (step === 3) {
            // Update emergency information if provided
            if (data.emergencyInfo) {
                this.propertyData.emergencyInfo = data.emergencyInfo;
                console.log('Updated emergency info in local property data:', data.emergencyInfo);
            }
        } else if (step === 4) {
            // Update property facts if provided
            if (data.propertyFacts) {
                this.propertyData.propertyFacts = data.propertyFacts;
                console.log('Updated property facts in local property data:', data.propertyFacts);
            }
        }

        console.log('Updated local property data:', this.propertyData);
    }

    async nextStep() {
        // Prevent concurrent navigation if a save is already in-flight
        if (this.isNavigating) return;

        if (this.currentStep < this.totalSteps) {
            // Compute target step before awaiting to avoid multiple increments from queued clicks
            const targetStep = Math.min(this.currentStep + 1, this.totalSteps);

            this.isNavigating = true;
            const nextBtn = document.getElementById('next-btn');
            if (nextBtn) {
                nextBtn.disabled = true;
                nextBtn.innerHTML = `<i class="fas fa-circle-notch fa-spin mr-2"></i><span class="btn-text">Saving...</span>`;
            }

            const saved = await this.saveCurrentStepData(true); // Validate required fields when moving to next step
            if (saved) {
                this.loadStep(targetStep);
            } else {
                console.error('Failed to save current step data');
                // Check if there's already a specific error displayed
                const existingICalError = document.getElementById('ical-validation-error');
                const existingGeneralError = document.getElementById('validation-errors');
                // Only show generic error if no specific error/banner is already displayed
                if (!existingICalError && !existingGeneralError) {
                    this.showStepError('Please fill in all required fields before proceeding to the next step.');
                }
                // Restore button state and text if we did not navigate
                this.updateNavigationButtons();
            }

            this.isNavigating = false;
            if (nextBtn) nextBtn.disabled = false;
        } else {
            // Complete setup
            this.completeSetup();
        }
    }

    async previousStep() {
        if (this.isNavigating) return;
        if (this.currentStep > 1) {
            this.isNavigating = true;
            const prevBtn = document.getElementById('prev-btn');
            if (prevBtn) {
                prevBtn.disabled = true;
                prevBtn.innerHTML = `<i class="fas fa-circle-notch fa-spin mr-2"></i><span class="btn-text">Saving...</span>`;
            }

            await this.saveCurrentStepData();
            const targetStep = Math.max(this.currentStep - 1, 1);
            this.loadStep(targetStep);

            this.isNavigating = false;
            if (prevBtn) {
                prevBtn.disabled = false;
                // Restore label/icon immediately in case the UI hasn't re-rendered yet
                prevBtn.innerHTML = `<i class="fas fa-arrow-left mr-2"></i><span class="btn-text">Previous</span>`;
            }
        }
    }

    updateProgressBar() {
        const modal = document.getElementById('property-setup-modal');
        if (modal) {
            // Update progress bar and step indicators
            const progressBar = modal.querySelector('.bg-white.rounded-full.h-2');
            if (progressBar) {
                progressBar.style.width = `${(this.currentStep / this.totalSteps) * 100}%`;
            }

            // Update step counter and percentage in header
            const stepCounter = modal.querySelector('.flex.items-center.justify-between.text-sm.mb-2.text-white span:first-child');
            if (stepCounter) {
                stepCounter.textContent = `Step ${this.currentStep} of ${this.totalSteps}`;
            }

            const percentageText = modal.querySelector('.flex.items-center.justify-between.text-sm.mb-2.text-white span:last-child');
            if (percentageText) {
                percentageText.textContent = `${Math.round((this.currentStep / this.totalSteps) * 100)}% Complete`;
            }

            // Update step text
            const stepTexts = modal.querySelectorAll('.text-xs.mt-2.text-white span');
            stepTexts.forEach((span, index) => {
                if (index + 1 <= this.currentStep) {
                    span.className = 'font-medium opacity-100';
                } else {
                    span.className = 'opacity-80';
                }
            });
        }
    }

    updateNavigationButtons() {
        const prevBtn = document.getElementById('prev-btn');
        const nextBtn = document.getElementById('next-btn');

        if (prevBtn) {
            prevBtn.disabled = this.currentStep === 1;
            prevBtn.className = `px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors ${this.currentStep === 1 ? 'opacity-50 cursor-not-allowed' : ''}`;
            // Always restore label/icon in case it was replaced with a spinner
            prevBtn.innerHTML = `<i class="fas fa-arrow-left mr-2"></i><span class="btn-text">Previous</span>`;
        }

        if (nextBtn) {
            nextBtn.innerHTML = `
                <span class="btn-text">${this.currentStep === this.totalSteps ? 'Complete Setup' : 'Next'}</span>
                <i class="fas ${this.currentStep === this.totalSteps ? 'fa-check' : 'fa-arrow-right'} ml-2"></i>
            `;

            // Reset button state for non-final steps
            if (this.currentStep !== this.totalSteps) {
                nextBtn.disabled = false;
                nextBtn.className = 'px-4 py-2 bg-persian-green text-white rounded-lg hover:bg-persian-green/90 transition-colors';
            }
        }

        // Update step indicator text in footer - use specific ID
        const stepIndicator = document.getElementById('step-indicator');
        console.log('Step indicator element:', stepIndicator);
        console.log('Current step:', this.currentStep, 'Step name:', this.stepNames[this.currentStep - 1]);
        if (stepIndicator) {
            const newText = `Step ${this.currentStep} of ${this.totalSteps}: ${this.stepNames[this.currentStep - 1]}`;
            console.log('Updating step indicator to:', newText);
            stepIndicator.textContent = newText;
        } else {
            console.log('Step indicator not found by ID');
        }
    }

    completeSetup() {
        // Show loading state
        const nextBtn = document.getElementById('next-btn');
        if (nextBtn) {
            nextBtn.disabled = true;
            nextBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i><span class="btn-text">Completing Setup...</span>';
        }

        // Prepare all setup data for submission
        const setupPayload = {
            basicInfo: this.setupData.basicInfo,
            houseRules: this.setupData.houseRules,
            emergencyInfo: this.setupData.emergencyInfo,
            propertyFacts: this.setupData.propertyFacts
        };

        // Complete setup with all knowledge data
        fetch(`/api/properties/${this.propertyId}/complete-setup`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin',
            body: JSON.stringify(setupPayload)
        })
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                // Close the setup modal first so follow-up UI is visible
                this.close();
                // After successful setup completion, check for pending items
                this.checkPendingItemsAfterSetup();
            } else {
                showErrorMessage(result.error || 'Failed to complete setup');
                // Restore button state
                if (nextBtn) {
                    nextBtn.disabled = false;
                    nextBtn.innerHTML = '<span class="btn-text">Complete Setup</span> <i class="fas fa-check ml-2"></i>';
                }
            }
        })
        .catch(error => {
            console.error('Error completing setup:', error);
            showErrorMessage('Failed to complete setup');
            // Restore button state
            if (nextBtn) {
                nextBtn.disabled = false;
                nextBtn.innerHTML = '<span class="btn-text">Complete Setup</span> <i class="fas fa-check ml-2"></i>';
            }
        });
    }

    checkPendingItemsAfterSetup() {
        // Check for pending knowledge items after setup completion
        fetch(`/api/properties/${this.propertyId}/knowledge/pending-count`, {
            method: 'GET',
            credentials: 'same-origin'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success && data.has_pending_items) {
                // Show warning about pending items and offer to review them
                this.showSetupCompletePendingItemsWarning(data.pending_count);
            } else {
                // No pending items, complete setup normally
                this.finishSetupCompletion();
            }
        })
        .catch(error => {
            console.error('Error checking pending items after setup:', error);
            // If check fails, complete setup normally (don't block on this check)
            this.finishSetupCompletion();
        });
    }

    showSetupCompletePendingItemsWarning(pendingCount) {
        // Create modal HTML for setup completion warning
        const modalHTML = `
            <div id="setup-complete-pending-warning-modal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[100]">
                <div class="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
                    <div class="p-6">
                        <div class="flex items-center mb-4">
                            <div class="flex-shrink-0">
                                <i class="fas fa-check-circle text-green-500 text-2xl"></i>
                            </div>
                            <div class="ml-3">
                                <h3 class="text-lg font-medium text-gray-900">
                                    Setup Complete!
                                </h3>
                            </div>
                        </div>

                        <div class="mb-6">
                            <p class="text-sm text-gray-600 mb-3">
                                Your property setup has been completed successfully!
                            </p>
                            <p class="text-sm text-gray-600">
                                However, there ${pendingCount > 1 ? 'are' : 'is'} <strong>${pendingCount}</strong> pending knowledge item${pendingCount > 1 ? 's' : ''}
                                that need${pendingCount > 1 ? '' : 's'} to be reviewed and approved before your property can be fully activated.
                            </p>
                        </div>

                        <div class="flex flex-col sm:flex-row gap-3">
                            <button onclick="propertySetupModal.reviewPendingItemsFromSetup()"
                                    class="flex-1 bg-persian-green hover:bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                                <i class="fas fa-book mr-2"></i>Review Items Now
                            </button>
                            <button onclick="propertySetupModal.finishSetupWithPendingItems()"
                                    class="flex-1 bg-gray-300 hover:bg-gray-400 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                                Review Later
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Add modal to page
        document.body.insertAdjacentHTML('beforeend', modalHTML);
    }

    reviewPendingItemsFromSetup() {
        // Close the warning modal
        const modal = document.getElementById('setup-complete-pending-warning-modal');
        if (modal) {
            modal.remove();
        }

        // Close the setup modal
        this.close();

        // Refresh properties and open knowledge management
        if (typeof loadProperties === 'function') {
            loadProperties();
        }

        // Find the property and open knowledge modal
        setTimeout(() => {
            if (typeof properties !== 'undefined') {
                const property = properties.find(p => p.id === this.propertyId);
                if (property && typeof openKnowledgeModal === 'function') {
                    openKnowledgeModal(property);
                }
            }
        }, 500);
    }

    finishSetupWithPendingItems() {
        // Close the warning modal
        const modal = document.getElementById('setup-complete-pending-warning-modal');
        if (modal) {
            modal.remove();
        }

        // Complete setup normally
        this.finishSetupCompletion();
    }

    finishSetupCompletion() {
        this.close();
        // Refresh the properties list
        if (typeof loadProperties === 'function') {
            loadProperties();
        }
        // Show success message
        showSuccessMessage('Property setup completed successfully! All knowledge has been saved, and we are ready to help your guests.');
    }

    close() {
        // Clean up resize listener
        if (this.resizeListener) {
            window.removeEventListener('resize', this.resizeListener);
            this.resizeListener = null;
        }

        const modal = document.getElementById('property-setup-modal');
        if (modal) {
            modal.remove();
            document.body.style.overflow = 'auto';
        }
    }

    // House Rules step implementation
    loadHouseRulesStep(content) {
        content.innerHTML = `
            <div>
                <div class="mb-6">
                    <h4 class="text-lg font-semibold text-dark-purple mb-2">
                        <i class="fas fa-gavel text-persian-green mr-2"></i>
                        House Rules
                    </h4>
                    <p class="text-gray-600">Set clear expectations for your guests. Enable the rules that apply to your property and customize them as needed. Make sure it matches what you have in your listing. Remember, changing your house rules here will not update the rules in your listing.</p>
                </div>

                <!-- Unified House Rules Content -->
                <div id="house-rules-content">
                    <!-- Will be populated by loadUnifiedRules() -->
                    <div class="text-center py-8">
                        <div class="loading-spinner mx-auto mb-4"></div>
                        <p class="text-gray-600">Loading house rules...</p>
                    </div>
                </div>
            </div>
        `;

        // Load unified rules section
        this.loadUnifiedRules();
    }

    loadEmergencyInformationStep(content) {
        content.innerHTML = `
            <div>
                <div class="mb-6">
                    <h4 class="text-lg font-semibold text-dark-purple mb-2">
                        <i class="fas fa-exclamation-triangle text-persian-green mr-2"></i>
                        Emergency Information
                    </h4>
                    <p class="text-gray-600">Provide essential emergency information for your guests. Enable and customize the information that applies to your property.</p>
                </div>

                <!-- Emergency Information Content -->
                <div id="emergency-info-content">
                    <!-- Will be populated by loadEmergencyInformation() -->
                    <div class="text-center py-8">
                        <div class="loading-spinner mx-auto mb-4"></div>
                        <p class="text-gray-600">Loading emergency information...</p>
                    </div>
                </div>
            </div>
        `;

        // Load emergency information
        this.loadEmergencyInformation();
    }

    loadPropertyFactsStep(content) {
        // Revised Property Facts - organized into folded sections
        // Removed location-based questions that can be answered via web search
        const propertyFactsData = {
            propertyFacts: {
                title: "Property Facts",
                icon: "fas fa-home",
                description: "Property-specific information that guests can't find elsewhere",
                questions: [
                    // Basic Property Characteristics (most fundamental info first)
                    "How many people can comfortably sit at the dining table?",
                    "Are there stairs inside the property that guests need to navigate?",

                    // Comfort & Environment (grouped together)
                    "Is there air conditioning available in all rooms?",
                    "What's the water pressure like in the shower?",
                    "What's the noise level like in this area?",

                    // Technology & Connectivity (grouped together)
                    "What's the internet speed like for video calls and streaming?",
                    "How's the cell phone signal strength at the property?",
                    "Which cell phone carrier works best in this area?",

                    // Practical Considerations (safety and logistics)
                    "Is parking included, and where exactly should guests park?",
                    "Can guests safely drink the tap water for drinking and cooking?",
                    "Are there any construction or renovation projects happening nearby?",

                    // Unique Property Features (most specific to this property)
                    "What wildlife might guests see around the property?",
                    "Are there any unique quirks about the property guests should know?",
                    "What should guests be particularly careful about at this property?"
                ]
            },
            locatingThings: {
                title: "Locating Things",
                icon: "fas fa-map-marker-alt",
                description: "Help guests find items and amenities in your property",
                questions: [
                    // Bedroom & Sleeping (start with where guests first go)
                    "What's the bedding configuration in each room?",
                    "Where can guests find extra pillows and blankets?",
                    "Where are the extra towels and linens stored?",
                    "How do guests set up sofabeds and where are the sheets stored?",

                    // Bathroom Essentials (logical next area)
                    "Where do you keep the extra toilet paper?",
                    "Where is the hair dryer located?",

                    // Kitchen & Dining (daily use items)
                    "Where are the wine glasses and coffee cups?",
                    "Where is the dishwasher detergent kept?",

                    // Cleaning & Maintenance (grouped together)
                    "Where are the cleaning supplies and broom stored?",
                    "Where do you store the vacuum cleaner?",
                    "Where is the tool kit for minor repairs?",

                    // Laundry & Personal Care (related activities)
                    "Where are the laundry detergent and fabric softener?",
                    "Where is the iron and ironing board located?",

                    // Waste & Recycling (practical daily need)
                    "Where should guests put trash and recycling, and when is pickup?",

                    // Special Equipment & Seasonal Items (less frequent but important)
                    "Do you provide a crib, pack-n-play, or high chair?",
                    "Where are beach towels stored (if applicable)?",
                    "Where do you store seasonal items like umbrellas, fans, or heaters?",

                    // Emergency & Safety Items (important but hopefully not needed)
                    "Where do you keep flashlights and candles?",

                    // Special Features (property-specific)
                    "Is there a fireplace or fire pit, and how do guests use it safely?"
                ]
            },
            hostRecommendations: {
                title: "Host Recommendations",
                icon: "fas fa-star",
                description: "Share your personal recommendations and local insights",
                questions: [
                    // Must-See & Must-Do (start with the most important)
                    "What's the one thing guests absolutely shouldn't miss in this area?",
                    "What are your favorite local attractions and things to do nearby?",
                    "What are some hidden gems that only locals know about?",

                    // Dining & Food (very common guest need)
                    "Which local restaurants and cafes do you recommend?",
                    "What's your personal favorite local coffee shop?",

                    // Family & Entertainment (specific audience needs)
                    "What do you recommend for families with children?",
                    "Are there sports channels available on the TV?",

                    // Timing & Events (helps with planning)
                    "What's the best time to visit local attractions to avoid crowds?",
                    "Are there any local events or festivals guests should know about?",

                    // Business & Practical (value-added services)
                    "Do you have partnerships or discounts with any local businesses?",
                    "Do you offer any discounts for longer stays or return visits?",

                    // Additional Resources (catch-all for other recommendations)
                    "Are there any other local contacts or resources you'd like to share?"
                ]
            }
        };

        content.innerHTML = `
            <div>
                <div class="mb-6">
                    <h4 class="text-lg font-semibold text-dark-purple mb-2">
                        <i class="fas fa-clipboard-list text-persian-green mr-2"></i>
                        Other Information
                    </h4>
                    <p class="text-gray-600 mb-4">
                        Answer the questions below to create comprehensive knowledge about your property so we can cover guest queries beyond amenities and areas covered before.
                        <strong>None of these questions are mandatory</strong> - provide answers that you feel would be helpful for this specific property.
                    </p>
                    <div class="bg-blue-50 border border-blue-200 rounded-lg p-3">
                        <div class="flex items-start">
                            <i class="fas fa-info-circle text-blue-500 mt-0.5 mr-2"></i>
                            <div class="text-sm text-blue-700">
                                <strong>Tip:</strong> The more detailed information you provide, the better we can help your guests with specific questions about your property.
                            </div>
                        </div>
                    </div>
                </div>

                <div class="space-y-6" id="property-facts-form">
                    ${this.renderPropertyFactsSections(propertyFactsData)}
                </div>

                <!-- Custom Property Facts Section -->
                <div class="mt-8">
                    <!-- Custom Facts List -->
                    <div id="custom-facts-list" class="space-y-3 mb-4">
                        <!-- Custom facts will be added here dynamically -->
                    </div>

                    <!-- Add Custom Fact Form (Initially Hidden) -->
                    <div id="custom-fact-form" class="hidden p-4 bg-blue-50 border border-blue-200 rounded-lg mb-4">
                        <h6 class="font-medium text-gray-900 mb-3">Add Custom Property Fact</h6>
                        <div class="space-y-3">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Property Fact</label>
                                <textarea id="custom-fact-content"
                                          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-persian-green focus:border-persian-green resize-none"
                                          rows="3"
                                          placeholder="Enter a useful fact about your property (e.g., 'The WiFi password is written on the router', 'Extra towels are in the hall closet')..."></textarea>
                            </div>
                            <div class="flex space-x-3">
                                <button onclick="propertySetupModal.saveCustomPropertyFact()"
                                        class="inline-flex items-center px-4 py-2 bg-persian-green text-white rounded-lg hover:bg-persian-green/90 transition-colors">
                                    <i class="fas fa-check mr-2"></i>
                                    Save Fact
                                </button>
                                <button onclick="propertySetupModal.cancelCustomPropertyFact()"
                                        class="inline-flex items-center px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                                    <i class="fas fa-times mr-2"></i>
                                    Cancel
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- Add Custom Fact Button -->
                    <button id="add-custom-fact-btn"
                            onclick="propertySetupModal.showCustomPropertyFactForm()"
                            class="inline-flex items-center px-4 py-2 border border-persian-green text-persian-green rounded-lg hover:bg-persian-green hover:text-white transition-colors">
                        <i class="fas fa-plus mr-2"></i>
                        Add Custom Property Fact
                    </button>
                </div>
            </div>
        `;

        // Load existing property facts if any
        this.loadExistingPropertyFacts();

        // Add auto-save listeners
        this.addPropertyFactsAutoSave();

        // Add Enter key support for custom fact inputs
        this.addCustomFactKeyListeners();
    }

    renderPropertyFactsSections(propertyFactsData) {
        let html = '';
        let questionIndex = 0;

        Object.keys(propertyFactsData).forEach(sectionKey => {
            const section = propertyFactsData[sectionKey];
            const sectionId = `section-${sectionKey}`;

            html += `
                <div class="border border-gray-200 rounded-lg">
                    <!-- Section Header -->
                    <div class="p-4 bg-gray-50 border-b border-gray-200 cursor-pointer"
                         onclick="propertySetupModal.togglePropertyFactsSection('${sectionId}')">
                        <div class="flex items-center justify-between">
                            <div class="flex items-center">
                                <i class="${section.icon} text-persian-green mr-3"></i>
                                <div>
                                    <h5 class="font-medium text-gray-900">${section.title}</h5>
                                    <p class="text-sm text-gray-600">${section.description}</p>
                                </div>
                            </div>
                            <div class="flex items-center space-x-2">
                                <span class="text-sm text-gray-500">${section.questions.length} questions</span>
                                <i class="fas fa-chevron-down transition-transform duration-200" id="${sectionId}-chevron"></i>
                            </div>
                        </div>
                    </div>

                    <!-- Section Content (Initially Hidden) -->
                    <div class="hidden p-4 space-y-4" id="${sectionId}-content">
                        ${section.questions.map(question => {
                            const currentIndex = questionIndex++;
                            return `
                                <div class="bg-white p-3 rounded border border-gray-100 property-fact-item" data-type="default">
                                    <label class="block text-sm font-medium text-gray-700 mb-2">
                                        ${question}
                                    </label>
                                    <textarea
                                        id="fact-${currentIndex}"
                                        name="fact-${currentIndex}"
                                        data-question="${question}"
                                        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-persian-green focus:border-persian-green resize-none"
                                        rows="2"
                                        placeholder="Enter your answer (optional)..."
                                    ></textarea>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            `;
        });

        return html;
    }

    togglePropertyFactsSection(sectionId) {
        const content = document.getElementById(`${sectionId}-content`);
        const chevron = document.getElementById(`${sectionId}-chevron`);

        if (content && chevron) {
            const isHidden = content.classList.contains('hidden');

            if (isHidden) {
                content.classList.remove('hidden');
                chevron.classList.add('rotate-180');
            } else {
                content.classList.add('hidden');
                chevron.classList.remove('rotate-180');
            }
        }
    }

    loadExistingPropertyFacts() {
        // Load existing property facts from setupData or propertyData
        if (this.setupData.propertyFacts && this.setupData.propertyFacts.length > 0) {
            const customFactsList = document.getElementById('custom-facts-list');

            this.setupData.propertyFacts.forEach((fact) => {
                const textarea = document.querySelector(`textarea[data-question="${fact.question}"]`);
                if (textarea) {
                    // Load answer for existing predefined questions
                    textarea.value = fact.answer || '';
                } else {
                    // This is a custom fact that needs to be recreated in the custom facts list
                    if (customFactsList && fact.question.startsWith('Custom Fact')) {
                        const customFactId = `custom-fact-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

                        const newFactHtml = `
                            <div class="bg-green-50 p-4 rounded-lg border border-green-200 custom-fact-item" data-fact-id="${customFactId}" data-type="custom">
                                <div class="flex justify-between items-start">
                                    <div class="flex-1">
                                        <div class="flex items-center mb-2">
                                            <i class="fas fa-plus-circle text-green-600 mr-2"></i>
                                            <span class="text-sm font-medium text-green-800">Custom Property Fact</span>
                                        </div>
                                        <p class="text-gray-700 text-sm">${fact.answer || ''}</p>
                                    </div>
                                    <button onclick="propertySetupModal.removeCustomPropertyFact('${customFactId}')"
                                            class="text-red-600 hover:text-red-800 ml-3 p-1 rounded hover:bg-red-100 transition-colors"
                                            title="Remove this fact">
                                        <i class="fas fa-trash-alt text-sm"></i>
                                    </button>
                                </div>
                            </div>
                        `;

                        customFactsList.insertAdjacentHTML('beforeend', newFactHtml);
                    }
                }
            });
        }
    }

    addPropertyFactsAutoSave() {
        const textareas = document.querySelectorAll('#property-facts-form textarea');
        textareas.forEach(textarea => {
            textarea.addEventListener('input', () => {
                // Debounced auto-save
                clearTimeout(this.propertyFactsAutoSaveTimeout);
                this.propertyFactsAutoSaveTimeout = setTimeout(() => {
                    this.savePropertyFactsData();
                }, 1000);
            });
        });
    }

    savePropertyFactsData() {
        const propertyFacts = [];

        // Save regular property facts questions
        const textareas = document.querySelectorAll('#property-facts-form textarea');
        textareas.forEach((textarea) => {
            const question = textarea.dataset.question;
            const answer = textarea.value.trim();

            if (answer) { // Only save non-empty answers
                propertyFacts.push({
                    question: question,
                    answer: answer
                });
            }
        });

        // Save custom property facts
        const customFacts = document.querySelectorAll('.custom-fact-item');
        customFacts.forEach((factElement, index) => {
            const factContent = factElement.querySelector('p')?.textContent?.trim();
            if (factContent) {
                propertyFacts.push({
                    question: `Custom Fact ${index + 1}`,
                    answer: factContent
                });
            }
        });

        this.setupData.propertyFacts = propertyFacts;
        console.log('Property facts data saved:', propertyFacts);

        // Also save to server immediately
        this.saveStepToServer(4, { propertyFacts: propertyFacts }).catch(error => {
            console.error('Error auto-saving property facts to server:', error);
        });
    }

    async savePropertyFacts() {
        this.savePropertyFactsData();

        // Property facts are optional, so always return true for validation
        // But still save to server for persistence
        const propertyFacts = this.setupData.propertyFacts || [];

        try {
            await this.saveStepToServer(4, { propertyFacts: propertyFacts });
            console.log('Property facts saved successfully');
        } catch (error) {
            console.error('Error saving property facts:', error);
            // Don't block progression even if server save fails
        }

        return true; // Always allow progression since facts are optional
    }

    showCustomPropertyFactForm() {
        const form = document.getElementById('custom-fact-form');
        const button = document.getElementById('add-custom-fact-btn');
        const contentInput = document.getElementById('custom-fact-content');

        if (form && button) {
            form.classList.remove('hidden');
            button.classList.add('hidden');
            contentInput?.focus();
        }
    }

    cancelCustomPropertyFact() {
        const form = document.getElementById('custom-fact-form');
        const button = document.getElementById('add-custom-fact-btn');
        const contentInput = document.getElementById('custom-fact-content');

        if (form && button) {
            form.classList.add('hidden');
            button.classList.remove('hidden');
            if (contentInput) {
                contentInput.value = '';
            }
        }
    }

    saveCustomPropertyFact() {
        const contentInput = document.getElementById('custom-fact-content');
        const content = contentInput?.value?.trim() || '';

        if (!content) {
            alert('Please enter a property fact before saving it.');
            contentInput?.focus();
            return;
        }

        // Generate unique ID for the custom fact
        const customFactId = `custom-fact-${Date.now()}`;

        // Add to the custom facts list
        const customFactsList = document.getElementById('custom-facts-list');
        if (customFactsList) {
            const newFactHtml = `
                <div class="bg-green-50 p-4 rounded-lg border border-green-200 custom-fact-item" data-fact-id="${customFactId}" data-type="custom">
                    <div class="flex justify-between items-start">
                        <div class="flex-1">
                            <div class="flex items-center mb-2">
                                <i class="fas fa-plus-circle text-green-600 mr-2"></i>
                                <span class="text-sm font-medium text-green-800">Custom Property Fact</span>
                            </div>
                            <p class="text-gray-700 text-sm">${content}</p>
                        </div>
                        <button onclick="propertySetupModal.removeCustomPropertyFact('${customFactId}')"
                                class="text-red-600 hover:text-red-800 ml-3 p-1 rounded hover:bg-red-100 transition-colors"
                                title="Remove this fact">
                            <i class="fas fa-trash-alt text-sm"></i>
                        </button>
                    </div>
                </div>
            `;

            customFactsList.insertAdjacentHTML('beforeend', newFactHtml);
        }

        // Save the data
        this.savePropertyFactsData();

        // Hide form and show button
        this.cancelCustomPropertyFact();

        console.log('Added custom property fact:', content);
    }

    removeCustomPropertyFact(factId) {
        const factElement = document.querySelector(`[data-fact-id="${factId}"]`);
        if (factElement) {
            factElement.remove();
            this.savePropertyFactsData();
        }
    }

    addCustomFactKeyListeners() {
        const contentInput = document.getElementById('custom-fact-content');

        if (contentInput) {
            contentInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.saveCustomPropertyFact();
                }
                if (e.key === 'Escape') {
                    e.preventDefault();
                    this.cancelCustomPropertyFact();
                }
            });
        }
    }

    removePropertyFact(index) {
        const factItems = document.querySelectorAll('.property-fact-item');
        if (factItems[index]) {
            // Only allow removal of custom facts
            if (factItems[index].dataset.type === 'custom') {
                factItems[index].remove();
                this.savePropertyFactsData();
            }
        }
    }

    loadReviewAndApproveStep(content) {
        content.innerHTML = `
            <div>
                <div class="mb-6">
                    <h4 class="text-lg font-semibold text-dark-purple mb-2">
                        <i class="fas fa-check-circle text-persian-green mr-2"></i>
                        Review and Approve
                    </h4>
                    <p class="text-gray-600">Review all the information you've provided and submit to finish your property setup. This is the time to make sure all the data is 100% correct and complete.</p>
                </div>

                <div class="space-y-6" id="review-sections">
                    <!-- Review sections will be loaded here -->
                </div>

                <div class="mt-8 p-4 bg-green-50 border border-green-200 rounded-lg">
                    <div class="flex items-start">
                        <i class="fas fa-info-circle text-green-500 mt-0.5 mr-3"></i>
                        <div class="text-sm text-green-700">
                            <strong>Ready to complete setup?</strong><br>
                            All the knowledge you've provided will be saved and used to help your guests.
                            You can always edit this information later from your property management dashboard.
                        </div>
                    </div>

                    <!-- Verification Checkbox -->
                    <div class="mt-4 pt-4 border-t border-green-200">
                        <label class="flex items-start cursor-pointer">
                            <input type="checkbox"
                                   id="data-verification-checkbox"
                                   class="mt-1 mr-3 h-4 w-4 text-persian-green border-gray-300 rounded focus:ring-persian-green"
                                   onchange="propertySetupModal.toggleCompleteButton()">
                            <span class="text-sm text-green-700">
                                <strong>I have reviewed and verified that all the data in every section above is 100% accurate and complete.</strong>
                                I understand this information will be used to help my guests.
                            </span>
                        </label>
                    </div>
                </div>
            </div>
        `;

        this.loadReviewSections();

        // Initially disable the Complete Setup button
        this.toggleCompleteButton();
    }

    toggleCompleteButton() {
        // Only apply validation logic on step 5 (Review step)
        if (this.currentStep !== this.totalSteps) {
            return;
        }

        const checkbox = document.getElementById('data-verification-checkbox');
        const nextBtn = document.getElementById('next-btn');

        if (checkbox && nextBtn) {
            const isChecked = checkbox.checked;
            nextBtn.disabled = !isChecked;

            if (isChecked) {
                nextBtn.className = 'px-4 py-2 bg-persian-green text-white rounded-lg hover:bg-persian-green/90 transition-colors';
            } else {
                nextBtn.className = 'px-4 py-2 bg-gray-300 text-gray-500 rounded-lg cursor-not-allowed';
            }
        }
    }

    loadReviewSections() {
        const container = document.getElementById('review-sections');
        if (!container) return;

        let html = '';

        // Section 1: Basic Information
        html += this.generateReviewSection(
            1,
            'Basic Information',
            'fas fa-info-circle',
            this.getBasicInfoSummary()
        );

        // Section 2: House Rules
        html += this.generateReviewSection(
            2,
            'House Rules',
            'fas fa-gavel',
            this.getHouseRulesSummary()
        );

        // Section 3: Emergency Information
        html += this.generateReviewSection(
            3,
            'Emergency Information',
            'fas fa-exclamation-triangle',
            this.getEmergencyInfoSummary()
        );

        // Section 4: Other Information
        html += this.generateReviewSection(
            4,
            'Other Information',
            'fas fa-clipboard-list',
            this.getPropertyFactsSummary()
        );

        container.innerHTML = html;
    }

    generateReviewSection(stepNumber, title, icon, summary) {
        return `
            <div class="bg-white border border-gray-200 rounded-lg p-6">
                <div class="flex items-center justify-between mb-4">
                    <h5 class="text-lg font-medium text-gray-900 flex items-center">
                        <i class="${icon} text-persian-green mr-2"></i>
                        ${title}
                    </h5>
                    <button onclick="propertySetupModal.editStep(${stepNumber})"
                            class="px-3 py-1 text-sm border border-persian-green text-persian-green rounded hover:bg-persian-green hover:text-white transition-colors">
                        <i class="fas fa-edit mr-1"></i>Edit
                    </button>
                </div>
                <div class="text-gray-600 text-sm">
                    ${summary}
                </div>
            </div>
        `;
    }

    getBasicInfoSummary() {
        // Always use propertyData as the source of truth since it contains the most up-to-date info
        const basicInfo = this.propertyData;

        console.log('Getting basic info summary from propertyData:', basicInfo);
        console.log('Property data keys:', Object.keys(basicInfo || {}));
        console.log('Property name:', basicInfo?.name);
        console.log('Property address:', basicInfo?.address);

        if (!basicInfo || Object.keys(basicInfo).length === 0) {
            console.log('No basic info found, returning empty message');
            return '<p class="text-gray-500 italic">No basic information provided yet.</p>';
        }

        // Build spaced sections similar to other review blocks
        const sections = [];

        // Basic property details
        let detailsBlock = '';
        if (basicInfo.name) detailsBlock += `<strong>Property Name:</strong> ${basicInfo.name}<br>`;
        if (basicInfo.address) detailsBlock += `<strong>Address:</strong> ${basicInfo.address}<br>`;
        if (basicInfo.description) detailsBlock += `<strong>Description:</strong> ${basicInfo.description}`;
        if (detailsBlock) sections.push(`<div>${detailsBlock}</div>`);

        // Schedule and calendar
        let scheduleBlock = '';
        if (basicInfo.icalUrl) scheduleBlock += `<strong>Calendar URL:</strong> Connected<br>`;
        if (basicInfo.checkInTime) scheduleBlock += `<strong>Check-in Time:</strong> ${basicInfo.checkInTime}<br>`;
        if (basicInfo.checkOutTime) scheduleBlock += `<strong>Check-out Time:</strong> ${basicInfo.checkOutTime}`;
        if (scheduleBlock) sections.push(`<div>${scheduleBlock}</div>`);

        // WiFi details
        if (basicInfo.wifiDetails?.network) {
            let wifiBlock = `<strong>WiFi Details:</strong> Network: ${basicInfo.wifiDetails.network}`;
            if (basicInfo.wifiDetails?.password) {
                wifiBlock += `, Password: ${basicInfo.wifiDetails.password}`;
            }
            sections.push(`<div>${wifiBlock}</div>`);
        }

        // Amenities details
        const amenities = basicInfo.amenities;
        if (amenities) {
            if (amenities.basic && amenities.basic.length > 0) {
                sections.push(`<div><strong>Basic Amenities:</strong> ${amenities.basic.join(', ')}</div>`);
            }

            if (amenities.appliances && amenities.appliances.length > 0) {
                let appliancesBlock = '<strong>Appliances:</strong><br>';
                amenities.appliances.forEach(appliance => {
                    appliancesBlock += `&nbsp;&nbsp;• ${appliance.name}`;
                    if (appliance.location) appliancesBlock += ` (${appliance.location})`;
                    if (appliance.brand || appliance.model) {
                        const brandModel = [appliance.brand, appliance.model].filter(Boolean).join(' ');
                        if (brandModel) appliancesBlock += ` - ${brandModel}`;
                    }
                    appliancesBlock += '<br>';
                });
                sections.push(`<div>${appliancesBlock}</div>`);
            }
        }

        const summary = sections.length > 0
            ? `<div class="space-y-2">${sections.join('')}</div>`
            : '<p class="text-gray-500 italic">No basic information provided yet.</p>';

        return summary;
    }

    getHouseRulesSummary() {
        const houseRules = this.setupData.houseRules;
        if (!houseRules || houseRules.length === 0) {
            return '<p class="text-gray-500 italic">No house rules configured.</p>';
        }

        const enabledRules = houseRules.filter(rule => rule.enabled);
        if (enabledRules.length === 0) {
            return '<p class="text-gray-500 italic">No house rules enabled.</p>';
        }

        let summary = `<strong>${enabledRules.length} house rules active:</strong><br><br>`;
        enabledRules.forEach(rule => {
            summary += `<strong>${rule.title}:</strong> ${rule.content || rule.description || 'No details provided'}<br><br>`;
        });

        return summary;
    }

    getEmergencyInfoSummary() {
        const emergencyInfo = this.setupData.emergencyInfo;
        if (!emergencyInfo || emergencyInfo.length === 0) {
            return '<p class="text-gray-500 italic">No emergency information configured.</p>';
        }

        const enabledInfo = emergencyInfo.filter(info => info.enabled);
        if (enabledInfo.length === 0) {
            return '<p class="text-gray-500 italic">No emergency information enabled.</p>';
        }

        let summary = `<strong>${enabledInfo.length} emergency procedures configured:</strong><br><br>`;
        enabledInfo.forEach(info => {
            summary += `<strong>${info.title}:</strong><br>`;
            if (info.instructions) {
                summary += `${info.instructions}<br>`;
            }
            if (info.location) {
                summary += `<em>Location: ${info.location}</em><br>`;
            }
            summary += '<br>';
        });

        return summary;
    }

    getPropertyFactsSummary() {
        const propertyFacts = this.setupData.propertyFacts;

        if (!propertyFacts || propertyFacts.length === 0) {
            return '<p class="text-gray-500 italic">No other information provided.</p>';
        }

        const answeredFacts = propertyFacts.filter(fact => fact.answer && fact.answer.trim());

        if (answeredFacts.length === 0) {
            return '<p class="text-gray-500 italic">No other information answered.</p>';
        }

        let summary = `<strong>${answeredFacts.length} other information items provided:</strong><br><br>`;
        summary += '<div class="space-y-2">';
        answeredFacts.forEach(fact => {
            // Show the answer content that will be fed to AI
            const answer = fact.answer.trim();
            const shortAnswer = answer.length > 100 ? answer.substring(0, 100) + '...' : answer;
            summary += `<div class="bg-gray-50 p-2 rounded text-sm">`;
            if (fact.question) {
                summary += `<strong>Q:</strong> ${fact.question}<br>`;
            }
            summary += `<strong>A:</strong> ${shortAnswer}`;
            summary += `</div>`;
        });
        summary += '</div>';

        return summary;
    }

    editStep(stepNumber) {
        // Save current step data before navigating
        this.saveCurrentStepData().then(() => {
            this.loadStep(stepNumber);
        });
    }

    async saveHouseRules() {
        console.log('Saving unified house rules...');

        // Collect all enabled rules from the unified section
        const allRules = [];
        const container = document.getElementById('house-rules-content');

        if (container && this.unifiedRulesData) {
            const checkboxes = container.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach((checkbox, index) => {
                if (checkbox.checked && this.unifiedRulesData[index]) {
                    const descTextarea = document.getElementById(`rule_content_${index}`);
                    const description = descTextarea ? descTextarea.value : '';

                    const rule = {
                        ...this.unifiedRulesData[index],
                        // Normalize on content; keep description for backward compatibility
                        content: description,
                        description: description,
                        enabled: true
                    };

                    // For imported rules without proper titles, use the description as title
                    if (!rule.title || rule.title === 'undefined') {
                        rule.title = description || rule.content || 'House Rule';
                    }

                    console.log(`House rule ${index}: title="${rule.title}", content="${description}"`);
                    allRules.push(rule);
                }
            });
        }

        // Save to setup data
        this.setupData.houseRules = allRules;

        console.log('House rules to save:', allRules);

        // Save to server
        const saved = await this.saveStepToServer(2, { houseRules: allRules });
        return saved;
    }



    async loadEmergencyInformation() {
        console.log('Loading emergency information...');

        // Check if we already have saved emergency info from user modifications
        if (this.setupData.emergencyInfo && this.setupData.emergencyInfo.length > 0) {
            console.log('✅ Using existing saved emergency info:', this.setupData.emergencyInfo.length);

            // Start with defaults only to avoid duplicating raw imported items
            const defaultEmergencyInfo = this.getDefaultEmergencyInfo();
            let allEmergencyInfo = [...defaultEmergencyInfo];

            // Overlay saved items (always enabled)
            this.setupData.emergencyInfo.forEach(savedItem => {
                const existingIndex = allEmergencyInfo.findIndex(item => item.id === savedItem.id);
                if (existingIndex >= 0) {
                    allEmergencyInfo[existingIndex] = { ...allEmergencyInfo[existingIndex], ...savedItem, enabled: true };
                } else {
                    allEmergencyInfo.push({ ...savedItem, enabled: true });
                }
            });

            // Sort for display (imported first)
            console.log('Final allEmergencyInfo before rendering:', allEmergencyInfo);
            this.renderEmergencyInformation(allEmergencyInfo);
            return;
        }

        // If no saved emergency info, load from original sources
        this.loadOriginalEmergencyInformation();
    }

    async loadOriginalEmergencyInformation() {
        console.log('Loading original emergency information from import data...');

        // Get default emergency information items
        const defaultEmergencyInfo = this.getDefaultEmergencyInfo();

        // Check for any imported emergency information
        const importedEmergencyInfo = this.getImportedEmergencyInfo();

        // Start with defaults and imported items (include existing custom items only for fresh loads)
        let allEmergencyInfo = this.mergeEmergencyInfo(defaultEmergencyInfo, importedEmergencyInfo, true);

        // If we have current emergency info from previous saves, merge it in
        if (this.currentEmergencyInfo && this.currentEmergencyInfo.length > 0) {
            console.log('Merging existing emergency info from current session:', this.currentEmergencyInfo);

            // Update the merged info with current session data
            this.currentEmergencyInfo.forEach(currentItem => {
                const existingIndex = allEmergencyInfo.findIndex(item => item.id === currentItem.id);
                if (existingIndex >= 0) {
                    // Update existing item
                    allEmergencyInfo[existingIndex] = currentItem;
                } else {
                    // Add new custom item
                    allEmergencyInfo.push(currentItem);
                }
            });
        }

        this.renderEmergencyInformation(allEmergencyInfo);
    }

    getDefaultEmergencyInfo() {
        return [
            {
                id: 'gas_leak',
                title: 'Gas Leak',
                instructions: 'Do not use electrical switches or open flames. Evacuate immediately and call gas company emergency line.',
                location: 'Gas shut-off valve location: ',
                enabled: false,
                type: 'default'
            },
            {
                id: 'water_leak',
                title: 'Water Leak',
                instructions: 'Turn off main water supply immediately. Contact property manager or emergency plumber.',
                location: 'Main water shut-off location: ',
                enabled: false,
                type: 'default'
            },
            {
                id: 'power_outage',
                title: 'Power Outage',
                instructions: 'Check circuit breaker first. If widespread outage, contact utility company.',
                location: 'Circuit breaker location: ',
                enabled: false,
                type: 'default'
            },
            {
                id: 'lockout',
                title: 'Lockout',
                instructions: 'Contact property manager or host immediately. Do not attempt to force entry.',
                location: '',
                enabled: false,
                type: 'default'
            },
            {
                id: 'severe_weather',
                title: 'Severe Weather',
                instructions: 'Stay indoors. Monitor local weather alerts. Know the location of safe areas.',
                location: 'Safe area location: ',
                enabled: false,
                type: 'default'
            },
            {
                id: 'carbon_monoxide',
                title: 'Carbon Monoxide Alarm',
                instructions: 'Evacuate immediately. Do not re-enter until cleared by professionals. Call 911.',
                location: '',
                enabled: false,
                type: 'default'
            },
            {
                id: 'first_aid',
                title: 'First Aid Kit',
                instructions: 'Basic first aid supplies for minor injuries.',
                location: 'First aid kit location: ',
                enabled: false,
                type: 'default'
            },
            {
                id: 'fire_extinguisher',
                title: 'Fire Extinguisher',
                instructions: 'For small fires only. Pull pin, aim at base of fire, squeeze handle, sweep side to side.',
                location: 'Fire extinguisher location: ',
                enabled: false,
                type: 'default'
            },
            {
                id: 'emergency_contacts',
                title: 'Emergency Contacts',
                instructions: 'Property Manager: [Phone]\nLocal Emergency: 911\nPoison Control: 1-800-222-1222',
                location: '',
                enabled: false,
                type: 'default'
            }
        ];
    }

    getImportedEmergencyInfo() {
        // Prefer curated imported items stored on property (already deduped/filtered server-side)
        const curated = Array.isArray(this.propertyData.emergencyInfo) ? this.propertyData.emergencyInfo : [];
        if (curated.length > 0) {
            return curated.map((item, index) => ({
                id: item.id || `imported_${index}`,
                title: item.title || item.type || 'Safety Information',
                instructions: item.instructions || item.description || '',
                location: item.location || '',
                enabled: item.enabled !== false, // default to true
                type: item.type || 'imported'
            }));
        }

        // Fallback: build from raw import arrays but filter and dedupe aggressively
        const importedSafety = this.propertyData.importData?.rawData?.extracted?.safety_info || [];
        const deepExtractedSafety = this.propertyData.importData?.rawData?.safety_info || [];
        const allImportedSafety = [...importedSafety, ...deepExtractedSafety];

        console.log('Imported safety info:', allImportedSafety);

        const filtered = this._filterAndDedupeImportedSafety(allImportedSafety);

        return filtered.map((item, index) => ({
            id: `imported_${index}`,
            title: item.title || item.type || 'Safety Information',
            instructions: item.description || item.instructions || '',
            location: item.location || '',
            enabled: true,
            type: 'imported'
        }));
    }

    mergeEmergencyInfo(defaultInfo, importedInfo, includeExistingCustom = true) {
        // Start with imported info (enabled by default)
        const merged = [...importedInfo];

        // Add any existing custom items from previous saves (only when safe to do so)
        if (includeExistingCustom) {
            const existingCustomItems = this.propertyData.emergencyInfo?.filter(item => item.type === 'custom') || [];
            merged.push(...existingCustomItems);
        }

        // Add default info that doesn't conflict
        defaultInfo.forEach(defaultItem => {
            const hasConflict = importedInfo.some(imported =>
                (imported.title || '').toLowerCase().includes((defaultItem.title || '').toLowerCase()) ||
                (defaultItem.title || '').toLowerCase().includes((imported.title || '').toLowerCase())
            );

            if (!hasConflict) {
                merged.push(defaultItem);
            }
        });

        return merged;
    }

    // Ensure imported emergency items are shown first, then defaults, then custom
    sortEmergencyInfoForDisplay(items) {
        if (!Array.isArray(items)) return items;
        return [...items].sort((a, b) => {
            const rank = (x) => x?.type === 'imported' ? 0 : (x?.type === 'default' ? 1 : 2);
            const ra = rank(a);
            const rb = rank(b);
            if (ra !== rb) return ra - rb;
            const ta = (a?.title || '').toLowerCase();
            const tb = (b?.title || '').toLowerCase();
            return ta.localeCompare(tb);
        });
    }

    renderEmergencyInformation(emergencyInfo) {
        const container = document.getElementById('emergency-info-content');
        if (!container) return;

        // Store emergency info for reference
        console.log('Setting currentEmergencyInfo in renderEmergencyInformation:', emergencyInfo);
        // Always sort for display so imported items appear first
        const orderedEmergencyInfo = this.sortEmergencyInfoForDisplay(emergencyInfo);
        this.currentEmergencyInfo = orderedEmergencyInfo;

        let html = '';

        // Add help text at the top
        html += `
            <div class="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <div class="flex items-start space-x-2">
                    <i class="fas fa-info-circle text-blue-600 mt-0.5"></i>
                    <div class="text-sm text-blue-800">
                        <p class="font-medium mb-1">Emergency Information Tips:</p>
                        <ul class="list-disc list-inside space-y-1 text-blue-700">
                            <li>Only enable information that applies to your property</li>
                            <li>Customize instructions to be specific to your location</li>
                            <li>Include exact locations for safety equipment and shut-offs</li>
                            <li>Keep emergency contact information up to date</li>
                        </ul>
                    </div>
                </div>
            </div>
        `;

        // Separate default/imported items from custom items (preserving sorted order)
        const defaultAndImportedItems = orderedEmergencyInfo.filter(info => info.type !== 'custom');
        const customItems = orderedEmergencyInfo.filter(info => info.type === 'custom');

        if (defaultAndImportedItems.length === 0 && customItems.length === 0) {
            html += `
                <div class="text-center py-8 text-gray-500">
                    <i class="fas fa-info-circle text-4xl mb-4"></i>
                    <p>No emergency information available. You can enable and customize the default options below.</p>
                </div>
            `;
        } else {
            // Render default and imported items first
            if (defaultAndImportedItems.length > 0) {
                html += '<div class="space-y-4" id="emergency-items-container">';

                defaultAndImportedItems.forEach((info, originalIndex) => {
                    // Find the original index in the full array
                    const index = orderedEmergencyInfo.findIndex(item => item.id === info.id);
                    html += this.generateEmergencyItemHTML(info, index);
                });

                html += '</div>';
            }

            // Render custom items at the bottom
            if (customItems.length > 0) {
                html += `
                    <div class="mt-8">
                        <h5 class="text-md font-medium text-gray-900 mb-4 flex items-center">
                            <i class="fas fa-plus-circle text-green-600 mr-2"></i>
                            Custom Emergency Items
                        </h5>
                        <div class="space-y-4" id="custom-emergency-items-container">
                `;

                customItems.forEach((info, originalIndex) => {
                    // Find the original index in the full array
                    const index = orderedEmergencyInfo.findIndex(item => item.id === info.id);
                    html += this.generateEmergencyItemHTML(info, index);
                });

                html += '</div></div>';
            }
        }

        // Add "Add Custom Emergency Item" button at the bottom
        html += `
            <div class="mt-6 mb-6">
                <button onclick="propertySetupModal.addCustomEmergencyItem()"
                        class="inline-flex items-center px-4 py-2 border border-persian-green text-persian-green rounded-lg hover:bg-persian-green hover:text-white transition-colors">
                    <i class="fas fa-plus mr-2"></i>
                    Add Custom Emergency Item
                </button>
            </div>
        `;

        container.innerHTML = html;

        // Add dynamic saving event listeners
        this.addEmergencyInfoEventListeners();
    }

    generateEmergencyItemHTML(info, index) {
        const isImported = info.type === 'imported';
        const isCustom = info.type === 'custom';
        const sourceClass = isImported ? 'bg-blue-100 text-blue-800' :
                           isCustom ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800';
        const sourceLabel = isImported ? 'Imported' : isCustom ? 'Custom' : 'Default';
        const borderClass = isImported ? 'border-blue-200 bg-blue-50' :
                           isCustom ? 'border-green-200 bg-green-50' : 'border-gray-200';

        return `
            <div class="border rounded-lg p-4 ${borderClass}" data-emergency-index="${index}">
                <div class="flex items-start space-x-3">
                    <input type="checkbox"
                           id="emergency_${index}"
                           data-emergency-id="${info.id}"
                           ${info.enabled ? 'checked' : ''}
                           class="mt-1 h-4 w-4 text-persian-green border-gray-300 rounded focus:ring-persian-green">
                    <div class="flex-1">
                        <div class="flex items-center justify-between mb-3">
                            <div class="flex items-center space-x-2">
                                ${isCustom ? `
                                    <input type="text"
                                           id="emergency_title_${index}"
                                           value="${info.title}"
                                           class="font-medium text-gray-900 px-2 py-1 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-persian-green focus:border-persian-green max-w-xs"
                                           placeholder="Emergency Title">
                                ` : `
                                    <label for="emergency_${index}" class="font-medium text-gray-900 cursor-pointer">
                                        ${info.title}
                                    </label>
                                `}
                                <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${sourceClass}">
                                    ${sourceLabel}
                                </span>
                            </div>
                            ${isCustom ? `
                                <button onclick="propertySetupModal.removeCustomEmergencyItem(${index})"
                                        class="text-red-600 hover:text-red-800 p-1"
                                        title="Remove custom item">
                                    <i class="fas fa-trash-alt"></i>
                                </button>
                            ` : ''}
                        </div>

                        <div class="space-y-3">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Instructions</label>
                                <textarea id="emergency_instructions_${index}"
                                          class="w-full p-2 border border-gray-300 rounded-md text-sm resize-none"
                                          rows="3"
                                          placeholder="Enter emergency instructions...">${info.instructions}</textarea>
                            </div>

                            ${info.location !== undefined ? `
                                <div>
                                    <label class="block text-sm font-medium text-gray-700 mb-1">Location/Additional Info</label>
                                    <input type="text"
                                           id="emergency_location_${index}"
                                           class="w-full p-2 border border-gray-300 rounded-md text-sm"
                                           placeholder="Enter location or additional information..."
                                           value="${info.location}">
                                </div>
                            ` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    addEmergencyInfoEventListeners() {
        const container = document.getElementById('emergency-info-content');
        if (!container) return;

        // Add event listeners for checkboxes
        const checkboxes = container.querySelectorAll('input[type="checkbox"]');
        checkboxes.forEach((checkbox, index) => {
            checkbox.addEventListener('change', () => {
                console.log(`Emergency checkbox ${index} changed to:`, checkbox.checked);
                this.updateEmergencyItemEnabled(index, checkbox.checked);
                this.saveEmergencyInfoDynamically();
            });
        });

        // Add event listeners for text inputs and textareas
        const textInputs = container.querySelectorAll('input[type="text"], textarea');
        textInputs.forEach((input) => {
            input.addEventListener('input', () => {
                console.log('Emergency info text changed:', input.id);
                this.saveEmergencyInfoDynamically();
            });
        });
    }

    updateEmergencyItemEnabled(index, enabled) {
        if (this.currentEmergencyInfo && this.currentEmergencyInfo[index]) {
            this.currentEmergencyInfo[index].enabled = enabled;
            console.log(`Updated emergency item ${index} enabled status:`, enabled);
        }
    }

    saveEmergencyInfoDynamically() {
        // Debounced auto-save
        clearTimeout(this.emergencyInfoAutoSaveTimeout);
        this.emergencyInfoAutoSaveTimeout = setTimeout(() => {
            console.log('Auto-saving emergency info...');

            // Update current emergency info with form data
            this.updateCurrentEmergencyInfoFromForm();

            // Save to setupData and server
            this.setupData.emergencyInfo = this.currentEmergencyInfo || [];
            this.saveStepToServer(3, { emergencyInfo: this.setupData.emergencyInfo }).catch(error => {
                console.error('Error auto-saving emergency info to server:', error);
            });
        }, 1000);
    }

    updateCurrentEmergencyInfoFromForm() {
        if (!this.currentEmergencyInfo) return;

        const container = document.getElementById('emergency-info-content');
        if (!container) return;

        this.currentEmergencyInfo.forEach((item, index) => {
            const checkbox = document.getElementById(`emergency_${index}`);
            const instructionsTextarea = document.getElementById(`emergency_instructions_${index}`);
            const locationInput = document.getElementById(`emergency_location_${index}`);
            const titleInput = document.getElementById(`emergency_title_${index}`);

            if (checkbox) {
                item.enabled = checkbox.checked;
            }
            if (instructionsTextarea) {
                item.instructions = instructionsTextarea.value.trim();
            }
            if (locationInput) {
                item.location = locationInput.value.trim();
            }
            if (titleInput) {
                item.title = titleInput.value.trim();
            }
        });

        console.log('Updated current emergency info from form:', this.currentEmergencyInfo);
    }

    saveEmergencyInformation() {
        console.log('Saving emergency information...');

        // Clear any previous validation errors
        this.clearValidationErrors();

        // Collect all enabled emergency info from the form
        const allEmergencyInfo = [];
        const validationErrors = [];
        const container = document.getElementById('emergency-info-content');

        if (container) {
            const checkboxes = container.querySelectorAll('input[type="checkbox"]');
            console.log('Found checkboxes:', checkboxes.length);
            checkboxes.forEach((checkbox, index) => {
                console.log(`Checkbox ${index}: checked=${checkbox.checked}, id=${checkbox.id}`);
                if (checkbox.checked) {
                    console.log(`Processing enabled checkbox ${index}`);
                }
                if (checkbox.checked) {
                    const instructionsTextarea = document.getElementById(`emergency_instructions_${index}`);
                    const locationInput = document.getElementById(`emergency_location_${index}`);

                    // For custom items, get title from input field; for others, get from label
                    const titleInput = document.getElementById(`emergency_title_${index}`);
                    const titleElement = document.querySelector(`label[for="emergency_${index}"]`);

                    const title = titleInput ? titleInput.value.trim() :
                                 titleElement ? titleElement.textContent.trim() : '';
                    const instructions = instructionsTextarea ? instructionsTextarea.value.trim() : '';

                    // Basic validation: enabled items should have title and instructions
                    if (!title) {
                        validationErrors.push(`Emergency item ${index + 1} is enabled but missing title`);
                        if (titleInput) {
                            this.highlightRequiredField(`emergency_title_${index}`);
                        }
                    } else {
                        if (titleInput) {
                            this.clearFieldHighlight(`emergency_title_${index}`);
                        }
                    }

                    if (!instructions) {
                        validationErrors.push(`"${title || 'Emergency item'}" is enabled but missing instructions`);
                        this.highlightRequiredField(`emergency_instructions_${index}`);
                    } else {
                        this.clearFieldHighlight(`emergency_instructions_${index}`);
                    }

                    // Determine the type based on the original data
                    const originalItem = this.currentEmergencyInfo && this.currentEmergencyInfo[index];
                    const itemType = originalItem ? originalItem.type : 'default';

                    const emergencyInfo = {
                        id: checkbox.dataset.emergencyId || `emergency_${index}`,
                        title: title,
                        instructions: instructions,
                        location: locationInput ? locationInput.value.trim() : '',
                        enabled: true,
                        type: itemType
                    };

                    allEmergencyInfo.push(emergencyInfo);
                }
            });
        }

        // Show validation errors if any
        if (validationErrors.length > 0) {
            this.showValidationErrors(validationErrors);
            return Promise.resolve(false);
        }

        // Save to setup data and preserve in current session
        this.setupData.emergencyInfo = allEmergencyInfo;
        console.log('Setting currentEmergencyInfo in saveEmergencyInformation:', allEmergencyInfo);
        this.currentEmergencyInfo = allEmergencyInfo; // Preserve for navigation

        console.log('Emergency information to save:', allEmergencyInfo);

        // Save to server
        return this.saveStepToServer(3, { emergencyInfo: allEmergencyInfo });
    }

    addCustomEmergencyItem() {
        console.log('Adding custom emergency item...');

        // Create a new custom emergency item
        const newCustomItem = {
            id: `custom_${Date.now()}`,
            title: '',
            instructions: '',
            location: '',
            enabled: true,
            type: 'custom'
        };

        // Add to current emergency info
        if (!this.currentEmergencyInfo) {
            this.currentEmergencyInfo = [];
        }
        this.currentEmergencyInfo.push(newCustomItem);

        // Re-render the emergency information
        this.renderEmergencyInformation(this.currentEmergencyInfo);

        // Focus on the new item's title field
        const newIndex = this.currentEmergencyInfo.length - 1;
        setTimeout(() => {
            const titleInput = document.getElementById(`emergency_title_${newIndex}`);
            if (titleInput) {
                titleInput.focus();
                titleInput.select();
            }
        }, 100);
    }

    removeCustomEmergencyItem(index) {
        console.log(`Removing custom emergency item at index ${index}...`);

        if (!this.currentEmergencyInfo || index < 0 || index >= this.currentEmergencyInfo.length) {
            console.error('Invalid index for removing emergency item');
            return;
        }

        const item = this.currentEmergencyInfo[index];

        // Only allow removal of custom items
        if (item.type !== 'custom') {
            console.error('Can only remove custom emergency items');
            return;
        }

        // Confirm removal if the item has content
        if (item.title.trim() || item.instructions.trim()) {
            if (!confirm(`Are you sure you want to remove "${item.title || 'this custom emergency item'}"?`)) {
                return;
            }
        }

        // Remove the item
        this.currentEmergencyInfo.splice(index, 1);

        // Re-render the emergency information
        this.renderEmergencyInformation(this.currentEmergencyInfo);
    }



    // House Rules management methods
    getDefaultRulesData() {
        return [
            {
                id: 'smoking',
                title: 'Smoking',
                content: 'No smoking anywhere on the property',
                enabled: false,
                type: 'default'
            },
            {
                id: 'parties',
                title: 'Parties and Events',
                content: 'No parties or events permitted',
                enabled: false,
                type: 'default'
            },
            {
                id: 'quiet_hours',
                title: 'Quiet Hours',
                content: 'Keep noise to a minimum between 10 PM and 8 AM',
                enabled: false,
                type: 'default'
            },
            {
                id: 'pets',
                title: 'Pets',
                content: 'No pets allowed unless specifically approved',
                enabled: false,
                type: 'default'
            },
            {
                id: 'occupancy',
                title: 'Property Capacity',
                content: 'Respect the maximum occupancy limit',
                enabled: false,
                type: 'default'
            },
            {
                id: 'commercial_photography',
                title: 'Commercial Photography',
                content: 'No commercial photography or filming without prior approval',
                enabled: false,
                type: 'default'
            },
            {
                id: 'shoes',
                title: 'Shoes in Property',
                content: 'Remove shoes when entering the property',
                enabled: false,
                type: 'default'
            }
        ];
    }

    adjustDefaultRulesWithImported(defaultRules) {
        // Get imported rules to check for conflicts/updates
        const extractedRules = this.propertyData.importData?.rawData?.extracted?.house_rules || [];
        const deepExtractedRules = this.propertyData.importData?.rawData?.house_rules || [];
        const allImportedRules = [...extractedRules, ...deepExtractedRules];

        console.log('🔧 Adjusting default rules with imported rules:', allImportedRules);

        // First, extract and apply check-in/check-out times to property data
        this.extractAndApplyTimesFromRules(allImportedRules);

        // Then check each imported rule against default rules for replacement
        allImportedRules.forEach(importedRule => {
            const description = importedRule.description?.toLowerCase() || '';
            const originalDescription = importedRule.description || '';

            // Check for quiet hours with specific times
            if (description.includes('quiet') && (description.includes('am') || description.includes('pm') || description.includes(':'))) {
                const quietRule = defaultRules.find(rule => rule.id === 'quiet_hours');
                if (quietRule) {
                    quietRule.description = originalDescription;
                    quietRule.title = importedRule.title || 'Quiet hours';
                    console.log('✅ Updated quiet hours rule with imported content:', quietRule.description);
                }
            }

            // Check for check-in times - update rule but time already extracted to property
            else if (description.includes('check') && description.includes('in') &&
                     (description.includes('am') || description.includes('pm') || description.includes(':'))) {
                const checkinRule = defaultRules.find(rule => rule.id === 'check_in_time');
                if (checkinRule) {
                    checkinRule.description = originalDescription;
                    checkinRule.title = importedRule.title || 'Check-in time';
                    console.log('✅ Updated check-in rule with imported content:', checkinRule.description);
                }
            }

            // Check for check-out times - update rule but time already extracted to property
            else if (description.includes('check') && description.includes('out') &&
                     (description.includes('am') || description.includes('pm') || description.includes(':'))) {
                const checkoutRule = defaultRules.find(rule => rule.id === 'check_out_time');
                if (checkoutRule) {
                    checkoutRule.description = originalDescription;
                    checkoutRule.title = importedRule.title || 'Check-out time';
                    console.log('✅ Updated check-out rule with imported content:', checkoutRule.description);
                }
            }

            // Check for guest limits
            else if (description.includes('guest') && (description.includes('maximum') || description.includes('max') || /\d+/.test(description))) {
                const guestRule = defaultRules.find(rule => rule.id === 'max_guests');
                if (guestRule) {
                    guestRule.description = originalDescription;
                    guestRule.title = importedRule.title || 'Maximum guests';
                    console.log('✅ Updated guest limit rule with imported content:', guestRule.description);
                }
            }

            // Check for smoking rules
            else if (description.includes('smok') || description.includes('no smoking')) {
                const smokingRule = defaultRules.find(rule => rule.id === 'no_smoking');
                if (smokingRule) {
                    smokingRule.description = originalDescription;
                    smokingRule.title = importedRule.title || 'No smoking';
                    console.log('✅ Updated smoking rule with imported content:', smokingRule.description);
                }
            }

            // Check for party/event rules
            else if (description.includes('part') || description.includes('event') || description.includes('gathering')) {
                const partyRule = defaultRules.find(rule => rule.id === 'no_parties');
                if (partyRule) {
                    partyRule.description = originalDescription;
                    partyRule.title = importedRule.title || 'No parties or events';
                    console.log('✅ Updated party rule with imported content:', partyRule.description);
                }
            }

            // Check for pet rules
            else if (description.includes('pet') || description.includes('animal') || description.includes('dog') || description.includes('cat')) {
                const petRule = defaultRules.find(rule => rule.id === 'no_pets');
                if (petRule) {
                    petRule.description = originalDescription;
                    petRule.title = importedRule.title || 'No pets';
                    console.log('✅ Updated pet rule with imported content:', petRule.description);
                }
            }
        });

        return defaultRules;
    }

    extractAndApplyTimesFromRules(importedRules) {
        console.log('🕐 Extracting check-in/check-out times from imported rules...');

        importedRules.forEach(rule => {
            const description = rule.description?.toLowerCase() || '';
            const originalDescription = rule.description || '';

            // Extract check-in times
            if (description.includes('check') && description.includes('in')) {
                const extractedTime = this.extractTimeFromText(originalDescription);
                if (extractedTime) {
                    console.log(`🕐 Extracted check-in time: ${extractedTime} from rule: "${originalDescription}"`);
                    this.propertyData.checkInTime = extractedTime;

                    // Update the basic info form if it's visible
                    const checkinInput = document.getElementById('checkin-time');
                    if (checkinInput) {
                        checkinInput.value = extractedTime;
                        console.log('✅ Updated check-in time input field');
                    }
                }
            }

            // Extract check-out times
            if (description.includes('check') && description.includes('out')) {
                const extractedTime = this.extractTimeFromText(originalDescription);
                if (extractedTime) {
                    console.log(`🕐 Extracted check-out time: ${extractedTime} from rule: "${originalDescription}"`);
                    this.propertyData.checkOutTime = extractedTime;

                    // Update the basic info form if it's visible
                    const checkoutInput = document.getElementById('checkout-time');
                    if (checkoutInput) {
                        checkoutInput.value = extractedTime;
                        console.log('✅ Updated check-out time input field');
                    }
                }
            }
        });
    }

    extractTimeFromText(text) {
        // Try to extract time in various formats
        const timePatterns = [
            /(\d{1,2}):(\d{2})\s*(AM|PM)/i,           // 3:00 PM, 11:30 AM
            /(\d{1,2})\s*(AM|PM)/i,                   // 3 PM, 11 AM
            /(\d{1,2}):(\d{2})/,                      // 15:00, 23:30 (24-hour)
            /after\s+(\d{1,2}):(\d{2})\s*(AM|PM)/i,   // after 3:00 PM
            /before\s+(\d{1,2}):(\d{2})\s*(AM|PM)/i,  // before 11:00 AM
            /(\d{1,2})\s*:\s*(\d{2})\s*(AM|PM)/i      // 3 : 00 PM (with spaces)
        ];

        for (const pattern of timePatterns) {
            const match = text.match(pattern);
            if (match) {
                let hour = parseInt(match[1]);
                let minute = match[2] ? parseInt(match[2]) : 0;
                const ampm = match[3]?.toUpperCase();

                // Convert to 24-hour format
                if (ampm === 'PM' && hour !== 12) {
                    hour += 12;
                } else if (ampm === 'AM' && hour === 12) {
                    hour = 0;
                }

                // Format as HH:MM
                return `${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;
            }
        }

        return null;
    }

    // Amenity management methods
    addBasicAmenity() {
        if (!this.propertyData.amenities) this.propertyData.amenities = { basic: [], appliances: [] };
        // Add an empty amenity that will show as an input field
        this.propertyData.amenities.basic.push('');
        this.loadAmenitiesSection();

        // Focus on the new input field after a short delay
        setTimeout(() => {
            const inputs = document.querySelectorAll('#basic-amenities input[type="text"]');
            const lastInput = inputs[inputs.length - 1];
            if (lastInput) {
                lastInput.focus();
            }
        }, 100);
    }

    async loadUnifiedRules() {
        console.log('🔧 Loading unified rules section...');

        // Build an import signature so we can invalidate stale saved rules when import data changes
        const extractedLen = this.propertyData.importData?.rawData?.extracted?.house_rules?.length || 0;
        const deepLen = this.propertyData.importData?.rawData?.house_rules?.length || 0;
        const ocrMainLen = (this.propertyData.importData?.rawData?.ocr_raw?.house_rules_ocr_main?.length
            || this.propertyData.importData?.rawData?.house_rules_ocr_main?.length || 0);
        const ocrAddLen = (this.propertyData.importData?.rawData?.ocr_raw?.house_rules_ocr_additional?.length
            || this.propertyData.importData?.rawData?.house_rules_ocr_additional?.length || 0);
        const importSignature = JSON.stringify({ extractedLen, deepLen, ocrMainLen, ocrAddLen });

        if (this.setupData.importSignature && this.setupData.importSignature !== importSignature) {
            console.log('♻️ Import data changed; discarding previously saved house rules to avoid duplication.');
            this.setupData.houseRules = [];
        }
        this.setupData.importSignature = importSignature;

        // Check if we already have saved house rules from user modifications
        if (this.setupData.houseRules && this.setupData.houseRules.length > 0) {
            console.log('✅ Using existing saved house rules:', this.setupData.houseRules.length);

            // Show ONLY the saved rules to avoid cluttering with disabled imported/default items
            const savedOnly = this.setupData.houseRules.map((r, idx) => ({
                id: r.id || `saved_${idx}`,
                title: r.title || this.extractRuleTitle(r.content || r.description || 'House Rule'),
                description: r.description || r.content || '',
                content: r.content || r.description || '',
                enabled: true,
                type: r.type || 'rule',
                source: r.source || 'imported'
            }));

            // Preserve order: imported first (all of these), then any custom added later
            this.unifiedRulesData = savedOnly;
            this.renderUnifiedRulesSection(this.unifiedRulesData);
            return;
        }

        // If no saved rules, load from original sources
        await this.loadOriginalUnifiedRules();
    }

    async loadOriginalUnifiedRules() {
        console.log('🔧 Loading original unified rules from import data...');

        // Get imported rules from multiple sources
        const extractedRules = this.propertyData.importData?.rawData?.extracted?.house_rules || [];
        const deepExtractedRules = this.propertyData.importData?.rawData?.house_rules || [];

        // Include OCR-derived rules if present (main and additional)
        const ocrMain = (this.propertyData.importData?.rawData?.ocr_raw?.house_rules_ocr_main
            || this.propertyData.importData?.rawData?.house_rules_ocr_main
            || this.propertyData.importData?.rawData?.house_rules_ocr
            || []);
        const ocrAdditional = (this.propertyData.importData?.rawData?.ocr_raw?.house_rules_ocr_additional
            || this.propertyData.importData?.rawData?.house_rules_ocr_additional
            || []);
        const ocrCombined = [...ocrMain, ...ocrAdditional].map(r => ({
            title: r.title || 'House Rule',
            description: (r.content || r.description || '').trim(),
            content: (r.content || r.description || '').trim(),
            type: r.type || 'rule',
            source: 'imported'
        })).filter(r => r.description);

        // Combine and deduplicate rules to prevent duplicates
        let rawCombinedRules = [...extractedRules, ...deepExtractedRules, ...ocrCombined];

        // Normalize helper for semantic dedupe (does not mutate display text)
        const normalizeRuleText = (text) => {
            let t = (text || '').toLowerCase();
            t = t.replace(/\u2026|\.\.\./g, ''); // ellipses
            t = t.replace(/\s+/g, ' ').trim();
            t = t.replace(/\s*:\s*/g, ': ');
            // Collapse common synonyms
            t = t.replace(/no parties or events/g, 'no parties');
            t = t.replace(/no events/g, 'no parties');
            t = t.replace(/no smoking(\.|$)/g, 'no smoking');
            t = t.replace(/pets not allowed/g, 'no pets');
            t = t.replace(/no pets allowed/g, 'no pets');
            return t;
        };

        const _seenContents = new Set();
        rawCombinedRules = rawCombinedRules.filter(r => {
            const displayText = (r.content || r.description || '').trim();
            const key = normalizeRuleText(displayText);
            if (!key) return false;
            if (_seenContents.has(key)) return false;
            _seenContents.add(key);
            return true; // preserve original casing/content
        });

        // Enhance quiet-hours: label and prefix time windows when needed
        const timeWindowRegex = /(\b\d{1,2}(?::\s?\d{2})?\s?(?:am|pm)\b)\s*(?:-|–|to)\s*(\b\d{1,2}(?::\s?\d{2})?\s?(?:am|pm)\b)/i;
        rawCombinedRules = rawCombinedRules.map(r => {
            const text = (r.content || r.description || '');
            const lc = text.toLowerCase();
            const isCheckInOut = lc.includes('check-in') || lc.includes('check in') || lc.includes('check-out') || lc.includes('check out');
            const looksQuiet = lc.includes('quiet') || lc.includes('noise');
            const hasTimeWindow = timeWindowRegex.test(text);
            if (!isCheckInOut && (looksQuiet || hasTimeWindow)) {
                if (!r.title || r.title.toLowerCase().includes('during your stay') || r.title.toLowerCase() === 'none') {
                    r.title = 'Quiet Hours';
                }
                if (hasTimeWindow && !/^\s*quiet\s*hours/i.test(text)) {
                    r.content = `Quiet hours: ${text.trim()}`;
                    r.description = r.description || r.content;
                }
            }
            return r;
        });

        console.log('🔍 Debugging imported rules:');
        console.log('  - extractedRules:', extractedRules);
        console.log('  - deepExtractedRules:', deepExtractedRules);
        console.log('  - ocrCombined:', ocrCombined);
        console.log('  - allImportedRules:', rawCombinedRules);
        console.log('  - propertyData.importData:', this.propertyData.importData);
        console.log('  - propertyData.importData?.rawData:', this.propertyData.importData?.rawData);

        // If no rules found in import data, try to fetch from knowledge items as fallback
        if (rawCombinedRules.length === 0) {
            console.log('No rules in import data, checking knowledge items...');
            try {
                const response = await fetch(`/api/knowledge-items?propertyId=${this.propertyId}`);
                if (response.ok) {
                    const knowledgeData = await response.json();
                    const ruleItems = knowledgeData.items?.filter(item =>
                        item.type === 'rule' &&
                        item.tags?.includes('imported')
                    ) || [];

                    console.log('Found rule items in knowledge:', ruleItems);

                    // Debug each rule item
                    ruleItems.forEach((item, index) => {
                        console.log(`  Rule ${index + 1}:`, {
                            type: item.type,
                            content: item.content,
                            tags: item.tags
                        });
                    });

                    // Convert knowledge items to rule format
                    const knowledgeRules = ruleItems.map(item => ({
                        title: this.extractRuleTitle(item.content),
                        description: item.content,
                        enabled: true,
                        type: 'rule',
                        source: 'knowledge_items'
                    }));

                    rawCombinedRules = knowledgeRules;
                }
            } catch (error) {
                console.error('Error fetching knowledge items:', error);
            }
        }

        // Filter out invalid imported rules
        const validImportedRules = this.filterValidRules(rawCombinedRules);
        console.log(`Filtered to ${validImportedRules.length} valid imported rules`);

        // Get default rules and filter out conflicts
        const defaultRules = this.getDefaultRulesData();
        const filteredDefaultRules = this.filterDefaultRulesForConflicts(defaultRules, validImportedRules);

        console.log(`Using ${filteredDefaultRules.length} default rules (${defaultRules.length - filteredDefaultRules.length} filtered out due to conflicts)`);

        // Combine rules: imported rules first (enabled), then default rules (disabled)
        const combinedRules = [
            ...validImportedRules.map(rule => ({ ...rule, enabled: true, source: 'imported' })),
            ...filteredDefaultRules.map(rule => ({ ...rule, enabled: false, source: 'default' }))
        ];

        // Enforce display order: Imported first, then defaults, then custom (if any are added later)
        const orderedRules = this.sortRulesForDisplay(combinedRules);

        console.log(`Total unified rules: ${combinedRules.length}`);

        // Store unified rules data for reuse
        this.unifiedRulesData = orderedRules;

        // Render unified rules section
        this.renderUnifiedRulesSection(orderedRules);
    }

    processBeforeYouLeaveRules(rules) {
        /**
         * Find and concatenate "Before you leave" rules into a single rule
         * This improves AI responses by providing comprehensive checkout instructions
         */
        const beforeYouLeaveRules = [];
        const otherRules = [];

        rules.forEach(rule => {
            if (!rule || !rule.description) {
                otherRules.push(rule);
                return;
            }

            const description = rule.description.toLowerCase();
            const title = (rule.title || '').toLowerCase();

            // Check if this is a "Before you leave" rule
            if (description.includes('before you leave') ||
                description.includes('before leaving') ||
                description.includes('when you leave') ||
                title.includes('before you leave') ||
                title.includes('before leaving')) {
                beforeYouLeaveRules.push(rule);
            } else {
                otherRules.push(rule);
            }
        });

        // If we found "Before you leave" rules, concatenate them
        if (beforeYouLeaveRules.length > 0) {
            console.log(`🔗 Found ${beforeYouLeaveRules.length} "Before you leave" rules, concatenating...`);

            // Extract the actual instructions (remove "Before you leave" prefix)
            const instructions = beforeYouLeaveRules.map(rule => {
                let instruction = rule.description;

                // Remove common prefixes
                instruction = instruction.replace(/^before you leave[,:]\s*/i, '');
                instruction = instruction.replace(/^before leaving[,:]\s*/i, '');
                instruction = instruction.replace(/^when you leave[,:]\s*/i, '');

                // Clean up and ensure proper formatting
                instruction = instruction.trim();
                if (instruction && !instruction.endsWith('.') && !instruction.endsWith(',')) {
                    instruction += '.';
                }

                return instruction;
            }).filter(instruction => instruction.length > 0);

            // Create concatenated rule
            if (instructions.length > 0) {
                const concatenatedRule = {
                    id: 'before_you_leave_combined',
                    title: 'Before you leave',
                    description: `Before you leave, ${instructions.join(' ').replace(/\.\s+/g, ', ').replace(/,$/, '.')}`,
                    content: `Before you leave, ${instructions.join(' ').replace(/\.\s+/g, ', ').replace(/,$/, '.')}`,
                    type: 'imported'
                };

                console.log('✅ Created concatenated "Before you leave" rule:', concatenatedRule.description);
                otherRules.push(concatenatedRule);
            }
        }

        return otherRules;
    }

    deduplicateRules(rules) {
        /**
         * Deduplicate house rules based on description content
         * This prevents the same rule from appearing multiple times
         */
        const seen = new Set();
        const deduplicated = [];

        rules.forEach(rule => {
            if (!rule) return;

            // Prefer content, fallback to description
            const text = (rule.content || rule.description || '').trim();
            if (!text) return;

            // Create a normalized key for comparison
            const normalized = text.toLowerCase();

            if (!seen.has(normalized)) {
                seen.add(normalized);
                // Ensure both fields are populated for downstream logic
                deduplicated.push({ ...rule, description: rule.description || text, content: rule.content || text });
            } else {
                console.log(`🚫 Filtered duplicate rule: "${text}"`);
            }
        });

        console.log(`📋 Deduplicated rules: ${rules.length} → ${deduplicated.length}`);
        return deduplicated;
    }

    filterValidRules(rules) {
        return rules.filter(rule => {
            const rawText = (rule.content || rule.description || '').trim();
            const description = rawText.toLowerCase();
            const titleText = (rule.title || '').trim().toLowerCase();

            // Filter out UI elements and invalid rules
            const invalidPatterns = [
                'select check-in date', 'select check-out date', 'select date',
                'exceptional check-in experience',
                'rated 5.0 out of 5', 'check-in5.0', 'guests1 guest',
                'show more', 'see more', 'hide', 'close', 'back', 'next'
            ];

            // Filter out check-in/check-out TIME rules only (require time-like tokens)
            const mentionsCheck = description.includes('check-in') || description.includes('check in') || description.includes('check-out') || description.includes('check out');
            const hasTimeToken = /\b\d{1,2}\s*(:\s*\d{2})?\s*(am|pm)?\b/.test(description) || description.includes(':00') || description.includes(':30');
            const hasKeywords = /(after|before|by|until)\s+\d/.test(description);
            const isTimeRule = mentionsCheck && (hasTimeToken || hasKeywords);

            const isInvalid = invalidPatterns.some(pattern => description.includes(pattern))
                || description === 'none'
                || titleText === 'show more';

            // Allow concise but meaningful rules (e.g., 'No parties', 'No smoking', 'Pets allowed')
            const isTooShort = description.length < 3;

            if (isTimeRule) {
                console.log(`🚫 Filtering out time rule (handled in Basic Info): "${rule.description}"`);
                return false;
            }

            return !isInvalid && !isTooShort;
        });
    }

    filterDefaultRulesForConflicts(defaultRules, importedRules) {
        return defaultRules.filter(defaultRule => {
            // Check if this default rule conflicts with any imported rule
            const hasConflict = importedRules.some(importedRule => {
                return this.rulesConflict(defaultRule, importedRule);
            });

            return !hasConflict;
        });
    }

    rulesConflict(defaultRule, importedRule) {
        // Use content field for new structure, fallback to description for compatibility
        const defaultContent = (defaultRule.content || defaultRule.description || '').toLowerCase();
        const importedContent = (importedRule.content || importedRule.description || '').toLowerCase();

        // Define conflict patterns based on rule IDs and content
        const conflictMappings = [
            {
                defaultIds: ['pets'],
                patterns: ['pet', 'animal', 'dog', 'cat', 'no pets']
            },
            {
                defaultIds: ['smoking'],
                patterns: ['smok', 'no smoking', 'cigarette']
            },
            {
                defaultIds: ['parties'],
                patterns: ['part', 'event', 'gathering', 'no parties']
            },
            {
                defaultIds: ['quiet_hours'],
                patterns: ['quiet', 'noise', 'silent']
            },
            {
                defaultIds: ['occupancy'],
                patterns: ['guest', 'occupancy', 'maximum', 'capacity']
            },
            {
                defaultIds: ['commercial_photography'],
                patterns: ['commercial', 'photography', 'filming', 'photo', 'video']
            }
        ];

        for (const mapping of conflictMappings) {
            // Check if default rule matches by ID
            const defaultMatches = mapping.defaultIds.includes(defaultRule.id);
            // Check if imported rule matches by content patterns
            const importedMatches = mapping.patterns.some(pattern => importedContent.includes(pattern));

            if (defaultMatches && importedMatches) {
                console.log(`🚫 Conflict detected: Default rule "${defaultRule.title}" conflicts with imported rule "${importedRule.title || importedRule.description}"`);
                return true;
            }
        }

        return false;
    }

    renderUnifiedRulesSection(rules) {
        const container = document.getElementById('house-rules-content');
        if (!container) {
            console.error('House rules content container not found');
            return;
        }

        // Always sort before rendering to guarantee imported items appear first
        const displayRules = this.sortRulesForDisplay(rules);

        let html = `
            <div class="space-y-4">
                <div class="text-sm text-gray-600 mb-4">
                    <p>Review and customize your house rules. Rules from your listing are enabled by default.</p>
                </div>
        `;

        displayRules.forEach((rule, index) => {
            const isImported = rule.source === 'imported';
            const sourceLabel = isImported ? 'From Listing' : 'Common Rule';
            const sourceClass = isImported ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-600';

            // Use content field for new structure, fallback to description for compatibility
            const ruleContent = rule.content || rule.description || '';

            html += `
                <div class="border rounded-lg p-4 ${isImported ? 'border-blue-200 bg-blue-50' : 'border-gray-200'}">
                    <div class="flex items-start space-x-3">
                        <input type="checkbox"
                               id="rule_${index}"
                               ${rule.enabled ? 'checked' : ''}
                               onchange="propertySetupModal.toggleRule(${index})"
                               class="mt-1 h-4 w-4 text-persian-green border-gray-300 rounded focus:ring-persian-green">
                        <div class="flex-1">
                            <div class="flex items-center space-x-2 mb-2">
                                <label for="rule_${index}" class="font-medium text-gray-900 cursor-pointer">
                                    ${rule.title || 'House Rule'}
                                </label>
                                <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${sourceClass}">
                                    ${sourceLabel}
                                </span>
                            </div>
                            <textarea id="rule_content_${index}"
                                      class="w-full p-2 border border-gray-300 rounded-md text-sm resize-none"
                                      rows="2"
                                      onchange="propertySetupModal.updateRuleContent(${index}, this.value)"
                                      placeholder="Enter rule content...">${ruleContent}</textarea>
                        </div>
                    </div>
                </div>
            `;
        });

        html += `
            </div>

            <!-- Add Custom Rule Section -->
            <div class="mt-6 pt-4 border-t border-gray-200">
                <div id="custom-rule-form" class="hidden mb-4 p-4 border border-gray-200 rounded-lg bg-gray-50">
                    <h5 class="font-medium text-gray-900 mb-3">Add Custom Rule</h5>
                    <div class="space-y-3">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Rule Content</label>
                            <textarea id="custom-rule-content"
                                      class="w-full p-2 border border-gray-300 rounded-md text-sm resize-none"
                                      rows="3"
                                      placeholder="e.g., No loud music after 10 PM"></textarea>
                        </div>
                        <div class="flex space-x-3">
                            <button type="button"
                                    onclick="propertySetupModal.saveCustomRule()"
                                    class="px-4 py-2 bg-persian-green text-white rounded-lg hover:bg-persian-green/90 transition-colors">
                                <i class="fas fa-check mr-2"></i>Save Rule
                            </button>
                            <button type="button"
                                    onclick="propertySetupModal.cancelCustomRule()"
                                    class="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                                <i class="fas fa-times mr-2"></i>Cancel
                            </button>
                        </div>
                    </div>
                </div>

                <button type="button"
                        id="add-custom-rule-btn"
                        onclick="propertySetupModal.showCustomRuleForm()"
                        class="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-persian-green">
                    <svg class="-ml-0.5 mr-2 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path>
                    </svg>
                    Add Custom Rule
                </button>
            </div>
        `;

        container.innerHTML = html;

        // Store rules data for saving
        this.unifiedRulesData = displayRules;

        // Add dynamic saving event listeners
        this.addHouseRulesEventListeners();

        console.log(`✅ Rendered ${rules.length} unified rules (${rules.filter(r => r.source === 'imported').length} imported, ${rules.filter(r => r.source === 'default').length} default)`);
    }

    addHouseRulesEventListeners() {
        const container = document.getElementById('house-rules-content');
        if (!container) return;

        // Add event listeners for checkboxes
        const checkboxes = container.querySelectorAll('input[type="checkbox"]');
        checkboxes.forEach((checkbox, index) => {
            checkbox.addEventListener('change', () => {
                console.log(`House rule checkbox ${index} changed to:`, checkbox.checked);
                this.updateHouseRuleEnabled(index, checkbox.checked);
                this.saveHouseRulesDynamically();
            });
        });

        // Add event listeners for text inputs and textareas
        const textInputs = container.querySelectorAll('input[type="text"], textarea');
        textInputs.forEach((input) => {
            input.addEventListener('input', () => {
                console.log('House rule text changed:', input.id);
                this.saveHouseRulesDynamically();
            });
        });
    }

    // Ensure imported rules are always shown first
    sortRulesForDisplay(rules) {
        if (!Array.isArray(rules)) return rules;
        return [...rules].sort((a, b) => {
            const rank = (r) => r?.source === 'imported' ? 0 : (r?.source === 'default' ? 1 : 2);
            const ra = rank(a);
            const rb = rank(b);
            if (ra !== rb) return ra - rb;
            // Stable secondary sort by title to keep UI deterministic
            const ta = (a?.title || '').toLowerCase();
            const tb = (b?.title || '').toLowerCase();
            return ta.localeCompare(tb);
        });
    }

    updateHouseRuleEnabled(index, enabled) {
        if (this.unifiedRulesData && this.unifiedRulesData[index]) {
            this.unifiedRulesData[index].enabled = enabled;
            console.log(`Updated house rule ${index} enabled status:`, enabled);
        }
    }

    saveHouseRulesDynamically() {
        // Debounced auto-save
        clearTimeout(this.houseRulesAutoSaveTimeout);
        this.houseRulesAutoSaveTimeout = setTimeout(() => {
            console.log('Auto-saving house rules...');

            // Update current rules data with form data
            this.updateCurrentHouseRulesFromForm();

            // Save to setupData and server
            this.setupData.houseRules = this.unifiedRulesData?.filter(rule => rule.enabled) || [];
            this.saveStepToServer(2, { houseRules: this.setupData.houseRules }).catch(error => {
                console.error('Error auto-saving house rules to server:', error);
            });
        }, 1000);
    }

    updateCurrentHouseRulesFromForm() {
        if (!this.unifiedRulesData) return;

        const container = document.getElementById('house-rules-content');
        if (!container) return;

        this.unifiedRulesData.forEach((rule, index) => {
            const checkbox = document.getElementById(`rule_${index}`);
            const contentTextarea = document.getElementById(`rule_content_${index}`);

            if (checkbox) {
                rule.enabled = checkbox.checked;
            }
            if (contentTextarea) {
                // Update both content and description for compatibility
                rule.content = contentTextarea.value.trim();
                rule.description = contentTextarea.value.trim();
            }
        });

        console.log('Updated current house rules from form:', this.unifiedRulesData);
    }

    toggleRule(index) {
        if (this.unifiedRulesData && this.unifiedRulesData[index]) {
            const checkbox = document.getElementById(`rule_${index}`);
            if (checkbox) {
                this.unifiedRulesData[index].enabled = checkbox.checked;
                console.log(`Toggled rule ${index}:`, this.unifiedRulesData[index].enabled);
                this.saveHouseRulesDynamically();
            }
        }
    }

    updateRuleContent(index, content) {
        if (this.unifiedRulesData && this.unifiedRulesData[index]) {
            this.unifiedRulesData[index].content = content;
            this.unifiedRulesData[index].description = content; // For compatibility
            console.log(`Updated rule ${index} content:`, content);
            this.saveHouseRulesDynamically();
        }
    }

    showCustomRuleForm() {
        const form = document.getElementById('custom-rule-form');
        const button = document.getElementById('add-custom-rule-btn');

        if (form && button) {
            form.classList.remove('hidden');
            button.classList.add('hidden');

            // Focus on title input
            const titleInput = document.getElementById('custom-rule-title');
            if (titleInput) {
                titleInput.focus();
            }
        }
    }

    cancelCustomRule() {
        const form = document.getElementById('custom-rule-form');
        const button = document.getElementById('add-custom-rule-btn');

        if (form && button) {
            form.classList.add('hidden');
            button.classList.remove('hidden');

            // Clear form
            const contentInput = document.getElementById('custom-rule-content');
            if (contentInput) contentInput.value = '';
        }
    }

    saveCustomRule() {
        const contentInput = document.getElementById('custom-rule-content');

        if (!contentInput) return;

        const content = contentInput.value.trim();

        // Validation
        if (!content) {
            alert('Please enter rule content');
            contentInput.focus();
            return;
        }

        const customRule = {
            id: `custom_${Date.now()}`,
            title: 'Custom Rule',
            content: content,
            description: content, // For compatibility
            enabled: true,
            type: 'custom',
            source: 'custom'
        };

        console.log('Adding custom rule:', customRule);

        this.unifiedRulesData = this.unifiedRulesData || [];
        this.unifiedRulesData.push(customRule);
        this.renderUnifiedRulesSection(this.unifiedRulesData);

        // Auto-save
        this.saveHouseRulesDynamically();

        // Hide form and show button
        this.cancelCustomRule();
    }

    loadCustomRules() {
        // Get existing custom rules from property data
        const existingCustomRules = this.propertyData.houseRules?.filter(rule => rule.type === 'custom') || [];
        this.renderRulesSection('custom-rules-container', existingCustomRules);
    }

    renderRulesSection(containerId, rules) {
        const container = document.getElementById(containerId);
        if (!container) return;

        container.innerHTML = rules.map((rule, index) => `
            <div class="border border-gray-200 rounded-lg p-4 ${rule.enabled ? 'bg-green-50 border-green-200' : 'bg-gray-50'}">
                <div class="flex items-start justify-between">
                    <div class="flex items-start space-x-3 flex-1">
                        <!-- Enable/Disable Toggle -->
                        <div class="flex items-center mt-1">
                            <input type="checkbox"
                                   id="${containerId}_${index}"
                                   ${rule.enabled ? 'checked' : ''}
                                   onchange="propertySetupModal.toggleSubRule('${containerId}', ${index})"
                                   class="w-4 h-4 text-persian-green border-gray-300 rounded focus:ring-persian-green">
                        </div>

                        <!-- Rule Content -->
                        <div class="flex-1">
                            <div class="flex items-center space-x-2 mb-2">
                                <h6 class="font-medium text-gray-900">${rule.title}</h6>
                                ${rule.type === 'imported' ? '<span class="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded">From Listing</span>' : ''}
                                ${rule.type === 'custom' ? '<span class="px-2 py-1 text-xs bg-purple-100 text-purple-800 rounded">Custom</span>' : ''}
                            </div>

                            <!-- Editable Description -->
                            <textarea id="${containerId}_desc_${index}"
                                      onchange="propertySetupModal.updateRuleDescription('${containerId}', ${index}, this.value)"
                                      class="w-full text-sm text-gray-600 border border-gray-200 rounded p-2 resize-none"
                                      rows="2"
                                      placeholder="Enter rule description...">${rule.description}</textarea>
                        </div>
                    </div>

                    <!-- Actions -->
                    <div class="flex items-center space-x-2 ml-4">
                        ${rule.type === 'custom' ? `
                            <button onclick="propertySetupModal.removeCustomRule(${index})"
                                    class="text-red-500 hover:text-red-700 p-1"
                                    title="Remove rule">
                                <i class="fas fa-trash text-sm"></i>
                            </button>
                        ` : ''}
                    </div>
                </div>
            </div>
        `).join('');
    }

    toggleSubRule(containerId, index) {
        // Find the rule in the appropriate section and toggle it
        const checkbox = document.getElementById(`${containerId}_${index}`);
        const isEnabled = checkbox.checked;

        // Update the visual state
        const ruleDiv = checkbox.closest('.border');
        if (isEnabled) {
            ruleDiv.classList.remove('bg-gray-50');
            ruleDiv.classList.add('bg-green-50', 'border-green-200');
        } else {
            ruleDiv.classList.remove('bg-green-50', 'border-green-200');
            ruleDiv.classList.add('bg-gray-50');
        }

        // Update the rule data (will be saved when step is saved)
        this.updateRuleInData(containerId, index, { enabled: isEnabled });
    }

    updateRuleDescription(containerId, index, newDescription) {
        this.updateRuleInData(containerId, index, { description: newDescription });
    }

    updateRuleInData(containerId, index, updates) {
        console.log(`Updating rule in ${containerId} at index ${index}:`, updates);

        // Update the rule data based on the container type
        if (containerId === 'default-rules-container') {
            // Update default rules data
            if (!this.defaultRulesData) {
                this.defaultRulesData = this.getDefaultRulesData();
            }
            if (this.defaultRulesData[index]) {
                Object.assign(this.defaultRulesData[index], updates);
                console.log(`Updated default rule ${index}:`, this.defaultRulesData[index]);
            }
        } else if (containerId === 'imported-rules-container') {
            // Update imported rules data
            if (!this.importedRulesData) {
                this.importedRulesData = [];
            }
            if (this.importedRulesData[index]) {
                Object.assign(this.importedRulesData[index], updates);
                console.log(`Updated imported rule ${index}:`, this.importedRulesData[index]);
            }
        } else if (containerId === 'custom-rules-container') {
            // Custom rules are already managed in propertyData.houseRules
            const customRules = this.propertyData.houseRules?.filter(rule => rule.type === 'custom') || [];
            if (customRules[index]) {
                Object.assign(customRules[index], updates);
                console.log(`Updated custom rule ${index}:`, customRules[index]);
            }
        }
    }

    addCustomRule() {
        const title = prompt('Enter rule title:');
        if (!title) return;

        const description = prompt('Enter rule description:');
        if (!description) return;

        const newRule = {
            id: `custom_${Date.now()}`,
            title: title,
            description: description,
            enabled: true,
            type: 'custom'
        };

        // Add to property data
        if (!this.propertyData.houseRules) {
            this.propertyData.houseRules = [];
        }
        this.propertyData.houseRules.push(newRule);

        // Reload custom rules section
        this.loadCustomRules();
    }

    removeCustomRule(index) {
        if (confirm('Are you sure you want to remove this custom rule?')) {
            const customRules = this.propertyData.houseRules?.filter(rule => rule.type === 'custom') || [];
            if (customRules[index]) {
                // Remove from property data
                const ruleToRemove = customRules[index];
                this.propertyData.houseRules = this.propertyData.houseRules.filter(rule => rule.id !== ruleToRemove.id);

                // Reload custom rules section
                this.loadCustomRules();
            }
        }
    }

    extractRuleTitle(description) {
        // Extract a short title from rule description
        if (!description) return 'Custom Rule';

        const words = description.split(' ').slice(0, 4);
        return words.join(' ') + (description.split(' ').length > 4 ? '...' : '');
    }

    updateBasicAmenity(index, value) {
        if (this.propertyData.amenities?.basic) {
            this.propertyData.amenities.basic[index] = value.trim();

            // Auto-save the changes
            this.saveCurrentStepData();

            // If the value is not empty, re-render to show as text instead of input
            if (value.trim() !== '') {
                this.loadAmenitiesSection();
            }
        }
    }

    removeBasicAmenity(index) {
        if (this.propertyData.amenities?.basic) {
            this.propertyData.amenities.basic.splice(index, 1);
            this.loadAmenitiesSection();
            // Auto-save after removal
            this.saveCurrentStepData();
        }
    }

    addAppliance() {
        if (!this.propertyData.amenities) this.propertyData.amenities = { basic: [], appliances: [] };
        this.propertyData.amenities.appliances.push({
            name: '',
            location: '',
            brand: '',
            model: ''
        });
        this.loadAmenitiesSection();
    }

    updateAppliance(index, field, value) {
        if (this.propertyData.amenities?.appliances && this.propertyData.amenities.appliances[index]) {
            this.propertyData.amenities.appliances[index][field] = value.trim();
            // Auto-save the changes
            this.saveCurrentStepData();
        }
    }

    removeAppliance(index) {
        if (this.propertyData.amenities?.appliances) {
            this.propertyData.amenities.appliances.splice(index, 1);
            this.loadAmenitiesSection();
            // Auto-save after removal
            this.saveCurrentStepData();
        }
    }

    _normalizeTextForComparison(text) {
        let s = (text || '').toLowerCase();
        s = s.replace(/[“”]/g, '"').replace(/[‘’]/g, "'").replace(/[—–]/g, '-');
        s = s.replace(/\"|"/g, '').replace(/'/g, '');
        s = s.replace(/\s+/g, ' ').trim();
        return s;
    }

    _getSemanticKeyEmergency(item) {
        const title = this._normalizeTextForComparison(item.title || item.type || '');
        const body = this._normalizeTextForComparison(item.description || item.instructions || '');
        return `${title} | ${body}`.trim();
    }

    _filterAndDedupeImportedSafety(items) {
        const headers = new Set(['safety & property', 'safety considerations', 'safety devices', 'none']);
        const seen = new Set();
        const out = [];
        (items || []).forEach(it => {
            const title = (it.title || it.type || '').trim();
            const instructions = (it.description || it.instructions || '').trim();
            if (!instructions) return;
            if (headers.has(title.toLowerCase())) return;
            const key = this._getSemanticKeyEmergency({ title, description: instructions });
            if (!key || seen.has(key)) return;
            seen.add(key);
            out.push({ title, description: instructions, location: it.location || '' });
        });
        return out;
    }
}

// Global instance
const propertySetupModal = new PropertySetupModal();

// Export for use in other files
window.propertySetupModal = propertySetupModal;
