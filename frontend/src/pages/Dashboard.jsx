import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  Shield,
  CheckCircle,
  AlertTriangle,
  FileText,
  FileCode,
  Database,
  Server,
  RefreshCw,
  ArrowRight,
  Lock,
  Activity,
  Clock,
  ShieldCheck,
  ShieldAlert,
  Trash2,
  Layers,
  FolderOpen,
} from 'lucide-react';
import UploadDropzone from '../components/Upload/UploadDropzone';
import ProcessingView from '../components/Processing/ProcessingView';
import { useHealth } from '../hooks/useHealth';
import { CATEGORY_THEMES } from '../utils/theme';
import {
  uploadDocument,
  detectPii,
  resolveEntities,
  getDocumentsOverview,
  deleteDocumentSession,
} from '../services/api';

export default function Dashboard() {
  const navigate = useNavigate();
  const { health, loading: healthLoading, error: healthError, refetch } = useHealth(15000);

  // Real operational overview from backend SQLite + active sessions
  const [overview, setOverview] = useState(null);
  const [overviewLoading, setOverviewLoading] = useState(true);

  // Upload and processing state
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStage, setProcessingStage] = useState('ingesting');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [uploadError, setUploadError] = useState(null);
  const [degradedMode, setDegradedMode] = useState(false);

  const timerRef = useRef(null);

  const fetchOverview = useCallback(async () => {
    try {
      setOverviewLoading(true);
      const data = await getDocumentsOverview();
      if (data && typeof data === 'object') {
        setOverview(data);
      }
    } catch {
      // Gracefully handle when mocked or unavailable in isolated unit tests
      setOverview(null);
    } finally {
      setOverviewLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOverview();
  }, [fetchOverview]);

  useEffect(() => {
    if (isProcessing) {
      setElapsedSeconds(0);
      timerRef.current = setInterval(() => {
        setElapsedSeconds((prev) => prev + 0.1);
      }, 100);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isProcessing]);

  const handleFileUpload = async (file) => {
    try {
      setUploadError(null);
      setIsProcessing(true);
      setProcessingStage('ingesting');
      setDegradedMode(false);

      const doc = await uploadDocument(file);

      setProcessingStage('detecting');
      await detectPii(doc.document_id);

      setProcessingStage('resolving');
      const entitiesRes = await resolveEntities(doc.document_id).catch((err) => {
        console.warn('Entity resolution warning (using degraded mode):', err);
        setDegradedMode(true);
        return { degraded_mode: true };
      });

      if (entitiesRes?.degraded_mode) {
        setDegradedMode(true);
      }

      setProcessingStage('complete');

      setTimeout(() => {
        setIsProcessing(false);
        navigate(`/review/${doc.document_id}`);
      }, 450);
    } catch (err) {
      console.error('Processing failed:', err);
      setProcessingStage('error');
      setUploadError(
        err.response?.data?.detail || err.message || 'An error occurred during document ingestion.'
      );
      setIsProcessing(false);
    }
  };

  const handleCancel = () => {
    setIsProcessing(false);
    setProcessingStage('ingesting');
    setUploadError('Processing was cancelled by user.');
  };

  const handlePurgeSession = async (docId, filename) => {
    if (!window.confirm(`Purge session "${filename}" and delete all local artifacts?`)) return;
    try {
      await deleteDocumentSession(docId);
      await fetchOverview();
    } catch (err) {
      console.error('Failed to delete session:', err);
    }
  };

  const handleRefreshAll = () => {
    refetch();
    fetchOverview();
  };

  const categoryDist = overview?.category_distribution || {};
  const totalDetected = overview?.total_candidates_detected || 0;
  const recentDocs = overview?.recent_documents || [];

  return (
    <div className="max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Workstation Command Header */}
      <div className="p-5 rounded-lg bg-[#0c1322] border border-slate-800 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold uppercase tracking-wider bg-sky-950/90 border border-sky-800 text-sky-300">
              Release-Ready Platform Active (P0–P9)
            </span>
            <span className="flex items-center gap-1 text-[11px] font-mono text-emerald-400">
              <Lock className="w-3 h-3" /> 100% Local Processing Guarantee
            </span>
          </div>
          <h2 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
            PrivyDoc Document Security Workspace
          </h2>
          <p className="text-slate-400 text-xs sm:text-sm max-w-3xl">
            Deterministic document ingestion, confidence-aware hybrid PII detection, explainable entity clustering, and
            verifiable physical stream sanitization.
          </p>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <button
            onClick={handleRefreshAll}
            disabled={healthLoading}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-sky-400 ${healthLoading ? 'animate-spin' : ''}`} />
            <span>Health Check</span>
          </button>
        </div>
      </div>

      {/* Live Operational Telemetry Strip (Backed by Real Backend SQLite & Session Data) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5" data-testid="dashboard-metrics-grid">
        <div className="p-4 rounded-lg bg-[#0c1322] border border-slate-800 flex items-start justify-between">
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
              Documents Processed
            </span>
            <span className="text-2xl font-bold font-mono text-white mt-1 block">
              {overview ? overview.total_documents : '—'}
            </span>
            <span className="text-[11px] text-slate-500 mt-0.5 block">
              Active sessions in local SQLite
            </span>
          </div>
          <div className="p-2 rounded-md bg-slate-900 border border-slate-800 text-sky-400">
            <FileText className="w-4 h-4" />
          </div>
        </div>

        <div className="p-4 rounded-lg bg-[#0c1322] border border-slate-800 flex items-start justify-between">
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
              Awaiting Review
            </span>
            <span className="text-2xl font-bold font-mono text-amber-400 mt-1 block">
              {overview ? overview.awaiting_review_count : '—'}
            </span>
            <span className="text-[11px] text-slate-500 mt-0.5 block">
              Unverified or pending decisions
            </span>
          </div>
          <div className="p-2 rounded-md bg-amber-950/40 border border-amber-900/60 text-amber-400">
            <Clock className="w-4 h-4" />
          </div>
        </div>

        <div className="p-4 rounded-lg bg-[#0c1322] border border-slate-800 flex items-start justify-between">
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
              Verified Exports
            </span>
            <span className="text-2xl font-bold font-mono text-emerald-400 mt-1 block">
              {overview ? overview.verified_exports_count : '—'}
            </span>
            <span className="text-[11px] text-slate-500 mt-0.5 block">
              Passed post-redaction audit
            </span>
          </div>
          <div className="p-2 rounded-md bg-emerald-950/40 border border-emerald-900/60 text-emerald-400">
            <ShieldCheck className="w-4 h-4" />
          </div>
        </div>

        <div className="p-4 rounded-lg bg-[#0c1322] border border-slate-800 flex items-start justify-between">
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
              Suppressed Summaries
            </span>
            <span className="text-2xl font-bold font-mono text-rose-400 mt-1 block">
              {overview ? overview.suppressed_summaries_count : '—'}
            </span>
            <span className="text-[11px] text-slate-500 mt-0.5 block">
              Blocked by SummaryGuard
            </span>
          </div>
          <div className="p-2 rounded-md bg-rose-950/40 border border-rose-900/60 text-rose-400">
            <ShieldAlert className="w-4 h-4" />
          </div>
        </div>
      </div>

      {/* Main Two-Column Workstation Grid: Left = Upload & Pipeline, Right = PII Distribution & Runtime Status */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column (7 cols): Primary Document Ingestion & Pipeline Progression */}
        <div className="lg:col-span-7 space-y-4">
          <div className="p-5 rounded-lg bg-[#0c1322] border border-slate-800 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-sky-400" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
                  Document Ingestion & Analysis Launchpad
                </h3>
              </div>
              <span className="text-[11px] font-mono text-slate-400">Formats: .TXT, .PDF (Max 20MB)</span>
            </div>

            {isProcessing ? (
              <ProcessingView
                stage={processingStage}
                elapsedSeconds={elapsedSeconds}
                degradedMode={degradedMode}
                error={uploadError}
                onCancel={handleCancel}
              />
            ) : (
              <UploadDropzone
                onUpload={handleFileUpload}
                isUploading={isProcessing}
                error={uploadError}
              />
            )}

            {uploadError && !isProcessing && (
              <div className="p-3.5 rounded-md bg-rose-950/40 border border-rose-900/60 text-rose-300 text-xs flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <div>
                  <strong className="font-semibold block">Ingestion or Validation Error:</strong>
                  <p className="mt-0.5">{uploadError}</p>
                </div>
              </div>
            )}

            {/* 5-Stage Privacy Lifecycle Bar */}
            <div className="pt-3 border-t border-slate-800/80">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-2.5 flex items-center justify-between">
                <span>Document Privacy Lifecycle</span>
                <span className="font-mono text-slate-500">5-Stage Fail-Closed Pipeline</span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
                <div className="p-2 rounded bg-slate-950 border border-slate-800/80 flex items-center gap-2">
                  <span className="w-4 h-4 rounded bg-sky-950 border border-sky-800 text-sky-400 flex items-center justify-center text-[10px] font-mono font-bold shrink-0">
                    1
                  </span>
                  <div className="min-w-0">
                    <div className="font-semibold text-slate-200 text-[11px] truncate">Ingestion</div>
                    <div className="text-[10px] text-slate-500 truncate">TXT / PDF Offsets</div>
                  </div>
                </div>
                <div className="p-2 rounded bg-slate-950 border border-slate-800/80 flex items-center gap-2">
                  <span className="w-4 h-4 rounded bg-sky-950 border border-sky-800 text-sky-400 flex items-center justify-center text-[10px] font-mono font-bold shrink-0">
                    2
                  </span>
                  <div className="min-w-0">
                    <div className="font-semibold text-slate-200 text-[11px] truncate">Hybrid Detection</div>
                    <div className="text-[10px] text-slate-500 truncate">Regex + Context NER</div>
                  </div>
                </div>
                <div className="p-2 rounded bg-slate-950 border border-slate-800/80 flex items-center gap-2">
                  <span className="w-4 h-4 rounded bg-sky-950 border border-sky-800 text-sky-400 flex items-center justify-center text-[10px] font-mono font-bold shrink-0">
                    3
                  </span>
                  <div className="min-w-0">
                    <div className="font-semibold text-slate-200 text-[11px] truncate">Entity Linking</div>
                    <div className="text-[10px] text-slate-500 truncate">Variant Clusters</div>
                  </div>
                </div>
                <div className="p-2 rounded bg-slate-950 border border-slate-800/80 flex items-center gap-2">
                  <span className="w-4 h-4 rounded bg-sky-950 border border-sky-800 text-sky-400 flex items-center justify-center text-[10px] font-mono font-bold shrink-0">
                    4
                  </span>
                  <div className="min-w-0">
                    <div className="font-semibold text-slate-200 text-[11px] truncate">Human Review</div>
                    <div className="text-[10px] text-slate-500 truncate">Authoritative Gate</div>
                  </div>
                </div>
                <div className="p-2 rounded bg-slate-950 border border-slate-800/80 flex items-center gap-2 col-span-2 sm:col-span-1">
                  <span className="w-4 h-4 rounded bg-emerald-950 border border-emerald-800 text-emerald-400 flex items-center justify-center text-[10px] font-mono font-bold shrink-0">
                    5
                  </span>
                  <div className="min-w-0">
                    <div className="font-semibold text-emerald-300 text-[11px] truncate">Sanitization</div>
                    <div className="text-[10px] text-emerald-500/80 truncate">Redaction & Summary</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column (5 cols): Real PII Category Distribution & Local Subsystem Health */}
        <div className="lg:col-span-5 space-y-4">
          {/* PII Category Distribution Panel */}
          <div className="p-5 rounded-lg bg-[#0c1322] border border-slate-800 space-y-3.5" data-testid="category-distribution-card">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                <Layers className="w-3.5 h-3.5 text-sky-400" />
                Active Session PII Distribution
              </span>
              <span className="text-[11px] font-mono text-slate-400">
                {totalDetected} total span{totalDetected === 1 ? '' : 's'}
              </span>
            </div>

            {totalDetected > 0 ? (
              <div className="space-y-2.5 pt-1">
                {['PERSON', 'EMAIL', 'PHONE', 'ADDRESS', 'ID_LIKE'].map((cat) => {
                  const count = categoryDist[cat] || 0;
                  const pct = totalDetected > 0 ? Math.round((count / totalDetected) * 100) : 0;
                  const theme = CATEGORY_THEMES[cat] || CATEGORY_THEMES.DEFAULT;
                  return (
                    <div key={cat} className="space-y-1 text-xs">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${theme.dotColor}`} />
                          <span className="text-slate-300 font-medium">{theme.label}</span>
                          <span className="text-[10px] font-mono text-slate-500">[{cat}]</span>
                        </div>
                        <span className="font-mono text-slate-300">
                          {count} <span className="text-slate-500">({pct}%)</span>
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden border border-slate-800/60">
                        <div
                          className={`h-full ${theme.barColor} transition-all duration-300`}
                          style={{ width: `${Math.max(count > 0 ? 4 : 0, pct)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="py-6 text-center text-xs text-slate-500 space-y-1 bg-slate-950/60 rounded border border-slate-800/60">
                <Activity className="w-5 h-5 text-slate-600 mx-auto mb-1" />
                <p className="text-slate-400 font-medium">No candidate telemetry in active sessions</p>
                <p className="text-[11px] text-slate-500">
                  Category distribution populates automatically from detected spans in active sessions.
                </p>
              </div>
            )}
          </div>

          {/* Local Runtime & Subsystem Health Panel */}
          <div className="p-5 rounded-lg bg-[#0c1322] border border-slate-800 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                <Server className="w-3.5 h-3.5 text-emerald-400" />
                Local Subsystem Telemetry
              </span>
              <span className="text-[10px] font-mono text-slate-500">127.0.0.1:8000</span>
            </div>

            <div className="space-y-2 text-xs">
              <div className="p-2.5 rounded bg-slate-950 border border-slate-800/80 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Server className="w-3.5 h-3.5 text-sky-400" />
                  <span className="text-slate-300 font-medium">FastAPI Engine</span>
                </div>
                <div className="flex items-center gap-1.5 font-mono text-[11px]">
                  {healthLoading ? (
                    <span className="text-slate-400">Connecting...</span>
                  ) : healthError ? (
                    <span className="text-amber-400 flex items-center gap-1 font-semibold">
                      <AlertTriangle className="w-3.5 h-3.5" /> Disconnected
                    </span>
                  ) : (
                    <span className="text-emerald-400 flex items-center gap-1 font-semibold">
                      <CheckCircle className="w-3.5 h-3.5" /> Online ({health?.app_name} v{health?.version})
                    </span>
                  )}
                </div>
              </div>

              <div className="p-2.5 rounded bg-slate-950 border border-slate-800/80 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Database className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-slate-300 font-medium">SQLite Metadata</span>
                </div>
                <div className="flex items-center gap-1.5 font-mono text-[11px]">
                  {health?.database_connected ? (
                    <span className="text-emerald-400 flex items-center gap-1 font-semibold">
                      <CheckCircle className="w-3.5 h-3.5" /> Ready (data/privydoc.db)
                    </span>
                  ) : (
                    <span className="text-slate-400">Checking...</span>
                  )}
                </div>
              </div>

              <div className="p-2.5 rounded bg-slate-950 border border-slate-800/80 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Shield className="w-3.5 h-3.5 text-sky-400" />
                  <span className="text-slate-300 font-medium">Privacy Boundary</span>
                </div>
                <span className="text-emerald-400 font-mono text-[11px] font-semibold flex items-center gap-1">
                  <CheckCircle className="w-3.5 h-3.5" /> 100% Local-First Active
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Document Sessions Table */}
      <div className="p-5 rounded-lg bg-[#0c1322] border border-slate-800 space-y-4" data-testid="recent-documents-panel">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2">
            <FolderOpen className="w-4 h-4 text-sky-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Active & Recent Document Sessions
            </h3>
          </div>
          <span className="text-[11px] font-mono text-slate-400">
            {recentDocs.length} session{recentDocs.length === 1 ? '' : 's'}
          </span>
        </div>

        {recentDocs.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-[10px] uppercase tracking-wider text-slate-400 font-mono">
                  <th className="py-2.5 px-3">Document</th>
                  <th className="py-2.5 px-3">Format / Size</th>
                  <th className="py-2.5 px-3">Candidates & Entities</th>
                  <th className="py-2.5 px-3">Export Verification</th>
                  <th className="py-2.5 px-3">Summary Guard</th>
                  <th className="py-2.5 px-3 text-right">Workstation Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {recentDocs.map((doc) => {
                  const expState = doc.export_state || 'UNVERIFIED';
                  const sumState = doc.summary_state || 'NOT_RUN';
                  return (
                    <tr key={doc.document_id} className="hover:bg-slate-900/60 transition">
                      <td className="py-2.5 px-3">
                        <div className="flex items-center gap-2">
                          {doc.file_type === 'pdf' ? (
                            <FileCode className="w-4 h-4 text-sky-400 shrink-0" />
                          ) : (
                            <FileText className="w-4 h-4 text-slate-400 shrink-0" />
                          )}
                          <div>
                            <Link
                              to={`/review/${doc.document_id}`}
                              className="font-semibold text-slate-100 hover:text-sky-400 transition block truncate max-w-[220px]"
                            >
                              {doc.filename}
                            </Link>
                            <span className="text-[10px] font-mono text-slate-500">
                              ID: {doc.document_id.slice(0, 12)}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-[11px] text-slate-300">
                        <span className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-[10px] mr-1.5">
                          {doc.file_type.toUpperCase()}
                        </span>
                        {doc.text_length?.toLocaleString()} chars • {doc.page_count}p
                      </td>
                      <td className="py-2.5 px-3 font-mono text-[11px]">
                        <span className="text-emerald-400 font-semibold">{doc.approved_count}</span>
                        <span className="text-slate-500"> / {doc.candidate_count} approved</span>
                        {doc.pending_count > 0 && (
                          <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-950/70 border border-amber-800/80 text-amber-300 text-[10px]">
                            {doc.pending_count} pending
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-3">
                        {expState === 'VERIFIED' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-800 text-emerald-300 font-mono text-[10px] font-semibold">
                            <ShieldCheck className="w-3 h-3" /> VERIFIED
                          </span>
                        ) : expState === 'FAILED' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-950/80 border border-rose-800 text-rose-300 font-mono text-[10px] font-semibold">
                            <ShieldAlert className="w-3 h-3" /> FAILED
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400 font-mono text-[10px]">
                            UNVERIFIED
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-3">
                        {sumState === 'VERIFIED' ? (
                          <span className="px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-800 text-emerald-300 font-mono text-[10px] font-semibold">
                            VERIFIED
                          </span>
                        ) : sumState === 'SUPPRESSED' ? (
                          <span className="px-2 py-0.5 rounded bg-rose-950/80 border border-rose-800 text-rose-300 font-mono text-[10px] font-semibold">
                            SUPPRESSED
                          </span>
                        ) : sumState === 'REQUIRES_REVIEW' ? (
                          <span className="px-2 py-0.5 rounded bg-amber-950/80 border border-amber-800 text-amber-300 font-mono text-[10px] font-semibold">
                            REVIEW REQ
                          </span>
                        ) : (
                          <span className="text-slate-500 font-mono text-[10px]">—</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <div className="inline-flex items-center gap-1.5">
                          <Link
                            to={`/review/${doc.document_id}`}
                            className="px-2.5 py-1 rounded bg-sky-600/90 hover:bg-sky-500 text-white font-semibold text-[11px] transition flex items-center gap-1"
                          >
                            <span>Review</span>
                            <ArrowRight className="w-3 h-3" />
                          </Link>
                          <Link
                            to={`/export/${doc.document_id}`}
                            className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-[11px] transition"
                          >
                            Export
                          </Link>
                          <button
                            onClick={() => handlePurgeSession(doc.document_id, doc.filename)}
                            className="p-1 rounded bg-slate-900 hover:bg-rose-950/80 text-slate-400 hover:text-rose-300 border border-slate-800 transition"
                            title="Purge Session"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-8 text-center text-xs text-slate-400 bg-slate-950/50 rounded-md border border-slate-800/60 space-y-1">
            <FileText className="w-6 h-6 text-slate-600 mx-auto mb-1.5" />
            <p className="font-semibold text-slate-300">
              {overviewLoading ? 'Loading local session index...' : 'No active document sessions in local SQLite store'}
            </p>
            <p className="text-[11px] text-slate-500">
              Upload a <code className="text-slate-300">.txt</code> or text-based <code className="text-slate-300">.pdf</code> document above to launch the detection and review pipeline.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
