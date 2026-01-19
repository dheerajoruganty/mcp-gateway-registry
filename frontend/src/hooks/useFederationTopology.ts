import { useState, useEffect, useCallback } from 'react';

/**
 * Node data structure for React Flow visualization.
 * Index signature required for React Flow 12 Node type compatibility.
 */
export interface RegistryNodeData {
  label: string;
  isLocal: boolean;
  enabled: boolean;
  status: 'healthy' | 'error' | 'disabled' | 'unknown';
  endpoint: string | null;
  serversCount: number;
  agentsCount: number;
  lastSync?: string;
  syncMode?: string;
  syncInterval?: number;
  [key: string]: unknown;
}

/**
 * Edge data structure for React Flow visualization.
 * Index signature required for React Flow 12 Edge type compatibility.
 */
export interface SyncEdgeData {
  status: 'healthy' | 'error' | 'unknown';
  lastSync: string | null;
  serversCount: number;
  agentsCount: number;
  [key: string]: unknown;
}

/**
 * Node structure matching React Flow's expected format.
 */
export interface TopologyNode {
  id: string;
  type: string;
  data: RegistryNodeData;
  position: { x: number; y: number };
}

/**
 * Edge structure matching React Flow's expected format.
 */
export interface TopologyEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  animated: boolean;
  data: SyncEdgeData;
}

/**
 * Topology response from the API.
 */
export interface TopologyResponse {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

/**
 * Peer configuration for creating/updating peers.
 */
export interface PeerConfig {
  peer_id: string;
  name: string;
  endpoint: string;
  enabled?: boolean;
  sync_mode?: 'all' | 'whitelist' | 'tag_filter';
  sync_interval_minutes?: number;
  whitelist_servers?: string[];
  whitelist_agents?: string[];
  tag_filters?: string[];
  // Authentication configuration
  auth_type?: 'none' | 'api_key' | 'oauth2';
  api_key?: string;
  oauth2_token_endpoint?: string;
  oauth2_client_id?: string;
  oauth2_client_secret?: string;
}

/**
 * Hook return type.
 */
interface UseFederationTopologyReturn {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  loading: boolean;
  error: string | null;
  refreshTopology: () => Promise<void>;
  syncPeer: (peerId: string) => Promise<boolean>;
  syncAllPeers: () => Promise<boolean>;
  addPeer: (config: PeerConfig) => Promise<boolean>;
  updatePeer: (peerId: string, updates: Partial<PeerConfig>) => Promise<boolean>;
  removePeer: (peerId: string) => Promise<boolean>;
  enablePeer: (peerId: string) => Promise<boolean>;
  disablePeer: (peerId: string) => Promise<boolean>;
}


/**
 * Internal fetch wrapper with error handling.
 */
async function _fetchApi<T>(
  url: string,
  options?: RequestInit,
): Promise<{ data: T | null; error: string | null }> {
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage = errorData.detail || `HTTP ${response.status}: ${response.statusText}`;
      return { data: null, error: errorMessage };
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return { data: null, error: null };
    }

    const data = await response.json();
    return { data, error: null };
  } catch (err) {
    const errorMessage = err instanceof Error ? err.message : 'Network error';
    return { data: null, error: errorMessage };
  }
}


/**
 * Hook for managing federation topology data.
 *
 * Uses native fetch API for all requests.
 * Provides methods for CRUD operations on peers and sync triggers.
 */
