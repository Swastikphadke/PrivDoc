import React from 'react';
import { ShieldCheck, Lock } from 'lucide-react';

export default function Header() {
  return (
    <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-lg bg-sky-600 flex items-center justify-center text-white shadow-lg shadow-sky-500/20">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
              PrivyDoc
              <span className="text-xs font-medium px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800">
                MVP v0.1.0
              </span>
            </h1>
            <p className="text-xs text-slate-400">Privacy-Aware Document Redaction & Summary</p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-950/60 border border-emerald-800/80 text-emerald-400 text-xs font-medium">
            <Lock className="w-3.5 h-3.5" />
            <span>Local Mode (127.0.0.1)</span>
          </div>
        </div>
      </div>
    </header>
  );
}
