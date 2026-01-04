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
    # 시뮬레이터 시작
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
    result = await query_agent(req.message)
    return result

@app.get("/api/dashboard-stats")
async def get_dashboard_stats():
    q1 = """
    MATCH (z:Zone)
    OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
    RETURN z.id as id, z.name as name, count(i) as count ORDER BY z.id
    """
    zone_stats = db.run_query(q1)
    
    q2 = """
    MATCH (e:Event)
    RETURN e.id as id, e.description as desc, e.type as type
    ORDER BY e.timestamp DESC LIMIT 5
    """
    events = db.run_query(q2)
    return {"zones": zone_stats, "events": events}

@app.get("/api/graph-data")
async def get_graph_data():
    # [수정 1] Item을 제외하던 WHERE 절 삭제 -> 모든 노드 조회
    query = """
    MATCH (n)
    OPTIONAL MATCH (n)-[r]->(m)
    RETURN n.id as source_id, labels(n)[0] as source_label, n.name as source_name, n.type as source_type,
           m.id as target_id, labels(m)[0] as target_label, m.name as target_name, m.type as target_type,
           type(r) as edge_type
    """
    data = db.run_query(query)
    
    nodes = {}
    edges = []
    
    # 색상 맵 (Item 색상 추가)
    color_map = {
        "Center": "#FF6F00", 
        "Zone": "#FF8F00", 
        "AGV": "#00897B",
        "Item": "#42A5F5",  # 아이템: 밝은 파랑
        "Event_ERROR": "#D32F2F", 
        "Event_PROMO": "#7B1FA2"
    }
    
    for row in data:
        # Source Node 처리
        s_id = row['source_id']
        s_lbl = row['source_label']
        s_key = f"{s_lbl}_{row.get('source_type', '')}" if s_lbl == 'Event' else s_lbl
        
        # Item은 텍스트 대신 박스 아이콘 사용
        s_label = "📦" if s_lbl == 'Item' else row.get('source_name', s_id)
        
        nodes[s_id] = {
            "id": s_id, 
            "label": s_label, 
            "group": s_lbl,
            "color": color_map.get(s_key, "#90A4AE"), 
            "font": {"color": "#fff" if s_lbl in ["Event", "Center"] else "#000"},
            "shape": "box" if s_lbl == "Zone" else "dot"
        }

        # Target Node 처리
        if row['target_id']:
            t_id = row['target_id']
            t_lbl = row['target_label']
            t_key = f"{t_lbl}_{row.get('target_type', '')}" if t_lbl == 'Event' else t_lbl

            t_label = "📦" if t_lbl == 'Item' else row.get('target_name', t_id)

            nodes[t_id] = {
                "id": t_id, 
                "label": t_label, 
                "group": t_lbl,
                "color": color_map.get(t_key, "#90A4AE"),
                "shape": "box" if t_lbl == "Zone" else "dot"
            }
            
            # [수정 2] 시각화 방향 조정 (Hierarchical Layout 최적화)
            # DB상: Item -> Zone (STORED_IN)
            # 시각화: Zone -> Item (화살표를 뒤집어야 Zone 밑에 Item이 달림)
            edge_type = row['edge_type']
            
            if edge_type == 'STORED_IN':
                v_from, v_to = t_id, s_id # Zone -> Item
                arrows = "to"
            elif edge_type == 'LOCATED_AT':
                 v_from, v_to = t_id, s_id # Zone -> AGV
                 arrows = "to"
            else:
                v_from, v_to = s_id, t_id # Normal flow
                arrows = "to"

            edge_key = f"{v_from}-{v_to}"
            
            # 중복 엣지 방지
            if not any(e['id'] == edge_key for e in edges):
                edges.append({
                    "id": edge_key, "from": v_from, "to": v_to, 
                    "label": edge_type, "arrows": arrows, 
                    "color": {"color": "#CFD8DC"}
                })
    
    return {"nodes": list(nodes.values()), "edges": edges}
