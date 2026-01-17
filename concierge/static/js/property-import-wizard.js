/**
 * Property Import Wizard JavaScript
 * Handles property import from Airbnb listings with deep data extraction
 */

class PropertyImportWizard {
    constructor() {
        this.currentStep = 1;
        this.totalSteps = 3; // Simplified: URL Import -> Listing Selection -> Import Complete
        this.wizardData = {};
        this.selectedListings = [];

        this.init();
    }

    init() {
        console.log('PropertySetupWizard initializing...');
        try {
            this.bindEvents();
            this.initializeHouseRules();
            this.initializeEmergencyInfo();
            this.loadProgress();
            
            // Force display initialization after everything else is set up
            setTimeout(() => {
                this.forceDisplayState();
            }, 100);
            
            // Also force display after a longer delay to override Firebase auth UI updates
            setTimeout(() => {
                console.log('SECOND FORCE - overriding any UI updates from auth/firebase...');
                this.forceDisplayState();
            }, 1000);
            
            console.log('PropertySetupWizard initialized successfully');
        } catch (error) {
            console.error('Error initializing PropertySetupWizard:', error);
        }
    }

    forceDisplayState() {
        console.log(`Showing step ${this.currentStep} - using inline styles...`);
        
        // Use inline styles to ensure proper display
        document.querySelectorAll('.wizard-step').forEach(step => {
            const stepNumber = parseInt(step.dataset.step);
            if (stepNumber === this.currentStep) {
                // Show current step
                step.style.setProperty('display', 'block', 'important');
                step.style.setProperty('visibility', 'visible', 'important');
                step.style.setProperty('opacity', '1', 'important');
                step.style.setProperty('position', 'relative', 'important');
                step.style.setProperty('left', 'auto', 'important');
                step.classList.add('active');
                console.log(`Step ${stepNumber} set to active and visible`);
            } else {
                // Hide other steps
                step.style.setProperty('display', 'none', 'important');
                step.style.setProperty('visibility', 'hidden', 'important');
                step.style.setProperty('opacity', '0', 'important');
                step.style.setProperty('position', 'absolute', 'important');
                step.style.setProperty('left', '-99999px', 'important');
                step.classList.remove('active');
            }
        });
        
        // Update progress
        this.updateProgress();
    }

    // Removed startDisplayMonitoring - now using CSS-based approach

