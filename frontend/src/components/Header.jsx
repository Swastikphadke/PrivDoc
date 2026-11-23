import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ShieldCheck, Lock, FileText, Download, Sparkles, ChevronRight, LayoutDashboard } from 'lucide-react';

export default function Header() {
  const location = useLocation();
  const path = location.pathname;

  // Extract active documentId if on /review/:id, /export/:id, or /summary/:id
  const match = path.match(/^\/(review|export|summary)\/([^/]+)/);
  const activeStage = match ? match[1] : null;
  const activeDocId = match ? match[2] : null;

  return (
    <header className="border-b border-slate-800/90 bg-[#090e1a]/95 backdrop-blur sticky top-0 z-50">
      <div className="max-w-[1600px] mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-4">
        {/* Left: Brand Identity & Contextual Breadcrumb */}
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/" className="flex items-center gap-2.5 group shrink-0">
            <div className="w-8 h-8 rounded-md bg-sky-600/90 border border-sky-400/30 flex items-center justify-center text-white shadow-sm group-hover:bg-sky-500 transition">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold tracking-tight text-white">PrivyDoc</span>
                <span className="text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded bg-slate-800/90 text-sky-400 border border-slate-700">
                  WORKSTATION
                </span>
              </div>
              <p className="text-[10px] text-slate-400 hidden sm:block leading-none mt-0.5">
                Privacy-Aware Document Redaction & Summary
              </p>
            </div>
          </Link>

          {activeDocId && (
            <div className="hidden md:flex items-center gap-1.5 text-xs text-slate-500 pl-2 border-l border-slate-800">
              <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
              <span className="font-mono text-[11px] text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                Session: {activeDocId.slice(0, 10)}
              </span>
            </div>
          )}
        </div>

        {/* Center: Active Document Workflow Stage Switcher */}
        {activeDocId && (
          <nav aria-label="Document workflow navigation" className="hidden sm:flex items-center gap-1 bg-slate-950 p-1 rounded-md border border-slate-800 text-xs">
            <Link
              to="/"
              className="px-2.5 py-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-900 transition flex items-center gap-1.5"
              title="Return to Command Center"
            >
              <LayoutDashboard className="w-3.5 h-3.5" />
              <span className="hidden lg:inline">Dashboard</span>
            </Link>
            <span className="text-slate-800">|</span>
            <Link
              to={`/review/${activeDocId}`}
              className={`px-2.5 py-1 rounded transition flex items-center gap-1.5 ${
                activeStage === 'review'
                  ? 'bg-sky-950/90 text-sky-300 border border-sky-700/80 font-semibold'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>1. Review & Entities</span>
            </Link>
            <Link
              to={`/export/${activeDocId}`}
              className={`px-2.5 py-1 rounded transition flex items-center gap-1.5 ${
                activeStage === 'export'
                  ? 'bg-sky-950/90 text-sky-300 border border-sky-700/80 font-semibold'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              <Download className="w-3.5 h-3.5" />
              <span>2. Redact & Verify</span>
            </Link>
            <Link
              to={`/summary/${activeDocId}`}
              className={`px-2.5 py-1 rounded transition flex items-center gap-1.5 ${
                activeStage === 'summary'
                  ? 'bg-sky-950/90 text-sky-300 border border-sky-700/80 font-semibold'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>3. Safe Summary</span>
            </Link>
          </nav>
        )}

        {/* Right: Local Boundary Assurance Pill */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-950/50 border border-emerald-800/70 text-emerald-300 text-[11px] font-mono font-medium">
            <Lock className="w-3 h-3 text-emerald-400" />
            <span>Local Mode (127.0.0.1)</span>
          </div>
        </div>
      </div>
    </header>
  );
}
