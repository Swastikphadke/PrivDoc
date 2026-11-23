import React from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  Cpu,
  Link2,
  Unlink,
  Check,
  X,
  RotateCcw,
  Eye,
  GitBranch,
  Layers,
  Info,
} from 'lucide-react';
import { CATEGORY_THEMES, STATUS_BADGES, CONFIDENCE_BADGES } from '../../utils/theme';

const TIER_BADGES = {
  EXACT: { label: 'Exact Match', className: 'bg-emerald-950/70 border-emerald-800 text-emerald-300' },
  DETERMINISTIC_VARIANT: { label: 'Deterministic Variant', className: 'bg-cyan-950/70 border-cyan-800 text-cyan-300' },
  PROBABLE_HEURISTIC: { label: 'Probable Heuristic', className: 'bg-indigo-950/70 border-indigo-800 text-indigo-300' },
  AMBIGUOUS_CONFLICT: { label: 'Ambiguous Conflict', className: 'bg-amber-950/80 border-amber-700 text-amber-300' },
  USER_DEFINED: { label: 'User Defined', className: 'bg-purple-950/70 border-purple-800 text-purple-300' },
};

export default function ContextualInspector({
  selectedCandidate = null,
  entities = [],
  candidates = [],
  onSelectCandidate,
  onApprove,
  onReject,
  onUndo,
  onApproveEntity,
  onRejectEntity,
  onUnlinkCandidate,
}) {
  if (!selectedCandidate) {
    return (
      <div
        data-testid="contextual-inspector-panel"
        className="flex flex-col h-full bg-[#090e1a] border border-slate-800 rounded-lg overflow-hidden"
      >
        <div className="px-3.5 py-2.5 bg-slate-900 border-b border-slate-800 flex items-center justify-between text-xs">
          <span className="font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-sky-400" />
            Contextual Inspector
          </span>
        </div>
        <div className="flex-1 p-6 flex flex-col items-center justify-center text-center text-xs text-slate-500 space-y-2">
          <Info className="w-7 h-7 text-slate-600" />
          <p className="font-medium text-slate-400">No Candidate Span Selected</p>
          <p className="text-[11px] text-slate-500 max-w-[220px]">
            Select any highlighted span in the document viewer or candidate list to inspect detection provenance and entity coreference links.
          </p>
        </div>
      </div>
    );
  }

  const theme = CATEGORY_THEMES[selectedCandidate.type] || CATEGORY_THEMES.DEFAULT;
  const statusInfo = STATUS_BADGES[selectedCandidate.review_status] || STATUS_BADGES.PENDING;
  const confInfo = CONFIDENCE_BADGES[selectedCandidate.confidence_band] || CONFIDENCE_BADGES.MEDIUM;
  const confPct = Math.round((selectedCandidate.confidence ?? 0.8) * 100);

  // Locate associated entity cluster if any
  const parentEntity =
    entities.find(
      (e) =>
        e.entity_id === selectedCandidate.entity_id ||
        (Array.isArray(e.candidate_ids) && e.candidate_ids.includes(selectedCandidate.candidate_id))
    ) || null;

  const linkedOccurrences = parentEntity
    ? parentEntity.candidate_ids
        .map((cid) => candidates.find((c) => c.candidate_id === cid))
        .filter(Boolean)
    : [selectedCandidate];

  const tierBadge = parentEntity
    ? TIER_BADGES[parentEntity.resolution_tier] || TIER_BADGES.EXACT
    : null;

  return (
    <div
      data-testid="contextual-inspector-panel"
      className="flex flex-col h-full bg-[#090e1a] border border-slate-800 rounded-lg overflow-hidden shadow-sm text-xs"
    >
      {/* Inspector Header */}
      <div className="px-3.5 py-2.5 bg-slate-900 border-b border-slate-800 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-1.5">
          <Cpu className="w-3.5 h-3.5 text-sky-400" />
          <span className="font-bold uppercase tracking-wider text-slate-200 text-[11px]">
            Contextual Evidence Inspector
          </span>
        </div>
        <span className="font-mono text-[10px] text-slate-400 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">
          {selectedCandidate.candidate_id}
        </span>
      </div>

      {/* Inspector Scrollable Body */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-4">
        {/* Section 1: Selected Span Summary & Decision Controls */}
        <div className="p-3 rounded-md bg-[#0c1322] border border-slate-800 space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <span className={`px-2 py-0.5 rounded border text-[10px] font-semibold ${theme.badgeClass}`}>
                {theme.label}
              </span>
              <span className={`px-2 py-0.5 rounded border text-[10px] ${statusInfo.className}`}>
                {statusInfo.label}
              </span>
            </div>
            <span className="font-mono text-[11px] text-slate-400">
              [{selectedCandidate.start}, {selectedCandidate.end})
              {selectedCandidate.page_number ? ` • P${selectedCandidate.page_number}` : ''}
            </span>
          </div>

          <div className="p-2 rounded bg-slate-950 border border-slate-800/90 font-mono text-xs text-white break-all">
            {selectedCandidate.text}
          </div>

          {/* Quick Occurrence Decision Controls */}
          <div className="flex items-center gap-1.5 pt-1">
            {selectedCandidate.review_status !== 'APPROVED' ? (
              <button
                type="button"
                onClick={() => onApprove?.(selectedCandidate.candidate_id)}
                className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 rounded bg-emerald-950/90 hover:bg-emerald-900 border border-emerald-700 text-emerald-300 font-semibold text-[11px] transition"
              >
                <Check className="w-3.5 h-3.5" />
                <span>Approve Span (A)</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onUndo?.(selectedCandidate.candidate_id)}
                className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 font-medium text-[11px] transition"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Revert to Pending</span>
              </button>
            )}
            {selectedCandidate.review_status !== 'REJECTED' && (
              <button
                type="button"
                onClick={() => onReject?.(selectedCandidate.candidate_id)}
                className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-white font-medium text-[11px] transition"
              >
                <X className="w-3.5 h-3.5" />
                <span>Reject Span (R)</span>
              </button>
            )}
          </div>
        </div>

        {/* Section 2: Detection Provenance & Heuristic Evidence */}
        <div className="p-3 rounded-md bg-[#0c1322] border border-slate-800 space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Detection Provenance
            </span>
            <span className="text-[10px] font-mono text-slate-400 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">
              {selectedCandidate.confidence_type || 'HEURISTIC_EVIDENCE'}
            </span>
          </div>

          {/* Evidence Bar */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px]">
              <span className={`font-semibold flex items-center gap-1.5 ${confInfo.className}`}>
                <span className={`w-2 h-2 rounded-full ${confInfo.dotClass}`} />
                {confInfo.label}
              </span>
              <span className="font-mono text-slate-200 font-semibold">{confPct}% evidence weight</span>
            </div>
            <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden border border-slate-800">
              <div
                className={`h-full ${confInfo.dotClass}`}
                style={{ width: `${Math.min(100, Math.max(10, confPct))}%` }}
              />
            </div>
          </div>

          {/* Detector Sources & Agreement */}
          <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-slate-800/70">
            <div className="flex items-center gap-1">
              <span className="text-[11px] text-slate-400">Detectors:</span>
              {selectedCandidate.sources?.map((src) => (
                <span
                  key={src}
                  className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-sky-300 font-mono text-[10px] uppercase"
                >
                  {src}
                </span>
              ))}
            </div>

            {selectedCandidate.detector_agreement === 'MULTI_DETECTOR_CONSENSUS' && (
              <span className="px-1.5 py-0.5 rounded bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-[10px] font-semibold">
                Consensus
              </span>
            )}
            {selectedCandidate.detector_agreement === 'TYPE_CONFLICT' && (
              <span className="px-1.5 py-0.5 rounded bg-rose-950/80 border border-rose-800 text-rose-300 text-[10px] font-semibold">
                Category Conflict
              </span>
            )}
          </div>

          {/* Why it was detected (Explanation & Context Signals) */}
          <div className="space-y-1.5 pt-1 border-t border-slate-800/70">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block">
              Why This Span Was Flagged
            </span>
            {selectedCandidate.explanation && selectedCandidate.explanation.length > 0 ? (
              <ul className="space-y-1 text-[11px] text-slate-300">
                {selectedCandidate.explanation.map((exp, i) => (
                  <li key={i} className="flex items-start gap-1.5 leading-snug">
                    <span className="text-sky-400 mt-0.5">•</span>
                    <span>{exp}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[11px] text-slate-400">
                Matched {selectedCandidate.type} pattern in canonical text stream.
              </p>
            )}

            {selectedCandidate.context_signals && selectedCandidate.context_signals.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {selectedCandidate.context_signals.map((sig, idx) => (
                  <span
                    key={idx}
                    className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-400 font-mono text-[10px]"
                  >
                    {sig}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Section 3: Entity Relationship & Coreference Cluster Visualization */}
        {parentEntity && (
          <div
            data-testid="contextual-entity-graph"
            className={`p-3 rounded-md bg-[#0c1322] border space-y-3 ${
              parentEntity.is_ambiguous ? 'border-amber-700/80' : 'border-slate-800'
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                  <GitBranch className="w-3 h-3 text-sky-400" />
                  Entity Coreference Cluster
                </span>
                <div className="flex flex-wrap items-center gap-1.5 mt-1">
                  <span className="font-bold text-white text-xs">{parentEntity.canonical_name}</span>
                  {tierBadge && (
                    <span className={`px-1.5 py-0.5 rounded border text-[10px] font-medium ${tierBadge.className}`}>
                      {tierBadge.label}
                    </span>
                  )}
                </div>
              </div>
              <span className="font-mono text-[11px] text-cyan-400 font-semibold shrink-0">
                {Math.round((parentEntity.confidence ?? 1) * 100)}%
              </span>
            </div>

            {parentEntity.is_ambiguous && (
              <div className="p-2 rounded bg-amber-950/60 border border-amber-800 text-amber-200 text-[11px] flex items-start gap-2">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                <span>
                  <strong>Ambiguity Safeguard Active:</strong> Multiple distinct anchors match this mention. Automatic
                  merge was blocked to prevent false coreference.
                </span>
              </div>
            )}

            {/* Visual Node-Link Cluster Representation */}
            <div className="p-2.5 rounded bg-slate-950 border border-slate-800/90 space-y-2">
              <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                <span>ANCHOR: {parentEntity.entity_id}</span>
                <span>{linkedOccurrences.length} occurrence(s)</span>
              </div>
              <div className="pl-2 border-l-2 border-sky-600/60 space-y-1.5">
                {parentEntity.variants?.map((variant) => (
                  <div key={variant} className="flex items-center gap-2 text-[11px]">
                    <span className="w-2 h-0.5 bg-sky-500/70" />
                    <span className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 font-mono text-slate-200">
                      {variant}
                    </span>
                    {variant === parentEntity.canonical_name && (
                      <span className="text-[9px] uppercase font-mono text-sky-400">canonical</span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Structured Link Reasons */}
            {parentEntity.link_reasons && parentEntity.link_reasons.length > 0 && (
              <div className="space-y-1">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block">
                  Resolution Evidence Rules
                </span>
                {parentEntity.link_reasons.map((lr, idx) => (
                  <div
                    key={idx}
                    className="p-2 rounded bg-slate-950/80 border border-slate-800/80 text-[11px] space-y-0.5"
                  >
                    <div className="flex items-center justify-between font-mono text-[10px]">
                      <span className="text-cyan-400 font-semibold">{lr.rule}</span>
                      {typeof lr.score === 'number' && (
                        <span className="text-slate-400">{Math.round(lr.score * 100)}%</span>
                      )}
                    </div>
                    <p className="text-slate-300 text-[11px] leading-snug">{lr.explanation}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Interactive Linked Occurrence Jump List */}
            <div className="space-y-1 pt-1 border-t border-slate-800/70">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block">
                Navigate Cluster Occurrences
              </span>
              <div className="space-y-1">
                {linkedOccurrences.map((occ, idx) => {
                  const isCurrent = occ.candidate_id === selectedCandidate.candidate_id;
                  const occStatus = STATUS_BADGES[occ.review_status] || STATUS_BADGES.PENDING;
                  return (
                    <div
                      key={occ.candidate_id}
                      onClick={() => onSelectCandidate?.(occ.candidate_id)}
                      className={`p-1.5 rounded border flex items-center justify-between cursor-pointer transition text-[11px] ${
                        isCurrent
                          ? 'bg-sky-950/60 border-sky-600 text-white'
                          : 'bg-slate-950 border-slate-800/70 text-slate-300 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center gap-1.5 truncate">
                        <span className="font-mono text-[10px] text-slate-500">#{idx + 1}</span>
                        <span className="font-mono truncate max-w-[110px]">{occ.text}</span>
                        <span className="font-mono text-[10px] text-slate-500">
                          [{occ.start},{occ.end})
                        </span>
                      </div>
                      <span className={`px-1 py-0.2 rounded border text-[9px] ${occStatus.className}`}>
                        {occStatus.label}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
