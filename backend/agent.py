import google.generativeai as genai
import os
from .database import db

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash') # 빠르고 저렴한 모델

async def query_agent(user_question: str):
    # 1. 사용자 의도 파악 (Routing)
    # 실제로는 LLM이 판단하게 해야 하지만, 데모를 위해 키워드로 약식 구현
    # "문제", "사고", "이유" -> Vector Search (RAG)
    # "상태", "위치", "개수" -> Graph Statistics
    
    context = ""
    
    # [Tool 1] Vector Search (문제 해결)
    if any(k in user_question for k in ["문제", "사고", "원인", "장애"]):
        embedding = genai.embed_content(
            model="models/text-embedding-004",
            content=user_question,
            task_type="retrieval_query"
        )['embedding']
        
        # Neo4j 벡터 검색 쿼리
        cypher = """
        CALL db.index.vector.queryNodes('event_embedding_index', 3, $emb)
        YIELD node, score
        RETURN node.description AS text, score
        """
        results = db.run_query(cypher, {"emb": embedding})
        context += f"[검색된 유사 장애 내역]: {str(results)}\n"

    # [Tool 2] Graph Status (현재 상태)
    else:
        cypher = """
        MATCH (z:Zone)
        OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
        OPTIONAL MATCH (a:AGV)-[:LOCATED_AT]->(z)
        RETURN z.name, count(i) as items, count(a) as agvs
        """
        results = db.run_query(cypher)
        context += f"[현재 센터 현황]: {str(results)}\n"

    # 2. Final Reasoning (Gemini)
    prompt = f"""
    당신은 스마트 물류센터의 AI 운영자입니다.
    아래의 [실시간 시스템 데이터]를 바탕으로 사용자의 질문에 답하세요.
    데이터에 없는 내용은 지어내지 말고 모른다고 하세요.
    
    [실시간 시스템 데이터]
    {context}
    
    사용자 질문: {user_question}
    답변:
    """
    
    response = model.generate_content(prompt)
    return response.text
