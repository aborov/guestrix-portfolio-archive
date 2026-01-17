// Firebase configuration - now loaded securely

// Firebase auth instance (initialized after secure config loading)
let auth = null;
// Holds the confirmation result from signInWithPhoneNumber for robust verify flows (Safari fix)
let confirmationResultGlobal = null;

// Initialize Firebase securely and get auth instance
async function initializeAuth() {
    try {
        if (typeof window.initializeFirebaseSecurely === 'function') {
            console.log("Initializing Firebase securely for auth...");
            await window.initializeFirebaseSecurely();
            auth = firebase.auth();
            console.log("Firebase auth initialized securely");
            // Use session persistence to avoid Safari storage issues with persistent auth
            try {
              await auth.setPersistence(firebase.auth.Auth.Persistence.SESSION);
              console.log("Firebase auth persistence set to SESSION");
            } catch (pErr) {
              console.warn("Failed to set auth persistence (SESSION):", pErr);
            }
        } else {
            console.error("Secure Firebase initialization function not available");
            throw new Error("Firebase secure initialization not available");
        }
    } catch (error) {
        console.error("Failed to initialize Firebase auth securely:", error);
        throw error;
    }
}

// Track if we're in the process of verifying a token with the server
let tokenVerificationInProgress = false;
let sessionVerified = false;

// Store the verification ID
let verificationId = '';

// Store email for email link authentication
let emailForSignIn = '';

// Email link authentication functions
async function sendEmailLink(email) {
    try {
        if (!auth) {
            await initializeAuth();
        }

        const actionCodeSettings = {
            // URL you want to redirect back to. The domain (www.example.com) for this
            // URL must be in the authorized domains list in the Firebase Console.
            url: window.location.origin + '/auth/email-link-signin',
            // This must be true.
            handleCodeInApp: true,
        };

        await auth.sendSignInLinkToEmail(email, actionCodeSettings);

        // Save the email locally so you don't need to ask the user for it again
        // if they open the link on the same device.
        window.localStorage.setItem('emailForSignIn', email);
        emailForSignIn = email;

        console.log('Email link sent successfully to:', email);
        return { success: true };
    } catch (error) {
        console.error('Error sending email link:', error);
        return { success: false, error: error.message };
    }
}

async function signInWithEmailLink(email, emailLink) {
    try {
        if (!auth) {
            await initializeAuth();
        }

        // Confirm the link is a sign-in with email link.
        if (auth.isSignInWithEmailLink(emailLink)) {
            const result = await auth.signInWithEmailLink(email, emailLink);

            // Clear email from storage.
            window.localStorage.removeItem('emailForSignIn');

            console.log('Successfully signed in with email link:', result.user.email);
            return { success: true, user: result.user };
        } else {
            throw new Error('Invalid email link');
        }
    } catch (error) {
        console.error('Error signing in with email link:', error);
        return { success: false, error: error.message };
    }
}

// Function to check if current URL is an email link
function isEmailLink() {
    if (!auth) return false;
    return auth.isSignInWithEmailLink(window.location.href);
}

// Function to get stored email for sign-in
function getStoredEmailForSignIn() {
    return window.localStorage.getItem('emailForSignIn') || emailForSignIn;
}

// Function to initialize phone authentication
async function initializePhoneAuth() {
  console.log('Initializing phone authentication...');
  try {
    // Ensure Firebase is initialized securely first
    if (!auth) {
      await initializeAuth();
    }
    // Initialize reCAPTCHA
    window.recaptchaVerifier = new firebase.auth.RecaptchaVerifier('recaptcha-container', {
      'size': 'normal',
      'callback': (response) => {
        // reCAPTCHA solved, call global callback if available, otherwise enable button directly
        console.log('reCAPTCHA verified successfully');
        if (typeof window.recaptchaCallback === 'function') {
          window.recaptchaCallback(response);
        } else {
          document.getElementById('send-code-button').disabled = false;
        }
      },
      'expired-callback': () => {
        // Response expired, call global callback if available, otherwise disable button directly
        console.log('reCAPTCHA expired');
        if (typeof window.recaptchaExpiredCallback === 'function') {
          window.recaptchaExpiredCallback();
        } else {
          document.getElementById('send-code-button').disabled = true;
        }
      }
    });
    
    console.log('Rendering reCAPTCHA...');
    window.recaptchaVerifier.render().then(function(widgetId) {
      window.recaptchaWidgetId = widgetId;
      console.log('reCAPTCHA rendered with widget ID:', widgetId);
    });
    
    // Add event listeners
    document.getElementById('send-code-button').addEventListener('click', sendVerificationCode);
    document.getElementById('verify-code-button').addEventListener('click', verifyCode);
    document.getElementById('back-to-phone').addEventListener('click', () => {
      showStep('phone-step');
    });
    
    console.log('Phone authentication initialized successfully');
  } catch (error) {
    console.error('Error initializing phone authentication:', error);
    showError('Error initializing phone authentication: ' + error.message);
  }
}

