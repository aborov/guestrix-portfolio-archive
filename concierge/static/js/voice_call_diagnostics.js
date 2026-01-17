/*
 * Voice Call Diagnostics System
 * Comprehensive logging and monitoring for voice call quality and issues
 */

// Voice Call Diagnostics Class
class VoiceCallDiagnostics {
    constructor(sessionId, propertyId, userId) {
        this.sessionId = sessionId;
        this.propertyId = propertyId;
        this.userId = userId;
        this.startTime = Date.now();
        this.lastMetricTime = this.startTime;

        // Session state tracking
        this.sessionInitialized = false;
        this.fallbackMode = false;
        this.initializationAttempts = 0;
        this.initializationErrors = [];
        this.fallbackSessionData = null;

        // Rate limiting for API calls
        this.lastEventTime = 0;
        this.eventQueue = [];
        this.isProcessingQueue = false;

        // Quality metrics tracking
        this.metrics = {
            connectionLatency: [],
            audioDropouts: 0,
            transcriptionErrors: 0,
            interruptionCount: 0,
            reconnectionCount: 0,
            averageResponseTime: [],
            audioQualityIssues: [],
            webSocketEvents: [],
            memoryUsage: [],
            bufferUnderruns: 0,
            bufferOverruns: 0
        };

        // Error and event tracking
        this.errors = [];
        this.warnings = [];
        this.eventTimeline = [];

        // Performance monitoring
        this.performanceObserver = null;
        this.memoryMonitorInterval = null;

        console.log(`[VoiceCallDiagnostics] Initialized for session ${sessionId}`);
    }
    
    // === CLIENT DIAGNOSTICS COLLECTION ===
    
    static collectClientDiagnostics() {
        const diagnostics = {
            // Browser Information
            userAgent: navigator.userAgent,
            browserName: VoiceCallDiagnostics.getBrowserName(),
            browserVersion: VoiceCallDiagnostics.getBrowserVersion(),
            platform: navigator.platform,
            language: navigator.language,
            languages: navigator.languages,
            
            // Device Capabilities
            mediaDevices: {
                supported: !!navigator.mediaDevices,
                enumerateDevices: !!navigator.mediaDevices?.enumerateDevices,
                getUserMedia: !!navigator.mediaDevices?.getUserMedia
            },
            
            // Audio Context Support
            audioContext: {
                supported: !!(window.AudioContext || window.webkitAudioContext),
                sampleRate: null, // Will be set after creation
                state: null,
                maxChannelCount: null
            },
            
            // WebSocket Support
            webSocket: {
                supported: !!window.WebSocket,
                extensions: null // Will be populated after connection
            },
            
            // Network Information (if available)
            connection: navigator.connection ? {
                effectiveType: navigator.connection.effectiveType,
                downlink: navigator.connection.downlink,
                rtt: navigator.connection.rtt,
                saveData: navigator.connection.saveData
            } : null,
            
            // Screen Information
            screen: {
                width: screen.width,
                height: screen.height,
                colorDepth: screen.colorDepth,
                pixelDepth: screen.pixelDepth
            },
            
            // Memory Information (if available)
            memory: navigator.deviceMemory || null,
            
            // Hardware Concurrency
            hardwareConcurrency: navigator.hardwareConcurrency || null,
            
            // Timezone
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            
            // Timestamp
            timestamp: new Date().toISOString()
        };
        
        return diagnostics;
    }
    
    static getBrowserName() {
        const userAgent = navigator.userAgent;
        if (userAgent.includes('Chrome')) return 'Chrome';
        if (userAgent.includes('Firefox')) return 'Firefox';
        if (userAgent.includes('Safari')) return 'Safari';
        if (userAgent.includes('Edge')) return 'Edge';
        if (userAgent.includes('Opera')) return 'Opera';
        return 'Unknown';
    }
    
    static getBrowserVersion() {
        const userAgent = navigator.userAgent;
        const match = userAgent.match(/(Chrome|Firefox|Safari|Edge|Opera)\/(\d+)/);
        return match ? match[2] : 'Unknown';
    }
    
