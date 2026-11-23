import React from 'react';
import { Users, Link2, Unlink, AlertTriangle, CheckCheck, XCircle } from 'lucide-react';
import { CATEGORY_THEMES } from '../../utils/theme';

export default function EntityGroupList({
  entities = [],
  candidates = [],
  onApproveEntity,
  onRejectEntity,
  onUnlinkCandidate,
}) {
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

  return (
    <div className="space-y-3 p-1">
      {entities.map((entity) => {
        const theme = CATEGORY_THEMES[entity.entity_type] || CATEGORY_THEMES.DEFAULT;
        const linkedCandidates = entity.candidate_ids.map((id) => candMap.get(id)).filter(Boolean);

        return (
          <div
            key={entity.entity_id}
            className="p-3.5 rounded-lg bg-slate-900/80 border border-slate-800 space-y-2.5 text-xs"
          >
            {/* Header: Canonical Name & Category */}
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-1.5">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${theme.badgeClass}`}>
                    {theme.label}
                  </span>
                  <span className="font-semibold text-slate-100 text-sm truncate max-w-[180px]">
                    {entity.canonical_name}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 mt-0.5">
                  {entity.candidate_ids.length} occurrence{entity.candidate_ids.length > 1 ? 's' : ''} •{' '}
                  <span className="font-mono text-cyan-400 font-medium">
                    {(entity.confidence * 100).toFixed(0)}% link confidence
                  </span>
                </div>
              </div>

              {/* Ambiguity Flag */}
              {entity.is_ambiguous && (
                <span
                  className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-950/80 border border-amber-800 text-amber-300 text-[10px]"
                  title="Ambiguous variants detected. Not merged automatically."
                >
                  <AlertTriangle className="w-3 h-3 text-amber-400" />
                  <span>Ambiguous</span>
                </span>
              )}
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

            {/* Evidence List */}
            {entity.evidence && entity.evidence.length > 0 && (
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
            )}

            {/* Occurrences list with Unlink option */}
            <div className="pt-2 border-t border-slate-800/60 space-y-1">
              <span className="text-slate-500 block text-[10px] uppercase tracking-wider font-semibold">
                Occurrences
              </span>
              <div className="space-y-1">
                {linkedCandidates.map((cand) => (
                  <div
                    key={cand.candidate_id}
                    className="flex items-center justify-between py-1 px-1.5 rounded bg-slate-950/60 border border-slate-800/40 text-[11px]"
                  >
                    <span className="font-mono text-slate-200 truncate max-w-[170px]">
                      {cand.text} <span className="text-slate-500">[{cand.start}, {cand.end})</span>
                    </span>
                    {entity.candidate_ids.length > 1 && (
                      <button
                        onClick={() => onUnlinkCandidate?.(cand.candidate_id)}
                        className="text-slate-400 hover:text-rose-400 p-0.5"
                        title="Unlink occurrence from this entity cluster"
                      >
                        <Unlink className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Group Decision Controls */}
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800/60">
              <button
                onClick={() => onApproveEntity?.(entity.candidate_ids)}
                className="flex items-center gap-1 px-2.5 py-1 rounded bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-700 text-emerald-300 text-xs font-medium"
                title="Approve all occurrences in this group"
              >
                <CheckCheck className="w-3.5 h-3.5" />
                <span>Approve All</span>
              </button>
              <button
                onClick={() => onRejectEntity?.(entity.candidate_ids)}
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
