// Note: This file is no longer used for API endpoints as they're managed by Amplify
// Keeping this file for static file serving if needed

require('dotenv').config();
const express = require('express');
const path = require('path');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3001;

// Enable CORS
app.use(cors());
app.use(express.json());

// Add API routes
const apiRoutes = require('./server/api-routes');
app.use('/api', apiRoutes);

// Serve static files from the root directory
app.use(express.static(path.join(__dirname)));

// Handle all routes by serving index.html (except API routes)
app.get('*', (req, res) => {
    // Don't serve index.html for API routes
    if (req.path.startsWith('/api/')) {
        return res.status(404).json({ error: 'API endpoint not found' });
    }
    res.sendFile(path.join(__dirname, 'index.html'));
});

// Start the server if this file is run directly
if (require.main === module) {
    app.listen(PORT, () => {
        console.log(`Server running on port ${PORT}`);
        console.log(`API routes available at http://localhost:${PORT}/api/`);
    });
}

// Export the app for potential use in other scripts
module.exports = app; 