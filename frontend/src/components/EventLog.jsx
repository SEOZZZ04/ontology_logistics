import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Bell, Zap } from 'lucide-react';

const EventLog = ({ events }) => {
  return (
    <div className="h-full w-full bg-white rounded-3xl p-6 shadow-sm border border-gray-100 flex flex-col">
      <h3 className="text-lg font-bold text-gray-800 mb-4 flex items-center gap-2">
        <Bell className="text-red-500" /> 실시간 운영 알림
      </h3>
      
      <div className="flex-1 overflow-y-auto space-y-3 pr-2 scrollbar-hide">
        <AnimatePresence>
          {events.length === 0 ? (
            <p className="text-gray-400 text-sm text-center mt-10">현재 특이사항 없습니다.</p>
          ) : (
            events.map((evt, idx) => (
              <motion.div
                key={`${idx}-${evt.title}`}
                initial={{ opacity: 0, x: 50 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                className={`p-4 rounded-2xl flex items-start gap-3 ${
                  evt.type === 'warning' ? 'bg-red-50' : 'bg-blue-50'
                }`}
              >
                <div className={`p-2 rounded-full ${evt.type === 'warning' ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'}`}>
                    <Zap size={16} />
                </div>
                <div>
                  <h4 className={`font-bold text-sm ${evt.type === 'warning' ? 'text-red-700' : 'text-blue-700'}`}>
                    {evt.title}
                  </h4>
                  <p className={`text-xs mt-1 ${evt.type === 'warning' ? 'text-red-500' : 'text-blue-500'}`}>
                    {evt.desc}
                  </p>
                </div>
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default EventLog;
