import React, { useState } from 'react';
import { Users, Link2, Unlink, AlertTriangle, CheckCheck, XCircle, ShieldAlert, Eye } from 'lucide-react';
import { CATEGORY_THEMES, STATUS_BADGES } from '../../utils/theme';

const TIER_LABELS = {
  EXACT: { label: 'Exact Match', className: 'bg-emerald-950/60 border-emerald-800/70 text-emerald-300' },
  DETERMINISTIC_VARIANT: { label: 'Deterministic Variant', className: 'bg-cyan-950/60 border-cyan-800/70 text-cyan-300' },
  PROBABLE_HEURISTIC: { label: 'Probable Heuristic', className: 'bg-indigo-950/60 border-indigo-800/70 text-indigo-300' },
  AMBIGUOUS_CONFLICT: { label: 'Ambiguous Conflict', className: 'bg-amber-950/80 border-amber-700 text-amber-300' },
  USER_DEFINED: { label: 'User Linked', className: 'bg-purple-950/60 border-purple-800/70 text-purple-300' },
};

export default function EntityGroupList({
  entities = [],
  candidates = [],
  selectedCandidateId = null,
  onSelectCandidate,
  onApproveEntity,
  onRejectEntity,
  onUnlinkCandidate,
}) {
  // Track pending confirmation for ambiguous or mixed-decision bulk actions: { [entity_id]: 'APPROVE' | 'REJECT' }
  const [confirmActionByEntity, setConfirmActionByEntity] = useState({});

  if (!entities || entities.length === 0) {
    return (
      <div className="p-8 text-center text-slate-500 text-xs">
        <Users className="w-8 h-8 mx-auto mb-2 opacity-30 text-slate-400" />
        <p>No entity clusters resolved.</p>
      </div>
    );
  }

  // Map candidate_id to candidate object
  const candMap = new Map(candidates.map((c) => [c.candidate_id, c]));

  const handleBulkTrigger = (entity, decisionType) => {
    // Require explicit inline confirmation when cluster is marked ambiguous
    if (entity.is_ambiguous && confirmActionByEntity[entity.entity_id] !== decisionType) {
      setConfirmActionByEntity((prev) => ({ ...prev, [entity.entity_id]: decisionType }));
      return;
    }
    setConfirmActionByEntity((prev) => {
      const next = { ...prev };
      delete next[entity.entity_id];
      return next;
    });
    if (decisionType === 'APPROVE') {
      onApproveEntity?.(entity.entity_id);
    } else {
      onRejectEntity?.(entity.entity_id);
    }
  };

  return (
    <div className="space-y-3 p-1">
      {entities.map((entity) => {
        const theme = CATEGORY_THEMES[entity.entity_type] || CATEGORY_THEMES.DEFAULT;
        const linkedCandidates = entity.candidate_ids.map((id) => candMap.get(id)).filter(Boolean);
        const tierBadge = TIER_LABELS[entity.resolution_tier] || TIER_LABELS.EXACT;
        const hasDetectorConflict = linkedCandidates.some(
          (c) => c.detector_agreement === 'TYPE_CONFLICT'
        );
        const pendingConfirm = confirmActionByEntity[entity.entity_id];

        return (
          <div
            key={entity.entity_id}
            data-testid={`entity-card-${entity.entity_id}`}
            className={`p-3.5 rounded-lg bg-slate-900/80 border space-y-2.5 text-xs ${
              entity.is_ambiguous ? 'border-amber-700/80' : 'border-slate-800'
            }`}
          >
            {/* Header: Canonical Name, Category & Resolution Tier */}
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${theme.badgeClass}`}>
                    {theme.label}
                  </span>
                  <span className="font-semibold text-slate-100 text-sm truncate max-w-[180px]">
                    {entity.canonical_name}
                  </span>
                  {entity.resolution_tier && (
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${tierBadge.className}`}
                    >
                      {tierBadge.label}
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-slate-400 mt-0.5">
                  {entity.candidate_ids.length} occurrence{entity.candidate_ids.length > 1 ? 's' : ''} •{' '}
                  <span className="font-mono text-cyan-400 font-medium">
                    {(entity.confidence * 100).toFixed(0)}% link confidence
                  </span>
                </div>
              </div>

              {/* Ambiguity & Detector Conflict Flags */}
              <div className="flex flex-col items-end gap-1">
                {entity.is_ambiguous && (
                  <span
                    data-testid="entity-ambiguous-badge"
                    className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-950/80 border border-amber-800 text-amber-300 text-[10px]"
                    title="Ambiguous variants detected. Not merged automatically."
                  >
                    <AlertTriangle className="w-3 h-3 text-amber-400" />
                    <span>Ambiguous</span>
                  </span>
                )}
                {hasDetectorConflict && (
                  <span
                    data-testid="entity-conflict-badge"
                    className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-rose-950/80 border border-rose-800 text-rose-300 text-[10px]"
                    title="Detector category disagreement on one or more occurrences."
                  >
                    <ShieldAlert className="w-3 h-3 text-rose-400" />
                    <span>Type Conflict</span>
                  </span>
                )}
              </div>
            </div>

            {/* Surface Variants */}
            {entity.variants && entity.variants.length > 1 && (
              <div className="p-2 rounded bg-slate-950 border border-slate-800/80 text-[11px]">
                <span className="text-slate-500 block mb-1">Variants observed:</span>
                <div className="flex flex-wrap gap-1">
                  {entity.variants.map((v) => (
                    <span key={v} className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-200 font-mono text-[10px]">
                      {v}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Structured Link Explanations (Stage 3) */}
            {entity.link_reasons && entity.link_reasons.length > 0 ? (
              <div className="text-[11px] text-slate-400 space-y-1" data-testid="entity-link-reasons">
                <span className="text-slate-500 block font-medium">Structured link explanations:</span>
                <div className="space-y-1">
                  {entity.link_reasons.map((lr, idx) => (
                    <div
                      key={idx}
                      className="p-1.5 rounded bg-slate-950/70 border border-slate-800/60 text-slate-300"
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span className="font-mono text-[10px] text-cyan-400 font-semibold">{lr.rule}</span>
                        {typeof lr.score === 'number' && (
                          <span className="font-mono text-[10px] text-slate-400">
                            {(lr.score * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-300 mt-0.5 leading-snug">{lr.explanation}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              entity.evidence &&
              entity.evidence.length > 0 && (
                <div className="text-[11px] text-slate-400 space-y-0.5">
                  <span className="text-slate-500 block">Link evidence:</span>
                  <ul className="list-disc list-inside space-y-0.5 text-slate-300">
                    {entity.evidence.map((ev, idx) => (
                      <li key={idx} className="truncate">
                        {ev}
                      </li>
                    ))}
                  </ul>
                </div>
              )
            )}

            {/* Non-merged Suggested Links (if any) */}
            {entity.suggested_links && entity.suggested_links.length > 0 && (
              <div className="p-2 rounded bg-amber-950/30 border border-amber-800/50 text-[11px] text-amber-200 space-y-1">
                <span className="font-semibold block text-[10px] uppercase tracking-wider text-amber-300">
                  Suggested Unmerged Links (Review Required)
                </span>
                {entity.suggested_links.map((sl, idx) => (
                  <p key={idx} className="text-[11px] text-amber-200/90">
                    {sl.explanation}
                  </p>
                ))}
              </div>
            )}

            {/* Occurrences list with click-to-inspect, status badges, and Unlink option */}
            <div className="pt-2 border-t border-slate-800/60 space-y-1">
              <span className="text-slate-500 block text-[10px] uppercase tracking-wider font-semibold">
                Occurrences (Click to inspect in document)
              </span>
              <div className="space-y-1">
                {linkedCandidates.map((cand) => {
                  const statusBadge = STATUS_BADGES[cand.review_status] || STATUS_BADGES.PENDING;
                  const isSelected = cand.candidate_id === selectedCandidateId;
                  return (
                    <div
                      key={cand.candidate_id}
                      onClick={() => onSelectCandidate?.(cand.candidate_id)}
                      className={`flex items-center justify-between py-1 px-1.5 rounded border text-[11px] cursor-pointer transition ${
                        isSelected
                          ? 'bg-sky-950/60 border-sky-600/80'
                          : 'bg-slate-950/60 border-slate-800/40 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center gap-1.5 min-w-0">
                        <Eye className="w-3 h-3 text-slate-500 shrink-0" />
                        <span className="font-mono text-slate-200 truncate max-w-[130px]">
                          {cand.text} <span className="text-slate-500">[{cand.start}, {cand.end})</span>
                        </span>
                        <span className={`px-1 py-0.2 rounded text-[9px] font-semibold border ${statusBadge.className}`}>
                          {statusBadge.label}
                        </span>
                        {cand.detector_agreement === 'TYPE_CONFLICT' && (
                          <span className="px-1 py-0.2 rounded text-[9px] bg-rose-950 border border-rose-700 text-rose-300">
                            Conflict
                          </span>
                        )}
                      </div>
                      {entity.candidate_ids.length > 1 && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onUnlinkCandidate?.(cand.candidate_id);
                          }}
                          className="text-slate-400 hover:text-rose-400 p-0.5"
                          title="Unlink occurrence from this entity cluster"
                        >
                          <Unlink className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Inline Bulk Confirmation Banner for Ambiguous Clusters */}
            {pendingConfirm && (
              <div
                data-testid="bulk-entity-confirm-banner"
                className="p-2 rounded bg-amber-950/70 border border-amber-700 text-amber-200 flex items-center justify-between gap-2 text-[11px]"
              >
                <span>
                  Confirm bulk <strong>{pendingConfirm}</strong> across {entity.candidate_ids.length} ambiguous occurrence(s)?
                </span>
                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    type="button"
                    onClick={() => handleBulkTrigger(entity, pendingConfirm)}
                    className="px-2 py-0.5 rounded bg-amber-600 hover:bg-amber-500 text-white font-semibold text-[10px]"
                  >
                    Confirm {pendingConfirm === 'APPROVE' ? 'Approve' : 'Reject'}
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setConfirmActionByEntity((prev) => {
                        const next = { ...prev };
                        delete next[entity.entity_id];
                        return next;
                      })
                    }
                    className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px]"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* Group Decision Controls */}
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800/60">
              <button
                onClick={() => handleBulkTrigger(entity, 'APPROVE')}
                className="flex items-center gap-1 px-2.5 py-1 rounded bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-700 text-emerald-300 text-xs font-medium"
                title="Approve all occurrences in this group"
              >
                <CheckCheck className="w-3.5 h-3.5" />
                <span>Approve All</span>
              </button>
              <button
                onClick={() => handleBulkTrigger(entity, 'REJECT')}
                className="flex items-center gap-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-400 hover:text-slate-200 text-xs"
                title="Reject all occurrences in this group"
              >
                <XCircle className="w-3.5 h-3.5" />
                <span>Reject All</span>
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
