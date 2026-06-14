import os
import boto3
import json

env_path = "rebridge_api/.env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                key, val = line.strip().split("=", 1)
                os.environ[key] = val

sqs = boto3.client("sqs", region_name=os.environ["REBRIDGE_REGION"])
item_id = "59232d4958c54cf7aa74893c0cabd5aa"

msg = {
    "item_id": item_id,
    "idem_key": "idem-trigger-123",
    "photo_keys": [f"items/{item_id}/photo-1"]
}

print("Sending message...")
sqs.send_message(
    QueueUrl=os.environ["REBRIDGE_GRADING_QUEUE_URL"],
    MessageBody=json.dumps(msg)
)
print("Message sent.")
