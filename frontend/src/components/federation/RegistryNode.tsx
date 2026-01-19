import React, { memo } from 'react';
import { Handle, Position, NodeProps, Node } from '@xyflow/react';
import {
  ServerIcon,
  GlobeAltIcon,
  SparklesIcon,
  UserGroupIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  PauseCircleIcon,
  QuestionMarkCircleIcon,
} from '@heroicons/react/24/outline';

/**
 * Federation source types.
 */
type FederationSourceType = 'local' | 'peer' | 'anthropic' | 'asor';

/**
 * Unified node data structure for all federation source types.
 */
export interface UnifiedRegistryNodeData {
  id?: string;
  type?: FederationSourceType;
  name: string;
  label?: string;
  status: 'healthy' | 'error' | 'disabled' | 'unknown';
  enabled: boolean;
  endpoint?: string | null;
  serversCount?: number;
  agentsCount?: number;
  servers_count?: number;
  agents_count?: number;
  lastSync?: string | null;
  last_sync?: string | null;
  syncMode?: string | null;
  sync_mode?: string | null;
  syncOnStartup?: boolean | null;
  sync_on_startup?: boolean | null;
  isLocal?: boolean;
  [key: string]: unknown;
}

/**
 * Custom node type for React Flow 12.
 */
type RegistryNodeType = Node<UnifiedRegistryNodeData, 'registry'>;


/**
 * Type-specific styling configuration.
 */
interface TypeStyleConfig {
  bgColor: string;
  borderColor: string;
  iconBg: string;
  iconColor: string;
  labelColor: string;
  badge: string;
  badgeBg: string;
  badgeText: string;
}


/**
 * Get styling configuration based on source type.
 */
function _getTypeStyles(sourceType: FederationSourceType): TypeStyleConfig {
  switch (sourceType) {
    case 'local':
      return {
        bgColor: 'bg-purple-50 dark:bg-purple-900/20',
        borderColor: 'border-purple-500',
        iconBg: 'bg-purple-100 dark:bg-purple-900/30',
        iconColor: 'text-purple-600 dark:text-purple-400',
        labelColor: 'text-purple-700 dark:text-purple-300',
        badge: 'Local',
        badgeBg: 'bg-purple-100 dark:bg-purple-900/50',
        badgeText: 'text-purple-700 dark:text-purple-300',
      };
    case 'peer':
      return {
        bgColor: 'bg-blue-50 dark:bg-blue-900/20',
        borderColor: 'border-blue-500',
        iconBg: 'bg-blue-100 dark:bg-blue-900/30',
        iconColor: 'text-blue-600 dark:text-blue-400',
        labelColor: 'text-blue-700 dark:text-blue-300',
        badge: 'Peer',
        badgeBg: 'bg-blue-100 dark:bg-blue-900/50',
        badgeText: 'text-blue-700 dark:text-blue-300',
      };
    case 'anthropic':
      return {
        bgColor: 'bg-amber-50 dark:bg-amber-900/20',
        borderColor: 'border-amber-500',
        iconBg: 'bg-amber-100 dark:bg-amber-900/30',
        iconColor: 'text-amber-600 dark:text-amber-400',
        labelColor: 'text-amber-700 dark:text-amber-300',
        badge: 'Anthropic MCP',
        badgeBg: 'bg-amber-100 dark:bg-amber-900/50',
        badgeText: 'text-amber-700 dark:text-amber-300',
      };
    case 'asor':
      return {
        bgColor: 'bg-cyan-50 dark:bg-cyan-900/20',
        borderColor: 'border-cyan-500',
        iconBg: 'bg-cyan-100 dark:bg-cyan-900/30',
        iconColor: 'text-cyan-600 dark:text-cyan-400',
        labelColor: 'text-cyan-700 dark:text-cyan-300',
        badge: 'ASOR',
        badgeBg: 'bg-cyan-100 dark:bg-cyan-900/50',
        badgeText: 'text-cyan-700 dark:text-cyan-300',
      };
    default:
      return {
        bgColor: 'bg-gray-50 dark:bg-gray-800',
        borderColor: 'border-gray-400',
        iconBg: 'bg-gray-100 dark:bg-gray-700',
        iconColor: 'text-gray-600 dark:text-gray-400',
        labelColor: 'text-gray-700 dark:text-gray-300',
        badge: 'Unknown',
        badgeBg: 'bg-gray-100 dark:bg-gray-700',
        badgeText: 'text-gray-600 dark:text-gray-400',
      };
  }
}


/**
 * Status indicator colors mapping.
 */
const STATUS_COLORS: Record<string, { border: string; icon: string }> = {
  healthy: {
    border: 'border-green-500',
    icon: 'text-green-500',
  },
  error: {
    border: 'border-red-500',
    icon: 'text-red-500',
  },
  disabled: {
    border: 'border-gray-400',
    icon: 'text-gray-400',
  },
  unknown: {
    border: 'border-yellow-500',
    icon: 'text-yellow-500',
  },
};


