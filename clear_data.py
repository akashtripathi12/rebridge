import os
import boto3
from botocore.exceptions import ClientError

def clear_dynamodb(table_name, region):
    print(f"Clearing DynamoDB table: {table_name} in {region}")
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)
    
    try:
        # Scan for all items
        response = table.scan(ProjectionExpression="PK, SK")
        items = response.get('Items', [])
        
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                ProjectionExpression="PK, SK",
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
            
        print(f"Found {len(items)} items to delete.")
        
        # Batch delete
        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(
                    Key={
                        'PK': item['PK'],
                        'SK': item['SK']
                    }
                )
        print("DynamoDB table cleared successfully.")
    except ClientError as e:
        print(f"Error clearing DynamoDB: {e}")

def clear_s3(bucket_name, region):
    print(f"Clearing S3 bucket: {bucket_name} in {region}")
    s3 = boto3.resource('s3', region_name=region)
    bucket = s3.Bucket(bucket_name)
    
    try:
        bucket.objects.all().delete()
        print("S3 bucket cleared successfully.")
    except ClientError as e:
        print(f"Error clearing S3 bucket: {e}")

if __name__ == "__main__":
    # Load env vars from rebridge_api/.env if needed, or just use hardcoded values from .env
    env_path = os.path.join(os.path.dirname(__file__), "rebridge_api", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip() and not line.startswith("#") and "=" in line:
                    key, val = line.strip().split("=", 1)
                    os.environ[key] = val

    table_name = os.environ.get("REBRIDGE_TABLE_NAME", "rebridge")
    bucket_name = os.environ.get("REBRIDGE_PHOTO_BUCKET", "rebridge-items")
    region = os.environ.get("REBRIDGE_REGION", "ap-south-1")

    clear_dynamodb(table_name, region)
    clear_s3(bucket_name, region)
    print("Done!")
