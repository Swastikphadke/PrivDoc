import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Download,
  FileText,
  FileCode,
  ShieldCheck,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  XCircle,
  Settings,
  Eye,
  Lock,
  RefreshCw,
  Info,
} from 'lucide-react';
import {
  getDocumentMetadata,
  getCandidates,
  getReviewSummary,
  redactDocument,
  reconstructPdf,
  getExportStatus,
  downloadExport,
} from '../services/api';

const PLACEHOLDER_OPTIONS = [
  { id: 'CATEGORY', label: '[CATEGORY]', desc: 'Preserves semantic type: [PERSON], [EMAIL]' },
  {
    id: 'ENTITY_INDEXED',
    label: '[CATEGORY_#]',
    desc: 'Coreference-preserving tokens: [PERSON_1], [PERSON_2], [EMAIL_1]',
  },
  { id: 'GENERIC', label: '[REDACTED]', desc: 'Standard uniform privacy mask' },
  { id: 'BLOCK', label: '████████', desc: 'Visual Unicode block characters' },
];

export default function ExportView() {
  const { documentId } = useParams();
  const navigate = useNavigate();

  const [document, setDocument] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Redaction configuration
  const [exportFormat, setExportFormat] = useState('txt');
  const [placeholderType, setPlaceholderType] = useState('CATEGORY');
  const [useReconstructionFallback, setUseReconstructionFallback] = useState(false);

  // Redaction execution & verification state
  const [isProcessing, setIsProcessing] = useState(false);
  const [redactionResult, setRedactionResult] = useState(null);
  const [redactionError, setRedactionError] = useState(null);
  const [isDownloading, setIsDownloading] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setError(null);
        setRedactionError(null);
        setDocument(null);
        setCandidates([]);
        setSummary(null);
        setRedactionResult(null);
        const [docMeta, cands, sum] = await Promise.all([
          getDocumentMetadata(documentId),
          getCandidates(documentId),
          getReviewSummary(documentId).catch(() => null),
        ]);
        setDocument(docMeta);
        setCandidates(cands || []);
        setSummary(sum);
        setExportFormat(docMeta.file_type === 'pdf' ? 'pdf' : 'txt');

        // Check if an export was already generated
        try {
          const existingExport = await getExportStatus(documentId);
          if (existingExport) {
            setRedactionResult(existingExport);
          }
        } catch {
          // No export yet
        }
      } catch (err) {
        console.error('Failed to load export data:', err);
        setError(err.response?.data?.detail || err.message || 'Session not found');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [documentId]);

  const handleExecuteRedaction = async () => {
    setIsProcessing(true);
    setRedactionError(null);
    try {
      const res = await redactDocument(documentId, {
        placeholderStyle: placeholderType,
        forceTextReconstruction: useReconstructionFallback,
      });
      setRedactionResult(res);
    } catch (err) {
      console.error('Redaction failed:', err);
      setRedactionError(err.response?.data?.detail || err.message || 'Redaction execution failed.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleExecuteReconstruction = async () => {
    setIsProcessing(true);
    setRedactionError(null);
    try {
      const res = await reconstructPdf(documentId, {
        placeholderStyle: placeholderType,
      });
      setRedactionResult(res);
    } catch (err) {
      console.error('Clean-text PDF reconstruction failed:', err);
      setRedactionError(err.response?.data?.detail || err.message || 'Clean-text reconstruction failed.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDownload = async () => {
    if (!redactionResult || redactionResult.export_state !== 'VERIFIED') return;
    setIsDownloading(true);
    try {
      const targetFmt = exportFormat || document.file_type;
      const res =
        targetFmt !== document.file_type
          ? await downloadExport(documentId, targetFmt)
          : await downloadExport(documentId);
      const blob = new Blob([res.data], {
        type: targetFmt === 'pdf' ? 'application/pdf' : 'text/plain;charset=utf-8',
      });
      const url = window.URL.createObjectURL(blob);
      const link = window.document.createElement('a');
      link.href = url;
      const baseFilename = redactionResult.export_filename || `sanitized_${document.filename}`;
      const downloadFilename =
        targetFmt === 'txt' && baseFilename.endsWith('.pdf')
          ? baseFilename.replace(/\.pdf$/i, '.txt')
          : baseFilename;
      link.setAttribute('download', downloadFilename);
      window.document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download failed:', err);
      alert(err.response?.data?.detail || err.message || 'Download failed.');
    } finally {
      setIsDownloading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-[80vh] flex flex-col items-center justify-center p-8 space-y-4">
        <div className="w-10 h-10 border-2 border-sky-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-medium text-slate-400">Loading export configuration...</p>
      </div>
    );
  }

  if (error || !document) {
    return (
      <div className="max-w-xl mx-auto my-12 p-6 rounded-xl bg-slate-900 border border-slate-800 text-center space-y-4">
        <AlertTriangle className="w-12 h-12 text-amber-400 mx-auto" />
        <h2 className="text-xl font-bold text-white">Export Session Unavailable</h2>
        <p className="text-sm text-slate-400">{error || 'Session not found.'}</p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-600 text-white text-xs font-semibold"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Return to Dashboard</span>
        </Link>
      </div>
    );
  }

  const approvedCandidates = candidates.filter((c) => c.review_status === 'APPROVED');
  const pendingCandidates = candidates.filter((c) => c.review_status === 'PENDING');
  const rejectedCandidates = candidates.filter((c) => c.review_status === 'REJECTED');

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      {/* Navigation Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            to={`/review/${documentId}`}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
              <Download className="w-5 h-5 text-sky-400" />
              Document Redaction & Export
            </h1>
            <p className="text-xs text-slate-400 font-mono mt-0.5">
              {document.filename} • {document.file_type.toUpperCase()} • Session ID: {documentId}
            </p>
          </div>
        </div>

        <Link
          to={`/summary/${documentId}`}
          className="text-xs font-semibold text-sky-400 hover:text-sky-300 flex items-center gap-1"
        >
          View Safe Summary &rarr;
        </Link>
      </div>

      {/* Review Gatekeeper Status Card */}
      <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
            Review Gatekeeper Verification
          </span>
          {pendingCandidates.length > 0 ? (
            <span className="px-2 py-0.5 rounded bg-amber-950 border border-amber-800 text-amber-300 text-xs font-semibold flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5" />
              {pendingCandidates.length} Pending Candidates
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded bg-emerald-950 border border-emerald-800 text-emerald-300 text-xs font-semibold flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              All Candidates Reviewed
            </span>
          )}
        </div>

        <div className="grid grid-cols-3 gap-4 pt-2 border-t border-slate-800/80 text-center">
          <div className="p-3 rounded-lg bg-slate-950 border border-slate-800/60">
            <span className="block text-2xl font-bold text-emerald-400 font-mono">
              {approvedCandidates.length}
            </span>
            <span className="text-[11px] text-slate-400">Approved for Redaction</span>
          </div>
          <div className="p-3 rounded-lg bg-slate-950 border border-slate-800/60">
            <span className="block text-2xl font-bold text-slate-300 font-mono">
              {rejectedCandidates.length}
            </span>
            <span className="text-[11px] text-slate-400">Rejected (Preserved)</span>
          </div>
          <div className="p-3 rounded-lg bg-slate-950 border border-slate-800/60">
            <span className="block text-2xl font-bold text-amber-400 font-mono">
              {pendingCandidates.length}
            </span>
            <span className="text-[11px] text-slate-400">Pending Review</span>
          </div>
        </div>

        {pendingCandidates.length > 0 && (
          <p className="text-xs text-amber-300/90 bg-amber-950/40 p-2.5 rounded border border-amber-900/60">
            Warning: You have unreviewed candidates. Pending candidates will NOT be redacted. Return to review
            workspace if you wish to inspect them.
          </p>
        )}
      </div>

      {/* Export Configuration Form */}
      <div className="p-6 rounded-xl bg-slate-900 border border-slate-800 space-y-6">
        <h2 className="text-sm font-bold text-white flex items-center gap-2">
          <Settings className="w-4 h-4 text-sky-400" />
          Redaction Configuration
        </h2>

        {/* Format Selector */}
        <div className="space-y-2">
          <label className="block text-xs font-semibold text-slate-300">Target Export Format</label>
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => setExportFormat('txt')}
              className={`p-3 rounded-lg border text-left transition flex items-center justify-between ${
                exportFormat === 'txt'
                  ? 'bg-sky-950/50 border-sky-600 text-white'
                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <FileText className="w-4 h-4 text-sky-400" />
                <div>
                  <span className="block text-xs font-semibold">Plain Text (.txt)</span>
                  <span className="text-[11px] text-slate-500">Universal sanitized text document</span>
                </div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => setExportFormat('pdf')}
              disabled={document.file_type !== 'pdf'}
              className={`p-3 rounded-lg border text-left transition flex items-center justify-between ${
                exportFormat === 'pdf'
                  ? 'bg-sky-950/50 border-sky-600 text-white'
                  : document.file_type !== 'pdf'
                  ? 'bg-slate-950/40 border-slate-900 text-slate-600 cursor-not-allowed'
                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <FileCode className="w-4 h-4 text-sky-400" />
                <div>
                  <span className="block text-xs font-semibold">Native PDF (.pdf)</span>
                  <span className="text-[11px] text-slate-500">
                    {document.file_type === 'pdf' ? 'PyMuPDF stream redaction' : 'Unavailable for TXT uploads'}
                  </span>
                </div>
              </div>
            </button>
          </div>
        </div>

        {/* Placeholder Mask Configuration */}
        <div className="space-y-2">
          <label className="block text-xs font-semibold text-slate-300">Redaction Mask Pattern</label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {PLACEHOLDER_OPTIONS.map((opt) => (
              <label
                key={opt.id}
                className={`p-3 rounded-lg border cursor-pointer transition flex items-start gap-2.5 ${
                  placeholderType === opt.id
                    ? 'bg-sky-950/40 border-sky-600 text-white'
                    : 'bg-slate-950 border-slate-800 text-slate-300 hover:bg-slate-800/40'
                }`}
              >
                <input
                  type="radio"
                  name="placeholder"
                  value={opt.id}
                  checked={placeholderType === opt.id}
                  onChange={(e) => setPlaceholderType(e.target.value)}
                  className="mt-0.5 text-sky-500 focus:ring-sky-500"
                />
                <div>
                  <span className="font-mono text-xs font-semibold text-white block">{opt.label}</span>
                  <span className="text-[11px] text-slate-400">{opt.desc}</span>
                </div>
              </label>
            ))}
          </div>
          <div
            data-testid="pseudonymization-disclosure-banner"
            className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-[11px] text-slate-400 flex items-start gap-2"
          >
            <Info className="w-3.5 h-3.5 text-sky-400 shrink-0 mt-0.5" />
            <span>
              <strong className="text-slate-300">Pseudonymization vs. Anonymization:</strong> Placeholder tokens (such as{' '}
              <code className="text-sky-300">[PERSON_1]</code> or <code className="text-sky-300">[PERSON]</code>) preserve
              document coreference and readability after removing direct identifiers, but pseudonymization is{' '}
              <strong className="text-slate-300">not guaranteed anonymization</strong>—contextual linkability and
              quasi-identifiers may still allow statistical inference.
            </span>
          </div>
        </div>

        {/* PDF Reconstruction Fallback Option */}
        {document.file_type === 'pdf' && (
          <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-300">Clean-Text PDF Reconstruction (DEC-004)</span>
              <input
                type="checkbox"
                checked={useReconstructionFallback}
                onChange={(e) => setUseReconstructionFallback(e.target.checked)}
                className="rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-sky-500"
              />
            </div>
            <p className="text-[11px] text-slate-400">
              When checked, rebuilds a brand new PDF purely from sanitized text. Use this if the original PDF contains
              unsupported vector objects, complex layers, or fails native stream verification.
            </p>
          </div>
        )}

        {/* Execution Button */}
        <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Independent post-export leak audit active</span>
          </div>

          <button
            onClick={handleExecuteRedaction}
            disabled={isProcessing}
            className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-lg shadow-sky-600/20 transition disabled:opacity-50"
          >
            {isProcessing ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Executing Redaction & Verification...</span>
              </>
            ) : (
              <>
                <ShieldCheck className="w-4 h-4" />
                <span>Execute Redaction & Verify Output</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Redaction Error Message */}
      {redactionError && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-900/60 text-rose-300 text-xs flex items-start gap-3">
          <XCircle className="w-5 h-5 flex-shrink-0 text-rose-400 mt-0.5" />
          <div>
            <span className="font-semibold block text-white">Redaction Execution Error</span>
            <span>{redactionError}</span>
          </div>
        </div>
      )}

      {/* Verification Audit Card & Download Section */}
      {redactionResult && (
        <div className="p-6 rounded-xl bg-slate-900 border border-slate-800 space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              Post-Export Verification Report
            </h2>

            <div className="flex items-center gap-2">
              {redactionResult.reconstructed_pdf_used && redactionResult.export_state === 'VERIFIED' && (
                <span className="px-2.5 py-1 rounded-md bg-cyan-950 border border-cyan-700 text-cyan-300 text-[11px] font-mono font-bold">
                  RECONSTRUCTED PDF
                </span>
              )}
              {redactionResult.export_state === 'VERIFIED' ? (
                <span className="px-3 py-1 rounded-full bg-emerald-950 border border-emerald-700 text-emerald-300 text-xs font-bold flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4" />
                  EXPORT VERIFIED SAFE
                </span>
              ) : (
                <span className="px-3 py-1 rounded-full bg-rose-950 border border-rose-700 text-rose-300 text-xs font-bold flex items-center gap-1.5">
                  <XCircle className="w-4 h-4" />
                  VERIFICATION FAILED (EXPORT BLOCKED)
                </span>
              )}
            </div>
          </div>

          {/* Verification Timestamp & Cryptographic Integrity Digest */}
          <div className="p-3 rounded-lg bg-slate-950 border border-slate-800/90 space-y-2 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-slate-400">
                Verified Timestamp:{' '}
                <code className="text-slate-200 font-mono">
                  {redactionResult.verification?.verified_at || 'Pending'}
                </code>
              </span>
              {redactionResult.export_sha256 && (
                <span className="text-slate-400">
                  SHA-256 Digest:{' '}
                  <code className="text-sky-300 font-mono">
                    {redactionResult.export_sha256.slice(0, 16)}...{redactionResult.export_sha256.slice(-8)}
                  </code>
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-500">
              Note: Cryptographic digest verifies post-export file byte integrity only; redaction correctness is established by the independent content-stream and metadata checks below.
            </p>
          </div>

          {/* Layout Loss Warning (if clean-text PDF used) */}
          {redactionResult.layout_warning && (
            <div className="p-3.5 rounded-lg bg-amber-950/40 border border-amber-900/60 text-amber-300 text-xs flex items-start gap-2.5">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 text-amber-400 mt-0.5" />
              <div>
                <span className="font-semibold block text-white">Layout Notice</span>
                <span>{redactionResult.layout_warning}</span>
              </div>
            </div>
          )}

          {/* Clean-Text PDF Reconstruction Offer Card (DEC-004 User-Triggered Fallback) */}
          {document.file_type === 'pdf' &&
            redactionResult.export_state === 'FAILED' &&
            !redactionResult.reconstructed_pdf_used && (
              <div className="p-5 rounded-xl bg-amber-950/30 border border-amber-800/80 space-y-3">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <h3 className="text-xs font-bold text-amber-200 uppercase tracking-wider">
                      Native PDF Verification Failed — Clean-Text Reconstruction Available
                    </h3>
                    <p className="text-xs text-amber-300/90 leading-relaxed">
                      Native PyMuPDF stream redaction could not be verified (extractable text, annotations, or unsupported structures remain).
                      To guarantee zero data leakage, export download is strictly blocked.
                    </p>
                    <p className="text-xs text-amber-400 font-medium">
                      DEC-004 Fallback: You can explicitly trigger <strong>Clean-Text PDF Reconstruction</strong> to generate a brand-new, clean PDF exclusively from verified sanitized text.
                    </p>
                  </div>
                </div>

                <div className="pt-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-t border-amber-900/60">
                  <span className="text-[11px] text-amber-400/80 italic">
                    * Note: Original graphical layout, images, and styling will be omitted.
                  </span>
                  <button
                    onClick={handleExecuteReconstruction}
                    disabled={isProcessing}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold text-xs shadow-md transition disabled:opacity-50"
                  >
                    {isProcessing ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Reconstructing & Verifying...</span>
                      </>
                    ) : (
                      <>
                        <FileCode className="w-3.5 h-3.5" />
                        <span>Reconstruct Clean-Text PDF Alternative</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}

          {/* Verification Checks Audit Grid */}
          <div className="space-y-2">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Verification Checks Performed
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {redactionResult.verification.checks_run.map((check) => (
                <div
                  key={check}
                  className="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80 flex items-center justify-between text-xs"
                >
                  <span className="font-mono text-slate-300">{check}</span>
                  <span className="text-[11px] text-emerald-400 font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Passed
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Issues List (if failed) */}
          {redactionResult.verification.issues.length > 0 && (
            <div className="p-4 rounded-lg bg-rose-950/30 border border-rose-900/50 space-y-2">
              <span className="text-xs font-bold text-rose-300 block">
                Verification Violations Detected ({redactionResult.verification.issues.length})
              </span>
              <ul className="space-y-1.5">
                {redactionResult.verification.issues.map((issue, idx) => (
                  <li key={idx} className="text-xs text-rose-200 flex items-start gap-2">
                    <XCircle className="w-3.5 h-3.5 text-rose-400 flex-shrink-0 mt-0.5" />
                    <span>
                      <strong className="font-mono text-rose-100">{issue.check_name}:</strong> {issue.description}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Sanitized Text Preview */}
          {redactionResult.sanitized_text_preview && (
            <div className="space-y-1.5">
              <span className="text-xs font-semibold text-slate-400">Sanitized Output Preview</span>
              <pre className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono text-slate-300 overflow-x-auto whitespace-pre-wrap">
                {redactionResult.sanitized_text_preview}
              </pre>
            </div>
          )}

          {/* Download Action Bar */}
          <div className="pt-4 border-t border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="text-xs text-slate-400">
              <span className="block font-medium text-slate-300">
                Applied Redactions: {redactionResult.approved_redactions_applied}
              </span>
              <span className="text-[11px] text-slate-500">
                Preserved: {redactionResult.rejected_spans_preserved} rejected, {redactionResult.unreviewed_spans_preserved} unreviewed
              </span>
            </div>

            <button
              onClick={handleDownload}
              disabled={!redactionResult.download_ready || isDownloading}
              className={`flex items-center gap-2 px-6 py-2.5 rounded-lg text-xs font-semibold transition ${
                redactionResult.download_ready
                  ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/20'
                  : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700/50'
              }`}
            >
              <Download className="w-4 h-4" />
              <span>
                {isDownloading
                  ? 'Preparing Download...'
                  : redactionResult.download_ready
                  ? `Download ${redactionResult.export_filename}`
                  : 'Download Blocked (Unverified)'}
              </span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