/**
 * Get icon component based on source type.
 */
function _getSourceIcon(sourceType: FederationSourceType, className: string): React.ReactNode {
  switch (sourceType) {
    case 'local':
      return <ServerIcon className={className} />;
    case 'peer':
      return <GlobeAltIcon className={className} />;
    case 'anthropic':
      return <SparklesIcon className={className} />;
    case 'asor':
      return <UserGroupIcon className={className} />;
    default:
      return <ServerIcon className={className} />;
  }
}


/**
 * Get status icon component based on status.
 */
function _getStatusIcon(status: string): React.ReactNode {
  const iconClass = `h-4 w-4 ${STATUS_COLORS[status]?.icon || STATUS_COLORS.unknown.icon}`;

  switch (status) {
    case 'healthy':
      return <CheckCircleIcon className={iconClass} />;
    case 'error':
      return <ExclamationCircleIcon className={iconClass} />;
    case 'disabled':
      return <PauseCircleIcon className={iconClass} />;
    default:
      return <QuestionMarkCircleIcon className={iconClass} />;
  }
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
 * Determine source type from node data.
 */
function _getSourceType(data: UnifiedRegistryNodeData): FederationSourceType {
  // Check explicit type field first
  if (data.type) {
    return data.type;
  }

  // Fall back to isLocal check for backwards compatibility
  if (data.isLocal) {
    return 'local';
  }

  return 'peer';
}


/**
 * Custom node component for registry visualization in React Flow.
 *
 * Displays registry information including:
 * - Registry name with source type icon
 * - Status indicator
 * - Server/agent counts
 * - Last sync time
 * - Source type badge
 */
const RegistryNode: React.FC<NodeProps<RegistryNodeType>> = ({ data, selected }) => {
  const sourceType = _getSourceType(data);
  const typeStyles = _getTypeStyles(sourceType);
  const statusColors = STATUS_COLORS[data.status] || STATUS_COLORS.unknown;
  const isLocal = sourceType === 'local';

  // Get counts (handle both snake_case and camelCase)
  const serversCount = data.serversCount ?? data.servers_count ?? 0;
  const agentsCount = data.agentsCount ?? data.agents_count ?? 0;
  const lastSync = data.lastSync ?? data.last_sync;

  // Use status border if not disabled, otherwise use type border
  const borderColor = data.status === 'disabled'
    ? 'border-gray-400'
    : (data.enabled ? statusColors.border : 'border-gray-400');

  return (
    <div
      className={`
        px-4 py-3 rounded-lg border-2 shadow-md transition-all duration-200
        ${typeStyles.bgColor} ${borderColor}
        ${selected ? 'ring-2 ring-purple-500 ring-offset-2 dark:ring-offset-gray-900' : ''}
        min-w-[180px] cursor-pointer hover:shadow-lg
      `}
    >
      {/* Source handle (top) - for incoming connections */}
      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-gray-400 border-2 border-white dark:border-gray-800"
      />

      {/* Header with icon and name */}
      <div className="flex items-center space-x-2 mb-2">
        <div className={`p-1.5 rounded ${typeStyles.iconBg}`}>
          {_getSourceIcon(sourceType, `h-5 w-5 ${typeStyles.iconColor}`)}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className={`text-sm font-semibold truncate ${typeStyles.labelColor}`}>
            {data.name || data.label || 'Unknown'}
          </h3>
        </div>
      </div>

      {/* Status row */}
      <div className="flex items-center justify-between text-xs mb-2">
        <div className="flex items-center space-x-1">
          {_getStatusIcon(data.status)}
          <span className="text-gray-600 dark:text-gray-400 capitalize">
            {data.status}
          </span>
        </div>
        {!isLocal && lastSync && (
          <span className="text-gray-500 dark:text-gray-400">
            {_formatTimeSince(lastSync)}
          </span>
        )}
      </div>

      {/* Stats row - show for non-local nodes or if counts are available */}
      {(!isLocal || serversCount > 0 || agentsCount > 0) && (
        <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 pt-2 border-t border-gray-200 dark:border-gray-700">
          <span>{serversCount} servers</span>
          <span>{agentsCount} agents</span>
        </div>
      )}

      {/* Source type badge */}
      <div className={`mt-2 text-xs ${typeStyles.badgeBg} ${typeStyles.badgeText} px-2 py-1 rounded text-center`}>
        {typeStyles.badge}
      </div>

      {/* Target handle (bottom) - for outgoing connections */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-gray-400 border-2 border-white dark:border-gray-800"
      />
    </div>
  );
};

export default memo(RegistryNode);
