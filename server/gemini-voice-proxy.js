/**
 * Secure WebSocket Proxy for Gemini Live API
 * This server acts as a proxy between the client and Gemini Live API
 * keeping the API key secure on the server side
 */

const WebSocket = require('ws');
const http = require('http');
const url = require('url');

// Environment variables
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const PORT = process.env.GEMINI_PROXY_PORT || 8081;

if (!GEMINI_API_KEY) {
    console.error('GEMINI_API_KEY environment variable is required');
    process.exit(1);
}

// Create HTTP server for WebSocket upgrade
const server = http.createServer();

// Create WebSocket server
const wss = new WebSocket.Server({ 
    server,
    path: '/gemini-voice-proxy'
});

console.log(`Gemini Voice Proxy Server starting on port ${PORT}`);

// Map to track client connections and their corresponding Gemini WebSocket connections
const connectionMap = new Map();

wss.on('connection', (clientWs, request) => {
    const clientId = generateClientId();
    console.log(`[${clientId}] Client connected from ${request.connection.remoteAddress}`);

    // Store client connection
    connectionMap.set(clientId, {
        clientWs: clientWs,
        geminiWs: null,
        isActive: false
    });

    clientWs.on('message', async (message) => {
        try {
            const data = JSON.parse(message.toString());
            await handleClientMessage(clientId, data);
        } catch (error) {
            console.error(`[${clientId}] Error parsing client message:`, error);
            sendErrorToClient(clientId, 'Invalid message format');
        }
    });

    clientWs.on('close', () => {
        console.log(`[${clientId}] Client disconnected`);
        cleanupConnection(clientId);
    });

    clientWs.on('error', (error) => {
        console.error(`[${clientId}] Client WebSocket error:`, error);
        cleanupConnection(clientId);
    });

    // Send acknowledgment to client
    clientWs.send(JSON.stringify({
        type: 'proxy_connected',
        clientId: clientId
    }));
});

async function handleClientMessage(clientId, message) {
    const connection = connectionMap.get(clientId);
    if (!connection) {
        console.error(`[${clientId}] Connection not found`);
        return;
    }

    // Handle different message types
    switch (message.type) {
        case 'start_session':
            await startGeminiSession(clientId, message.config);
            break;

        case 'end_session':
            await endGeminiSession(clientId);
            break;

        case 'gemini_message':
            // Forward message to Gemini Live API
            if (connection.geminiWs && connection.geminiWs.readyState === WebSocket.OPEN) {
                connection.geminiWs.send(JSON.stringify(message.data));
            } else {
                sendErrorToClient(clientId, 'Gemini session not active');
            }
            break;

        default:
            console.warn(`[${clientId}] Unknown message type: ${message.type}`);
    }
}

async function startGeminiSession(clientId, config) {
    const connection = connectionMap.get(clientId);
    if (!connection) return;

    try {
        console.log(`[${clientId}] Starting Gemini Live API session`);

        // Create WebSocket connection to Gemini Live API
        const geminiWsUrl = `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=${GEMINI_API_KEY}&alt=json`;
        
        const geminiWs = new WebSocket(geminiWsUrl);
        connection.geminiWs = geminiWs;

        geminiWs.on('open', () => {
            console.log(`[${clientId}] Connected to Gemini Live API`);
            connection.isActive = true;

            // Send initial configuration if provided
            if (config) {
                geminiWs.send(JSON.stringify(config));
            }

            // Notify client that session is ready
            connection.clientWs.send(JSON.stringify({
                type: 'session_started',
                status: 'connected'
            }));
        });

        geminiWs.on('message', (message) => {
            // Forward Gemini response to client
            let data;
            if (message instanceof Buffer || message instanceof ArrayBuffer) {
                // Handle binary data (audio)
                connection.clientWs.send(message);
            } else {
                // Handle text/JSON data
                try {
                    data = JSON.parse(message.toString());
                    connection.clientWs.send(JSON.stringify({
                        type: 'gemini_response',
                        data: data
                    }));
                } catch (parseError) {
                    console.error(`[${clientId}] Error parsing Gemini response:`, parseError);
                }
            }
        });

        geminiWs.on('close', (code, reason) => {
            console.log(`[${clientId}] Gemini WebSocket closed:`, code, reason.toString());
            connection.isActive = false;
            connection.geminiWs = null;

            // Notify client
            if (connection.clientWs.readyState === WebSocket.OPEN) {
                connection.clientWs.send(JSON.stringify({
                    type: 'session_ended',
                    reason: 'gemini_disconnected'
                }));
            }
        });

        geminiWs.on('error', (error) => {
            console.error(`[${clientId}] Gemini WebSocket error:`, error);
            sendErrorToClient(clientId, 'Gemini connection error');
            connection.isActive = false;
            connection.geminiWs = null;
        });

    } catch (error) {
        console.error(`[${clientId}] Error starting Gemini session:`, error);
        sendErrorToClient(clientId, 'Failed to start Gemini session');
    }
}

async function endGeminiSession(clientId) {
    const connection = connectionMap.get(clientId);
    if (!connection) return;

    console.log(`[${clientId}] Ending Gemini session`);

    if (connection.geminiWs) {
        try {
            // Send end session message to Gemini
            if (connection.geminiWs.readyState === WebSocket.OPEN) {
                connection.geminiWs.send(JSON.stringify({
                    realtime_input: {
                        activity_end: {}
                    }
                }));
                
                connection.geminiWs.send(JSON.stringify({
                    realtime_input: {
                        audio_stream_end: true
                    }
                }));
            }

            connection.geminiWs.close(1000, 'Session ended by client');
        } catch (error) {
            console.error(`[${clientId}] Error closing Gemini WebSocket:`, error);
        }
        
        connection.geminiWs = null;
    }

    connection.isActive = false;

    // Notify client
    if (connection.clientWs.readyState === WebSocket.OPEN) {
        connection.clientWs.send(JSON.stringify({
            type: 'session_ended',
            reason: 'client_request'
        }));
    }
}

function sendErrorToClient(clientId, errorMessage) {
    const connection = connectionMap.get(clientId);
    if (connection && connection.clientWs.readyState === WebSocket.OPEN) {
        connection.clientWs.send(JSON.stringify({
            type: 'error',
            message: errorMessage
        }));
    }
}

function cleanupConnection(clientId) {
    const connection = connectionMap.get(clientId);
    if (connection) {
        // Close Gemini WebSocket if open
        if (connection.geminiWs) {
            try {
                connection.geminiWs.close(1000, 'Client disconnected');
            } catch (error) {
                console.error(`[${clientId}] Error closing Gemini WebSocket during cleanup:`, error);
            }
        }
        
        // Remove from connection map
        connectionMap.delete(clientId);
        console.log(`[${clientId}] Connection cleaned up`);
    }
}

function generateClientId() {
    return 'client_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
}

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('\nShutting down Gemini Voice Proxy Server...');
    
    // Close all connections
    for (const [clientId, connection] of connectionMap) {
        try {
            if (connection.clientWs) {
                connection.clientWs.close(1000, 'Server shutting down');
            }
            if (connection.geminiWs) {
                connection.geminiWs.close(1000, 'Server shutting down');
            }
        } catch (error) {
            console.error(`Error closing connection ${clientId}:`, error);
        }
    }
    
    connectionMap.clear();
    server.close(() => {
        console.log('Server closed');
        process.exit(0);
    });
});

// Start the server
server.listen(PORT, () => {
    console.log(`Gemini Voice Proxy Server running on port ${PORT}`);
}); 