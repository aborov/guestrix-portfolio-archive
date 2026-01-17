require('dotenv').config();
const express = require('express');
const path = require('path');
const cors = require('cors');
const AWS = require('aws-sdk');

const app = express();
const PORT = process.env.PORT || 3001;

// Initialize AWS Systems Manager
const ssm = new AWS.SSM({
    region: 'us-east-2' // Default region, will be overridden by parameters
});

// Function to get parameters from SSM
async function getParameters() {
    try {
        console.log('Fetching parameters from SSM...');
        const params = {
            Path: '/amplify/d1u169ifu6z79x/dev/',
            WithDecryption: true,
            Recursive: true
        };
        
        const result = await ssm.getParametersByPath(params).promise();
        console.log('SSM Parameters fetched:', result.Parameters);
        
        const parameters = {};
        result.Parameters.forEach(param => {
            const key = param.Name.split('/').pop();
            parameters[key] = param.Value;
        });
        
        console.log('Processed parameters:', parameters);
        return parameters;
    } catch (error) {
        console.error('Error getting parameters:', error);
        throw error;
    }
}

// Configure AWS with parameters from SSM
async function configureAWS() {
    try {
        const parameters = await getParameters();
        console.log('Configuring AWS with parameters...');
        AWS.config.update({
            region: parameters.REGION || 'us-east-2',
            accessKeyId: parameters.ACCESS_KEY_ID,
            secretAccessKey: parameters.SECRET_ACCESS_KEY
        });
        console.log('AWS configured successfully with region:', parameters.REGION || 'us-east-2');
    } catch (error) {
        console.error('Error configuring AWS:', error);
    }
}

// Initialize AWS configuration
configureAWS();

// Enable CORS
app.use(cors());
app.use(express.json());

// Serve static files from the root directory
app.use(express.static(path.join(__dirname, '..')));

// Handle all routes by serving index.html
app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, '..', 'index.html'));
});

// Note: Waitlist endpoints have been removed as they're now managed by Amplify's API

app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
}); 