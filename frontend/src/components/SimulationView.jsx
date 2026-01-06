import React from 'react';
import { motion } from 'framer-motion';
import { Package, Truck, ArrowRight, Container } from 'lucide-react';

const SimulationView = ({ nodes }) => {
  // AGV만 필터링
  const agvs = nodes.filter(n => n.group === 'AGV');

  // Zone 위치 매핑 (화면상 좌표)
  const zonePositions = {
    'Inbound': { left: '10%', label: '입고' },
    'Storage_A': { left: '35%', label: '보관' },
    'Packing': { left: '60%', label: '분류/포장' },
    'Outbound': { left: '85%', label: '출고' }
  };

  return (
    <div className="h-full w-full bg-white rounded-3xl p-6 shadow-sm border border-gray-100 flex flex-col relative overflow-hidden">
      <h3 className="text-lg font-bold text-gray-800 mb-4 flex items-center gap-2">
        <Truck className="text-blue-500" /> 실시간 물류 이동 현황
      </h3>
      
      {/* 배경 라인 */}
      <div className="absolute top-1/2 left-10 right-10 h-1 bg-gray-100 -z-0"></div>

      {/* Zone 표시 */}
      <div className="flex-1 w-full relative">
        {Object.entries(zonePositions).map(([key, info]) => (
          <div key={key} className="absolute top-1/2 transform -translate-y-1/2 flex flex-col items-center gap-2" style={{ left: info.left }}>
            <div className="w-12 h-12 bg-gray-50 rounded-2xl flex items-center justify-center border-2 border-gray-100 z-10">
              <Container size={20} className="text-gray-400" />
            </div>
            <span className="text-xs font-bold text-gray-500">{info.label}</span>
          </div>
        ))}

        {/* 움직이는 AGV */}
        {agvs.map((agv) => {
           // 시각화를 위해 단순화: 배터리에 따라 색상 변경
           const color = agv.battery < 20 ? 'bg-red-500' : 'bg-blue-500';
           
           // 실제 위치 데이터에 따라 X축 좌표 결정 (임시 로직)
           // 실제로는 LOCATED_AT 관계를 보고 결정해야 하지만, 여기선 데모 효과를 위해 랜덤성 부여
           return (
             <motion.div
               key={agv.id}
               className={`absolute top-1/2 -mt-8 ${color} text-white text-[10px] px-2 py-1 rounded-full shadow-lg z-20 flex items-center gap-1`}
               animate={{ 
                 left: agv.status === 'IDLE' ? '10%' : ['10%', '35%', '60%', '85%'][Math.floor(Math.random()*4)]
               }}
               transition={{ duration: 2, ease: "easeInOut" }}
             >
               <Truck size={12} /> {agv.label}
             </motion.div>
           );
        })}
      </div>
    </div>
  );
};

export default SimulationView;
