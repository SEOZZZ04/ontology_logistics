from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import asyncio
from contextlib import asynccontextmanager

from .database import db
from .simulator import simulator
from .agent import query_agent

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/ui", StaticFiles(directory="frontend", html=True), name="ui")

class ChatRequest(BaseModel):
    message: str

@app.get("/")
async def read_root():
    return RedirectResponse(url="/ui/index.html")

@app.post("/api/chat")
async def chat(req: ChatRequest):
    result = await query_agent(req.message)
    return result

@app.get("/api/dashboard-stats")
async def get_dashboard_stats():
    # 1. 구역별 정확한 물량 카운트
    q1 = """
    MATCH (z:Zone)
    OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
    RETURN z.id as id, z.name as name, count(i) as count ORDER BY z.id
    """
    zone_stats = db.run_query(q1)
    
    # 2. 이벤트 목록
    q2 = """
    MATCH (e:Event)
    RETURN e.id as id, e.description as desc, e.type as type
    ORDER BY e.timestamp DESC LIMIT 5
    """
    events = db.run_query(q2)
    
    return {"zones": zone_stats, "events": events}

@app.get("/api/graph-data")
async def get_graph_data():
    # [핵심 변경] Item 노드는 제외하고 가져옵니다! (그래프 고정용)
    # 오직 인프라(Center, Zone), 자원(AGV, Worker), 사건(Event)만 가져옴
    query = """
    MATCH (n)-[r]->(m)
    WHERE NOT labels(n)[0] = 'Item' AND NOT labels(m)[0] = 'Item'
    RETURN n.id as source_id, labels(n)[0] as source_label, n.name as source_name, n.type as source_type,
           m.id as target_id, labels(m)[0] as target_label, m.name as target_name, m.type as target_type,
           type(r) as edge_type
    """
    data = db.run_query(query)
    
    nodes = {}
    edges = []
    
    # 당근마켓 스타일 컬러 팔레트
    color_map = {
        "Center": "#FF8A3D",    # 당근 주황
        "Zone": "#FFB985",      # 연한 주황
        "AGV": "#26C6DA",       # 민트 (기계)
        "Event_ERROR": "#FF5252", # 에러 (빨강)
        "Event_PROMOTION": "#AB47BC" # 프로모션 (보라)
    }
    
    for row in data:
        s_id, s_lbl = row['source_id'], row['source_label']
        s_color_key = f"{s_lbl}_{row.get('source_type', '')}" if s_lbl == 'Event' else s_lbl
        
        if s_id not in nodes:
            nodes[s_id] = {
                "id": s_id, 
                "label": row.get('source_name', s_id),
                "group": s_lbl,
                "color": color_map.get(s_color_key, "#CFD8DC") # 기본 회색
            }

        t_id, t_lbl = row['target_id'], row['target_label']
        t_color_key = f"{t_lbl}_{row.get('target_type', '')}" if t_lbl == 'Event' else t_lbl

        if t_id not in nodes:
             nodes[t_id] = {
                "id": t_id, 
                "label": row.get('target_name', t_id),
                "group": t_lbl,
                "color": color_map.get(t_color_key, "#CFD8DC")
            }
            
        edges.append({
            "from": s_id, "to": t_id, "label": row['edge_type'],
            "color": {"color": "#B0BEC5"}, "arrows": "to"
        })
    
    return {"nodes": list(nodes.values()), "edges": edges}
