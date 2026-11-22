import React from 'react';

export default function Footer() {
  return (
    <footer className="border-t border-slate-800 bg-slate-950/60 py-6 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center text-xs text-slate-500 space-y-2">
        <div className="flex justify-center space-x-6 text-slate-400">
          <span>Local-First Processing</span>
          <span>•</span>
          <span>Human-in-the-Loop</span>
          <span>•</span>
          <span>Redact Before Summarize</span>
          <span>•</span>
          <span>Verified Export</span>
        </div>
        <p>PrivyDoc enforces strict zero-cloud boundary. No document content is ever sent to external APIs.</p>
      </div>
    </footer>
  );
}
