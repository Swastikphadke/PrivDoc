import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import ReviewWorkspace from './ReviewWorkspace';
import * as api from '../services/api';

describe('ReviewWorkspace Page', () => {
  const mockDocMeta = {
    document_id: 'doc_test_abc',
    filename: 'confidential_report.txt',
    file_type: 'txt',
    status: 'PROCESSED',
    page_count: 1,
    text_length: 120,
    extracted_text: 'Employee Swastik Phadke can be reached at swastik@example.com for confidential review.',
    warnings: [],
  };

  const mockCandidates = [
    {
      candidate_id: 'c_01',
      document_id: 'doc_test_abc',
      start: 9,
      end: 23,
      text: 'Swastik Phadke',
      type: 'PERSON',
      confidence: 0.98,
      confidence_band: 'HIGH',
      sources: ['gliner', 'regex'],
      review_status: 'PENDING',
    },
    {
      candidate_id: 'c_02',
      document_id: 'doc_test_abc',
      start: 42,
      end: 61,
      text: 'swastik@example.com',
      type: 'EMAIL',
      confidence: 1.0,
      confidence_band: 'HIGH',
      sources: ['regex'],
      review_status: 'APPROVED',
    },
  ];

  const mockEntities = {
    document_id: 'doc_test_abc',
    total_entities: 1,
    entities: [
      {
        entity_id: 'ent_01',
        canonical_name: 'Swastik Phadke',
        entity_type: 'PERSON',
        candidate_ids: ['c_01'],
        variants: ['Swastik Phadke'],
        confidence: 0.95,
        is_ambiguous: false,
        evidence: ['Exact surface name match'],
      },
    ],
    degraded_mode: false,
    slm_available: true,
    warnings: [],
  };

  const mockSummary = {
    document_id: 'doc_test_abc',
    total_candidates: 2,
    approved_count: 1,
    rejected_count: 0,
    pending_count: 1,
    manual_count: 0,
    candidates: mockCandidates,
  };

  beforeEach(() => {
    vi.spyOn(api, 'getDocumentMetadata').mockResolvedValue(mockDocMeta);
    vi.spyOn(api, 'getCandidates').mockResolvedValue(mockCandidates);
    vi.spyOn(api, 'getEntities').mockResolvedValue(mockEntities);
    vi.spyOn(api, 'getReviewSummary').mockResolvedValue(mockSummary);
  });

  it('renders review workspace with document metadata and candidate sidebar', async () => {
    render(
      <MemoryRouter initialEntries={['/review/doc_test_abc']}>
        <Routes>
          <Route path="/review/:documentId" element={<ReviewWorkspace />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText(/Loading document review workspace/i)).toBeDefined();

    await waitFor(() => {
      expect(screen.getByText('confidential_report.txt')).toBeDefined();
    });

    expect(screen.getAllByText('Swastik Phadke').length).toBeGreaterThan(0);
    expect(screen.getAllByText('swastik@example.com').length).toBeGreaterThan(0);
  });

  it('submits approve action when approve button is clicked', async () => {
    const submitReviewSpy = vi.spyOn(api, 'submitReviewDecision').mockResolvedValue({
      ...mockSummary,
      approved_count: 2,
      pending_count: 0,
      candidates: mockCandidates.map((c) => ({ ...c, review_status: 'APPROVED' })),
    });

    render(
      <MemoryRouter initialEntries={['/review/doc_test_abc']}>
        <Routes>
          <Route path="/review/:documentId" element={<ReviewWorkspace />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('confidential_report.txt')).toBeDefined();
    });

    const approveButton = screen.getByTitle('Approve Redaction (Shortcut: A)');
    expect(approveButton).toBeDefined();
    fireEvent.click(approveButton);

    await waitFor(() => {
      expect(submitReviewSpy).toHaveBeenCalledWith('doc_test_abc', expect.objectContaining({
        decision: 'APPROVE',
      }));
    });
  });
});
