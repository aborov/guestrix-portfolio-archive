# Release Notes

## Version 1.0.6 - 2025-10-13

### Changes
- **Google Places API Integration for Location-Based Recommendations**
  - Implemented comprehensive Google Places API integration to replace generic web search for location queries
  - Provides accurate distances, travel times (walking/driving/transit/bicycling), ratings, and real-time business hours
  - Integrated as a function calling tool (`search_nearby_places`) for the AI assistant
  - Automatic geocoding of property addresses for precise location-based searches
  - Results include structured data: ratings (1-5 stars), review counts, price levels (1-4), open/closed status
  - Distance calculation with multiple travel modes and walkability indicators
  - Comprehensive error handling with graceful fallback to Google Search when API unavailable

- **Enhanced AI Assistant Capabilities**
  - Updated system prompts to prioritize Places API for restaurant, cafe, attraction, and local business queries
  - AI now provides 1-2 targeted recommendations with accurate distance and travel time information
  - Improved presentation format with ratings, hours, price levels, and walkability indicators
  - Seamless integration with both text chat and voice call interfaces

- **API Configuration and Documentation**
  - Added complete setup guide for Google Places API configuration (`docs/GOOGLE_PLACES_API_SETUP.md`)
  - Created quick start reference guide (`docs/PLACES_API_QUICK_START.md`)
  - Implemented comprehensive test suite (`test_places_api_integration.py`) with 7 test scenarios
  - Environment-based API key configuration with conditional feature enabling

### Technical Details
- **New Files Created**:
  - `concierge/utils/places_api.py` - Core Places API integration module
    - `search_nearby_places()` - Search for places by type/keyword with filters
    - `calculate_distance_and_duration()` - Get accurate travel times and distances
    - `get_place_details()` - Retrieve detailed info (hours, reviews, website, phone)
    - `find_nearby_with_details()` - Comprehensive search combining all features
    - `get_coordinates_from_address()` - Geocoding for property addresses
    - `format_place_for_response()` - Format results for AI presentation
  - `docs/GOOGLE_PLACES_API_SETUP.md` - Complete setup and troubleshooting guide
  - `docs/PLACES_API_QUICK_START.md` - Quick reference for deployment
  - `test_places_api_integration.py` - Automated test suite (7 tests, 100% pass rate)
  - `GOOGLE_PLACES_API_INTEGRATION_SUMMARY.md` - Implementation summary

- **Files Modified**:
  - `concierge/utils/firestore_ai_helpers.py`
    - Added `search_nearby_places` function declaration for RAG queries
    - Integrated Places API as function calling tool with conditional enabling
    - Handler for Places API function calls with property location extraction
  - `concierge/utils/ai_helpers.py`
    - Added Places API function declaration for text chat
    - Integrated Places API call handling and response formatting
    - Enhanced function calling flow to support multiple tools
  - `concierge/static/js/guest_dashboard_utils.js`
    - Updated system prompts to prioritize Places API over Google Search
    - Added guidance on when to use Places API vs generic search
    - Enhanced response formatting instructions for location-based queries
  - `concierge/static/js/guest_dashboard_voice_call.js`
    - Updated voice call system prompts for Places API integration
    - Natural language presentation guidelines for voice responses
  - `concierge/app.py`
    - Fixed Flask-SocketIO compatibility with `allow_unsafe_werkzeug=True` for development

### API Requirements
- **Google Cloud APIs Enabled**:
  - Places API (New) - `places.googleapis.com`
  - Places API (Legacy) - `places-backend.googleapis.com`
  - Distance Matrix API - `distance-matrix-backend.googleapis.com`
  - Directions API - `directions-backend.googleapis.com`
  - Geocoding API - `geocoding-backend.googleapis.com`

- **Environment Variable**:
  - `GOOGLE_PLACES_API_KEY` - Required for Places API functionality
  - Gracefully falls back to Google Search if not configured

