import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  FileCheck,
  Shield,
  ShieldCheck,
  ShieldAlert,
  ArrowLeft,
  Sparkles,
  Download,
  AlertTriangle,
  RefreshCw,
  Cpu,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Clock,
  Layers,
  Info,
  Calendar,
  Search,
} from 'lucide-react';
import { getDocumentMetadata, getSummary, generateSummary } from '../services/api';

export default function SummaryView() {
  const { documentId } = useParams();

  const [document, setDocument] = useState(null);
  const [summaryData, setSummaryData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [maxLength, setMaxLength] = useState(300);
  const [forceExtractive, setForceExtractive] = useState(false);

  const fetchOrCreateSummary = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const docMeta = await getDocumentMetadata(documentId);
      setDocument(docMeta);

      // Check if summary already exists
      try {
        const existing = await getSummary(documentId);
        if (existing) {
          setSummaryData(existing);
          setLoading(false);
          return;
        }
      } catch (err) {
        // 404 means not generated yet; trigger generation
      }

      // Auto-trigger initial generation
      setGenerating(true);
      const generated = await generateSummary(documentId, {
        maxLength,
        forceExtractive,
      });
      setSummaryData(generated);
    } catch (err) {
      console.error('Failed to load summary:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to retrieve or generate summary.');
    } finally {
      setLoading(false);
      setGenerating(false);
    }
  }, [documentId, maxLength, forceExtractive]);

  useEffect(() => {
    fetchOrCreateSummary();
  }, [fetchOrCreateSummary]);

  const handleRegenerate = async (extractive = false) => {
    try {
      setGenerating(true);
      setError(null);
      const generated = await generateSummary(documentId, {
        maxLength,
        forceExtractive: extractive || forceExtractive,
      });
      setSummaryData(generated);
    } catch (err) {
      console.error('Regeneration failed:', err);
      setError(err.response?.data?.detail || err.message || 'Regeneration failed.');
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-[80vh] flex flex-col items-center justify-center p-8 space-y-4">
        <div className="w-10 h-10 border-2 border-sky-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-medium text-slate-400">Loading privacy-safe summary view...</p>
      </div>
    );
  }

  if (error && !summaryData) {
    return (
      <div className="max-w-2xl mx-auto my-12 p-6 rounded-xl bg-slate-900 border border-slate-800 text-center space-y-4">
        <AlertTriangle className="w-12 h-12 text-amber-400 mx-auto" />
        <h2 className="text-xl font-bold text-white">Summary Unavailable</h2>
        <p className="text-sm text-slate-400">{error}</p>
        <div className="flex items-center justify-center gap-3 pt-2">
          <Link
            to={`/review/${documentId}`}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Return to Review</span>
          </Link>
          <button
            onClick={() => handleRegenerate(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold transition"
          >
            <RefreshCw className="w-4 h-4" />
            <span>Generate Extractive Summary</span>
          </button>
        </div>
      </div>
    );
  }

  const state = summaryData?.state || 'PENDING';
  const isSuppressed = state === 'SUPPRESSED';
  const isVerified = state === 'VERIFIED';
  const isRequiresReview = state === 'REQUIRES_REVIEW';
  const engineUsed = summaryData?.engine_used || 'UNKNOWN';
  const structured = summaryData?.content;
  const verifReport = summaryData?.verification_report;
  const quasiAssessment = verifReport?.quasi_assessment;

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      {/* Navigation Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div className="flex items-center gap-3">
          <Link
            to={`/export/${documentId}`}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
            title="Back to Export"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-sky-400" />
              Privacy-Preserving Document Summary
            </h1>
            <p className="text-xs text-slate-400 font-mono mt-0.5">
              {document?.filename || documentId} • Strict Sanitized-Only Data Contract
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => handleRegenerate(false)}
            disabled={generating}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${generating ? 'animate-spin' : ''}`} />
            <span>Regenerate</span>
          </button>
          <Link
            to={`/export/${documentId}`}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow transition"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export Document</span>
          </Link>
        </div>
      </div>

      {/* Status & Engine Badges Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 rounded-xl bg-slate-900 border border-slate-800">
        <div className="flex items-center gap-3">
          {/* State Badge */}
          {isVerified && (
            <span
              data-testid="summary-state-badge"
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-950/80 text-emerald-400 border border-emerald-800/80"
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              VERIFIED
            </span>
          )}
          {isSuppressed && (
            <span
              data-testid="summary-state-badge"
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-rose-950/80 text-rose-400 border border-rose-800/80"
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              SUPPRESSED
            </span>
          )}
          {isRequiresReview && (
            <span
              data-testid="summary-state-badge"
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-950/80 text-amber-400 border border-amber-800/80"
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              REQUIRES REVIEW
            </span>
          )}
          {!isVerified && !isSuppressed && !isRequiresReview && (
            <span
              data-testid="summary-state-badge"
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700"
            >
              <Clock className="w-3.5 h-3.5" />
              {state}
            </span>
          )}

          {/* Engine Badge */}
          <span
            data-testid="summary-engine-badge"
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-slate-800/80 text-sky-400 border border-slate-700"
          >
            <Cpu className="w-3.5 h-3.5" />
            {engineUsed === 'SLM'
              ? 'Local SLM'
              : engineUsed === 'EXTRACTIVE_FALLBACK'
              ? 'Extractive Fallback (SLM Unavailable)'
              : engineUsed}
          </span>
        </div>

        {summaryData?.retry_count !== undefined && (
          <span className="text-xs text-slate-400 font-mono">
            Retries: {summaryData.retry_count}
          </span>
        )}
      </div>

      {/* Suppression Notice (Fail-Safe Block) */}
      {isSuppressed && (
        <div
          data-testid="suppression-banner"
          className="p-5 rounded-xl bg-rose-950/40 border border-rose-800/60 space-y-3"
        >
          <div className="flex items-center gap-2 text-rose-400 font-semibold text-sm">
            <ShieldAlert className="w-5 h-5 flex-shrink-0" />
            <span>Summary Suppressed: Privacy Verification Failed</span>
          </div>
          <p className="text-xs text-rose-300 leading-relaxed">
            The generated summary failed post-generation privacy verification checks and has been suppressed to prevent sensitive data leakage.
            No unverified text or residual PII is displayed.
          </p>
          {summaryData?.warning_message && (
            <div className="p-3 rounded-lg bg-slate-950 border border-rose-900/50 text-xs font-mono text-rose-300">
              Cause: {summaryData.warning_message}
            </div>
          )}
          <div className="pt-2">
            <button
              onClick={() => handleRegenerate(true)}
              disabled={generating}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-rose-700 hover:bg-rose-600 text-white text-xs font-semibold shadow transition"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry with Deterministic Extractive Fallback</span>
            </button>
          </div>
        </div>
      )}

      {/* Requires Review Warning Banner */}
      {isRequiresReview && summaryData?.warning_message && (
        <div
          data-testid="requires-review-warning-banner"
          className="p-4 rounded-xl bg-amber-950/40 border border-amber-800/60 flex items-start gap-2.5 text-xs text-amber-200"
        >
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold block text-amber-300">Human Review Advisory</span>
            <span>{summaryData.warning_message}</span>
          </div>
        </div>
      )}

      {/* Structured Summary Content (Rendered only when NOT suppressed) */}
      {!isSuppressed && structured && (
        <div data-testid="structured-summary-container" className="space-y-4">
          {/* Main Narrative Card */}
          <div className="p-6 rounded-xl bg-slate-900 border border-slate-800 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-sm font-bold text-white flex items-center gap-2">
                <FileCheck className="w-4 h-4 text-sky-400" />
                Sanitized Summary Narrative
              </h2>
              <span className="text-[11px] text-slate-400 font-mono">
                Preserves [CATEGORY] Placeholders
              </span>
            </div>
            <div
              data-testid="summary-narrative-text"
              className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-xs sm:text-sm leading-relaxed text-slate-200 font-sans"
            >
              {structured.summary_text}
            </div>
          </div>

          {/* Key Points & Important Findings */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Key Points */}
            <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
              <h3 className="text-xs font-semibold text-sky-400 uppercase tracking-wider flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5" />
                Key Points
              </h3>
              {structured.key_points && structured.key_points.length > 0 ? (
                <ul className="space-y-1.5 text-xs text-slate-300">
                  {structured.key_points.map((pt, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="text-sky-400 mt-0.5">•</span>
                      <span>{pt}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-500 italic">No specific bullet points extracted.</p>
              )}
            </div>

            {/* Important Findings */}
            <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
              <h3 className="text-xs font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Important Findings
              </h3>
              {structured.important_findings && structured.important_findings.length > 0 ? (
                <ul className="space-y-1.5 text-xs text-slate-300">
                  {structured.important_findings.map((finding, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="text-emerald-400 mt-0.5">•</span>
                      <span>{finding}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-500 italic">No specific findings listed.</p>
              )}
            </div>
          </div>

          {/* Dates & Figures and Source Evidence */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Dates & Figures */}
            <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
              <h3 className="text-xs font-semibold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5" />
                Relevant Dates & Figures
              </h3>
              {structured.relevant_dates_or_figures && structured.relevant_dates_or_figures.length > 0 ? (
                <ul className="space-y-1.5 text-xs text-slate-300">
                  {structured.relevant_dates_or_figures.map((item, i) => (
                    <li key={i} className="flex items-start gap-2 font-mono">
                      <span className="text-amber-400">•</span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-500 italic">No specific dates or figures recorded.</p>
              )}
            </div>

            {/* Source Evidence */}
            <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
              <h3 className="text-xs font-semibold text-purple-400 uppercase tracking-wider flex items-center gap-1.5">
                <Search className="w-3.5 h-3.5" />
                Source Evidence
              </h3>
              {structured.source_evidence && structured.source_evidence.length > 0 ? (
                <ul className="space-y-1.5 text-xs text-slate-300">
                  {structured.source_evidence.map((ev, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="text-purple-400 mt-0.5">•</span>
                      <span>{ev}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-500 italic">Summary grounded entirely in sanitized text context.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Verification Shield Audit Breakdown */}
      {verifReport && (
        <div data-testid="verification-shield-card" className="p-6 rounded-xl bg-slate-900 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <h2 className="text-sm font-bold text-white">Summary Privacy Verification Shield</h2>
            </div>
            <span
              className={`text-xs font-semibold px-2 py-0.5 rounded ${
                verifReport.status === 'PASSED'
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                  : verifReport.status === 'REQUIRES_REVIEW'
                  ? 'bg-amber-950 text-amber-400 border border-amber-800'
                  : 'bg-rose-950 text-rose-400 border border-rose-800'
              }`}
            >
              {verifReport.status === 'PASSED'
                ? 'ALL CHECKS PASSED'
                : verifReport.status === 'REQUIRES_REVIEW'
                ? 'REQUIRES REVIEW'
                : 'CHECKS FAILED'}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {verifReport.checks &&
              verifReport.checks.map((chk, idx) => {
                const checkPassed = chk.status === 'PASSED';
                const checkWarn = chk.status === 'WARNING';
                return (
                  <div
                    key={idx}
                    className={`p-3.5 rounded-lg border text-xs flex flex-col justify-between space-y-1 ${
                      checkPassed
                        ? 'bg-slate-950/60 border-slate-800 text-slate-300'
                        : checkWarn
                        ? 'bg-amber-950/30 border-amber-900/60 text-amber-300'
                        : 'bg-rose-950/30 border-rose-900/60 text-rose-300'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-white uppercase tracking-wider text-[11px]">
                        {chk.check_name.replace(/_/g, ' ')}
                      </span>
                      {checkPassed ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      ) : checkWarn ? (
                        <AlertTriangle className="w-4 h-4 text-amber-400" />
                      ) : (
                        <XCircle className="w-4 h-4 text-rose-400" />
                      )}
                    </div>
                    <p className="text-slate-400 text-[11px] leading-tight">
                      {chk.details || (checkPassed ? 'Check passed with 0 leaks.' : 'Failed.')}
                    </p>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* Quasi-Identifier Risk Assessment & Mandatory Disclaimer */}
      {quasiAssessment && (
        <div
          data-testid="quasi-risk-assessment-card"
          className="p-6 rounded-xl bg-slate-900 border border-slate-800 space-y-4"
        >
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <Info className="w-4 h-4 text-sky-400" />
              <h2 className="text-sm font-bold text-white">Quasi-Identifier Risk Assessment</h2>
            </div>
            <span
              className={`text-xs font-semibold px-2 py-0.5 rounded ${
                quasiAssessment.risk_level === 'LOW'
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                  : quasiAssessment.risk_level === 'MEDIUM'
                  ? 'bg-amber-950 text-amber-400 border border-amber-800'
                  : 'bg-rose-950 text-rose-400 border border-rose-800'
              }`}
            >
              Risk Level: {quasiAssessment.risk_level}
            </span>
          </div>

          {quasiAssessment.findings && quasiAssessment.findings.length > 0 ? (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold text-slate-300">Evaluated Co-Occurrence Findings:</h3>
              <ul className="space-y-1 text-xs text-slate-400">
                {quasiAssessment.findings.map((f, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-400 mt-0.5 flex-shrink-0" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-slate-400">
              No high-risk demographic, departmental, or role-based co-occurrence combinations detected.
            </p>
          )}

          {/* Mandatory Disclaimer Box */}
          <div
            data-testid="quasi-disclaimer"
            className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-[11px] text-slate-400 leading-relaxed space-y-1"
          >
            <span className="font-semibold text-slate-300 block">Notice on Re-Identification:</span>
            {quasiAssessment.disclaimer ||
              'Quasi-identifier risk evaluation assesses statistical re-identification risk flags based on demographic or contextual co-occurrences; it does not constitute mathematical or legal proof of complete anonymity.'}
          </div>
        </div>
      )}
    </div>
  );
}