// Function to send verification code
function sendVerificationCode() {
  console.log('Sending verification code...');
  const phoneNumber = getCompletePhoneNumber('phone-number');
  
  if (!phoneNumber) {
    showError('Please enter a valid phone number');
    console.error('Phone number is empty');
    return;
  }
  
  console.log('Phone number:', phoneNumber);
  
  try {
    const appVerifier = window.recaptchaVerifier;
    console.log('Using reCAPTCHA verifier:', appVerifier);
    
    // Show loading state
    document.getElementById('send-code-button').disabled = true;
    document.getElementById('send-code-button').textContent = 'Sending...';
    
    auth.signInWithPhoneNumber(phoneNumber, appVerifier)
      .then((confirmationResult) => {
        // SMS sent. Save the verification ID
        console.log('SMS sent successfully, verification ID received');
        verificationId = confirmationResult.verificationId;
        // Save confirmationResult for confirm() path (more robust on Safari)
        confirmationResultGlobal = confirmationResult;
        showStep('code-step');
        hideError();
        document.getElementById('send-code-button').textContent = 'Send Verification Code';
      })
      .catch((error) => {
        showError('Error sending verification code: ' + error.message);
        console.error('Error sending verification code:', error);
        document.getElementById('send-code-button').disabled = false;
        document.getElementById('send-code-button').textContent = 'Send Verification Code';
        
        // Reset reCAPTCHA
        if (window.recaptchaWidgetId) {
          console.log('Resetting reCAPTCHA widget:', window.recaptchaWidgetId);
          grecaptcha.reset(window.recaptchaWidgetId);
        } else {
          console.log('No reCAPTCHA widget ID found, recreating verifier');
          // Re-create the reCAPTCHA verifier
          window.recaptchaVerifier.clear();
          initializePhoneAuth();
        }
      });
  } catch (error) {
    showError('Error in verification process: ' + error.message);
    console.error('Error in verification process:', error);
    document.getElementById('send-code-button').disabled = false;
    document.getElementById('send-code-button').textContent = 'Send Verification Code';
  }
}

