import sys
import os
import time
import json
import threading
import uvicorn

# Ensure tests module can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tests.conftest import Harness
from rebridge_api.worker import GradingWorker
from rebridge_service.grading_pipeline import GradingPipeline
from rebridge_api.routing_adapter import EventEmittingRouter
from rebridge_service.quality_precheck import QualityPrecheck
from rebridge_service.grading_engine import GradingEngine
from rebridge_service.confidence_gate import ConfidenceGate
from fastapi.middleware.cors import CORSMiddleware

# A fake grading engine so we don't need AWS Bedrock credentials locally
class MockGradingEngine(GradingEngine):
    def __init__(self):
        pass
    def evaluate(self, image_bytes_list, model_timeout=None):
        from rebridge_service.models import Grade, GradeAssessment, Defect, CompletenessResult
        import random
        # Randomize grade and confidence for testing
        grade_choice = random.choice([Grade.LIKE_NEW, Grade.VERY_GOOD, Grade.GOOD, Grade.ACCEPTABLE])
        confidence = random.uniform(0.65, 0.98) # Some will go to review console
        return GradeAssessment(
            grade=grade_choice,
            confidence=confidence,
            summary="Simulated grading assessment from local E2E simulation.",
            defects=[Defect(location="toe", severity="minor")],
            completeness=CompletenessResult(is_complete=True, missing_components=[]),
        )

# Mock value estimator
def value_estimator(meta, assessment):
    from decimal import Decimal
    return Decimal("150.0")

def dummy_pixel_decoder(raw: bytes) -> list[list[float]]:
    return [[10.0, 200.0, 10.0], [200.0, 10.0, 200.0], [10.0, 200.0, 10.0]]

def setup_app():
    harness = Harness()
    
    # Patch object store to return a reachable URL instead of fake-bucket.local
    def fake_presign_put(key: str, ttl_seconds: int = 300):
        from rebridge_data.models import PresignedUrl
        url = PresignedUrl(
            url=f"http://localhost:8000/mock-upload/{key}",
            method="PUT",
            headers={},
            expires_in=ttl_seconds,
        )
        harness.object_store.presigned.append(url)
        return url
    harness.object_store.presign_put = fake_presign_put

    @harness.app.api_route("/mock-upload/{key:path}", methods=["PUT", "POST", "OPTIONS"])
    async def mock_upload(key: str):
        harness.object_store.put_object(key, b"dummy image bytes")
        return {"status": "ok"}
    
    # Add CORS middleware so frontend can communicate on localhost:3000
    harness.app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    pipeline = GradingPipeline(
        item_repo=harness.item_repo,
        object_store=harness.object_store,
        review_repo=harness.review_repo,
        precheck=QualityPrecheck(),
        grading_engine=MockGradingEngine(),
        confidence_gate=ConfidenceGate(0.8),
        card_service=harness.card_service,
        eventing=harness.eventing,
        router=EventEmittingRouter(harness.routing, harness.eventing),
        pixel_decoder=dummy_pixel_decoder,
        value_estimator=value_estimator,
    )

    worker = GradingWorker(pipeline_provider=lambda: pipeline)

    def worker_loop():
        print("[Worker] Started background SQS poller thread...")
        while True:
            if harness.queue.messages:
                msg = harness.queue.messages.pop(0)
                record = {
                    "body": json.dumps({
                        "item_id": msg.item_id, 
                        "idem_key": msg.idem_key, 
                        "photo_keys": msg.photo_keys
                    })
                }
                print(f"[Worker] Processing grading message for item: {msg.item_id}")
                worker.handle({"Records": [record]})
                print(f"[Worker] Finished processing {msg.item_id}")
            time.sleep(1.0)

    # Start the worker thread
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()

    return harness.app

app = setup_app()

if __name__ == "__main__":
    print("[API] Starting local simulation backend with in-memory database...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
