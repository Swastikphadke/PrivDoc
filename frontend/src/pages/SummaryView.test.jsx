import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import SummaryView from './SummaryView';
import * as api from '../services/api';

describe('SummaryView Component', () => {
  const mockDocMeta = {
    document_id: 'doc_sum_123',
    filename: 'settlement_agreement.txt',
    file_type: 'txt',
    status: 'VERIFIED',
    page_count: 1,
    text_length: 500,
  };

  const mockVerifiedSummary = {
    document_id: 'doc_sum_123',
    state: 'VERIFIED',
    engine_used: 'LOCAL_SLM',
    model_name: 'qwen2.5:1.5b-instruct',
    structured_content: {
      summary_text: 'The agreement outlines confidential terms between [PERSON] and [PERSON] regarding milestone payments.',
      key_points: ['Milestone payment terms protected', 'Mutual non-disclosure in force'],
      important_findings: ['Deliverables scheduled for Q4', 'Compliance verified'],
      relevant_dates_and_figures: ['October 14, 2024', '$50,000'],
      source_evidence: ['Section 4 confidentiality obligations'],
    },
    verification_report: {
      overall_passed: true,
      checks: [
        { check_name: 'DIRECT_LEAKAGE', passed: true, details: 'No direct leakage found' },
        { check_name: 'ALIAS_AND_VARIANTS', passed: true, details: 'No entity aliases found' },
        { check_name: 'PII_REDETECTION', passed: true, details: 'Deterministic and NER scans clean' },
        { check_name: 'QUASI_IDENTIFIERS', passed: true, details: 'Low risk' },
        { check_name: 'SOURCE_CONSISTENCY', passed: true, details: 'Grounded in sanitized text' },
      ],
      issues: [],
      verified_at: '2024-10-14T12:00:00Z',
    },
    quasi_identifier_assessment: {
      risk_level: 'LOW',
      findings: [],
      disclaimer: 'Quasi-identifier risk evaluation assesses statistical re-identification risk flags based on demographic or contextual co-occurrences; it does not constitute mathematical or legal proof of complete anonymity.',
    },
    attempts: 1,
  };

  const mockSuppressedSummary = {
    document_id: 'doc_sum_123',
    state: 'SUPPRESSED',
    engine_used: 'LOCAL_SLM',
    model_name: 'qwen2.5:1.5b-instruct',
    suppression_reason: 'Residual PII detected in summary of category PERSON via contextual NER scan.',
    structured_content: null,
    verification_report: {
      overall_passed: false,
      checks: [
        { check_name: 'DIRECT_LEAKAGE', passed: true, details: 'No direct leakage found' },
        { check_name: 'ALIAS_AND_VARIANTS', passed: true, details: 'No entity aliases found' },
        { check_name: 'PII_REDETECTION', passed: false, details: 'NER detected category PERSON' },
      ],
      issues: ['NER detected category PERSON'],
      verified_at: '2024-10-14T12:00:00Z',
    },
    quasi_identifier_assessment: {
      risk_level: 'MEDIUM',
      findings: ['QI-001: Demographic co-occurrence detected'],
      disclaimer: 'Quasi-identifier risk evaluation assesses statistical re-identification risk flags based on demographic or contextual co-occurrences; it does not constitute mathematical or legal proof of complete anonymity.',
    },
    attempts: 3,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderView = (initialId = 'doc_sum_123') => {
    return render(
      <MemoryRouter initialEntries={[`/summary/${initialId}`]}>
        <Routes>
          <Route path="/summary/:documentId" element={<SummaryView />} />
        </Routes>
      </MemoryRouter>
    );
  };

  it('renders verified structured summary with all content fields and engine badge', async () => {
    vi.spyOn(api, 'getDocumentMetadata').mockResolvedValue(mockDocMeta);
    vi.spyOn(api, 'getSummary').mockResolvedValue(mockVerifiedSummary);

    renderView();

    await waitFor(() => {
      const badge = screen.getByTestId('summary-state-badge');
      expect(badge.textContent).toContain('VERIFIED');
    });

    expect(screen.getByTestId('summary-engine-badge').textContent).toContain('Local SLM');
    expect(screen.getByTestId('summary-narrative-text').textContent).toContain(
      'The agreement outlines confidential terms between [PERSON] and [PERSON]'
    );
    expect(screen.getByText('Milestone payment terms protected')).toBeDefined();
    expect(screen.getByText('Deliverables scheduled for Q4')).toBeDefined();
    expect(screen.getByText('$50,000')).toBeDefined();
    expect(screen.getByText('Section 4 confidentiality obligations')).toBeDefined();
  });

  it('renders verification shield report breakdown', async () => {
    vi.spyOn(api, 'getDocumentMetadata').mockResolvedValue(mockDocMeta);
    vi.spyOn(api, 'getSummary').mockResolvedValue(mockVerifiedSummary);

    renderView();

    await waitFor(() => {
      expect(screen.getByTestId('verification-shield-card')).toBeDefined();
    });

    expect(screen.getByText('ALL CHECKS PASSED')).toBeDefined();
    expect(screen.getByText('DIRECT LEAKAGE')).toBeDefined();
    expect(screen.getByText('PII REDETECTION')).toBeDefined();
  });

  it('renders quasi-identifier assessment and mandatory non-anonymity disclaimer', async () => {
    vi.spyOn(api, 'getDocumentMetadata').mockResolvedValue(mockDocMeta);
    vi.spyOn(api, 'getSummary').mockResolvedValue(mockVerifiedSummary);

    renderView();

    await waitFor(() => {
      expect(screen.getByTestId('quasi-risk-assessment-card')).toBeDefined();
    });

    expect(screen.getByTestId('quasi-disclaimer').textContent).toContain(
      'Quasi-identifier risk evaluation assesses statistical re-identification risk flags based on demographic or contextual co-occurrences; it does not constitute mathematical or legal proof of complete anonymity.'
    );
  });

  it('blocks narrative text and displays suppression banner when state is SUPPRESSED', async () => {
    vi.spyOn(api, 'getDocumentMetadata').mockResolvedValue(mockDocMeta);
    vi.spyOn(api, 'getSummary').mockResolvedValue(mockSuppressedSummary);

    renderView();

    await waitFor(() => {
      expect(screen.getByTestId('summary-state-badge').textContent).toContain('SUPPRESSED');
    });

    expect(screen.getByTestId('suppression-banner')).toBeDefined();
    expect(screen.getByText(/Summary Suppressed: Privacy Verification Failed/)).toBeDefined();
    expect(screen.queryByTestId('structured-summary-container')).toBeNull();
    expect(screen.getByText(/Residual PII detected in summary/)).toBeDefined();
    expect(screen.getByText('Retry with Deterministic Extractive Fallback')).toBeDefined();
  });

  it('correctly displays extractive fallback engine badge', async () => {
    const extractiveSummary = {
      ...mockVerifiedSummary,
      engine_used: 'EXTRACTIVE_FALLBACK',
    };
    vi.spyOn(api, 'getDocumentMetadata').mockResolvedValue(mockDocMeta);
    vi.spyOn(api, 'getSummary').mockResolvedValue(extractiveSummary);

    renderView();

    await waitFor(() => {
      expect(screen.getByTestId('summary-engine-badge').textContent).toContain(
        'Extractive Fallback (SLM Unavailable)'
      );
    });
  });
});
