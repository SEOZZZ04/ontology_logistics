from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import asyncio
from contextlib import asynccontextmanager

# 기존 DB/Sim/Agent 모듈은 그대로 활용 (데이터 생성/저장은 필요하므로)
from .database import db
from .simulator import simulator
from .agent import query_agent

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. DB 초기화 및 기초 데이터 생성
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

@app.post("/api/chat")
async def chat(req: ChatRequest):
    # 검색 및 질문 처리
    result = await query_agent(req.message)
    return result

# [핵심 1] 온톨로지 구조(뼈대)만 리턴하는 API
@app.get("/api/ontology-structure")
async def get_ontology_structure():
    # Item, Event는 제외하고 오직 센터, 구역, 장비만 조회
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
        # 노드 생성
        s_id = row['source_id']
        nodes[s_id] = {"id": s_id, "label": row['source_name'], "group": row['source_label']}
        
        if row['target_id']:
            t_id = row['target_id']
            nodes[t_id] = {"id": t_id, "label": row['target_name'], "group": row['target_label']}
            
            # 엣지 생성
            edge_key = f"{s_id}-{t_id}"
            if not any(e['id'] == edge_key for e in edges):
                edges.append({"id": edge_key, "from": s_id, "to": t_id, "label": row['edge_type']})

    return {"nodes": list(nodes.values()), "edges": edges}

# [핵심 2] 상태(색상 변경용) 데이터 리턴
@app.get("/api/system-status")
async def get_system_status():
    # 1. 구역별 물동량 카운트
    q_count = """
    MATCH (z:Zone)
    OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
    RETURN z.id as id, count(i) as count
    """
    counts = {row['id']: row['count'] for row in db.run_query(q_count)}
    
    # 2. 현재 발생한 '장애(ERROR)' 이벤트가 연결된 구역 찾기
    # 이벤트 노드(Event)가 센터(Center)나 특정 구역과 연결되어 있을 수 있음
    # 시뮬레이터 로직상 Event는 Center에 달리지만, 
    # 여기서는 '설명(description)'이나 로직을 통해 어디가 문제인지 판단하여 프론트로 보냄
    q_error = """
    MATCH (e:Event {type: 'ERROR'})
    RETURN e.description as desc
    """
    errors = db.run_query(q_error)
    
    # 장애가 발생한 노드 ID 목록 (단순화: 에러 있으면 무조건 Z_IN, Z_SORT 등 관련 구역 빨간색)
    error_nodes = []
    if errors:
        # 장애가 존재하면 주요 라인 전체를 경고 상태로
        # (더 정교하게 하려면 Event와 Zone을 연결해야 하지만, 시각적 효과를 위해 단순화)
        error_nodes = ['Z_IN', 'Z_SORT'] 

    return {
        "counts": counts,
        "error_nodes": error_nodes,
        "active_events": [e['desc'] for e in errors]
    }