// Function to verify code
function verifyCode() {
  console.log('Verifying code...');
  const code = document.getElementById('verification-code').value;
  
  if (!code) {
    showError('Please enter the verification code');
    console.error('Verification code is empty');
    return;
  }
  
  console.log('Verification code entered:', code);
  console.log('Using verification ID:', verificationId ? 'Available' : 'Not available');
  
  if (!verificationId) {
    showError('Verification session expired. Please try again.');
    console.error('No verification ID available');
    showStep('phone-step');
    return;
  }
  
  try {
    // Show loading state
    document.getElementById('verify-code-button').disabled = true;
    document.getElementById('verify-code-button').textContent = 'Verifying...';
    
    const credential = firebase.auth.PhoneAuthProvider.credential(verificationId, code);
    console.log('Created phone auth credential');
    
    // Mark that we're starting the verification process
    tokenVerificationInProgress = true;
    
    // Prefer confirmationResult.confirm on Safari and generally when available; fallback to signInWithCredential
    const signInPromise = confirmationResultGlobal
      ? confirmationResultGlobal.confirm(code)
      : auth.signInWithCredential(credential);
    
    // Add a timeout guard to handle Safari hanging on sign-in
    const timeoutMs = 20000; // 20s
    const timeoutPromise = new Promise((_, reject) => setTimeout(() => reject(new Error('Verification timed out. Please try again.')), timeoutMs));
    
    Promise.race([signInPromise, timeoutPromise])
      .then((userCredential) => {
        // User signed in successfully
        console.log('User signed in successfully:', userCredential.user.uid);
        showStep('success-step');
        hideError();
        
        // Get the ID token
        console.log('Getting ID token...');
        return userCredential.user.getIdToken(true);
      })
      .then((idToken) => {
        // Send the token to the backend for verification
        console.log('ID token received, sending to backend for verification');
        console.log('Token (first 10 chars):', idToken.substring(0, 10) + '...');
        
        return fetch('/auth/verify-token', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ idToken: idToken }),
          credentials: 'same-origin' // Include cookies in the request
        });
      })
      .then(response => {
        console.log('Response status:', response.status);
        
        // Handle different response statuses
        if (response.status === 202) {
          // Status 202: New user needs account type selection
          console.log('New user detected (status 202), parsing JSON for redirect');
          return response.json().then(data => {
            // Return the data with a special flag to indicate this is a redirect case
            return { ...data, isRedirect: true };
          });
        } else if (response.status === 409) {
          // Status 409: Conflict (duplicate account)
          return response.json().then(data => {
            throw { status: response.status, data: data };
          }).catch(jsonError => {
            console.error('Failed to parse 409 JSON response:', jsonError);
            throw new Error('Duplicate account detected but could not parse response: ' + jsonError.message);
          });
        } else if (!response.ok) {
          // For other error statuses, attempt to get response text for more context on failure
          return response.text().then(text => {
              console.error('Server returned non-OK status. Response text:', text);
              throw new Error('Server responded with status: ' + response.status);
          }).catch(() => {
               // If getting text fails, throw generic error
               throw new Error('Server responded with status: ' + response.status);
          });
        }
        
        return response.json();
      })
      .then(data => {
        console.log('Server response:', data);
        
        // Handle redirect case (status 202 - new user needs account type selection)
        if (data && data.isRedirect && data.redirect) {
          console.log('New user redirect detected, redirecting to:', data.redirect);
          if (data.message) {
            console.log('Message from server:', data.message);
          }
          // Redirect immediately for new user flow
          tokenVerificationInProgress = false;
          window.location.href = data.redirect;
          return;
        }
        
        if (data.success) {
          console.log('Token verified successfully, redirecting to dashboard');
          // Mark session as verified
          sessionVerified = true;
          // Redirect to dashboard after a short delay
          setTimeout(() => {
            tokenVerificationInProgress = false; // Reset flag before redirect
            window.location.href = '/dashboard';
          }, 1000);
        } else {
          throw new Error(data.error || 'Failed to verify token with server');
        }
      })
      .catch((error) => {
        tokenVerificationInProgress = false; // Reset flag on error
        document.getElementById('verify-code-button').disabled = false;
        document.getElementById('verify-code-button').textContent = 'Verify Code';
        
        // Handle the special case of 409 Conflict (duplicate account)
        if (error.status === 409 && error.data) {
          console.log('[verifyCode] Duplicate account detected, handling redirect:', error.data);
          console.log('[verifyCode] Error data redirect:', error.data.redirect);
          console.log('[verifyCode] Error data error:', error.data.error);
          if (error.data.redirect) {
            console.log('[verifyCode] About to show error and redirect to:', error.data.redirect);
            showError(error.data.error + ' Redirecting to login...');
            console.log('[verifyCode] Error message displayed, setting timeout for redirect');
            setTimeout(() => {
              console.log('[verifyCode] Executing redirect to:', error.data.redirect);
              window.location.href = error.data.redirect;
            }, 2000);
            return;
          }
        }
        
        showError('Error verifying code: ' + error.message);
        console.error('Error verifying code:', error);
      });
  } catch (error) {
    tokenVerificationInProgress = false; // Reset flag on error
    document.getElementById('verify-code-button').disabled = false;
    document.getElementById('verify-code-button').textContent = 'Verify Code';
    showError('Error in verification process: ' + error.message);
    console.error('Error in verification process:', error);
  }
}

