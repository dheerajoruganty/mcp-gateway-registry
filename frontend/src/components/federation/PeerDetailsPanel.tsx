import React, { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import {
  XMarkIcon,
  ArrowPathIcon,
  TrashIcon,
  PlayIcon,
  PauseIcon,
  ServerIcon,
  ClockIcon,
  CubeIcon,
  LinkIcon,
} from '@heroicons/react/24/outline';
import { RegistryNodeData } from '../../hooks/useFederationTopology';


interface PeerDetailsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  peerId: string | null;
  data: RegistryNodeData | null;
  onSync: (peerId: string) => Promise<void>;
  onEnable: (peerId: string) => Promise<void>;
  onDisable: (peerId: string) => Promise<void>;
  onRemove: (peerId: string) => Promise<void>;
}


/**
 * Format timestamp to readable string.
 */
function _formatTime(isoString: string | undefined): string {
  if (!isoString) return 'Never';
  const date = new Date(isoString);
  return date.toLocaleString();
}


/**
 * Get status badge styles.
 */
function _getStatusBadge(status: string): { bg: string; text: string; label: string } {
  switch (status) {
    case 'healthy':
      return {
        bg: 'bg-green-100 dark:bg-green-900/30',
        text: 'text-green-700 dark:text-green-400',
        label: 'Healthy',
      };
    case 'error':
      return {
        bg: 'bg-red-100 dark:bg-red-900/30',
        text: 'text-red-700 dark:text-red-400',
        label: 'Error',
      };
    case 'disabled':
      return {
        bg: 'bg-gray-100 dark:bg-gray-700',
        text: 'text-gray-700 dark:text-gray-400',
        label: 'Disabled',
      };
    default:
      return {
        bg: 'bg-yellow-100 dark:bg-yellow-900/30',
        text: 'text-yellow-700 dark:text-yellow-400',
        label: 'Unknown',
      };
  }
}


/**
 * Side panel component showing detailed peer information.
 *
 * Displays:
 * - Peer status and endpoint
 * - Sync statistics
 * - Action buttons (sync, enable/disable, remove)
 */
