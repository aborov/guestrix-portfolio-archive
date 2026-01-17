/**
 * API routes for Guestrix server
 */
const express = require('express');
const router = express.Router();

// Environment variables
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;

// Route to securely provide Gemini API key to authenticated clients
router.get('/gemini-config', (req, res) => {
    // In production, you should add authentication here
    // For example, check for valid session/JWT token
    
    if (!GEMINI_API_KEY) {
        console.error("Gemini API key not configured on server");
        return res.status(500).json({ 
            error: "API key not configured",
            message: "Voice call functionality is currently unavailable"
        });
    }
    
    // Return the API key securely
    res.json({
        apiKey: GEMINI_API_KEY
    });
});

module.exports = router; 