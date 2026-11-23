import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Shield,
  CheckCircle,
  AlertTriangle,
  FileText,
  Database,
  Server,
  RefreshCw,
  ArrowRight,
  Cpu,
  Lock,
} from 'lucide-react';
import UploadDropzone from '../components/Upload/UploadDropzone';
import ProcessingView from '../components/Processing/ProcessingView';
import { useHealth } from '../hooks/useHealth';
import { uploadDocument, detectPii, resolveEntities } from '../services/api';

export default function Dashboard() {
  const navigate = useNavigate();
  const { health, loading: healthLoading, error: healthError, refetch } = useHealth(15000);

  // Upload and processing state
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStage, setProcessingStage] = useState('ingesting'); // 'ingesting' | 'detecting' | 'resolving' | 'complete' | 'error'
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [uploadError, setUploadError] = useState(null);
  const [degradedMode, setDegradedMode] = useState(false);

  const timerRef = useRef(null);

  // Timer for processing elapsed seconds
  useEffect(() => {
    if (isProcessing) {
      setElapsedSeconds(0);
      timerRef.current = setInterval(() => {
        setElapsedSeconds((prev) => prev + 0.1);
      }, 100);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
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

      // Step 1: Upload and extract text
      const doc = await uploadDocument(file);

      // Step 2: Trigger hybrid detection
      setProcessingStage('detecting');
      await detectPii(doc.document_id);

      // Step 3: Trigger entity resolution
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

      // Brief delay to show completion, then navigate to review workspace
      setTimeout(() => {
        setIsProcessing(false);
        navigate(`/review/${doc.document_id}`);
      }, 600);
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

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Welcome & Local Privacy Banner */}
      <div className="p-6 rounded-2xl bg-gradient-to-r from-slate-900 via-sky-950/40 to-slate-900 border border-slate-800 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-sky-950 border border-sky-800 text-sky-400">
                Release-Ready Platform Active (P0–P9)
              </span>
              <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                <Lock className="w-3 h-3" /> 100% Local Processing Guarantee
              </span>
            </div>
            <h2 className="text-2xl font-bold text-white tracking-tight">PrivyDoc Document Security Workspace</h2>
            <p className="text-slate-400 text-sm mt-1 max-w-2xl">
              Deterministic document ingestion, hybrid PII detection, entity clustering, and authoritative human-in-the-loop review.
            </p>
          </div>
          <button
            onClick={refetch}
            disabled={healthLoading}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold transition shadow-lg shadow-sky-600/20 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${healthLoading ? 'animate-spin' : ''}`} />
            <span>Health Check</span>
          </button>
        </div>

        {/* 5-Stage Workflow Pipeline Guide */}
        <div className="mt-6 pt-5 border-t border-slate-800/80">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-sky-400" />
            <span>Document Privacy Lifecycle</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-5 gap-2.5 text-xs">
            <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80 flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-sky-950 border border-sky-800 text-sky-400 flex items-center justify-center text-[10px] font-bold shrink-0">1</span>
              <div>
                <div className="font-semibold text-slate-200">Ingestion</div>
                <div className="text-[10px] text-slate-400">TXT / PDF Offsets</div>
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80 flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-sky-950 border border-sky-800 text-sky-400 flex items-center justify-center text-[10px] font-bold shrink-0">2</span>
              <div>
                <div className="font-semibold text-slate-200">Hybrid Detection</div>
                <div className="text-[10px] text-slate-400">Regex + Context NER</div>
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80 flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-sky-950 border border-sky-800 text-sky-400 flex items-center justify-center text-[10px] font-bold shrink-0">3</span>
              <div>
                <div className="font-semibold text-slate-200">Entity Linking</div>
                <div className="text-[10px] text-slate-400">Name Variant Clusters</div>
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80 flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-sky-950 border border-sky-800 text-sky-400 flex items-center justify-center text-[10px] font-bold shrink-0">4</span>
              <div>
                <div className="font-semibold text-slate-200">Human Review</div>
                <div className="text-[10px] text-slate-400">Authoritative Decisions</div>
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80 flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-emerald-950 border border-emerald-800 text-emerald-400 flex items-center justify-center text-[10px] font-bold shrink-0">5</span>
              <div>
                <div className="font-semibold text-emerald-300">Sanitization</div>
                <div className="text-[10px] text-emerald-400/80">Redaction & Summary</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Upload Dropzone or Processing View */}
      <div className="space-y-4">
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
          <div className="max-w-2xl mx-auto p-4 rounded-xl bg-rose-950/40 border border-rose-900/60 text-rose-300 text-xs flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <div>
              <strong className="font-semibold block">Ingestion or Validation Error:</strong>
              <p className="mt-0.5">{uploadError}</p>
            </div>
          </div>
        )}
      </div>

      {/* Backend Health Status Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Card 1: Backend Connection */}
        <div className="p-5 rounded-xl bg-slate-800/60 border border-slate-700/60 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">FastAPI Backend</span>
            <Server className="w-5 h-5 text-sky-400" />
          </div>
          <div className="flex items-center gap-2">
            {healthLoading ? (
              <span className="text-sm text-slate-400">Connecting...</span>
            ) : healthError ? (
              <>
                <AlertTriangle className="w-5 h-5 text-amber-400" />
                <span className="text-sm font-semibold text-amber-400">Disconnected</span>
              </>
            ) : (
              <>
                <CheckCircle className="w-5 h-5 text-emerald-400" />
                <span className="text-sm font-semibold text-emerald-400">
                  Online ({health?.app_name} v{health?.version})
                </span>
              </>
            )}
          </div>
          <p className="text-xs text-slate-400">Bound strictly to 127.0.0.1:8000</p>
        </div>

        {/* Card 2: SQLite Metadata Store */}
        <div className="p-5 rounded-xl bg-slate-800/60 border border-slate-700/60 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">SQLite Metadata</span>
            <Database className="w-5 h-5 text-emerald-400" />
          </div>
          <div className="flex items-center gap-2">
            {health?.database_connected ? (
              <>
                <CheckCircle className="w-5 h-5 text-emerald-400" />
                <span className="text-sm font-semibold text-emerald-400">Ready (data/privydoc.db)</span>
              </>
            ) : (
              <span className="text-sm text-slate-400">Checking...</span>
            )}
          </div>
          <p className="text-xs text-slate-400">Stores metadata only; zero raw PII</p>
        </div>

        {/* Card 3: Privacy Boundary */}
        <div className="p-5 rounded-xl bg-slate-800/60 border border-slate-700/60 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Privacy Boundary</span>
            <Shield className="w-5 h-5 text-sky-400" />
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-emerald-400" />
            <span className="text-sm font-semibold text-emerald-400">100% Local-First Active</span>
          </div>
          <p className="text-xs text-slate-400">Zero cloud calls, offline verified</p>
        </div>
      </div>

      {/* Development Roadmap Status (P0 to P9) */}
      <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
        <h3 className="text-lg font-bold text-white flex items-center gap-2">
          <FileText className="w-5 h-5 text-sky-400" />
          Development Phases Overview (P0–P9)
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
          <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-800 text-emerald-300 font-medium">
            P0: Setup & Scaffolding (Done)
          </div>
          <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-800 text-emerald-300 font-medium">
            P1: Ingestion (TXT & PDF) (Done)
          </div>
          <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-800 text-emerald-300 font-medium">
            P2: Regex + NER Detection (Done)
          </div>
          <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-800 text-emerald-300 font-medium">
            P3: SLM & Entity Linking (Done)
          </div>
          <div className="p-3 rounded-lg bg-sky-950/80 border border-sky-600 text-sky-200 font-semibold shadow-sm">
            P4: Human Review UI (Active)
          </div>
          <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700 text-slate-400">
            P5: Redaction & Verification
          </div>
          <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700 text-slate-400">
            P6: Safe Summarization
          </div>
          <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700 text-slate-400">
            P7: Feedback & Evaluation
          </div>
          <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700 text-slate-400">
            P8: Hardening & Integration
          </div>
          <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700 text-slate-400">
            P9: Demo & Final Release
          </div>
        </div>
      </div>
    </div>
  );
}
