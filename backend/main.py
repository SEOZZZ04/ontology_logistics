from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
from contextlib import asynccontextmanager

from .database import db
from .simulator import simulator
from .agent import query_agent

# 앱 시작/종료 시 실행될 로직
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시
    db.init_schema()  # 스키마 생성
    db.seed_data()    # 기초 데이터 생성
    asyncio.create_task(simulator.start()) # 시뮬레이터 가동
    yield
    # 종료 시
    simulator.stop()
    db.close()

app = FastAPI(lifespan=lifespan)

# CORS 설정 (프론트엔드 통신용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 서빙 (프론트엔드)
app.mount("/ui", StaticFiles(directory="frontend", html=True), name="ui")

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat(req: ChatRequest):
    response = await query_agent(req.message)
    return {"reply": response}

@app.get("/api/graph-data")
async def get_graph_data():
    # 시각화를 위한 전체 노드/엣지 데이터 반환
    query = """
    MATCH (n)-[r]->(m)
    RETURN n.id as source_id, labels(n)[0] as source_label, 
           m.id as target_id, labels(m)[0] as target_label, 
           type(r) as edge_type
    """
    data = db.run_query(query)
    
    # vis.js 포맷으로 변환
    nodes = set()
    edges = []
    for row in data:
        # 노드 색상 지정
        color_map = {"Center": "#ff9900", "Zone": "#97c2fc", "AGV": "#fb7e81", "Item": "#7be141", "Event": "#ff0000"}
        
        nodes.add((row['source_id'], row['source_label'], color_map.get(row['source_label'], '#ccc')))
        nodes.add((row['target_id'], row['target_label'], color_map.get(row['target_label'], '#ccc')))
        edges.append({"from": row['source_id'], "to": row['target_id'], "label": row['edge_type']})
    
    node_list = [{"id": n[0], "label": f"{n[1]}\n{n[0]}", "color": n[2]} for n in list(nodes)]
    
    return {"nodes": node_list, "edges": edges}

@app.get("/")
def read_root():
    return {"message": "Logistics AI Agent Running. Go to /ui/index.html"}
