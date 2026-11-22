import { useState, useEffect, useCallback } from 'react';
import { checkHealth } from '../services/api';

/**
 * Custom hook to monitor backend health status.
 */
export function useHealth(pollIntervalMs = 15000) {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchHealth = useCallback(async () => {
    try {
      setLoading(true);
      const data = await checkHealth();
      setHealth(data);
      setError(null);
    } catch (err) {
      setError(err.message || 'Unable to connect to local backend');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    if (pollIntervalMs > 0) {
      const interval = setInterval(fetchHealth, pollIntervalMs);
      return () => clearInterval(interval);
    }
  }, [fetchHealth, pollIntervalMs]);

  return { health, loading, error, refetch: fetchHealth };
}