    bindEvents() {
        console.log('Binding events...');
        
        // Navigation buttons - with error checking
        const nextBtn = document.getElementById('next-btn');
        const prevBtn = document.getElementById('prev-btn');
        const saveBtn = document.getElementById('save-progress');
        
        if (nextBtn) {
            nextBtn.addEventListener('click', () => this.nextStep());
            console.log('Next button bound');
        } else {
            console.error('Next button not found');
        }
        
        if (prevBtn) {
            prevBtn.addEventListener('click', () => this.previousStep());
            console.log('Previous button bound');
        } else {
            console.error('Previous button not found');
        }
        
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveProgress());
            console.log('Save button bound');
        } else {
            console.error('Save button not found');
        }

        // File uploads
        this.setupFileDropzones();

        // Progress steps click handlers
        this.bindProgressSteps();

        // Other buttons - with safe binding
        this.safeBindEvent('search-local-places', 'click', () => this.searchLocalPlaces());
        this.safeBindEvent('start-manual-entry', 'click', () => this.startManualEntry());
        this.safeBindEvent('start-voice-chat', 'click', () => this.startVoiceChat());
        this.safeBindEvent('add-custom-rule', 'click', () => this.addCustomRule());
        this.safeBindEvent('add-custom-emergency', 'click', () => this.addCustomEmergency());

        // Form field tracking
        this.trackFormChanges();
        
        console.log('All events bound successfully');
        
        // Test wizard elements
        this.testWizardElements();
    }

    testWizardElements() {
        console.log('Testing wizard elements...');
        
        // Check if all wizard steps exist
        const steps = document.querySelectorAll('.wizard-step');
        console.log(`Found ${steps.length} wizard steps`);
        
        // Check if navigation buttons exist
        const navButtons = ['next-btn', 'prev-btn', 'save-progress'];
        navButtons.forEach(btnId => {
            const btn = document.getElementById(btnId);
            console.log(`${btnId}: ${btn ? 'Found' : 'MISSING'}`);
        });
        
        // Check current display state and CSS classes
        steps.forEach((step, index) => {
            const display = window.getComputedStyle(step).display;
            const visibility = window.getComputedStyle(step).visibility;
            const hasActive = step.classList.contains('active');
            const stepNum = step.getAttribute('data-step');
            console.log(`Step ${index + 1} (data-step="${stepNum}"):`, {
                display: display,
                visibility: visibility,
                hasActiveClass: hasActive,
                classList: step.classList.toString()
            });
        });
    }

    safeBindEvent(elementId, eventType, handler) {
        const element = document.getElementById(elementId);
        if (element) {
            element.addEventListener(eventType, handler);
            console.log(`${elementId} bound to ${eventType}`);
        } else {
            console.warn(`Element ${elementId} not found for ${eventType} binding`);
        }
    }

    bindProgressSteps() {
        const progressSteps = document.querySelectorAll('.progress-step');
        progressSteps.forEach((step, index) => {
            step.addEventListener('click', () => {
                const targetStep = index + 1;
                
                // Allow navigation to any step, but validate current step first
                if (this.validateCurrentStep()) {
                    this.currentStep = targetStep;
                    this.updateDisplay();
                    console.log(`🔄 Navigated to step ${targetStep} via progress click`);
                } else {
                    console.warn('⚠️ Cannot navigate - current step has validation errors');
                    // Optionally show a message to the user
                    this.showValidationMessage();
                }
            });
        });
        console.log(`✅ Bound click handlers to ${progressSteps.length} progress steps`);
    }

    showValidationMessage() {
        // Show a brief validation message
        const toast = document.createElement('div');
        toast.className = 'alert alert-warning position-fixed';
        toast.style.cssText = 'top: 20px; right: 20px; z-index: 9999; max-width: 300px;';
        toast.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="bi bi-exclamation-triangle me-2"></i>
                Please complete the required fields before proceeding.
            </div>
        `;
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    setupFileDropzones() {
        // Only handle facts dropzone since json-dropzone was removed from step 2
        const dropzones = ['facts-dropzone'];
        
        dropzones.forEach(zoneId => {
            const dropzone = document.getElementById(zoneId);
            const fileInput = document.getElementById('facts-file');

            // Click to upload
            dropzone.addEventListener('click', () => fileInput.click());

            // Drag and drop
            dropzone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropzone.classList.add('drag-over');
            });

            dropzone.addEventListener('dragleave', () => {
                dropzone.classList.remove('drag-over');
            });

            dropzone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropzone.classList.remove('drag-over');
                
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    fileInput.files = files;
                    this.handleFileUpload(files, zoneId);
                }
            });

            // File input change (only for facts-file since json-file was removed)
            if (fileInput) {
                fileInput.addEventListener('change', (e) => {
                    if (e.target.files.length > 0) {
                        this.handleFileUpload(e.target.files, zoneId);
                    }
                });
            }
        });
    }

    async handleFileUpload(files, zoneId) {
        if (!files || files.length === 0) return;
        
        const file = files[0];
        const dropzone = document.getElementById(zoneId);
        
        // Show uploading state
        dropzone.innerHTML = `
            <div class="upload-status text-center">
                <div class="spinner-border spinner-border-sm me-2" role="status"></div>
                <span>Processing ${file.name}...</span>
            </div>
        `;
        
        try {
            const uploadType = 'facts'; // Only facts upload now
            const result = await this.uploadFileToServer(file, uploadType);
            
            if (result.success) {
                // Store the processed data
                this.wizardData.property_facts = {
                    ...this.wizardData.property_facts || {},
                    uploaded_file: result.filename,
                    processed_data: result.data
                };
                
                // Show success
                dropzone.innerHTML = `
                    <div class="upload-success text-center">
                        <i class="bi bi-check-circle-fill text-success fs-1 mb-2"></i>
                        <p class="mb-1">${result.filename}</p>
                        <div class="upload-details">
                            <small class="text-muted">${result.data.message || 'File processed successfully'}</small>
                        </div>
                    </div>
                `;
                
                // Auto-save progress after successful upload
                this.saveProgress();
                
            } else {
                throw new Error(result.error || 'Upload failed');
            }
            
        } catch (error) {
            console.error('File upload error:', error);
            dropzone.innerHTML = `
                <div class="upload-error text-center">
                    <i class="bi bi-exclamation-triangle-fill text-danger fs-1 mb-2"></i>
                    <p class="text-danger mb-1">Error: ${error.message}</p>
                    <div class="mt-2">
                        <button class="btn btn-sm btn-outline-primary" onclick="document.getElementById('facts-file').click()">
                            Try Again
                        </button>
                    </div>
                </div>
            `;
        }
    }

    async uploadFileToServer(file, uploadType) {
        try {
            // Create FormData for file upload
            const formData = new FormData();
            formData.append('file', file);
            formData.append('action', 'upload_file');
            formData.append('upload_type', uploadType);
            
            // Upload file to server
            const response = await fetch('/setup', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (!result.success) {
                throw new Error(result.error || 'Upload failed');
            }
            
            // Auto-populate form fields based on extracted data
            if (result.data && result.data.type === 'airbnb_data') {
                this.populateFromAirbnbData(result.data.data);
            } else if (result.data && result.data.type === 'property_facts') {
                this.populateFromPropertyFacts(result.data.data);
            }
            
            return {
                success: true,
                filename: result.filename,
                data: result.data
            };
            
        } catch (error) {
            console.error('File upload error:', error);
            return {
                success: false,
                error: error.message || 'Failed to upload file'
            };
        }
    }
    
    populateFromAirbnbData(data) {
        // Auto-populate basic info from Airbnb data
        if (data.name && !document.getElementById('property-name').value) {
            document.getElementById('property-name').value = data.name;
        }
        if (data.description && !document.getElementById('description').value) {
            document.getElementById('description').value = data.description;
        }
        
        // Populate house rules if available
        if (data.house_rules) {
            const rulesText = typeof data.house_rules === 'string' ? data.house_rules : 
                             Array.isArray(data.house_rules) ? data.house_rules.join('\n') : '';
            
            // Find an appropriate rule text area to populate
            const customRuleTextarea = document.querySelector('#house-rules-container textarea[placeholder*="Additional details"]');
            if (customRuleTextarea && !customRuleTextarea.value) {
                customRuleTextarea.value = rulesText;
            }
        }
        
        console.log('✓ Auto-populated form fields from Airbnb data');
    }
    
    populateFromPropertyFacts(data) {
        // Handle different types of extracted property facts
        if (data.ai_extracted) {
            console.log('✓ Property facts extracted with AI:', data.ai_extracted.substring(0, 200) + '...');
        }
        
        if (data.raw_content) {
            console.log('✓ Raw content available for manual review');
        }
        
        // For now, just log the extracted data
        // Could be enhanced to parse specific fields and auto-populate the form
        console.log('✓ Property facts file processed successfully');
    }

    initializeHouseRules() {
        const commonRules = [
            { id: 'no-smoking', text: 'No smoking inside the property', enabled: true },
            { id: 'no-pets', text: 'No pets allowed', enabled: false },
            { id: 'no-parties', text: 'No parties or events', enabled: true },
            { id: 'quiet-hours', text: 'Quiet hours: 10 PM - 8 AM', enabled: true },
            { id: 'max-guests', text: 'Maximum occupancy as listed', enabled: true },
            { id: 'no-shoes', text: 'Please remove shoes indoors', enabled: false },
            { id: 'check-out-clean', text: 'Please clean up before checkout', enabled: true },
            { id: 'report-damages', text: 'Report any damages immediately', enabled: true }
        ];

        this.renderRulesList(commonRules, 'house-rules-container');
    }

    initializeEmergencyInfo() {
        const emergencyScenarios = [
            { 
                id: 'power-outage', 
                title: 'Power Outage', 
                enabled: true,
                instructions: 'Check the electrical panel in the basement. Contact host if power doesn\'t return within 2 hours.',
                location: 'Electrical panel: Basement, left wall'
            },
            { 
                id: 'water-leak', 
                title: 'Water Leak/Burst Pipe', 
                enabled: true,
                instructions: 'Turn off main water valve immediately and contact host. Do not use electrical appliances near water.',
                location: 'Main water valve: Under kitchen sink'
            },
            { 
                id: 'hvac-failure', 
                title: 'Heating/Cooling Failure', 
                enabled: true,
                instructions: 'Check thermostat settings first. If no response, contact host.',
                location: 'Thermostat: Main hallway'
            },
            { 
                id: 'fire-emergency', 
                title: 'Fire Emergency', 
                enabled: true,
                instructions: 'Call 911 immediately. Use fire extinguisher only for small fires. Evacuate if in doubt.',
                location: 'Fire extinguisher: Kitchen cabinet under sink'
            },
            { 
                id: 'gas-leak', 
                title: 'Gas Leak', 
                enabled: true,
                instructions: 'Do not use electrical switches. Ventilate area. Shut off gas valve if safe to do so. Call gas company and 911.',
                location: 'Gas shutoff: Outside near meter'
            },
            { 
                id: 'lockout', 
                title: 'Locked Out', 
                enabled: true,
                instructions: 'Contact host immediately. Backup key location will be provided separately.',
                location: 'Smart lock backup: Contact host for instructions'
            }
        ];

        this.renderEmergencyList(emergencyScenarios, 'emergency-info-container');
    }

    renderRulesList(rules, containerId) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.warn(`Container ${containerId} not found for rules list`);
            return;
        }
        container.innerHTML = rules.map(rule => `
            <div class="form-section">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <label class="toggle-switch">
                            <input type="checkbox" id="${rule.id}" ${rule.enabled ? 'checked' : ''} data-rule-id="${rule.id}">
                            <span class="toggle-slider"></span>
                        </label>
                        <span class="ms-3">${rule.text}</span>
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="editRule('${rule.id}')">
                        <i class="bi bi-pencil"></i>
                    </button>
                </div>
                <div class="mt-2">
                    <textarea class="form-control form-control-sm" 
                              data-rule-details="${rule.id}" 
                              placeholder="Additional details or specific instructions..."
                              rows="2"></textarea>
                </div>
            </div>
        `).join('');
    }

    renderEmergencyList(scenarios, containerId) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.warn(`Container ${containerId} not found for emergency list`);
            return;
        }
        container.innerHTML = scenarios.map(scenario => `
            <div class="form-section">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="flex-grow-1">
                        <label class="toggle-switch">
                            <input type="checkbox" id="${scenario.id}" ${scenario.enabled ? 'checked' : ''} data-emergency-id="${scenario.id}">
                            <span class="toggle-slider"></span>
                        </label>
                        <span class="ms-3 fw-bold">${scenario.title}</span>
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="editEmergency('${scenario.id}')">
                        <i class="bi bi-pencil"></i>
                    </button>
                </div>
                <div class="row">
                    <div class="col-md-6">
                        <label class="form-label small text-muted">What to do:</label>
                        <textarea class="form-control form-control-sm" 
                                  data-emergency-instructions="${scenario.id}"
                                  rows="3">${scenario.instructions}</textarea>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label small text-muted">Location/Access:</label>
                        <textarea class="form-control form-control-sm" 
                                  data-emergency-location="${scenario.id}"
                                  rows="3">${scenario.location}</textarea>
                    </div>
                </div>
            </div>
        `).join('');
    }

    addCustomRule() {
        const container = document.getElementById('house-rules-container');
        const ruleId = 'custom-' + Date.now();
        
        const newRuleHTML = `
            <div class="form-section" data-custom-rule="${ruleId}">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <label class="toggle-switch">
                            <input type="checkbox" id="${ruleId}" checked data-rule-id="${ruleId}">
                            <span class="toggle-slider"></span>
                        </label>
                        <input type="text" class="form-control form-control-sm ms-3" 
                               style="display: inline-block; width: 70%;"
                               placeholder="Enter your custom rule..." 
                               data-custom-rule-text="${ruleId}">
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeCustomRule('${ruleId}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
                <div class="mt-2">
                    <textarea class="form-control form-control-sm" 
                              data-rule-details="${ruleId}" 
                              placeholder="Additional details..."
                              rows="2"></textarea>
                </div>
            </div>
        `;
        
        container.insertAdjacentHTML('beforeend', newRuleHTML);
    }

    addCustomEmergency() {
        const container = document.getElementById('emergency-info-container');
        const emergencyId = 'custom-' + Date.now();
        
        const newEmergencyHTML = `
            <div class="form-section" data-custom-emergency="${emergencyId}">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="flex-grow-1">
                        <label class="toggle-switch">
                            <input type="checkbox" id="${emergencyId}" checked data-emergency-id="${emergencyId}">
                            <span class="toggle-slider"></span>
                        </label>
                        <input type="text" class="form-control form-control-sm ms-3" 
                               style="display: inline-block; width: 70%;"
                               placeholder="Emergency type..." 
                               data-custom-emergency-title="${emergencyId}">
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeCustomEmergency('${emergencyId}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
                <div class="row">
                    <div class="col-md-6">
                        <label class="form-label small text-muted">What to do:</label>
                        <textarea class="form-control form-control-sm" 
                                  data-emergency-instructions="${emergencyId}"
                                  rows="3"
                                  placeholder="Instructions for this emergency..."></textarea>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label small text-muted">Location/Access:</label>
                        <textarea class="form-control form-control-sm" 
                                  data-emergency-location="${emergencyId}"
                                  rows="3"
                                  placeholder="Where to find relevant equipment/shutoffs..."></textarea>
                    </div>
                </div>
            </div>
        `;
        
        container.insertAdjacentHTML('beforeend', newEmergencyHTML);
    }

    async searchLocalPlaces() {
        const address = document.getElementById('property-address').value;
        if (!address) {
            alert('Please enter a property address in Step 1 first.');
            return;
        }

        const loadingBtn = document.getElementById('search-local-places');
        const originalText = loadingBtn.innerHTML;
        loadingBtn.innerHTML = '<i class="bi bi-hourglass-split me-2"></i>Searching with AI...';
        loadingBtn.disabled = true;

        try {
            // Preserve existing selections before search
            const existingSelections = this.collectLocalPlaces();
            
            const response = await fetch('/setup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    action: 'search_local_places',
                    address: address
                })
            });

            const data = await response.json();
            if (data.success && data.places) {
                // Store the places data
                this.localPlacesData = data.places.map(place => ({
                    ...place,
                    selected: false  // Default to unselected
                }));
                
                // Restore any existing selections
                existingSelections.forEach(existing => {
                    const place = this.localPlacesData.find(p => p.name === existing.name);
                    if (place) {
                        place.selected = existing.selected;
                    }
                });
                
                this.renderLocalPlaces(this.localPlacesData);
                console.log('AI-powered places search completed:', this.localPlacesData.length, 'places found');
            } else {
                console.error('Error searching local places:', data.error);
                alert('Error searching for places: ' + (data.error || 'Please try again'));
            }
        } catch (error) {
            console.error('Error searching local places:', error);
            alert('Error searching for places. Please try again.');
        } finally {
            loadingBtn.innerHTML = originalText;
            loadingBtn.disabled = false;
        }
    }

        renderLocalPlaces(places) {
        const container = document.getElementById('local-places-container');
        container.innerHTML = `
            <div class="recommendations-grid">
                ${places.map(place => `
                    <div class="recommendation-item ${place.selected ? 'selected' : ''}" 
                         data-place-id="${place.name}"
                         onclick="togglePlaceSelection(${JSON.stringify(place.name)})">
                        <div style="flex: 1;">
                            <strong>${place.name}</strong>
                            <br><small class="text-muted text-capitalize">${place.type}</small>
                            ${place.rating ? `<br><span class="badge bg-warning text-dark">★ ${place.rating}</span>` : ''}
                            ${place.address ? `<br><small class="text-muted">${place.address}</small>` : ''}
                            ${place.description ? `<br><small class="text-info">${place.description}</small>` : ''}
                        </div>
                        <div>
                            <label class="toggle-switch">
                                <input type="checkbox" ${place.selected ? 'checked' : ''}>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    startManualEntry() {
        const form = document.getElementById('manual-entry-form');
        form.style.display = 'block';
        
        // Initialize manual entry data if not exists
        if (!this.wizardData.property_facts) {
            this.wizardData.property_facts = {};
        }
        if (!this.wizardData.property_facts.manual_entry) {
            this.wizardData.property_facts.manual_entry = {
                rooms: []
            };
        }
        
        form.innerHTML = this.generateManualEntryForm();
        this.bindManualEntryEvents();
    }

    generateManualEntryForm() {
        const roomTypes = this.getRoomTypeDefinitions();
        
        return `
            <div class="card">
                <div class="card-header bg-success text-white d-flex justify-content-between align-items-center">
                    <h5 class="mb-0">Manual Property Entry</h5>
                    <button type="button" class="btn btn-light btn-sm" id="close-manual-entry">
                        <i class="fas fa-times"></i> Close
                    </button>
                </div>
                <div class="card-body">
                    <div class="row mb-3">
                        <div class="col-md-12">
                            <label class="form-label">Add Room/Area</label>
                            <div class="d-flex gap-2 flex-wrap">
                                ${Object.keys(roomTypes).map(roomType => `
                                    <button type="button" class="btn btn-outline-primary btn-sm" 
                                            data-room-type="${roomType}">
                                        <i class="${roomTypes[roomType].icon}"></i> ${roomTypes[roomType].name}
                                    </button>
                                `).join('')}
                            </div>
                        </div>
                    </div>
                    
                    <div id="rooms-container">
                        ${this.renderExistingRooms()}
                    </div>
                    
                    <div class="mt-3 pt-3 border-top">
                        <div class="d-flex justify-content-between">
                            <button type="button" class="btn btn-secondary" id="cancel-manual-entry">
                                Cancel
                            </button>
                            <button type="button" class="btn btn-success" id="save-manual-entry">
                                <i class="fas fa-save"></i> Save Property Data
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    getRoomTypeDefinitions() {
        return {
            'BEDROOM': {
                name: 'Bedroom',
                icon: 'fas fa-bed',
                amenities: [
                    'QUEEN_BED', 'KING_BED', 'DOUBLE_BED', 'SINGLE_BED', 'BUNK_BED', 'SOFA_BED',
                    'AC', 'HEATING', 'HANGERS', 'IRON', 'ROOM_DARKENING_SHADES', 
                    'BED_LINENS', 'WARDROBE_OR_CLOSET', 'DRESSER', 'NIGHTSTAND'
                ]
            },
            'FULL_BATHROOM': {
                name: 'Full Bathroom',
                icon: 'fas fa-bath',
                amenities: [
                    'AC', 'HEATING', 'SHAMPOO', 'HAIR_DRYER', 'BATHTUB', 'SHOWER',
                    'HOT_WATER', 'BODY_SOAP', 'SHOWER_GEL', 'CONDITIONER', 'TOWELS',
                    'TOILET_PAPER', 'MIRROR'
                ]
            },
            'HALF_BATHROOM': {
                name: 'Half Bathroom',
                icon: 'fas fa-toilet',
                amenities: [
                    'AC', 'HEATING', 'SHAMPOO', 'HOT_WATER', 'BODY_SOAP', 
                    'SHOWER_GEL', 'CONDITIONER', 'TOWELS', 'TOILET_PAPER', 'MIRROR'
                ]
            },
            'KITCHEN': {
                name: 'Kitchen',
                icon: 'fas fa-utensils',
                amenities: [
                    'MICROWAVE', 'COFFEE_MAKER', 'REFRIGERATOR', 'DISHWASHER', 
                    'DISHES_AND_SILVERWARE', 'COOKING_BASICS', 'OVEN', 'STOVE',
                    'TOASTER', 'FREEZER', 'BLENDER', 'COFFEE', 'WINE_GLASSES',
                    'DINING_TABLE', 'KETTLE', 'CUTTING_BOARD'
                ]
            },
            'LIVING_ROOM': {
                name: 'Living Room',
                icon: 'fas fa-couch',
                amenities: [
                    'TV', 'AC', 'HEATING', 'SOUND_SYSTEM', 'BOOKS', 'SOFA',
                    'COFFEE_TABLE', 'ENTERTAINMENT_CENTER', 'CABLE_TV', 'FIREPLACE'
                ]
            },
            'DINING_ROOM': {
                name: 'Dining Room',
                icon: 'fas fa-chair',
                amenities: [
                    'AC', 'HEATING', 'DINING_TABLE', 'WINE_GLASSES', 'CHAIRS',
                    'BUFFET', 'CHANDELIER'
                ]
            },
            'LAUNDRY_ROOM': {
                name: 'Laundry Room',
                icon: 'fas fa-tshirt',
                amenities: [
                    'WASHER', 'DRYER', 'IRON', 'IRONING_BOARD', 'LAUNDRY_DETERGENT',
                    'HANGERS', 'DRYING_RACK'
                ]
            },
            'WORKSPACE': {
                name: 'Workspace/Office',
                icon: 'fas fa-laptop',
                amenities: [
                    'AC', 'LAPTOP_FRIENDLY_WORKSPACE', 'DESK', 'CHAIR', 'WIFI',
                    'PRINTER', 'LAMP', 'STORAGE'
                ]
            },
            'EXTERIOR': {
                name: 'Outdoor Area',
                icon: 'fas fa-tree',
                amenities: [
                    'BBQ_AREA', 'PATIO_OR_BALCONY', 'GARDEN_OR_BACKYARD', 
                    'ALFRESCO_DINING', 'FIRE_PIT', 'OUTDOOR_SEATING', 'PATIO',
                    'POOL', 'HOT_TUB', 'OUTDOOR_FURNITURE'
                ]
            },
            'OTHER': {
                name: 'Other Room',
                icon: 'fas fa-door-open',
                amenities: [
                    'AC', 'HEATING', 'STORAGE', 'CLOSET', 'EXERCISE_EQUIPMENT'
                ]
            }
        };
    }
    
    renderExistingRooms() {
        const rooms = this.wizardData.property_facts.manual_entry?.rooms || [];
        if (rooms.length === 0) {
            return `<div class="text-center text-muted py-4">
                <i class="fas fa-home fa-3x mb-2"></i>
                <p>No rooms added yet. Click the buttons above to start adding rooms to your property.</p>
            </div>`;
        }
        
        return rooms.map((room, index) => this.renderRoomCard(room, index)).join('');
    }

    renderRoomCard(room, index) {
        const roomTypes = this.getRoomTypeDefinitions();
        const roomType = roomTypes[room.type] || roomTypes['OTHER'];
        
        return `
            <div class="card mb-3" id="room-${index}">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <div>
                        <i class="${roomType.icon}"></i>
                        <strong>${room.name || roomType.name}</strong>
                    </div>
                    <button type="button" class="btn btn-outline-danger btn-sm" 
                            data-remove-room="${index}">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
                <div class="card-body">
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <label class="form-label">Room Name</label>
                            <input type="text" class="form-control" 
                                   value="${room.name || ''}" 
                                   data-room-name="${index}"
                                   placeholder="${roomType.name}">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">Location/Notes</label>
                            <input type="text" class="form-control" 
                                   value="${room.location || ''}" 
                                   data-room-location="${index}"
                                   placeholder="e.g., 2nd floor, near kitchen">
                        </div>
                    </div>
                    
                    <div class="amenities-section">
                        <label class="form-label">Available Amenities & Features</label>
                        <div class="row">
                            ${roomType.amenities.map(amenity => `
                                <div class="col-md-4 col-sm-6 mb-2">
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" 
                                               id="amenity-${index}-${amenity}"
                                               ${room.amenities?.includes(amenity) ? 'checked' : ''}
                                               data-room-amenity="${index}" data-amenity="${amenity}">
                                        <label class="form-check-label" for="amenity-${index}-${amenity}">
                                            ${this.formatAmenityName(amenity)}
                                        </label>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                    
                    <div class="mt-3">
                        <label class="form-label">Custom Amenities</label>
                        <div class="d-flex gap-2 mb-2">
                            <input type="text" class="form-control" 
                                   id="custom-amenity-${index}" 
                                   placeholder="Add custom amenity">
                            <button type="button" class="btn btn-outline-primary" 
                                    data-add-custom-amenity="${index}">
                                <i class="fas fa-plus"></i>
                            </button>
                        </div>
                        <div id="custom-amenities-${index}">
                            ${(room.customAmenities || []).map((amenity, amenityIndex) => `
                                <span class="badge bg-secondary me-1 mb-1">
                                    ${amenity}
                                                                    <button type="button" class="btn-close btn-close-white ms-1" 
                                        data-remove-custom-amenity="${index}" data-amenity-index="${amenityIndex}"
                                        style="font-size: 0.7em;"></button>
                                </span>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    formatAmenityName(amenity) {
        return amenity.toLowerCase()
                     .replace(/_/g, ' ')
                     .replace(/\b\w/g, l => l.toUpperCase());
    }

    addRoom(roomType) {
        const roomTypes = this.getRoomTypeDefinitions();
        const newRoom = {
            type: roomType,
            name: '',
            location: '',
            amenities: [],
            customAmenities: []
        };
        
        if (!this.wizardData.property_facts.manual_entry) {
            this.wizardData.property_facts.manual_entry = { rooms: [] };
        }
        
        this.wizardData.property_facts.manual_entry.rooms.push(newRoom);
        this.refreshRoomsContainer();
        this.saveProgress();
    }

    removeRoom(index) {
        if (confirm('Are you sure you want to remove this room?')) {
            this.wizardData.property_facts.manual_entry.rooms.splice(index, 1);
            this.refreshRoomsContainer();
            this.saveProgress();
        }
    }

    updateRoomName(index, name) {
        this.wizardData.property_facts.manual_entry.rooms[index].name = name;
        this.saveProgress();
    }

    updateRoomLocation(index, location) {
        this.wizardData.property_facts.manual_entry.rooms[index].location = location;
        this.saveProgress();
    }

    updateRoomAmenity(index, amenity, checked) {
        const room = this.wizardData.property_facts.manual_entry.rooms[index];
        if (!room.amenities) room.amenities = [];
        
        if (checked) {
            if (!room.amenities.includes(amenity)) {
                room.amenities.push(amenity);
            }
        } else {
            room.amenities = room.amenities.filter(a => a !== amenity);
        }
        this.saveProgress();
    }

    addCustomAmenity(index) {
        const input = document.getElementById(`custom-amenity-${index}`);
        const amenity = input.value.trim();
        
        if (amenity) {
            const room = this.wizardData.property_facts.manual_entry.rooms[index];
            if (!room.customAmenities) room.customAmenities = [];
            
            if (!room.customAmenities.includes(amenity)) {
                room.customAmenities.push(amenity);
                input.value = '';
                this.refreshCustomAmenities(index);
                this.saveProgress();
            }
        }
    }

    removeCustomAmenity(index, amenityIndex) {
        const room = this.wizardData.property_facts.manual_entry.rooms[index];
        room.customAmenities.splice(amenityIndex, 1);
        this.refreshCustomAmenities(index);
        this.saveProgress();
    }

    refreshCustomAmenities(roomIndex) {
        const container = document.getElementById(`custom-amenities-${roomIndex}`);
        const room = this.wizardData.property_facts.manual_entry.rooms[roomIndex];
        
        container.innerHTML = (room.customAmenities || []).map((amenity, amenityIndex) => `
            <span class="badge bg-secondary me-1 mb-1">
                ${amenity}
                <button type="button" class="btn-close btn-close-white ms-1" 
                        data-remove-custom-amenity="${roomIndex}" data-amenity-index="${amenityIndex}"
                        style="font-size: 0.7em;"></button>
            </span>
        `).join('');
        // Events are handled by delegation on the parent form, so no need to rebind
    }

    refreshRoomsContainer() {
        const container = document.getElementById('rooms-container');
        container.innerHTML = this.renderExistingRooms();
        // Events are handled by delegation on the parent form, so no need to rebind
    }

    bindManualEntryEvents() {
        // Use event delegation to handle all manual entry events
        const form = document.getElementById('manual-entry-form');
        
        // Remove existing event listener if it exists
        if (form._manualEntryHandler) {
            form.removeEventListener('click', form._manualEntryHandler);
            form.removeEventListener('change', form._manualEntryHandler);
            form.removeEventListener('input', form._manualEntryHandler);
        }
        
        // Create a single event handler for all manual entry events
        const handleManualEntryEvent = (event) => {
            const target = event.target;
            
            // Handle room type buttons
            if (target.dataset.roomType) {
                event.preventDefault();
                this.addRoom(target.dataset.roomType);
                return;
            }
            
            // Handle remove room buttons
            if (target.dataset.removeRoom !== undefined) {
                event.preventDefault();
                this.removeRoom(parseInt(target.dataset.removeRoom));
                return;
            }
            
            // Handle close/cancel buttons
            if (target.id === 'close-manual-entry' || target.id === 'cancel-manual-entry') {
                event.preventDefault();
                this.closeManualEntry();
                return;
            }
            
            // Handle save button
            if (target.id === 'save-manual-entry') {
                event.preventDefault();
                this.saveManualEntry();
                return;
            }
            
            // Handle room name changes
            if (target.dataset.roomName !== undefined) {
                const roomIndex = parseInt(target.dataset.roomName);
                this.updateRoomName(roomIndex, target.value);
                return;
            }
            
            // Handle room location changes
            if (target.dataset.roomLocation !== undefined) {
                const roomIndex = parseInt(target.dataset.roomLocation);
                this.updateRoomLocation(roomIndex, target.value);
                return;
            }
            
            // Handle amenity checkboxes
            if (target.dataset.roomAmenity !== undefined) {
                const roomIndex = parseInt(target.dataset.roomAmenity);
                const amenity = target.dataset.amenity;
                this.updateRoomAmenity(roomIndex, amenity, target.checked);
                return;
            }
            
            // Handle add custom amenity buttons
            if (target.dataset.addCustomAmenity !== undefined) {
                event.preventDefault();
                const roomIndex = parseInt(target.dataset.addCustomAmenity);
                this.addCustomAmenity(roomIndex);
                return;
            }
            
            // Handle remove custom amenity buttons
            if (target.dataset.removeCustomAmenity !== undefined) {
                event.preventDefault();
                const roomIndex = parseInt(target.dataset.removeCustomAmenity);
                const amenityIndex = parseInt(target.dataset.amenityIndex);
                this.removeCustomAmenity(roomIndex, amenityIndex);
                return;
            }
        };
        
        // Store the handler so we can remove it later
        form._manualEntryHandler = handleManualEntryEvent;
        
        // Add event listeners
        form.addEventListener('click', handleManualEntryEvent);
        form.addEventListener('change', handleManualEntryEvent);
        form.addEventListener('input', handleManualEntryEvent);
    }

    closeManualEntry() {
        const form = document.getElementById('manual-entry-form');
        form.style.display = 'none';
    }

    saveManualEntry() {
        // Save the current state
        this.saveProgress();
        
        // Show success message
        const alert = document.createElement('div');
        alert.className = 'alert alert-success alert-dismissible fade show';
        alert.innerHTML = `
            <i class="fas fa-check-circle"></i> Property data saved successfully!
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        const form = document.getElementById('manual-entry-form');
        form.insertBefore(alert, form.firstChild);
        
        // Auto-hide after 3 seconds
        setTimeout(() => {
            if (alert.parentNode) {
                alert.remove();
            }
        }, 3000);
    }

    startVoiceChat() {
        console.log('🎙️ Starting voice chat integration...');
        
        // Show the voice chat interface
        const chatInterface = document.getElementById('voice-chat-interface');
        if (chatInterface) {
            chatInterface.style.display = 'block';
            chatInterface.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        
        // Collect current wizard data for the voice agent
        this.collectFormData();
        
        // Initialize voice agent if available
        if (window.voiceAgent && window.voiceAgent.handleVoiceChatStart) {
            console.log('📊 Current wizard data for voice agent:', this.wizardData);
            
            // Update progress summary if gaps analysis is available
            if (window.voiceAgent.analyzeKnowledgeGaps) {
                try {
                    const gaps = window.voiceAgent.analyzeKnowledgeGaps(this.wizardData);
                    console.log('📋 Knowledge gaps identified:', gaps);
                    
                    if (typeof updateVoiceProgressSummary === 'function') {
                        updateVoiceProgressSummary(gaps);
                    }
                } catch (error) {
                    console.error('❌ Error analyzing knowledge gaps:', error);
                }
            }
            
            // Don't call the voice agent directly here - it manages its own button handlers
            // window.voiceAgent.handleVoiceChatStart();
        } else {
            console.error('❌ Voice agent not available');
            
            // Show fallback message in the chat
            const conversation = document.getElementById('voice-chat-messages');
            if (conversation) {
                conversation.innerHTML = `
                    <div class="text-center text-muted py-4">
                        <i class="bi bi-exclamation-triangle fs-1 mb-2 text-warning"></i>
                        <p><strong>Voice agent is loading...</strong></p>
                        <p class="small">Please wait a moment and try again.</p>
                    </div>
                `;
            }
        }
    }

    trackFormChanges() {
        // Track changes to form fields and save to wizardData
        const inputs = document.querySelectorAll('input, textarea, select');
        inputs.forEach(input => {
            input.addEventListener('change', () => {
                this.collectFormData();
            });
        });
    }

    collectFormData() {
        try {
            // Safely get form field values
            const getValue = (id) => {
                const element = document.getElementById(id);
                return element ? element.value || '' : '';
            };
            
            const getChecked = (id) => {
                const element = document.getElementById(id);
                return element ? element.checked || false : false;
            };
            
            // Collect all form data safely - PRESERVE EXISTING CRITICAL DATA
            const preservedData = {
                // Preserve critical fields that aren't form-based
                knowledge_drafts: this.wizardData?.knowledge_drafts || [],
                voice_sessions: this.wizardData?.voice_sessions || [],
                voiceCollectedData: this.wizardData?.voiceCollectedData || [],
                applianceInfo: this.wizardData?.applianceInfo || [],
                procedureInfo: this.wizardData?.procedureInfo || [],
                locationInfo: this.wizardData?.locationInfo || [],
                contactInfo: this.wizardData?.contactInfo || [],
                parkingInfo: this.wizardData?.parkingInfo || [],
                emergencyDetails: this.wizardData?.emergencyDetails || [],
                clarifiedResponses: this.wizardData?.clarifiedResponses || []
            };
            
            this.wizardData = {
                // FIRST: Preserve all existing non-form data
                ...preservedData,
                
                // THEN: Update with current form data
                basic_info: {
                    property_name: getValue('property-name'),
                    property_address: getValue('property-address'),
                    description: getValue('property-description'),
                    checkin_time: getValue('check-in-time'),
                    checkout_time: getValue('check-out-time'),
                    wifi_network: getValue('wifi-network'),
                    wifi_password: getValue('wifi-password')
                },
                airbnb_data: (() => {
                    const currentIcalUrl = getValue('ical-url');
                    const currentDataRequested = getChecked('data-requested');  
                    const existingData = this.wizardData?.airbnb_data || {};
                    
                    return {
                        // Preserve existing data first
                        ...existingData,
                        // Only override ical_url if field has a value, otherwise keep existing
                        ...(currentIcalUrl ? { ical_url: currentIcalUrl } : {}),
                        // Always update data_requested checkbox status
                        data_requested: currentDataRequested
                    };
                })(),
                house_rules: this.collectRulesData(),
                emergency_info: this.collectEmergencyData(),
                local_recommendations: {
                    places: this.collectLocalPlaces()
                },
                property_facts: {
                    ...this.wizardData?.property_facts || {},  // Preserve uploaded file data
                    manual_entry: this.wizardData?.property_facts?.manual_entry || { rooms: [] }
                }
            };
            
            console.log('Form data collected:', this.wizardData);
        } catch (error) {
            console.error('Error collecting form data:', error);
        }
    }

    collectRulesData() {
        const rules = [];
        document.querySelectorAll('[data-rule-id]').forEach(checkbox => {
            const ruleId = checkbox.dataset.ruleId;
            const detailsField = document.querySelector(`[data-rule-details="${ruleId}"]`);
            const customTextField = document.querySelector(`[data-custom-rule-text="${ruleId}"]`);
            
            // Get rule text - custom field takes precedence, otherwise use the span text
            let text = '';
            if (customTextField) {
                text = customTextField.value;
            } else {
                const textSpan = checkbox.closest('.form-section').querySelector('span:not(.toggle-slider)');
                if (textSpan) {
                    // Prioritize saved text attribute (set by inline editing), then display text
                    text = textSpan.getAttribute('data-saved-text') || textSpan.textContent.trim();
                }
            }
            
            rules.push({
                id: ruleId,
                enabled: checkbox.checked,
                text: text,
                details: detailsField ? detailsField.value : ''
            });
        });
        return rules;
    }

    collectEmergencyData() {
        const emergencies = [];
        document.querySelectorAll('[data-emergency-id]').forEach(checkbox => {
            const emergencyId = checkbox.dataset.emergencyId;
            const instructionsField = document.querySelector(`[data-emergency-instructions="${emergencyId}"]`);
            const locationField = document.querySelector(`[data-emergency-location="${emergencyId}"]`);
            const customTitleField = document.querySelector(`[data-custom-emergency-title="${emergencyId}"]`);
            
            // Get title - custom field takes precedence, otherwise use the span.fw-bold text
            let title = '';
            if (customTitleField) {
                title = customTitleField.value;
            } else {
                const titleSpan = checkbox.closest('.form-section').querySelector('span.fw-bold');
                title = titleSpan ? titleSpan.textContent.trim() : '';
            }
            
            emergencies.push({
                id: emergencyId,
                enabled: checkbox.checked,
                title: title,
                instructions: instructionsField ? instructionsField.value : '',
                location: locationField ? locationField.value : ''
            });
        });
        return emergencies;
    }

    collectLocalPlaces() {
        const places = [];
        try {
            document.querySelectorAll('.recommendation-item').forEach(item => {
                const checkbox = item.querySelector('input[type="checkbox"]');
                const nameElement = item.querySelector('strong');
                const typeElement = item.querySelector('small.text-muted');
                const ratingElement = item.querySelector('.badge');
                const addressElement = item.querySelector('small.text-muted:last-of-type');
                const descriptionElement = item.querySelector('small.text-info');
                
                if (item.dataset.placeId) {
                    const place = {
                        name: item.dataset.placeId,
                        type: typeElement ? typeElement.textContent.replace('★', '').trim() : 'general',
                        selected: checkbox ? checkbox.checked : false
                    };
                    
                    // Extract rating from badge if present
                    if (ratingElement && ratingElement.textContent.includes('★')) {
                        place.rating = parseFloat(ratingElement.textContent.replace('★', '').trim());
                    }
                    
                    // Extract address (look for address-like text)
                    const smallElements = item.querySelectorAll('small.text-muted');
                    smallElements.forEach(small => {
                        const text = small.textContent.trim();
                        if (text && !text.match(/^(restaurant|cafe|attractions|recreation|shopping)$/i) && text.includes(',')) {
                            place.address = text;
                        }
                    });
                    
                    // Extract description
                    if (descriptionElement) {
                        place.description = descriptionElement.textContent.trim();
                    }
                    
                    places.push(place);
                }
            });
            
            // If we have stored places data and no DOM places, use stored data
            if (places.length === 0 && this.localPlacesData && this.localPlacesData.length > 0) {
                return this.localPlacesData.map(storedPlace => ({
                    ...storedPlace
                }));
            }
            
            // Merge with stored data if available
            if (this.localPlacesData && this.localPlacesData.length > 0) {
                this.localPlacesData.forEach(storedPlace => {
                    const existingPlace = places.find(p => p.name === storedPlace.name);
                    if (!existingPlace) {
                        places.push({
                            name: storedPlace.name,
                            type: storedPlace.type || 'general',
                            selected: false,
                            rating: storedPlace.rating || 0,
                            address: storedPlace.address || '',
                            description: storedPlace.description || ''
                        });
                    } else {
                        // Merge additional data
                        existingPlace.rating = existingPlace.rating || storedPlace.rating || 0;
                        existingPlace.address = existingPlace.address || storedPlace.address || '';
                        existingPlace.description = existingPlace.description || storedPlace.description || '';
                    }
                });
            }
        } catch (error) {
            console.error('Error collecting local places:', error);
        }
        
        return places;
    }

    nextStep() {
        if (this.validateCurrentStep()) {
            this.collectFormData();
            
            if (this.currentStep < this.totalSteps) {
                this.currentStep++;
                this.updateDisplay();
                this.saveProgress();
                
                // Handle Step 7 initialization
                if (this.currentStep === 7) {
                    this.handleStep7();
                }
            } else {
                this.finishWizard();
            }
        }
    }

    previousStep() {
        if (this.currentStep > 1) {
            this.currentStep--;
            this.updateDisplay();
        }
    }

    validateCurrentStep() {
        // Validate required fields for current step
        if (this.currentStep === 1) {
            const name = document.getElementById('property-name').value;
            const address = document.getElementById('property-address').value;
            
            if (!name || !address) {
                alert('Please fill in the required fields: Property Name and Address');
                return false;
            }
        }
        
        return true;
    }

    updateDisplay() {
        console.log(`Updating display for step ${this.currentStep}`);
        
        // Use inline styles to override the immediate script's inline styles
        document.querySelectorAll('.wizard-step').forEach(step => {
            const stepNumber = parseInt(step.dataset.step);
            if (stepNumber === this.currentStep) {
                // Show current step
                step.style.setProperty('display', 'block', 'important');
                step.style.setProperty('visibility', 'visible', 'important');
                step.style.setProperty('opacity', '1', 'important');
                step.style.setProperty('position', 'relative', 'important');
                step.style.setProperty('left', 'auto', 'important');
                step.classList.add('active');
                console.log(`Showing step ${stepNumber}`);
            } else {
                // Hide other steps
                step.style.setProperty('display', 'none', 'important');
                step.style.setProperty('visibility', 'hidden', 'important');
                step.style.setProperty('opacity', '0', 'important');
                step.style.setProperty('position', 'absolute', 'important');
                step.style.setProperty('left', '-99999px', 'important');
                step.classList.remove('active');
            }
        });

        this.updateProgress();
    }

    updateProgress() {
        // Update progress indicator
        document.querySelectorAll('.progress-step').forEach((step, index) => {
            const stepNum = index + 1;
            const circle = step.querySelector('.step-circle');
            
            // Remove all state classes
            step.classList.remove('active', 'completed');
            circle.classList.remove('active', 'completed');
            
            if (stepNum === this.currentStep) {
                // Current step - active state
                step.classList.add('active');
                circle.classList.add('active');
            } else if (stepNum < this.currentStep) {
                // Completed steps
                step.classList.add('completed');
                circle.classList.add('completed');
                
                // Clear the number and show checkmark
                circle.textContent = '';
            } else {
                // Future steps - show step number
                circle.textContent = stepNum;
            }
        });

        // Update progress bar
        const progressPercentage = (this.currentStep - 1) / (this.totalSteps - 1) * 100;
        const progressBar = document.querySelector('.progress-bar-fill');
        if (progressBar) {
            progressBar.style.width = `${progressPercentage}%`;
        }

        // Update navigation buttons
        const prevBtn = document.getElementById('prev-btn');
        const nextBtn = document.getElementById('next-btn');
        
        if (prevBtn) {
            prevBtn.disabled = this.currentStep === 1;
        }
        
        if (nextBtn) {
            if (this.currentStep === this.totalSteps) {
                nextBtn.innerHTML = 'Create Property <i class="bi bi-check-circle ms-2"></i>';
            } else {
                nextBtn.innerHTML = 'Next <i class="bi bi-arrow-right ms-2"></i>';
            }
        }
    }

    async saveProgress() {
        this.collectFormData();
        
        try {
            const response = await fetch('/setup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    action: 'save_progress',
                    step: this.currentStep,
                    data: this.wizardData
                })
            });

            const result = await response.json();
            if (result.success) {
                // Show brief success indicator
                const saveBtn = document.getElementById('save-progress');
                const originalText = saveBtn.innerHTML;
                saveBtn.innerHTML = '<i class="bi bi-check-circle me-2"></i>Saved';
                setTimeout(() => {
                    saveBtn.innerHTML = originalText;
                }, 2000);
            }
        } catch (error) {
            console.error('Error saving progress:', error);
        }
    }

    async loadProgress() {
        try {
            const response = await fetch('/setup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    action: 'load_progress'
                })
            });

            const result = await response.json();
            if (result.success && result.data && Object.keys(result.data).length > 0) {
                this.wizardData = result.data;
                
                // For better UX, always start at step 1 but still load the data
                // The user can navigate to any step they want
                // if (result.step) {
                //     this.currentStep = result.step;
                // }
                console.log('Data loaded, starting at step 1 for better UX');
                
                // Initialize dynamic content first, then populate
                this.initializeHouseRules();
                this.initializeEmergencyInfo();
                
                // Wait for DOM to update and then populate with retry logic
                this.populateFieldsWithRetry();
                
                console.log('Progress loaded successfully', this.wizardData);
            } else {
                console.log('No previous progress found');
            }
        } catch (error) {
            console.warn('Could not load progress (this is normal for first visit):', error);
        }
    }

    populateFieldsWithRetry(attempt = 0) {
        // Check if key elements exist
        const houseRulesContainer = document.getElementById('house-rules-container');
        const emergencyContainer = document.getElementById('emergency-info-container');
        
        if (houseRulesContainer && emergencyContainer && 
            (houseRulesContainer.children.length > 0 || emergencyContainer.children.length > 0)) {
            // DOM elements are ready, populate fields
            this.populateFormFields();
        } else if (attempt < 10) {
            // Wait a bit more and try again
            setTimeout(() => {
                this.populateFieldsWithRetry(attempt + 1);
            }, 100);
        } else {
            console.warn('Could not populate form fields after multiple attempts');
            // Try to populate anyway in case some elements exist
            this.populateFormFields();
        }
    }

    populateFormFields() {
        try {
            // Populate basic information
            const basicInfo = this.wizardData.basic_info || {};
            this.setFieldValue('property-name', basicInfo.property_name);
            this.setFieldValue('property-address', basicInfo.property_address);
            this.setFieldValue('property-description', basicInfo.description);
            this.setFieldValue('check-in-time', basicInfo.checkin_time);
            this.setFieldValue('check-out-time', basicInfo.checkout_time);
            this.setFieldValue('wifi-network', basicInfo.wifi_network);
            this.setFieldValue('wifi-password', basicInfo.wifi_password);

            // Populate Airbnb data
            const airbnbData = this.wizardData.airbnb_data || {};
            this.setFieldValue('ical-url', airbnbData.ical_url);
            this.setCheckboxValue('data-requested', airbnbData.data_requested);

            // Populate house rules - handle both array and object format
            const houseRules = this.wizardData.house_rules || [];
            if (Array.isArray(houseRules)) {
                houseRules.forEach(rule => {
                    if (rule.id) {
                        // Check if this is a custom rule that needs to be recreated
                        if (rule.id.startsWith('custom-') && !document.getElementById(rule.id)) {
                            this.recreateCustomRule(rule);
                        }
                        
                        this.setCheckboxValue(rule.id, rule.enabled);
                        
                        // Update rule text - be more careful about when to update
                        if (!rule.id.startsWith('custom-')) {
                            // For default rules, store the saved custom text
                            const textElement = document.querySelector(`[data-rule-id="${rule.id}"]`)?.closest('.form-section')?.querySelector('span:not(.toggle-slider)');
                            if (textElement && rule.text) {
                                // Always set the text to what was saved, regardless of what's currently displayed
                                textElement.textContent = rule.text;
                                textElement.setAttribute('data-saved-text', rule.text);
                                console.log(`✓ Restored rule text for ${rule.id}: ${rule.text}`);
                            }
                        }
                        // Update details textarea if it exists
                        const detailsField = document.querySelector(`[data-rule-details="${rule.id}"]`);
                        if (detailsField && rule.details) {
                            detailsField.value = rule.details;
                            console.log(`✓ Updated rule details for ${rule.id}: ${rule.details}`);
                        }
                    }
                });
            } else {
                // Handle legacy object format
                Object.entries(houseRules).forEach(([key, value]) => {
                    if (typeof value === 'object' && value.enabled !== undefined) {
                        this.setCheckboxValue(key, value.enabled);
                    }
                });
            }

            // Populate emergency info - handle both array and object format
            const emergencyInfo = this.wizardData.emergency_info || [];
            if (Array.isArray(emergencyInfo)) {
                emergencyInfo.forEach(emergency => {
                    if (emergency.id) {
                        // Check if this is a custom emergency that needs to be recreated
                        if (emergency.id.startsWith('custom-') && !document.getElementById(emergency.id)) {
                            this.recreateCustomEmergency(emergency);
                        }
                        
                        this.setCheckboxValue(emergency.id, emergency.enabled);
                        // Update title if it was customized
                        const titleElement = document.querySelector(`[data-emergency-id="${emergency.id}"]`)?.closest('.form-section')?.querySelector('span.fw-bold');
                        if (titleElement && emergency.title && emergency.title !== titleElement.textContent) {
                            titleElement.textContent = emergency.title;
                            console.log(`Updated emergency title for ${emergency.id}: ${emergency.title}`);
                        }
                        // Update instructions and location
                        const instructionsField = document.querySelector(`[data-emergency-instructions="${emergency.id}"]`);
                        if (instructionsField && emergency.instructions) {
                            instructionsField.value = emergency.instructions;
                        }
                        const locationField = document.querySelector(`[data-emergency-location="${emergency.id}"]`);
                        if (locationField && emergency.location) {
                            locationField.value = emergency.location;
                        }
                    }
                });
            } else {
                // Handle legacy object format
                Object.entries(emergencyInfo).forEach(([key, value]) => {
                    if (typeof value === 'object' && value.enabled !== undefined) {
                        this.setCheckboxValue(key, value.enabled);
                    }
                });
            }

            // Populate local places if any
            const localData = this.wizardData.local_recommendations || {};
            if (localData.places && localData.places.length > 0) {
                this.localPlacesData = localData.places;
                this.renderLocalPlaces(localData.places);
            }

            // ENHANCED: Preserve and display voice session data if any
            const voiceSessions = this.wizardData.voice_sessions || [];
            if (voiceSessions.length > 0) {
                console.log(`📋 Restored ${voiceSessions.length} voice sessions from Firestore`);
                voiceSessions.forEach((session, index) => {
                    console.log(`  Session ${index + 1}: ${session.sessionId?.slice(-8) || 'unknown'} - ${Object.keys(session.extractedAnswers || {}).length} answers`);
                });
            }

            // ENHANCED: Preserve and display knowledge drafts if any (for Step 7)
            const knowledgeDrafts = this.wizardData.knowledge_drafts || [];
            if (knowledgeDrafts.length > 0) {
                console.log(`📋 Restored ${knowledgeDrafts.length} knowledge drafts from Firestore`);
                // If we're on Step 7, display them immediately
                if (this.currentStep === 7) {
                    this.displayKnowledgeDrafts(knowledgeDrafts);
                }
            }

            // ENHANCED: Log summary of all preserved data for debugging
            const preservedDataSummary = [];
            if (this.wizardData.voice_sessions) preservedDataSummary.push(`${this.wizardData.voice_sessions.length} voice sessions`);
            if (this.wizardData.knowledge_drafts) preservedDataSummary.push(`${this.wizardData.knowledge_drafts.length} knowledge drafts`);
            if (this.wizardData.voiceCollectedData) preservedDataSummary.push(`${this.wizardData.voiceCollectedData.length} voice data entries`);
            if (this.wizardData.applianceInfo) preservedDataSummary.push(`${this.wizardData.applianceInfo.length} appliance entries`);
            if (this.wizardData.parkingInfo) preservedDataSummary.push(`${this.wizardData.parkingInfo.length} parking entries`);
            if (this.wizardData.emergencyDetails) preservedDataSummary.push(`${this.wizardData.emergencyDetails.length} emergency details`);
            
            if (preservedDataSummary.length > 0) {
                console.log(`🔄 Preserved data loaded: ${preservedDataSummary.join(', ')}`);
            }

            console.log('Form fields populated from saved data');
        } catch (error) {
            console.error('Error populating form fields:', error);
        }
    }

    recreateCustomRule(rule) {
        const container = document.getElementById('house-rules-container');
        if (!container) return;
        
        const newRuleHTML = `
            <div class="form-section" data-custom-rule="${rule.id}">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <label class="toggle-switch">
                            <input type="checkbox" id="${rule.id}" ${rule.enabled ? 'checked' : ''} data-rule-id="${rule.id}">
                            <span class="toggle-slider"></span>
                        </label>
                        <span class="ms-3">${rule.text || 'Custom Rule'}</span>
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeCustomRule('${rule.id}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
                <div class="mt-2">
                    <textarea class="form-control form-control-sm" 
                              data-rule-details="${rule.id}" 
                              placeholder="Additional details..."
                              rows="2">${rule.details || ''}</textarea>
                </div>
            </div>
        `;
        
        container.insertAdjacentHTML('beforeend', newRuleHTML);
        console.log(`✓ Recreated custom rule: ${rule.id}`);
    }

    recreateCustomEmergency(emergency) {
        const container = document.getElementById('emergency-info-container');
        if (!container) return;
        
        const newEmergencyHTML = `
            <div class="form-section" data-custom-emergency="${emergency.id}">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="flex-grow-1">
                        <label class="toggle-switch">
                            <input type="checkbox" id="${emergency.id}" ${emergency.enabled ? 'checked' : ''} data-emergency-id="${emergency.id}">
                            <span class="toggle-slider"></span>
                        </label>
                        <span class="ms-3 fw-bold">${emergency.title || 'Custom Emergency'}</span>
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeCustomEmergency('${emergency.id}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
                <div class="row">
                    <div class="col-md-6">
                        <label class="form-label small text-muted">What to do:</label>
                        <textarea class="form-control form-control-sm" 
                                  data-emergency-instructions="${emergency.id}"
                                  rows="3">${emergency.instructions || ''}</textarea>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label small text-muted">Location/Access:</label>
                        <textarea class="form-control form-control-sm" 
                                  data-emergency-location="${emergency.id}"
                                  rows="3">${emergency.location || ''}</textarea>
                    </div>
                </div>
            </div>
        `;
        
        container.insertAdjacentHTML('beforeend', newEmergencyHTML);
        console.log(`✓ Recreated custom emergency: ${emergency.id}`);
    }

    setFieldValue(fieldId, value) {
        const field = document.getElementById(fieldId);
        if (field && value !== undefined && value !== null) {
            field.value = value;
            console.log(`✓ Field ${fieldId} set to: "${value}"`);
        } else if (!field) {
            console.warn(`✗ Field element not found: ${fieldId}`);
        } else {
            console.log(`⚬ Field ${fieldId} skipped (empty value): ${value}`);
        }
    }

    setCheckboxValue(fieldId, value) {
        // Try to find checkbox by id first
        let checkbox = document.getElementById(fieldId);
        
        // If not found by id, try to find by data-rule-id or data-emergency-id
        if (!checkbox) {
            checkbox = document.querySelector(`[data-rule-id="${fieldId}"]`) || 
                      document.querySelector(`[data-emergency-id="${fieldId}"]`);
        }
        
        if (checkbox && typeof value === 'boolean') {
            checkbox.checked = value;
            console.log(`✓ Checkbox ${fieldId} set to ${value}`);
        } else if (!checkbox) {
            console.warn(`✗ Checkbox element not found: ${fieldId}`);
        } else {
            console.warn(`✗ Invalid value for checkbox ${fieldId}: ${value} (type: ${typeof value})`);
        }
    }

    // Step 7: Knowledge Review Implementation
    async handleStep7() {
        console.log("🎯 Starting Step 7: Knowledge Review");
        
        // Show initial loading state
        this.showStep7Loading(true, "Preparing knowledge review...");
        
        try {
            // Check if drafts already exist
            const existingDrafts = this.wizardData.knowledge_drafts;
            
            if (existingDrafts && existingDrafts.length > 0) {
                // Display existing drafts
                console.log(`📋 Found ${existingDrafts.length} existing knowledge drafts`);
                this.displayKnowledgeDrafts(existingDrafts);
            } else {
                // Generate new drafts
                console.log("🔄 Generating new knowledge drafts...");
                await this.generateKnowledgeDrafts();
            }
            
            this.showStep7Loading(false);
            
        } catch (error) {
            console.error("❌ Error in Step 7:", error);
            this.showStep7Error("Failed to load knowledge review. Please try again.");
        }
    }

    async generateKnowledgeDrafts() {
        console.log("🧠 Generating knowledge drafts with AI...");
        
        this.showStep7Loading(true, "AI is analyzing your property information and generating knowledge items...");
        
        try {
            const response = await fetch('/setup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    action: 'generate_knowledge_drafts',
                    wizard_data: this.wizardData
                })
            });

            const result = await response.json();
            
            if (result.success) {
                console.log(`✅ Generated ${result.drafts.length} knowledge drafts`);
                
                // Store drafts in wizard data with persistent storage
                this.wizardData.knowledge_drafts = result.drafts;
                console.log("🔄 Stored knowledge drafts in wizardData:", this.wizardData.knowledge_drafts.length, "items");
                
                // Also ensure global window.wizardInstance is updated
                if (window.wizardInstance) {
                    window.wizardInstance.wizardData.knowledge_drafts = result.drafts;
                    console.log("🔄 Updated global wizardInstance with knowledge drafts");
                }
                
                // Save to Firestore immediately to persist knowledge drafts
                await this.saveProgress();
                
                console.log("💾 Knowledge drafts saved to Firestore for persistent storage");
                
                // Display the drafts
                this.displayKnowledgeDrafts(result.drafts);
                
            } else {
                throw new Error(result.error || 'Failed to generate knowledge drafts');
            }
            
        } catch (error) {
            console.error("❌ Error generating knowledge drafts:", error);
            this.showStep7Error(error.message);
            throw error;
        }
    }

    displayKnowledgeDrafts(drafts) {
        console.log(`📋 Displaying ${drafts.length} knowledge drafts`);
        
        // Group drafts by category
        const groupedDrafts = this.groupDraftsByCategory(drafts);
        
        // Update counts
        this.updateKnowledgeCounts(drafts);
        
        // Render categories
        this.renderKnowledgeCategories(groupedDrafts);
        
        // Setup event listeners
        this.setupKnowledgeEventListeners();
        
        // Show the final instructions
        const instructionsEl = document.getElementById('final-instructions');
        if (instructionsEl) {
            instructionsEl.classList.remove('d-none');
        }
    }

    groupDraftsByCategory(drafts) {
        const groups = {};
        
        drafts.forEach(draft => {
            const category = draft.category || 'General';
            if (!groups[category]) {
                groups[category] = [];
            }
            groups[category].push(draft);
        });
        
        // Sort categories for better display order
        const categoryOrder = ['Basic Information', 'House Rules', 'Emergency Information', 'Local Recommendations', 'Property Facts', 'Voice Session Data', 'General'];
        const sortedGroups = {};
        
        categoryOrder.forEach(category => {
            if (groups[category]) {
                sortedGroups[category] = groups[category];
            }
        });
        
        // Add any remaining categories
        Object.keys(groups).forEach(category => {
            if (!sortedGroups[category]) {
                sortedGroups[category] = groups[category];
            }
        });
        
        return sortedGroups;
    }

    renderKnowledgeCategories(groupedDrafts) {
        const container = document.getElementById('knowledge-categories-container');
        if (!container) {
            console.error("❌ Knowledge categories container not found");
            return;
        }
        
        container.innerHTML = '';
        
        Object.keys(groupedDrafts).forEach(category => {
            const categoryDiv = document.createElement('div');
            categoryDiv.className = 'knowledge-category mb-4';
            
            const items = groupedDrafts[category];
            const approvedCount = items.filter(item => item.status === 'approved').length;
            
            categoryDiv.innerHTML = `
                <div class="category-header d-flex justify-content-between align-items-center mb-3">
                    <h5 class="mb-0">${category}</h5>
                    <div class="category-stats">
                        <span class="badge bg-primary me-2">${items.length} items</span>
                        <span class="badge bg-success">${approvedCount} approved</span>
                    </div>
                </div>
                <div class="category-items">
                    ${items.map(item => this.renderKnowledgeItem(item)).join('')}
                </div>
            `;
            
            container.appendChild(categoryDiv);
        });
    }

    renderKnowledgeItem(item) {
        const statusClass = item.status === 'approved' ? 'approved' : 
                           item.status === 'rejected' ? 'rejected' : 'pending';
        
        const statusIcon = item.status === 'approved' ? 'bi-check-circle-fill' : 
                          item.status === 'rejected' ? 'bi-x-circle-fill' : 'bi-clock';
        
        const typeClass = this.getKnowledgeTypeClass(item.type);
        
        return `
            <div class="knowledge-item ${statusClass}" data-item-id="${item.id}">
                <div class="item-header d-flex justify-content-between align-items-start">
                    <div class="item-info flex-grow-1">
                        <div class="d-flex align-items-center mb-2">
                            <span class="type-badge badge ${typeClass} me-2">${item.type}</span>
                            <span class="status-icon text-${statusClass}"><i class="bi ${statusIcon}"></i></span>
                        </div>
                        <h6 class="item-title mb-1">${item.title}</h6>
                        ${item.question ? `<div class="item-question text-muted small mb-2">${item.question}</div>` : ''}
                    </div>
                    <div class="item-actions">
                        <button class="btn btn-sm btn-outline-secondary me-1" onclick="editKnowledgeItem('${item.id}')" title="Edit">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteKnowledgeItem('${item.id}')" title="Delete">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
                <div class="item-content">
                    <div class="content-text">${item.content}</div>
                </div>
                <div class="item-footer d-flex justify-content-between align-items-center mt-2">
                    <div class="approval-actions">
                        ${item.status !== 'approved' ? `
                            <button class="btn btn-sm btn-success me-2" onclick="approveKnowledgeItem('${item.id}')">
                                <i class="bi bi-check me-1"></i>Approve
                            </button>
                        ` : `
                            <button class="btn btn-sm btn-outline-secondary me-2" onclick="unapproveKnowledgeItem('${item.id}')">
                                <i class="bi bi-arrow-counterclockwise me-1"></i>Unapprove
                            </button>
                        `}
                        ${item.status !== 'rejected' ? `
                            <button class="btn btn-sm btn-outline-warning" onclick="rejectKnowledgeItem('${item.id}')">
                                <i class="bi bi-x me-1"></i>Reject
                            </button>
                        ` : `
                            <button class="btn btn-sm btn-outline-secondary" onclick="unrejectKnowledgeItem('${item.id}')">
                                <i class="bi bi-arrow-counterclockwise me-1"></i>Unreject
                            </button>
                        `}
                    </div>
                    ${item.source ? `<small class="text-muted">Source: ${item.source}</small>` : ''}
                </div>
            </div>
        `;
    }

    getKnowledgeTypeClass(type) {
        const typeClasses = {
            'basic_info': 'bg-primary',
            'house_rule': 'bg-warning',
            'emergency': 'bg-danger',
            'local_recommendation': 'bg-info',
            'property_fact': 'bg-success',
            'voice_data': 'bg-secondary',
            'other': 'bg-dark'
        };
        
        return typeClasses[type] || 'bg-secondary';
    }

    updateKnowledgeCounts(drafts) {
        const totalCount = drafts.length;
        const approvedCount = drafts.filter(item => item.status === 'approved').length;
        const pendingCount = drafts.filter(item => item.status === 'pending').length;
        const rejectedCount = drafts.filter(item => item.status === 'rejected').length;
        
        // Update draft counts in UI
        const totalCountEl = document.getElementById('total-drafts-count');
        const approvedCountEl = document.getElementById('approved-drafts-count');
        const pendingCountEl = document.getElementById('pending-drafts-count');
        
        if (totalCountEl) totalCountEl.textContent = totalCount;
        if (approvedCountEl) approvedCountEl.textContent = approvedCount;
        if (pendingCountEl) pendingCountEl.textContent = pendingCount;
        
        console.log(`📊 Knowledge counts: ${totalCount} total, ${approvedCount} approved, ${pendingCount} pending, ${rejectedCount} rejected`);
    }

    setupKnowledgeEventListeners() {
        // Approve all button
        const approveAllBtn = document.getElementById('approve-all-drafts');
        if (approveAllBtn) {
            approveAllBtn.addEventListener('click', () => this.approveAllKnowledgeItems());
        }
        
        // Add new item button
        const addItemBtn = document.getElementById('add-knowledge-item');
        if (addItemBtn) {
            addItemBtn.addEventListener('click', () => this.showAddKnowledgeItemModal());
        }
        
        console.log("✅ Knowledge review event listeners setup complete");
    }

    async approveAllKnowledgeItems() {
        console.log("👍 Approving all knowledge items...");
        
        const drafts = this.wizardData.knowledge_drafts || [];
        const pendingItems = drafts.filter(item => item.status === 'pending');
        
        if (pendingItems.length === 0) {
            alert("No pending items to approve.");
            return;
        }
        
        // Update all pending items to approved
        drafts.forEach(item => {
            if (item.status === 'pending') {
                item.status = 'approved';
            }
        });
        
        try {
            // Save to backend
            await this.saveKnowledgeDrafts();
            
            // Update display
            this.displayKnowledgeDrafts(drafts);
            
            this.showStep7Success(`Approved ${pendingItems.length} knowledge items!`);
            
        } catch (error) {
            console.error("❌ Error approving all items:", error);
            this.showStep7Error("Failed to approve all items. Please try again.");
        }
    }

    async saveKnowledgeDrafts() {
        try {
            const response = await fetch('/setup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    action: 'save_knowledge_drafts',
                    drafts: this.wizardData.knowledge_drafts
                })
            });

            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error || 'Failed to save knowledge drafts');
            }
            
            // Also save to wizard data
            await this.saveProgress();
            
        } catch (error) {
            console.error("❌ Error saving knowledge drafts:", error);
            throw error;
        }
    }

    showStep7Loading(show, message = "Loading...") {
        const loadingEl = document.getElementById('knowledge-loading');
        const errorEl = document.getElementById('knowledge-error');
        const contentEl = document.getElementById('knowledge-drafts');
        
        if (loadingEl) {
            loadingEl.style.display = show ? 'block' : 'none';
            if (show && message) {
                const messageEl = loadingEl.querySelector('p');
                if (messageEl) messageEl.textContent = message;
            }
        }
        
        if (show) {
            if (errorEl) errorEl.classList.add('d-none');
            if (contentEl) contentEl.classList.add('d-none');
        } else {
            if (contentEl) contentEl.classList.remove('d-none');
        }
    }

    showStep7Success(message) {
        const loadingEl = document.getElementById('knowledge-loading');
        const errorEl = document.getElementById('knowledge-error');
        const contentEl = document.getElementById('knowledge-drafts');
        
        if (loadingEl) loadingEl.style.display = 'none';
        if (errorEl) errorEl.classList.add('d-none');
        if (contentEl) contentEl.classList.remove('d-none');
        
        // Create a temporary success alert
        const instructionsEl = document.getElementById('final-instructions');
        if (instructionsEl) {
            const successAlert = document.createElement('div');
            successAlert.className = 'alert alert-success mb-3';
            successAlert.innerHTML = `<i class="bi bi-check-circle me-2"></i>${message}`;
            instructionsEl.parentNode.insertBefore(successAlert, instructionsEl);
            
            // Auto-hide success message after 5 seconds
            setTimeout(() => {
                if (successAlert.parentNode) {
                    successAlert.parentNode.removeChild(successAlert);
                }
            }, 5000);
        }
    }

    showStep7Error(message) {
        const loadingEl = document.getElementById('knowledge-loading');
        const errorEl = document.getElementById('knowledge-error');
        const contentEl = document.getElementById('knowledge-drafts');
        
        if (loadingEl) loadingEl.style.display = 'none';
        if (contentEl) contentEl.classList.add('d-none');
        
        if (errorEl) {
            errorEl.classList.remove('d-none');
            const messageEl = errorEl.querySelector('p');
            if (messageEl) messageEl.textContent = message;
        }
    }

    showAddKnowledgeItemModal() {
        // Get or create modal
        let modal = document.getElementById('add-knowledge-modal');
        if (!modal) {
            modal = this.createAddKnowledgeModal();
            document.body.appendChild(modal);
        }
        
        // Reset form
        const form = modal.querySelector('form');
        if (form) form.reset();
        
        // Show modal
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }

    createAddKnowledgeModal() {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = 'add-knowledge-modal';
        modal.setAttribute('tabindex', '-1');
        
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Add Knowledge Item</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="add-knowledge-form">
                            <div class="mb-3">
                                <label class="form-label">Type</label>
                                <select class="form-select" name="type" required>
                                    <option value="basic_info">Basic Information</option>
                                    <option value="house_rule">House Rule</option>
                                    <option value="emergency">Emergency Information</option>
                                    <option value="local_recommendation">Local Recommendation</option>
                                    <option value="property_fact">Property Fact</option>
                                    <option value="other">Other</option>
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Title</label>
                                <input type="text" class="form-control" name="title" required>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Content</label>
                                <textarea class="form-control" name="content" rows="4" required></textarea>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Question (optional)</label>
                                <input type="text" class="form-control" name="question" placeholder="What question does this answer?">
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-primary" onclick="saveNewKnowledgeItem()">Add Item</button>
                    </div>
                </div>
            </div>
        `;
        
        return modal;
    }

    async finishWizard() {
        console.log("🏁 Finishing wizard and creating property...");
        
        // Validate Step 7 if we're on Step 7
        if (this.currentStep === 7) {
            const drafts = this.wizardData.knowledge_drafts || [];
            const approvedCount = drafts.filter(item => item.status === 'approved').length;
            
            if (approvedCount === 0) {
                alert('Please approve at least one knowledge item before creating your property.');
                return;
            }
            
            console.log(`✅ Found ${approvedCount} approved knowledge items`);
        }
        
        this.collectFormData();
        
        const loadingOverlay = document.getElementById('loadingOverlay');
        loadingOverlay.style.display = 'flex';
        
        try {
            const response = await fetch('/setup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    action: 'create_property',
                    wizard_data: this.wizardData
                })
            });

            const result = await response.json();
            if (result.success) {
                console.log("✅ Property created successfully!");
                
                // Show success message briefly before redirect
                const successDiv = document.createElement('div');
                successDiv.className = 'alert alert-success position-fixed';
                successDiv.style.cssText = 'top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 9999; min-width: 300px; text-align: center;';
                successDiv.innerHTML = `
                    <h5><i class="bi bi-check-circle me-2"></i>Property Created Successfully!</h5>
                    <p>Redirecting to your properties...</p>
                `;
                document.body.appendChild(successDiv);
                
                // Redirect after brief delay
                setTimeout(() => {
                    window.location.href = '/properties';
                }, 2000);
            } else {
                throw new Error(result.error || 'Unknown error occurred');
            }
        } catch (error) {
            console.error('Error creating property:', error);
            alert('Error creating property: ' + error.message + '\nPlease try again.');
        } finally {
            loadingOverlay.style.display = 'none';
        }
    }
}

// Global functions for onclick handlers
window.editRule = function(ruleId) {
    try {
        const ruleElement = document.querySelector(`[data-rule-id="${ruleId}"]`);
        if (!ruleElement) {
            console.warn('Rule element not found:', ruleId);
            return;
        }
        
        const ruleSection = ruleElement.closest('.form-section');
        const ruleText = ruleSection.querySelector('span:not(.toggle-slider)');
        
        if (!ruleText) {
            console.warn('Rule text element not found:', ruleId);
            return;
        }
        
        // Skip if already editing
        if (ruleSection.querySelector('.editing-input')) {
            return;
        }
        
        // Get the current saved text (prioritize data-saved-text attribute)
        const currentText = ruleText.getAttribute('data-saved-text') || ruleText.textContent.trim();
        
        // Create inline edit input
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'form-control form-control-sm editing-input';
        input.value = currentText; // Pre-populate with current saved text
        input.style.display = 'inline-block';
        input.style.width = '300px';
        input.style.marginRight = '10px';
        
        // Replace text with input
        ruleText.style.display = 'none';
        ruleText.parentNode.insertBefore(input, ruleText);
        
        // Focus on input and select all text
        input.focus();
        input.select();
        
        // Save function
        function saveEdit() {
            const newText = input.value.trim();
            
            // Always restore display first
            ruleText.style.display = '';
            
            // Remove input safely
            try {
                if (input.parentNode) {
                    input.parentNode.removeChild(input);
                }
            } catch (e) {
                // Input might have been removed already
            }
            
            // Only update if text actually changed
            if (newText && newText !== currentText) {
                ruleText.textContent = newText;
                ruleText.setAttribute('data-saved-text', newText);
                console.log(`✓ Rule text updated for ${ruleId}: "${newText}"`);
                
                // Update wizard data after a brief delay to ensure DOM is stable
                setTimeout(() => {
                    if (window.wizardInstance) {
                        window.wizardInstance.collectFormData();
                    }
                }, 100);
            }
        }
        
        // Cancel function
        function cancelEdit() {
            ruleText.style.display = '';
            try {
                if (input.parentNode) {
                    input.parentNode.removeChild(input);
                }
            } catch (e) {
                // Input might have been removed already
            }
        }
        
        // Event listeners
        input.addEventListener('blur', saveEdit);
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                saveEdit();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                cancelEdit();
            }
        });
        
    } catch (error) {
        console.error('Error editing rule:', error);
    }
};

window.editEmergency = function(emergencyId) {
    try {
        const emergencyElement = document.querySelector(`[data-emergency-id="${emergencyId}"]`);
        if (!emergencyElement) {
            console.warn('Emergency element not found:', emergencyId);
            return;
        }
        
        const emergencySection = emergencyElement.closest('.form-section');
        const emergencyTitle = emergencySection.querySelector('span.fw-bold');
        
        if (!emergencyTitle) {
            console.warn('Emergency title not found:', emergencyId);
            return;
        }
        
        // Skip if already editing
        if (emergencySection.querySelector('.editing-input')) {
            return;
        }
        
        // Create a simple inline edit for the title
        const currentTitle = emergencyTitle.textContent.trim();
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'form-control form-control-sm editing-input';
        input.value = currentTitle;
        input.style.display = 'inline-block';
        input.style.width = '80%';
        input.style.marginRight = '10px';
        
        // Replace title with input
        emergencyTitle.style.display = 'none';
        emergencyTitle.parentNode.insertBefore(input, emergencyTitle);
        
        // Focus on input
        input.focus();
        input.select();
        
        // Save on blur or enter
        function saveEdit() {
            try {
                const newTitle = input.value.trim();
                if (newTitle && newTitle !== currentTitle) {
                    emergencyTitle.textContent = newTitle;
                    console.log('Emergency title updated:', emergencyId, newTitle);
                    
                    // Update wizard data
                    if (window.wizardInstance) {
                        window.wizardInstance.collectFormData();
                    }
                }
                
                // Restore original display
                emergencyTitle.style.display = '';
                
                // Safe removal - check if input still exists and has a parent
                if (input && input.parentNode && input.parentNode.contains(input)) {
                    input.parentNode.removeChild(input);
                } else if (input && document.body.contains(input)) {
                    // If input exists somewhere in the DOM, remove it
                    input.remove();
                }
            } catch (error) {
                console.error('Error saving emergency edit:', error);
                // Ensure input is removed even if there's an error
                try {
                    if (input && input.parentNode) {
                        input.remove();
                    }
                } catch (removeError) {
                    console.error('Error removing input element:', removeError);
                }
            }
        }
        
        input.addEventListener('blur', saveEdit);
        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                saveEdit();
            }
            if (e.key === 'Escape') {
                // Cancel edit
                emergencyTitle.style.display = '';
                if (input && input.parentNode && input.parentNode.contains(input)) {
                    input.parentNode.removeChild(input);
                } else if (input && document.body.contains(input)) {
                    input.remove();
                }
            }
        });
        
    } catch (error) {
        console.error('Error editing emergency:', error);
    }
};

window.removeCustomRule = function(ruleId) {
    try {
        const ruleElement = document.querySelector(`[data-custom-rule="${ruleId}"]`);
        if (ruleElement) {
            ruleElement.remove();
            console.log(`✓ Removed custom rule: ${ruleId}`);
            
            // Update wizard data
            if (window.wizardInstance) {
                window.wizardInstance.collectFormData();
            }
        }
    } catch (error) {
        console.error('Error removing custom rule:', error);
    }
};

window.removeCustomEmergency = function(emergencyId) {
    try {
        const emergencyElement = document.querySelector(`[data-custom-emergency="${emergencyId}"]`);
        if (emergencyElement) {
            emergencyElement.remove();
            console.log(`✓ Removed custom emergency: ${emergencyId}`);
            
            // Update wizard data
            if (window.wizardInstance) {
                window.wizardInstance.collectFormData();
            }
        }
    } catch (error) {
        console.error('Error removing custom emergency:', error);
    }
};



window.togglePlaceSelection = function(placeName) {
    try {
        // Escape any special characters in the place name for the selector
        const escapedPlaceName = CSS.escape(placeName);
        const item = document.querySelector(`[data-place-id="${escapedPlaceName}"]`);
        if (!item) {
            console.warn('Place item not found:', placeName);
            return;
        }
        
        const checkbox = item.querySelector('input[type="checkbox"]');
        if (!checkbox) {
            console.warn('Checkbox not found for place:', placeName);
            return;
        }
        
        checkbox.checked = !checkbox.checked;
        item.classList.toggle('selected', checkbox.checked);
        
        // Update the wizard data
        if (window.wizardInstance) {
            window.wizardInstance.collectFormData();
        }
        
        console.log('Place selection toggled:', placeName, checkbox.checked);
    } catch (error) {
        console.error('Error toggling place selection:', error);
    }
};

// Knowledge Review Global Functions
window.approveKnowledgeItem = async function(itemId) {
    try {
        console.log(`👍 Approving knowledge item: ${itemId}`);
        
        if (!window.wizardInstance || !window.wizardInstance.wizardData || !window.wizardInstance.wizardData.knowledge_drafts) {
            console.error("No wizard instance or knowledge drafts found");
            return;
        }
        
        const drafts = window.wizardInstance.wizardData.knowledge_drafts;
        const item = drafts.find(draft => draft.id === itemId);
        
        if (item) {
            item.status = 'approved';
            await window.wizardInstance.saveKnowledgeDrafts();
            window.wizardInstance.displayKnowledgeDrafts(drafts);
            console.log(`✅ Approved knowledge item: ${itemId}`);
        } else {
            console.error(`Knowledge item with ID ${itemId} not found in drafts`);
        }
    } catch (error) {
        console.error('Error approving knowledge item:', error);
    }
};

window.unapproveKnowledgeItem = async function(itemId) {
    try {
        console.log(`↩️ Unapproving knowledge item: ${itemId}`);
        
        if (!window.wizardInstance || !window.wizardInstance.wizardData.knowledge_drafts) {
            console.error("No wizard instance or knowledge drafts found");
            return;
        }
        
        const drafts = window.wizardInstance.wizardData.knowledge_drafts;
        const item = drafts.find(draft => draft.id === itemId);
        
        if (item) {
            item.status = 'pending';
            await window.wizardInstance.saveKnowledgeDrafts();
            window.wizardInstance.displayKnowledgeDrafts(drafts);
            console.log(`✅ Unapproved knowledge item: ${itemId}`);
        }
    } catch (error) {
        console.error('Error unapproving knowledge item:', error);
    }
};

window.rejectKnowledgeItem = async function(itemId) {
    try {
        console.log(`❌ Rejecting knowledge item: ${itemId}`);
        
        if (!window.wizardInstance || !window.wizardInstance.wizardData.knowledge_drafts) {
            console.error("No wizard instance or knowledge drafts found");
            return;
        }
        
        const drafts = window.wizardInstance.wizardData.knowledge_drafts;
        const item = drafts.find(draft => draft.id === itemId);
        
        if (item) {
            item.status = 'rejected';
            await window.wizardInstance.saveKnowledgeDrafts();
            window.wizardInstance.displayKnowledgeDrafts(drafts);
            console.log(`✅ Rejected knowledge item: ${itemId}`);
        }
    } catch (error) {
        console.error('Error rejecting knowledge item:', error);
    }
};

window.unrejectKnowledgeItem = async function(itemId) {
    try {
        console.log(`↩️ Unrejecting knowledge item: ${itemId}`);
        
        if (!window.wizardInstance || !window.wizardInstance.wizardData.knowledge_drafts) {
            console.error("No wizard instance or knowledge drafts found");
            return;
        }
        
        const drafts = window.wizardInstance.wizardData.knowledge_drafts;
        const item = drafts.find(draft => draft.id === itemId);
        
        if (item) {
            item.status = 'pending';
            await window.wizardInstance.saveKnowledgeDrafts();
            window.wizardInstance.displayKnowledgeDrafts(drafts);
            console.log(`✅ Unrejected knowledge item: ${itemId}`);
        }
    } catch (error) {
        console.error('Error unrejecting knowledge item:', error);
    }
};

window.editKnowledgeItem = function(itemId) {
    try {
        console.log(`✏️ Editing knowledge item: ${itemId}`);
        
        if (!window.wizardInstance || !window.wizardInstance.wizardData.knowledge_drafts) {
            console.error("No wizard instance or knowledge drafts found");
            return;
        }
        
        const drafts = window.wizardInstance.wizardData.knowledge_drafts;
        const item = drafts.find(draft => draft.id === itemId);
        
        if (item) {
            showEditKnowledgeItemModal(item);
        }
    } catch (error) {
        console.error('Error editing knowledge item:', error);
    }
};

window.deleteKnowledgeItem = async function(itemId) {
    try {
        console.log(`🗑️ Deleting knowledge item: ${itemId}`);
        
        if (!confirm('Are you sure you want to delete this knowledge item?')) {
            return;
        }
        
        if (!window.wizardInstance || !window.wizardInstance.wizardData.knowledge_drafts) {
            console.error("No wizard instance or knowledge drafts found");
            return;
        }
        
        const drafts = window.wizardInstance.wizardData.knowledge_drafts;
        const itemIndex = drafts.findIndex(draft => draft.id === itemId);
        
        if (itemIndex !== -1) {
            drafts.splice(itemIndex, 1);
            await window.wizardInstance.saveKnowledgeDrafts();
            window.wizardInstance.displayKnowledgeDrafts(drafts);
            console.log(`✅ Deleted knowledge item: ${itemId}`);
        }
    } catch (error) {
        console.error('Error deleting knowledge item:', error);
    }
};

window.saveNewKnowledgeItem = async function() {
    try {
        console.log("💾 Saving new knowledge item...");
        
        const form = document.getElementById('add-knowledge-form');
        if (!form) {
            console.error("Add knowledge form not found");
            return;
        }
        
        const formData = new FormData(form);
        const newItem = {
            id: `item_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            type: formData.get('type'),
            title: formData.get('title'),
            content: formData.get('content'),
            question: formData.get('question') || null,
            status: 'pending',
            source: 'manual',
            category: getCategoryFromType(formData.get('type')),
            created_at: new Date().toISOString()
        };
        
        if (!window.wizardInstance) {
            console.error("No wizard instance found");
            return;
        }
        
        if (!window.wizardInstance.wizardData.knowledge_drafts) {
            window.wizardInstance.wizardData.knowledge_drafts = [];
        }
        
        window.wizardInstance.wizardData.knowledge_drafts.push(newItem);
        await window.wizardInstance.saveKnowledgeDrafts();
        window.wizardInstance.displayKnowledgeDrafts(window.wizardInstance.wizardData.knowledge_drafts);
        
        // Close modal
        const modal = document.getElementById('add-knowledge-modal');
        if (modal) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        }
        
        console.log(`✅ Added new knowledge item: ${newItem.id}`);
        
    } catch (error) {
        console.error('Error saving new knowledge item:', error);
    }
};

