import React, { useMemo, useRef } from 'react';
import { CATEGORY_THEMES, STATUS_BADGES } from '../../utils/theme';
import { PlusCircle, ShieldAlert } from 'lucide-react';

export default function TextViewer({
  canonicalText = '',
  text = '',
  candidates = [],
  selectedCandidateId = null,
  onSelectCandidate,
  onManualSelect,
  onTextSelected,
}) {
  const containerRef = useRef(null);
  const rawText = canonicalText || text || '';
  const notifySelect = onManualSelect || onTextSelected;

  /**
   * Split canonical text into non-overlapping segments for rendering highlights.
   * Uses half-open offsets [start, end).
   */
  const segments = useMemo(() => {
    if (!rawText) return [];
    if (!candidates || candidates.length === 0) {
      return [{ text: rawText, candidate: null, key: 'plain_all' }];
    }

    // Sort candidates by start offset ascending
    const sorted = [...candidates].sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start));

    const segs = [];
    let curr = 0;

    for (const cand of sorted) {
      // If candidate is out of bounds or behind current offset, skip or handle overlap
      if (cand.start < curr) continue;
      if (cand.end > rawText.length) continue;

      // Plain text before candidate
      if (cand.start > curr) {
        segs.push({
          text: rawText.slice(curr, cand.start),
          candidate: null,
          key: `plain_${curr}_${cand.start}`,
        });
      }

      // Candidate text
      segs.push({
        text: rawText.slice(cand.start, cand.end),
        candidate: cand,
        key: `cand_${cand.candidate_id}`,
      });

      curr = cand.end;
    }

    // Remaining text after last candidate
    if (curr < rawText.length) {
      segs.push({
        text: rawText.slice(curr),
        candidate: null,
        key: `plain_${curr}_end`,
      });
    }

    return segs;
  }, [rawText, candidates]);

  /**
   * Handle mouse selection inside text container to propose manual redaction span.
   */
  const handleMouseUp = () => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return;

    const selectedText = selection.toString().trim();
    if (!selectedText || selectedText.length < 2) return;

    // Find first occurrence of selected text within canonical text near selection focus
    const index = rawText.indexOf(selectedText);
    if (index !== -1) {
      notifySelect?.({
        start: index,
        end: index + selectedText.length,
        text: selectedText,
      });
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-950 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
      {/* Viewer Header */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900 border-b border-slate-800 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-200">Canonical Text Representation</span>
          <span className="text-slate-400 font-mono">({rawText.length.toLocaleString()} characters)</span>
        </div>
        <div className="flex items-center gap-2 text-slate-400">
          <span>Select text with mouse to add manual redaction</span>
          <kbd className="px-1.5 py-0.5 bg-slate-800 border border-slate-700 rounded text-[10px] text-cyan-300 font-mono">
            M
          </kbd>
        </div>
      </div>

      {/* Text Body */}
      <div
        ref={containerRef}
        onMouseUp={handleMouseUp}
        className="flex-1 p-6 overflow-y-auto font-mono text-sm leading-relaxed text-slate-300 whitespace-pre-wrap select-text selection:bg-cyan-900 selection:text-cyan-100"
      >
        {!rawText ? (
          <div className="p-8 text-center text-slate-500 text-xs">No canonical text available.</div>
        ) : (
          segments.map((seg) => {
            if (!seg.candidate) {
              return <span key={seg.key}>{seg.text}</span>;
            }

            const cand = seg.candidate;
            const theme = CATEGORY_THEMES[cand.type] || CATEGORY_THEMES.DEFAULT;
            const isSelected = cand.candidate_id === selectedCandidateId;
            const isApproved = cand.review_status === 'APPROVED';
            const isRejected = cand.review_status === 'REJECTED';

            return (
              <mark
                key={seg.key}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectCandidate?.(cand.candidate_id);
                }}
                className={`cursor-pointer px-1 py-0.5 rounded transition-all inline-block ${
                  theme.highlightClass
                } ${
                  isSelected ? 'ring-2 ring-cyan-400 ring-offset-2 ring-offset-slate-950 shadow-md' : ''
                } ${
                  isApproved ? 'bg-emerald-950/80 border-b-2 border-emerald-500 text-emerald-200 font-medium' : ''
                } ${
                  isRejected ? 'opacity-40 line-through text-slate-400 border-b-0' : ''
                }`}
                title={`${cand.type} (${cand.confidence_band} Confidence) — Status: ${cand.review_status}`}
              >
                {seg.text}
                <span className="ml-1 text-[10px] font-sans uppercase font-bold opacity-75 select-none">
                  [{theme.label}]
                </span>
              </mark>
            );
          })
        )}
      </div>
    </div>
  );
}
