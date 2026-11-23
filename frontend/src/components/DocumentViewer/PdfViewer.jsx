import React, { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight, FileText, ZoomIn, ZoomOut } from 'lucide-react';
import { getPdfPageImageUrl } from '../../services/api';
import { CATEGORY_THEMES } from '../../utils/theme';

export default function PdfViewer({
  documentId,
  pageCount = 1,
  currentPage,
  onPageChange,
  coordinates = [],
  candidates = [],
  selectedCandidateId = null,
  onSelectCandidate,
}) {
  const [zoom, setZoom] = useState(100);
  const [internalPage, setInternalPage] = useState(1);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);

  const activePage = currentPage !== undefined ? currentPage : internalPage;

  const handlePageSwitch = (nextPage) => {
    const clamped = Math.max(1, Math.min(pageCount, nextPage));
    setInternalPage(clamped);
    onPageChange?.(clamped);
  };

  const pageCoordinates = useMemo(
    () => coordinates.filter((c) => c.page_number === activePage),
    [coordinates, activePage]
  );

  // Page geometry from extracted CoordinateSpan (accounts for rotation and cropbox)
  const pageGeometry = useMemo(() => {
    const first = pageCoordinates[0];
    return {
      x0: first?.page_x0 ?? 0,
      y0: first?.page_y0 ?? 0,
      width: first?.page_width > 0 ? first.page_width : 595,
      height: first?.page_height > 0 ? first.page_height : 842,
    };
  }, [pageCoordinates]);

  // Candidates on this page with valid bounding boxes
  const pageCandidates = useMemo(() => {
    return candidates.filter(
      (c) =>
        (c.page_number === activePage || (!c.page_number && activePage === 1)) &&
        Array.isArray(c.bbox) &&
        c.bbox.length === 4
    );
  }, [candidates, activePage]);

  return (
    <div className="flex flex-col h-full bg-slate-950 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
      {/* PDF Controls */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900 border-b border-slate-800 text-xs">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-cyan-400" />
          <span className="font-semibold text-slate-200">PDF Visual Page Stream</span>
          <span className="text-slate-400 font-mono" data-testid="pdf-page-indicator">
            Page {activePage} of {pageCount}
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
              onClick={() => handlePageSwitch(activePage - 1)}
              disabled={activePage <= 1}
              className="p-1 text-slate-300 bg-slate-800 hover:bg-slate-700 disabled:opacity-30 rounded border border-slate-700"
              title="Previous Page"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => handlePageSwitch(activePage + 1)}
              disabled={activePage >= pageCount}
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
              src={getPdfPageImageUrl(documentId, activePage)}
              alt={`PDF Page ${activePage}`}
              className="w-full h-auto block select-none pointer-events-none"
              onLoad={() => {
                setImageLoaded(true);
                setImageError(false);
              }}
              onError={() => setImageError(true)}
            />
          )}

          {/* Interactive Candidate Bounding-Box Overlays */}
          {!imageError && pageCandidates.length > 0 && (
            <div className="absolute inset-0 pointer-events-none" data-testid="pdf-bbox-overlay-layer">
              {pageCandidates.map((cand) => {
                const [x0, y0, x1, y1] = cand.bbox;
                const leftPct = Math.max(0, Math.min(100, ((x0 - pageGeometry.x0) / pageGeometry.width) * 100));
                const topPct = Math.max(0, Math.min(100, ((y0 - pageGeometry.y0) / pageGeometry.height) * 100));
                const widthPct = Math.max(0.5, Math.min(100 - leftPct, ((x1 - x0) / pageGeometry.width) * 100));
                const heightPct = Math.max(0.5, Math.min(100 - topPct, ((y1 - y0) / pageGeometry.height) * 100));

                const isSelected = cand.candidate_id === selectedCandidateId;
                const isApproved = cand.review_status === 'APPROVED';
                const isRejected = cand.review_status === 'REJECTED';
                const theme = CATEGORY_THEMES[cand.type] || CATEGORY_THEMES.DEFAULT;

                return (
                  <button
                    key={cand.candidate_id}
                    type="button"
                    data-testid={`pdf-bbox-${cand.candidate_id}`}
                    onClick={() => onSelectCandidate?.(cand.candidate_id)}
                    style={{
                      left: `${leftPct}%`,
                      top: `${topPct}%`,
                      width: `${widthPct}%`,
                      height: `${heightPct}%`,
                    }}
                    title={`${cand.type}: ${cand.text} (${cand.review_status})`}
                    className={`absolute pointer-events-auto rounded-sm transition-all cursor-pointer ${
                      isApproved
                        ? 'bg-emerald-500/35 border-2 border-emerald-500'
                        : isRejected
                        ? 'bg-slate-500/15 border border-dashed border-slate-400 opacity-50'
                        : 'bg-amber-400/30 border-2 border-amber-500'
                    } ${isSelected ? 'ring-2 ring-cyan-400 z-10 shadow-lg' : ''}`}
                  >
                    <span className="sr-only">
                      {theme.label}: {cand.text}
                    </span>
                  </button>
                );
              })}
            </div>
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