### Cost & Usage
- Google Maps Platform includes $200/month free credit
- Expected usage: 50-100 API calls/month per active property
- Estimated cost: $5-15/month per property (typically covered by free tier)

### Notes
- This release significantly improves the accuracy and quality of location-based recommendations
- Places API provides structured, real-time data versus generic web search results
- Backward compatible - existing deployments without API key continue using Google Search
- No database changes required - all changes in application layer

## Version 1.0.5 - 2025-09-06

### Changes
- **Travel guide strategy and prompt enhancements (PKB-104, PKB-107)**
  - Added strategic recommendation guidelines for travel advice: start with 1–2 top options, request clarifying trip context, and tailor suggestions throughout the conversation.
  - Updated shared system prompts to embed travel-guide capabilities and personalization guidance in `static/js/guest_dashboard_utils.js`.
  - Improves guest experience with more relevant, concise, and context-aware recommendations.

- **Time retrieval tool and backend wiring (PKB-104, PKB-107)**
  - Implemented the `get_current_time` capability with property-aware timezone handling.
  - Added backend support and integration in `utils/ai_helpers.py` and `utils/gemini_live_handler.py` to keep text chat path consistent.
  - Ensures timely, location-correct responses in both voice calls and text chat.

- **Gemini Live function-calling fix (WebSocket 1007 disconnects)**
  - Resolved critical issue where voice calls disconnected with code 1007 "Request contains an invalid argument" when the model requested tool calls.
  - Switched client WebSocket function responses to the correct Live API format using `tool_response.function_responses[]` with `id` mapping, instead of `client_content` with `role: "function"` parts.
  - Ensures proper matching of `FunctionResponse` to the model-issued `FunctionCall` via `id`, per official spec.

- **Time retrieval tool now reliable in voice and text**
  - `get_current_time` handled consistently across voice calls and text chat.
  - Voice path: client returns `tool_response` with the computed time payload.
  - Text path: server flow continues to work with proper function response parts.

- **Error handling and acknowledgements**
  - Standardized error tool responses (`tool_response.function_responses[].response: { error, message }`).
  - Added lightweight acknowledgement response for native `google_search` tool calls using the correct `tool_response` envelope.

- **Cleanup and logging reduction**
  - Removed excessive console logging and verbose debug output from function-calling paths to reduce noise in production.

### Technical Details
- **Files Changed**:
  - `concierge/static/js/guest_dashboard_voice_call.js`
    - Implemented `tool_response.function_responses` for:
      - `get_current_time` (includes `id` from the function call)
      - `process_query_with_rag`
      - `google_search` acknowledgement
    - Standardized error responses and removed debug spam.
  - `concierge/utils/gemini_live_handler.py`
    - Added support for sending proper function responses using `types.Part.from_function_response(...)` in server-managed flows.
  - `concierge/static/js/guest_dashboard_utils.js`
    - System prompt updates to include strategic travel guide capabilities and name personalization guidance.
  - `concierge/utils/ai_helpers.py`
    - Time retrieval utility improvements and property-context timezone handling.
  - `concierge/sockets/handlers.py`, `concierge/static/js/guest_dashboard_main.js`, `concierge/utils/dynamodb_client.py`
    - Supporting updates aligned with the new guided recommendations and time tool integration.

### Notes
- This release focuses on correctness of Live API tool-call interactions and stabilizes voice calls under function-calling scenarios.
- See internal diagnostics notes for background on the 1007 closures and the corrected schema.

## Version 1.0.4 - 2025-08-31

### Changes
- **Calendar Date Display Fix**
  - Fixed critical off-by-one error in host dashboard calendar view where reservations were showing incorrect date ranges
  - Implemented consistent date-only parsing with `parseDateOnly()` function to avoid timezone-related shifts
  - Changed calendar rendering to treat check-out dates as exclusive (reservation Aug 28-31 now shows bars Aug 28-30)
  - Updated `formatDateForCalendar()` to use local date formatting instead of UTC `toISOString()`
  - Enhanced tooltip and reservation detail calculations to reflect correct date ranges
  - Fixed List View vs Calendar View date consistency issues

