const AWS = require('aws-sdk');
// Configure AWS SDK logging
AWS.config.logger = console;
AWS.config.update({ 
    region: process.env.REGION || 'us-east-2',
    logger: console
});

const dynamoDB = new AWS.DynamoDB.DocumentClient();
const TABLE_NAME = `WaitList-${process.env.ENV}`;

/**
 * @type {import('@types/aws-lambda').APIGatewayProxyHandler}
 */
exports.handler = async (event, context) => {
    try {
        // Log the raw event first
        console.log('=== START OF FUNCTION EXECUTION ===');
        console.log('Raw event:', JSON.stringify(event, null, 2));
        console.log('Context:', JSON.stringify(context, null, 2));
        console.log('Environment:', process.env.ENV);
        console.log('Region:', process.env.REGION);
        console.log('Table Name:', TABLE_NAME);
        
        let body;
        // Check if this is a test event
        if (event.hasOwnProperty('firstName') && event.hasOwnProperty('lastName') && event.hasOwnProperty('email')) {
            console.log('Detected test event format');
            body = event;
        } else if (event.body) {
            console.log('Detected API Gateway event format');
            try {
                body = JSON.parse(event.body);
                console.log('Parsed API Gateway body:', JSON.stringify(body, null, 2));
            } catch (error) {
                console.error('Error parsing request body:', error);
                return {
                    statusCode: 400,
                    headers: {
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': '*'
                    },
                    body: JSON.stringify({ error: 'Invalid request body' })
                };
            }
        } else {
            console.error('Unsupported event format:', JSON.stringify(event, null, 2));
            return {
                statusCode: 400,
                headers: {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': '*'
                },
                body: JSON.stringify({ error: 'Unsupported event format' })
            };
        }
        
        console.log('Processing body:', JSON.stringify(body, null, 2));
        const { firstName, lastName, email } = body;
        console.log('Extracted fields:', JSON.stringify({ firstName, lastName, email }, null, 2));
        
        if (!email || !firstName || !lastName) {
            console.log('Missing required fields:', JSON.stringify({ email, firstName, lastName }, null, 2));
            return {
                statusCode: 400,
                headers: {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': '*'
                },
                body: JSON.stringify({ error: 'All fields are required' })
            };
        }

        const timestamp = new Date().toISOString();
        const params = {
            TableName: TABLE_NAME,
            Item: {
                id: timestamp,
                firstName,
                lastName,
                email,
                createdAt: timestamp
            }
        };

        console.log('Prepared DynamoDB params:', JSON.stringify(params, null, 2));

        console.log('Attempting DynamoDB put operation...');
        const result = await dynamoDB.put(params).promise();
        console.log('DynamoDB put result:', JSON.stringify(result, null, 2));
        console.log('Successfully added to waitlist');
        console.log('=== END OF FUNCTION EXECUTION ===');
        return {
            statusCode: 200,
            headers: {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': '*'
            },
            body: JSON.stringify({ success: true })
        };
    } catch (error) {
        console.error('Error in handler:', error);
        console.error('Error details:', JSON.stringify({
            message: error.message,
            code: error.code,
            statusCode: error.statusCode,
            retryable: error.retryable,
            time: error.time,
            stack: error.stack
        }, null, 2));
        console.log('=== END OF FUNCTION EXECUTION ===');
        return {
            statusCode: 500,
            headers: {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': '*'
            },
            body: JSON.stringify({ error: 'Failed to add to waitlist', details: error.message })
        };
    }
};
