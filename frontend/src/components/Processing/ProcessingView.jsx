import React from 'react';
import { Loader2, CheckCircle2, AlertTriangle, Shield, XCircle } from 'lucide-react';

export default function ProcessingView({
  stage = 'ingesting', // 'ingesting' | 'detecting' | 'resolving' | 'complete' | 'error'
  elapsedSeconds = 0,
  degradedMode = false,
  error = null,
  onCancel,
}) {
  const steps = [
    {
      id: 'ingesting',
      title: 'Document Ingestion & Text Extraction',
      description: 'Parsing UTF-8 / PDF text streams and mapping coordinate geometry.',
    },
    {
      id: 'detecting',
      title: 'Hybrid PII Detection Engine',
      description: 'Running regex patterns, contextual NER models, and false-positive filters.',
    },
    {
      id: 'resolving',
      title: 'Entity Resolution & Clustering',
      description: 'Linking name variants, initials, and titles with conservative ambiguity safeguards.',
    },
  ];

  const getStepStatus = (stepId) => {
    const order = ['ingesting', 'detecting', 'resolving', 'complete'];
    const currentIndex = order.indexOf(stage);
    const stepIndex = order.indexOf(stepId);

    if (stage === 'error') {
      return stepIndex === currentIndex ? 'error' : stepIndex < currentIndex ? 'done' : 'pending';
    }
    if (stepIndex < currentIndex) return 'done';
    if (stepIndex === currentIndex) return 'active';
    return 'pending';
  };

  return (
    <div className="w-full max-w-xl mx-auto p-8 rounded-xl bg-slate-900 border border-slate-800 space-y-6">
      <div className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-cyan-950/80 border border-cyan-800 text-cyan-400">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-slate-100">Document Processing Pipeline</h2>
            <p className="text-xs text-slate-400">Deterministic local pipeline execution</p>
          </div>
        </div>
        <span className="text-xs font-mono text-cyan-400 bg-slate-800 px-2.5 py-1 rounded border border-slate-700">
          {elapsedSeconds.toFixed(1)}s elapsed
        </span>
      </div>

      {/* Steps List */}
      <div className="space-y-4">
        {steps.map((step) => {
          const status = getStepStatus(step.id);
          return (
            <div
              key={step.id}
              className={`p-4 rounded-lg border transition-all ${
                status === 'active'
                  ? 'bg-cyan-950/20 border-cyan-800/80 text-cyan-100'
                  : status === 'done'
                  ? 'bg-slate-900 border-slate-800 text-slate-300'
                  : 'bg-slate-950/40 border-slate-800/50 text-slate-500'
              }`}
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5">
                  {status === 'active' && <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />}
                  {status === 'done' && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
                  {status === 'pending' && <div className="w-4 h-4 rounded-full border border-slate-700" />}
                  {status === 'error' && <XCircle className="w-4 h-4 text-rose-400" />}
                </div>
                <div>
                  <h4 className="text-sm font-medium text-slate-200">{step.title}</h4>
                  <p className="text-xs text-slate-400 mt-0.5">{step.description}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Degraded Mode Warning */}
      {degradedMode && (
        <div className="p-3.5 rounded-lg bg-amber-950/40 border border-amber-800 text-amber-200 flex items-start gap-2.5 text-xs">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <strong className="font-semibold text-amber-100">Operating in Degraded Mode:</strong>
            <p className="mt-0.5 text-amber-300/90">
              Local SLM (Ollama) is offline or timed out. Ingestion and detection completed using deterministic rules and
              statistical NER models.
            </p>
          </div>
        </div>
      )}

      {/* Error View */}
      {error && (
        <div className="p-4 rounded-lg bg-rose-950/50 border border-rose-800 text-rose-200 text-xs">
          <p className="font-semibold text-rose-100">Pipeline Execution Halted</p>
          <p className="mt-1 text-rose-300">{error}</p>
        </div>
      )}

      {/* Cancel button */}
      {onCancel && (
        <div className="pt-2 flex justify-end">
          <button
            onClick={onCancel}
            className="text-xs text-slate-400 hover:text-slate-200 px-3 py-1.5 rounded hover:bg-slate-800 transition"
          >
            Cancel and Return
          </button>
        </div>
      )}
    </div>
  );
}
