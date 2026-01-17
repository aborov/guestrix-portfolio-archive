const config = {
    api: {
        endpoint: 'https://fx6ti5wvm9.execute-api.us-east-2.amazonaws.com/dev'
    }
    // Removed gemini section - API key should never be exposed to client
};

// Removed all window.GEMINI_API_KEY assignments for security
// The API key will be fetched from the server when needed

export default config; 