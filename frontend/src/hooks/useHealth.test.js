import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useHealth } from './useHealth';
import * as api from '../services/api';

describe('useHealth Hook', () => {
  it('returns health payload successfully', async () => {
    const mockHealth = {
      status: 'healthy',
      app_name: 'PrivyDoc',
      version: '0.1.0',
      database_connected: true,
      local_privacy_mode: true,
    };

    vi.spyOn(api, 'checkHealth').mockResolvedValue(mockHealth);

    const { result } = renderHook(() => useHealth(0));

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.health).toEqual(mockHealth);
    expect(result.current.error).toBeNull();
  });

  it('handles backend error gracefully', async () => {
    vi.spyOn(api, 'checkHealth').mockRejectedValue(new Error('Connection refused'));

    const { result } = renderHook(() => useHealth(0));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Connection refused');
    expect(result.current.health).toBeNull();
  });
});
