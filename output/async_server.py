import os
import json
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from data.live_worker import LiveDataWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("AsyncServer")

# Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR = os.path.join(BASE_DIR, "output", "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "output", "templates")
DATA_PATH = os.path.join(BASE_DIR, "output", "dashboard_data.json")

# Initialize live worker
live_worker = LiveDataWorker()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start live market data worker
    logger.info("Lifespan startup: starting live data worker...")
    await live_worker.start()
    yield
    # Shutdown: Stop live worker
    logger.info("Lifespan shutdown: stopping live data worker...")
    await live_worker.stop()

app = FastAPI(lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Track active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Total clients: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                # Handle dead connections silently
                pass

manager = ConnectionManager()

# Hook live worker updates directly to WebSocket manager broadcast
async def live_feed_callback(payload: dict):
    await manager.broadcast({
        "type": "live_tick",
        "data": payload
    })

live_worker.subscribe(live_feed_callback)

def load_dashboard_data():
    if not os.path.exists(DATA_PATH):
        return {
            "regime_info": {"regime": "UNKNOWN", "reason": "No data file", "vix": 15.0, "pcr": 1.0, "nifty_trend": "NEUTRAL"},
            "picks": {"intraday_picks": [], "high_risk_picks": [], "swing_picks": []},
            "sector_momentum": {"sectors": [], "top_sector": "None"}
        }
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return {
                "regime_info": {"regime": "ERROR", "reason": "Parse error", "vix": 15.0, "pcr": 1.0, "nifty_trend": "NEUTRAL"},
                "picks": {"intraday_picks": [], "high_risk_picks": [], "swing_picks": []},
                "sector_momentum": {"sectors": [], "top_sector": "None"}
            }

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    data = load_dashboard_data()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "regime": data.get("regime_info", {}),
            "picks": data.get("picks", {}),
            "sector_momentum": data.get("sector_momentum", {"sectors": [], "top_sector": "None"})
        }
    )

@app.get("/api/data")
async def get_api_data():
    return load_dashboard_data()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    # Send historical baseline/ticks of tracked symbols immediately to bootstrap the client charts
    bootstrap_data = {
        "type": "bootstrap",
        "history": {sym: live_worker.history[sym] for sym in live_worker.symbols}
    }
    await manager.send_personal_message(bootstrap_data, websocket)
    
    try:
        while True:
            # Keep connection alive, listen for client pings if needed
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)
