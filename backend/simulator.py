import asyncio
import random
import uuid
import google.generativeai as genai
import os
from .database import db

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

async def get_embedding(text):
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
        )
        return result['embedding']
    except:
        return [0.0] * 768

class LogisticsSimulator:
    def __init__(self):
        self.is_running = False
        self.promotion_active = False
        self.error_active = False

    async def start(self):
        self.is_running = True
        print("🚀 [Sim] 시뮬레이션 가동! (순차 이동 모드)")
        while self.is_running:
            await self.tick()
            await asyncio.sleep(2.0) # 2초 단위 틱

    def stop(self):
        self.is_running = False

    async def tick(self):
        # 0. 상태 및 이벤트 확률 계산
        spawn_count = 0
        
        # [이벤트 로직] 생략 (기존과 동일하게 유지하거나 필요시 추가)
        # 프로모션 발생
        if not self.promotion_active and random.random() < 0.05:
            self.promotion_active = True
            await self.create_event("PROMO", "✨ 블랙프라이데이 세일 시작! 물량 폭주!")
        if self.promotion_active and random.random() < 0.1:
            self.promotion_active = False
            db.run_query("MATCH (e:Event {type: 'PROMO'}) DETACH DELETE e")

        # 장애 발생
        if not self.error_active and random.random() < 0.05:
            self.error_active = True
            await self.create_event("ERROR", "⚠️ 컨베이어 벨트 고장! 작업 지연!")
        if self.error_active and random.random() < 0.2:
            self.error_active = False
            db.run_query("MATCH (e:Event {type: 'ERROR'}) DETACH DELETE e")

        # === [핵심 수정] 실행 순서를 '역순'으로 변경하여 순간이동 방지 ===
        
        # 1. [출고 완료] (가장 마지막 단계부터 처리)
        db.run_query("""
        MATCH (i:Item)-[r:STORED_IN]->(z_out:Zone {id: 'Z_OUT'})
        WITH i LIMIT 5
        DETACH DELETE i
        """)

        # 2. [이동 로직] 분류 -> 출고 (장애 없을 때만)
        if not self.error_active:
            db.run_query("""
            MATCH (i:Item)-[r:STORED_IN]->(z_sort:Zone {id: 'Z_SORT'})
            MATCH (z_out:Zone {id: 'Z_OUT'})
            WITH i, r, z_out LIMIT 5
            DELETE r
            CREATE (i)-[:STORED_IN]->(z_out)
            """)

        # 3. [이동 로직] 입고 -> 분류 (장애 없을 때만)
        if not self.error_active:
            db.run_query("""
            MATCH (i:Item)-[r:STORED_IN]->(z_in:Zone {id: 'Z_IN'})
            MATCH (z_sort:Zone {id: 'Z_SORT'})
            WITH i, r, z_sort LIMIT 5
            DELETE r
            CREATE (i)-[:STORED_IN]->(z_sort)
            """)

        # 4. [입고 생성] (가장 처음에 생성)
        if self.error_active:
            spawn_count = 0
        elif self.promotion_active:
            spawn_count = random.randint(3, 6)
        else:
            spawn_count = random.randint(1, 2)

        for _ in range(spawn_count):
            item_id = f"ITM_{str(uuid.uuid4())[:4]}"
            # Item 노드 생성 (Zone에 연결)
            q = """
            MATCH (z:Zone {id: 'Z_IN'})
            CREATE (i:Item {id: $id, type: 'Normal', timestamp: datetime()})
            CREATE (i)-[:STORED_IN]->(z)
            """
            db.run_query(q, {"id": item_id})

    async def create_event(self, type, desc):
        vec = await get_embedding(desc)
        evt_id = f"EVT_{str(uuid.uuid4())[:4]}"
        q = """
        MATCH (c:Center)
        CREATE (e:Event {id: $id, description: $desc, type: $type, timestamp: datetime()})
        SET e.embedding = $vec
        MERGE (c)-[:HAS_EVENT]->(e)
        """
        db.run_query(q, {"id": evt_id, "desc": desc, "type": type, "vec": vec})

simulator = LogisticsSimulator()
