import uvicorn
from rebridge_api.wiring import build_app, Settings

app = build_app(Settings.from_env())

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
