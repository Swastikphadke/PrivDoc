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

  it('approves all linked occurrences when Approve All is clicked in EntityGroups tab', async () => {
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

    // Switch to Entities tab
    fireEvent.click(screen.getByText(/Entities \(1\)/i));

    const approveAllBtn = await screen.findByTitle('Approve all occurrences in this group');
    fireEvent.click(approveAllBtn);

    await waitFor(() => {
      expect(submitReviewSpy).toHaveBeenCalledWith('doc_test_abc', expect.objectContaining({
        candidateId: 'c_01',
        decision: 'APPROVE',
        applyToLinked: true,
      }));
    });
  });

  it('rejects all linked occurrences when Reject All is clicked in EntityGroups tab', async () => {
    const multiOccurrenceCandidates = [
      ...mockCandidates,
      {
        candidate_id: 'c_03',
        document_id: 'doc_test_abc',
        start: 85,
        end: 94,
        text: 'S. Phadke',
        type: 'PERSON',
        confidence: 0.88,
        confidence_band: 'HIGH',
        sources: ['regex'],
        review_status: 'PENDING',
        entity_id: 'ent_01',
      },
    ];
    vi.spyOn(api, 'getCandidates').mockResolvedValue(multiOccurrenceCandidates);
    vi.spyOn(api, 'getEntities').mockResolvedValue({
      ...mockEntities,
      entities: [
        {
          ...mockEntities.entities[0],
          candidate_ids: ['c_01', 'c_03'],
          variants: ['Swastik Phadke', 'S. Phadke'],
        },
      ],
    });

    const submitReviewSpy = vi.spyOn(api, 'submitReviewDecision').mockResolvedValue({
      ...mockSummary,
      approved_count: 1,
      rejected_count: 2,
      pending_count: 0,
      candidates: multiOccurrenceCandidates.map((c) =>
        c.candidate_id === 'c_01' || c.candidate_id === 'c_03'
          ? { ...c, review_status: 'REJECTED' }
          : c
      ),
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

    // Switch to Entities tab
    fireEvent.click(screen.getByText(/Entities \(1\)/i));

    const rejectAllBtn = await screen.findByTitle('Reject all occurrences in this group');
    fireEvent.click(rejectAllBtn);

    await waitFor(() => {
      expect(submitReviewSpy).toHaveBeenCalledWith('doc_test_abc', expect.objectContaining({
        candidateId: 'c_01',
        decision: 'REJECT',
        applyToLinked: true,
      }));
    });
  });

  it('opens Redact All Similar modal when Redact all similar button is clicked on CandidateCard', async () => {
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

    const redactSimilarBtns = screen.getAllByTitle('Preview and redact all identical occurrences');
    fireEvent.click(redactSimilarBtns[0]);

    // Confirm modal opens and confirm action triggers applyToSimilar: true
    const confirmBtn = await screen.findByText(/Approve All .* Occurrences/i);
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(submitReviewSpy).toHaveBeenCalledWith('doc_test_abc', expect.objectContaining({
        candidateId: 'c_01',
        decision: 'APPROVE',
        applyToSimilar: true,
      }));
    });
  });

  it('renders PDF bounding-box overlays and supports page navigation in PDF View', async () => {
    vi.spyOn(api, 'getDocumentMetadata').mockResolvedValue({
      ...mockDocMeta,
      filename: 'confidential_report.pdf',
      file_type: 'pdf',
      page_count: 2,
    });
    vi.spyOn(api, 'getDocumentCoordinates').mockResolvedValue({
      document_id: 'doc_test_abc',
      page_count: 2,
      total_spans: 1,
      coordinates: [
        {
          page_number: 1,
          bbox: [50, 100, 150, 115],
          char_start: 9,
          char_end: 23,
          text: 'Swastik Phadke',
          page_x0: 0,
          page_y0: 0,
          page_width: 595,
          page_height: 842,
          page_rotation: 0,
        },
      ],
    });
    vi.spyOn(api, 'getCandidates').mockResolvedValue([
      {
        ...mockCandidates[0],
        page_number: 1,
        bbox: [50, 100, 150, 115],
      },
    ]);

    render(
      <MemoryRouter initialEntries={['/review/doc_test_abc']}>
        <Routes>
          <Route path="/review/:documentId" element={<ReviewWorkspace />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('confidential_report.pdf')).toBeDefined();
    });

    // Switch to PDF View
    fireEvent.click(screen.getByText('PDF View'));

    // Verify bounding-box overlay renders for candidate c_01
    const bboxBtn = await screen.findByTestId('pdf-bbox-c_01');
    expect(bboxBtn).toBeDefined();
    expect(screen.getByTestId('pdf-page-indicator').textContent).toContain('Page 1 of 2');

    // Navigate to next page
    fireEvent.click(screen.getByTitle('Next Page'));
    expect(screen.getByTestId('pdf-page-indicator').textContent).toContain('Page 2 of 2');
  });

  it('displays Stage 3 structured link explanations, conflict badges, and requires confirmation before bulk actions on ambiguous entities', async () => {
    const stage3Candidates = [
      {
        candidate_id: 'c_amb_1',
        document_id: 'doc_test_abc',
        start: 9,
        end: 17,
        text: 'J. Smith',
        type: 'PERSON',
        confidence: 0.72,
        confidence_band: 'MEDIUM',
        sources: ['regex'],
        detector_agreement: 'TYPE_CONFLICT',
        review_status: 'PENDING',
        entity_id: 'ent_amb_1',
      },
    ];
    vi.spyOn(api, 'getCandidates').mockResolvedValue(stage3Candidates);
    vi.spyOn(api, 'getEntities').mockResolvedValue({
      document_id: 'doc_test_abc',
      total_entities: 1,
      degraded_mode: false,
      slm_available: false,
      warnings: [],
      entities: [
        {
          entity_id: 'ent_amb_1',
          canonical_name: 'J. Smith',
          entity_type: 'PERSON',
          candidate_ids: ['c_amb_1'],
          variants: ['J. Smith'],
          confidence: 0.45,
          resolution_tier: 'AMBIGUOUS_CONFLICT',
          is_ambiguous: true,
          evidence: ['Ambiguous initial: matches John Smith and James Smith'],
          link_reasons: [
            {
              rule: 'AMBIGUITY_SAFEGUARD',
              source_variant: 'J. Smith',
              target_variant: 'John Smith, James Smith',
              score: 0.45,
              explanation: "Ambiguous initial 'J. Smith' matches multiple distinct anchors (John Smith, James Smith).",
            },
          ],
        },
      ],
    });

    const submitSpy = vi.spyOn(api, 'submitReviewDecision').mockResolvedValue({
      ...mockSummary,
      approved_count: 1,
      pending_count: 0,
      candidates: [{ ...stage3Candidates[0], review_status: 'APPROVED' }],
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

    fireEvent.click(screen.getByText(/Entities \(1\)/i));

    expect(await screen.findByTestId('entity-ambiguous-badge')).toBeDefined();
    expect(screen.getByTestId('entity-conflict-badge')).toBeDefined();
    expect(screen.getByTestId('entity-link-reasons').textContent).toContain('AMBIGUITY_SAFEGUARD');

    // First click on Approve All for an ambiguous entity opens the confirmation banner without submitting yet
    fireEvent.click(screen.getByTitle('Approve all occurrences in this group'));
    expect(submitSpy).not.toHaveBeenCalled();
    expect(screen.getByTestId('bulk-entity-confirm-banner')).toBeDefined();

    // Confirming executes the bulk approval
    fireEvent.click(screen.getByText('Confirm Approve'));
    await waitFor(() => {
      expect(submitSpy).toHaveBeenCalledWith(
        'doc_test_abc',
        expect.objectContaining({
          candidateId: 'c_amb_1',
          decision: 'APPROVE',
          applyToLinked: true,
        })
      );
    });
  });
});
