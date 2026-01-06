import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User } from 'lucide-react';
import axios from 'axios';

const ChatBot = ({ onHighlightNodes }) => {
  const [messages, setMessages] = useState([
    { role: 'ai', text: '안녕하세요. 물류 관제 AI입니다. 무엇을 도와드릴까요?' }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef();

  // 자동 스크롤
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    
    const userMsg = input;
    setMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setInput("");
    setLoading(true);

    try {
      // PROD 환경에선 상대경로, 로컬에선 localhost
      const apiBase = import.meta.env.PROD ? '' : 'http://localhost:8000';
      const res = await axios.post(`${apiBase}/api/chat`, { message: userMsg });
      
      const { reply, related_nodes } = res.data;
      
      setMessages(prev => [...prev, { role: 'ai', text: reply }]);
      
      // 상위 컴포넌트로 하이라이트 요청 전달
      if (related_nodes && related_nodes.length > 0) {
        onHighlightNodes(related_nodes);
      }
    } catch (e) {
      setMessages(prev => [...prev, { role: 'ai', text: '오류가 발생했습니다.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full w-full bg-white rounded-3xl p-6 shadow-sm border border-gray-100 flex flex-col">
      <h3 className="text-lg font-bold text-gray-800 mb-4 flex items-center gap-2">
        <Bot className="text-green-500" /> AI 관제 어시스턴트
      </h3>

      {/* 메시지 영역 */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-2" ref={scrollRef}>
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
              msg.role === 'user' 
                ? 'bg-[#3182F6] text-white rounded-tr-none' 
                : 'bg-gray-100 text-gray-800 rounded-tl-none'
            }`}>
              {msg.text}
            </div>
          </div>
        ))}
        {loading && (
             <div className="flex justify-start">
                 <div className="bg-gray-100 px-4 py-3 rounded-2xl rounded-tl-none text-sm text-gray-500">
                     분석 중...
                 </div>
             </div>
        )}
      </div>

      {/* 입력 영역 */}
      <div className="relative">
        <input 
          type="text" 
          className="w-full bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 pr-12 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
          placeholder="예: 지금 3호기 상태 어때?"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleSend()}
        />
        <button 
          onClick={handleSend}
          className="absolute right-2 top-1/2 transform -translate-y-1/2 p-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
};

export default ChatBot;
