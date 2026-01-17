# Lambda Function Testing

This directory contains Lambda functions for the Concierge app. The `ingestion_lambda_function.py` has been updated to use **Firestore as the primary database** instead of the deprecated DynamoDB ConciergeTable. 

## Architecture Update

**IMPORTANT**: The main data operations (users, properties, knowledge sources, knowledge items, reservations) have been migrated from DynamoDB (ConciergeTable) to Firestore. DynamoDB is now only used for:
- Conversations (separate table)
- WebSocket connections (separate table)

The `ConciergeTable` is **DEPRECATED** and will be removed once migration is complete.

## Prerequisites

Ensure you have the following environment variables set:

```
# DEPRECATED: DYNAMODB_TABLE_NAME is no longer used for main operations
# export DYNAMODB_TABLE_NAME=ConciergeTable
export LANCEDB_S3_URI=s3://your-bucket/lancedb
export LANCEDB_TABLE_NAME=knowledge_base
export GEMINI_API_KEY=your-gemini-api-key
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/firebase-credentials.json
```

You'll also need:
- AWS credentials configured (via `~/.aws/credentials` or environment variables) for LanceDB S3 access
- Firebase/Firestore credentials for primary database operations

## Testing Locally

Two test scripts are provided in the `concierge/scripts` directory:

### 1. Test Ingestion Lambda

This script creates a test knowledge item in **Firestore** and calls the Lambda handler function directly:

```bash
python scripts/test_ingestion_lambda.py --property-id YOUR_PROPERTY_ID
```

Options:
- `--property-id` (required): The property ID to use for the test item
- `--action`: Action to test (`ingest`, `update`, or `delete`), default is `ingest`
- `--item-id`: Use an existing item ID instead of creating a new one
- `--source-id`: Use a specific source ID
- `--dynamodb-table`: ~~DynamoDB table name~~ **DEPRECATED** (now uses Firestore)

Example for testing item deletion:
```bash
python scripts/test_ingestion_lambda.py --property-id YOUR_PROPERTY_ID --action delete --item-id ITEM_ID --source-id SOURCE_ID
```

### 2. Verify Firestore and LanceDB Sync

This script verifies that knowledge items in **Firestore** match those in LanceDB:

```bash
python scripts/verify_lancedb_firestore.py
```

Options:
- `--lancedb-uri`: LanceDB S3 URI
- `--lancedb-table`: LanceDB table name
- `--limit`: Limit the number of items to check
- `--sample`: Number of items to sample for content verification (default: 5)

## Deploying to AWS Lambda

1. Create a deployment package:

```bash
mkdir -p dist
cd lambda_src
pip install -r requirements.txt --target ../dist/
cp ingestion_lambda_function.py ../dist/
cd ..
cd dist
zip -r ../lambda_deployment.zip .
cd ..
```

2. Deploy the package using the AWS CLI:

```bash
aws lambda update-function-code \
    --function-name knowledge-ingestion-lambda \
    --zip-file fileb://lambda_deployment.zip
```

3. Update environment variables (note: DYNAMODB_TABLE_NAME removed):

```bash
aws lambda update-function-configuration \
    --function-name knowledge-ingestion-lambda \
    --environment "Variables={LANCEDB_S3_URI=s3://your-bucket/lancedb,LANCEDB_TABLE_NAME=knowledge_base,GEMINI_API_KEY=your-gemini-api-key,GOOGLE_APPLICATION_CREDENTIALS=/opt/firebase-credentials.json}"
```

4. Set up IAM permissions:
   - ~~Ensure the Lambda execution role has permissions for DynamoDB (read/write)~~ **DEPRECATED**
   - Ensure it has access to the S3 bucket used for LanceDB
   - Ensure Firebase/Firestore credentials are properly configured

## Troubleshooting

- Check Lambda logs in CloudWatch
- Verify environment variables are correctly set
- Ensure IAM permissions are properly configured for S3 (LanceDB)
- Ensure Firestore credentials are properly configured
- Test locally first before deploying to AWS 

## Migration Notes

If you're migrating from the old DynamoDB-based system:
1. Run the migration script: `python scripts/migrate_to_firestore.py`
2. Update all environment variables to remove `DYNAMODB_TABLE_NAME`
3. Deploy updated Lambda functions
4. Verify all operations work with Firestore
5. **Only then** delete the old ConciergeTable 