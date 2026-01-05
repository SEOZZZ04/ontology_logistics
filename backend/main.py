from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import asyncio
import time
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
        # 쿼리 엔진은 기존 로직 활용 (agent.py는 수정 불필요하거나 기존 유지)
        result = await query_agent(req.message)
        return result
    except Exception as e:
        logger.error(f"Chat Error: {e}")
        return {"reply": "시스템 오류가 발생했습니다.", "related_nodes": []}

@app.get("/api/system-status")
async def get_system_status():
    current_time = time.time()
    
    # 1. Zone 통계
    q_zone = """
    MATCH (z:Zone)
    OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
    RETURN z.id as id, count(i) as count
    """
    counts = {row['id']: row['count'] for row in db.run_query(q_zone)}
    
    # 2. AGV 상태 (애니메이션 핵심 데이터)
    # 위치(LOCATED_AT) 혹은 이동중(MOVING_TO) 정보를 모두 가져옴
    q_agv = """
    MATCH (a:AGV)
    OPTIONAL MATCH (a)-[at:LOCATED_AT]->(z_curr:Zone)
    OPTIONAL MATCH (a)-[mv:MOVING_TO]->(z_dest:Zone)
    OPTIONAL MATCH (src:Zone)-[:CONNECTED_TO]->(z_dest) 
    // MOVING_TO일 경우 출발지 추론 (단순화: 역방향 추적 혹은 로직상 고정)
    // 여기서는 Simulator가 Z_IN->Z_SORT, Z_SORT->Z_OUT 고정이므로 하드코딩 대신 
    // 이전 위치를 추론하거나 DB에 출발지를 저장하는게 좋지만, 
    // 시각화를 위해 단순하게 '현재 상태'만 반환
    
    RETURN 
        a.id as id, 
        z_curr.id as current_zone, 
        z_dest.id as target_zone,
        mv.start_time as start_time,
        mv.duration as duration
    """
    
    agv_data = []
    for row in db.run_query(q_agv):
        status = "IDLE"
        progress = 0.0
        src = None
        dst = None
        
        if row['target_zone']:
            status = "MOVING"
            dst = row['target_zone']
            # 출발지 추론 (토폴로지 기반)
            src = "Z_IN" if dst == "Z_SORT" else ("Z_SORT" if dst == "Z_OUT" else "Z_IN")
            
            # 진행률 계산
            elapsed = current_time - row['start_time']
            progress = min(elapsed / row['duration'], 1.0) if row['duration'] else 0
        else:
            src = row['current_zone']
            dst = row['current_zone'] # 이동 안 함
        
        agv_data.append({
            "id": row['id'],
            "status": status,
            "source": src,
            "target": dst,
            "progress": progress
        })

    # 3. 이벤트
    q_events = "MATCH (e:Event) RETURN e.type as type, e.description as desc ORDER BY e.timestamp DESC LIMIT 1"
    events = db.run_query(q_events)
    
    return {
        "timestamp": current_time,
        "counts": counts,
        "agvs": agv_data,
        "events": events
    }

@app.get("/api/node-details/{node_id}")
async def get_node_details(node_id: str):
    # 상세 정보 조회 로직 유지
    q = """
    MATCH (n {id: $id})
    OPTIONAL MATCH (i:Item)-[:STORED_IN|LOADED_ON]->(n)
    RETURN n.name as name, n.type as type, count(i) as item_count, collect(i.id)[0..5] as recent_items
    """
    res = db.run_query(q, {"id": node_id})
    return res[0] if res else {}
