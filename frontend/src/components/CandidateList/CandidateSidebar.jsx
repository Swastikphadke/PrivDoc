import React, { useState, useMemo } from 'react';
import { Search, Filter, ShieldCheck, Layers, Users, CheckCircle2, Clock, XCircle } from 'lucide-react';
import CandidateCard from './CandidateCard';
import EntityGroupList from '../EntityGroups/EntityGroupList';

export default function CandidateSidebar({
  candidates = [],
  entities = [],
  selectedCandidateId = null,
  onSelectCandidate,
  onApprove,
  onApproveCandidate,
  onReject,
  onRejectCandidate,
  onUndo,
  onUndoCandidate,
  onChangeCategory,
  onRedactSimilar,
  onApproveLinked,
  onApproveEntity,
  onRejectEntity,
  onUnlinkCandidate,
  onAddManual,
}) {
  const handleApprove = onApproveCandidate || onApprove;
  const handleReject = onRejectCandidate || onReject;
  const handleUndo = onUndoCandidate || onUndo;

  const [activeTab, setActiveTab] = useState(() => {
    if (typeof window !== 'undefined' && window.location?.search?.includes('tab=entities')) {
      return 'entities';
    }
    return 'candidates';
  }); // 'candidates' | 'entities'
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');

  // Review statistics
  const stats = useMemo(() => {
    const total = candidates.length;
    const approved = candidates.filter((c) => c.review_status === 'APPROVED').length;
    const rejected = candidates.filter((c) => c.review_status === 'REJECTED').length;
    const pending = candidates.filter(
      (c) => c.review_status === 'PENDING' || c.review_status === 'NEEDS_REVIEW'
    ).length;
    return { total, approved, rejected, pending };
  }, [candidates]);

  // Filtered candidate list
  const filteredCandidates = useMemo(() => {
    return candidates.filter((cand) => {
      // Category filter
      if (categoryFilter !== 'ALL' && cand.type !== categoryFilter) {
        return false;
      }
      // Status filter
      if (statusFilter !== 'ALL' && cand.review_status !== statusFilter) {
        return false;
      }
      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return cand.text.toLowerCase().includes(q) || cand.type.toLowerCase().includes(q);
      }
      return true;
    });
  }, [candidates, categoryFilter, statusFilter, searchQuery]);

  // Map entity_id -> occurrence count
  const entityCounts = useMemo(() => {
    const map = new Map();
    for (const ent of entities) {
      map.set(ent.entity_id, ent.candidate_ids.length);
    }
    return map;
  }, [entities]);

  const categories = ['ALL', 'PERSON', 'EMAIL', 'PHONE', 'ADDRESS', 'ID_LIKE'];
  const statuses = ['ALL', 'PENDING', 'APPROVED', 'REJECTED'];

  return (
    <div className="flex flex-col h-full bg-slate-950 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
      {/* Top Review Stats Bar */}
      <div className="p-3 bg-slate-900 border-b border-slate-800 grid grid-cols-4 gap-2 text-center text-xs">
        <div className="p-1.5 rounded bg-slate-800/80 border border-slate-700/60">
          <div className="text-slate-400 text-[10px] uppercase font-semibold">Total</div>
          <div className="text-slate-100 font-mono font-bold text-sm">{stats.total}</div>
        </div>
        <div className="p-1.5 rounded bg-emerald-950/50 border border-emerald-800/60">
          <div className="text-emerald-400 text-[10px] uppercase font-semibold">Approved</div>
          <div className="text-emerald-300 font-mono font-bold text-sm">{stats.approved}</div>
        </div>
        <div className="p-1.5 rounded bg-slate-800/40 border border-slate-700/40">
          <div className="text-slate-400 text-[10px] uppercase font-semibold">Rejected</div>
          <div className="text-slate-400 font-mono font-bold text-sm">{stats.rejected}</div>
        </div>
        <div className="p-1.5 rounded bg-amber-950/40 border border-amber-800/60">
          <div className="text-amber-400 text-[10px] uppercase font-semibold">Pending</div>
          <div className="text-amber-300 font-mono font-bold text-sm">{stats.pending}</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-800 bg-slate-900/60 text-xs">
        <button
          onClick={() => setActiveTab('candidates')}
          className={`flex-1 py-2.5 font-medium border-b-2 transition flex items-center justify-center gap-1.5 ${
            activeTab === 'candidates'
              ? 'border-cyan-500 text-cyan-400 bg-slate-900'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Candidates ({candidates.length})</span>
        </button>
        <button
          onClick={() => setActiveTab('entities')}
          className={`flex-1 py-2.5 font-medium border-b-2 transition flex items-center justify-center gap-1.5 ${
            activeTab === 'entities'
              ? 'border-cyan-500 text-cyan-400 bg-slate-900'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Users className="w-3.5 h-3.5" />
          <span>Entities ({entities.length})</span>
        </button>
      </div>

      {/* Search & Filters (Candidate Tab only) */}
      {activeTab === 'candidates' && (
        <div className="p-3 border-b border-slate-800 space-y-2 bg-slate-900/40 text-xs">
          {/* Search box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search candidate text..."
              className="w-full bg-slate-900 border border-slate-700/80 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Category Filter Pills */}
          <div className="flex flex-wrap gap-1">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setCategoryFilter(cat)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium border transition ${
                  categoryFilter === cat
                    ? 'bg-cyan-950 border-cyan-700 text-cyan-300'
                    : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* Status Filter Pills */}
          <div className="flex gap-1 pt-1 border-t border-slate-800/60">
            {statuses.map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-2 py-0.5 rounded text-[10px] uppercase font-semibold transition ${
                  statusFilter === st
                    ? 'bg-slate-700 text-slate-100'
                    : 'bg-slate-900/80 text-slate-500 hover:text-slate-300'
                }`}
              >
                {st}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Content List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {activeTab === 'candidates' ? (
          filteredCandidates.length > 0 ? (
            filteredCandidates.map((cand) => (
              <CandidateCard
                key={cand.candidate_id}
                candidate={cand}
                isSelected={cand.candidate_id === selectedCandidateId}
                onSelect={onSelectCandidate}
                onApprove={handleApprove}
                onReject={handleReject}
                onUndo={handleUndo}
                onChangeCategory={onChangeCategory}
                onRedactSimilar={onRedactSimilar}
                onApproveLinked={onApproveLinked}
                linkedCount={cand.entity_id ? entityCounts.get(cand.entity_id) || 1 : 1}
              />
            ))
          ) : (
            <div className="p-8 text-center text-slate-500 text-xs">
              <p>No candidates match the selected filters.</p>
            </div>
          )
        ) : (
          <EntityGroupList
            entities={entities}
            candidates={candidates}
            selectedCandidateId={selectedCandidateId}
            onSelectCandidate={onSelectCandidate}
            onApproveEntity={onApproveEntity}
            onRejectEntity={onRejectEntity}
            onUnlinkCandidate={onUnlinkCandidate}
          />
        )}
      </div>
    </div>
  );
}
