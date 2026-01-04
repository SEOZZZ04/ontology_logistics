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
    except Exception as e:
        print(f"Embedding Error: {e}")
        return [0.0] * 768

class LogisticsSimulator:
    def __init__(self):
        self.is_running = False
        self.promotion_active = False # 프로모션 상태 플래그

    async def start(self):
        self.is_running = True
        print("🚀 [Sim] 시뮬레이션 가동! (Flow: IN -> SORT -> OUT)")
        while self.is_running:
            await self.tick()
            await asyncio.sleep(2) # 2초마다 갱신 (속도 업)

    def stop(self):
        self.is_running = False

    async def tick(self):
        # 1. [프로모션] 랜덤 발생 (5% 확률)
        if not self.promotion_active and random.random() < 0.05:
            self.promotion_active = True
            evt_id = f"PROMO_{str(uuid.uuid4())[:4]}"
            desc = "🔥 블랙프라이데이 긴급 프로모션 시작! 주문 폭주!"
            print(f"✨ {desc}")
            
            vec = await get_embedding(desc)
            # 프로모션 노드 생성 및 센터 연결
            q = """
            MATCH (c:Center)
            CREATE (e:Event {id: $id, description: $desc, type: 'PROMOTION', timestamp: datetime()})
            SET e.embedding = $vec
            MERGE (c)-[:HAS_EVENT]->(e)
            """
            db.run_query(q, {"id": evt_id, "desc": desc, "vec": vec})

        # 프로모션 중이면 물량 3배, 종료 확률 10%
        spawn_rate = 0.8 if self.promotion_active else 0.3
        if self.promotion_active and random.random() < 0.1:
            self.promotion_active = False
            print("END 프로모션 종료.")
            db.run_query("MATCH (e:Event {type: 'PROMOTION'}) DETACH DELETE e")

        # 2. [입고] 물건 생성 (Spawn)
        if random.random() < spawn_rate:
            # 한 번에 1~3개씩 입고
            for _ in range(random.randint(1, 3)):
                item_id = f"ITEM_{str(uuid.uuid4())[:4]}"
                q = """
                MATCH (z:Zone {id: 'Z_IN'})
                CREATE (i:Item {id: $id, type: 'Normal', timestamp: datetime()})
                CREATE (i)-[:STORED_IN]->(z)
                """
                db.run_query(q, {"id": item_id})

        # 3. [이동] 입고존 -> 분류존 (Flow)
        # AGV가 없어도 컨베이어처럼 자동 이동시킴 (시각적 흐름 위해)
        q_move_1 = """
        MATCH (i:Item)-[r:STORED_IN]->(from:Zone {id: 'Z_IN'})
        MATCH (to:Zone {id: 'Z_SORT'})
        WITH i, r, to LIMIT 3
        DELETE r
        CREATE (i)-[:STORED_IN]->(to)
        """
        db.run_query(q_move_1)

        # 4. [이동] 분류존 -> 출고존 (Flow)
        q_move_2 = """
        MATCH (i:Item)-[r:STORED_IN]->(from:Zone {id: 'Z_SORT'})
        MATCH (to:Zone {id: 'Z_OUT'})
        WITH i, r, to LIMIT 3
        DELETE r
        CREATE (i)-[:STORED_IN]->(to)
        """
        db.run_query(q_move_2)

        # 5. [출고] 배송 완료 (데이터 삭제)
        # 계속 쌓이면 그래프 터지므로 출고존에서 사라지게 처리
        q_ship = """
        MATCH (i:Item)-[r:STORED_IN]->(z:Zone {id: 'Z_OUT'})
        WITH i LIMIT 2
        DETACH DELETE i
        """
        db.run_query(q_ship)

        # 6. [장애] 랜덤 장애 발생 (3% 확률)
        if random.random() < 0.03:
            evt_id = f"ERR_{str(uuid.uuid4())[:4]}"
            desc = random.choice([
                "⚠️ 분류기 모터 과열 경고",
                "⚠️ 입고존 바코드 스캐너 인식 실패",
                "⚠️ AGV-02 경로 이탈 발생"
            ])
            print(f"🚨 {desc}")
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
