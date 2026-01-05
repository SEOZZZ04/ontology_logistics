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
        self.event_active = False
        self.current_event_type = None
        self.event_start_time = 0
        self.last_event_end_time = 0
        
        # 설정값
        self.MIN_EVENT_DURATION = 20.0 
        self.EVENT_COOLDOWN = 15.0
        
        # AGV 이동 소요 시간 (초) - 애니메이션 속도 결정
        self.AGV_TRAVEL_TIME = 3.0 

    async def start(self):
        self.is_running = True
        print("🚀 [Sim] 디지털 트윈 시뮬레이터 가동")
        while self.is_running:
            await self.tick()
            await asyncio.sleep(1.0) # 1초 단위 틱

    def stop(self):
        self.is_running = False

    async def tick(self):
        curr_time = time.time()
        
        # 1. 이벤트/장애물 관리 (기존 로직 유지)
        if self.event_active:
            if curr_time - self.event_start_time > self.MIN_EVENT_DURATION:
                if random.random() < 0.2: self.end_event()
        else:
            if curr_time - self.last_event_end_time > self.EVENT_COOLDOWN:
                if random.random() < 0.1: await self.trigger_random_event()

        is_error = (self.event_active and self.current_event_type == 'ERROR')
        
        # 2. 아이템 생성 (Inbound)
        spawn_rate = 0.8 if (self.event_active and self.current_event_type == 'PROMO') else 0.4
        if not is_error and random.random() < spawn_rate:
            await self.spawn_item()

        # 3. AGV 로직 (상태 기반 이동)
        if not is_error:
            # 이동 완료 체크 및 상태 업데이트
            await self.check_agv_movements(curr_time)
            
            # 새로운 작업 할당
            await self.assign_task('AGV_01', 'Z_IN', 'Z_SORT', curr_time)
            await self.assign_task('AGV_02', 'Z_SORT', 'Z_OUT', curr_time)

        # 4. 트럭 상차
        if random.random() < 0.2:
            await self.process_truck()

    async def spawn_item(self):
        item_id = f"BOX_{str(uuid.uuid4())[:4].upper()}"
        # 아이템 생성 시 시각적 효과를 위해 'CREATED' 상태 부여
        q = """
        MATCH (z:Zone {id: 'Z_IN'})
        CREATE (i:Item {id: $id, status: 'WAITING', timestamp: datetime()})
        CREATE (i)-[:STORED_IN]->(z)
        """
        db.run_query(q, {"id": item_id})

    async def assign_task(self, agv_id, src_id, dst_id, curr_time):
        # AGV가 IDLE 상태이고, 출발지에 물건이 있을 때만 이동 시작
        q_check = """
        MATCH (a:AGV {id: $agv_id})
        WHERE NOT (a)-[:MOVING_TO]->() -- 이동 중이 아닐 때
        MATCH (src:Zone {id: $src})
        MATCH (i:Item)-[:STORED_IN]->(src)
        WITH a, i, src LIMIT 1
        RETURN a.id, i.id as item_id
        """
        res = db.run_query(q_check, {"agv_id": agv_id, "src": src_id})
        
        if res:
            item_id = res[0]['item_id']
            # 이동 시작 (상태 변경: LOCATED_AT 삭제 -> MOVING_TO 관계 생성)
            # start_time을 기록하여 프론트엔드가 위치를 보간(Interpolation)하게 함
            q_move = """
            MATCH (a:AGV {id: $agv_id})-[l:LOCATED_AT]->(src:Zone {id: $src})
            MATCH (i:Item {id: $item_id})-[s:STORED_IN]->(src)
            MATCH (dst:Zone {id: $dst})
            DELETE l, s
            CREATE (a)-[:MOVING_TO {start_time: $now, duration: $dur}]->(dst)
            CREATE (i)-[:LOADED_ON]->(a)
            SET a.status = 'MOVING', i.status = 'TRANSIT'
            """
            db.run_query(q_move, {
                "agv_id": agv_id, "src": src_id, "dst": dst_id, "item_id": item_id,
                "now": curr_time, "dur": self.AGV_TRAVEL_TIME
            })

    async def check_agv_movements(self, curr_time):
        # 이동 중인 AGV 중 시간이 다 된 것들을 목적지에 도착 처리
        q_arrived = """
        MATCH (a:AGV)-[m:MOVING_TO]->(dst:Zone)
        WHERE $now >= m.start_time + m.duration
        MATCH (i:Item)-[l:LOADED_ON]->(a)
        DELETE m, l
        CREATE (a)-[:LOCATED_AT]->(dst)
        CREATE (i)-[:STORED_IN]->(dst)
        SET a.status = 'IDLE', i.status = 'ARRIVED'
        RETURN a.id
        """
        db.run_query(q_arrived, {"now": curr_time})

    async def process_truck(self):
        q_truck = """
        MATCH (z:Zone {id: 'Z_OUT'})
        MATCH (i:Item)-[r:STORED_IN]->(z)
        WITH i, r LIMIT 5
        DETACH DELETE i
        """
        db.run_query(q_truck)

    async def trigger_random_event(self):
        evt_type = "PROMO" if random.random() < 0.5 else "ERROR"
        desc = "🚀 [주문 폭주] 처리량 급증!" if evt_type == "PROMO" else "🚨 [설비 고장] 컨베이어 정지!"
        
        self.event_active = True
        self.current_event_type = evt_type
        self.event_start_time = time.time()
        
        evt_id = f"EVT_{str(uuid.uuid4())[:4]}"
        q = """
        MATCH (c:Center)
        CREATE (e:Event {id: $id, description: $desc, type: $type, timestamp: datetime()})
        MERGE (c)-[:HAS_EVENT]->(e)
        """
        db.run_query(q, {"id": evt_id, "desc": desc, "type": evt_type})

    def end_event(self):
        if self.current_event_type:
            db.run_query(f"MATCH (e:Event {{type: '{self.current_event_type}'}}) DETACH DELETE e")
        self.event_active = False
        self.current_event_type = None
        self.last_event_end_time = time.time()

simulator = LogisticsSimulator()