const PeerDetailsPanel: React.FC<PeerDetailsPanelProps> = ({
  isOpen,
  onClose,
  peerId,
  data,
  onSync,
  onEnable,
  onDisable,
  onRemove,
}) => {
  const [syncing, setSyncing] = React.useState(false);
  const [actionLoading, setActionLoading] = React.useState<string | null>(null);

  if (!peerId || !data) return null;

  const statusBadge = _getStatusBadge(data.status);
  const isLocal = data.isLocal;

  const handleSync = async () => {
    setSyncing(true);
    await onSync(peerId);
    setSyncing(false);
  };

  const handleEnable = async () => {
    setActionLoading('enable');
    await onEnable(peerId);
    setActionLoading(null);
  };

  const handleDisable = async () => {
    setActionLoading('disable');
    await onDisable(peerId);
    setActionLoading(null);
  };

  const handleRemove = async () => {
    if (window.confirm(`Are you sure you want to remove "${data.label}"? This action cannot be undone.`)) {
      setActionLoading('remove');
      await onRemove(peerId);
      setActionLoading(null);
      onClose();
    }
  };

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-40" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black bg-opacity-10 dark:bg-opacity-30" />
        </Transition.Child>

        <div className="fixed inset-y-0 right-0 flex max-w-full">
          <Transition.Child
            as={Fragment}
            enter="transform transition ease-in-out duration-300"
            enterFrom="translate-x-full"
            enterTo="translate-x-0"
            leave="transform transition ease-in-out duration-300"
            leaveFrom="translate-x-0"
            leaveTo="translate-x-full"
          >
            <Dialog.Panel className="w-screen max-w-sm">
              <div className="flex h-full flex-col overflow-y-auto bg-white dark:bg-gray-800 shadow-xl">
                {/* Header */}
                <div className="px-4 py-4 bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center space-x-3">
                      <div className={`p-2 rounded-lg ${isLocal ? 'bg-purple-100 dark:bg-purple-900/30' : 'bg-gray-100 dark:bg-gray-700'}`}>
                        <ServerIcon className={`h-6 w-6 ${isLocal ? 'text-purple-600 dark:text-purple-400' : 'text-gray-600 dark:text-gray-400'}`} />
                      </div>
                      <div>
                        <Dialog.Title className="text-lg font-medium text-gray-900 dark:text-white">
                          {data.label}
                        </Dialog.Title>
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${statusBadge.bg} ${statusBadge.text}`}>
                          {statusBadge.label}
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300"
                      onClick={onClose}
                    >
                      <XMarkIcon className="h-6 w-6" />
                    </button>
                  </div>
                </div>

                {/* Content */}
                <div className="flex-1 px-4 py-4 space-y-6">
                  {/* Endpoint info */}
                  {!isLocal && data.endpoint && (
                    <div>
                      <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2 flex items-center">
                        <LinkIcon className="h-4 w-4 mr-1" />
                        Endpoint
                      </h4>
                      <p className="text-sm text-gray-900 dark:text-white break-all bg-gray-50 dark:bg-gray-900 rounded-lg p-2">
                        {data.endpoint}
                      </p>
                    </div>
                  )}

                  {/* Sync statistics */}
                  {!isLocal && (
                    <div>
                      <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
                        Sync Statistics
                      </h4>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3 text-center">
                          <CubeIcon className="h-5 w-5 text-gray-400 mx-auto mb-1" />
                          <div className="text-xl font-semibold text-gray-900 dark:text-white">
                            {data.serversCount}
                          </div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">Servers</div>
                        </div>
                        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3 text-center">
                          <ServerIcon className="h-5 w-5 text-gray-400 mx-auto mb-1" />
                          <div className="text-xl font-semibold text-gray-900 dark:text-white">
                            {data.agentsCount}
                          </div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">Agents</div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Last sync time */}
                  {!isLocal && (
                    <div>
                      <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2 flex items-center">
                        <ClockIcon className="h-4 w-4 mr-1" />
                        Last Sync
                      </h4>
                      <p className="text-sm text-gray-900 dark:text-white">
                        {_formatTime(data.lastSync)}
                      </p>
                    </div>
                  )}

                  {/* Sync configuration */}
                  {!isLocal && data.syncMode && (
                    <div>
                      <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
                        Configuration
                      </h4>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-gray-500 dark:text-gray-400">Mode</span>
                          <span className="text-gray-900 dark:text-white capitalize">{data.syncMode}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-500 dark:text-gray-400">Interval</span>
                          <span className="text-gray-900 dark:text-white">{data.syncInterval} min</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Local registry message */}
                  {isLocal && (
                    <div className="text-center py-8">
                      <ServerIcon className="h-12 w-12 text-purple-500 mx-auto mb-4" />
                      <h4 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                        This Registry
                      </h4>
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        This is your local MCP Gateway Registry. Other registries can pull servers and agents from here.
                      </p>
                    </div>
                  )}
                </div>

                {/* Action buttons */}
                {!isLocal && (
                  <div className="px-4 py-4 bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 space-y-3">
                    {/* Sync button */}
                    <button
                      onClick={handleSync}
                      disabled={syncing || !data.enabled}
                      className="w-full flex items-center justify-center px-4 py-2 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {syncing ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                          Syncing...
                        </>
                      ) : (
                        <>
                          <ArrowPathIcon className="h-4 w-4 mr-2" />
                          Sync Now
                        </>
                      )}
                    </button>

                    {/* Enable/Disable button */}
                    {data.enabled ? (
                      <button
                        onClick={handleDisable}
                        disabled={actionLoading === 'disable'}
                        className="w-full flex items-center justify-center px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 rounded-lg transition-colors disabled:opacity-50"
                      >
                        {actionLoading === 'disable' ? (
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600 mr-2"></div>
                        ) : (
                          <PauseIcon className="h-4 w-4 mr-2" />
                        )}
                        Disable Sync
                      </button>
                    ) : (
                      <button
                        onClick={handleEnable}
                        disabled={actionLoading === 'enable'}
                        className="w-full flex items-center justify-center px-4 py-2 text-sm font-medium text-green-700 dark:text-green-400 bg-green-100 dark:bg-green-900/30 hover:bg-green-200 dark:hover:bg-green-900/50 rounded-lg transition-colors disabled:opacity-50"
                      >
                        {actionLoading === 'enable' ? (
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-green-600 mr-2"></div>
                        ) : (
                          <PlayIcon className="h-4 w-4 mr-2" />
                        )}
                        Enable Sync
                      </button>
                    )}

                    {/* Remove button */}
                    <button
                      onClick={handleRemove}
                      disabled={actionLoading === 'remove'}
                      className="w-full flex items-center justify-center px-4 py-2 text-sm font-medium text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-900/30 hover:bg-red-200 dark:hover:bg-red-900/50 rounded-lg transition-colors disabled:opacity-50"
                    >
                      {actionLoading === 'remove' ? (
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-red-600 mr-2"></div>
                      ) : (
                        <TrashIcon className="h-4 w-4 mr-2" />
                      )}
                      Remove Peer
                    </button>
                  </div>
                )}
              </div>
            </Dialog.Panel>
          </Transition.Child>
        </div>
      </Dialog>
    </Transition>
  );
};

export default PeerDetailsPanel;
