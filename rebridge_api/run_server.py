import os
import uvicorn
from rebridge_api.wiring import build_app, Settings

app = build_app(Settings.from_env())

if __name__ == "__main__":
    # Bind to 0.0.0.0 for cloud deployment (Render, etc.)
    # Use PORT env var if available (Render requirement), else default to 8000
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
