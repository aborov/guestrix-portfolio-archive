/**
 * Resource Loader - Handles loading external resources with fallbacks
 */

// Function to load CSS with fallback
function loadCssWithFallback(url, fallbackUrl) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = url;
    
    // Add error handler to try fallback
    link.onerror = function() {
        console.warn(`Failed to load CSS from ${url}, trying fallback...`);
        if (fallbackUrl) {
            const fallbackLink = document.createElement('link');
            fallbackLink.rel = 'stylesheet';
            fallbackLink.href = fallbackUrl;
            document.head.appendChild(fallbackLink);
        } else {
            console.error(`Failed to load CSS from ${url} and no fallback provided.`);
        }
    };
    
    document.head.appendChild(link);
}

// Function to load JavaScript with fallback
function loadScriptWithFallback(url, fallbackUrl, callback) {
    const script = document.createElement('script');
    script.src = url;
    script.async = true;
    
    // Add error handler to try fallback
    script.onerror = function() {
        console.warn(`Failed to load script from ${url}, trying fallback...`);
        if (fallbackUrl) {
            const fallbackScript = document.createElement('script');
            fallbackScript.src = fallbackUrl;
            fallbackScript.async = true;
            fallbackScript.onload = callback;
            fallbackScript.onerror = function() {
                console.error(`Failed to load script from fallback ${fallbackUrl}`);
            };
            document.body.appendChild(fallbackScript);
        } else {
            console.error(`Failed to load script from ${url} and no fallback provided.`);
        }
    };
    
    script.onload = callback;
    document.body.appendChild(script);
}

// Load essential resources with fallbacks
document.addEventListener('DOMContentLoaded', function() {
    // Bootstrap CSS
    loadCssWithFallback(
        'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
        '/static/css/bootstrap.min.css'
    );
    
    // Bootstrap Icons
    loadCssWithFallback(
        'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css',
        '/static/css/bootstrap-icons.css'
    );
    
    // Socket.IO
    loadScriptWithFallback(
        'https://cdn.socket.io/4.7.5/socket.io.min.js',
        '/static/js/socket.io.min.js'
    );
    
    // Firebase App - only load if not already loaded
    if (typeof firebase === 'undefined') {
        console.log("Firebase not detected, loading from CDN...");
        loadScriptWithFallback(
            'https://www.gstatic.com/firebasejs/9.22.0/firebase-app-compat.js',
            '/static/js/firebase-app-compat.js',
            function() {
                // Load Firebase Auth after App is loaded
                loadScriptWithFallback(
                    'https://www.gstatic.com/firebasejs/9.22.0/firebase-auth-compat.js',
                    '/static/js/firebase-auth-compat.js'
                );
            }
        );
    } else {
        console.log("Firebase already loaded, skipping load from resource-loader");
    }
    
    // reCAPTCHA
    loadScriptWithFallback(
        'https://www.google.com/recaptcha/api.js',
        '/static/js/recaptcha-api.js'
    );
});
