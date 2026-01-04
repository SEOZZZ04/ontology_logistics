import asyncio
import random
import uuid
import time
import os
import google.generativeai as genai
from .database import db

# API 키 설정 (없으면 에러 방지 처리)
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
except:
    pass

class LogisticsSimulator:
    def __init__(self):
        self.is_running = False
        
        # 이벤트 제어 변수
        self.event_active = False      # 현재 이벤트 진행 여부
        self.current_event_type = None # PROMO or ERROR
        self.event_start_time = 0
        self.last_event_end_time = 0   # 마지막 이벤트가 끝난 시간 (쿨다운용)
        
        # 설정값
        self.MIN_EVENT_DURATION = 20.0 # 이벤트 최소 지속 시간 (초)
        self.EVENT_COOLDOWN = 15.0     # 이벤트 종료 후 다음 이벤트까지 대기 시간 (초)

    async def start(self):
        self.is_running = True
        print("🚀 [Sim] 풀 사이클 물류 시뮬레이터 가동 (In -> Sort -> Out -> Truck)")
        while self.is_running:
            await self.tick()
            await asyncio.sleep(1.5) # 1.5초 틱 (너무 빠르지 않게)

    def stop(self):
        self.is_running = False

    async def tick(self):
        curr_time = time.time()
        
        # ==========================================
        # 1. 이벤트 라이프사이클 관리 (20초 유지 & 쿨다운)
        # ==========================================
        if self.event_active:
            # 이벤트 진행 중: 20초 지났는지 확인
            duration = curr_time - self.event_start_time
            if duration > self.MIN_EVENT_DURATION:
                # 20초 지남 -> 20% 확률로 종료 (자연스러운 종료 유도)
                if random.random() < 0.2:
                    self.end_event()
        else:
            # 이벤트 없음: 쿨다운 체크
            time_since_last = curr_time - self.last_event_end_time
            if time_since_last > self.EVENT_COOLDOWN:
                # 쿨다운 지남 -> 10% 확률로 새 이벤트 발생
                if random.random() < 0.1:
                    await self.trigger_random_event()

        # ==========================================
        # 2. 물류 흐름 (장애 발생 시 AGV 멈춤)
        # ==========================================
        is_error = (self.event_active and self.current_event_type == 'ERROR')
        
        # [Step 1] 입고 (Inbound) 생성
        # 프로모션이면 많이, 평시면 적당히, 장애면 중단
        spawn_rate = 0
        if self.event_active and self.current_event_type == 'PROMO':
            spawn_rate = 0.8 # 80% 확률로 생성
        elif not is_error:
            spawn_rate = 0.4 # 40% 확률
        
        if random.random() < spawn_rate:
            await self.spawn_item()

        # [Step 2 & 3] AGV 이동 (Pick & Place)
        if not is_error:
            # AGV_01: In -> Sort
            await self.process_agv('AGV_01', 'Z_IN', 'Z_SORT')
            # AGV_02: Sort -> Out
            await self.process_agv('AGV_02', 'Z_SORT', 'Z_OUT')

        # [Step 4] 트럭 상차 (Truck Loading)
        # 트럭은 주기적으로 와서 Z_OUT에 있는걸 다 가져감
        if random.random() < 0.3: # 30% 확률로 트럭 도착
            await self.process_truck()

    async def spawn_item(self):
        item_id = f"BOX_{str(uuid.uuid4())[:4].upper()}"
        q = """
        MATCH (z:Zone {id: 'Z_IN'})
        CREATE (i:Item {id: $id, status: 'WAITING', timestamp: datetime()})
        CREATE (i)-[:STORED_IN]->(z)
        """
        db.run_query(q, {"id": item_id})

    async def process_agv(self, agv_id, src_zone, dst_zone):
        # 1. AGV가 물건을 들고 있는지 확인
        q_check = """
        MATCH (a:AGV {id: $agv_id})
        OPTIONAL MATCH (i:Item)-[:LOADED_ON]->(a)
        RETURN i.id as item_id
        """
        res = db.run_query(q_check, {"agv_id": agv_id})
        carrying_item = res[0]['item_id'] if res else None

        if carrying_item:
            # [Place] 목적지에 내려놓기
            q_drop = """
            MATCH (a:AGV {id: $agv_id})
            MATCH (i:Item)-[r:LOADED_ON]->(a)
            MATCH (z:Zone {id: $dst})
            DELETE r
            CREATE (i)-[:STORED_IN]->(z)
            SET i.status = 'ARRIVED'
            """
            db.run_query(q_drop, {"agv_id": agv_id, "dst": dst_zone})
        else:
            # [Pick] 출발지에서 하나 집기 (FIFO)
            q_pick = """
            MATCH (z:Zone {id: $src})
            MATCH (i:Item)-[r:STORED_IN]->(z)
            WITH i, r, z ORDER BY i.timestamp ASC LIMIT 1
            MATCH (a:AGV {id: $agv_id})
            DELETE r
            CREATE (i)-[:LOADED_ON]->(a)
            SET i.status = 'MOVING'
            """
            db.run_query(q_pick, {"agv_id": agv_id, "src": src_zone})

    async def process_truck(self):
        # Z_OUT에 있는 아이템들을 삭제 (트럭 출발)
        q_truck = """
        MATCH (z:Zone {id: 'Z_OUT'})
        MATCH (i:Item)-[r:STORED_IN]->(z)
        WITH i, r LIMIT 5
        DETACH DELETE i
        """
        db.run_query(q_truck)

    async def trigger_random_event(self):
        # 프로모션 vs 장애 반반
        evt_type = "PROMO" if random.random() < 0.5 else "ERROR"
        desc = "✨ 주문 폭주! 물량 급증!" if evt_type == "PROMO" else "⚠️ 컨베이어 벨트 고장! 작업 중단!"
        
        self.event_active = True
        self.current_event_type = evt_type
        self.event_start_time = time.time()
        
        # DB에 이벤트 노드 생성
        vec = [0.0] * 768 # 임베딩은 생략하거나 더미값
        evt_id = f"EVT_{str(uuid.uuid4())[:4]}"
        q = """
        MATCH (c:Center)
        CREATE (e:Event {id: $id, description: $desc, type: $type, timestamp: datetime()})
        MERGE (c)-[:HAS_EVENT]->(e)
        """
        db.run_query(q, {"id": evt_id, "desc": desc, "type": evt_type})
        print(f"🔥 이벤트 발생: {evt_type}")

    def end_event(self):
        print(f"🏁 이벤트 종료: {self.current_event_type}")
        # DB에서 이벤트 삭제
        if self.current_event_type:
            db.run_query(f"MATCH (e:Event {{type: '{self.current_event_type}'}}) DETACH DELETE e")
        
        self.event_active = False
        self.current_event_type = None
        self.last_event_end_time = time.time()

simulator = LogisticsSimulator()
