import React, { Fragment, useState, useEffect } from 'react';
import { Dialog, Transition, Switch } from '@headlessui/react';
import {
  XMarkIcon,
  ArrowPathIcon,
  SparklesIcon,
  UserGroupIcon,
  Cog6ToothIcon,
} from '@heroicons/react/24/outline';
import {
  FederationSourceConfigUpdate,
  FederationSyncResult,
} from '../../hooks/useUnifiedFederationTopology';


/**
 * Federation source type for the modal.
 */
type SourceType = 'anthropic' | 'asor';


interface FederationSourceModalProps {
  isOpen: boolean;
  onClose: () => void;
  sourceType: SourceType;
  currentConfig: {
    enabled: boolean;
    endpoint: string | null;
    syncOnStartup: boolean | null;
    serversCount?: number;
    agentsCount?: number;
  };
  onSync: () => Promise<FederationSyncResult | null>;
  onUpdateConfig: (updates: FederationSourceConfigUpdate) => Promise<boolean>;
}


/**
 * Get display info for a source type.
 */
function _getSourceInfo(sourceType: SourceType): {
  title: string;
  description: string;
  icon: React.ReactNode;
  bgColor: string;
  textColor: string;
} {
  if (sourceType === 'anthropic') {
    return {
      title: 'Anthropic MCP',
      description: 'Configure federation from Anthropic Model Context Protocol registry.',
      icon: <SparklesIcon className="h-6 w-6 text-amber-500" />,
      bgColor: 'bg-amber-50 dark:bg-amber-900/20',
      textColor: 'text-amber-700 dark:text-amber-300',
    };
  }

  return {
    title: 'ASOR Agents',
    description: 'Configure federation from Workday ASOR agents registry.',
    icon: <UserGroupIcon className="h-6 w-6 text-cyan-500" />,
    bgColor: 'bg-cyan-50 dark:bg-cyan-900/20',
    textColor: 'text-cyan-700 dark:text-cyan-300',
  };
}


/**
 * Modal component for configuring Anthropic/ASOR federation sources.
 *
 * Provides controls for:
 * - Enable/disable toggle
 * - Endpoint URL configuration
 * - Sync on startup toggle
 * - Manual sync trigger
 */
