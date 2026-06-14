"""Quick test: create a new item, upload a test photo, enqueue grading, poll for result."""
import os, json, time, urllib.request, urllib.error

env_path = "rebridge_api/.env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

from rebridge_api.wiring import build_services, Settings

settings = Settings.from_env()
built = build_services(settings)

# 1. Create an item
from rebridge_data.models import ItemMeta, ItemStatus
import uuid, datetime
item_id = uuid.uuid4().hex
meta = ItemMeta(
    item_id=item_id,
    status=ItemStatus.CREATED,
    category="shoes",
    age_months=2,
    context_source="order_scan",
    created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    context_ref="TEST-123",
)
built.item_repo.put_item_meta(meta)
print(f"[1] Created item: {item_id}")

# 2. Upload a tiny test PNG to S3
photo_key = f"items/{item_id}/photo-1"
# 1x1 white PNG
png_bytes = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001"
    "0800000000003a7e9b55000000"
    "0a49444154789c626000000002000148af0446"
    "0000000049454e44ae426082"
)
built.object_store._client.put_object(
    Bucket=settings.photo_bucket, Key=photo_key, Body=png_bytes
)
print(f"[2] Uploaded test photo to s3://{settings.photo_bucket}/{photo_key}")

# 3. Run the pipeline directly
from rebridge_data.models import GradingMessage
msg = GradingMessage(item_id=item_id, idem_key="test-direct", photo_keys=[photo_key])

from rebridge_api.wiring import build_worker
worker = build_worker(settings, built=built)
body = json.dumps({"item_id": msg.item_id, "idem_key": msg.idem_key, "photo_keys": list(msg.photo_keys)})
print("[3] Running worker.handle...")
result = worker.handle({"Records": [{"body": body}]})
print(f"[4] Worker result: {result}")

# 4. Check final status
agg = built.item_repo.get_item(item_id)
print(f"[5] Final status: {agg.meta.status.value}")
print(f"[5] Grade: {agg.grade}")
print(f"[5] Card: {agg.card}")
print(f"[5] Decision: {agg.decision}")
