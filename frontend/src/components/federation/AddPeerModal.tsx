import React, { Fragment, useState } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { XMarkIcon, PlusIcon } from '@heroicons/react/24/outline';
import { PeerConfig } from '../../hooks/useFederationTopology';


interface AddPeerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (config: PeerConfig) => Promise<boolean>;
}


/**
 * Generate a peer ID from the name.
 */
function _generatePeerId(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 50);
}


/**
 * Modal component for adding a new peer registry.
 *
 * Provides a form for entering peer configuration including:
 * - Name and endpoint
 * - Sync mode and interval
 * - Enable/disable toggle
 */
const AddPeerModal: React.FC<AddPeerModalProps> = ({
  isOpen,
  onClose,
  onAdd,
}) => {
  const [name, setName] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [syncMode, setSyncMode] = useState<'all' | 'whitelist' | 'tag_filter'>('all');
  const [syncInterval, setSyncInterval] = useState(60);
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Authentication fields
  const [authType, setAuthType] = useState<'none' | 'api_key' | 'oauth2'>('none');
  const [apiKey, setApiKey] = useState('');
  const [oauth2TokenEndpoint, setOauth2TokenEndpoint] = useState('');
  const [oauth2ClientId, setOauth2ClientId] = useState('');
  const [oauth2ClientSecret, setOauth2ClientSecret] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validation
    if (!name.trim()) {
      setError('Name is required');
      return;
    }
    if (!endpoint.trim()) {
      setError('Endpoint URL is required');
      return;
    }

    // Validate URL format
    try {
      new URL(endpoint);
    } catch {
      setError('Invalid endpoint URL format');
      return;
    }

    // Validate sync interval
    if (syncInterval < 5 || syncInterval > 1440) {
      setError('Sync interval must be between 5 and 1440 minutes');
      return;
    }

    // Validate auth configuration
    if (authType === 'api_key' && !apiKey.trim()) {
      setError('API key is required when using API key authentication');
      return;
    }
    if (authType === 'oauth2') {
      if (!oauth2TokenEndpoint.trim()) {
        setError('Token endpoint is required for OAuth2 authentication');
        return;
      }
      if (!oauth2ClientId.trim()) {
        setError('Client ID is required for OAuth2 authentication');
        return;
      }
      if (!oauth2ClientSecret.trim()) {
        setError('Client secret is required for OAuth2 authentication');
        return;
      }
    }

    setLoading(true);

    const config: PeerConfig = {
      peer_id: _generatePeerId(name),
      name: name.trim(),
      endpoint: endpoint.trim(),
      enabled,
      sync_mode: syncMode,
      sync_interval_minutes: syncInterval,
      auth_type: authType,
      ...(authType === 'api_key' && { api_key: apiKey.trim() }),
      ...(authType === 'oauth2' && {
        oauth2_token_endpoint: oauth2TokenEndpoint.trim(),
        oauth2_client_id: oauth2ClientId.trim(),
        oauth2_client_secret: oauth2ClientSecret.trim(),
      }),
    };

    const success = await onAdd(config);

    setLoading(false);

    if (success) {
      // Reset form and close
      setName('');
      setEndpoint('');
      setSyncMode('all');
      setSyncInterval(60);
      setEnabled(true);
      setAuthType('none');
      setApiKey('');
      setOauth2TokenEndpoint('');
      setOauth2ClientId('');
      setOauth2ClientSecret('');
      onClose();
    } else {
      setError('Failed to add peer. Please check the configuration and try again.');
    }
  };

  const handleClose = () => {
    if (!loading) {
      setError(null);
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
                <Dialog.Title
                  as="div"
                  className="flex items-center justify-between mb-4"
                >
                  <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                    Add Peer Registry
                  </h3>
                  <button
                    type="button"
                    className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300"
                    onClick={handleClose}
                  >
                    <XMarkIcon className="h-5 w-5" />
                  </button>
                </Dialog.Title>

                <form onSubmit={handleSubmit} className="space-y-4">
                  {/* Error message */}
                  {error && (
                    <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-sm rounded-lg">
                      {error}
                    </div>
                  )}

                  {/* Name field */}
                  <div>
                    <label
                      htmlFor="peer-name"
                      className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                    >
                      Name
                    </label>
                    <input
                      id="peer-name"
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="e.g., Central Registry"
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      disabled={loading}
                    />
                  </div>

                  {/* Endpoint field */}
                  <div>
                    <label
                      htmlFor="peer-endpoint"
                      className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                    >
                      Endpoint URL
                    </label>
                    <input
                      id="peer-endpoint"
                      type="url"
                      value={endpoint}
                      onChange={(e) => setEndpoint(e.target.value)}
                      placeholder="https://registry.example.com"
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      disabled={loading}
                    />
                  </div>

                  {/* Sync mode field */}
                  <div>
                    <label
                      htmlFor="sync-mode"
                      className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                    >
                      Sync Mode
                    </label>
                    <select
                      id="sync-mode"
                      value={syncMode}
                      onChange={(e) => setSyncMode(e.target.value as 'all' | 'whitelist' | 'tag_filter')}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      disabled={loading}
                    >
                      <option value="all">All (sync everything)</option>
                      <option value="whitelist">Whitelist (specific items)</option>
                      <option value="tag_filter">Tag Filter (by tags)</option>
                    </select>
                  </div>

                  {/* Sync interval field */}
                  <div>
                    <label
                      htmlFor="sync-interval"
                      className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                    >
                      Sync Interval (minutes)
                    </label>
                    <input
                      id="sync-interval"
                      type="number"
                      min={5}
                      max={1440}
                      value={syncInterval}
                      onChange={(e) => setSyncInterval(parseInt(e.target.value) || 60)}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      disabled={loading}
                    />
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      Between 5 and 1440 minutes (24 hours)
                    </p>
                  </div>

                  {/* Authentication type field */}
                  <div>
                    <label
                      htmlFor="auth-type"
                      className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                    >
                      Authentication
                    </label>
                    <select
                      id="auth-type"
                      value={authType}
                      onChange={(e) => setAuthType(e.target.value as 'none' | 'api_key' | 'oauth2')}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      disabled={loading}
                    >
                      <option value="none">None (trusted internal)</option>
                      <option value="api_key">API Key</option>
                      <option value="oauth2">OAuth2 Client Credentials</option>
                    </select>
                  </div>

                  {/* API Key field (shown when auth_type is api_key) */}
                  {authType === 'api_key' && (
                    <div>
                      <label
                        htmlFor="api-key"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                      >
                        API Key
                      </label>
                      <input
                        id="api-key"
                        type="password"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        placeholder="Enter API key"
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                        disabled={loading}
                      />
                    </div>
                  )}

                  {/* OAuth2 fields (shown when auth_type is oauth2) */}
                  {authType === 'oauth2' && (
                    <>
                      <div>
                        <label
                          htmlFor="oauth2-token-endpoint"
                          className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                        >
                          Token Endpoint
                        </label>
                        <input
                          id="oauth2-token-endpoint"
                          type="url"
                          value={oauth2TokenEndpoint}
                          onChange={(e) => setOauth2TokenEndpoint(e.target.value)}
                          placeholder="https://auth.example.com/oauth/token"
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                          disabled={loading}
                        />
                      </div>
                      <div>
                        <label
                          htmlFor="oauth2-client-id"
                          className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                        >
                          Client ID
                        </label>
                        <input
                          id="oauth2-client-id"
                          type="text"
                          value={oauth2ClientId}
                          onChange={(e) => setOauth2ClientId(e.target.value)}
                          placeholder="Enter client ID"
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                          disabled={loading}
                        />
                      </div>
                      <div>
                        <label
                          htmlFor="oauth2-client-secret"
                          className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                        >
                          Client Secret
                        </label>
                        <input
                          id="oauth2-client-secret"
                          type="password"
                          value={oauth2ClientSecret}
                          onChange={(e) => setOauth2ClientSecret(e.target.value)}
                          placeholder="Enter client secret"
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                          disabled={loading}
                        />
                      </div>
                    </>
                  )}

                  {/* Enabled toggle */}
                  <div className="flex items-center">
                    <input
                      id="peer-enabled"
                      type="checkbox"
                      checked={enabled}
                      onChange={(e) => setEnabled(e.target.checked)}
                      className="h-4 w-4 text-purple-600 focus:ring-purple-500 border-gray-300 rounded"
                      disabled={loading}
                    />
                    <label
                      htmlFor="peer-enabled"
                      className="ml-2 block text-sm text-gray-700 dark:text-gray-300"
                    >
                      Enable sync immediately
                    </label>
                  </div>

                  {/* Action buttons */}
                  <div className="flex justify-end space-x-3 pt-4">
                    <button
                      type="button"
                      onClick={handleClose}
                      className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
                      disabled={loading}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="flex items-center px-4 py-2 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      disabled={loading}
                    >
                      {loading ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                          Adding...
                        </>
                      ) : (
                        <>
                          <PlusIcon className="h-4 w-4 mr-2" />
                          Add Peer
                        </>
                      )}
                    </button>
                  </div>
                </form>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
};

export default AddPeerModal;