const FederationSourceModal: React.FC<FederationSourceModalProps> = ({
  isOpen,
  onClose,
  sourceType,
  currentConfig,
  onSync,
  onUpdateConfig,
}) => {
  // Form state
  const [enabled, setEnabled] = useState(currentConfig.enabled);
  const [endpoint, setEndpoint] = useState(currentConfig.endpoint || '');
  const [syncOnStartup, setSyncOnStartup] = useState(currentConfig.syncOnStartup || false);

  // UI state
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const sourceInfo = _getSourceInfo(sourceType);

  // Update form when config changes
  useEffect(() => {
    setEnabled(currentConfig.enabled);
    setEndpoint(currentConfig.endpoint || '');
    setSyncOnStartup(currentConfig.syncOnStartup || false);
  }, [currentConfig]);

  /**
   * Handle config save.
   */
  const handleSave = async () => {
    setError(null);
    setSuccess(null);
    setLoading(true);

    // Validate endpoint if provided
    if (endpoint.trim() && enabled) {
      try {
        new URL(endpoint);
      } catch {
        setError('Invalid endpoint URL format');
        setLoading(false);
        return;
      }
    }

    const updates: FederationSourceConfigUpdate = {
      enabled,
      endpoint: endpoint.trim() || undefined,
      sync_on_startup: syncOnStartup,
    };

    const result = await onUpdateConfig(updates);

    setLoading(false);

    if (result) {
      setSuccess('Configuration saved successfully');
      setTimeout(() => setSuccess(null), 3000);
    } else {
      setError('Failed to save configuration');
    }
  };

  /**
   * Handle manual sync.
   */
  const handleSync = async () => {
    if (!enabled) {
      setError('Enable the federation source before syncing');
      return;
    }

    setError(null);
    setSuccess(null);
    setSyncing(true);

    const result = await onSync();

    setSyncing(false);

    if (result && result.success) {
      const itemCount = sourceType === 'anthropic'
        ? result.servers_synced
        : result.agents_synced;
      const itemType = sourceType === 'anthropic' ? 'servers' : 'agents';
      setSuccess(`Sync complete: ${itemCount} ${itemType} synced`);
      setTimeout(() => setSuccess(null), 5000);
    } else if (result) {
      setError(result.error_message || 'Sync failed');
    } else {
      setError('Sync failed');
    }
  };

  const handleClose = () => {
    if (!loading && !syncing) {
      setError(null);
      setSuccess(null);
      onClose();
    }
  };

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={handleClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black bg-opacity-25 dark:bg-opacity-50" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-2xl bg-white dark:bg-gray-800 p-6 text-left align-middle shadow-xl transition-all">
                {/* Header */}
                <Dialog.Title
                  as="div"
                  className="flex items-center justify-between mb-4"
                >
                  <div className="flex items-center space-x-3">
                    <div className={`p-2 rounded-lg ${sourceInfo.bgColor}`}>
                      {sourceInfo.icon}
                    </div>
                    <div>
                      <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                        {sourceInfo.title}
                      </h3>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        Federation Source
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300"
                    onClick={handleClose}
                    disabled={loading || syncing}
                  >
                    <XMarkIcon className="h-5 w-5" />
                  </button>
                </Dialog.Title>

                {/* Description */}
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                  {sourceInfo.description}
                </p>

                {/* Messages */}
                {error && (
                  <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-sm rounded-lg">
                    {error}
                  </div>
                )}
                {success && (
                  <div className="mb-4 p-3 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 text-sm rounded-lg">
                    {success}
                  </div>
                )}

                {/* Configuration form */}
                <div className="space-y-5">
                  {/* Enable/Disable toggle */}
                  <div className="flex items-center justify-between">
                    <div>
                      <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Enable Federation
                      </label>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        Allow syncing from this source
                      </p>
                    </div>
                    <Switch
                      checked={enabled}
                      onChange={setEnabled}
                      className={`${
                        enabled
                          ? sourceType === 'anthropic'
                            ? 'bg-amber-500'
                            : 'bg-cyan-500'
                          : 'bg-gray-200 dark:bg-gray-600'
                      } relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 ${
                        sourceType === 'anthropic'
                          ? 'focus:ring-amber-500'
                          : 'focus:ring-cyan-500'
                      }`}
                      disabled={loading || syncing}
                    >
                      <span
                        className={`${
                          enabled ? 'translate-x-6' : 'translate-x-1'
                        } inline-block h-4 w-4 transform rounded-full bg-white transition-transform`}
                      />
                    </Switch>
                  </div>

                  {/* Endpoint URL */}
                  <div>
                    <label
                      htmlFor="endpoint"
                      className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                    >
                      Endpoint URL
                    </label>
                    <input
                      id="endpoint"
                      type="url"
                      value={endpoint}
                      onChange={(e) => setEndpoint(e.target.value)}
                      placeholder={
                        sourceType === 'anthropic'
                          ? 'https://registry.modelcontextprotocol.io'
                          : 'https://asor.example.com/api/agents'
                      }
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      disabled={loading || syncing}
                    />
                  </div>

                  {/* Sync on startup toggle */}
                  <div className="flex items-center justify-between">
                    <div>
                      <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Sync on Startup
                      </label>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        Automatically sync when registry starts
                      </p>
                    </div>
                    <Switch
                      checked={syncOnStartup}
                      onChange={setSyncOnStartup}
                      className={`${
                        syncOnStartup
                          ? 'bg-purple-600'
                          : 'bg-gray-200 dark:bg-gray-600'
                      } relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500`}
                      disabled={loading || syncing}
                    >
                      <span
                        className={`${
                          syncOnStartup ? 'translate-x-6' : 'translate-x-1'
                        } inline-block h-4 w-4 transform rounded-full bg-white transition-transform`}
                      />
                    </Switch>
                  </div>

                  {/* Current stats */}
                  <div className={`p-4 rounded-lg ${sourceInfo.bgColor}`}>
                    <h4 className={`text-sm font-medium ${sourceInfo.textColor} mb-2`}>
                      Current Status
                    </h4>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-gray-600 dark:text-gray-400">Status:</span>
                        <span className={`ml-2 font-medium ${enabled ? 'text-green-600 dark:text-green-400' : 'text-gray-500 dark:text-gray-400'}`}>
                          {enabled ? 'Enabled' : 'Disabled'}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-600 dark:text-gray-400">
                          {sourceType === 'anthropic' ? 'Servers:' : 'Agents:'}
                        </span>
                        <span className="ml-2 font-medium text-gray-900 dark:text-white">
                          {sourceType === 'anthropic'
                            ? currentConfig.serversCount || 0
                            : currentConfig.agentsCount || 0}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Action buttons */}
                <div className="mt-6 flex justify-between">
                  {/* Sync button */}
                  <button
                    type="button"
                    onClick={handleSync}
                    disabled={loading || syncing || !enabled}
                    className={`flex items-center px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                      sourceType === 'anthropic'
                        ? 'text-amber-700 bg-amber-100 hover:bg-amber-200 dark:text-amber-300 dark:bg-amber-900/30 dark:hover:bg-amber-900/50'
                        : 'text-cyan-700 bg-cyan-100 hover:bg-cyan-200 dark:text-cyan-300 dark:bg-cyan-900/30 dark:hover:bg-cyan-900/50'
                    }`}
                  >
                    <ArrowPathIcon className={`h-4 w-4 mr-2 ${syncing ? 'animate-spin' : ''}`} />
                    {syncing ? 'Syncing...' : 'Sync Now'}
                  </button>

                  {/* Save/Cancel buttons */}
                  <div className="flex space-x-3">
                    <button
                      type="button"
                      onClick={handleClose}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
                      disabled={loading || syncing}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleSave}
                      disabled={loading || syncing}
                      className="flex items-center px-4 py-2 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {loading ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                          Saving...
                        </>
                      ) : (
                        <>
                          <Cog6ToothIcon className="h-4 w-4 mr-2" />
                          Save
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
};

export default FederationSourceModal;
