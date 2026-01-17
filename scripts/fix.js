const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, '../concierge/static/js/guest_dashboard_main.js');

// Read the file
let content = fs.readFileSync(filePath, 'utf8');

// Create a backup
fs.writeFileSync(`${filePath}.backup3`, content);

// Get the file content before the problematic section (up to line 919)
const fileLines = content.split('\n');
const headContent = fileLines.slice(0, 919).join('\n');

// Add the fixed comment and render function
const fixedContent = 
`${headContent}

// Helper functions fetchPropertyDetails and fetchPropertyKnowledgeItems are imported from guest_dashboard_utils.js

// Render Reservations
function renderReservations(reservations, container) {
    container.innerHTML = ''; // Clear previous content
    const now = new Date();

    // If no reservations, show a message and exit early`;

// Get the rest of the file (from line 993 onward)
const tailIndex = fileLines.findIndex(line => line.includes("// If no reservations, show a message and exit early"));
const tailContent = fileLines.slice(tailIndex + 1).join('\n');

// Combine the fixed content with the tail content
const finalContent = `${fixedContent}
${tailContent}`;

// Write the updated content back to the file
fs.writeFileSync(filePath, finalContent);

console.log('File updated successfully!'); 