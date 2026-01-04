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
        print("🧹 [DB] 기존 데이터 삭제 및 초기화 중...")
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
        print("🏗️ [DB] 기초 맵(Topology) 생성 중 (좌표 고정)...")
        # [핵심] x, y 좌표를 속성으로 추가하여 강제 고정
        query = """
        // 1. 센터 (중앙 상단)
        MERGE (c:Center {id: 'DT_HUB'}) 
        SET c.name = '동탄 허브', c.x = 0, c.y = -150
        
        // 2. 구역 (좌 -> 우 배치)
        MERGE (z1:Zone {id: 'Z_IN'})   SET z1.name = '입고존', z1.x = -250, z1.y = 0
        MERGE (z2:Zone {id: 'Z_SORT'}) SET z2.name = '분류존', z2.x = 0,    z2.y = 0
        MERGE (z3:Zone {id: 'Z_OUT'})  SET z3.name = '출고존', z3.x = 250,  z3.y = 0

        // 3. 관계 연결
        MERGE (c)-[:HAS_ZONE]->(z1)
        MERGE (c)-[:HAS_ZONE]->(z2)
        MERGE (c)-[:HAS_ZONE]->(z3)

        MERGE (z1)-[:CONNECTED_TO]->(z2)
        MERGE (z2)-[:CONNECTED_TO]->(z3)
        
        // 4. AGV (구역 주변에 배치)
        MERGE (a1:AGV {id: 'AGV_01'}) SET a1.status = 'IDLE', a1.x = -250, a1.y = 100
        MERGE (a2:AGV {id: 'AGV_02'}) SET a2.status = 'IDLE', a2.x = 0,    a2.y = 100
        
        MERGE (a1)-[:LOCATED_AT]->(z1)
        MERGE (a2)-[:LOCATED_AT]->(z2)
        """
        self.run_query(query)
        print("✅ [DB] 기초 데이터(좌표 포함) 생성 완료.")

db = Neo4jHandler()
