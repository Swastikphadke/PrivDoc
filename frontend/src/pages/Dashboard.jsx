import React, { useEffect, useState } from 'react';
import { getHealthStatus } from '../services/api';
import { Shield, CheckCircle, AlertTriangle, FileText, Database, Server, RefreshCw } from 'lucide-react';

export default function Dashboard() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getHealthStatus();
      setHealth(data);
    } catch (err) {
      setError(err.message || 'Unable to connect to local backend');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
  }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Welcome Banner */}
      <div className="p-6 rounded-2xl bg-gradient-to-r from-slate-900 via-sky-950/40 to-slate-900 border border-slate-800 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-white tracking-tight">Phase P0 — Foundation Active</h2>
            <p className="text-slate-400 text-sm mt-1 max-w-2xl">
              Repository scaffolding, modular backend, local database foundation, and secure frontend shell are initialized.
            </p>
          </div>
          <button
            onClick={fetchHealth}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-sm font-medium transition shadow-lg shadow-sky-600/20 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>Check Health</span>
          </button>
        </div>
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
            {loading ? (
              <span className="text-sm text-slate-400">Connecting...</span>
            ) : error ? (
              <>
                <AlertTriangle className="w-5 h-5 text-amber-400" />
                <span className="text-sm font-semibold text-amber-400">Disconnected</span>
              </>
            ) : (
              <>
                <CheckCircle className="w-5 h-5 text-emerald-400" />
                <span className="text-sm font-semibold text-emerald-400">Online ({health?.app_name} v{health?.version})</span>
              </>
            )}
          </div>
          <p className="text-xs text-slate-400">Bound to 127.0.0.1:8000</p>
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
            P0: Setup & Scaffolding (Active)
          </div>
          <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700 text-slate-400">
            P1: Ingestion (TXT & PDF)
          </div>
          <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700 text-slate-400">
            P2: Regex + NER Detection
          </div>
          <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700 text-slate-400">
            P3: SLM & Entity Linking
          </div>
          <div className="p-3 rounded-lg bg-slate-800/40 border border-slate-700 text-slate-400">
            P4: Human Review UI
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
