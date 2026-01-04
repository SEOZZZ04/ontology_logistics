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

    # [핵심] 온톨로지 스키마 초기화
    def init_schema(self):
        print("⚙️ [DB] 온톨로지 스키마 및 제약조건 설정 중...")
        queries = [
            # 1. 고유 ID 제약조건 (데이터 중복 방지)
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Center) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (z:Zone) REQUIRE z.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (a:AGV) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Item) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE",
            
            # 2. 벡터 인덱스 생성 (Graph RAG용)
            """
            CREATE VECTOR INDEX event_embedding_index IF NOT EXISTS
            FOR (e:Event) ON (e.embedding)
            OPTIONS {indexConfig: {
              `vector.dimensions`: 768,
              `vector.similarity_function`: 'cosine'
            }}
            """
        ]
        with self.driver.session() as session:
            for q in queries:
                session.run(q)
        print("✅ [DB] 스키마 설정 완료.")

    # [초기 데이터] 맵 생성
    def seed_data(self):
        print("🏗️ [DB] 기초 맵(Topology) 생성 중...")
        query = """
        MERGE (c:Center {id: 'DT_HUB', name: '동탄 허브'})
        
        MERGE (z1:Zone {id: 'Z_IN', name: '입고존'})
        MERGE (z2:Zone {id: 'Z_SORT', name: '분류존'})
        MERGE (z3:Zone {id: 'Z_OUT', name: '출고존'})

        MERGE (c)-[:HAS_ZONE]->(z1)
        MERGE (c)-[:HAS_ZONE]->(z2)
        MERGE (c)-[:HAS_ZONE]->(z3)

        MERGE (z1)-[:CONNECTED_TO]->(z2)
        MERGE (z2)-[:CONNECTED_TO]->(z3)
        
        // AGV 초기 배치
        MERGE (a1:AGV {id: 'AGV_01', status: 'IDLE'})-[:LOCATED_AT]->(z1)
        MERGE (a2:AGV {id: 'AGV_02', status: 'IDLE'})-[:LOCATED_AT]->(z1)
        """
        self.run_query(query)
        print("✅ [DB] 기초 데이터 생성 완료.")

db = Neo4jHandler()
