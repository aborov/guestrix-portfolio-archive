// Test script for name update functionality
// Run this in the browser console on the guest dashboard

console.log('🧪 Starting comprehensive name update test...');

// Test 1: Check current state
console.log('=== Test 1: Current State ===');
console.log('window.GUEST_NAME:', window.GUEST_NAME);
console.log('window.dashboardState?.guestName:', window.dashboardState?.guestName);
console.log('window.isTemporaryUser:', window.isTemporaryUser);
console.log('window.tempIdToken:', window.tempIdToken ? 'Present' : 'Missing');

// Test 2: Check cookie
console.log('=== Test 2: Cookie Check ===');
function getGuestNameFromCookie() {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'guest_name' && value) {
            return decodeURIComponent(value);
        }
    }
    return null;
}
const cookieName = getGuestNameFromCookie();
console.log('Cookie guest_name:', cookieName);

// Test 3: Simulate name update
console.log('=== Test 3: Simulate Name Update ===');
const testName = 'TestUser_' + Date.now();
console.log('Setting test name:', testName);

// Update window variables
window.GUEST_NAME = testName;
if (window.dashboardState) {
    window.dashboardState.guestName = testName;
    window.dashboardState.guestNameSource = 'test';
}

// Store in cookie
document.cookie = `guest_name=${testName}; path=/; max-age=86400`;
console.log('Stored name in cookie');

// Test 4: Simulate API call
console.log('=== Test 4: Simulate API Call ===');
if (window.isTemporaryUser) {
    console.log('Making API call to update database...');
    fetch('/api/profile', {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            displayName: testName
        })
    })
    .then(response => response.json())
    .then(data => {
        console.log('API response:', data);
        if (data.success) {
            console.log('✅ API call successful');
        } else {
            console.warn('❌ API call failed:', data.error);
        }
    })
    .catch(error => {
        console.error('❌ API call error:', error);
    });
} else {
    console.log('Not a temporary user, skipping API call');
}

// Test 5: Check persistence after simulated reload
console.log('=== Test 5: Simulate Page Reload ===');
console.log('Simulating page reload...');
console.log('After "reload", the name should be restored from:');
console.log('1. Database (if API call succeeded)');
console.log('2. Cookie (if database failed)');
console.log('3. Template data (fallback)');

// Test 6: Check system prompt
console.log('=== Test 6: System Prompt Check ===');
if (typeof createSharedSystemPrompt === 'function') {
    const systemPrompt = createSharedSystemPrompt();
    console.log('System prompt includes guest name:', systemPrompt.includes(testName));
    console.log('System prompt length:', systemPrompt.length);
} else {
    console.log('createSharedSystemPrompt function not available');
}

console.log('🧪 Test complete! Check the results above.'); 