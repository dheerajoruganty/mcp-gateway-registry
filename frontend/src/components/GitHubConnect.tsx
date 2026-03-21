import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

interface GitHubConnectProps {
  onShowToast?: (message: string, type: 'success' | 'error') => void;
  compact?: boolean;
}

interface GitHubStatus {
  connected: boolean;
  username?: string;
}

const GitHubIcon: React.FC<{ className?: string }> = ({ className = 'h-5 w-5' }) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
  </svg>
);

const GitHubConnect: React.FC<GitHubConnectProps> = ({ onShowToast, compact = false }) => {
  const [status, setStatus] = useState<GitHubStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [hidden, setHidden] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await axios.get('/api/github/status');
      setStatus(response.data);
    } catch (error: any) {
      if (error.response?.status === 503) {
        setHidden(true);
      } else {
        setStatus({ connected: false });
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Check for ?github_connected=true in URL params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('github_connected') === 'true') {
      if (onShowToast) {
        onShowToast('GitHub account connected successfully', 'success');
      }
      params.delete('github_connected');
      const newUrl = params.toString()
        ? `${window.location.pathname}?${params.toString()}`
        : window.location.pathname;
      window.history.replaceState({}, '', newUrl);
    }
  }, [onShowToast]);

  const handleConnect = () => {
    window.location.href = `${axios.defaults.baseURL || ''}/api/github/connect`;
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      await axios.post('/api/github/disconnect');
      setStatus({ connected: false });
      if (onShowToast) {
        onShowToast('GitHub account disconnected', 'success');
      }
    } catch (error: any) {
      if (onShowToast) {
        onShowToast('Failed to disconnect GitHub account', 'error');
      }
    } finally {
      setDisconnecting(false);
    }
  };

  if (hidden || loading) return null;

  if (status?.connected) {
    if (compact) {
      return (
        <div className="flex items-center gap-2 py-1.5">
          <div className="w-2 h-2 rounded-full bg-green-500" />
          <span className="text-sm text-gray-600 dark:text-gray-300">
            GitHub connected{status.username ? ` as ${status.username}` : ''}
          </span>
          <button
            onClick={handleDisconnect}
            disabled={disconnecting}
            className="text-xs text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors ml-1"
          >
            {disconnecting ? 'Disconnecting...' : 'Disconnect'}
          </button>
        </div>
      );
    }

    return (
      <div className="flex items-center gap-3 p-3 rounded-lg border border-green-200 dark:border-green-700 bg-green-50 dark:bg-green-900/20">
        <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
        <GitHubIcon className="h-5 w-5 text-gray-700 dark:text-gray-300" />
        <span className="text-sm text-gray-700 dark:text-gray-200 flex-1">
          GitHub connected{status.username ? ` as ${status.username}` : ''}
        </span>
        <button
          onClick={handleDisconnect}
          disabled={disconnecting}
          className="text-sm text-gray-500 hover:text-red-500 dark:text-gray-400 dark:hover:text-red-400 transition-colors"
        >
          {disconnecting ? 'Disconnecting...' : 'Disconnect'}
        </button>
      </div>
    );
  }

  // Not connected
  if (compact) {
    return (
      <div className="flex items-center gap-2 py-2">
        <GitHubIcon className="h-4 w-4 text-gray-500 dark:text-gray-400" />
        <button
          onClick={handleConnect}
          className="text-sm font-medium text-amber-700 dark:text-amber-300 hover:text-amber-800 dark:hover:text-amber-200 transition-colors"
        >
          Connect GitHub
        </button>
        <span className="text-xs text-gray-400 dark:text-gray-500">for private repos</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
      <GitHubIcon className="h-5 w-5 text-gray-600 dark:text-gray-400" />
      <div className="flex-1">
        <p className="text-sm text-gray-700 dark:text-gray-200">
          Connect your GitHub account to access private repositories
        </p>
      </div>
      <button
        onClick={handleConnect}
        className="px-3 py-1.5 text-sm font-medium text-white bg-gray-800 dark:bg-gray-600 hover:bg-gray-700 dark:hover:bg-gray-500 rounded-md transition-colors"
      >
        Connect
      </button>
    </div>
  );
};

export default GitHubConnect;
