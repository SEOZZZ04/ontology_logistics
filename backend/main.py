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
    # 정확한 물량 집계
    q1 = """
    MATCH (z:Zone)
    OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
    RETURN z.id as id, z.name as name, count(i) as count ORDER BY z.id
    """
    zone_stats = db.run_query(q1)
    
    # 최근 이벤트
    q2 = """
    MATCH (e:Event)
    RETURN e.id as id, e.description as desc, e.type as type
    ORDER BY e.timestamp DESC LIMIT 5
    """
    events = db.run_query(q2)
    return {"zones": zone_stats, "events": events}

@app.get("/api/graph-data")
async def get_graph_data():
    # [핵심] Item 제외, 모든 노드 조회. 
    # 관계가 없어도 노드는 리턴 (OPTIONAL MATCH)
    query = """
    MATCH (n) WHERE NOT 'Item' IN labels(n)
    OPTIONAL MATCH (n)-[r]->(m) WHERE NOT 'Item' IN labels(m)
    RETURN n.id as source_id, labels(n)[0] as source_label, n.name as source_name, n.type as source_type,
           m.id as target_id, labels(m)[0] as target_label, m.name as target_name, m.type as target_type,
           type(r) as edge_type
    """
    data = db.run_query(query)
    
    nodes = {}
    edges = []
    
    color_map = {
        "Center": "#FF6F00", "Zone": "#FF8F00", "AGV": "#00897B",
        "Event_ERROR": "#D32F2F", "Event_PROMO": "#7B1FA2"
    }
    
    for row in data:
        # Source Node
        s_id = row['source_id']
        s_lbl = row['source_label']
        s_key = f"{s_lbl}_{row.get('source_type', '')}" if s_lbl == 'Event' else s_lbl
        
        nodes[s_id] = {
            "id": s_id, "label": row.get('source_name', s_id), "group": s_lbl,
            "color": color_map.get(s_key, "#90A4AE"), "font": {"color": "#fff" if s_lbl=="Event" else "#000"}
        }

        # Target Node
        if row['target_id']:
            t_id = row['target_id']
            t_lbl = row['target_label']
            t_key = f"{t_lbl}_{row.get('target_type', '')}" if t_lbl == 'Event' else t_lbl

            nodes[t_id] = {
                "id": t_id, "label": row.get('target_name', t_id), "group": t_lbl,
                "color": color_map.get(t_key, "#90A4AE")
            }
            
            edge_key = f"{s_id}-{t_id}"
            if not any(e['id'] == edge_key for e in edges):
                edges.append({
                    "id": edge_key, "from": s_id, "to": t_id, "label": row['edge_type'],
                    "arrows": "to", "color": {"color": "#CFD8DC"}
                })
    
    return {"nodes": list(nodes.values()), "edges": edges}
