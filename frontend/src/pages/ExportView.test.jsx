import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import ExportView from './ExportView';
import * as api from '../services/api';

describe('ExportView Page', () => {
  const mockDocMeta = {
    document_id: 'doc_exp_123',
    filename: 'executive_memo.pdf',
    file_type: 'pdf',
    status: 'PROCESSED',
    page_count: 2,
    text_length: 500,
    extracted_text: 'Strictly confidential memo regarding Vikram Malhotra and contact details.',
    warnings: [],
  };

  const mockCandidates = [
    {
      candidate_id: 'c_01',
      document_id: 'doc_exp_123',
      start: 36,
      end: 51,
      text: 'Vikram Malhotra',
      type: 'PERSON',
      confidence: 0.98,
      confidence_band: 'HIGH',
      sources: ['regex'],
      review_status: 'APPROVED',
    },
    {
      candidate_id: 'c_02',
      document_id: 'doc_exp_123',
      start: 0,
      end: 8,
      text: 'Strictly',
      type: 'PERSON',
      confidence: 0.4,
      confidence_band: 'LOW',
      sources: ['gliner'],
      review_status: 'REJECTED',
    },
  ];

  const mockSummary = {
    total_candidates: 2,
    approved: 1,
    rejected: 1,
    pending: 0,
    completion_percentage: 100.0,
    is_complete: true,
  };

  const mockVerifiedResult = {
    document_id: 'doc_exp_123',
    export_state: 'VERIFIED',
    file_type: 'pdf',
    export_filename: 'sanitized_executive_memo.pdf',
    approved_redactions_applied: 1,
    rejected_spans_preserved: 1,
    unreviewed_spans_preserved: 0,
    sanitized_text_preview: 'Strictly confidential memo regarding [PERSON] and contact details.',
    reconstructed_pdf_used: false,
    layout_warning: null,
    download_ready: true,
    verification: {
      status: 'PASSED',
      checks_run: [
        'File Integrity Check',
        'Direct Text Scan (0 leaks)',
        'Known Variants & Substrings (0 leaks)',
        'Normalized Pattern Check',
        'PDF Annotation Scrubbing',
        'PDF Metadata Cleansing',
        'PDF Embedded Files Check',
        'PDF JavaScript & Active Content',
      ],
      issues: [],
      warnings: [],
      verified_at: '2026-11-23T06:30:00Z',
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(api, 'getDocumentMetadata').mockResolvedValue(mockDocMeta);
    vi.spyOn(api, 'getCandidates').mockResolvedValue(mockCandidates);
    vi.spyOn(api, 'getReviewSummary').mockResolvedValue(mockSummary);
    vi.spyOn(api, 'getExportStatus').mockResolvedValue(null);
    vi.spyOn(api, 'redactDocument').mockResolvedValue(mockVerifiedResult);
    vi.spyOn(api, 'reconstructPdf').mockResolvedValue({
      ...mockVerifiedResult,
      reconstructed_pdf_used: true,
      layout_warning: 'Export generated via clean-text PDF reconstruction. Original graphical layout, styling, and embedded images were omitted to guarantee verifiable privacy.',
    });
    vi.spyOn(api, 'downloadExport').mockResolvedValue({ data: new ArrayBuffer(8) });
  });

  const renderComponent = () => {
    return render(
      <MemoryRouter initialEntries={['/export/doc_exp_123']}>
        <Routes>
          <Route path="/export/:documentId" element={<ExportView />} />
        </Routes>
      </MemoryRouter>
    );
  };

  it('renders document metadata and review gatekeeper status correctly', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(/executive_memo\.pdf/i)).toBeDefined();
      expect(screen.getByText(/Document Redaction & Export/i)).toBeDefined();
      expect(screen.getByText(/All Candidates Reviewed/i)).toBeDefined();
    });

    expect(screen.getByText('Approved for Redaction')).toBeDefined();
    expect(screen.getByText('Rejected (Preserved)')).toBeDefined();
  });

  it('allows changing placeholder options including ENTITY_INDEXED and displays pseudonymization disclosure', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(/\[CATEGORY\]/i)).toBeDefined();
    });

    // Verify pseudonymization vs. anonymization disclosure banner is rendered
    const disclosure = screen.getByTestId('pseudonymization-disclosure-banner');
    expect(disclosure.textContent).toMatch(/not guaranteed anonymization/i);

    // Select ENTITY_INDEXED ([CATEGORY_#]) option
    const entityIndexedRadio = screen.getByDisplayValue('ENTITY_INDEXED');
    fireEvent.click(entityIndexedRadio);
    expect(entityIndexedRadio.checked).toBe(true);

    const genericRadio = screen.getByDisplayValue('GENERIC');
    fireEvent.click(genericRadio);
    expect(genericRadio.checked).toBe(true);
  });

  it('triggers redaction execution and displays verification audit report', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(/Execute Redaction & Verify Output/i)).toBeDefined();
    });

    const redactButton = screen.getByText(/Execute Redaction & Verify Output/i);
    fireEvent.click(redactButton);

    await waitFor(() => {
      expect(api.redactDocument).toHaveBeenCalledWith('doc_exp_123', {
        placeholderStyle: 'CATEGORY',
        forceTextReconstruction: false,
      });
      expect(screen.getByText(/Post-Export Verification Report/i)).toBeDefined();
      expect(screen.getByText(/EXPORT VERIFIED SAFE/i)).toBeDefined();
      expect(screen.getByText(/Direct Text Scan \(0 leaks\)/i)).toBeDefined();
      expect(screen.getByText(/Download sanitized_executive_memo\.pdf/i)).toBeDefined();
    });
  });

  it('handles download button click when verified', async () => {
    window.URL.createObjectURL = vi.fn().mockReturnValue('blob:http://localhost/mock-blob');
    window.URL.revokeObjectURL = vi.fn();

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(/Execute Redaction & Verify Output/i)).toBeDefined();
    });

    fireEvent.click(screen.getByText(/Execute Redaction & Verify Output/i));

    await waitFor(() => {
      expect(screen.getByText(/Download sanitized_executive_memo\.pdf/i)).toBeDefined();
    });

    const downloadBtn = screen.getByText(/Download sanitized_executive_memo\.pdf/i);
    fireEvent.click(downloadBtn);

    await waitFor(() => {
      expect(api.downloadExport).toHaveBeenCalledWith('doc_exp_123');
    });
  });

  it('passes selected txt format when downloading a PDF session as Plain Text (.txt)', async () => {
    window.URL.createObjectURL = vi.fn().mockReturnValue('blob:http://localhost/mock-blob');
    window.URL.revokeObjectURL = vi.fn();

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(/Execute Redaction & Verify Output/i)).toBeDefined();
    });

    // Switch export format to Plain Text (.txt)
    fireEvent.click(screen.getByText(/Plain Text \(\.txt\)/i));
    fireEvent.click(screen.getByText(/Execute Redaction & Verify Output/i));

    await waitFor(() => {
      expect(screen.getByText(/Download sanitized_executive_memo\.pdf/i)).toBeDefined();
    });

    fireEvent.click(screen.getByText(/Download sanitized_executive_memo\.pdf/i));

    await waitFor(() => {
      expect(api.downloadExport).toHaveBeenCalledWith('doc_exp_123', 'txt');
    });
  });

  it('displays verification failure alert when export verification fails', async () => {
    const failedResult = {
      ...mockVerifiedResult,
      export_state: 'FAILED',
      download_ready: false,
      verification: {
        status: 'FAILED',
        checks_run: ['File Integrity Check', 'Direct Text Scan (1 leaks)'],
        issues: [
          {
            check_name: 'Direct Text Scan',
            severity: 'CRITICAL',
            description: 'Approved PERSON candidate remains present in exported text.',
            page_number: 1,
            candidate_id: 'c_01',
            entity_id: null,
          },
        ],
        warnings: [],
        verified_at: '2026-11-23T06:30:00Z',
      },
    };

    api.redactDocument.mockResolvedValueOnce(failedResult);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(/Execute Redaction & Verify Output/i)).toBeDefined();
    });

    fireEvent.click(screen.getByText(/Execute Redaction & Verify Output/i));

    await waitFor(() => {
      expect(screen.getByText(/VERIFICATION FAILED \(EXPORT BLOCKED\)/i)).toBeDefined();
      expect(
        screen.getByText(/Approved PERSON candidate remains present in exported text\./i)
      ).toBeDefined();
      expect(screen.getByText(/Download Blocked \(Unverified\)/i)).toBeDefined();
    });
  });

  it('shows layout loss warning when clean-text reconstruction is used', async () => {
    const reconstructedResult = {
      ...mockVerifiedResult,
      reconstructed_pdf_used: true,
      layout_warning: 'Reconstructed clean layout PDF from sanitized text; original styling was not preserved.',
    };

    api.redactDocument.mockResolvedValueOnce(reconstructedResult);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(/Execute Redaction & Verify Output/i)).toBeDefined();
    });

    fireEvent.click(screen.getByText(/Execute Redaction & Verify Output/i));

    await waitFor(() => {
      expect(screen.getByText(/Layout Notice/i)).toBeDefined();
      expect(
        screen.getByText(/Reconstructed clean layout PDF from sanitized text/i)
      ).toBeDefined();
    });
  });

  it('offers clean-text reconstruction as a separate user-triggered action when native verification fails', async () => {
    const failedResult = {
      ...mockVerifiedResult,
      export_state: 'FAILED',
      download_ready: false,
      reconstructed_pdf_used: false,
      reconstruction_offered: true,
      layout_warning: 'Native PDF redaction verification failed: extractable sensitive content or unsupported structures were detected.',
      verification: {
        status: 'FAILED',
        checks_run: ['File Integrity Check', 'Direct Text Scan'],
        issues: [
          {
            check_name: 'Direct Text Scan',
            severity: 'ERROR',
            description: 'Approved candidate leak detected.',
            page_number: 1,
            candidate_id: 'c_01',
          },
        ],
        warnings: [],
        verified_at: '2026-11-23T06:30:00Z',
      },
    };

    api.redactDocument.mockResolvedValueOnce(failedResult);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(/Execute Redaction & Verify Output/i)).toBeDefined();
    });

    fireEvent.click(screen.getByText(/Execute Redaction & Verify Output/i));

    await waitFor(() => {
      expect(screen.getByText(/VERIFICATION FAILED \(EXPORT BLOCKED\)/i)).toBeDefined();
      expect(screen.getByText(/Native PDF Verification Failed — Clean-Text Reconstruction Available/i)).toBeDefined();
      expect(screen.getByText(/Reconstruct Clean-Text PDF Alternative/i)).toBeDefined();
    });
  });

  it('allows user to explicitly trigger clean-text reconstruction after native verification failure and promotes to VERIFIED on pass', async () => {
    const failedResult = {
      ...mockVerifiedResult,
      export_state: 'FAILED',
      download_ready: false,
      reconstructed_pdf_used: false,
      reconstruction_offered: true,
      layout_warning: 'Native PDF redaction verification failed.',
      verification: {
        status: 'FAILED',
        checks_run: ['File Integrity Check'],
        issues: [{ check_name: 'Direct Text Scan', severity: 'ERROR', description: 'Leak', page_number: 1 }],
        warnings: [],
        verified_at: '2026-11-23T06:30:00Z',
      },
    };

    api.redactDocument.mockResolvedValueOnce(failedResult);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(/Execute Redaction & Verify Output/i)).toBeDefined();
    });

    fireEvent.click(screen.getByText(/Execute Redaction & Verify Output/i));

    await waitFor(() => {
      expect(screen.getByText(/Reconstruct Clean-Text PDF Alternative/i)).toBeDefined();
    });

    // Explicitly click clean-text reconstruction button
    fireEvent.click(screen.getByText(/Reconstruct Clean-Text PDF Alternative/i));

    await waitFor(() => {
      expect(api.reconstructPdf).toHaveBeenCalledWith('doc_exp_123', {
        placeholderStyle: 'CATEGORY',
      });
      expect(screen.getByText(/EXPORT VERIFIED SAFE/i)).toBeDefined();
      expect(screen.getByText(/Download sanitized_executive_memo\.pdf/i)).toBeDefined();
    });
  });
});
