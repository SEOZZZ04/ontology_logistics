from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import asyncio
from contextlib import asynccontextmanager
import logging

from .database import db
from .simulator import simulator
from .agent import query_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.clean_database()
    db.init_schema()
    db.seed_data()
    sim_task = asyncio.create_task(simulator.start())
    yield
    simulator.stop()
    await sim_task
    db.close()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/ui", StaticFiles(directory="frontend", html=True), name="ui")

class ChatRequest(BaseModel):
    message: str

@app.get("/")
async def read_root():
    return RedirectResponse(url="/ui/index.html")

@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        result = await query_agent(req.message)
        return result
    except Exception as e:
        logger.error(f"Chat Error: {e}")
        return {
            "reply": f"죄송합니다. AI 서비스 연결이 불안정합니다. ({str(e)})",
            "related_nodes": []
        }

@app.get("/api/system-status")
async def get_system_status():
    # 1. 구역별 아이템 개수
    q_count = """
    MATCH (z:Zone)
    OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
    RETURN z.id as id, count(i) as count
    """
    counts = {row['id']: row['count'] for row in db.run_query(q_count)}
    
    # 2. AGV 상태 확인 (운반 중인 물건이 있는지)
    q_agv = """
    MATCH (a:AGV)
    OPTIONAL MATCH (i:Item)-[:LOADED_ON]->(a)
    RETURN a.id as id, i.id as carrying_item
    """
    agv_status = {row['id']: row['carrying_item'] for row in db.run_query(q_agv)}

    # 3. 이벤트 정보
    q_events = "MATCH (e:Event) RETURN e.type as type, e.description as desc ORDER BY e.timestamp DESC LIMIT 3"
    events = db.run_query(q_events)
    
    error_active = any(e['type'] == 'ERROR' for e in events)
    promo_active = any(e['type'] == 'PROMO' for e in events)

    return {
        "counts": counts,
        "agv_status": agv_status, # AGV 정보 추가됨
        "events": events,
        "error_active": error_active,
        "promo_active": promo_active
    }

@app.get("/api/node-details/{node_id}")
async def get_node_details(node_id: str):
    # AGV인 경우 운반 중인 아이템 표시
    if node_id.startswith("AGV"):
        q = """
        MATCH (a:AGV {id: $id})
        OPTIONAL MATCH (i:Item)-[:LOADED_ON]->(a)
        RETURN i.id as id, toString(i.timestamp) as time
        """
    else:
        # Zone인 경우 보관 중인 아이템 표시
        q = """
        MATCH (z:Zone {id: $id})
        OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
        RETURN i.id as id, toString(i.timestamp) as time
        ORDER BY i.timestamp DESC LIMIT 10
        """
        
    items = db.run_query(q, {"id": node_id})
    valid_items = [i for i in items if i['id'] is not None]
    
    return {"node_id": node_id, "items": valid_items}
