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

# [채팅 API]
@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        result = await query_agent(req.message)
        return result
    except Exception as e:
        logger.error(f"Chat Error: {e}")
        # 에러 메시지를 더 구체적으로 반환하지 않고 사용자에게는 정중하게 표현
        return {
            "reply": f"죄송합니다. AI 모델 연결 중 오류가 발생했습니다. (Error: {str(e)})",
            "related_nodes": []
        }

# [시스템 상태 API]
@app.get("/api/system-status")
async def get_system_status():
    # 1. 구역별 카운트
    q_count = "MATCH (z:Zone) OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z) RETURN z.id as id, count(i) as count"
    counts = {row['id']: row['count'] for row in db.run_query(q_count)}
    
    # 2. 최근 이벤트
    q_events = "MATCH (e:Event) RETURN e.type as type, e.description as desc ORDER BY e.timestamp DESC LIMIT 3"
    events = db.run_query(q_events)
    
    # 3. 현재 장애/프로모션 활성 여부 (Simulator 상태와 DB 이벤트로 판단)
    error_active = any(e['type'] == 'ERROR' for e in events)
    promo_active = any(e['type'] == 'PROMO' for e in events)

    return {
        "counts": counts,
        "events": events,
        "error_active": error_active,
        "promo_active": promo_active
    }

# [노드 상세 정보 API] (새로 추가됨)
@app.get("/api/node-details/{node_id}")
async def get_node_details(node_id: str):
    # 해당 존에 있는 아이템 리스트 조회
    q = """
    MATCH (z:Zone {id: $id})
    OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
    RETURN i.id as id, toString(i.timestamp) as time
    ORDER BY i.timestamp DESC LIMIT 10
    """
    items = db.run_query(q, {"id": node_id})
    # 아이템이 없는 경우(null) 필터링
    valid_items = [i for i in items if i['id'] is not None]
    
    return {"node_id": node_id, "items": valid_items}
