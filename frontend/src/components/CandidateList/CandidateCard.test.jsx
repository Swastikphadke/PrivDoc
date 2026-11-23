import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import CandidateCard from './CandidateCard';

describe('CandidateCard Component', () => {
  const mockCandidate = {
    candidate_id: 'c_test_01',
    document_id: 'doc_123',
    start: 10,
    end: 25,
    text: 'Rajesh Sharma',
    type: 'PERSON',
    confidence: 0.94,
    confidence_band: 'HIGH',
    sources: ['gliner', 'regex'],
    page_number: 1,
    review_status: 'PENDING',
    entity_id: 'ent_01',
  };

  it('renders candidate details, confidence band, and status badge', () => {
    render(<CandidateCard candidate={mockCandidate} isSelected={false} />);

    expect(screen.getByText('Rajesh Sharma')).toBeDefined();
    expect(screen.getByText('[10, 25)')).toBeDefined();
    expect(screen.getByText('Pending')).toBeDefined();
    expect(screen.getByText(/High Conf/i)).toBeDefined();
  });

  it('triggers onApprove callback when approve button is clicked', () => {
    const onApprove = vi.fn();
    render(<CandidateCard candidate={mockCandidate} onApprove={onApprove} />);

    const approveBtn = screen.getByRole('button', { name: /approve/i });
    fireEvent.click(approveBtn);

    expect(onApprove).toHaveBeenCalledWith('c_test_01');
  });

  it('triggers onReject callback when reject button is clicked', () => {
    const onReject = vi.fn();
    render(<CandidateCard candidate={mockCandidate} onReject={onReject} />);

    const rejectBtn = screen.getByRole('button', { name: /reject/i });
    fireEvent.click(rejectBtn);

    expect(onReject).toHaveBeenCalledWith('c_test_01');
  });

  it('renders undo button when status is APPROVED or REJECTED', () => {
    const approvedCand = { ...mockCandidate, review_status: 'APPROVED' };
    const onUndo = vi.fn();

    render(<CandidateCard candidate={approvedCand} onUndo={onUndo} />);

    const undoBtn = screen.getByRole('button', { name: /undo/i });
    fireEvent.click(undoBtn);

    expect(onUndo).toHaveBeenCalledWith('c_test_01');
  });
});