- **Property Setup Modal Improvements**
  - Removed redundant property capacity question from Step 4 (Other Information) since it already exists in Step 2
  - Streamlined property setup flow to reduce user confusion and duplicate data entry
  - Enhanced navigation with concurrent operation prevention and step clamping for better reliability
  - Improved previous button functionality with immediate label and icon restoration
  - Removed redundant first aid kit location question to reduce setup complexity
  - Enhanced house rules handling with simplified logic and duplicate filtering

- **OCR and Scraper Enhancements**
  - Implemented OCR functionality for house rules and safety information extraction using Gemini AI
  - Added screenshot capture capabilities for house rules and safety modals using Selenium
  - Enhanced Airbnb scraper with comprehensive data extraction from both main and dedicated safety pages
  - Improved integration of direct listing URLs for more flexible data retrieval
  - Updated scraper to better handle house rules with clarity and consistency

- **Voice Call UX Enhancements**
  - Prevented duplicate "Listening..." messages in chat during voice calls
  - Enhanced message handling to skip consecutive status messages and reduce chat clutter
  - Improved chat message categorization with message type parameters

- **Feedback System Improvements**
  - Enhanced feedback submission to allow partial ratings (at least one of enjoyment or accuracy required)
  - Updated client-side logic to reflect new submission requirements and improve state management
  - Improved feedback storage in DynamoDB to handle optional fields more efficiently
  - Updated UI elements to clarify rating scales for enjoyment and accuracy
  - Enhanced feedback handling logic in WebSocket connections

- **Voice Call Button Reliability Fix**
  - Fixed critical issue where voice call button would grey out during poor connection, preventing users from ending calls
  - Modified `checkVoiceCallReadiness()` to keep button enabled as "End Call" during any non-idle call state
  - Ensures users can always hang up regardless of connection quality or missing IDs
  - Starting a call still requires good connection, but ending is always possible

- **Transcript Masking in Host Dashboard**
  - Added transcript preprocessing in host Conversations view to mask foreign characters for better readability
  - Implemented `preprocessTranscriptForHost()` function mirroring guest dashboard logic but applied only at render time
  - Preserves original transcript data in DynamoDB while improving host UI experience
  - Added backward compatibility for existing conversations without language codes
  - Applied masking to both voice transcripts and text chat messages

- **Language Code Persistence**
  - Enhanced voice session creation to store language configuration in DynamoDB
  - Persists `LanguageCode`, model, sanitization settings, and WebSocket URL with each voice session
  - Enables proper transcript masking in host dashboard based on actual session language
  - Defaults to `en-US` for missing language codes

- **Export Functionality**
  - Implemented conversation export feature for both voice and text conversations
  - Downloads timestamped .txt files containing conversation metadata and messages
  - Works for both voice transcripts and text chat conversations
  - No backend changes required - pure frontend implementation

- **Modal Layout Improvements**
  - Fixed conversation details modal to ensure Close and Export buttons are always accessible
  - Changed from `max-h-[90vh]` to `h-[95vh] flex flex-col overflow-hidden` layout
  - Header and footer are non-scrolling with `flex-shrink-0`
  - Content area uses `flex-1 overflow-y-auto` for proper scrolling

- **Voice Call Diagnostics Error Fix**
  - Fixed null reference error in voice call diagnostics finalization
  - Added stable reference capture to prevent async callback issues
  - Resolved `TypeError: Cannot read properties of null (reading 'dumpDiagnosticInfo')` warnings

