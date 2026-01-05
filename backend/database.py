import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class Neo4jHandler:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI")
        self.user = os.getenv("NEO4J_USERNAME")
        self.password = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self):
        self.driver.close()

    def run_query(self, query, parameters=None):
        with self.driver.session() as session:
            result = session.run(query, parameters)
            return [record.data() for record in result]

    def clean_database(self):
        print("🧹 [DB] 초기화 중...")
        self.run_query("MATCH (n) DETACH DELETE n")

    def init_schema(self):
        print("⚙️ [DB] 스키마 및 인덱스 설정 중...")
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Center) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (z:Zone) REQUIRE z.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (a:AGV) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Item) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE",
            """
            CREATE VECTOR INDEX event_embedding_index IF NOT EXISTS
            FOR (e:Event) ON (e.embedding)
            OPTIONS {indexConfig: { `vector.dimensions`: 768, `vector.similarity_function`: 'cosine' }}
            """
        ]
        with self.driver.session() as session:
            for q in queries:
                session.run(q)

    def seed_data(self):
        print("🏗️ [DB] 고도화된 온톨로지 생성 중...")
        query = """
        // 1. 센터 정의
        MERGE (c:Center {id: 'DT_HUB', name: 'Smart Digital Twin Center'})
        
        // 2. 주요 구역 (Zone) 정의 - 좌표 메타데이터 포함 (시각화용)
        MERGE (z1:Zone {id: 'Z_IN', name: 'Inbound Dock', type: 'DOCK', x: -300, y: 0})
        MERGE (z2:Zone {id: 'Z_SORT', name: 'Auto Sorter', type: 'PROCESS', x: 0, y: 0})
        MERGE (z3:Zone {id: 'Z_OUT', name: 'Outbound Bay', type: 'DOCK', x: 300, y: 0})
        
        // 3. AGV 정의
        MERGE (a1:AGV {id: 'AGV_01', name: 'Fast-Bot Alpha', status: 'IDLE'})
        MERGE (a2:AGV {id: 'AGV_02', name: 'Heavy-Bot Beta', status: 'IDLE'})

        // 4. 트럭 정의
        MERGE (t:Truck {id: 'TRUCK', name: 'Logistics Truck', status: 'WAITING'})

        // 5. 관계 정의 (구조적 연결)
        MERGE (c)-[:HAS_ZONE]->(z1)
        MERGE (c)-[:HAS_ZONE]->(z2)
        MERGE (c)-[:HAS_ZONE]->(z3)
        MERGE (z3)-[:LOADING_AREA]->(t)

        // 6. 경로(Path) 정의 (물리적 이동 가능 경로)
        MERGE (z1)-[:CONNECTED_TO {distance: 10, type: 'CONVEYOR'}]->(z2)
        MERGE (z2)-[:CONNECTED_TO {distance: 10, type: 'AGV_PATH'}]->(z3)

        // 7. 초기 위치 설정
        MERGE (a1)-[:LOCATED_AT]->(z1)
        MERGE (a2)-[:LOCATED_AT]->(z2)
        """
        self.run_query(query)
        print("✅ [DB] 온톨로지 구축 완료.")

db = Neo4jHandler()
