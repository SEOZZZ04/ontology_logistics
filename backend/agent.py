import google.generativeai as genai
import os
import json
from .database import db

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

async def get_embedding(text):
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_query"
    )
    return result['embedding']

async def query_agent(user_question: str):
    related_node_ids = []
    context_texts = []
    
    # [Tool 1] Vector Search (장애, 문제 검색)
    if any(k in user_question for k in ["문제", "사고", "원인", "장애", "이벤트", "빨간"]):
        embedding = await get_embedding(user_question)
        
        # 노드 ID까지 같이 반환하도록 수정
        cypher = """
        CALL db.index.vector.queryNodes('event_embedding_index', 5, $emb)
        YIELD node, score
        RETURN node.id AS id, node.description AS text, score
        """
        results = db.run_query(cypher, {"emb": embedding})
        
        for r in results:
            related_node_ids.append(r['id'])
            context_texts.append(f"[유사 장애 이벤트] ID:{r['id']}, 내용:{r['text']}")

    # [Tool 2] Graph Status (현재 물동량 상태)
    # 질문에 특정 구역 이름이 들어가면 그 구역을 하이라이트 대상에 추가
    zone_map = {"입고": "Z_IN", "분류": "Z_SORT", "출고": "Z_OUT"}
    for keyword, zone_id in zone_map.items():
        if keyword in user_question:
            related_node_ids.append(zone_id)

    # 전체 통계 데이터 가져오기
    cypher = """
    MATCH (z:Zone)
    OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z)
    RETURN z.name as zone, count(i) as items
    """
    stats = db.run_query(cypher)
    context_texts.append(f"[실시간 구역별 적재 현황]: {str(stats)}")

    # 2. Final Reasoning (Gemini)
    prompt = f"""
    당신은 물류센터 관제 시스템의 AI입니다.
    [시스템 데이터]를 기반으로 질문에 간결하고 명확하게 답하세요.
    
    [시스템 데이터]
    {json.dumps(context_texts, ensure_ascii=False)}
    
    질문: {user_question}
    답변:
    """
    
    response = model.generate_content(prompt)
    
    # 답변 텍스트와 관련된 노드 ID 목록을 함께 반환
    return {
        "reply": response.text.strip(),
        "related_nodes": list(set(related_node_ids)) # 중복제거
    }