// Function to check authentication state
async function checkAuthState() {
  console.log('Checking authentication state...');
  
  // Ensure Firebase is initialized securely first
  if (!auth) {
    try {
      await initializeAuth();
    } catch (error) {
      console.error('Failed to initialize Firebase for auth state check:', error);
      return;
    }
  }
  
  // If we're in the middle of token verification, don't trigger redirects
  if (tokenVerificationInProgress) {
    console.log('Token verification in progress, skipping auth state check');
    return;
  }
  
  auth.onAuthStateChanged(user => {
    console.log('Auth state changed, user:', user ? `signed in (${user.uid})` : 'signed out');
    const dashboardLink = document.getElementById('dashboard-link');
    const profileLink = document.getElementById('profile-link');
    const logoutButton = document.getElementById('logout-button');

    // Check if we're on a phone login flow page
    const isPhoneLoginFlow = window.location.pathname.includes('/auth/phone-login') ||
                            window.location.pathname.includes('/auth/signup-choice') ||
                            window.location.pathname.includes('/auth/complete-phone-auth') ||
                            window.location.pathname.includes('/auth/create-standalone-guest') ||
                            window.location.pathname.includes('/auth/process-magic-link') ||
                            document.querySelector('.login-card h2')?.textContent?.includes('Phone');

    if (user) {
      // User is signed in with Firebase.
      console.log('User is signed in with Firebase. Updating UI.');
      if (dashboardLink) dashboardLink.style.display = 'block';
      if (profileLink) profileLink.style.display = 'block';
      if (logoutButton) logoutButton.style.display = 'block';
      
      // Don't interfere with phone login flow, magic link processing, or email link signin
      const isEmailLinkSignin = window.location.pathname.includes('/auth/email-link-signin');
      
      if (isPhoneLoginFlow || isEmailLinkSignin) {
        console.log('On special auth flow page, skipping auth state verification to avoid interference');
        return;
      }
      
      // Check if we need to verify the token with our backend
      if (!sessionVerified && !tokenVerificationInProgress) {
        // Only do this if we're not already in the process and session isn't verified
        const shouldVerifyToken = window.location.pathname === '/' || 
                                 window.location.pathname === '/login' ||
                                 window.location.pathname === '/auth/login';
        
        if (shouldVerifyToken) {
          console.log('User signed in with Firebase but session not verified. Verifying token...');
          verifyTokenWithBackend(user);
        }
      }
      
      // For login pages, check if session is verified
      const authContainer = document.getElementById('auth-container');
      const isLoginPage = window.location.pathname === '/' || 
                         window.location.pathname === '/login' ||
                         window.location.pathname === '/auth/login' ||
                         window.location.pathname.endsWith('/') ||
                         window.location.pathname === '';
      
      if (isLoginPage && !sessionVerified) {
        // User is signed in with Firebase but session not verified with backend
        // Show a message with option to sign out and use different account
        console.log('User signed in with Firebase but session not verified. Showing sign out option.');
        
        if (authContainer) {
          authContainer.style.display = 'block';
          // Add a notice with sign out option
          authContainer.innerHTML = `
            <div class="auth-step" id="already-signed-notice" style="text-align: center; padding: 20px;">
              <h3>Already Signed In</h3>
              <p>You're signed in with Firebase but need to verify your session.</p>
              <p>If you want to sign in with a different account:</p>
              <button id="manual-signout-btn" class="btn" style="background: #dc3545; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; margin: 10px;">
                Sign Out & Use Different Account
              </button>
              <p><small>Or wait for automatic verification to complete...</small></p>
            </div>
          `;
          
          // Add click handler for sign out button
          const signOutBtn = document.getElementById('manual-signout-btn');
          if (signOutBtn) {
            signOutBtn.addEventListener('click', function() {
              console.log('Manual sign out requested...');
              
              // Clear session flags
              sessionVerified = false;
              tokenVerificationInProgress = false;
              
              // Sign out from Firebase
              auth.signOut().then(() => {
                console.log('Signed out successfully, page will reload');
                window.location.reload();
              }).catch((error) => {
                console.error('Error signing out:', error);
                // Force reload anyway
                window.location.reload();
              });
            });
          }
        }
      } else {
        // Hide auth form for other cases
        if (authContainer) authContainer.style.display = 'none';
      }
    } else {
      // User is signed out of Firebase.
      console.log('User is signed out of Firebase. Updating UI.');
      sessionVerified = false; // Reset session verification flag
      
      if (dashboardLink) dashboardLink.style.display = 'none';
      if (profileLink) profileLink.style.display = 'none';
      if (logoutButton) logoutButton.style.display = 'none';

      // Don't interfere with phone login flow
      if (isPhoneLoginFlow) {
        console.log('On phone login flow page, skipping auth state UI changes to avoid interference');
        return;
      }

      // Only show login form and initialize if on the root page or login page
      console.log('Current pathname:', window.location.pathname);
      const isLoginPage = window.location.pathname === '/' || 
                         window.location.pathname === '/login' ||
                         window.location.pathname === '/auth/login' ||
                         window.location.pathname.endsWith('/') ||
                         window.location.pathname === '';
      
      if (isLoginPage) {
        console.log('On login page, showing login form');
        const authContainer = document.getElementById('auth-container');
        if (authContainer) authContainer.style.display = 'block'; 
        showStep('phone-step'); // Show the phone input form
        initializePhoneAuth(); // Set up recaptcha and listeners
      } else {
        // If signed out and not on root, do NOT redirect to '/'. Backend handles auth.
        console.warn('User signed out (client-side), but backend session may be valid. No redirect performed to avoid loop.');
        console.log('Current pathname is not recognized as login page:', window.location.pathname);
        // Optionally, display a UI warning or prompt here.
      }
    }
  });
}

