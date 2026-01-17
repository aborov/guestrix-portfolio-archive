# Authentication Troubleshooting Guide

## Common Issues and Solutions

### 1. Firebase Rate Limiting Error (`auth/too-many-requests`)

**Problem**: You see the error "We have blocked all requests from this device due to unusual activity. Try again later."

**Cause**: Firebase has temporarily blocked your device/IP due to too many SMS verification requests in a short period.

**Solutions**:
1. **Wait it out**: The block is temporary and will lift automatically after 15-30 minutes
2. **Use a different device**: Try logging in from a different device or network
3. **Use a different phone number**: If you have access to another phone number, try that
4. **Clear browser data**: Clear cookies and localStorage for the site
5. **Use incognito/private mode**: This can sometimes bypass the rate limit

### 2. reCAPTCHA Issues

**Problem**: reCAPTCHA not loading or failing verification

**Solutions**:
1. **Refresh the page**: Try refreshing and starting over
2. **Check ad blockers**: Disable ad blockers or privacy extensions
3. **Check network**: Ensure you have a stable internet connection
4. **Try different browser**: Some browsers have stricter security settings

### 3. Invalid Phone Number Format

**Problem**: "Invalid phone number" error

**Solutions**:
1. **Include country code**: Always start with + followed by country code (e.g., +1 for US)
2. **Remove spaces and dashes**: Use only numbers after the country code
3. **Example formats**:
   - US: +1234567890
   - UK: +441234567890
   - International: +[country code][number]

### 4. Verification Code Issues

**Problem**: "Invalid verification code" or "Code expired"

**Solutions**:
1. **Check the code carefully**: Ensure you're entering all 6 digits correctly
2. **Try again quickly**: Codes expire after a few minutes
3. **Request new code**: If expired, go back and request a new verification code
4. **Check SMS delivery**: Sometimes SMS can be delayed

## For Developers

### Rate Limiting Best Practices

1. **Implement exponential backoff**: Don't retry immediately after failures
2. **Show clear error messages**: Let users know how long to wait
3. **Provide alternatives**: Offer email authentication or other methods
4. **Monitor usage**: Track authentication attempts to identify issues early

### Firebase Configuration

Ensure your Firebase project has:
- SMS authentication enabled
- Proper quotas configured
- reCAPTCHA properly set up
- Valid domain authorization

### Environment Considerations

- **Development**: Use Firebase Auth Emulator to avoid rate limits during development
- **Production**: Configure proper rate limiting and monitoring
- **Testing**: Use test phone numbers provided by Firebase for automated testing

## Getting Help

If you continue to experience issues:
1. Check the browser console for detailed error messages
2. Verify your internet connection
3. Try a different device or network
4. Contact support if problems persist

## Technical Details

The authentication system uses:
- Firebase Authentication for phone verification
- reCAPTCHA for bot protection
- Session management for user state
- Rate limiting to prevent abuse

Rate limits are typically:
- 5 SMS per phone number per hour
- 100 SMS per day per project
- Additional limits based on device/IP 