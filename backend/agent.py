import google.generativeai as genai
import os
import json
import logging
from .database import db

# 로거 설정
logger = logging.getLogger(__name__)

# [중요] 모델명을 안정적인 버전으로 변경
# 만약 2.5를 꼭 써야 한다면 API 키 권한을 확인해야 합니다.
MODEL_NAME = 'gemini-2.5-flash' 

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(MODEL_NAME)

async def get_embedding(text):
    try:
        # 텍스트 임베딩 모델
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_query"
        )
        return result['embedding']
    except Exception as e:
        logger.error(f"Embedding Error: {e}")
        return [0.0] * 768 # 에러 시 더미 벡터 반환하여 시스템 다운 방지

async def query_agent(user_question: str):
    related_node_ids = []
    context_texts = []
    
    # 1. 키워드 매핑 (빠른 검색)
    zone_map = {"입고": "Z_IN", "분류": "Z_SORT", "출고": "Z_OUT", "동탄": "DT_HUB"}
    for key, val in zone_map.items():
        if key in user_question:
            related_node_ids.append(val)

    # 2. 벡터 검색 (DB에서 유사 이벤트/장애 검색)
    try:
        embedding = await get_embedding(user_question)
        cypher = """
        CALL db.index.vector.queryNodes('event_embedding_index', 3, $emb)
        YIELD node, score
        WHERE score > 0.6
        RETURN node.id AS id, node.description AS text, node.type as type
        """
        results = db.run_query(cypher, {"emb": embedding})
        
        for r in results:
            context_texts.append(f"[관련 기록] {r['type']}: {r['text']}")
            # 장애 기록이 있다면 해당 구역을 추정해서 하이라이트 (단순화된 로직)
            if r['type'] == 'ERROR':
                related_node_ids.append('Z_IN') 
                related_node_ids.append('Z_SORT')

    except Exception as e:
        logger.error(f"Vector Search Fail: {e}")

    # 3. 실시간 통계 데이터
    stats_query = "MATCH (z:Zone) OPTIONAL MATCH (i:Item)-[:STORED_IN]->(z) RETURN z.name, count(i) as cnt"
    stats = db.run_query(stats_query)
    context_texts.append(f"[현재 물동량 Status]: {str(stats)}")

    # 4. LLM 응답 생성
    prompt = f"""
    당신은 물류센터 관제 AI입니다. 아래 [Context]를 보고 사용자의 질문에 답하세요.
    - 답변은 2문장 이내로 간결하게 하세요.
    - 문제가 있다면 원인을 설명하고, 없다면 현재 상태를 요약하세요.
    
    [Context]
    {json.dumps(context_texts, ensure_ascii=False)}
    
    User: {user_question}
    AI:
    """
    
    try:
        response = model.generate_content(prompt)
        reply_text = response.text.strip()
    except Exception as e:
        logger.error(f"LLM Gen Error: {e}")
        reply_text = "죄송합니다. AI 모델 응답을 생성할 수 없습니다. 로그를 확인해주세요."

    return {
        "reply": reply_text,
        "related_nodes": list(set(related_node_ids))
    }
