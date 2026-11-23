import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard';
import * as api from '../services/api';

describe('Dashboard Workstation Page', () => {
  const mockOverview = {
    total_documents: 3,
    awaiting_review_count: 1,
    verified_exports_count: 2,
    suppressed_summaries_count: 1,
    total_candidates_detected: 18,
    category_distribution: {
      PERSON: 7,
      EMAIL: 4,
      PHONE: 4,
      FINANCIAL_ID: 3,
    },
    recent_documents: [
      {
        document_id: 'doc_session_01',
        filename: 'demo_sample_report.pdf',
        file_type: 'pdf',
        status: 'EXPORTED',
        page_count: 2,
        text_length: 1450,
        upload_timestamp: '2026-11-23T16:00:00Z',
        total_candidates: 8,
        approved_count: 7,
        rejected_count: 1,
        pending_count: 0,
        export_verification_status: 'VERIFIED',
        summary_verification_status: 'VERIFIED',
      },
      {
        document_id: 'doc_session_02',
        filename: 'incident_log.txt',
        file_type: 'txt',
        status: 'PROCESSED',
        page_count: 1,
        text_length: 620,
        upload_timestamp: '2026-11-23T16:10:00Z',
        total_candidates: 10,
        approved_count: 4,
        rejected_count: 0,
        pending_count: 6,
        export_verification_status: 'UNVERIFIED',
        summary_verification_status: 'SUPPRESSED',
      },
    ],
  };

  beforeEach(() => {
    vi.spyOn(api, 'getDocumentsOverview').mockResolvedValue(mockOverview);
    vi.spyOn(api, 'checkHealth').mockResolvedValue({
      status: 'ok',
      app_name: 'PrivyDoc',
      version: '0.1.0',
      database_connected: true,
    });
  });

  it('renders real backend telemetry metrics, category distribution, and recent document sessions table', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('demo_sample_report.pdf')).toBeDefined();
    });

    expect(screen.getByText('incident_log.txt')).toBeDefined();
    expect(screen.getByTestId('recent-documents-panel')).toBeDefined();
    expect(screen.getByText('18 total spans')).toBeDefined();
    expect(screen.getByText('Person')).toBeDefined();
    expect(screen.getByText('Email')).toBeDefined();
  });
});