### Technical Details
- **Files Changed**:
  - `concierge/static/js/host_dashboard.js` (calendar date handling, feedback improvements, transcript masking, export functionality)
  - `concierge/static/js/property-setup-modal.js` (removed redundant capacity question, navigation enhancements, house rules handling, previous button improvements)
  - `concierge/static/js/guest_dashboard_utils.js` (duplicate message prevention)
  - `concierge/static/js/guest_dashboard_voice_call.js` (message handling improvements, button state logic, diagnostics fix, language persistence)
  - `concierge/static/js/guest_dashboard_feedback.js` (feedback submission logic)
  - `concierge/api/routes.py` (feedback API improvements)
  - `concierge/sockets/handlers.py` (WebSocket feedback handling)
  - `concierge/utils/dynamodb_client.py` (feedback storage improvements)
  - `concierge/templates/guest_dashboard.html` (feedback UI updates)
  - `concierge/templates/host_dashboard.html` (modal layout improvements)
  - `concierge/utils/airbnb_integration.py` (direct listing URL integration)
  - `concierge/utils/airbnb_scraper.py` (OCR integration, comprehensive data extraction, house rules handling)
  - `concierge/scripts/extract_rules_via_gemini.py` (new OCR script for rules extraction)

### Notes
- This consolidated release combines all improvements from the previous 1.0.4 and 1.0.5 versions plus recent enhancements
- The calendar fix resolves a critical UX issue where reservations appeared to span incorrect dates
- Property setup flow is now more streamlined and less confusing for hosts with improved navigation
- OCR functionality significantly enhances data extraction capabilities for house rules and safety information
- Voice call experience is improved with cleaner chat messages and better reliability
- Feedback system is more flexible and user-friendly
- Transcript masking provides better readability while preserving data integrity
- Export functionality enables hosts to easily save conversation records

## Version 1.0.3 - 2025-08-13

### Changes
- Property Setup & Import UX improvements
  - Address field no longer prepopulates with neighborhood-only imported values; shows them as a hint until a real street address is entered
  - Inline legal note beside Address, iCal URL, and WiFi labels explaining why private info isn’t auto-imported
  - Prevent closing modals (Property Import, Property Setup, Property Management) by clicking outside
  - Added pre-setup “Keep Your Listing in Sync” gate modal for newly imported properties
  - Step 4 question wording fix: removed “vacuum” from cleaning supplies question to avoid duplication
  - Property card live updates when address is changed in Setup modal
- Property Import URL handling
  - Accepts “/h/{slug}” custom host links; normalizes by following redirects to listing URL
  - Accepts links without scheme (airbnb.com/…); auto-prefixes https
  - Added responsive “Supported links” tip with examples and where to find them
- Knowledge items
  - Completion now upgrades matching pending items to approved instead of creating duplicates; merges tags and standardizes content
- Guest Dashboard (mobile web)
  - Adjusted layout to use dynamic viewport units (svh/dvh with 100vh fallback) so the chat area is not obscured by Safari/Chrome browser UI
  - Removed overscroll past the chat input; entire page now fits inside the visible browsing area
  - Ensured inner flex containers use min-height: 0 to prevent accidental overflow and preserve smooth, contained scrolling of the chat history only

### Technical Details
- Mobile web viewport fixes in `templates/guest_dashboard.html`
  - `.main-layout` height now based on `calc(100dvh - X)`/`calc(100svh - X)` with `100vh` fallback across breakpoints
  - Introduced `.app-page-root` wrapper to clamp the page to the visible viewport and set `overflow-y: hidden`
  - Added `min-height: 0` to key flex containers to allow shrinking within the fixed viewport and avoid parent overflow
- Enhanced URL normalization in `AirbnbScraper._normalize_airbnb_url()` and validation to support `/h/` links and scheme-less inputs
- Setup completion endpoint converts pending knowledge items based on normalized content/title/body and type match
- Deployment script (`deploy_flask_app_aws.sh`) reliability fixes: absolute paths for key and app dir; resolved SSH wait hang

### Jira Tickets
- PKB-61, PKB-62 improvements extended; PKB-67, PKB-70 addressing Setup and modal UX; additional URL support and KB dedupe

---

## Version 1.0.2 - 2025-08-10

### Changes
- **PKB-61**: Property Setup improvements
  - Enforced street-address validation on Basic Information step; shows specific banner and inline guidance; blocks Next until corrected
  - Clearer UX around validation banners to avoid generic messages masking specific issues

