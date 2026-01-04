import asyncio
import random
import uuid
import google.generativeai as genai
import os
from .database import db

# 임베딩 생성을 위한 설정
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

async def get_embedding(text):
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_document",
    )
    return result['embedding']

class LogisticsSimulator:
    def __init__(self):
        self.is_running = False

    async def start(self):
        self.is_running = True
        print("🚀 [Sim] 시뮬레이션 시작!")
        while self.is_running:
            await self.tick()
            await asyncio.sleep(5)  # 5초마다 상태 변화

    def stop(self):
        self.is_running = False
        print("🛑 [Sim] 시뮬레이션 중지.")

    async def tick(self):
        # 1. 랜덤 이벤트: 물건 입고
        if random.random() < 0.4:
            item_id = f"ITEM_{str(uuid.uuid4())[:4]}"
            print(f"📦 [Sim] 물건 입고: {item_id}")
            query = """
            MATCH (z:Zone {id: 'Z_IN'})
            CREATE (i:Item {id: $id, type: 'Normal'})
            CREATE (i)-[:STORED_IN]->(z)
            """
            db.run_query(query, {"id": item_id})

        # 2. 랜덤 이벤트: AGV 이동 (입고 -> 분류)
        if random.random() < 0.3:
            print("🤖 [Sim] AGV 이동 중...")
            query = """
            MATCH (a:AGV)-[r:LOCATED_AT]->(from:Zone)-[:CONNECTED_TO]->(to:Zone)
            WHERE a.status = 'IDLE'
            WITH a, r, to LIMIT 1
            DELETE r
            CREATE (a)-[:LOCATED_AT]->(to)
            """
            db.run_query(query)

        # 3. 중요: 장애 발생 (Vector RAG용 데이터 생성)
        if random.random() < 0.1: # 10% 확률
            event_id = f"EVT_{str(uuid.uuid4())[:4]}"
            desc = random.choice([
                "AGV 1번 모터 과열로 인한 속도 저하",
                "분류존 센서 오작동으로 인한 물량 적체",
                "입고존 바닥 미끄러짐 사고 발생",
                "네트워크 지연으로 인한 명령 수신 실패"
            ])
            print(f"🚨 [Sim] 장애 발생: {desc}")
            
            # Gemini로 임베딩 생성
            vector = await get_embedding(desc)
            
            query = """
            CREATE (e:Event {id: $id, description: $desc, timestamp: datetime()})
            SET e.embedding = $vector
            WITH e
            MATCH (z:Zone) WHERE z.name IN ['입고존', '분류존'] 
            WITH e, z LIMIT 1 
            CREATE (e)-[:AFFECTS]->(z)
            """
            db.run_query(query, {"id": event_id, "desc": desc, "vector": vector})

simulator = LogisticsSimulator()
