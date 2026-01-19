import React, { useCallback, useMemo, useState } from 'react';
import {
  ReactFlow,
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import {
  PlusIcon,
  ArrowPathIcon,
  ArrowsPointingOutIcon,
  GlobeAltIcon,
  SparklesIcon,
  UserGroupIcon,
  ServerIcon,
  XMarkIcon,
  TrashIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  PauseCircleIcon,
} from '@heroicons/react/24/outline';

import { useTheme } from '../contexts/ThemeContext';
import RegistryNode, { UnifiedRegistryNodeData } from '../components/federation/RegistryNode';
import AddPeerModal from '../components/federation/AddPeerModal';
import FederationSourceModal from '../components/federation/FederationSourceModal';
import {
  useUnifiedFederationTopology,
  UnifiedTopologyNode,
  UnifiedTopologyEdge,
  PeerConfig,
} from '../hooks/useUnifiedFederationTopology';


/**
 * Custom node types for React Flow.
 */
const nodeTypes = {
  registry: RegistryNode,
};


/**
 * Get edge style based on status.
 */
function _getEdgeStyle(status: string): React.CSSProperties {
  const baseStyle: React.CSSProperties = {
    strokeWidth: 2,
  };

  switch (status) {
    case 'healthy':
      return { ...baseStyle, stroke: '#22c55e' };
    case 'error':
      return { ...baseStyle, stroke: '#ef4444' };
    case 'disabled':
      return { ...baseStyle, stroke: '#9ca3af', strokeDasharray: '5 5' };
    default:
      return { ...baseStyle, stroke: '#eab308' };
  }
}


/**
 * Convert API topology nodes to React Flow nodes.
 */
function _convertToFlowNodes(
  apiNodes: UnifiedTopologyNode[],
): Node<UnifiedRegistryNodeData>[] {
  return apiNodes.map((node) => ({
    id: node.id,
    type: 'registry',
    position: node.position,
    data: {
      id: node.id,
      type: node.type,
      name: node.name,
      label: node.name,
      status: node.status,
      enabled: node.enabled,
      endpoint: node.endpoint,
      serversCount: node.servers_count,
      agentsCount: node.agents_count,
      servers_count: node.servers_count,
      agents_count: node.agents_count,
      lastSync: node.last_sync,
      last_sync: node.last_sync,
      syncMode: node.sync_mode,
      sync_mode: node.sync_mode,
      syncOnStartup: node.sync_on_startup,
      sync_on_startup: node.sync_on_startup,
      isLocal: node.type === 'local',
    },
    draggable: true,
  }));
}


/**
 * Convert API topology edges to React Flow edges.
 */
function _convertToFlowEdges(apiEdges: UnifiedTopologyEdge[]): Edge[] {
  return apiEdges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    animated: edge.animated,
    style: _getEdgeStyle(edge.status),
    data: {
      status: edge.status,
      serversSynced: edge.servers_synced,
      agentsSynced: edge.agents_synced,
    },
  }));
}


/**
 * Format time since last sync.
 */
function _formatTimeSince(isoString: string | undefined | null): string {
  if (!isoString) return 'Never';

  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}


/**
 * Get status badge component.
 */
function _getStatusBadge(status: string): React.ReactNode {
  const baseClasses = 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium';

  switch (status) {
    case 'healthy':
      return (
        <span className={`${baseClasses} bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400`}>
          <CheckCircleIcon className="h-3 w-3 mr-1" />
          Healthy
        </span>
      );
    case 'error':
      return (
        <span className={`${baseClasses} bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400`}>
          <ExclamationCircleIcon className="h-3 w-3 mr-1" />
          Error
        </span>
      );
    case 'disabled':
      return (
        <span className={`${baseClasses} bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400`}>
          <PauseCircleIcon className="h-3 w-3 mr-1" />
          Disabled
        </span>
      );
    default:
      return (
        <span className={`${baseClasses} bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400`}>
          Unknown
        </span>
      );
  }
}


/**
 * Federation Map page component.
 *
 * Displays a visual topology of all federation sources:
 * - Local registry (center)
 * - Peer registries
 * - Anthropic MCP source
 * - ASOR agents source
 */
