import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 5000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const getHealthStatus = async () => {
  const response = await apiClient.get('/api/health');
  return response.data;
};

export const getRootStatus = async () => {
  const response = await apiClient.get('/api/');
  return response.data;
};
