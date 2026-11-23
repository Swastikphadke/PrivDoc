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
    engine_used: 'SLM',
    content: {
      summary_text: 'The agreement outlines confidential terms between [PERSON] and [PERSON] regarding milestone payments.',
      key_points: ['Milestone payment terms protected', 'Mutual non-disclosure in force'],
      important_findings: ['Deliverables scheduled for Q4', 'Compliance verified'],
      relevant_dates_or_figures: ['October 14, 2024', '$50,000'],
      source_evidence: ['Section 4 confidentiality obligations'],
    },
    verification_report: {
      status: 'PASSED',
      checks: [
        { check_name: 'DIRECT_LEAKAGE', status: 'PASSED', details: 'No direct leakage found' },
        { check_name: 'ALIAS_VARIANT', status: 'PASSED', details: 'No entity aliases found' },
        { check_name: 'PII_REDETECTION', status: 'PASSED', details: 'Deterministic and NER scans clean' },
        { check_name: 'QUASI_IDENTIFIER', status: 'PASSED', details: 'Low risk' },
        { check_name: 'SOURCE_CONSISTENCY', status: 'PASSED', details: 'Grounded in sanitized text' },
        { check_name: 'PROMPT_INJECTION_DEFENSE', status: 'PASSED', details: 'Zero prompt injection directives detected' },
      ],
      quasi_assessment: {
        risk_level: 'LOW',
        flagged_rules: [],
        findings: [],
        disclaimer: 'Quasi-identifier risk evaluation assesses statistical re-identification risk flags based on demographic or contextual co-occurrences; it does not constitute mathematical or legal proof of complete anonymity.',
      },
      verified_at: '2024-10-14T12:00:00Z',
    },
    retry_count: 0,
    warning_message: null,
  };

  const mockSuppressedSummary = {
    document_id: 'doc_sum_123',
    state: 'SUPPRESSED',
    engine_used: 'SLM',
    content: null,
    verification_report: {
      status: 'FAILED',
      checks: [
        { check_name: 'DIRECT_LEAKAGE', status: 'PASSED', details: 'No direct leakage found' },
        { check_name: 'ALIAS_VARIANT', status: 'PASSED', details: 'No entity aliases found' },
        { check_name: 'PII_REDETECTION', status: 'FAILED', details: 'NER detected category PERSON' },
      ],
      quasi_assessment: {
        risk_level: 'MEDIUM',
        flagged_rules: ['QI-001'],
        findings: ['QI-001: Demographic co-occurrence detected'],
        disclaimer: 'Quasi-identifier risk evaluation assesses statistical re-identification risk flags based on demographic or contextual co-occurrences; it does not constitute mathematical or legal proof of complete anonymity.',
      },
      verified_at: '2024-10-14T12:00:00Z',
    },
    retry_count: 2,
    warning_message: 'Residual PII detected in summary of category PERSON via contextual NER scan.',
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

  it('renders an actual backend SummaryResponse.model_dump() payload including REQUIRES_REVIEW quasi-identifier warnings', async () => {
    // Exact JSON payload serialized by backend SummaryService.generate_summary().model_dump(mode="json")
    const backendModelDumpPayload = {
      document_id: 'doc_contract_001',
      state: 'REQUIRES_REVIEW',
      engine_used: 'EXTRACTIVE_FALLBACK',
      content: {
        summary_text: 'The Chief Security Officer in Cybersecurity Operations submitted the incident findings on November 18, 2024 regarding the $250,000 budget allocation.',
        key_points: [
          'The Chief Security Officer in Cybersecurity Operations submitted the incident findings on November 18, 2024 regarding the $250,000 budget allocation.',
        ],
        important_findings: [
          'The Chief Security Officer in Cybersecurity Operations submitted the incident findings on November 18, 2024 regarding the $250,000 budget allocation.',
        ],
        relevant_dates_or_figures: ['November 18, 2024', '$250,000'],
        source_evidence: [
          'The Chief Security Officer in Cybersecurity Operations submitted the incident findings on November 18, 2024 regarding th...',
        ],
      },
      verification_report: {
        status: 'REQUIRES_REVIEW',
        checks: [
          { check_name: 'DIRECT_LEAKAGE', status: 'PASSED', details: 'Zero approved sensitive entity values detected in summary.' },
          { check_name: 'ALIAS_VARIANT', status: 'PASSED', details: 'Zero known entity variants or initials detected in summary.' },
          { check_name: 'PII_REDETECTION', status: 'PASSED', details: 'Zero unmasked PII entities detected across regex and contextual scans.' },
          { check_name: 'QUASI_IDENTIFIER', status: 'WARNING', details: 'High quasi-identifier risk: 2 co-occurrence rule(s) flagged. Manual review required before distribution.' },
          { check_name: 'SOURCE_CONSISTENCY', status: 'PASSED', details: 'All dates, figures, and facts strictly grounded in sanitized source text.' },
          { check_name: 'PROMPT_INJECTION_DEFENSE', status: 'PASSED', details: 'Zero prompt injection directives or system boundary artifacts detected.' },
        ],
        quasi_assessment: {
          risk_level: 'HIGH',
          flagged_rules: ['QI-001', 'QI-004'],
          findings: [
            'Rule QI-001 triggered: Co-occurrence of executive role, department, and location or date',
            'Rule QI-004 triggered: Executive role combined with specific department',
          ],
          disclaimer: 'Quasi-identifier risk evaluation assesses statistical re-identification risk flags based on demographic or contextual co-occurrences; it does not constitute mathematical or legal proof of complete anonymity.',
        },
        verified_at: '2026-11-23T14:20:00+00:00',
      },
      retry_count: 0,
      warning_message: 'Summary flagged for human review: plausible quasi-identifier co-occurrences were detected. Quasi-identifier flags reflect potential statistical re-identification risk and do not guarantee anonymity.',
    };

    vi.spyOn(api, 'getDocumentMetadata').mockResolvedValue(mockDocMeta);
    vi.spyOn(api, 'getSummary').mockResolvedValue(backendModelDumpPayload);

    renderView('doc_contract_001');

    await waitFor(() => {
      expect(screen.getByTestId('summary-state-badge').textContent).toContain('REQUIRES REVIEW');
    });

    expect(screen.getByTestId('summary-narrative-text').textContent).toContain('$250,000 budget allocation');
    expect(screen.getByText('November 18, 2024')).toBeDefined();
    expect(screen.getByText('$250,000')).toBeDefined();
    expect(screen.getByText('Risk Level: HIGH')).toBeDefined();
    expect(screen.getByText(/Rule QI-001 triggered/i)).toBeDefined();
    expect(screen.getByTestId('requires-review-warning-banner').textContent).toContain(
      'Summary flagged for human review'
    );
    expect(screen.getByTestId('quasi-disclaimer').textContent).toContain('does not constitute mathematical or legal proof');
  });
});
