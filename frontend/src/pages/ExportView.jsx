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
  Settings,
  Eye,
  Lock,
  RefreshCw,
  Sliders,
} from 'lucide-react';
import { getDocumentMetadata, getCandidates, getReviewSummary } from '../services/api';

const PLACEHOLDER_OPTIONS = [
  { id: 'REDACTED', label: '[REDACTED]', desc: 'Standard uniform privacy mask' },
  { id: 'CATEGORY', label: '[CATEGORY]', desc: 'Preserves semantic type: [PERSON], [EMAIL]' },
  { id: 'ENTITY_TAG', label: '[ENTITY_N]', desc: 'Consistent pseudonym: [PERSON_1], [PERSON_2]' },
  { id: 'BLACK_BOX', label: '████████', desc: 'Visual black bar / Unicode block characters' },
];

export default function ExportView() {
  const { documentId } = useParams();
  const navigate = useNavigate();

  const [document, setDocument] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Export settings
  const [exportFormat, setExportFormat] = useState('txt');
  const [placeholderType, setPlaceholderType] = useState('CATEGORY');
  const [useReconstructionFallback, setUseReconstructionFallback] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const [docMeta, cands, sum] = await Promise.all([
          getDocumentMetadata(documentId),
          getCandidates(documentId),
          getReviewSummary(documentId).catch(() => null),
        ]);
        setDocument(docMeta);
        setCandidates(cands || []);
        setSummary(sum);
        setExportFormat(docMeta.file_type === 'pdf' ? 'pdf' : 'txt');
      } catch (err) {
        console.error('Failed to load export data:', err);
        setError(err.response?.data?.detail || err.message || 'Session not found');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [documentId]);

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
          Export Configuration
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
                    {document.file_type === 'pdf' ? 'PyMuPDF vector redaction' : 'Unavailable for TXT uploads'}
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
        </div>

        {/* PDF Fallback Rule Option */}
        {exportFormat === 'pdf' && (
          <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-300">Clean-Text PDF Reconstruction</span>
              <input
                type="checkbox"
                checked={useReconstructionFallback}
                onChange={(e) => setUseReconstructionFallback(e.target.checked)}
                className="rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-sky-500"
              />
            </div>
            <p className="text-[11px] text-slate-400">
              Per architectural rule, if native PyMuPDF PDF redaction fails verification, export is blocked.
              Enabling this allows falling back to generating a fresh reconstructed PDF with layout warnings.
            </p>
          </div>
        )}

        {/* Verification & Download Action */}
        <div className="pt-4 border-t border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Cryptographic offset and leak checks active</span>
          </div>

          <button
            onClick={() => {
              alert(
                `Phase P4 Human Review Verified!\n\nExport configuration ready:\n- Format: ${exportFormat.toUpperCase()}\n- Redactions: ${approvedCandidates.length} approved spans\n- Mask: ${placeholderType}\n\nPhase P5 Redaction Engine will generate and verify the sanitized bytes.`
              );
            }}
            className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-lg shadow-sky-600/20 transition"
          >
            <Download className="w-4 h-4" />
            <span>Generate & Export Redacted File</span>
          </button>
        </div>
      </div>
    </div>
  );
}
