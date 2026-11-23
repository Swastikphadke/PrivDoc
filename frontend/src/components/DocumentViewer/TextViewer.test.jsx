import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import TextViewer from './TextViewer';

describe('TextViewer Component', () => {
  const sampleText = 'Contact Alice Smith at alice@example.com for details.';
  const sampleCandidates = [
    {
      candidate_id: 'c_01',
      start: 8,
      end: 19,
      text: 'Alice Smith',
      type: 'PERSON',
      confidence: 0.95,
      confidence_band: 'HIGH',
      review_status: 'PENDING',
    },
    {
      candidate_id: 'c_02',
      start: 23,
      end: 40,
      text: 'alice@example.com',
      type: 'EMAIL',
      confidence: 1.0,
      confidence_band: 'HIGH',
      review_status: 'APPROVED',
    },
  ];

  it('renders canonical text with highlight spans for detected candidates', () => {
    const onSelectCandidate = vi.fn();

    render(
      <TextViewer
        text={sampleText}
        candidates={sampleCandidates}
        selectedCandidateId="c_01"
        onSelectCandidate={onSelectCandidate}
      />
    );

    expect(screen.getByText('Alice Smith')).toBeDefined();
    expect(screen.getByText('alice@example.com')).toBeDefined();
    expect(screen.getByText(/Contact/)).toBeDefined();
  });

  it('calls onSelectCandidate when candidate highlight is clicked', () => {
    const onSelectCandidate = vi.fn();

    render(
      <TextViewer
        text={sampleText}
        candidates={sampleCandidates}
        selectedCandidateId={null}
        onSelectCandidate={onSelectCandidate}
      />
    );

    const aliceSpan = screen.getByText('Alice Smith');
    fireEvent.click(aliceSpan);

    expect(onSelectCandidate).toHaveBeenCalledWith('c_01');
  });

  it('displays empty state when no text is provided', () => {
    render(<TextViewer text="" candidates={[]} />);
    expect(screen.getByText('No canonical text available.')).toBeDefined();
  });
});
