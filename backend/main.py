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
    # [수정됨] 시작할 때 DB를 깨끗하게 비우고 시작 (ConstraintError 해결)
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
    # 1. 구역별 물동량
    q1 = """
    MATCH (z:Zone)
    OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
    RETURN z.id as id, z.name as name, count(i) as count ORDER BY z.id
    """
    zone_stats = db.run_query(q1)
    
    # 2. 현재 활성 장애 이벤트 수
    q2 = "MATCH (e:Event) RETURN count(e) as error_count"
    error_stats = db.run_query(q2)
    
    return {"zones": zone_stats, "errors": error_stats[0]['error_count'] if error_stats else 0}


@app.get("/api/graph-data")
async def get_graph_data():
    query = """
    MATCH (n)-[r]->(m)
    RETURN n.id as source_id, labels(n)[0] as source_label, n.name as source_name,
           m.id as target_id, labels(m)[0] as target_label, m.name as target_name,
           type(r) as edge_type
    """
    data = db.run_query(query)
    
    nodes = {}
    edges = []
    
    # 산업 현장 느낌의 색상 팔레트
    color_map = {
        "Center": {"background": "#FFC107", "border": "#FFA000"}, 
        "Zone": {"background": "#0277BD", "border": "#01579B"},
        "AGV": {"background": "#00C853", "border": "#00A844"},
        "Item": {"background": "#B0BEC5", "border": "#90A4AE"},
        "Event": {"background": "#D32F2F", "border": "#B71C1C"}
    }
    
    for row in data:
        s_id, s_lbl = row['source_id'], row['source_label']
        t_id, t_lbl = row['target_id'], row['target_label']
        
        if s_id not in nodes:
            nodes[s_id] = {
                "id": s_id, 
                "label": row.get('source_name', s_id),
                "group": s_lbl,
                "color": color_map.get(s_lbl, {})
            }
        if t_id not in nodes:
             nodes[t_id] = {
                "id": t_id, 
                "label": row.get('target_name', t_id),
                "group": t_lbl,
                "color": color_map.get(t_lbl, {})
            }
            
        edges.append({
            "from": s_id, 
            "to": t_id, 
            "label": row['edge_type'],
            "color": {"color": "#546E7A"},
            "arrows": "to"
        })
    
    return {"nodes": list(nodes.values()), "edges": edges}
