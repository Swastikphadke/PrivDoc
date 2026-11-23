import React, { useState } from 'react';
import { ChevronLeft, ChevronRight, FileText, ZoomIn, ZoomOut } from 'lucide-react';
import { getPdfPageImageUrl } from '../../services/api';

export default function PdfViewer({
  documentId,
  pageCount = 1,
  currentPage = 1,
  onPageChange,
  coordinates = [],
  candidates = [],
}) {
  const [zoom, setZoom] = useState(100);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);

  const pageCoordinates = coordinates.filter((c) => c.page_number === currentPage);

  return (
    <div className="flex flex-col h-full bg-slate-950 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
      {/* PDF Controls */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900 border-b border-slate-800 text-xs">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-cyan-400" />
          <span className="font-semibold text-slate-200">PDF Visual Page Stream</span>
          <span className="text-slate-400 font-mono">
            Page {currentPage} of {pageCount}
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* Zoom controls */}
          <div className="flex items-center gap-1 bg-slate-800 rounded px-1.5 py-0.5 border border-slate-700">
            <button
              onClick={() => setZoom((z) => Math.max(50, z - 10))}
              className="p-1 text-slate-400 hover:text-slate-200"
              title="Zoom out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="text-[11px] font-mono w-10 text-center text-slate-300">{zoom}%</span>
            <button
              onClick={() => setZoom((z) => Math.min(200, z + 10))}
              className="p-1 text-slate-400 hover:text-slate-200"
              title="Zoom in"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Page navigation */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => onPageChange?.(Math.max(1, currentPage - 1))}
              disabled={currentPage <= 1}
              className="p-1 text-slate-300 bg-slate-800 hover:bg-slate-700 disabled:opacity-30 rounded border border-slate-700"
              title="Previous Page"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => onPageChange?.(Math.min(pageCount, currentPage + 1))}
              disabled={currentPage >= pageCount}
              className="p-1 text-slate-300 bg-slate-800 hover:bg-slate-700 disabled:opacity-30 rounded border border-slate-700"
              title="Next Page"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Page Canvas View */}
      <div className="flex-1 overflow-auto p-6 flex items-center justify-center bg-slate-900/40">
        <div
          className="relative shadow-2xl border border-slate-700 rounded bg-white overflow-hidden transition-all duration-150"
          style={{ width: `${(zoom / 100) * 600}px` }}
        >
          {documentId && (
            <img
              src={getPdfPageImageUrl(documentId, currentPage)}
              alt={`PDF Page ${currentPage}`}
              className="w-full h-auto block select-none pointer-events-none"
              onLoad={() => {
                setImageLoaded(true);
                setImageError(false);
              }}
              onError={() => setImageError(true)}
            />
          )}

          {imageError && (
            <div className="p-12 text-center text-slate-500 text-xs bg-slate-950">
              <p>Unable to render PDF page bitmap stream.</p>
              <p className="mt-1 text-slate-600">Switch to Canonical Text view to review extracted content.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
