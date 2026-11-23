import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  FileText,
  FileCode,
  Shield,
  CheckCircle2,
  XCircle,
  Clock,
  ArrowRight,
  RotateCcw,
  Scissors,
  Download,
  FileCheck,
  AlertTriangle,
  ArrowLeft,
  Trash2,
  Maximize2,
} from 'lucide-react';
import TextViewer from '../components/DocumentViewer/TextViewer';
import PdfViewer from '../components/DocumentViewer/PdfViewer';
import CandidateSidebar from '../components/CandidateList/CandidateSidebar';
import ManualRedactionModal from '../components/Modals/ManualRedactionModal';
import RedactSimilarModal from '../components/Modals/RedactSimilarModal';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import {
  getDocumentMetadata,
  getDocumentCoordinates,
  getCandidates,
  getEntities,
  getReviewSummary,
  submitReviewDecision,
  addManualCandidate,
  linkEntities,
  deleteDocumentSession,
} from '../services/api';

export default function ReviewWorkspace() {
  const { documentId } = useParams();
  const navigate = useNavigate();

  // State
  const [document, setDocument] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [entities, setEntities] = useState([]);
  const [coordinates, setCoordinates] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // View mode for PDFs ('text' or 'pdf') & current page
  const [viewMode, setViewMode] = useState('text');
  const [currentPage, setCurrentPage] = useState(1);

  // Selected candidate and text selection
  const [selectedCandidateId, setSelectedCandidateId] = useState(null);
  const [textSelection, setTextSelection] = useState(null);

  // Modals
  const [isManualModalOpen, setIsManualModalOpen] = useState(false);
  const [similarTargetCandidate, setSimilarTargetCandidate] = useState(null);
  const [isSimilarSubmitting, setIsSimilarSubmitting] = useState(false);

  // Load document and candidates
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [docMeta, candsData, entitiesData, summaryData] = await Promise.all([
        getDocumentMetadata(documentId),
        getCandidates(documentId),
        getEntities(documentId).catch(() => ({ entities: [] })),
        getReviewSummary(documentId).catch(() => null),
      ]);

      setDocument(docMeta);
      setCandidates(candsData || []);
      setEntities(entitiesData?.entities || []);
      setSummary(summaryData);

      if (docMeta?.file_type === 'pdf') {
        try {
          const coordsRes = await getDocumentCoordinates(documentId);
          setCoordinates(coordsRes?.coordinates || []);
        } catch {
          setCoordinates([]);
        }
      }

      // Default selected candidate to first pending if none selected
      if (candsData && candsData.length > 0) {
        setSelectedCandidateId((prev) => {
          if (prev) return prev;
          const firstPending = candsData.find((c) => c.review_status === 'PENDING') || candsData[0];
          return firstPending?.candidate_id || null;
        });
      }
    } catch (err) {
      console.error('Error loading review workspace:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to load document session.');
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Selected Candidate object
  const selectedCandidate = useMemo(() => {
    return candidates.find((c) => c.candidate_id === selectedCandidateId) || null;
  }, [candidates, selectedCandidateId]);

  // Sync PDF page when selected candidate has a page_number
  useEffect(() => {
    if (selectedCandidate?.page_number && selectedCandidate.page_number >= 1) {
      setCurrentPage(selectedCandidate.page_number);
    }
  }, [selectedCandidate]);

  // Handle Review Decisions (Approve, Reject, Pending/Undo)
  const handleReviewAction = useCallback(
    async (candidateId, decision, extra = {}) => {
      try {
        const res = await submitReviewDecision(documentId, {
          candidateId,
          decision,
          newType: extra.newType,
          applyToLinked: extra.applyToLinked,
          applyToSimilar: extra.applyToSimilar,
        });

        setCandidates(res.candidates);
        setSummary(res);

        // Update selected candidate if needed or advance to next pending
        if (decision !== 'PENDING') {
          const remainingPending = res.candidates.filter(
            (c) => c.review_status === 'PENDING' && c.candidate_id !== candidateId
          );
          if (remainingPending.length > 0) {
            setSelectedCandidateId(remainingPending[0].candidate_id);
          }
        }
      } catch (err) {
        console.error('Review action failed:', err);
        alert(err.response?.data?.detail || 'Failed to apply review decision.');
      }
    },
    [documentId]
  );

  // Keyboard Shortcuts: A = Approve, R = Reject, M = Manual
  const shortcutHandlers = useMemo(
    () => ({
      onApprove: () => {
        if (selectedCandidateId) {
          handleReviewAction(selectedCandidateId, 'APPROVE');
        }
      },
      onReject: () => {
        if (selectedCandidateId) {
          handleReviewAction(selectedCandidateId, 'REJECT');
        }
      },
      onManualRedact: () => {
        if (textSelection) {
          setIsManualModalOpen(true);
        }
      },
    }),
    [selectedCandidateId, textSelection, handleReviewAction]
  );

  useKeyboardShortcuts(shortcutHandlers);

  // Manual Candidate Creation
  const handleManualSubmit = async ({ start, end, type, pageNumber, bbox }) => {
    try {
      const newCand = await addManualCandidate(documentId, {
        start,
        end,
        type,
        pageNumber,
        bbox,
      });

      // Reload full state to sync entities and summary
      await loadData();
      setSelectedCandidateId(newCand.candidate_id);
      setTextSelection(null);
    } catch (err) {
      console.error('Failed to create manual candidate:', err);
      alert(err.response?.data?.detail || 'Failed to create manual redaction.');
    }
  };

  // Bulk: Redact all similar
  const handleRedactSimilarConfirm = async () => {
    if (!similarTargetCandidate) return;
    try {
      setIsSimilarSubmitting(true);
      await handleReviewAction(similarTargetCandidate.candidate_id, 'APPROVE', {
        applyToSimilar: true,
      });
      setSimilarTargetCandidate(null);
    } finally {
      setIsSimilarSubmitting(false);
    }
  };

  // Unlink Candidate from Entity Group
  const handleUnlinkCandidate = async (candidateId) => {
    try {
      await linkEntities(documentId, {
        candidateIds: [candidateId],
        action: 'UNLINK',
      });
      await loadData();
    } catch (err) {
      console.error('Unlink failed:', err);
      alert(err.response?.data?.detail || 'Failed to unlink candidate.');
    }
  };

  // Purge Session
  const handleDeleteSession = async () => {
    if (window.confirm('Are you sure you want to delete this session? All local artifacts will be purged.')) {
      try {
        await deleteDocumentSession(documentId);
        navigate('/');
      } catch (err) {
        console.error('Delete failed:', err);
        alert(err.response?.data?.detail || 'Failed to delete session.');
      }
    }
  };

  // Compute matching candidates for "redact all similar" modal
  const similarCandidates = useMemo(() => {
    if (!similarTargetCandidate) return [];
    const norm = similarTargetCandidate.text.trim().toLowerCase();
    return candidates.filter((c) => c.text.trim().toLowerCase() === norm);
  }, [similarTargetCandidate, candidates]);

  // Loading state
  if (loading) {
    return (
      <div className="min-h-[80vh] flex flex-col items-center justify-center p-8 space-y-4">
        <div className="w-10 h-10 border-2 border-sky-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-medium text-slate-400">Loading document review workspace...</p>
      </div>
    );
  }

  // Error state
  if (error || !document) {
    return (
      <div className="max-w-2xl mx-auto my-12 p-6 rounded-xl bg-slate-900 border border-slate-800 text-center space-y-4">
        <AlertTriangle className="w-12 h-12 text-amber-400 mx-auto" />
        <h2 className="text-xl font-bold text-white">Review Workspace Unavailable</h2>
        <p className="text-sm text-slate-400">{error || 'Session not found or expired.'}</p>
        <button
          onClick={() => navigate('/')}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Return to Dashboard</span>
        </button>
      </div>
    );
  }

  const approvedCount = summary?.approved_count ?? candidates.filter((c) => c.review_status === 'APPROVED').length;
  const rejectedCount = summary?.rejected_count ?? candidates.filter((c) => c.review_status === 'REJECTED').length;
  const pendingCount = summary?.pending_count ?? candidates.filter((c) => c.review_status === 'PENDING').length;
  const totalCount = candidates.length;

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] overflow-hidden bg-slate-950">
      {/* Top Workspace Header */}
      <div className="h-14 border-b border-slate-800 bg-slate-900/90 px-4 sm:px-6 flex items-center justify-between shrink-0">
        {/* Left: Document info & Back */}
        <div className="flex items-center gap-3">
          <Link
            to="/"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
            title="Back to Dashboard"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded bg-slate-800 text-sky-400">
              {document.file_type === 'pdf' ? <FileCode className="w-4 h-4" /> : <FileText className="w-4 h-4" />}
            </span>
            <div>
              <h1 className="text-xs sm:text-sm font-bold text-white truncate max-w-[200px] sm:max-w-xs">
                {document.filename}
              </h1>
              <span className="text-[10px] text-slate-400 font-mono">
                {document.file_type.toUpperCase()} • {document.text_length} chars • {document.page_count} page(s)
              </span>
            </div>
          </div>
        </div>

        {/* Center: Review Summary Stats & Shortcuts Badge */}
        <div className="hidden lg:flex items-center gap-4 text-xs">
          <div className="flex items-center gap-3 px-3 py-1 rounded-lg bg-slate-950 border border-slate-800">
            <div className="flex items-center gap-1.5 text-slate-300">
              <span className="font-semibold text-white">{totalCount}</span>
              <span className="text-slate-500">Detected</span>
            </div>
            <span className="text-slate-700">|</span>
            <div className="flex items-center gap-1.5 text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span className="font-semibold">{approvedCount}</span>
              <span className="text-slate-500">Approved</span>
            </div>
            <span className="text-slate-700">|</span>
            <div className="flex items-center gap-1.5 text-slate-400">
              <XCircle className="w-3.5 h-3.5" />
              <span className="font-semibold">{rejectedCount}</span>
              <span className="text-slate-500">Rejected</span>
            </div>
            <span className="text-slate-700">|</span>
            <div className="flex items-center gap-1.5 text-amber-400">
              <Clock className="w-3.5 h-3.5" />
              <span className="font-semibold">{pendingCount}</span>
              <span className="text-slate-500">Pending</span>
            </div>
          </div>

          {/* Keyboard hints */}
          <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">A</span> Approve
            <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">R</span> Reject
            <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">M</span> Manual
          </div>
        </div>

        {/* Right: Mode Switcher & Export / Summary Actions */}
        <div className="flex items-center gap-2">
          {document.file_type === 'pdf' && (
            <div className="flex rounded-lg bg-slate-950 p-0.5 border border-slate-800 text-xs">
              <button
                onClick={() => setViewMode('text')}
                className={`px-2.5 py-1 rounded-md transition ${
                  viewMode === 'text' ? 'bg-sky-600 text-white font-semibold' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Canonical Text
              </button>
              <button
                onClick={() => setViewMode('pdf')}
                className={`px-2.5 py-1 rounded-md transition ${
                  viewMode === 'pdf' ? 'bg-sky-600 text-white font-semibold' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                PDF View
              </button>
            </div>
          )}

          <Link
            to={`/summary/${documentId}`}
            className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition"
          >
            <FileCheck className="w-3.5 h-3.5 text-sky-400" />
            <span>Summary</span>
          </Link>

          <Link
            to={`/export/${documentId}`}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-lg shadow-sky-600/20 transition"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export</span>
          </Link>

          <button
            onClick={handleDeleteSession}
            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition"
            title="Purge Document Session"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Review Grid */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 overflow-hidden">
        {/* Left Column: Document Viewer (Text or PDF) */}
        <div className="lg:col-span-8 flex flex-col h-full overflow-hidden border-r border-slate-800 bg-slate-900/40">
          {viewMode === 'text' || document.file_type === 'txt' ? (
            <TextViewer
              text={document.extracted_text}
              candidates={candidates}
              selectedCandidateId={selectedCandidateId}
              onSelectCandidate={(id) => setSelectedCandidateId(id)}
              onTextSelected={(sel) => setTextSelection(sel)}
            />
          ) : (
            <PdfViewer
              documentId={documentId}
              pageCount={document.page_count}
              currentPage={currentPage}
              onPageChange={setCurrentPage}
              coordinates={coordinates}
              candidates={candidates}
              selectedCandidateId={selectedCandidateId}
              onSelectCandidate={(id) => setSelectedCandidateId(id)}
            />
          )}

          {/* Bottom Bar: Manual selection trigger */}
          {textSelection && (
            <div className="p-2.5 bg-slate-900 border-t border-slate-800 flex items-center justify-between text-xs animate-fadeIn shrink-0">
              <div className="flex items-center gap-2">
                <span className="p-1 rounded bg-sky-950 text-sky-400">
                  <Scissors className="w-3.5 h-3.5" />
                </span>
                <span className="text-slate-300">
                  Selected span: <span className="font-mono text-white">"{textSelection.text}"</span>{' '}
                  <span className="text-slate-500 font-mono">[{textSelection.start}, {textSelection.end})</span>
                </span>
              </div>
              <button
                onClick={() => setIsManualModalOpen(true)}
                className="px-3 py-1 rounded-md bg-sky-600 hover:bg-sky-500 text-white font-medium text-xs shadow transition"
              >
                Mark for Redaction (M)
              </button>
            </div>
          )}
        </div>

        {/* Right Column: Candidate Sidebar (Cards & Entities) */}
        <div className="lg:col-span-4 flex flex-col h-full overflow-hidden bg-slate-900/70">
          <CandidateSidebar
            candidates={candidates}
            entities={entities}
            summary={summary}
            selectedCandidateId={selectedCandidateId}
            onSelectCandidate={(id) => setSelectedCandidateId(id)}
            onApprove={(id) => handleReviewAction(id, 'APPROVE')}
            onReject={(id) => handleReviewAction(id, 'REJECT')}
            onUndo={(id) => handleReviewAction(id, 'PENDING')}
            onChangeCategory={(id, newType) => handleReviewAction(id, 'APPROVE', { newType })}
            onApproveLinked={(id) => handleReviewAction(id, 'APPROVE', { applyToLinked: true })}
            onRedactSimilar={(idOrCand) => {
              const target =
                typeof idOrCand === 'object' && idOrCand !== null
                  ? idOrCand
                  : candidates.find((c) => c.candidate_id === idOrCand);
              if (target) setSimilarTargetCandidate(target);
            }}
            onApproveEntity={(entityIdOrCandIds) => {
              if (Array.isArray(entityIdOrCandIds) && entityIdOrCandIds.length > 0) {
                handleReviewAction(entityIdOrCandIds[0], 'APPROVE', { applyToLinked: true });
                return;
              }
              const entity = entities.find((e) => e.entity_id === entityIdOrCandIds);
              if (entity && entity.candidate_ids.length > 0) {
                handleReviewAction(entity.candidate_ids[0], 'APPROVE', { applyToLinked: true });
              }
            }}
            onRejectEntity={(entityIdOrCandIds) => {
              if (Array.isArray(entityIdOrCandIds) && entityIdOrCandIds.length > 0) {
                handleReviewAction(entityIdOrCandIds[0], 'REJECT', { applyToLinked: true });
                return;
              }
              const entity = entities.find((e) => e.entity_id === entityIdOrCandIds);
              if (entity && entity.candidate_ids.length > 0) {
                handleReviewAction(entity.candidate_ids[0], 'REJECT', { applyToLinked: true });
              }
            }}
            onUnlinkCandidate={handleUnlinkCandidate}
            onAddManual={() => {
              if (textSelection) {
                setIsManualModalOpen(true);
              } else {
                alert('Highlight a text snippet in the canonical text viewer first, then click Manual Redaction.');
              }
            }}
          />
        </div>
      </div>

      {/* Manual Redaction Modal */}
      <ManualRedactionModal
        isOpen={isManualModalOpen}
        onClose={() => setIsManualModalOpen(false)}
        onSubmit={handleManualSubmit}
        selection={textSelection}
      />

      {/* Redact All Similar Modal */}
      <RedactSimilarModal
        isOpen={Boolean(similarTargetCandidate)}
        onClose={() => setSimilarTargetCandidate(null)}
        onConfirm={handleRedactSimilarConfirm}
        targetCandidate={similarTargetCandidate}
        matchingCandidates={similarCandidates}
        isSubmitting={isSimilarSubmitting}
      />
    </div>
  );
}
