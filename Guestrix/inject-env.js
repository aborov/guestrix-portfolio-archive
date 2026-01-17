// Script to inject environment variables into all HTML files
// This is used during the Amplify build process

const fs = require('fs');
const path = require('path');
const glob = require('glob');

// Get environment variables to inject
// Removed GEMINI_API_KEY for security - it should never be exposed to client
const ENV_VARS = {
    // Add any other non-sensitive config here if needed
    // But NOT the API key
};

console.log('Injecting environment variables into the app...');
console.log('Environment variables to inject:', ENV_VARS);

// Find all HTML files in the dist directory
const htmlFiles = glob.sync('dist/*.html');
console.log('Found HTML files:', htmlFiles);

// Inject environment variables as a global object
const envScriptContent = `
<script>
  window.__ENV__ = ${JSON.stringify(ENV_VARS)};
</script>
`;

// Process each HTML file
htmlFiles.forEach(filePath => {
    console.log(`Processing ${filePath}...`);

    // Read the HTML file
    let content = fs.readFileSync(filePath, 'utf-8');

    // Check if environment variables are already injected
    if (content.includes('window.__ENV__')) {
        console.log(`Environment variables already injected in ${filePath}, skipping...`);
        return;
    }

    // Insert the script right before the closing head tag
    content = content.replace('</head>', `${envScriptContent}\n</head>`);

    // Write the updated content back
    fs.writeFileSync(filePath, content);
    console.log(`Environment variables injected into ${filePath}`);
});

console.log('Environment variables injection completed!');