export function useFederationTopology(): UseFederationTopologyReturn {
  const [nodes, setNodes] = useState<TopologyNode[]>([]);
  const [edges, setEdges] = useState<TopologyEdge[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  /**
   * Fetch topology data from the API.
   */
  const refreshTopology = useCallback(async () => {
    setLoading(true);
    setError(null);

    const { data, error: fetchError } = await _fetchApi<TopologyResponse>(
      '/api/v1/peers/topology',
    );

    if (fetchError) {
      setError(fetchError);
      setNodes([]);
      setEdges([]);
    } else if (data) {
      setNodes(data.nodes);
      setEdges(data.edges);
    }

    setLoading(false);
  }, []);

  /**
   * Trigger sync for a specific peer.
   */
  const syncPeer = useCallback(async (peerId: string): Promise<boolean> => {
    const { error: syncError } = await _fetchApi(
      `/api/v1/peers/${encodeURIComponent(peerId)}/sync`,
      { method: 'POST' },
    );

    if (syncError) {
      console.error(`Failed to sync peer ${peerId}:`, syncError);
      return false;
    }

    // Refresh topology after sync
    await refreshTopology();
    return true;
  }, [refreshTopology]);

  /**
   * Trigger sync for all enabled peers.
   */
  const syncAllPeers = useCallback(async (): Promise<boolean> => {
    const { error: syncError } = await _fetchApi(
      '/api/v1/peers/sync',
      { method: 'POST' },
    );

    if (syncError) {
      console.error('Failed to sync all peers:', syncError);
      return false;
    }

    // Refresh topology after sync
    await refreshTopology();
    return true;
  }, [refreshTopology]);

  /**
   * Add a new peer.
   */
  const addPeer = useCallback(async (config: PeerConfig): Promise<boolean> => {
    const { error: addError } = await _fetchApi(
      '/api/v1/peers',
      {
        method: 'POST',
        body: JSON.stringify(config),
      },
    );

    if (addError) {
      console.error('Failed to add peer:', addError);
      setError(addError);
      return false;
    }

    // Refresh topology after adding peer
    await refreshTopology();
    return true;
  }, [refreshTopology]);

  /**
   * Update an existing peer.
   */
  const updatePeer = useCallback(async (
    peerId: string,
    updates: Partial<PeerConfig>,
  ): Promise<boolean> => {
    const { error: updateError } = await _fetchApi(
      `/api/v1/peers/${encodeURIComponent(peerId)}`,
      {
        method: 'PUT',
        body: JSON.stringify(updates),
      },
    );

    if (updateError) {
      console.error(`Failed to update peer ${peerId}:`, updateError);
      setError(updateError);
      return false;
    }

    // Refresh topology after update
    await refreshTopology();
    return true;
  }, [refreshTopology]);

  /**
   * Remove a peer.
   */
  const removePeer = useCallback(async (peerId: string): Promise<boolean> => {
    const { error: removeError } = await _fetchApi(
      `/api/v1/peers/${encodeURIComponent(peerId)}`,
      { method: 'DELETE' },
    );

    if (removeError) {
      console.error(`Failed to remove peer ${peerId}:`, removeError);
      setError(removeError);
      return false;
    }

    // Refresh topology after removal
    await refreshTopology();
    return true;
  }, [refreshTopology]);

  /**
   * Enable a peer.
   */
  const enablePeer = useCallback(async (peerId: string): Promise<boolean> => {
    const { error: enableError } = await _fetchApi(
      `/api/v1/peers/${encodeURIComponent(peerId)}/enable`,
      { method: 'POST' },
    );

    if (enableError) {
      console.error(`Failed to enable peer ${peerId}:`, enableError);
      setError(enableError);
      return false;
    }

    // Refresh topology after enable
    await refreshTopology();
    return true;
  }, [refreshTopology]);

  /**
   * Disable a peer.
   */
  const disablePeer = useCallback(async (peerId: string): Promise<boolean> => {
    const { error: disableError } = await _fetchApi(
      `/api/v1/peers/${encodeURIComponent(peerId)}/disable`,
      { method: 'POST' },
    );

    if (disableError) {
      console.error(`Failed to disable peer ${peerId}:`, disableError);
      setError(disableError);
      return false;
    }

    // Refresh topology after disable
    await refreshTopology();
    return true;
  }, [refreshTopology]);

  // Initial load
  useEffect(() => {
    refreshTopology();
  }, [refreshTopology]);

  return {
    nodes,
    edges,
    loading,
    error,
    refreshTopology,
    syncPeer,
    syncAllPeers,
    addPeer,
    updatePeer,
    removePeer,
    enablePeer,
    disablePeer,
  };
}
