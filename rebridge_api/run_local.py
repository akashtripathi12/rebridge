import sys
import os
import time
import json
import threading
import uvicorn
import boto3

# Ensure tests module can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def load_dotenv():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    if "=" in line:
                        key, val = line.strip().split("=", 1)
                        os.environ[key] = val

load_dotenv()

from rebridge_api.wiring import build_app, build_worker, build_services, Settings
from fastapi.middleware.cors import CORSMiddleware

def setup_app():
    # Construct settings from environment variables populated by load_dotenv()
    settings = Settings.from_env()

    built = build_services(settings)
    app = build_app(settings, built)
    
    # Add CORS middleware so frontend can communicate on localhost:3000
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Bypass Cognito JWT verification for local testing since the frontend doesn't have a login UI yet.
    # The stub is given the operator role so the back-office routes (create/grade/route/listing
    # CRUD/review) are reachable in local dev.
    from rebridge_api.dependencies import get_current_user, CurrentUser
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        subject="local-dev-user", claims={"sub": "local-dev-user"}, role="operator"
    )

    # Build the worker using the live AWS data layers
    worker = build_worker(settings)

    # Create an SQS client to poll the live grading queue
    sqs = boto3.client("sqs", region_name=settings.region)
    queue_url = settings.grading_queue_url

    def worker_loop():
        print(f"[Worker] Started background SQS poller thread for {queue_url}...")
        while True:
            try:
                response = sqs.receive_message(
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=1,
                    WaitTimeSeconds=20 # Long polling
                )
                
                messages = response.get("Messages", [])
                for msg in messages:
                    receipt_handle = msg["ReceiptHandle"]
                    body = msg["Body"]
                    print(f"[Worker] Received message from SQS")
                    
                    # Pass the message to the GradingWorker handler using Lambda event format
                    record = {
                        "body": body
                    }
                    worker.handle({"Records": [record]})
                    print(f"[Worker] Finished processing message")
                    
                    # Delete the message from the queue after successful processing
                    sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=receipt_handle
                    )
            except Exception as e:
                print(f"[Worker] Error in SQS poller: {e}")
                time.sleep(5)

    # Start the worker thread
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()

    # Intercept lifecycle events to feed NotificationWorker directly in local mode
    original_publish = built.eventing._publish
    def local_publish(event_type, item_id, payload=None):
        event = original_publish(event_type, item_id, payload)
        # Manually trigger the NotificationWorker with the event
        try:
            built.notification_worker.handle({"Records": [{"body": json.dumps(event.__dict__)}]})
            print(f"[Worker] NotificationWorker successfully processed {event_type.value} event locally")
        except Exception as e:
            print(f"[Worker] NotificationWorker failed: {e}")
        return event

    built.eventing._publish = local_publish

    return app

app = setup_app()

if __name__ == "__main__":
    print("[API] Starting AWS-backed backend on port 8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
