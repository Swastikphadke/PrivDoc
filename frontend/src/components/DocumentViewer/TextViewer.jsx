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
      return [{ text: rawText, candidate: null, start: 0, end: rawText.length, key: 'plain_all' }];
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
          start: curr,
          end: cand.start,
          key: `plain_${curr}_${cand.start}`,
        });
      }

      // Candidate text
      segs.push({
        text: rawText.slice(cand.start, cand.end),
        candidate: cand,
        start: cand.start,
        end: cand.end,
        key: `cand_${cand.candidate_id}`,
      });

      curr = cand.end;
    }

    // Remaining text after last candidate
    if (curr < rawText.length) {
      segs.push({
        text: rawText.slice(curr),
        candidate: null,
        start: curr,
        end: rawText.length,
        key: `plain_${curr}_end`,
      });
    }

    return segs;
  }, [rawText, candidates]);

  /**
   * Handle mouse selection inside text container to propose manual redaction span.
   * Uses DOM Range offset relative to the segment's canonical data-char-start attribute
   * so selecting repeated words in a document resolves the exact selected occurrence.
   */
  const handleMouseUp = () => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return;

    const rawSelected = selection.toString();
    const selectedText = rawSelected.trim();
    if (!selectedText || selectedText.length < 2) return;

    let resolvedStart = -1;

    try {
      if (selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        const findCharStart = (node) => {
          let el = node?.nodeType === 3 ? node.parentElement : node;
          while (el && el !== containerRef.current) {
            if (el.dataset?.charStart !== undefined) {
              return parseInt(el.dataset.charStart, 10);
            }
            el = el.parentElement;
          }
          return null;
        };

        const segStart = findCharStart(range.startContainer);
        if (segStart !== null && !Number.isNaN(segStart)) {
          const leadingWhitespace = rawSelected.length - rawSelected.trimStart().length;
          const exactCandidateIdx = segStart + range.startOffset + leadingWhitespace;

          if (rawText.slice(exactCandidateIdx, exactCandidateIdx + selectedText.length) === selectedText) {
            resolvedStart = exactCandidateIdx;
          } else {
            const winStart = Math.max(0, exactCandidateIdx - 15);
            const localIdx = rawText.indexOf(selectedText, winStart);
            if (localIdx !== -1 && localIdx <= exactCandidateIdx + 25) {
              resolvedStart = localIdx;
            }
          }
        }
      }
    } catch {
      // Fallback to indexOf below if synthetic test selection lacks DOM range
    }

    if (resolvedStart === -1) {
      resolvedStart = rawText.indexOf(selectedText);
    }

    if (resolvedStart !== -1) {
      notifySelect?.({
        start: resolvedStart,
        end: resolvedStart + selectedText.length,
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
              return (
                <span key={seg.key} data-char-start={seg.start} data-char-end={seg.end}>
                  {seg.text}
                </span>
              );
            }

            const cand = seg.candidate;
            const theme = CATEGORY_THEMES[cand.type] || CATEGORY_THEMES.DEFAULT;
            const isSelected = cand.candidate_id === selectedCandidateId;
            const isApproved = cand.review_status === 'APPROVED';
            const isRejected = cand.review_status === 'REJECTED';

            return (
              <mark
                key={seg.key}
                data-char-start={seg.start}
                data-char-end={seg.end}
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
                <span data-char-start={seg.start} data-char-end={seg.end}>
                  {seg.text}
                </span>
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
