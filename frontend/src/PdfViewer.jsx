import React, { useEffect, useRef, useState, useCallback } from 'react';
import { loadScript, getToken } from './Docutils';
import { Spinner, PageSkeleton, EndOfDocument } from './Sharedui';
import { useIntersectionVisible } from './Hooks';
import { CenteredNoteButton, FloatingNotePanel } from './NoteSection';

const PDFJS_VERSION = '3.4.120';
const PDFJS_CDN = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}`;

// ── Text layer: line-grouped spans with non-overlapping vertical bounds ─────
//
// THE CORE PROBLEM with fixed height/top:
//   Every span gets top = baselineY - (fontHeight * ascenderRatio) and
//   height = fontHeight. But line-spacing in PDFs is usually 120-140% of
//   fontHeight, so the span's bottom (baseline + descender) overlaps the
//   whitespace above the NEXT line's span top. When the cursor enters that
//   overlap zone, the browser hits the wrong line's spans.
//
// FIX — compute height from actual line spacing:
//   1. Parse all items, compute their baseline Y.
//   2. Group items that share the same baseline (same line).
//   3. Sort lines top-to-bottom.
//   4. Each line's span height = gap to the NEXT line's baseline (capped at
//      fontHeight * 1.5 for the last line). This guarantees zero vertical
//      overlap between lines — the spans tile perfectly with no gaps or overlaps.
//
const renderTextLayer = async (textLayer, page, viewport) => {
  textLayer.innerHTML = '';
  const { items } = await page.getTextContent();
  const fragment = document.createDocumentFragment();

  // ── 1. Compute transformed data for every item ───────────────────────────
  const parsed = [];
  for (const item of items) {
    if (!item.str) continue;
    const tx = window.pdfjsLib.Util.transform(viewport.transform, item.transform);
    const fontHeight = Math.hypot(tx[0], tx[1]);
    if (fontHeight < 1) continue;

    const baselineX  = tx[4];
    const baselineY  = tx[5];
    const pdfWidthPx = (item.width ?? 0) * viewport.scale;
    const spanWidth  = pdfWidthPx > 2 ? pdfWidthPx : fontHeight * 0.5;

    parsed.push({ str: item.str, baselineX, baselineY, fontHeight, spanWidth });
  }

  if (parsed.length === 0) return;

  // ── 2. Group by baseline Y (round to 1 decimal to merge same-line items) ─
  const lineMap = new Map();
  for (const p of parsed) {
    const key = Math.round(p.baselineY * 10) / 10;
    if (!lineMap.has(key)) lineMap.set(key, []);
    lineMap.get(key).push(p);
  }

  // ── 3. Sort lines top→bottom (ascending Y in CSS coords) ─────────────────
  const sortedBaselines = [...lineMap.keys()].sort((a, b) => a - b);

  // ── 4. For each line, height = distance to next line's baseline ───────────
  //       This makes spans tile perfectly — zero overlap, zero gap.
  for (let i = 0; i < sortedBaselines.length; i++) {
    const baseline     = sortedBaselines[i];
    const nextBaseline = sortedBaselines[i + 1];
    const lineItems    = lineMap.get(baseline);

    // Representative font size for this line
    const fontHeight = lineItems.reduce((m, p) => Math.max(m, p.fontHeight), 0);

    // Height: gap to next line, capped so we don't over-extend on last line
    // or on lines with huge spacing (e.g. after headings).
    // Minimum = fontHeight * 0.8 so short lines are still clickable.
    let spanHeight;
    if (nextBaseline !== undefined) {
      const gap = nextBaseline - baseline;
      // clamp: at least 80% of fontHeight, at most 140% (ignore huge paragraph gaps)
      spanHeight = Math.min(Math.max(gap, fontHeight * 0.8), fontHeight * 1.4);
    } else {
      spanHeight = fontHeight * 1.1; // last line: just cap + small descender
    }

    // Top of the span = baseline minus ascender (80% of fontHeight).
    // Using 80% instead of 100% leaves a small gap above cap-height so
    // moving the cursor above the line doesn't accidentally grab it.
    const ascender = fontHeight * 0.80;
    const top = baseline - ascender;

    for (const p of lineItems) {
      const span = document.createElement('span');
      span.textContent = p.str;
      span.style.cssText = `
        position:               absolute;
        left:                   ${p.baselineX}px;
        top:                    ${top}px;
        width:                  ${p.spanWidth}px;
        height:                 ${spanHeight}px;
        font-size:              ${p.fontHeight}px;
        font-family:            sans-serif;
        line-height:            1;
        white-space:            pre;
        overflow:               hidden;
        color:                  transparent;
        -webkit-text-fill-color:transparent;
        background:             transparent;
        text-shadow:            none;
        text-decoration:        none;
        cursor:                 text;
        user-select:            text;
        -webkit-user-select:    text;
        pointer-events:         auto;
      `;
      fragment.appendChild(span);
    }
  }

  textLayer.appendChild(fragment);
};

// ── Single rendered page ──────────────────────────────────────────────────────
const PdfPage = ({
  pdf, pageNum, containerWidth, onVisible,
  noteContent, onNoteChange, isNoteOpen, onToggleNote, onNoteSave,
}) => {
  const canvasRef     = useRef(null);
  const textLayerRef  = useRef(null);
  const renderTaskRef = useRef(null);
  const [rendered, setRendered]   = useState(false);
  const [rendering, setRendering] = useState(false);
  const wrapperRef  = useIntersectionVisible(pageNum, onVisible);
  const hasRendered = useRef(false);
  const lastWidth   = useRef(0);

  useEffect(() => {
    if (!wrapperRef.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !hasRendered.current && !rendering) {
          hasRendered.current = true;
          renderPage();
        }
      },
      { threshold: 0.1 }
    );
    observer.observe(wrapperRef.current);
    return () => observer.disconnect();
  }, [rendering]);

  const renderPage = useCallback(async () => {
    const canvas    = canvasRef.current;
    const textLayer = textLayerRef.current;
    if (!pdf || !canvas) return;
    if (containerWidth === lastWidth.current && rendered) return;

    renderTaskRef.current?.cancel();
    renderTaskRef.current = null;
    setRendering(true);

    try {
      const page = await pdf.getPage(pageNum);

      const dpr         = window.devicePixelRatio || 1;
      const unscaled    = page.getViewport({ scale: 1 });
      const cssScale    = containerWidth / unscaled.width;

      // Canvas renders at physical pixels (HiDPI sharp)
      const renderVP = page.getViewport({ scale: cssScale * dpr });
      // Text layer uses CSS pixels (coordinates match layout)
      const cssVP    = page.getViewport({ scale: cssScale });

      canvas.width        = renderVP.width;
      canvas.height       = renderVP.height;
      canvas.style.width  = `${containerWidth}px`;
      canvas.style.height = `${cssVP.height}px`;

      if (textLayer) {
        textLayer.style.width  = `${cssVP.width}px`;
        textLayer.style.height = `${cssVP.height}px`;
      }

      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const task = page.render({ canvasContext: ctx, viewport: renderVP });
      renderTaskRef.current = task;
      await task.promise;

      if (textLayer) await renderTextLayer(textLayer, page, cssVP);

      lastWidth.current = containerWidth;
      setRendered(true);
    } catch (err) {
      if (err?.name !== 'RenderingCancelledException') {
        console.error(`Page ${pageNum} render error:`, err);
      }
    } finally {
      setRendering(false);
    }
  }, [pdf, pageNum, containerWidth]);

  useEffect(() => {
    if (hasRendered.current && containerWidth > 0 && containerWidth !== lastWidth.current) {
      renderPage();
    }
  }, [containerWidth, renderPage]);

  useEffect(() => () => { renderTaskRef.current?.cancel(); }, []);

  return (
    <div className="flex flex-col items-center space-y-0">
      <div
        ref={wrapperRef}
        data-page={pageNum}
        className="relative group mx-auto transition-transform duration-300"
        style={{ width: 'fit-content' }}
      >
        <div className="absolute -left-10 top-0 text-xs text-gray-400 font-medium opacity-0 group-hover:opacity-100 transition-opacity select-none">
          p.{pageNum}
        </div>

        <div
          className="bg-white shadow-sm hover:shadow-md transition-shadow duration-300 border border-gray-200/60 relative"
          style={{
            width:     `${containerWidth}px`,
            minHeight: rendered ? undefined : `${containerWidth * 1.414}px`,
            overflow:  'hidden',
          }}
        >
          {!rendered && <PageSkeleton />}

          <canvas
            ref={canvasRef}
            className="block"
            style={{ pointerEvents: 'none', display: 'block' }}
          />

          <div
            ref={textLayerRef}
            className="pdf-text-layer"
            style={{
              position:         'absolute',
              top:              0,
              left:             0,
              overflow:         'hidden',
              pointerEvents:    'auto',
              userSelect:       'text',
              WebkitUserSelect: 'text',
              zIndex:           2,
            }}
          />

          {rendering && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <Spinner size="w-7 h-7" color="border-t-gray-400" />
            </div>
          )}

          <div className="border-t border-gray-100 flex items-center justify-center px-4 py-2.5 bg-white">
            <CenteredNoteButton
              hasNote={!!noteContent}
              isOpen={isNoteOpen}
              onClick={() => onToggleNote(pageNum)}
              pageNum={pageNum}
            />
          </div>
        </div>
      </div>

      <FloatingNotePanel
        pageNum={pageNum}
        note={noteContent || ''}
        onChange={(val) => onNoteChange(pageNum, val)}
        isOpen={isNoteOpen}
        onClose={() => onToggleNote(pageNum)}
        onSave={onNoteSave}
      />
    </div>
  );
};

// ── Main PdfViewer ────────────────────────────────────────────────────────────
const PdfViewer = ({
  pdfUrl, onPageChange, pageNotes, onNoteChange,
  openNotePageNum, onToggleNote, onNoteSave,
}) => {
  const [ready, setReady]               = useState(false);
  const [error, setError]               = useState(null);
  const [totalPages, setTotalPages]     = useState(0);
  const [currentPage, setCurrentPage]   = useState(1);
  const [containerWidth, setContainerWidth] = useState(860);
  const [padding, setPadding]           = useState(48);
  const pdfDocRef    = useRef(null);
  const scrollRef    = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    loadScript(`${PDFJS_CDN}/pdf.min.js`)
      .then(() => {
        window.pdfjsLib.GlobalWorkerOptions.workerSrc = `${PDFJS_CDN}/pdf.worker.min.js`;
        setReady(true);
      })
      .catch(() => setError('Failed to load PDF.js'));
  }, []);

  useEffect(() => {
    const measure = () => {
      if (containerRef.current) {
        const totalWidth = containerRef.current.clientWidth;
        const p = totalWidth < 640 ? 16 : 48;
        setPadding(p);
        setContainerWidth(Math.max(totalWidth - p * 2, 280));
      }
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (containerRef.current) ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!ready || !pdfUrl) return;
    const token =
      new URL(pdfUrl, window.location.href).searchParams.get('token') || getToken();

    window.pdfjsLib
      .getDocument({
        url: pdfUrl,
        httpHeaders: token ? { Authorization: `Bearer ${token}` } : {},
        withCredentials: false,
      })
      .promise
      .then((pdf) => {
        pdfDocRef.current = pdf;
        setTotalPages(pdf.numPages);
        setCurrentPage(1);
        setError(null);
      })
      .catch((err) => {
        console.error('PDF load error:', err);
        setError('Failed to load PDF. Please try again.');
      });

    return () => { pdfDocRef.current?.destroy(); pdfDocRef.current = null; };
  }, [ready, pdfUrl]);

  useEffect(() => () => { pdfDocRef.current?.destroy(); }, []);

  const handlePageVisible = useCallback((pageNum) => {
    setCurrentPage(pageNum);
    onPageChange?.(pageNum);
  }, [onPageChange]);

  const scrollToPage = (pageNum) => {
    const p  = Math.max(1, Math.min(pageNum, totalPages));
    const el = scrollRef.current?.querySelector(`[data-page="${p}"]`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  if (error) return (
    <div className="flex items-center justify-center p-8 text-red-500 text-sm font-medium">{error}</div>
  );
  if (!ready || totalPages === 0) return (
    <div className="flex items-center justify-center p-12">
      <Spinner size="w-8 h-8" color="border-t-gray-500" />
    </div>
  );

  return (
    <div className="relative flex" ref={containerRef}>
      <div ref={scrollRef} className="flex-1 overflow-y-auto pb-20 scroll-smooth" style={{ maxHeight: '100vh' }}>
        <div
          className="flex flex-col items-center space-y-8 pt-8"
          style={{ paddingLeft: padding, paddingRight: padding }}
        >
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((pageNum) => (
            <PdfPage
              key={pageNum}
              pdf={pdfDocRef.current}
              pageNum={pageNum}
              containerWidth={containerWidth}
              onVisible={handlePageVisible}
              noteContent={pageNotes?.[pageNum] || ''}
              onNoteChange={onNoteChange}
              isNoteOpen={openNotePageNum === pageNum}
              onToggleNote={onToggleNote}
              onNoteSave={onNoteSave}
            />
          ))}
          <EndOfDocument />
        </div>
      </div>

      <div className="absolute top-4 right-4 z-10 flex flex-col items-end gap-2 pointer-events-none">
        <div className="bg-white/90 backdrop-blur-sm border border-gray-200 shadow-sm px-4 py-1.5 rounded-full pointer-events-auto select-none">
          <span className="text-xs font-medium text-gray-600">
            Page {currentPage} of {totalPages}
          </span>
        </div>
        <div className="bg-white/90 backdrop-blur-sm border border-gray-200 shadow-sm px-2 py-1.5 rounded-full pointer-events-auto flex items-center gap-1 select-none">
          {[
            { label: '<', title: 'Previous page', delta: -1, disabled: currentPage <= 1 },
            { label: '>', title: 'Next page',     delta:  1, disabled: currentPage >= totalPages },
          ].map(({ label, title, delta, disabled }) => (
            <button
              key={title}
              onClick={() => scrollToPage(currentPage + delta)}
              disabled={disabled}
              title={title}
              className="w-6 h-6 flex items-center justify-center text-gray-500 hover:bg-gray-100 rounded-full disabled:opacity-30 disabled:cursor-not-allowed transition-all text-base leading-none"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default PdfViewer;