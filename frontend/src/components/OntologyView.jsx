import React, { useRef, useEffect } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

const OntologyView = ({ data, highlightNodes }) => {
  const fgRef = useRef();

  // 하이라이트 요청 시 줌인 효과
  useEffect(() => {
    if (highlightNodes.size > 0 && fgRef.current) {
      // 첫 번째 하이라이트 노드 찾기
      const firstId = Array.from(highlightNodes)[0];
      const node = data.nodes.find(n => n.id === firstId);
      
      if (node) {
        fgRef.current.centerAt(node.x, node.y, 1000);
        fgRef.current.zoom(2.5, 2000); // 2.5배 확대, 2초 동안
      }
    }
  }, [highlightNodes, data]);

  return (
    <div className="h-full w-full bg-white rounded-3xl p-4 shadow-sm border border-gray-100 overflow-hidden relative">
        <div className="absolute top-4 left-4 z-10 bg-white/80 px-3 py-1 rounded-full backdrop-blur-sm">
            <h3 className="text-sm font-bold text-gray-800">Ontology Graph</h3>
        </div>
      <ForceGraph2D
        ref={fgRef}
        width={window.innerWidth / 2 - 40} // 반응형 처리는 CSS로 하는게 좋지만 ForceGraph 특성상 고정값 필요
        height={window.innerHeight / 2 - 40}
        graphData={data}
        nodeLabel="label"
        nodeColor={node => {
            if (highlightNodes.has(node.id)) return '#EF4444'; // 검색된 노드는 빨간색
            if (node.group === 'Zone') return '#E5E7EB';
            if (node.group === 'AGV') return '#3B82F6'; // 파란색
            return '#9CA3AF';
        }}
        nodeRelSize={6}
        linkColor={() => "#F3F4F6"}
        enableNodeDrag={false}
        enableZoom={true}
      />
    </div>
  );
};

export default OntologyView;