    static async assessNetworkQuality() {
        return new Promise((resolve) => {
            const startTime = performance.now();
            const testImage = new Image();
            
            testImage.onload = () => {
                const loadTime = performance.now() - startTime;
                resolve({
                    latency: loadTime,
                    timestamp: new Date().toISOString(),
                    connectionType: navigator.connection?.effectiveType || 'unknown'
                });
            };
            
            testImage.onerror = () => {
                resolve({
                    latency: -1,
                    error: 'Network test failed',
                    timestamp: new Date().toISOString()
                });
            };
            
            // Use a small test resource from the same domain
            testImage.src = '/favicon.ico?' + Date.now();
        });
    }
    
    // === EVENT LOGGING ===
    
    async logEvent(eventType, details = {}, errorInfo = null, warningInfo = null) {
        const timestamp = new Date().toISOString();

        // Add to local timeline
        this.eventTimeline.push({
            timestamp,
            event: eventType,
            details
        });

        // Track errors and warnings locally
        if (errorInfo) {
            this.errors.push({ timestamp, event: eventType, error: errorInfo });
        }
        if (warningInfo) {
            this.warnings.push({ timestamp, event: eventType, warning: warningInfo });
        }

        console.log(`[VoiceCallDiagnostics] Event: ${eventType}`, details);

        // Rate limit API calls - only send important events immediately
        const importantEvents = ['SESSION_INITIALIZED', 'CALL_STARTED', 'CALL_ENDING', 'WEBSOCKET_ERROR', 'MICROPHONE_ACCESS_DENIED'];

        if (importantEvents.includes(eventType)) {
            // Send important events immediately
            this.sendEventToBackend(eventType, details, errorInfo, warningInfo);
        } else {
            // Queue less important events and send in batches
            this.eventQueue.push({
                event_type: eventType,
                details,
                error_info: errorInfo,
                warning_info: warningInfo,
                timestamp
            });

            // Process queue every 10 seconds
            if (!this.isProcessingQueue) {
                setTimeout(() => this.processEventQueue(), 10000);
                this.isProcessingQueue = true;
            }
        }
    }

