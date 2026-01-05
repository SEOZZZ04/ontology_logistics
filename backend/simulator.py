import asyncio
import random
import uuid
import time
import os
import google.generativeai as genai
from .database import db

try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
except:
    pass

class LogisticsSimulator:
    def __init__(self):
        self.is_running = False
        
        # 이벤트 제어
        self.event_active = False
        self.current_event_type = None
        self.event_start_time = 0
        self.last_event_end_time = 0
        
        # 설정값
        self.MIN_EVENT_DURATION = 15.0 
        self.EVENT_COOLDOWN = 10.0
        self.AGV_TRAVEL_TIME = 2.0  # AGV 이동 속도 (초)
        self.TRUCK_CYCLE_TIME = 8.0 # 트럭 체류 시간

    async def start(self):
        self.is_running = True
        print("🚀 [Sim] 시뮬레이터 무한 루프 시작")
        while self.is_running:
            try:
                await self.tick()
            except Exception as e:
                print(f"⚠️ [Sim Error] Tick 중 오류 발생 (자동 복구): {e}")
            await asyncio.sleep(1.0)

    def stop(self):
        self.is_running = False

    async def tick(self):
        curr_time = time.time()
        
        # 1. 이벤트 라이프사이클 (프로모션 / 장애)
        if self.event_active:
            if curr_time - self.event_start_time > self.MIN_EVENT_DURATION:
                if random.random() < 0.3: self.end_event()
        else:
            if curr_time - self.last_event_end_time > self.EVENT_COOLDOWN:
                # 20% 확률로 이벤트 발생
                if random.random() < 0.2: await self.trigger_random_event()

        is_error = (self.event_active and self.current_event_type == 'ERROR')
        is_promo = (self.event_active and self.current_event_type == 'PROMO')
        
        # 2. 입고 (Inbound) - 프로모션 시 대량 발생
        spawn_prob = 0.9 if is_promo else 0.4
        if not is_error and random.random() < spawn_prob:
            # 프로모션이면 한 번에 여러 개 생성
            count = 3 if is_promo else 1
            for _ in range(count):
                await self.spawn_item()

        # 3. AGV 이동 관리
        if not is_error:
            await self.check_movements(curr_time)
            # 순환 구조: In -> Sort, Sort -> Out, Out -> In(회귀)
            await self.assign_task('AGV_01', 'Z_IN', 'Z_SORT', curr_time)
            await self.assign_task('AGV_02', 'Z_SORT', 'Z_OUT', curr_time)

        # 4. 트럭 로직 (도착 -> 상차 -> 출발)
        await self.process_truck(curr_time)

    async def spawn_item(self):
        item_id = f"BOX_{str(uuid.uuid4())[:4].upper()}"
        q = """
        MATCH (z:Zone {id: 'Z_IN'})
        CREATE (i:Item {id: $id, status: 'WAITING', timestamp: datetime()})
        CREATE (i)-[:STORED_IN]->(z)
        """
        db.run_query(q, {"id": item_id})

    async def assign_task(self, agv_id, src_id, dst_id, curr_time):
        # 출발지에 물건이 있고 AGV가 놀고 있을 때 이동
        q_check = """
        MATCH (a:AGV {id: $agv_id})
        WHERE NOT (a)-[:MOVING_TO]->()
        MATCH (src:Zone {id: $src})
        MATCH (i:Item)-[:STORED_IN]->(src)
        WITH a, i, src LIMIT 1
        RETURN a.id, i.id as item_id
        """
        res = db.run_query(q_check, {"agv_id": agv_id, "src": src_id})
        
        if res:
            item_id = res[0]['item_id']
            # 이동 시작
            q_move = """
            MATCH (a:AGV {id: $agv_id})-[l:LOCATED_AT]->(src:Zone)
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

    async def check_movements(self, curr_time):
        # 이동 완료 처리 (AGV & Truck)
        q_arrived = """
        MATCH (n)-[m:MOVING_TO]->(dst:Zone)
        WHERE $now >= m.start_time + m.duration
        OPTIONAL MATCH (i:Item)-[l:LOADED_ON]->(n)
        DELETE m, l
        CREATE (n)-[:LOCATED_AT]->(dst)
        // 아이템은 Zone에 보관 처리
        FOREACH(x IN CASE WHEN i IS NOT NULL THEN [1] ELSE [] END | 
            CREATE (i)-[:STORED_IN]->(dst) 
            SET i.status = 'ARRIVED'
        )
        SET n.status = 'IDLE'
        """
        db.run_query(q_arrived, {"now": curr_time})

    async def process_truck(self, curr_time):
        # 트럭 상태 확인
        q_truck = "MATCH (t:Truck) RETURN t.status as status, t.id as id"
        res = db.run_query(q_truck)
        if not res: return
        
        status = res[0]['status']
        truck_id = res[0]['id']

        # 1. 대기중(WAITING) -> 출고존으로 이동(MOVING_TO Z_OUT)
        if status == 'WAITING':
            # 물건이 Z_OUT에 3개 이상 쌓이면 출발
            q_cnt = "MATCH (z:Zone {id: 'Z_OUT'})<-[:STORED_IN]-(i:Item) RETURN count(i) as cnt"
            cnt = db.run_query(q_cnt)[0]['cnt']
            
            if cnt >= 2: # 물건 2개 이상이면 트럭 호출
                # 500(화면 밖) -> 300(Z_OUT) 이동 설정
                # 여기서는 DB 관계만 설정하고 프론트가 애니메이션 처리
                q_in = """
                MATCH (t:Truck {id: $tid}), (z:Zone {id: 'Z_OUT'})
                CREATE (t)-[:MOVING_TO {start_time: $now, duration: 3.0}]->(z)
                SET t.status = 'INBOUND'
                """
                db.run_query(q_in, {"tid": truck_id, "now": curr_time})

        # 2. IDLE(도착완료) -> 상차 후 -> 떠남(MOVING_TO HOME/Virtual)
        elif status == 'IDLE':
            # 상차 (아이템 삭제)
            q_load = """
            MATCH (z:Zone {id: 'Z_OUT'})
            MATCH (i:Item)-[r:STORED_IN]->(z)
            WITH i, r LIMIT 5
            DETACH DELETE i
            """
            db.run_query(q_load)
            
            # 떠나기 (다시 화면 밖으로)
            # Z_OUT에서 멀어지는 애니메이션을 위해 가상의 노드나 좌표 로직 필요
            # 여기선 상태를 OUTBOUND로 바꾸고 프론트에서 처리
            q_out = """
            MATCH (t:Truck {id: $tid})-[l:LOCATED_AT]->(z)
            DELETE l
            SET t.status = 'WAITING' 
            """
            # 다시 WAITING으로 바로 가지만, 프론트에서 일정 시간 애니메이션 보여줌
            db.run_query(q_out, {"tid": truck_id})

    async def trigger_random_event(self):
        evt_type = "PROMO" if random.random() < 0.6 else "ERROR"
        desc = "🎉 [주문 폭주] 주문량이 2배로 증가합니다!" if evt_type == "PROMO" else "🚨 [설비 장애] 컨베이어 벨트가 멈췄습니다!"
        
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
        print(f"🔥 이벤트 발생: {evt_type}")

    def end_event(self):
        print(f"🏁 이벤트 종료: {self.current_event_type}")
        if self.current_event_type:
            db.run_query(f"MATCH (e:Event {{type: '{self.current_event_type}'}}) DETACH DELETE e")
        self.event_active = False
        self.current_event_type = None
        self.last_event_end_time = time.time()

simulator = LogisticsSimulator()