// Function to verify token with backend
async function verifyTokenWithBackend(user) {
  tokenVerificationInProgress = true;
  console.log('Getting ID token to verify with backend...');

  // Ensure Firebase is initialized
  if (!auth) {
    try {
      await initializeAuth();
    } catch (error) {
      console.error('Failed to initialize Firebase for token verification:', error);
      tokenVerificationInProgress = false;
      return;
    }
  }

  user.getIdToken(true)
    .then(idToken => {
      console.log('ID token received, sending to backend (/auth/verify-token)');
      // console.log('Token (first 10 chars):', idToken.substring(0, 10) + '...'); // Keep token private unless debugging

      return fetch('/auth/verify-token', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ idToken: idToken }),
        credentials: 'same-origin' // Include cookies in the request
      });
    })
    .then(response => {
      console.log('[verifyTokenWithBackend] Received response from /auth/verify-token');
      console.log('[verifyTokenWithBackend] Response Status:', response.status);
      console.log('[verifyTokenWithBackend] Response OK?:', response.ok);

      // Handle different response statuses
      if (response.status === 202) {
        // Status 202: New user needs account type selection
        console.log('[verifyTokenWithBackend] New user detected (status 202), parsing JSON for redirect');
        return response.json().then(data => {
          // Return the data with a special flag to indicate this is a redirect case
          return { ...data, isRedirect: true };
        });
      } else if (response.status === 409) {
        // Status 409: Conflict (duplicate account)
        return response.json().then(data => {
          throw { status: response.status, data: data };
        }).catch(jsonError => {
          console.error('Failed to parse 409 JSON response:', jsonError);
          throw new Error('Duplicate account detected but could not parse response: ' + jsonError.message);
        });
      } else if (!response.ok) {
        // For other error statuses, attempt to get response text for more context on failure
        return response.text().then(text => {
            console.error('[verifyTokenWithBackend] Server returned non-OK status. Response text:', text);
            throw new Error('Server verification failed with status: ' + response.status);
        }).catch(() => {
             // If getting text fails, throw generic error
             throw new Error('Server verification failed with status: ' + response.status);
        });
      }
      
      console.log('[verifyTokenWithBackend] Attempting to parse response JSON...');
      return response.json(); // Attempt to parse JSON
    })
    .then(data => {
      console.log('[verifyTokenWithBackend] Successfully parsed JSON response:', data);
      tokenVerificationInProgress = false;

      // Handle redirect case (status 202 - new user needs account type selection)
      if (data && data.isRedirect && data.redirect) {
        console.log('[verifyTokenWithBackend] New user redirect detected, redirecting to:', data.redirect);
        if (data.message) {
          console.log('[verifyTokenWithBackend] Message from server:', data.message);
        }
        // Redirect immediately for new user flow
        window.location.href = data.redirect;
        return;
      }

      if (data && data.success) { // Check if data exists and has success property
        console.log('[verifyTokenWithBackend] Token verified successfully with server. data.success:', data.success);
        sessionVerified = true;

        // Now that the session is verified, redirect from authentication pages
        const isAuthPage = window.location.pathname === '/' || 
                          window.location.pathname === '/login' ||
                          window.location.pathname === '/auth/login' ||
                          window.location.pathname.includes('/auth/phone-login') ||
                          window.location.pathname.includes('/auth/email-link-signin') ||
                          window.location.pathname.endsWith('/') ||
                          window.location.pathname === '';
        
        if (isAuthPage) {
          console.log('[verifyTokenWithBackend] Session verified, redirecting from auth page to /dashboard');
          const redirectUrl = data.redirect_url || '/dashboard';
          window.location.href = redirectUrl;
        } else {
          console.log('[verifyTokenWithBackend] Session verified, already on page:', window.location.pathname);
          // Might need to update UI elements if already on dashboard but session wasn't verified before
        }
      } else {
        console.error('[verifyTokenWithBackend] Server response JSON did not indicate success. Data:', data);
        
        // Check if this is a duplicate account error with a redirect
        if (data && data.redirect) {
          console.log('[verifyTokenWithBackend] Duplicate account detected, redirecting to:', data.redirect);
          showError(data.error + ' Redirecting to login...');
          setTimeout(() => {
            window.location.href = data.redirect;
          }, 2000);
          return;
        }
        
        // Use error message from server if available, otherwise generic message
        const errorMessage = data && data.error ? data.error : 'Failed to verify token with server (invalid response structure)'; 
        throw new Error(errorMessage);
      }
    })
    .catch(error => {
      console.error('[verifyTokenWithBackend] Caught error during backend token verification process:', error);
      tokenVerificationInProgress = false;
      
      // Handle the special case of 409 Conflict (duplicate account)
      if (error.status === 409 && error.data) {
        console.log('[verifyTokenWithBackend] Duplicate account detected, handling redirect:', error.data);
        console.log('[verifyTokenWithBackend] Error data redirect:', error.data.redirect);
        console.log('[verifyTokenWithBackend] Error data error:', error.data.error);
        if (error.data.redirect) {
          console.log('[verifyTokenWithBackend] About to show error and redirect to:', error.data.redirect);
          showError(error.data.error + ' Redirecting to login...');
          console.log('[verifyTokenWithBackend] Error message displayed, setting timeout for redirect');
          setTimeout(() => {
            console.log('[verifyTokenWithBackend] Executing redirect to:', error.data.redirect);
            window.location.href = error.data.redirect;
          }, 2000);
          return;
        }
      }
      
      // Display the specific error message caught
      showError('Error verifying authentication: ' + (error.message || 'Unknown error'));
    });
}