- **PKB-62**: Knowledge Base management enhancements for hosts
  - Default sort shows Pending items first in Property Management → Knowledge Base tab
  - Improves visibility of items needing review/approval

- QR Code access shortcuts for guests
  - Enabled QR Code button in Configuration tab to download PNG of property’s magic link (`/api/properties/<id>/magic-link/qr`)

- **PKB-64**: Voice call UX improvements in Guest Dashboard
  - Added Mute button shown during active calls; clearly indicates muted/unmuted state and lets users pause their mic while continuing to hear Staycee
  - Renamed voice button to "Call Staycee" ("Call" on small screens); increased icon and text sizes; more rounded styling
  - Replaced mic icon with clearer speaker-with-waves icon

- **PKB-63**: Connection quality detection and safeguards for voice calls
  - Detects poor internet (Network Information API + latency probe); disables call button with "Poor Connection" status and suggests using text chat
  - Blocks starting a voice call when connection is insufficient; re-enables automatically once conditions improve
  - Adds in-chat guidance to switch to text during unstable connectivity

- **PKB-58**: Comprehensive voice call diagnostics and transcription system
  - Implemented consolidated voice call transcription storage with diagnostics system
  - Added robust fallback mechanism for voice call session creation failures
  - Enhanced session finalization logic with proper error handling
  - Fixed DynamoDB UpdateExpression path overlap errors
  - Optimized voice call diagnostics for DynamoDB free tier usage
  - Improved float to Decimal conversion in voice call session finalization
  - Enhanced ExpressionAttributeNames handling in voice call event logging
  - Added comprehensive client-side diagnostics for voice call quality monitoring
  - Implemented real-time audio quality assessment and network monitoring
  - Added graceful fallback when primary session creation fails

### Additional Changes (2025-08-10)
- **PKB-45**: Firestore database separation by environment
  - Production (GCP) uses `'(default)'` DB; staging (AWS) and local use `'development'` DB
  - Centralized Firestore client selection based on `DEPLOYMENT_ENV`
  - Deployment units set `DEPLOYMENT_ENV` appropriately via systemd

- Data migration and cleanup
  - Added `scripts/migrate_users_to_development.py` to move/copy users and related data (properties, reservations, knowledge sources/items) from `'(default)'` → `'development'`
  - Extended `scripts/check_orphaned_firestore_data.py` with `--delete-orphaned-reservations` for safe cleanup
  - Added `scripts/cleanup_orphaned_dynamodb.py` to remove DynamoDB items referencing properties missing from both Firestore DBs
  - Performed migration: 12 users (8 moved, 4 copied) with related data
  - Cleaned DynamoDB: removed 36 orphaned items and 408 test/diagnostic entries; curated remaining records

- Deployment hardening
  - `deploy_flask_app.sh`: preserve venv; ensure venv exists and reinstall requirements + gunicorn/eventlet; set `DEPLOYMENT_ENV` and credentials in unit
  - Fixed production service by recreating venv and reloading systemd

- Gemini configuration
  - Environment-based API key selection: paid key in production, free key in staging/dev
  - Rate limiter tuned per environment (higher limits for paid, conservative for free)
  - Pinned `google-genai==1.29.0` and ensured `google.genai` availability

- Local development
  - Recreated venv with Homebrew Python (OpenSSL backend) to eliminate LibreSSL warning

### Technical Details
- **Branch**: PKB-45-database-separation (plus PKB-58-call-enhancements)
- **Files Changed**: 4 files
- **Key Commits**:
  - 6493955: Fix voice call diagnostics fallback mechanism and enhance session finalization logic
  - 715c90f: Complete consolidated voice call transcription storage system
  - 8f6b320: Consolidate voice call transcription storage with diagnostics system
  - 7669727: Fix float to Decimal conversion in voice call session finalization
  - 5492e38: Fix ExpressionAttributeNames handling in voice call event logging
  - 6eac663: Fix DynamoDB UpdateExpression path overlap error
  - 44deb1f: Fix voice call session finalization issues
  - d95baf2: Optimize voice call diagnostics for DynamoDB free tier
  - 35ae7ef: Fix voice call diagnostics integration issues
  - f86f192: Implement comprehensive voice call diagnostics system

