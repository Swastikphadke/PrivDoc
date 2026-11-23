import { describe, it, expect } from 'vitest';
import { apiClient } from './api';

describe('API Client Configuration', () => {
  it('has default timeout configured', () => {
    expect(apiClient.defaults.timeout).toBe(10000);
  });

  it('sets application/json header', () => {
    expect(apiClient.defaults.headers['Content-Type']).toBe('application/json');
  });

  it('points to local backend', () => {
    expect(apiClient.defaults.baseURL).toMatch(/127\.0\.0\.1|localhost/);
  });
});
