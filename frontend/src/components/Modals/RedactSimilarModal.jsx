import React from 'react';
import { CopyCheck, X, AlertCircle, ShieldAlert } from 'lucide-react';
import { CATEGORY_THEMES, REVIEW_STATUS_THEMES } from '../../utils/theme';

export default function RedactSimilarModal({
  isOpen,
  onClose,
  onConfirm,
  targetCandidate,
  matchingCandidates = [],
  isSubmitting = false,
}) {
  if (!isOpen || !targetCandidate) return null;

  const affectedCount = matchingCandidates.length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
      <div
        className="w-full max-w-lg rounded-xl bg-slate-900 border border-slate-800 shadow-2xl p-6 space-y-5"
        role="dialog"
        aria-modal="true"
        aria-labelledby="redact-similar-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-purple-950 border border-purple-800/80 text-purple-400">
              <CopyCheck className="w-4 h-4" />
            </div>
            <div>
              <h3 id="redact-similar-title" className="text-base font-bold text-white">
                Redact All Similar Occurrences
              </h3>
              <p className="text-xs text-slate-400">
                Explicit preview of affected candidates matching target text
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
            aria-label="Close modal"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Target Text Info */}
        <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
          <span className="text-[11px] text-slate-400 font-medium">Matching Target Text:</span>
          <p className="font-mono text-xs font-semibold text-white bg-slate-900 p-2 rounded border border-slate-800">
            "{targetCandidate.text}"
          </p>
        </div>

        {/* Affected Candidates Preview Table */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
            <span>Affected Occurrences ({affectedCount})</span>
            <span className="text-[11px] text-amber-400 font-normal flex items-center gap-1">
              <AlertCircle className="w-3 h-3" /> All will be marked as APPROVED
            </span>
          </div>

          <div className="max-h-48 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950 p-2 space-y-1.5">
            {matchingCandidates.map((cand, idx) => {
              const theme = CATEGORY_THEMES[cand.type] || CATEGORY_THEMES.DEFAULT;
              const statusTheme = REVIEW_STATUS_THEMES[cand.review_status] || REVIEW_STATUS_THEMES.PENDING;

              return (
                <div
                  key={cand.candidate_id || idx}
                  className="flex items-center justify-between p-2 rounded bg-slate-900/80 border border-slate-800/60 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-slate-400 text-[11px]">
                      [{cand.start}, {cand.end})
                    </span>
                    <span className={`px-1.5 py-0.2 rounded text-[10px] font-semibold border ${theme.badgeClass}`}>
                      {theme.label}
                    </span>
                    <span className="font-mono text-slate-200 text-xs">
                      {cand.text}
                    </span>
                  </div>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${statusTheme.badgeClass}`}>
                    {statusTheme.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Warning Banner */}
        <div className="p-3 rounded-lg bg-amber-950/40 border border-amber-800/60 flex items-start gap-2.5 text-xs text-amber-200">
          <ShieldAlert className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
          <p>
            This bulk action marks all {affectedCount} matching occurrence{affectedCount > 1 ? 's' : ''} for
            redaction. You can still undo individual decisions before final document export.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-end gap-3 pt-2 border-t border-slate-800">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isSubmitting}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium transition shadow-lg shadow-purple-600/20 disabled:opacity-50"
          >
            <CopyCheck className="w-3.5 h-3.5" />
            <span>{isSubmitting ? 'Applying...' : `Approve All ${affectedCount} Occurrences`}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