const FederationMap: React.FC = () => {
  const { theme } = useTheme();
  const isDarkMode = theme === 'dark';

  // Unified topology hook
  const {
    nodes: apiNodes,
    edges: apiEdges,
    metadata,
    loading,
    error,
    refreshTopology,
    syncPeer,
    syncAllPeers,
    addPeer,
    enablePeer,
    disablePeer,
    removePeer,
    syncAnthropic,
    updateAnthropicConfig,
    syncAsor,
    updateAsorConfig,
  } = useUnifiedFederationTopology();

  // React Flow state
  const flowNodes = useMemo(() => _convertToFlowNodes(apiNodes), [apiNodes]);
  const flowEdges = useMemo(() => _convertToFlowEdges(apiEdges), [apiEdges]);
  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges);

  // Selection state
  const [selectedNode, setSelectedNode] = useState<UnifiedTopologyNode | null>(null);

  // Modal state
  const [addPeerModalOpen, setAddPeerModalOpen] = useState(false);
  const [sourceModalOpen, setSourceModalOpen] = useState(false);
  const [sourceModalType, setSourceModalType] = useState<'anthropic' | 'asor'>('anthropic');

  // Sync nodes when API data changes
  React.useEffect(() => {
    setNodes(_convertToFlowNodes(apiNodes));
    setEdges(_convertToFlowEdges(apiEdges));
  }, [apiNodes, apiEdges, setNodes, setEdges]);

  /**
   * Handle node click to show details or open config modal.
   */
  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const apiNode = apiNodes.find((n) => n.id === node.id);
      if (!apiNode) return;

      // For Anthropic/ASOR, open config modal
      if (apiNode.type === 'anthropic') {
        setSourceModalType('anthropic');
        setSourceModalOpen(true);
      } else if (apiNode.type === 'asor') {
        setSourceModalType('asor');
        setSourceModalOpen(true);
      } else {
        // For local/peer, show details panel
        setSelectedNode(apiNode);
      }
    },
    [apiNodes],
  );

  /**
   * Handle peer sync.
   */
  const handlePeerSync = useCallback(async () => {
    if (!selectedNode || selectedNode.type !== 'peer') return;
    await syncPeer(selectedNode.id);
  }, [selectedNode, syncPeer]);

  /**
   * Handle peer enable.
   */
  const handlePeerEnable = useCallback(async () => {
    if (!selectedNode || selectedNode.type !== 'peer') return;
    await enablePeer(selectedNode.id);
  }, [selectedNode, enablePeer]);

  /**
   * Handle peer disable.
   */
  const handlePeerDisable = useCallback(async () => {
    if (!selectedNode || selectedNode.type !== 'peer') return;
    await disablePeer(selectedNode.id);
  }, [selectedNode, disablePeer]);

  /**
   * Handle peer remove.
   */
  const handlePeerRemove = useCallback(async () => {
    if (!selectedNode || selectedNode.type !== 'peer') return;
    if (window.confirm(`Are you sure you want to remove "${selectedNode.name}"?`)) {
      await removePeer(selectedNode.id);
      setSelectedNode(null);
    }
  }, [selectedNode, removePeer]);

  /**
   * Handle add peer.
   */
  const handleAddPeer = useCallback(
    async (config: PeerConfig) => {
      return addPeer(config);
    },
    [addPeer],
  );

  /**
   * Get selected node config for source modal.
   */
  const getSourceModalConfig = useCallback(() => {
    const sourceNode = apiNodes.find((n) => n.type === sourceModalType);
    return {
      enabled: sourceNode?.enabled ?? false,
      endpoint: sourceNode?.endpoint ?? null,
      syncOnStartup: sourceNode?.sync_on_startup ?? false,
      serversCount: sourceNode?.servers_count ?? 0,
      agentsCount: sourceNode?.agents_count ?? 0,
    };
  }, [apiNodes, sourceModalType]);

  // Get type icon for details panel
  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'local':
        return <ServerIcon className="h-5 w-5" />;
      case 'peer':
        return <GlobeAltIcon className="h-5 w-5" />;
      case 'anthropic':
        return <SparklesIcon className="h-5 w-5" />;
      case 'asor':
        return <UserGroupIcon className="h-5 w-5" />;
      default:
        return <ServerIcon className="h-5 w-5" />;
    }
  };

  // MiniMap node color function
  const miniMapNodeColor = (node: Node): string => {
    const data = node.data as UnifiedRegistryNodeData;
    switch (data.type) {
      case 'local':
        return '#7c3aed';
      case 'peer':
        return '#3b82f6';
      case 'anthropic':
        return '#f59e0b';
      case 'asor':
        return '#06b6d4';
      default:
        return '#9ca3af';
    }
  };

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <div className="flex-none px-6 py-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              Federation Map
            </h1>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              View and manage federated registry sources
            </p>
          </div>
          <div className="flex items-center space-x-3">
            {/* Stats */}
            {metadata && (
              <div className="text-sm text-gray-500 dark:text-gray-400 mr-4">
                <span className="font-medium text-gray-700 dark:text-gray-300">
                  {metadata.enabled_sources}
                </span>
                /{metadata.total_sources} sources |{' '}
                <span className="font-medium text-gray-700 dark:text-gray-300">
                  {metadata.total_servers}
                </span>{' '}
                servers |{' '}
                <span className="font-medium text-gray-700 dark:text-gray-300">
                  {metadata.total_agents}
                </span>{' '}
                agents
              </div>
            )}
            {/* Actions */}
            <button
              onClick={refreshTopology}
              disabled={loading}
              className="inline-flex items-center px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
            >
              <ArrowPathIcon className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
            <button
              onClick={syncAllPeers}
              disabled={loading}
              className="inline-flex items-center px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
            >
              <ArrowsPointingOutIcon className="h-4 w-4 mr-2" />
              Sync All Peers
            </button>
            <button
              onClick={() => setAddPeerModalOpen(true)}
              className="inline-flex items-center px-3 py-2 border border-transparent rounded-lg text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 transition-colors"
            >
              <PlusIcon className="h-4 w-4 mr-2" />
              Add Peer
            </button>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* React Flow canvas */}
        <div className="flex-1 relative">
          {error && (
            <div className="absolute top-4 left-4 right-4 z-10 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400">
              {error}
            </div>
          )}

          {loading && apiNodes.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto mb-4"></div>
                <p className="text-gray-500 dark:text-gray-400">Loading federation topology...</p>
              </div>
            </div>
          ) : apiNodes.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md">
                <GlobeAltIcon className="h-16 w-16 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                  No Federation Sources
                </h3>
                <p className="text-gray-500 dark:text-gray-400 mb-4">
                  Get started by adding peer registries or enabling Anthropic/ASOR federation.
                </p>
                <button
                  onClick={() => setAddPeerModalOpen(true)}
                  className="inline-flex items-center px-4 py-2 border border-transparent rounded-lg text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 transition-colors"
                >
                  <PlusIcon className="h-4 w-4 mr-2" />
                  Add Peer Registry
                </button>
              </div>
            </div>
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={onNodeClick}
              fitView
              fitViewOptions={{ padding: 0.2 }}
              minZoom={0.5}
              maxZoom={2}
              className={isDarkMode ? 'dark' : ''}
            >
              <Background
                variant={BackgroundVariant.Dots}
                gap={20}
                size={1}
                color={isDarkMode ? '#374151' : '#e5e7eb'}
              />
              <Controls className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg" />
              <MiniMap
                nodeColor={miniMapNodeColor}
                maskColor={isDarkMode ? 'rgba(0,0,0,0.5)' : 'rgba(0,0,0,0.1)'}
                className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg"
              />
            </ReactFlow>
          )}
        </div>

        {/* Details panel for peer/local nodes */}
        {selectedNode && selectedNode.type !== 'anthropic' && selectedNode.type !== 'asor' && (
          <div className="w-80 flex-none bg-white dark:bg-gray-800 border-l border-gray-200 dark:border-gray-700 overflow-y-auto">
            <div className="p-4">
              {/* Header */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-2">
                  <div
                    className={`p-2 rounded-lg ${
                      selectedNode.type === 'local'
                        ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400'
                        : 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
                    }`}
                  >
                    {getTypeIcon(selectedNode.type)}
                  </div>
                  <div>
                    <h3 className="font-medium text-gray-900 dark:text-white">
                      {selectedNode.name}
                    </h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">
                      {selectedNode.type} Registry
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedNode(null)}
                  className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300"
                >
                  <XMarkIcon className="h-5 w-5" />
                </button>
              </div>

              {/* Status */}
              <div className="mb-4">
                {_getStatusBadge(selectedNode.status)}
              </div>

              {/* Details */}
              <div className="space-y-3 mb-6">
                {selectedNode.endpoint && (
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-1">
                      Endpoint
                    </p>
                    <p className="text-sm text-gray-900 dark:text-white break-all">
                      {selectedNode.endpoint}
                    </p>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-1">
                      Servers
                    </p>
                    <p className="text-lg font-semibold text-gray-900 dark:text-white">
                      {selectedNode.servers_count}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-1">
                      Agents
                    </p>
                    <p className="text-lg font-semibold text-gray-900 dark:text-white">
                      {selectedNode.agents_count}
                    </p>
                  </div>
                </div>
                {selectedNode.last_sync && (
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-1">
                      Last Sync
                    </p>
                    <p className="text-sm text-gray-900 dark:text-white">
                      {_formatTimeSince(selectedNode.last_sync)}
                    </p>
                  </div>
                )}
                {selectedNode.sync_mode && (
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase mb-1">
                      Sync Mode
                    </p>
                    <p className="text-sm text-gray-900 dark:text-white capitalize">
                      {selectedNode.sync_mode}
                    </p>
                  </div>
                )}
              </div>

              {/* Actions (only for peers) */}
              {selectedNode.type === 'peer' && (
                <div className="space-y-2">
                  <button
                    onClick={handlePeerSync}
                    disabled={!selectedNode.enabled}
                    className="w-full inline-flex items-center justify-center px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
                  >
                    <ArrowPathIcon className="h-4 w-4 mr-2" />
                    Sync Now
                  </button>
                  {selectedNode.enabled ? (
                    <button
                      onClick={handlePeerDisable}
                      className="w-full inline-flex items-center justify-center px-4 py-2 border border-yellow-300 dark:border-yellow-600 rounded-lg text-sm font-medium text-yellow-700 dark:text-yellow-300 bg-yellow-50 dark:bg-yellow-900/20 hover:bg-yellow-100 dark:hover:bg-yellow-900/30 transition-colors"
                    >
                      <PauseCircleIcon className="h-4 w-4 mr-2" />
                      Disable
                    </button>
                  ) : (
                    <button
                      onClick={handlePeerEnable}
                      className="w-full inline-flex items-center justify-center px-4 py-2 border border-green-300 dark:border-green-600 rounded-lg text-sm font-medium text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/20 hover:bg-green-100 dark:hover:bg-green-900/30 transition-colors"
                    >
                      <CheckCircleIcon className="h-4 w-4 mr-2" />
                      Enable
                    </button>
                  )}
                  <button
                    onClick={handlePeerRemove}
                    className="w-full inline-flex items-center justify-center px-4 py-2 border border-red-300 dark:border-red-600 rounded-lg text-sm font-medium text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                  >
                    <TrashIcon className="h-4 w-4 mr-2" />
                    Remove
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Add Peer Modal */}
      <AddPeerModal
        isOpen={addPeerModalOpen}
        onClose={() => setAddPeerModalOpen(false)}
        onAdd={handleAddPeer}
      />

      {/* Federation Source Config Modal (Anthropic/ASOR) */}
      <FederationSourceModal
        isOpen={sourceModalOpen}
        onClose={() => setSourceModalOpen(false)}
        sourceType={sourceModalType}
        currentConfig={getSourceModalConfig()}
        onSync={sourceModalType === 'anthropic' ? syncAnthropic : syncAsor}
        onUpdateConfig={
          sourceModalType === 'anthropic' ? updateAnthropicConfig : updateAsorConfig
        }
      />
    </div>
  );
};

export default FederationMap;
