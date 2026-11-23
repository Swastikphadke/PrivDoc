import React, { useState } from 'react';
import {
  Check,
  X,
  RotateCcw,
  Eye,
  EyeOff,
  Copy,
  Link2,
  Layers,
  ChevronDown,
} from 'lucide-react';
import { CATEGORY_THEMES, CONFIDENCE_BADGES, STATUS_BADGES } from '../../utils/theme';

export default function CandidateCard({
  candidate,
  isSelected = false,
  onSelect,
  onApprove,
  onReject,
  onUndo,
  onChangeCategory,
  onRedactSimilar,
  onApproveLinked,
  linkedCount = 1,
}) {
  const [isMasked, setIsMasked] = useState(false);
  const [isChangingType, setIsChangingType] = useState(false);

  const theme = CATEGORY_THEMES[candidate.type] || CATEGORY_THEMES.DEFAULT;
  const statusInfo = STATUS_BADGES[candidate.review_status] || STATUS_BADGES.PENDING;
  const confInfo = CONFIDENCE_BADGES[candidate.confidence_band] || CONFIDENCE_BADGES.MEDIUM;

  const displaySnippet = isMasked
    ? candidate.text.slice(0, 1) + '*'.repeat(Math.max(2, candidate.text.length - 2)) + candidate.text.slice(-1)
    : candidate.text;

  const categories = ['PERSON', 'EMAIL', 'PHONE', 'ADDRESS', 'ID_LIKE'];

  return (
    <div
      onClick={() => onSelect?.(candidate.candidate_id)}
      className={`p-3.5 rounded-lg border text-xs transition-all cursor-pointer ${
        isSelected
          ? 'bg-slate-900 border-cyan-500 shadow-md ring-1 ring-cyan-500/50'
          : 'bg-slate-900/70 border-slate-800 hover:border-slate-700 hover:bg-slate-900'
      }`}
    >
      {/* Header: Category Badge + Review Status */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5">
          <span className={`px-2 py-0.5 rounded border text-[11px] font-semibold ${theme.badgeClass}`}>
            {theme.label}
          </span>
          <span className={`px-2 py-0.5 rounded border text-[11px] ${statusInfo.className}`}>
            {statusInfo.label}
          </span>
        </div>

        {/* Confidence Band (Strictly separated from approval) */}
        <div className="flex items-center gap-1 text-[11px] font-medium" title="Detector Confidence Band">
          <span className={`w-2 h-2 rounded-full ${confInfo.dotClass}`} />
          <span className={confInfo.className}>{confInfo.label}</span>
        </div>
      </div>

      {/* Snippet / Text Value */}
      <div className="flex items-center justify-between p-2 rounded bg-slate-950 border border-slate-800/80 my-2 font-mono text-slate-100">
        <span className="truncate max-w-[210px]">{displaySnippet}</span>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setIsMasked((m) => !m);
          }}
          className="p-1 text-slate-500 hover:text-slate-300"
          title={isMasked ? 'Reveal text' : 'Mask text'}
        >
          {isMasked ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* Metadata & Provenance */}
      <div className="flex items-center justify-between text-[11px] text-slate-400 mb-2">
        <span className="font-mono">
          [{candidate.start}, {candidate.end})
        </span>
        <div className="flex items-center gap-1">
          <span>Src:</span>
          {candidate.sources?.map((src) => (
            <span key={src} className="px-1.5 py-0.2 bg-slate-800 rounded text-slate-300 text-[10px]">
              {src}
            </span>
          ))}
        </div>
      </div>

      {/* Explanation & Agreement Signals (Stage 2 Provenance) */}
      {(candidate.explanation?.length > 0 || candidate.is_ambiguous_suggestion || candidate.detector_agreement === 'TYPE_CONFLICT') && (
        <div className="mb-2.5 px-2 py-1 rounded bg-slate-950/70 border border-slate-800/70 text-[10px] text-slate-400 space-y-0.5">
          {candidate.detector_agreement === 'MULTI_DETECTOR_CONSENSUS' && (
            <span className="text-emerald-400 font-semibold block">✓ Multi-Detector Consensus</span>
          )}
          {candidate.detector_agreement === 'TYPE_CONFLICT' && (
            <span className="text-amber-400 font-semibold block">⚠ Detector Category Conflict</span>
          )}
          {candidate.is_ambiguous_suggestion && (
            <span className="text-amber-400 font-semibold block">⚠ Ambiguous Surname Suggestion</span>
          )}
          {candidate.explanation?.[0] && (
            <span className="block truncate" title={candidate.explanation.join(' • ')}>
              {candidate.explanation[0]}
            </span>
          )}
        </div>
      )}

      {/* Actions Toolbar */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
        {/* Approve / Reject Controls */}
        <div className="flex items-center gap-1.5">
          {candidate.review_status !== 'APPROVED' ? (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onApprove?.(candidate.candidate_id);
              }}
              className="flex items-center gap-1 px-2.5 py-1 rounded bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-700 text-emerald-300 text-xs font-medium transition"
              title="Approve Redaction (Shortcut: A)"
            >
              <Check className="w-3.5 h-3.5" />
              <span>Approve</span>
            </button>
          ) : (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onUndo?.(candidate.candidate_id);
              }}
              className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition"
              title="Revert to Pending"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Undo</span>
            </button>
          )}

          {candidate.review_status !== 'REJECTED' && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onReject?.(candidate.candidate_id);
              }}
              className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-400 hover:text-slate-200 text-xs transition"
              title="Reject Redaction (Shortcut: R)"
            >
              <X className="w-3.5 h-3.5" />
              <span>Reject</span>
            </button>
          )}
        </div>

        {/* Change Category or Redact Similar */}
        <div className="relative">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setIsChangingType((v) => !v);
            }}
            className="flex items-center gap-1 px-2 py-1 rounded bg-slate-800/60 hover:bg-slate-800 text-slate-400 text-xs"
            title="Change PII Category"
          >
            <span>Type</span>
            <ChevronDown className="w-3 h-3" />
          </button>

          {isChangingType && (
            <div className="absolute right-0 bottom-full mb-1 w-28 bg-slate-900 border border-slate-700 rounded-lg shadow-xl z-20 py-1">
              {categories.map((cat) => (
                <button
                  key={cat}
                  onClick={(e) => {
                    e.stopPropagation();
                    onChangeCategory?.(candidate.candidate_id, cat);
                    setIsChangingType(false);
                  }}
                  className={`w-full text-left px-2.5 py-1 text-[11px] hover:bg-slate-800 ${
                    candidate.type === cat ? 'text-cyan-400 font-semibold' : 'text-slate-300'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Bulk actions footer */}
      <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-800/50 text-[11px]">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRedactSimilar?.(candidate.candidate_id);
          }}
          className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1"
          title="Preview and redact all identical occurrences"
        >
          <Layers className="w-3 h-3" />
          <span>Redact all similar</span>
        </button>

        {candidate.entity_id && linkedCount > 1 && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onApproveLinked?.(candidate.candidate_id);
            }}
            className="text-purple-400 hover:text-purple-300 flex items-center gap-1"
            title="Approve all occurrences linked to this entity"
          >
            <Link2 className="w-3 h-3" />
            <span>Approve linked ({linkedCount})</span>
          </button>
        )}
      </div>
    </div>
  );
}