// Function to logout
async function logout() {
  console.log("Attempting logout...");
  
  // Ensure Firebase is initialized
  if (!auth) {
    try {
      await initializeAuth();
    } catch (error) {
      console.error('Failed to initialize Firebase for logout:', error);
      // Continue with server-side logout anyway
    }
  }
  
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
    // Then sign out from Firebase
    return auth.signOut();
  })
  .then(() => {
    console.log('User signed out successfully from both server and Firebase');
    sessionVerified = false; // Reset our session verification flag
    window.location.href = '/'; // Redirect to home/login page
  })
  .catch((error) => {
    console.error('Error during logout process:', error);
    // Try to redirect anyway
    window.location.href = '/';
  });
}

// Helper functions for UI
function showStep(stepId) {
  // Hide all steps
  const steps = document.getElementsByClassName('auth-step');
  for (let i = 0; i < steps.length; i++) {
    steps[i].style.display = 'none';
  }

  // Show the requested step
  document.getElementById(stepId).style.display = 'block';

  // Hide auth form section (legal consent and buttons) during verification steps
  const authFormSection = document.getElementById('auth-form-section');
  if (authFormSection) {
    if (stepId === 'code-step' || stepId === 'success-step') {
      authFormSection.style.display = 'none';
    } else {
      authFormSection.style.display = 'block';
    }
  }
}

function showError(message) {
  console.log('[showError] Attempting to show error message:', message);
  const errorElement = document.getElementById('error-message');
  console.log('[showError] Error element found:', !!errorElement);
  if (errorElement) {
    errorElement.textContent = message;
    errorElement.style.display = 'block';
    console.log('[showError] Error message set and displayed');
  } else {
    console.error('[showError] Error element not found');
  }
}

function hideError() {
  document.getElementById('error-message').style.display = 'none';
}

// Check auth state on every page
document.addEventListener('DOMContentLoaded', async () => {
  try {
    await checkAuthState();
  } catch (error) {
    console.error('Error during authentication state check:', error);
  }
});
