import { useState, useEffect, useCallback } from 'react';

/**
 * Federation source types matching backend enum.
 */
export type FederationSourceType = 'local' | 'peer' | 'anthropic' | 'asor';

/**
 * Unified node data structure for all federation source types.
 * Index signature required for React Flow 12 Node type compatibility.
 */
export interface UnifiedNodeData {
  id: string;
  type: FederationSourceType;
  name: string;
  status: 'healthy' | 'error' | 'disabled' | 'unknown';
  enabled: boolean;
  endpoint: string | null;
  serversCount: number;
  agentsCount: number;
  lastSync?: string | null;
  syncMode?: string | null;
  syncIntervalMinutes?: number | null;
  syncOnStartup?: boolean | null;
  position: { x: number; y: number };
  [key: string]: unknown;
}

/**
 * Edge data structure for federation topology.
 */
export interface UnifiedEdgeData {
  status: 'healthy' | 'error' | 'disabled' | 'unknown';
  serversSynced: number;
  agentsSynced: number;
  [key: string]: unknown;
}

/**
 * Node structure matching the API response.
 */
export interface UnifiedTopologyNode {
  id: string;
  type: FederationSourceType;
  name: string;
  status: 'healthy' | 'error' | 'disabled' | 'unknown';
  enabled: boolean;
  endpoint: string | null;
  servers_count: number;
  agents_count: number;
  last_sync: string | null;
  sync_mode: string | null;
  sync_interval_minutes: number | null;
  sync_on_startup: boolean | null;
  position: { x: number; y: number };
}

/**
 * Edge structure matching the API response.
 */
export interface UnifiedTopologyEdge {
  id: string;
  source: string;
  target: string;
  status: 'healthy' | 'error' | 'disabled' | 'unknown';
  animated: boolean;
  servers_synced: number;
  agents_synced: number;
}

/**
 * Topology metadata from API.
 */
export interface TopologyMetadata {
  total_sources: number;
  enabled_sources: number;
  total_servers: number;
  total_agents: number;
  last_updated: string;
}

/**
 * Full topology response from API.
 */
export interface UnifiedTopologyResponse {
  nodes: UnifiedTopologyNode[];
  edges: UnifiedTopologyEdge[];
  metadata: TopologyMetadata;
}

/**
 * Sync result from federation source sync.
 */
export interface FederationSyncResult {
  success: boolean;
  source: string;
  servers_synced: number;
  agents_synced: number;
  duration_seconds: number;
  error_message?: string;
  synced_at: string;
}

/**
 * Configuration update for federation source.
 */
export interface FederationSourceConfigUpdate {
  enabled?: boolean;
  endpoint?: string;
  sync_on_startup?: boolean;
  auth_env_var?: string;
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
  auth_type?: 'none' | 'api_key' | 'oauth2';
  api_key?: string;
  oauth2_token_endpoint?: string;
  oauth2_client_id?: string;
  oauth2_client_secret?: string;
}

/**
 * Hook return type.
 */
interface UseUnifiedFederationTopologyReturn {
  // Data
  nodes: UnifiedTopologyNode[];
  edges: UnifiedTopologyEdge[];
  metadata: TopologyMetadata | null;
  loading: boolean;
  error: string | null;

  // Refresh
  refreshTopology: () => Promise<void>;

  // Peer operations (from existing hook)
  syncPeer: (peerId: string) => Promise<boolean>;
  syncAllPeers: () => Promise<boolean>;
  addPeer: (config: PeerConfig) => Promise<boolean>;
  updatePeer: (peerId: string, updates: Partial<PeerConfig>) => Promise<boolean>;
  removePeer: (peerId: string) => Promise<boolean>;
  enablePeer: (peerId: string) => Promise<boolean>;
  disablePeer: (peerId: string) => Promise<boolean>;

  // Anthropic operations
  syncAnthropic: () => Promise<FederationSyncResult | null>;
  updateAnthropicConfig: (updates: FederationSourceConfigUpdate) => Promise<boolean>;

  // ASOR operations
  syncAsor: () => Promise<FederationSyncResult | null>;
  updateAsorConfig: (updates: FederationSourceConfigUpdate) => Promise<boolean>;
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
 * Hook for managing unified federation topology data.
 *
 * Fetches from /api/v1/federation/unified-topology and provides
 * methods for all federation sources (peers, Anthropic, ASOR).
 */
export function useUnifiedFederationTopology(): UseUnifiedFederationTopologyReturn {
  const [nodes, setNodes] = useState<UnifiedTopologyNode[]>([]);
  const [edges, setEdges] = useState<UnifiedTopologyEdge[]>([]);
  const [metadata, setMetadata] = useState<TopologyMetadata | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  /**
   * Fetch unified topology data from the API.
   */
  const refreshTopology = useCallback(async () => {
    setLoading(true);
    setError(null);

    const { data, error: fetchError } = await _fetchApi<UnifiedTopologyResponse>(
      '/api/v1/federation/unified-topology',
    );

    if (fetchError) {
      setError(fetchError);
      setNodes([]);
      setEdges([]);
      setMetadata(null);
    } else if (data) {
      setNodes(data.nodes);
      setEdges(data.edges);
      setMetadata(data.metadata);
    }

    setLoading(false);
  }, []);

  // --- Peer Operations ---

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

    await refreshTopology();
    return true;
  }, [refreshTopology]);

  // --- Anthropic Operations ---

  /**
   * Trigger sync from Anthropic MCP registry.
   */
  const syncAnthropic = useCallback(async (): Promise<FederationSyncResult | null> => {
    const { data, error: syncError } = await _fetchApi<FederationSyncResult>(
      '/api/v1/federation/anthropic/sync',
      { method: 'POST' },
    );

    if (syncError) {
      console.error('Failed to sync Anthropic:', syncError);
      setError(syncError);
      return null;
    }

    await refreshTopology();
    return data;
  }, [refreshTopology]);

  /**
   * Update Anthropic federation configuration.
   */
  const updateAnthropicConfig = useCallback(async (
    updates: FederationSourceConfigUpdate,
  ): Promise<boolean> => {
    const { error: updateError } = await _fetchApi(
      '/api/v1/federation/anthropic/config',
      {
        method: 'PUT',
        body: JSON.stringify(updates),
      },
    );

    if (updateError) {
      console.error('Failed to update Anthropic config:', updateError);
      setError(updateError);
      return false;
    }

    await refreshTopology();
    return true;
  }, [refreshTopology]);

  // --- ASOR Operations ---

  /**
   * Trigger sync from ASOR.
   */
  const syncAsor = useCallback(async (): Promise<FederationSyncResult | null> => {
    const { data, error: syncError } = await _fetchApi<FederationSyncResult>(
      '/api/v1/federation/asor/sync',
      { method: 'POST' },
    );

    if (syncError) {
      console.error('Failed to sync ASOR:', syncError);
      setError(syncError);
      return null;
    }

    await refreshTopology();
    return data;
  }, [refreshTopology]);

  /**
   * Update ASOR federation configuration.
   */
  const updateAsorConfig = useCallback(async (
    updates: FederationSourceConfigUpdate,
  ): Promise<boolean> => {
    const { error: updateError } = await _fetchApi(
      '/api/v1/federation/asor/config',
      {
        method: 'PUT',
        body: JSON.stringify(updates),
      },
    );

    if (updateError) {
      console.error('Failed to update ASOR config:', updateError);
      setError(updateError);
      return false;
    }

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
    metadata,
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
    syncAnthropic,
    updateAnthropicConfig,
    syncAsor,
    updateAsorConfig,
  };
}
