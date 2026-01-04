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
        print("🏗️ [DB] 기초 온톨로지 생성 중...")
        # 좌표값 제거 -> 프론트엔드 계층형 레이아웃 사용 예정
        query = """
        // 1. 센터
        MERGE (c:Center {id: 'DT_HUB', name: '한국물류 동탄허브'})
        
        // 2. 구역
        MERGE (z1:Zone {id: 'Z_IN', name: '입고존(Inbound)'})
        MERGE (z2:Zone {id: 'Z_SORT', name: '분류존(Sorting)'})
        MERGE (z3:Zone {id: 'Z_OUT', name: '출고존(Outbound)'})

        // 3. 구조 연결 (Center -> Zones)
        MERGE (c)-[:HAS_ZONE]->(z1)
        MERGE (c)-[:HAS_ZONE]->(z2)
        MERGE (c)-[:HAS_ZONE]->(z3)

        // 4. 물류 흐름 연결 (In -> Sort -> Out)
        MERGE (z1)-[:NEXT_STEP]->(z2)
        MERGE (z2)-[:NEXT_STEP]->(z3)
        
        // 5. AGV 배치
        MERGE (a1:AGV {id: 'AGV_01', name: 'AGV-01 (대기중)'})
        MERGE (a2:AGV {id: 'AGV_02', name: 'AGV-02 (대기중)'})
        
        MERGE (a1)-[:LOCATED_AT]->(z1)
        MERGE (a2)-[:LOCATED_AT]->(z2)
        """
        self.run_query(query)
        print("✅ [DB] 기초 데이터 생성 완료.")

db = Neo4jHandler()
