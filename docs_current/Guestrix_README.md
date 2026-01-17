# Guestrix

A platform for short-term rental property management.

## Environment Variables Setup

### GitHub Secrets Setup
1. In your GitHub repository, go to Settings > Secrets and variables > Actions
2. Add a new repository secret named `GEMINI_API_KEY` with your Google Gemini API key as the value

### AWS Amplify Environment Setup
1. Open AWS Amplify console
2. Select your Guestrix app
3. Go to Environment variables
4. Add the following environment variables:
   - `GEMINI_API_KEY`: Use GitHub secret by setting value to `${GEMINI_API_KEY}`

### Local Development
For local development, there are several ways to provide the API key:

#### Option 1: Environment File (with Node.js server)
Create a `.env` file in the root directory with:
```
GEMINI_API_KEY=your_gemini_api_key_here
```

#### Option 2: Browser localStorage (static file server)
When using a simple static file server (like Python's http.server), the application 
will prompt you to enter your Gemini API key and store it in the browser's localStorage
for future use. This makes testing easier without running the full Node.js server.

⚠️ NEVER commit your actual API keys to the repository!
