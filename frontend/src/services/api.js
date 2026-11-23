import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// System & Health
export const getHealthStatus = async () => {
  const response = await apiClient.get('/api/health');
  return response.data;
};
export const checkHealth = getHealthStatus;

// Ingestion & Documents
export const uploadDocument = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post('/api/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

export const getDocumentMetadata = async (documentId) => {
  const response = await apiClient.get(`/api/documents/${documentId}`);
  return response.data;
};

export const getDocumentCoordinates = async (documentId) => {
  const response = await apiClient.get(`/api/documents/${documentId}/coordinates`);
  return response.data;
};

export const deleteDocumentSession = async (documentId) => {
  const response = await apiClient.delete(`/api/documents/${documentId}`);
  return response.data;
};

export const getPdfPageImageUrl = (documentId, pageNumber) => {
  return `${API_BASE_URL}/api/documents/${documentId}/pages/${pageNumber}/render`;
};

// Detection & Candidates
export const detectPii = async (documentId) => {
  const response = await apiClient.post(`/api/documents/${documentId}/detect`);
  return response.data;
};

export const getCandidates = async (documentId) => {
  const response = await apiClient.get(`/api/documents/${documentId}/candidates`);
  return response.data;
};

// Review Actions
export const submitReviewDecision = async (documentId, { candidateId, decision, newType, applyToLinked, applyToSimilar }) => {
  const response = await apiClient.post(`/api/documents/${documentId}/review`, {
    candidate_id: candidateId,
    decision,
    new_type: newType || null,
    apply_to_linked: Boolean(applyToLinked),
    apply_to_similar: Boolean(applyToSimilar),
  });
  return response.data;
};

export const getReviewSummary = async (documentId) => {
  const response = await apiClient.get(`/api/documents/${documentId}/review`);
  return response.data;
};

export const addManualCandidate = async (documentId, { start, end, type = 'PERSON', pageNumber = null, bbox = null }) => {
  const response = await apiClient.post(`/api/documents/${documentId}/candidates/manual`, {
    start,
    end,
    type,
    page_number: pageNumber,
    bbox,
  });
  return response.data;
};

// Entity Resolution
export const resolveEntities = async (documentId) => {
  const response = await apiClient.post(`/api/documents/${documentId}/entities/resolve`);
  return response.data;
};

export const getEntities = async (documentId) => {
  const response = await apiClient.get(`/api/documents/${documentId}/entities`);
  return response.data;
};

export const linkEntities = async (documentId, { candidateIds, targetEntityId = null, action = 'LINK' }) => {
  const response = await apiClient.post(`/api/documents/${documentId}/entities/link`, {
    candidate_ids: candidateIds,
    target_entity_id: targetEntityId,
    action,
  });
  return response.data;
};

// Redaction & Export
export const redactDocument = async (documentId, options = {}) => {
  const response = await apiClient.post(`/api/documents/${documentId}/redact`, {
    placeholder_style: options.placeholderStyle || 'CATEGORY',
    custom_placeholder: options.customPlaceholder || null,
    force_text_reconstruction: !!options.forceTextReconstruction,
  });
  return response.data;
};

export const reconstructPdf = async (documentId, options = {}) => {
  const response = await apiClient.post(`/api/documents/${documentId}/reconstruct-pdf`, {
    placeholder_style: options.placeholderStyle || 'CATEGORY',
    custom_placeholder: options.customPlaceholder || null,
    force_text_reconstruction: true,
  });
  return response.data;
};

export const getExportStatus = async (documentId) => {
  const response = await apiClient.get(`/api/documents/${documentId}/export/status`);
  return response.data;
};

export const downloadExport = async (documentId) => {
  const response = await apiClient.get(`/api/documents/${documentId}/export`, {
    responseType: 'blob',
  });
  return response;
};

