from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio
import os
import json
import google.generativeai as genai
from neo4j_manager import Neo4jManager
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()

# --- 설정 및 초기화 ---
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

db = Neo4jManager()

# 전역 시뮬레이션 상태
sim_state = {
    "traffic_level": 1.0,
    "events": []
}

# --- 백그라운드 시뮬레이터 ---
async def run_simulation_loop():
    print("🚀 [System] Simulation Engine Started")
    while True:
        try:
            # 1. 시뮬레이션 물리 엔진 가동 (이동, 배터리 소모)
            db.update_simulation_step(traffic_level=sim_state["traffic_level"])
            
            # 2. 랜덤 이벤트 생성기 (쇼핑몰 연동 시늉)
            import random
            if random.random() < 0.02: # 2% 확률로 이벤트 발생
                if sim_state["traffic_level"] == 1.0:
                    evt_title = "⚡ 깜짝 타임세일 시작!"
                    evt_desc = "주문량 300% 폭증 예상"
                    sim_state["traffic_level"] = 3.0
                    sim_state["events"].insert(0, {"title": evt_title, "desc": evt_desc, "type": "warning"})
                    db.inject_event("PROMOTION", "Traffic Surge")
                else:
                    evt_title = "✅ 세일 종료"
                    evt_desc = "물동량 정상화"
                    sim_state["traffic_level"] = 1.0
                    sim_state["events"].insert(0, {"title": evt_title, "desc": evt_desc, "type": "info"})
            
            # 이벤트 로그는 최근 10개만 유지
            if len(sim_state["events"]) > 10:
                sim_state["events"] = sim_state["events"][:10]
                
            await asyncio.sleep(1.5) # 1.5초마다 갱신
        except Exception as e:
            print(f"⚠️ Sim Error: {e}")
            await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_ontology() # 서버 시작 시 온톨로지 리셋
    task = asyncio.create_task(run_simulation_loop())
    yield
    task.cancel()
    db.close()

app = FastAPI(lifespan=lifespan)

# CORS 설정 (프론트엔드 통신 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API 엔드포인트 ---

@app.get("/api/dashboard")
def get_dashboard():
    """프론트엔드가 1초마다 호출: 그래프 데이터 + 이벤트 로그"""
    data = db.get_dashboard_data()
    return {
        "graph": data,
        "events": sim_state["events"],
        "traffic_level": sim_state["traffic_level"]
    }

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat_agent(req: ChatRequest):
    """
    RAG Agent: 현재 그래프 상황을 컨텍스트로 주입받아 답변하고,
    시각화를 위해 관련된 노드 ID를 추출하여 반환함.
    """
    # 1. 현재 상황 스냅샷 가져오기
    context_data = db.get_context_for_llm()
    
    # 2. 시스템 프롬프트 구성 (Toss 스타일 페르소나)
    system_prompt = f"""
    당신은 최첨단 물류센터 관제 AI입니다. 
    현재 물류센터 상황 데이터: {json.dumps(context_data, ensure_ascii=False)}
    
    [지시사항]
    1. 사용자의 질문에 대해 위 데이터를 근거로 답변하세요.
    2. 말투는 '토스(Toss)' 앱처럼 정중하고, 간결하고, 명확하게 하세요. (예: "~입니다", "~확인되었습니다")
    3. 답변과 직접적으로 관련된 온톨로지 노드 ID가 있다면 반드시 추출하세요.
    
    [출력 형식]
    반드시 아래 JSON 포맷으로만 응답하세요. 마크다운 쓰지 마세요.
    {{
        "reply": "사용자에게 할 답변 내용",
        "related_nodes": ["관련된_노드ID_1", "관련된_노드ID_2"]
    }}
    """
    
    try:
        response = model.generate_content(f"{system_prompt}\n사용자 질문: {req.message}")
        # JSON 파싱 (Gemini가 가끔 마크다운 ```json ... ```을 붙일 수 있음)
        text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"LLM Error: {e}")
        return {
            "reply": "죄송합니다. 현재 AI 연결 상태가 불안정하여 답변을 생성할 수 없습니다.", 
            "related_nodes": []
        }

# 정적 파일 서빙 (배포 시 React 빌드 파일 연결)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
