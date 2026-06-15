import boto3
import os

bucket_name = "rebridge-items"
region = "ap-south-1"

s3 = boto3.client("s3", region_name=region)

cors_configuration = {
    'CORSRules': [{
        'AllowedHeaders': ['*'],
        'AllowedMethods': ['PUT', 'POST', 'GET', 'HEAD'],
        'AllowedOrigins': [
            'http://localhost:3000',
            'https://rebridge-beta.vercel.app'
        ],
        'ExposeHeaders': ['ETag']
    }]
}

print(f"Setting CORS on bucket {bucket_name} in region {region}...")
try:
    s3.put_bucket_cors(Bucket=bucket_name, CORSConfiguration=cors_configuration)
    print("CORS successfully applied.")
except Exception as e:
    print(f"Error applying CORS: {e}")
