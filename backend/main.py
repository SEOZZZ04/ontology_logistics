from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import asyncio
from contextlib import asynccontextmanager

# 기존 모듈 가져오기
from .database import db
from .simulator import simulator
from .agent import query_agent

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. DB 초기화
    db.clean_database()
    db.init_schema()
    db.seed_data()
    # 2. 시뮬레이터 가동
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

# [수정] LLM 채팅 엔드포인트 보완
@app.post("/api/chat")
async def chat(req: ChatRequest):
    print(f"💬 [Chat 요청] 사용자: {req.message}") # 터미널 로그 추가
    try:
        # agent.py의 query_agent 함수 호출
        result = await query_agent(req.message)
        print(f"🤖 [Chat 응답] AI: {result['reply'][:30]}...") 
        return result
    except Exception as e:
        print(f"❌ [Chat 에러] {str(e)}")
        return {"reply": "죄송합니다. 내부 시스템 오류로 답변할 수 없습니다.", "related_nodes": []}

# [데이터 API 1] 온톨로지 구조 (노드/엣지) - 한 번만 로딩
@app.get("/api/ontology-structure")
async def get_ontology_structure():
    # Item, Event 제외 -> 구조만 리턴
    query = """
    MATCH (n)
    WHERE labels(n)[0] IN ['Center', 'Zone', 'AGV']
    OPTIONAL MATCH (n)-[r]->(m)
    WHERE labels(m)[0] IN ['Center', 'Zone', 'AGV']
    RETURN n.id as source_id, labels(n)[0] as source_label, n.name as source_name,
           m.id as target_id, labels(m)[0] as target_label, m.name as target_name,
           type(r) as edge_type
    """
    data = db.run_query(query)
    
    nodes = {}
    edges = []
    
    for row in data:
        s_id = row['source_id']
        # 그룹 설정 (시각화용)
        nodes[s_id] = {"id": s_id, "label": row['source_name'], "group": row['source_label']}
        
        if row['target_id']:
            t_id = row['target_id']
            nodes[t_id] = {"id": t_id, "label": row['target_name'], "group": row['target_label']}
            
            edge_key = f"{s_id}-{t_id}"
            if not any(e['id'] == edge_key for e in edges):
                edges.append({"id": edge_key, "from": s_id, "to": t_id, "label": row['edge_type']})

    return {"nodes": list(nodes.values()), "edges": edges}

# [데이터 API 2] 실시간 상태 (카운트 & 에러)
@app.get("/api/system-status")
async def get_system_status():
    # 1. 구역별 물동량 (상단 카드용)
    q_count = """
    MATCH (z:Zone)
    OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
    RETURN z.id as id, count(i) as count
    """
    counts = {row['id']: row['count'] for row in db.run_query(q_count)}
    
    # 2. 장애 이벤트 확인
    q_error = """
    MATCH (e:Event {type: 'ERROR'})
    RETURN e.description as desc
    """
    errors = db.run_query(q_error)
    
    # 장애 발생 시 관련 노드(Zone) ID 추출
    error_nodes = []
    if errors:
        error_nodes = ['Z_IN', 'Z_SORT'] # 장애 시 입고/분류 라인 경고

    return {
        "counts": counts,
        "error_nodes": error_nodes,
        "active_events": [e['desc'] for e in errors]
    }
