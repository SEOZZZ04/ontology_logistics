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

# 로깅 설정 (터미널에서 확인용)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. DB 초기화 (필수)
    db.clean_database()
    db.init_schema()
    db.seed_data()
    # 2. 시뮬레이터 시작
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

# [채팅 API] LLM 에러가 나도 죽지 않도록 예외 처리
@app.post("/api/chat")
async def chat(req: ChatRequest):
    logger.info(f"Chat Req: {req.message}")
    try:
        result = await query_agent(req.message)
        return result
    except Exception as e:
        logger.error(f"Chat Error: {e}")
        return {
            "reply": "죄송합니다. 현재 AI 모델 연결 상태가 불안정하여 답변할 수 없습니다. 잠시 후 다시 시도해주세요.",
            "related_nodes": []
        }

# [상태 API] 프론트엔드가 2초마다 호출
@app.get("/api/system-status")
async def get_system_status():
    # 1. 구역별 아이템 개수 집계
    q_count = """
    MATCH (z:Zone)
    OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
    RETURN z.id as id, count(i) as count
    """
    counts = {row['id']: row['count'] for row in db.run_query(q_count)}
    
    # 2. 에러 이벤트 확인
    q_error = """
    MATCH (e:Event {type: 'ERROR'})
    RETURN e.description as desc
    """
    errors = db.run_query(q_error)
    
    # 장애 시 빨간색 표시할 노드들
    error_nodes = []
    if errors:
        error_nodes = ['Z_IN', 'Z_SORT'] # 장애 발생 시 앞단 라인 경고

    # 3. 최근 5개 이벤트 (로그용)
    q_events = """
    MATCH (e:Event)
    RETURN e.type as type, e.description as desc
    ORDER BY e.timestamp DESC LIMIT 5
    """
    recent_events = db.run_query(q_events)

    return {
        "counts": counts,
        "error_nodes": error_nodes,
        "events": recent_events
    }
