import React, { useState, useEffect } from 'react';
import axios from 'axios';
import SimulationView from './components/SimulationView';
import OntologyView from './components/OntologyView';
import EventLog from './components/EventLog';
import ChatBot from './components/ChatBot';

function App() {
  const [data, setData] = useState({ graph: { nodes: [], links: [] }, events: [], traffic: 1.0 });
  const [highlightNodes, setHighlightNodes] = useState(new Set());

  // 데이터 폴링 (1초 주기)
  useEffect(() => {
    const apiBase = import.meta.env.PROD ? '' : 'http://localhost:8000';
    const interval = setInterval(async () => {
      try {
        const res = await axios.get(`${apiBase}/api/dashboard`);
        setData({
          graph: res.data.graph,
          events: res.data.events,
          traffic: res.data.traffic_level
        });
      } catch (e) {
        console.error("Connection Error", e);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // 챗봇에서 노드 하이라이트 요청 시 처리
  const handleHighlight = (nodeIds) => {
    setHighlightNodes(new Set(nodeIds));
    // 3초 후 하이라이트 해제 (선택사항)
    setTimeout(() => setHighlightNodes(new Set()), 5000);
  };

  return (
    <div className="w-full h-screen bg-[#F2F4F6] p-4 box-border font-sans">
      <div className="grid grid-cols-2 grid-rows-2 gap-4 h-full">
        {/* 1. 물류 흐름 (좌상) */}
        <div className="overflow-hidden">
          <SimulationView nodes={data.graph.nodes} />
        </div>
        
        {/* 2. 이벤트 로그 (우상) */}
        <div className="overflow-hidden">
          <EventLog events={data.events} />
        </div>

        {/* 3. 온톨로지 뷰 (좌하) */}
        <div className="overflow-hidden">
          <OntologyView data={data.graph} highlightNodes={highlightNodes} />
        </div>

        {/* 4. 챗봇 (우하) */}
        <div className="overflow-hidden">
          <ChatBot onHighlightNodes={handleHighlight} />
        </div>
      </div>
    </div>
  );
}

export default App;
