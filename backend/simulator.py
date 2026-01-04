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

    async def start(self):
        self.is_running = True
        print("🚀 [Sim] 시뮬레이션 가동! (당근 테마 적용)")
        while self.is_running:
            await self.tick()
            await asyncio.sleep(1.5) # 속도 조절

    def stop(self):
        self.is_running = False

    async def tick(self):
        # 1. [프로모션]
        if not self.promotion_active and random.random() < 0.05:
            self.promotion_active = True
            evt_id = f"PROMO_{str(uuid.uuid4())[:4]}"
            desc = "🥕 당근마켓 지역 직거래 페스티벌! 물량 급증!"
            print(f"✨ {desc}")
            vec = await get_embedding(desc)
            
            # 이벤트 노드 생성 (Zone 전체에 영향)
            q = """
            MATCH (c:Center)
            MERGE (e:Event {id: $id, description: $desc, type: 'PROMOTION', timestamp: datetime()})
            SET e.embedding = $vec
            MERGE (c)-[:HAS_EVENT]->(e)
            """
            db.run_query(q, {"id": evt_id, "desc": desc, "vec": vec})

        if self.promotion_active and random.random() < 0.1:
            self.promotion_active = False
            db.run_query("MATCH (e:Event {type: 'PROMOTION'}) DETACH DELETE e")

        # 2. [입고] 물량 투입 (DB에는 넣되, 그래프 시각화는 제외할 것임)
        spawn_count = random.randint(3, 8) if self.promotion_active else random.randint(1, 3)
        for _ in range(spawn_count):
            item_id = f"ITM_{str(uuid.uuid4())[:4]}"
            q = """
            MATCH (z:Zone {id: 'Z_IN'})
            CREATE (i:Item {id: $id, type: 'Normal', timestamp: datetime()})
            CREATE (i)-[:STORED_IN]->(z)
            """
            db.run_query(q, {"id": item_id})

        # 3. [이동] 입고 -> 분류
        db.run_query("""
        MATCH (i:Item)-[r:STORED_IN]->(from:Zone {id: 'Z_IN'})
        MATCH (to:Zone {id: 'Z_SORT'})
        WITH i, r, to LIMIT 5
        DELETE r
        CREATE (i)-[:STORED_IN]->(to)
        """)

        # 4. [이동] 분류 -> 출고
        db.run_query("""
        MATCH (i:Item)-[r:STORED_IN]->(from:Zone {id: 'Z_SORT'})
        MATCH (to:Zone {id: 'Z_OUT'})
        WITH i, r, to LIMIT 5
        DELETE r
        CREATE (i)-[:STORED_IN]->(to)
        """)

        # 5. [배송완료] 출고존에서 삭제 (속도 조절: 쌓이게 둠)
        db.run_query("""
        MATCH (i:Item)-[r:STORED_IN]->(z:Zone {id: 'Z_OUT'})
        WITH i LIMIT 3
        DETACH DELETE i
        """)

        # 6. [장애]
        if random.random() < 0.05:
            evt_id = f"ERR_{str(uuid.uuid4())[:4]}"
            desc = random.choice([
                "⚠️ 분류기 벨트 끼임", "⚠️ 지게차 배터리 방전", "⚠️ 포장지 부족 알림"
            ])
            vec = await get_embedding(desc)
            q = """
            MATCH (z:Zone) WHERE z.name IN ['분류존', '입고존']
            WITH z, rand() AS r ORDER BY r LIMIT 1
            CREATE (e:Event {id: $id, description: $desc, type: 'ERROR', timestamp: datetime()})
            SET e.embedding = $vec
            CREATE (e)-[:AFFECTS]->(z)
            """
            db.run_query(q, {"id": evt_id, "desc": desc, "vec": vec})

simulator = LogisticsSimulator()
