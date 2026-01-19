import React, { memo } from 'react';
import {
  BaseEdge,
  EdgeProps,
  getSmoothStepPath,
  EdgeLabelRenderer,
  Edge,
} from '@xyflow/react';
import { SyncEdgeData } from '../../hooks/useFederationTopology';

/**
 * Custom edge type for React Flow 12.
 */
type SyncEdgeType = Edge<SyncEdgeData, 'sync'>;


/**
 * Edge color mapping based on sync status.
 */
const EDGE_COLORS: Record<string, string> = {
  healthy: '#22c55e', // green-500
  error: '#ef4444',   // red-500
  unknown: '#eab308', // yellow-500
};


/**
 * Custom edge component for visualizing sync relationships.
 *
 * Shows:
 * - Animated flow when sync is healthy
 * - Color based on sync status
 * - Label with sync statistics on hover
 */
const SyncEdge: React.FC<EdgeProps<SyncEdgeType>> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}) => {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 16,
  });

  const edgeColor = data ? EDGE_COLORS[data.status] || EDGE_COLORS.unknown : EDGE_COLORS.unknown;
  const isAnimated = data?.status === 'healthy';

  return (
    <>
      {/* Animated background path for healthy connections */}
      {isAnimated && (
        <BaseEdge
          id={`${id}-bg`}
          path={edgePath}
          style={{
            stroke: edgeColor,
            strokeWidth: 6,
            strokeOpacity: 0.15,
          }}
        />
      )}

      {/* Main edge path */}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: edgeColor,
          strokeWidth: selected ? 3 : 2,
          strokeDasharray: isAnimated ? '5 5' : undefined,
          animation: isAnimated ? 'dashdraw 0.5s linear infinite' : undefined,
        }}
        markerEnd="url(#arrow)"
      />

      {/* Edge label on selection */}
      {selected && data && (
        <EdgeLabelRenderer>
          <div
            className="absolute pointer-events-none px-2 py-1 rounded bg-gray-800 text-white text-xs shadow-lg"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
          >
            <div className="font-medium">{data.serversCount} servers, {data.agentsCount} agents</div>
            {data.lastSync && (
              <div className="text-gray-300 text-[10px]">
                Last: {new Date(data.lastSync).toLocaleTimeString()}
              </div>
            )}
          </div>
        </EdgeLabelRenderer>
      )}

      {/* CSS for animation */}
      <style>
        {`
          @keyframes dashdraw {
            from {
              stroke-dashoffset: 10;
            }
            to {
              stroke-dashoffset: 0;
            }
          }
        `}
      </style>
    </>
  );
};

export default memo(SyncEdge);
