import boto3
import json
import csv
from datetime import datetime

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table_name = 'WaitList-dev'
table = dynamodb.Table(table_name)

def query_table():
    # Initialize variables
    all_items = []
    last_evaluated_key = None
    
    # Scan the table with pagination
    while True:
        if last_evaluated_key:
            response = table.scan(
                FilterExpression="contains(#msg, :search_term)",
                ExpressionAttributeNames={"#msg": "message"},
                ExpressionAttributeValues={":search_term": "Calculator"},
                ExclusiveStartKey=last_evaluated_key
            )
        else:
            response = table.scan(
                FilterExpression="contains(#msg, :search_term)",
                ExpressionAttributeNames={"#msg": "message"},
                ExpressionAttributeValues={":search_term": "Calculator"}
            )
        
        all_items.extend(response.get('Items', []))
        
        # Check if there are more items to fetch
        last_evaluated_key = response.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break
    
    return all_items

def export_to_csv(items, filename):
    if not items:
        print("No items found matching the criteria.")
        return
    
    # Get all unique field names from all items
    fieldnames = set()
    for item in items:
        fieldnames.update(item.keys())
    fieldnames = sorted(fieldnames)
    
    # Write to CSV
    with open(filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(items)
    
    print(f"Exported {len(items)} items to {filename}")

if __name__ == "__main__":
    print("Querying WaitList-dev table for records containing 'Calculator' in the message...")
    items = query_table()
    
    # Generate timestamp for the output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f'waitlist_calculator_export_{timestamp}.csv'
    
    export_to_csv(items, output_file)
