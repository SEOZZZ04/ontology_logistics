import React from 'react';
import { motion } from 'framer-motion';
import { Truck, Package, ArrowRight, Warehouse } from 'lucide-react';

const SimulationView = ({ nodes }) => {
  // AGV 노드만 필터링
  const agvs = nodes.filter(n => n.group === 'AGV');

  // Zone ID에 따른 화면 위치 매핑 (Inbound -> Outbound)
  const getPosition = (zoneId) => {
    // 백엔드에서 LOCATED_AT 관계를 보내주지 않고 노드 속성만 보낸다면, 
    // 실제로는 관계 데이터를 파싱해야 하지만, 데모용으로는 좌표를 모사합니다.
    // *Neo4j Manager에서 nodes 데이터에 x, y 좌표를 보내주도록 했으므로 그것을 활용하거나
    // Zone ID 기반으로 고정 위치를 잡습니다.
    switch(true) {
      case zoneId === 'Inbound': return '10%';
      case zoneId === 'Storage_A': return '30%';
      case zoneId === 'Storage_B': return '30%';
      case zoneId === 'Packing': return '60%';
      case zoneId === 'Outbound': return '90%';
      default: return '10%';
    }
  };

  // AGV가 현재 어떤 Zone에 있는지 찾는 로직은 백엔드 링크 데이터가 필요하지만,
  // 시각적 단순화를 위해 AGV 상태에 따라 임의의 위치를 보여주는 방식으로 데모 구현
  const getAgvLeftPos = (agv) => {
      // 실제로는 graph links에서 (:AGV)-[:LOCATED_AT]->(:Zone)을 찾아야 함.
      // 여기서는 AGV 상태 텍스트를 파싱하거나 랜덤성을 부여해 움직임을 표현
      if (agv.status === 'IDLE') return '10%';
      if (agv.status === 'Unloading...') return '90%';
      // 움직이는 중이면 랜덤 위치 (데모 효과)
      return `${Math.floor(Math.random() * 60 + 20)}%`; 
  };

  return (
    <div className="w-full h-full p-6 flex flex-col relative">
      <h2 className="text-xl font-bold text-toss-text mb-2 flex items-center gap-2">
        <Truck className="text-toss-blue" /> 실시간 물류 흐름
      </h2>
      <p className="text-sm text-toss-grey mb-8">AGV가 입고부터 출고까지 자동으로 이동합니다.</p>

      {/* 배경 트랙 */}
      <div className="flex-1 relative flex items-center justify-between px-12">
        <div className="absolute left-0 w-full h-2 bg-toss-bg rounded-full -z-10" />

        {/* 고정 스테이션 표시 */}
        {['입고', '보관', '분류/포장', '출고'].map((label, idx) => (
          <div key={idx} className="flex flex-col items-center gap-2 bg-white z-10 p-2">
            <div className="w-12 h-12 rounded-2xl bg-toss-bg flex items-center justify-center text-toss-grey">
              <Warehouse size={20} />
            </div>
            <span className="text-xs font-bold text-toss-grey">{label}</span>
          </div>
        ))}

        {/* 움직이는 AGV 아이콘 */}
        {agvs.map(agv => (
          <motion.div
            key={agv.id}
            className="absolute top-1/2 -mt-10 flex flex-col items-center"
            initial={{ left: '10%' }}
            animate={{ 
              left: getAgvLeftPos(agv) 
            }}
            transition={{ duration: 2, ease: "easeInOut" }}
          >
            <div className={`
              px-3 py-1.5 rounded-full text-xs font-bold text-white shadow-lg flex items-center gap-1
              ${agv.battery < 20 ? 'bg-toss-red' : 'bg-toss-blue'}
            `}>
              <Truck size={12} /> {agv.label}
            </div>
            <div className="text-[10px] text-toss-grey mt-1 font-mono">
              {agv.battery}%
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
};

export default SimulationView;
