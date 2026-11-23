import React, { useState, useRef } from 'react';
import { UploadCloud, FileText, AlertCircle, ShieldCheck, FileCheck } from 'lucide-react';

export default function UploadDropzone({ onUpload, isUploading = false, error = null }) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [localError, setLocalError] = useState(null);
  const fileInputRef = useRef(null);

  const MAX_SIZE_BYTES = 20 * 1024 * 1024; // 20MB

  const handleFiles = (files) => {
    setLocalError(null);
    if (!files || files.length === 0) return;
    const file = files[0];

    // Check extension
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (!['txt', 'pdf'].includes(ext)) {
      setLocalError('Invalid file format. PrivyDoc strictly accepts .txt and text-based .pdf files.');
      return;
    }

    // Check size limit
    if (file.size > MAX_SIZE_BYTES) {
      setLocalError(`File size exceeds the 20MB maximum limit (${(file.size / (1024 * 1024)).toFixed(1)}MB).`);
      return;
    }

    onUpload(file);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    if (isUploading) return;
    handleFiles(e.dataTransfer.files);
  };

  const handleChange = (e) => {
    handleFiles(e.target.files);
  };

  return (
    <div className="w-full max-w-2xl mx-auto space-y-4">
      {/* Drag & Drop Surface */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-xl p-8 sm:p-12 text-center cursor-pointer transition-all duration-200 ${
          isDragOver
            ? 'border-cyan-500 bg-cyan-950/20'
            : 'border-slate-800 bg-slate-900/60 hover:border-slate-700 hover:bg-slate-900'
        } ${isUploading ? 'opacity-60 cursor-not-allowed' : ''}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.pdf"
          className="hidden"
          onChange={handleChange}
          disabled={isUploading}
        />

        <div className="flex flex-col items-center justify-center space-y-4">
          <div className="p-4 rounded-full bg-slate-800/80 border border-slate-700 text-cyan-400">
            <UploadCloud className="w-8 h-8" />
          </div>

          <div>
            <h3 className="text-lg font-semibold text-slate-100">
              {isUploading ? 'Uploading and validating file...' : 'Drop your document here or click to browse'}
            </h3>
            <p className="text-sm text-slate-400 mt-1">
              Supports <span className="text-slate-200 font-medium">.txt</span> and text-based{' '}
              <span className="text-slate-200 font-medium">.pdf</span> (Max 20MB)
            </p>
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-400 bg-slate-800/50 px-3 py-1.5 rounded-full border border-slate-700/60">
            <FileText className="w-3.5 h-3.5 text-cyan-400" />
            <span>Deterministic UTF-8 and PDF text extraction with Unicode coordinate mapping</span>
          </div>
        </div>
      </div>

      {/* Local Security Assurance */}
      <div className="flex items-center justify-between p-3.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-400 flex-shrink-0" />
          <span>
            <strong className="text-slate-100 font-medium">Local-Only Processing:</strong> Documents remain strictly on
            your machine at <code className="text-cyan-300">127.0.0.1</code>. No cloud data transmission.
          </span>
        </div>
        <span className="text-[11px] uppercase tracking-wider text-emerald-400 font-semibold bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800">
          Air-Gapped Ready
        </span>
      </div>

      {/* Error alert */}
      {(error || localError) && (
        <div className="p-4 rounded-lg bg-rose-950/50 border border-rose-800 text-rose-200 flex items-start gap-3 text-sm">
          <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium text-rose-100">Upload Validation Error</p>
            <p className="text-xs text-rose-300 mt-0.5">{error || localError}</p>
          </div>
        </div>
      )}
    </div>
  );
}
