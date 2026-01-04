import asyncio
import random
import uuid
import time
import os
import google.generativeai as genai
from .database import db

# 모델명 안전하게 설정
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
        
        # 이벤트 상태 관리
        self.promotion_active = False
        self.error_active = False
        self.promo_start_time = 0
        self.error_start_time = 0
        
        # 최소 유지 시간 (초)
        self.MIN_DURATION = 20.0

    async def start(self):
        self.is_running = True
        print("🚀 [Sim] 시뮬레이션 고도화 가동! (AGV 운송 모드)")
        while self.is_running:
            await self.tick()
            await asyncio.sleep(2.0) # 2초 단위 틱

    def stop(self):
        self.is_running = False

    async def tick(self):
        curr_time = time.time()
        
        # ==========================================
        # 1. 이벤트 로직 (최소 시간 보장 적용)
        # ==========================================
        
        # [프로모션]
        if self.promotion_active:
            # 20초가 지났고, 10% 확률로 종료
            if (curr_time - self.promo_start_time > self.MIN_DURATION) and random.random() < 0.1:
                self.promotion_active = False
                db.run_query("MATCH (e:Event {type: 'PROMO'}) DETACH DELETE e")
                print("✨ 프로모션 종료")
        else:
            # 2% 확률로 시작 (빈도 낮춤)
            if random.random() < 0.02:
                self.promotion_active = True
                self.promo_start_time = curr_time
                await self.create_event("PROMO", "✨ 반짝 세일! 주문량 급증!")
                print("✨ 프로모션 시작!")

        # [장애]
        if self.error_active:
            # 20초가 지났고, 15% 확률로 해결
            if (curr_time - self.error_start_time > self.MIN_DURATION) and random.random() < 0.15:
                self.error_active = False
                db.run_query("MATCH (e:Event {type: 'ERROR'}) DETACH DELETE e")
                print("✅ 장애 해결")
        else:
            # 3% 확률로 발생
            if random.random() < 0.03:
                self.error_active = True
                self.error_start_time = curr_time
                await self.create_event("ERROR", "⚠️ AGV 통신 오류 발생! 작업 지연!")
                print("⚠️ 장애 발생!")

        # ==========================================
        # 2. AGV 운송 로직 (Pick & Place)
        # ==========================================
        # 장애 상태가 아닐 때만 AGV 가동
        if not self.error_active:
            # (1) AGV_01: 입고(Z_IN) -> 분류(Z_SORT)
            await self.process_agv_step('AGV_01', 'Z_IN', 'Z_SORT')
            
            # (2) AGV_02: 분류(Z_SORT) -> 출고(Z_OUT)
            await self.process_agv_step('AGV_02', 'Z_SORT', 'Z_OUT')

        # ==========================================
        # 3. 출고 처리 (Z_OUT에 있는 물건 삭제)
        # ==========================================
        db.run_query("""
        MATCH (i:Item)-[r:STORED_IN]->(z:Zone {id: 'Z_OUT'})
        WITH i LIMIT 3
        DETACH DELETE i
        """)

        # ==========================================
        # 4. 신규 입고 (Z_IN 생성)
        # ==========================================
        spawn_count = 0
        if self.error_active:
            spawn_count = 0
        elif self.promotion_active:
            spawn_count = random.randint(2, 4)
        else:
            spawn_count = random.randint(0, 2) # 평시 물량 조절

        for _ in range(spawn_count):
            item_id = f"BOX_{str(uuid.uuid4())[:4].upper()}"
            q = """
            MATCH (z:Zone {id: 'Z_IN'})
            CREATE (i:Item {id: $id, type: 'Normal', timestamp: datetime()})
            CREATE (i)-[:STORED_IN]->(z)
            """
            db.run_query(q, {"id": item_id})

    async def process_agv_step(self, agv_id, src_zone, dst_zone):
        """
        AGV가 물건을 집거나(Pick), 내려놓는(Place) 로직
        """
        # 1. AGV가 현재 물건을 들고 있는지 확인
        q_check = """
        MATCH (a:AGV {id: $agv_id})
        OPTIONAL MATCH (i:Item)-[:LOADED_ON]->(a)
        RETURN i.id as item_id
        """
        res = db.run_query(q_check, {"agv_id": agv_id})
        current_item = res[0]['item_id'] if res else None

        if current_item:
            # [Place] 물건을 목적지에 내려놓음
            q_drop = """
            MATCH (a:AGV {id: $agv_id})
            MATCH (i:Item)-[r:LOADED_ON]->(a)
            MATCH (z_dest:Zone {id: $dest})
            DELETE r
            CREATE (i)-[:STORED_IN]->(z_dest)
            """
            db.run_query(q_drop, {"agv_id": agv_id, "dest": dst_zone})
        else:
            # [Pick] 출발지에서 물건을 집음 (FIFO)
            q_pick = """
            MATCH (z_src:Zone {id: $src})
            MATCH (i:Item)-[r:STORED_IN]->(z_src)
            MATCH (a:AGV {id: $agv_id})
            WITH i, r, a ORDER BY i.timestamp ASC LIMIT 1
            DELETE r
            CREATE (i)-[:LOADED_ON]->(a)
            """
            db.run_query(q_pick, {"agv_id": agv_id, "src": src_zone})

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
