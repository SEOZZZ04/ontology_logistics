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
        self.run_query("MATCH (n) DETACH DELETE n")

    def init_schema(self):
        print("⚙️ [DB] 스키마 설정 중...")
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
        print("🏗️ [DB] 한국형 물류 센터 온톨로지 생성...")
        query = """
        // 1. 센터 정의
        MERGE (c:Center {id: 'DT_HUB', name: '스마트 물류 센터'})
        
        // 2. 구역 (Zone) - 한글 라벨
        MERGE (z1:Zone {id: 'Z_IN', name: '입고존', type: 'DOCK', x: -300, y: 0})
        MERGE (z2:Zone {id: 'Z_SORT', name: '분류존', type: 'PROCESS', x: 0, y: 0})
        MERGE (z3:Zone {id: 'Z_OUT', name: '출고존', type: 'DOCK', x: 300, y: 0})
        
        // 3. AGV 정의
        MERGE (a1:AGV {id: 'AGV_01', name: '1호기', status: 'IDLE'})
        MERGE (a2:AGV {id: 'AGV_02', name: '2호기', status: 'IDLE'})

        // 4. 트럭 정의 (초기 위치는 화면 밖)
        MERGE (t:Truck {id: 'TRUCK', name: '배송 트럭', status: 'WAITING', x: 500, y: 0})

        // 5. 연결 관계
        MERGE (c)-[:HAS_ZONE]->(z1)
        MERGE (c)-[:HAS_ZONE]->(z2)
        MERGE (c)-[:HAS_ZONE]->(z3)
        MERGE (z3)-[:LOADING_AREA]->(t)

        // 6. 이동 경로 정의
        MERGE (z1)-[:CONNECTED_TO {distance: 10}]->(z2)
        MERGE (z2)-[:CONNECTED_TO {distance: 10}]->(z3)

        // 7. 초기 배치
        MERGE (a1)-[:LOCATED_AT]->(z1)
        MERGE (a2)-[:LOCATED_AT]->(z2)
        """
        self.run_query(query)
        print("✅ [DB] 데이터 구축 완료.")

db = Neo4jHandler()