### Jira Tickets
- **PKB-61**: Basic Information validation and banner UX
- **PKB-62**: Knowledge Base pending-first sorting
- **PKB-64**: Voice call UX improvements (Mute button, button label/size/icon)
- **PKB-63**: Connection quality detection and call button gating
- **PKB-58**: Voice call diagnostics and transcription system enhancements

---

## Version 1.0.1 - 2025-08-04

### Changes
- **PKB-56**: Filter host-specific flash messages from guest-facing templates to prevent confusion
  - Added comprehensive filtering for knowledge management messages in guest authentication flows
  - Affected templates: magic_link_verify, account_type_selection, phone_login, and pin_entry
  - Prevents guests from seeing host-specific notifications about knowledge items, file uploads, etc.

- **PKB-57**: Improved guest authentication experience
  - Hide logout button for temporary users
  - Remove phone login link from magic link verification page
  - Streamlined guest verification flow

- **PKB-60**: Enhanced system prompts
  - Prohibits AI from promising to take action on guest issues
  - Prevents referring to guests by generic names when no actual name is provided
  - Improved guest context management

- **PKB-52**: Cleaned up Knowledge Base UI
  - Removed unused Bulk Approve button from Knowledge Base tab in Property Management modal
  - Streamlined the knowledge item management interface

- **PKB-53**: Enhanced property setup completion flow
  - Added warning for pending knowledge items after property setup
  - Improved property activation workflow with clear next steps
  - Added validation to prevent reservation sync for inactive properties
  - Enhanced error handling and user feedback during setup completion

- **PKB-51**: Enhanced property setup
  - Added sofabed setup question to property setup modal's Other Information step
  - Improved guest guidance during property onboarding

### Technical Details
- **Branch**: 8-ab-onboarding
- **Files Changed**: 15 files
- **Key Commits**:
  - 84c89ed: PKB-56/PKB-57 - Filter host-specific flash messages
  - 1ec868e: PKB-57 - Hide logout button for temporary users
  - f24e1b4: PKB-60 - System prompt enhancements
  - b3069b3: PKB-52 - Remove Bulk Approve button
  - 651dc8b: PKB-51 - Add sofabed setup question
  - 2dc64dd: PKB-53 - Enhanced property setup completion flow

### Jira Tickets
- **PKB-56**: Filter host-specific notifications from guest views
- **PKB-57**: UI improvements for temporary users and magic link verification
- **PKB-60**: System prompt enhancements for better guest interaction
- **PKB-52**: Remove unused Bulk Approve functionality from Knowledge Base
- **PKB-53**: Property setup completion flow and reservation sync improvements
- **PKB-51**: Property setup modal enhancements for guest guidance

---

## Version History
- **1.0.6 (2025-10-13)**: Google Places API integration for accurate location-based recommendations with distances, travel times, ratings, and real-time hours
- **1.0.5 (2025-09-06)**: Gemini Live function-calling fix (WebSocket 1007), reliable time retrieval in voice/text, standardized tool responses, and logging cleanup
- **1.0.4 (2025-08-18)**: Voice call button reliability, transcript masking, export functionality, modal layout improvements, and diagnostics error fixes
- **1.0.3 (2025-08-13)**: Property setup UX improvements, URL handling enhancements, knowledge base deduplication, and mobile web viewport fixes
- **1.0.2 (2025-08-10)**: PKB-64 + PKB-63 + PKB-58 - Voice call UX (Mute, button updates), connection quality detection/gating, and comprehensive diagnostics/transcription
- **1.0.1 (2025-08-04)**: PKB-51 + PKB-52 + PKB-53 + PKB-56 + PKB-57 + PKB-60 - Comprehensive guest experience improvements, property setup enhancements, and bug fixes