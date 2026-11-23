import React from 'react';
import { useLocation } from 'react-router-dom';
import { ShieldCheck } from 'lucide-react';

export default function Footer() {
  const location = useLocation();
  // Hide footer on full-viewport review workstation to maximize document inspection height
  if (location.pathname.startsWith('/review/')) {
    return null;
  }

  return (
    <footer className="border-t border-slate-800/80 bg-[#070b14] py-4 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-2 text-[11px] text-slate-500">
        <div className="flex flex-wrap items-center justify-center gap-3 text-slate-400 font-mono">
          <span className="flex items-center gap-1 text-emerald-400/90">
            <ShieldCheck className="w-3.5 h-3.5" /> Zero-Egress Boundary
          </span>
          <span>•</span>
          <span>Local-First Processing</span>
          <span>•</span>
          <span>Human-in-the-Loop Authority</span>
          <span>•</span>
          <span>Redact Before Summarize</span>
          <span>•</span>
          <span>Fail-Closed Export Verification</span>
        </div>
        <p className="text-slate-500">
          Bound exclusively to <code className="text-slate-400 font-mono">127.0.0.1</code>. Zero cloud inference or telemetry.
        </p>
      </div>
    </footer>
  );
}
