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
    # 시작 시 DB 초기화 -> 스키마 설정 -> 기초 데이터 -> 시뮬레이터 ON
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
    # 1. 구역별 물동량 (Item Count)
    q1 = """
    MATCH (z:Zone)
    OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
    RETURN z.name as name, count(i) as count ORDER BY z.id
    """
    zone_stats = db.run_query(q1)
    
    # 2. 이벤트 현황 (장애 & 프로모션)
    q2 = """
    MATCH (e:Event)
    RETURN 
        sum(CASE WHEN e.type = 'ERROR' THEN 1 ELSE 0 END) as error_count,
        sum(CASE WHEN e.type = 'PROMOTION' THEN 1 ELSE 0 END) as promo_count,
        collect(e.description) as recent_events
    """
    evt_stats = db.run_query(q2)
    stats = evt_stats[0] if evt_stats else {'error_count': 0, 'promo_count': 0, 'recent_events': []}
    
    return {
        "zones": zone_stats, 
        "errors": stats['error_count'],
        "promotions": stats['promo_count'],
        "recent_events": stats['recent_events']
    }

@app.get("/api/graph-data")
async def get_graph_data():
    query = """
    MATCH (n)-[r]->(m)
    RETURN n.id as source_id, labels(n)[0] as source_label, n.name as source_name, n.type as source_type,
           m.id as target_id, labels(m)[0] as target_label, m.name as target_name, m.type as target_type,
           type(r) as edge_type
    """
    data = db.run_query(query)
    
    nodes = {}
    edges = []
    
    # 색상 팔레트 (프로모션 추가)
    color_map = {
        "Center": "#FFC107", 
        "Zone": "#0277BD",
        "AGV": "#00C853",
        "Item": "#B0BEC5",
        "Event_ERROR": "#D32F2F",     # 장애: 빨강
        "Event_PROMOTION": "#9C27B0"  # 프로모션: 보라
    }
    
    for row in data:
        # Source Node 처리
        s_id = row['source_id']
        s_label = row['source_label']
        # 이벤트의 경우 타입(ERROR/PROMOTION)에 따라 색상 분기
        s_color_key = f"{s_label}_{row.get('source_type', '')}" if s_label == 'Event' else s_label
        
        if s_id not in nodes:
            nodes[s_id] = {
                "id": s_id, 
                "label": row.get('source_name', s_id),
                "group": s_label,
                "color": color_map.get(s_color_key, color_map.get(s_label, "#999"))
            }

        # Target Node 처리
        t_id = row['target_id']
        t_label = row['target_label']
        t_color_key = f"{t_label}_{row.get('target_type', '')}" if t_label == 'Event' else t_label

        if t_id not in nodes:
             nodes[t_id] = {
                "id": t_id, 
                "label": row.get('target_name', t_id),
                "group": t_label,
                "color": color_map.get(t_color_key, color_map.get(t_label, "#999"))
            }
            
        edges.append({
            "from": s_id, "to": t_id, 
            "color": {"color": "#546E7A", "opacity": 0.4}
        })
    
    return {"nodes": list(nodes.values()), "edges": edges}