function getCategoryFromType(type) {
    const categoryMap = {
        'basic_info': 'Basic Information',
        'house_rule': 'House Rules',
        'emergency': 'Emergency Information',
        'local_recommendation': 'Local Recommendations',
        'property_fact': 'Property Facts',
        'voice_data': 'Voice Session Data',
        'other': 'General'
    };
    
    return categoryMap[type] || 'General';
}

function showEditKnowledgeItemModal(item) {
    // Get or create edit modal
    let modal = document.getElementById('edit-knowledge-modal');
    if (!modal) {
        modal = createEditKnowledgeModal();
        document.body.appendChild(modal);
    }
    
    // Populate form with item data
    const form = modal.querySelector('#edit-knowledge-form');
    if (form) {
        form.dataset.itemId = item.id;
        form.querySelector('[name="type"]').value = item.type || 'other';
        form.querySelector('[name="title"]').value = item.title || '';
        form.querySelector('[name="content"]').value = item.content || '';
        form.querySelector('[name="question"]').value = item.question || '';
    }
    
    // Show modal
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
}

function createEditKnowledgeModal() {
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.id = 'edit-knowledge-modal';
    modal.setAttribute('tabindex', '-1');
    
    modal.innerHTML = `
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Edit Knowledge Item</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <form id="edit-knowledge-form">
                        <div class="mb-3">
                            <label class="form-label">Type</label>
                            <select class="form-select" name="type" required>
                                <option value="basic_info">Basic Information</option>
                                <option value="house_rule">House Rule</option>
                                <option value="emergency">Emergency Information</option>
                                <option value="local_recommendation">Local Recommendation</option>
                                <option value="property_fact">Property Fact</option>
                                <option value="other">Other</option>
                            </select>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Title</label>
                            <input type="text" class="form-control" name="title" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Content</label>
                            <textarea class="form-control" name="content" rows="4" required></textarea>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Question (optional)</label>
                            <input type="text" class="form-control" name="question" placeholder="What question does this answer?">
                        </div>
                    </form>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-primary" onclick="saveEditedKnowledgeItem()">Save Changes</button>
                </div>
            </div>
        </div>
    `;
    
    return modal;
}

