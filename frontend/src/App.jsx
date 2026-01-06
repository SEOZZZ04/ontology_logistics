import React, { useState, useEffect } from 'react';
import axios from 'axios';
import SimulationView from './components/SimulationView';
import OntologyView from './components/OntologyView';
import EventLog from './components/EventLog';
import ChatBot from './components/ChatBot';

function App() {
  // 전체 데이터 상태
  const [data, setData] = useState({ 
    graph: { nodes: [], links: [] }, 
    events: [], 
    traffic_level: 1.0 
  });
  
  // 검색/대화로 인한 하이라이트 상태
  const [highlightNodes, setHighlightNodes] = useState(new Set());

  // 1초마다 백엔드에서 데이터 폴링
  useEffect(() => {
    // 배포 환경과 로컬 환경 자동 구분
    const apiBase = import.meta.env.PROD ? '' : 'http://localhost:8000';
    
    const fetchData = async () => {
      try {
        const res = await axios.get(`${apiBase}/api/dashboard`);
        setData(res.data);
      } catch (e) {
        console.error("Dashboard connection failed", e);
      }
    };

    fetchData(); // 즉시 실행
    const interval = setInterval(fetchData, 1000);
    return () => clearInterval(interval);
  }, []);

  // 챗봇이 특정 노드를 언급했을 때 호출
  const handleHighlight = (nodeIds) => {
    setHighlightNodes(new Set(nodeIds));
    // 5초 후 하이라이트 자동 해제
    setTimeout(() => setHighlightNodes(new Set()), 5000);
  };

  return (
    <div className="w-full h-screen p-4 grid grid-cols-2 grid-rows-2 gap-4 box-border">
      
      {/* 1. 좌상: 물류 흐름 (Simulation) */}
      <div className="rounded-3xl overflow-hidden shadow-sm bg-white">
        <SimulationView nodes={data.graph.nodes} />
      </div>
      
      {/* 2. 우상: 이벤트 로그 (Notifications) */}
      <div className="rounded-3xl overflow-hidden shadow-sm bg-white">
        <EventLog events={data.events} traffic={data.traffic_level} />
      </div>

      {/* 3. 좌하: 온톨로지 뷰 (Graph) */}
      <div className="rounded-3xl overflow-hidden shadow-sm bg-white border border-gray-100">
        <OntologyView data={data.graph} highlightNodes={highlightNodes} />
      </div>

      {/* 4. 우하: AI 에이전트 (Chat) */}
      <div className="rounded-3xl overflow-hidden shadow-sm bg-white">
        <ChatBot onHighlightNodes={handleHighlight} />
      </div>

    </div>
  );
}

export default App;
