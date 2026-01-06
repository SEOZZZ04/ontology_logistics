import os
import random
from datetime import datetime
from neo4j import GraphDatabase
from dotenv import load_dotenv

# 환경 변수 로드 (.env 파일이 같은 경로에 있어야 함)
load_dotenv()

class Neo4jManager:
    def __init__(self):
        # Neo4j AuraDB 연결 정보 (보안을 위해 환경변수 사용 필수)
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        
        if not uri or not password:
            raise ValueError("❌ .env 파일에 NEO4J_URI 및 NEO4J_PASSWORD가 설정되지 않았습니다.")

        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        print("✅ Neo4j Database Connected Successfully.")

    def close(self):
        self.driver.close()
        print("🛑 Neo4j Connection Closed.")

    # =================================================================
    # [SECTION 1] 온톨로지 초기화 (The Genesis)
    # =================================================================
    def init_ontology(self):
        """
        DB를 초기화하고, 물류센터의 기본 맵(Topology)과 제약조건(Constraint)을 생성합니다.
        이 함수는 서버 시작 시 한 번 실행됩니다.
        """
        with self.driver.session() as session:
            print("🔄 Initializing Ontology...")

            # 1. 기존 데이터 및 스키마 클리어 (주의: 데모용이므로 전체 삭제)
            session.run("MATCH (n) DETACH DELETE n")
            # 기존 제약조건 삭제 로직은 복잡하므로 여기선 생략하고, 바로 생성 시도

            # 2. 제약조건(Constraint) 설정 - 데이터 무결성 보장 (중복 ID 방지)
            # Neo4j 버전 5.x 구문 호환
            constraints = [
                "CREATE CONSTRAINT zone_id_unique IF NOT EXISTS FOR (z:Zone) REQUIRE z.id IS UNIQUE",
                "CREATE CONSTRAINT agv_id_unique IF NOT EXISTS FOR (a:AGV) REQUIRE a.id IS UNIQUE",
                "CREATE CONSTRAINT order_id_unique IF NOT EXISTS FOR (o:Order) REQUIRE o.id IS UNIQUE"
            ]
            for q in constraints:
                session.run(q)

            # 3. 맵(Map) 생성: Zone(구역) 정의
            # (Inbound) -> (Storage_A) -> (Process_Packing) -> (Outbound) 구조
            # 좌표(x, y)는 프론트엔드 시각화를 위해 미리 정의합니다.
            create_zones_query = """
            CREATE (z1:Zone {id: 'Inbound', name: '입고장', type: 'dock', x: -200, y: 0})
            CREATE (z2:Zone {id: 'Storage_A', name: '보관 A구역', type: 'storage', x: -50, y: -100})
            CREATE (z3:Zone {id: 'Storage_B', name: '보관 B구역', type: 'storage', x: -50, y: 100})
            CREATE (z4:Zone {id: 'Packing', name: '포장 라인', type: 'process', x: 100, y: 0})
            CREATE (z5:Zone {id: 'Outbound', name: '출고장', type: 'dock', x: 250, y: 0})
            
            // 경로(Path) 연결 - AGV가 이동 가능한 길
            CREATE (z1)-[:CONNECTED_TO {distance: 50}]->(z2)
            CREATE (z1)-[:CONNECTED_TO {distance: 50}]->(z3)
            CREATE (z2)-[:CONNECTED_TO {distance: 50}]->(z4)
            CREATE (z3)-[:CONNECTED_TO {distance: 50}]->(z4)
            CREATE (z4)-[:CONNECTED_TO {distance: 50}]->(z5)
            
            // 순환 구조 (출고 후 다시 입고 대기소로 복귀 가능하게)
            CREATE (z5)-[:CONNECTED_TO {distance: 100}]->(z1)
            """
            session.run(create_zones_query)

            # 4. AGV(로봇) 생성 및 초기 배치
            create_agv_query = """
            MATCH (start:Zone {id: 'Inbound'})
            UNWIND range(1, 4) AS i
            CREATE (a:AGV {
                id: 'AGV-' + toString(i), 
                name: '로봇 ' + toString(i) + '호기', 
                status: 'IDLE', 
                battery: 100,
                last_update: datetime()
            })
            CREATE (a)-[:LOCATED_AT]->(start)
            """
            session.run(create_agv_query)

            print("✨ Ontology Setup Complete: Zones and AGVs created.")

    # =================================================================
    # [SECTION 2] 시뮬레이션 로직 (The Physics)
    # =================================================================
    def update_simulation_step(self, traffic_level=1.0):
        """
        이 함수가 호출될 때마다 시간이 1틱 흐릅니다.
        AGV가 이동하고, 배터리가 소모되고, 상태가 변합니다.
        
        Args:
            traffic_level (float): 1.0(평시) ~ 3.0(혼잡). 이동 확률에 영향을 줌.
        """
        with self.driver.session() as session:
            
            # 1. 배터리 소모 로직 (움직이는 녀석은 더 많이 소모)
            session.run("""
                MATCH (a:AGV)
                SET a.battery = CASE 
                    WHEN a.battery <= 0 THEN 0
                    WHEN a.status = 'MOVING' THEN a.battery - 0.5 
                    ELSE a.battery - 0.1 
                END
                SET a.status = CASE
                    WHEN a.battery < 20 THEN 'LOW_BATTERY'
                    ELSE a.status
                END
            """)

            # 2. AGV 이동 로직 (핵심)
            # 현재 위치에서 연결된(CONNECTED_TO) 다음 구역 중 하나를 랜덤하게 선택하여 이동
            # 단, IDLE이거나 MOVING인 상태에서만 이동. (고장/충전중엔 이동 불가)
            move_query = """
            MATCH (a:AGV)-[old_rel:LOCATED_AT]->(current:Zone)-[:CONNECTED_TO]->(next:Zone)
            WHERE a.battery > 5 AND (a.status = 'IDLE' OR a.status = 'MOVING')
            // 확률적 이동: 트래픽이 높으면 더 자주 움직임
            AND rand() < (0.3 * $traffic)
            
            // 기존 위치 관계 삭제 및 새 위치 관계 생성 (Atomic Update)
            DELETE old_rel
            CREATE (a)-[:LOCATED_AT]->(next)
            
            // 상태 업데이트: 움직였으므로 MOVING, 만약 Outbound면 작업 완료로 IDLE
            SET a.status = CASE 
                WHEN next.id = 'Outbound' THEN 'Unloading...'
                ELSE 'MOVING' 
            END
            SET a.last_update = datetime()
            
            RETURN a.id, current.id, next.id
            """
            result = session.run(move_query, traffic=traffic_level)
            
            # 3. Unloading 상태인 녀석들 다시 IDLE로 변경 (잠시 멈춤 효과 후)
            session.run("""
                MATCH (a:AGV) WHERE a.status = 'Unloading...'
                SET a.status = 'IDLE'
            """)

    # =================================================================
    # [SECTION 3] 데이터 조회 (The Eyes) - 프론트엔드/LLM용
    # =================================================================
    def get_dashboard_data(self):
        """프론트엔드 시각화를 위한 전체 그래프 스냅샷 반환"""
        with self.driver.session() as session:
            # 모든 노드 가져오기
            nodes_query = """
            MATCH (n) 
            RETURN n.id as id, labels(n)[0] as group, n.name as label, 
                   n.status as status, n.battery as battery, 
                   n.type as type, n.x as x, n.y as y
            """
            nodes = session.run(nodes_query).data()

            # 모든 관계 가져오기 (시각화용)
            # AGV 위치 관계(LOCATED_AT)와 맵 연결 관계(CONNECTED_TO) 모두 포함
            links_query = """
            MATCH (n)-[r]->(m)
            RETURN n.id as source, m.id as target, type(r) as type
            """
            links = session.run(links_query).data()

            return {"nodes": nodes, "links": links}

    def get_context_for_llm(self):
        """LLM에게 줄 현재 상황 요약 텍스트"""
        with self.driver.session() as session:
            # 1. 문제 있는 AGV 조회
            issues = session.run("""
                MATCH (a:AGV) 
                WHERE a.battery < 20 OR a.status = 'ERROR'
                RETURN a.name, a.status, a.battery
            """).data()
            
            # 2. 구역별 혼잡도 (AGV가 몇 대 있는지)
            density = session.run("""
                MATCH (z:Zone)<-[:LOCATED_AT]-(a:AGV)
                RETURN z.name, count(a) as count
                ORDER BY count DESC
            """).data()
            
            return {"issues": issues, "density": density}

    # =================================================================
    # [SECTION 4] 이벤트 주입 (The Chaos)
    # =================================================================
    def inject_event(self, event_type, description):
        """외부 이벤트(프로모션, 고장 등)를 그래프에 반영"""
        with self.driver.session() as session:
            session.run("""
                CREATE (e:Event {
                    id: apoc.create.uuid(),
                    type: $type,
                    description: $desc,
                    timestamp: datetime()
                })
                // 이벤트는 보통 입고장이나 포장 라인에 영향을 줌 (데모용)
                WITH e
                MATCH (z:Zone) WHERE z.id IN ['Inbound', 'Packing']
                MERGE (e)-[:IMPACTS]->(z)
            """, type=event_type, desc=description)