window.saveEditedKnowledgeItem = async function() {
    try {
        console.log("💾 Saving edited knowledge item...");
        
        const form = document.getElementById('edit-knowledge-form');
        if (!form) {
            console.error("Edit knowledge form not found");
            return;
        }
        
        const itemId = form.dataset.itemId;
        if (!itemId) {
            console.error("No item ID found in form");
            return;
        }
        
        const formData = new FormData(form);
        
        if (!window.wizardInstance || !window.wizardInstance.wizardData.knowledge_drafts) {
            console.error("No wizard instance or knowledge drafts found");
            return;
        }
        
        const drafts = window.wizardInstance.wizardData.knowledge_drafts;
        const item = drafts.find(draft => draft.id === itemId);
        
        if (item) {
            // Update item properties
            item.type = formData.get('type');
            item.title = formData.get('title');
            item.content = formData.get('content');
            item.question = formData.get('question') || null;
            item.category = getCategoryFromType(formData.get('type'));
            item.updated_at = new Date().toISOString();
            
            await window.wizardInstance.saveKnowledgeDrafts();
            window.wizardInstance.displayKnowledgeDrafts(drafts);
            
            // Close modal
            const modal = document.getElementById('edit-knowledge-modal');
            if (modal) {
                const bsModal = bootstrap.Modal.getInstance(modal);
                if (bsModal) bsModal.hide();
            }
            
            console.log(`✅ Updated knowledge item: ${itemId}`);
        }
        
    } catch (error) {
        console.error('Error saving edited knowledge item:', error);
    }
};

// Initialize wizard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing wizard...');
    try {
        window.wizardInstance = new PropertySetupWizard();
        console.log('Wizard instance created and stored globally');
    } catch (error) {
        console.error('Failed to create wizard instance:', error);
    }
}); 