    async sendEventToBackend(eventType, details, errorInfo, warningInfo) {
        try {
            await fetch('/api/voice-call/event', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    event_type: eventType,
                    details,
                    error_info: errorInfo,
                    warning_info: warningInfo
                })
            });
        } catch (error) {
            console.error(`[VoiceCallDiagnostics] Failed to log event ${eventType}:`, error);
        }
    }

    async processEventQueue() {
        if (this.eventQueue.length === 0) {
            this.isProcessingQueue = false;
            return;
        }

        // Send up to 5 events at once
        const eventsToSend = this.eventQueue.splice(0, 5);

        for (const event of eventsToSend) {
            await this.sendEventToBackend(
                event.event_type,
                event.details,
                event.error_info,
                event.warning_info
            );

            // Small delay between events
            await new Promise(resolve => setTimeout(resolve, 100));
        }

        // Continue processing if there are more events
        if (this.eventQueue.length > 0) {
            setTimeout(() => this.processEventQueue(), 5000);
        } else {
            this.isProcessingQueue = false;
        }
    }
    
    // === QUALITY MONITORING ===
    
    assessAudioQuality(audioBuffer) {
        if (!audioBuffer || audioBuffer.byteLength === 0) {
            return null;
        }
        
        const analysis = {
            timestamp: Date.now(),
            bufferSize: audioBuffer.byteLength,
            silenceRatio: this.calculateSilenceRatio(audioBuffer),
            energyLevel: this.calculateEnergyLevel(audioBuffer),
            clippingDetected: this.detectClipping(audioBuffer),
            noiseLevel: this.calculateNoiseLevel(audioBuffer)
        };
        
        // Log quality issues
        if (analysis.silenceRatio > 0.8) {
            this.logEvent('AUDIO_QUALITY_WARNING', analysis, null, 'High silence ratio detected');
        }
        
        if (analysis.clippingDetected) {
            this.logEvent('AUDIO_QUALITY_WARNING', analysis, null, 'Audio clipping detected');
        }
        
        return analysis;
    }
    
    calculateSilenceRatio(audioBuffer) {
        try {
            const view = new DataView(audioBuffer);
            const numSamples = Math.floor(audioBuffer.byteLength / 2);
            let silentSamples = 0;
            const threshold = 100; // Silence threshold
            
            for (let i = 0; i < numSamples; i += 10) { // Sample every 10th sample
                const sample = Math.abs(view.getInt16(i * 2, true));
                if (sample < threshold) silentSamples++;
            }
            
            return silentSamples / (numSamples / 10);
        } catch (error) {
            console.warn('[VoiceCallDiagnostics] Error calculating silence ratio:', error);
            return 0;
        }
    }
    
    calculateEnergyLevel(audioBuffer) {
        try {
            const view = new DataView(audioBuffer);
            const numSamples = Math.floor(audioBuffer.byteLength / 2);
            let totalEnergy = 0;
            
            for (let i = 0; i < numSamples; i += 10) { // Sample every 10th sample
                const sample = view.getInt16(i * 2, true);
                totalEnergy += Math.abs(sample);
            }
            
            return totalEnergy / (numSamples / 10);
        } catch (error) {
            console.warn('[VoiceCallDiagnostics] Error calculating energy level:', error);
            return 0;
        }
    }
    
    detectClipping(audioBuffer) {
        try {
            const view = new DataView(audioBuffer);
            const numSamples = Math.floor(audioBuffer.byteLength / 2);
            const clippingThreshold = 32000; // Near max int16 value
            
            for (let i = 0; i < numSamples; i += 10) { // Sample every 10th sample
                const sample = Math.abs(view.getInt16(i * 2, true));
                if (sample > clippingThreshold) {
                    return true;
                }
            }
            
            return false;
        } catch (error) {
            console.warn('[VoiceCallDiagnostics] Error detecting clipping:', error);
            return false;
        }
    }
    
    calculateNoiseLevel(audioBuffer) {
        // Simple noise level calculation - could be enhanced
        return this.calculateEnergyLevel(audioBuffer);
    }
    
    // === WEBSOCKET MONITORING ===
    
    monitorWebSocketHealth(webSocket) {
        if (!webSocket) return null;
        
        const metrics = {
            readyState: webSocket.readyState,
            bufferedAmount: webSocket.bufferedAmount,
            protocol: webSocket.protocol,
            extensions: webSocket.extensions,
            timestamp: Date.now()
        };
        
        // Monitor buffer buildup
        if (metrics.bufferedAmount > 1024 * 1024) { // 1MB threshold
            this.logEvent('WEBSOCKET_WARNING', metrics, null, 'WebSocket buffer buildup detected');
        }
        
        return metrics;
    }
    
    // === PERFORMANCE MONITORING ===
    
    startPerformanceMonitoring() {
        // Monitor memory usage every 10 seconds
        this.memoryMonitorInterval = setInterval(() => {
            this.recordMemoryUsage();
        }, 10000);
        
        console.log('[VoiceCallDiagnostics] Started performance monitoring');
    }
    
    stopPerformanceMonitoring() {
        if (this.memoryMonitorInterval) {
            clearInterval(this.memoryMonitorInterval);
            this.memoryMonitorInterval = null;
        }
        
        console.log('[VoiceCallDiagnostics] Stopped performance monitoring');
    }
    
    recordMemoryUsage() {
        if (performance.memory) {
            const memoryInfo = {
                usedJSHeapSize: performance.memory.usedJSHeapSize,
                totalJSHeapSize: performance.memory.totalJSHeapSize,
                jsHeapSizeLimit: performance.memory.jsHeapSizeLimit,
                timestamp: Date.now()
            };
            
            this.metrics.memoryUsage.push(memoryInfo);
            
            // Keep only last 20 memory readings
            if (this.metrics.memoryUsage.length > 20) {
                this.metrics.memoryUsage.shift();
            }
            
            // Check for memory issues
            const usageRatio = memoryInfo.usedJSHeapSize / memoryInfo.jsHeapSizeLimit;
            if (usageRatio > 0.8) {
                this.logEvent('MEMORY_WARNING', memoryInfo, null, 'High memory usage detected');
            }
        }
    }
    
    // === METRICS UPDATES ===
    
    async updateMetrics(metricsUpdate) {
        // Merge with local metrics
        Object.assign(this.metrics, metricsUpdate);
        
        try {
            await fetch('/api/voice-call/metrics/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    metrics: { QualityMetrics: metricsUpdate }
                })
            });
        } catch (error) {
            console.error('[VoiceCallDiagnostics] Failed to update metrics:', error);
        }
    }
    
    // === SESSION MANAGEMENT ===

    async initializeSession(guestName = null, reservationId = null, maxRetries = 3) {
        const clientDiagnostics = VoiceCallDiagnostics.collectClientDiagnostics();
        const networkQuality = await VoiceCallDiagnostics.assessNetworkQuality();

        // Track initialization attempts
        this.initializationAttempts = 0;
        this.initializationErrors = [];

        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            this.initializationAttempts = attempt;

            try {
                console.log(`[VoiceCallDiagnostics] Session initialization attempt ${attempt}/${maxRetries}`);

                const response = await fetch('/api/voice-call/session/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: this.sessionId,
                        property_id: this.propertyId,
                        user_id: this.userId,
                        client_diagnostics: clientDiagnostics,
                        network_quality: networkQuality,
                        guest_name: guestName,
                        reservation_id: reservationId
                    }),
                    timeout: 10000  // 10 second timeout
                });

                if (response.ok) {
                    const result = await response.json();
                    console.log('[VoiceCallDiagnostics] Session initialized successfully on attempt', attempt);
                    this.sessionInitialized = true;
                    this.startPerformanceMonitoring();

                    // Log successful initialization
                    this.logEvent('SESSION_INITIALIZATION_SUCCESS', {
                        attempt: attempt,
                        total_attempts: this.initializationAttempts,
                        guest_name: guestName,
                        reservation_id: reservationId
                    });

                    return true;
                } else {
                    const errorText = await response.text();
                    const error = `HTTP ${response.status}: ${errorText}`;
                    this.initializationErrors.push(error);

                    console.error(`[VoiceCallDiagnostics] Session initialization failed on attempt ${attempt}: ${error}`);

                    // Don't retry on certain errors
                    if (response.status === 400 || response.status === 401 || response.status === 403) {
                        console.error('[VoiceCallDiagnostics] Non-retryable error, stopping attempts');
                        break;
                    }

                    // Wait before retry (exponential backoff)
                    if (attempt < maxRetries) {
                        const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000); // Max 5 seconds
                        console.log(`[VoiceCallDiagnostics] Waiting ${delay}ms before retry...`);
                        await new Promise(resolve => setTimeout(resolve, delay));
                    }
                }
            } catch (error) {
                const errorMsg = error.message || 'Unknown error';
                this.initializationErrors.push(errorMsg);

                console.error(`[VoiceCallDiagnostics] Session initialization error on attempt ${attempt}:`, error);

                // Wait before retry on network errors
                if (attempt < maxRetries) {
                    const delay = Math.min(1000 * Math.pow(2, attempt - 1), 5000);
                    console.log(`[VoiceCallDiagnostics] Waiting ${delay}ms before retry...`);
                    await new Promise(resolve => setTimeout(resolve, delay));
                }
            }
        }

        // All attempts failed - enable fallback mode
        console.error('[VoiceCallDiagnostics] All session initialization attempts failed, enabling fallback mode');
        this.sessionInitialized = false;
        this.fallbackMode = true;

        // Log the failure with all error details
        this.logEvent('SESSION_INITIALIZATION_FAILED', {
            total_attempts: this.initializationAttempts,
            errors: this.initializationErrors,
            guest_name: guestName,
            reservation_id: reservationId,
            fallback_enabled: true
        });

        // Start performance monitoring even in fallback mode
        this.startPerformanceMonitoring();

        // Try to create a local fallback session record
        await this.createFallbackSession(guestName, reservationId, clientDiagnostics, networkQuality);

        return false; // Indicate initialization failed, but system continues in fallback mode
    }
    
    async finalizeSession(endReason, finalMetrics = {}) {
        this.stopPerformanceMonitoring();

        // Calculate final metrics
        const sessionDuration = Date.now() - this.startTime;
        const enhancedFinalMetrics = {
            ...finalMetrics,
            sessionDuration,
            totalEvents: this.eventTimeline.length,
            totalErrors: this.errors.length,
            totalWarnings: this.warnings.length,
            averageMemoryUsage: this.calculateAverageMemoryUsage(),
            initializationAttempts: this.initializationAttempts,
            initializationErrors: this.initializationErrors,
            fallbackMode: this.fallbackMode
        };

        // Log finalization event
        await this.logEvent('SESSION_FINALIZATION', {
            end_reason: endReason,
            final_metrics: enhancedFinalMetrics
        });

        if (this.sessionInitialized) {
            // Normal session finalization
            try {
                // Fire-and-forget guaranteed finalize first
                try {
                    fetch('/api/voice-call/session/finalize', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ session_id: this.sessionId, end_reason: endReason }),
                        keepalive: true
                    });
                } catch (e) {
                    // ignore
                }

                await fetch('/api/voice-call/session/end', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: this.sessionId,
                        end_reason: endReason,
                        final_metrics: enhancedFinalMetrics
                    }),
                    timeout: 10000
                });

                console.log(`[VoiceCallDiagnostics] Session finalized with reason: ${endReason}`);
            } catch (error) {
                console.error('[VoiceCallDiagnostics] Failed to finalize session:', error);
                // Fall back to uploading fallback data
                this.fallbackMode = true;
            }
        }

        if (this.fallbackMode) {
            // Try to upload all fallback data
            console.log('[VoiceCallDiagnostics] Finalizing session in fallback mode');
            const uploadSuccess = await this.uploadFallbackData();

            if (uploadSuccess) {
                console.log(`[VoiceCallDiagnostics] Fallback session finalized with reason: ${endReason}`);
            } else {
                console.error('[VoiceCallDiagnostics] Failed to upload fallback data, keeping in localStorage');
                // Data remains in localStorage for potential later upload
            }
        }
    }
    
    calculateAverageMemoryUsage() {
        if (this.metrics.memoryUsage.length === 0) return 0;

        const totalUsage = this.metrics.memoryUsage.reduce((sum, usage) => sum + usage.usedJSHeapSize, 0);
        return totalUsage / this.metrics.memoryUsage.length;
    }

    // === FALLBACK SESSION MANAGEMENT ===

    async createFallbackSession(guestName, reservationId, clientDiagnostics, networkQuality) {
        console.log('[VoiceCallDiagnostics] Creating fallback session record');

        // Store session data locally for later upload
        this.fallbackSessionData = {
            sessionId: this.sessionId,
            propertyId: this.propertyId,
            userId: this.userId,
            guestName: guestName,
            reservationId: reservationId,
            clientDiagnostics: clientDiagnostics,
            networkQuality: networkQuality,
            startTime: new Date().toISOString(),
            initializationErrors: this.initializationErrors,
            events: [],
            transcripts: [],
            metrics: {},
            status: 'FALLBACK_MODE'
        };

        // Store in localStorage as backup
        try {
            localStorage.setItem(`voice_session_${this.sessionId}`, JSON.stringify(this.fallbackSessionData));
            console.log('[VoiceCallDiagnostics] Fallback session data stored in localStorage');
        } catch (error) {
            console.error('[VoiceCallDiagnostics] Failed to store fallback session in localStorage:', error);
        }

        // Try to upload the fallback session to a different endpoint
        try {
            await fetch('/api/voice-call/session/fallback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.fallbackSessionData),
                timeout: 5000
            });
            console.log('[VoiceCallDiagnostics] Fallback session uploaded successfully');
        } catch (error) {
            console.error('[VoiceCallDiagnostics] Failed to upload fallback session:', error);
            // Continue anyway - we have localStorage backup
        }
    }

    async uploadFallbackData() {
        if (!this.fallbackMode || !this.fallbackSessionData) {
            return;
        }

        console.log('[VoiceCallDiagnostics] Attempting to upload fallback session data');

        // Update fallback data with current state
        this.fallbackSessionData.events = this.eventTimeline;
        this.fallbackSessionData.metrics = this.metrics;
        this.fallbackSessionData.endTime = new Date().toISOString();
        this.fallbackSessionData.duration = Date.now() - this.startTime;

        try {
            const response = await fetch('/api/voice-call/session/fallback-upload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.fallbackSessionData),
                timeout: 10000
            });

            if (response.ok) {
                console.log('[VoiceCallDiagnostics] Fallback data uploaded successfully');
                // Clear localStorage backup
                localStorage.removeItem(`voice_session_${this.sessionId}`);
                return true;
            } else {
                console.error('[VoiceCallDiagnostics] Failed to upload fallback data:', response.status);
                return false;
            }
        } catch (error) {
            console.error('[VoiceCallDiagnostics] Error uploading fallback data:', error);
            return false;
        }
    }

    // Enhanced event logging that works in fallback mode
    async logEvent(eventType, details = null, errorInfo = null, warningInfo = null) {
        const timestamp = new Date().toISOString();
        const event = {
            timestamp,
            event: eventType,
            details: details || {},
            error: errorInfo,
            warning: warningInfo
        };

        // Always store locally
        this.eventTimeline.push(event);

        if (errorInfo) {
            this.errors.push({ timestamp, event: eventType, error: errorInfo });
        }

        if (warningInfo) {
            this.warnings.push({ timestamp, event: eventType, warning: warningInfo });
        }

        // Enhanced console logging with context
        this.logToConsole(eventType, details, errorInfo, warningInfo);

        // Try to send to backend if session is initialized
        if (this.sessionInitialized) {
            await this.sendEventToBackend(eventType, details, errorInfo, warningInfo);
        } else if (this.fallbackMode) {
            // In fallback mode, update the fallback data
            if (this.fallbackSessionData) {
                this.fallbackSessionData.events = this.eventTimeline;

                // Update localStorage
                try {
                    localStorage.setItem(`voice_session_${this.sessionId}`, JSON.stringify(this.fallbackSessionData));
                } catch (error) {
                    console.error('[VoiceCallDiagnostics] Failed to update localStorage:', error);
                }
            }

            console.log(`[VoiceCallDiagnostics] Event logged in fallback mode: ${eventType}`);
        }
    }

    // Comprehensive console logging with context
    logToConsole(eventType, details, errorInfo, warningInfo) {
        const sessionInfo = `Session: ${this.sessionId} | Property: ${this.propertyId}`;
        const modeInfo = this.sessionInitialized ? 'NORMAL' : (this.fallbackMode ? 'FALLBACK' : 'INITIALIZING');
        const prefix = `[VoiceCallDiagnostics|${modeInfo}] ${sessionInfo}`;

        if (errorInfo) {
            console.error(`${prefix} ERROR - ${eventType}:`, {
                error: errorInfo,
                details: details,
                timestamp: new Date().toISOString(),
                sessionState: {
                    initialized: this.sessionInitialized,
                    fallbackMode: this.fallbackMode,
                    initializationAttempts: this.initializationAttempts,
                    totalEvents: this.eventTimeline.length,
                    totalErrors: this.errors.length
                }
            });
        } else if (warningInfo) {
            console.warn(`${prefix} WARNING - ${eventType}:`, {
                warning: warningInfo,
                details: details,
                timestamp: new Date().toISOString(),
                sessionState: {
                    initialized: this.sessionInitialized,
                    fallbackMode: this.fallbackMode,
                    initializationAttempts: this.initializationAttempts
                }
            });
        } else {
            console.log(`${prefix} ${eventType}:`, {
                details: details,
                timestamp: new Date().toISOString()
            });
        }
    }

    // Debug information dump
    dumpDiagnosticInfo() {
        const info = {
            sessionId: this.sessionId,
            propertyId: this.propertyId,
            userId: this.userId,
            sessionInitialized: this.sessionInitialized,
            fallbackMode: this.fallbackMode,
            initializationAttempts: this.initializationAttempts,
            initializationErrors: this.initializationErrors,
            totalEvents: this.eventTimeline.length,
            totalErrors: this.errors.length,
            totalWarnings: this.warnings.length,
            sessionDuration: Date.now() - this.startTime,
            fallbackSessionData: this.fallbackSessionData ? 'Present' : 'None',
            localStorageKey: `voice_session_${this.sessionId}`,
            hasLocalStorageData: !!localStorage.getItem(`voice_session_${this.sessionId}`)
        };

        console.group(`[VoiceCallDiagnostics] Diagnostic Information - ${this.sessionId}`);
        console.table(info);
        console.log('Recent Events:', this.eventTimeline.slice(-5));
        console.log('All Errors:', this.errors);
        console.log('All Warnings:', this.warnings);
        console.groupEnd();

        return info;
    }

    // === SESSION RECOVERY ===

    static recoverOrphanedSessions() {
        // Recover any orphaned sessions from localStorage
        console.log('[VoiceCallDiagnostics] Checking for orphaned sessions in localStorage');

        const orphanedSessions = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.startsWith('voice_session_')) {
                try {
                    const sessionData = JSON.parse(localStorage.getItem(key));
                    const sessionAge = Date.now() - new Date(sessionData.startTime).getTime();

                    // Consider sessions older than 1 hour as orphaned
                    if (sessionAge > 60 * 60 * 1000) {
                        orphanedSessions.push({
                            key: key,
                            sessionId: sessionData.sessionId,
                            age: sessionAge,
                            data: sessionData
                        });
                    }
                } catch (error) {
                    console.error(`[VoiceCallDiagnostics] Error parsing orphaned session ${key}:`, error);
                }
            }
        }

        if (orphanedSessions.length > 0) {
            console.log(`[VoiceCallDiagnostics] Found ${orphanedSessions.length} orphaned sessions`);

            // Try to upload orphaned sessions
            orphanedSessions.forEach(async (session) => {
                try {
                    const response = await fetch('/api/voice-call/session/fallback-upload', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(session.data),
                        timeout: 10000
                    });

                    if (response.ok) {
                        console.log(`[VoiceCallDiagnostics] Uploaded orphaned session: ${session.sessionId}`);
                        localStorage.removeItem(session.key);
                    } else {
                        console.error(`[VoiceCallDiagnostics] Failed to upload orphaned session: ${session.sessionId}`);
                    }
                } catch (error) {
                    console.error(`[VoiceCallDiagnostics] Error uploading orphaned session ${session.sessionId}:`, error);
                }
            });
        }

        return orphanedSessions;
    }

    static setupGlobalErrorHandling() {
        // Setup global error handling for voice call diagnostics

        // Handle unhandled promise rejections
        window.addEventListener('unhandledrejection', (event) => {
            if (event.reason && event.reason.message && event.reason.message.includes('voice')) {
                console.error('[VoiceCallDiagnostics] Unhandled voice-related promise rejection:', event.reason);

                // Try to log this error to any active diagnostics sessions
                if (window.activeVoiceCallDiagnostics) {
                    window.activeVoiceCallDiagnostics.logEvent('UNHANDLED_PROMISE_REJECTION', {
                        error: event.reason.message,
                        stack: event.reason.stack
                    }, event.reason);
                }
            }
        });

        // Handle general errors
        window.addEventListener('error', (event) => {
            if (event.error && event.error.message && event.error.message.includes('voice')) {
                console.error('[VoiceCallDiagnostics] Unhandled voice-related error:', event.error);

                // Try to log this error to any active diagnostics sessions
                if (window.activeVoiceCallDiagnostics) {
                    window.activeVoiceCallDiagnostics.logEvent('UNHANDLED_ERROR', {
                        message: event.error.message,
                        filename: event.filename,
                        lineno: event.lineno,
                        colno: event.colno
                    }, event.error);
                }
            }
        });

        console.log('[VoiceCallDiagnostics] Global error handling setup complete');
    }
}

// Setup global error handling when the script loads
VoiceCallDiagnostics.setupGlobalErrorHandling();

// Recover orphaned sessions when the page loads
document.addEventListener('DOMContentLoaded', () => {
    VoiceCallDiagnostics.recoverOrphanedSessions();
});

// Export for use in other modules
window.VoiceCallDiagnostics = VoiceCallDiagnostics;
