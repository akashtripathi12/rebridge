import os
from rebridge_api.wiring import build_worker, Settings
from rebridge_data.models import GradingMessage

env_path = "rebridge_api/.env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                if "=" in line:
                    key, val = line.strip().split("=", 1)
                    os.environ[key] = val

settings = Settings.from_env()
worker = build_worker(settings)

item_id = "7629be027f744aa88d61cadeee2d9fc8"
msg = GradingMessage(item_id=item_id, idem_key="idem-debug-123", photo_keys=[f"items/{item_id}/photo-1", f"items/{item_id}/photo-2", f"items/{item_id}/photo-3", f"items/{item_id}/photo-4"])

import threading

def run_it():
    print("Running pipeline...")
    try:
        worker.pipeline_provider().run(msg)
        print("Success!")
    except Exception as e:
        import traceback
        traceback.print_exc()

t = threading.Thread(target=run_it)
t.start()
t.join()
