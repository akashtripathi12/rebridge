import requests
import boto3
import os

env_path = "rebridge_api/.env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, val = line.strip().split("=", 1)
                os.environ[key] = val

region = os.environ.get("REBRIDGE_REGION")
bucket = os.environ.get("REBRIDGE_PHOTO_BUCKET")

s3 = boto3.client("s3", region_name=region)
url = s3.generate_presigned_url("put_object", Params={"Bucket": bucket, "Key": "test-file.txt"}, ExpiresIn=300)

print("URL:", url)

res = requests.put(url, data=b"hello", headers={"Content-Type": "text/plain"})
print(res.status_code)
print(res.text)
