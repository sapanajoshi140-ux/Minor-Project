import React, { useEffect, useRef, useState, useCallback } from 'react';
import { loadScript, getToken } from './Docutils';
import { Spinner, PageSkeleton, EndOfDocument } from './Sharedui';
import { useIntersectionVisible } from './Hooks';
import { CenteredNoteButton, FloatingNotePanel } from './NoteSection';

const PDFJS_VERSION = '3.4.120';
const PDFJS_CDN = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}`;

// ── Off-screen canvas for measuring natural text widths (avoids DOM thrash) ──
let _measureCanvas = null;
const getMeasureCtx = () => {
  if (!_measureCanvas) {
    _measureCanvas = document.createElement('canvas');
    _measureCanvas.width  = 1;
    _measureCanvas.height = 1;
  }
  return _measureCanvas.getContext('2d');
};

const measureTextWidth = (str, fontHeight) => {
  const ctx = getMeasureCtx();
  ctx.font = `${fontHeight}px sans-serif`;
  return ctx.measureText(str).width || 1;
};

// ── CSS injected once: selection highlight + span base styles ─────────────────
let _cssInjected = false;
const injectTextLayerCSS = () => {
  if (_cssInjected) return;
  _cssInjected = true;
  const style = document.createElement('style');
  style.textContent = `
    /* Isolate stacking context so canvas repaints never pierce the text layer */
    .pdf-text-layer {
      isolation: isolate;
    }

    /* Base span: invisible text positioned over the canvas glyph */
    .pdf-text-layer span {
      position:                absolute;
      color:                   transparent;
      -webkit-text-fill-color: transparent;
      white-space:             pre;
      cursor:                  text;
      user-select:             text;
      -webkit-user-select:     text;
      pointer-events:          auto;
      transform-origin:        0% 100%; /* scale from bottom-left (baseline) */
      line-height:             1;
      /* overflow:visible so scaleX never clips characters */
      overflow:                visible;
    }

    /* Selection highlight — semi-transparent blue, text stays transparent */
    .pdf-text-layer span::selection {
      background:              rgba(59, 130, 246, 0.30);
      color:                   transparent;
      -webkit-text-fill-color: transparent;
    }
    .pdf-text-layer span::-moz-selection {
      background:              rgba(59, 130, 246, 0.30);
      color:                   transparent;
    }
  `;
  document.head.appendChild(style);
};

// ── renderTextLayer ───────────────────────────────────────────────────────────
//
// Design goals (vs the previous version):
//
//  A. PIXEL-PERFECT WIDTH via scaleX
//     Each span's natural browser-rendered width differs from the PDF's reported
//     width due to font substitution, kerning, and character spacing. We measure
//     the natural width with an off-screen canvas and apply CSS scaleX so the
//     rendered span width exactly matches the PDF coordinate space.  This is the
//     same technique used by Mozilla's official pdf.js viewer; it's the only
//     reliable way to align character positions for drag-selection without
//     re-implementing the font renderer.
//
//  B. ZERO INTER-LINE OVERLAP
//     spanHeight = exact gap to next line's baseline.  Lines tile perfectly —
//     no gaps, no overlaps.  Multi-line drag-select never skips a line.
//
//  C. TIGHTER BASELINE GROUPING (0.5 px tolerance)
//     Round baseline to nearest 0.5 instead of 1.0.  Items with sub-pixel
//     differences in their transform (e.g. bold + regular on the same line)
//     now correctly land in the same group.
//
//  D. ACCURATE ASCENDER (0.75 em)
//     Cap-height ≈ 75% of em for most Latin fonts.  Top of span is baseline
//     minus 0.75 × fontHeight, leaving a small gap above letters so the cursor
//     never accidentally selects the line above when hovering between lines.
//
//  E. ROTATION SUPPORT
//     If the PDF transform includes a rotation component (tx[1] ≠ 0), the
//     span gets a matching CSS rotate() + scaleX() transform so rotated
//     text (stamps, watermarks, vertical labels) is still selectable.
//
//  F. TRAILING SPACE PRESERVATION
//     item.str already contains trailing spaces in most PDFs.  white-space:pre
//     preserves them so inter-word gaps are real DOM characters — dragging
//     across a word boundary selects the space correctly.
//
const renderTextLayer = async (textLayer, page, viewport) => {
  injectTextLayerCSS();
  textLayer.innerHTML = '';

  const { items } = await page.getTextContent({ includeMarkedContent: false });
  if (!items.length) return;

  const fragment = document.createDocumentFragment();

  // ── 1. Parse every content item ──────────────────────────────────────────
  const parsed = [];
  for (const item of items) {
    if (!item.str) continue;

    // Full 2-D affine transform in viewport (CSS pixel) space:
    //   [a, b, c, d, e, f]  →  scaleX=a, skewY=b, skewX=c, scaleY=d, tx=e, ty=f
    const tx = window.pdfjsLib.Util.transform(viewport.transform, item.transform);

    // Font height = magnitude of the y-column of the 2×2 sub-matrix
    const fontHeight = Math.hypot(tx[2], tx[3]);
    if (fontHeight < 1) continue;

    // Clockwise rotation angle (0 for ordinary horizontal text)
    const angle = Math.atan2(tx[1], tx[0]);

    // Baseline in CSS pixel coords
    const baselineX = tx[4];
    const baselineY = tx[5];

    // PDF reports item.width in unscaled user units; multiply by viewport.scale
    // to get the intended width in CSS pixels.
    const pdfWidthPx = (item.width ?? 0) * viewport.scale;

    parsed.push({ str: item.str, baselineX, baselineY, fontHeight, pdfWidthPx, angle });
  }

  if (!parsed.length) return;

  // ── 2. Group items by baseline Y (0.5 px tolerance) ─────────────────────
  const lineMap = new Map();
  for (const p of parsed) {
    // Round to nearest 0.5 so sub-pixel differences on the same visual line
    // all collapse to the same key.
    const key = Math.round(p.baselineY * 2) / 2;
    if (!lineMap.has(key)) lineMap.set(key, []);
    lineMap.get(key).push(p);
  }

  // ── 3. Sort groups top → bottom ──────────────────────────────────────────
  const sortedBaselines = [...lineMap.keys()].sort((a, b) => a - b);

  // ── 4. Emit a span per item with scaleX-corrected width ──────────────────
  for (let i = 0; i < sortedBaselines.length; i++) {
    const baseline     = sortedBaselines[i];
    const nextBaseline = sortedBaselines[i + 1];
    const lineItems    = lineMap.get(baseline);

    // Representative font size for this line (tallest item)
    const fontHeight = lineItems.reduce((m, p) => Math.max(m, p.fontHeight), 0);

    // Ascender: top of span = baseline − 0.75 × fontHeight
    // 0.75 matches cap-height in most Latin fonts; leaves a sliver of dead
    // space above the letters so hovering between lines never misfires.
    const ascender = fontHeight * 0.75;
    const top      = baseline - ascender;

    // spanHeight = exact gap to next baseline → zero overlap, zero gap.
    // For the last line use ascender + descender (0.75 + 0.25 = 1.0 × font).
    let spanHeight;
    if (nextBaseline !== undefined) {
      spanHeight = nextBaseline - baseline;
      // Safety floor: never shorter than half a fontHeight (still hittable)
      if (spanHeight < fontHeight * 0.5) spanHeight = fontHeight * 0.5;
    } else {
      spanHeight = fontHeight; // last line: full em
    }

    for (const p of lineItems) {
      const span = document.createElement('span');
      span.textContent = p.str;

      // ── scaleX: fit natural browser width to PDF-reported width ─────────
      // We render at fontHeight px in sans-serif.  The browser's glyph metrics
      // rarely match the PDF's exact advance widths.  CSS scaleX corrects this
      // without re-measuring every character — a single canvas.measureText()
      // per span is O(1) and costs < 1 μs.
      let scaleX = 1;
      if (p.pdfWidthPx > 2 && p.str.trim().length > 0) {
        const naturalW = measureTextWidth(p.str, p.fontHeight);
        if (naturalW > 0) scaleX = p.pdfWidthPx / naturalW;
        // Clamp scaleX: never squish below 0.5× or stretch above 3× —
        // extreme values usually mean the PDF width field is unreliable
        // (e.g. zero-width spaces, ligature placeholders).
        scaleX = Math.min(Math.max(scaleX, 0.5), 3.0);
      }

      // ── Build CSS transform ───────────────────────────────────────────────
      // transform-origin is bottom-left (0% 100%) so scaleX expands rightward
      // from the baseline start — matching how text is normally laid out.
      let transform = '';
      const isRotated = Math.abs(p.angle) > 0.005; // ~0.3°
      if (isRotated) {
        const deg = -(p.angle * 180) / Math.PI;
        transform = scaleX !== 1
          ? `rotate(${deg.toFixed(3)}deg) scaleX(${scaleX.toFixed(4)})`
          : `rotate(${deg.toFixed(3)}deg)`;
      } else if (scaleX !== 1) {
        transform = `scaleX(${scaleX.toFixed(4)})`;
      }

      // ── Apply styles ──────────────────────────────────────────────────────
      // Set properties individually (avoids cssText string re-parse on every span)
      span.style.left      = `${p.baselineX}px`;
      span.style.top       = `${top}px`;
      span.style.fontSize  = `${p.fontHeight}px`;
      span.style.height    = `${spanHeight}px`;
      // Width: let the browser measure natural width, then scaleX fits it.
      // Do NOT set an explicit width — that would clip overflow and break
      // sub-pixel character hit-testing inside the span.
      if (transform) span.style.transform = transform;

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

      const dpr      = window.devicePixelRatio || 1;
      const unscaled = page.getViewport({ scale: 1 });
      const cssScale = containerWidth / unscaled.width;

      // Canvas: physical pixels (HiDPI sharp)
      const renderVP = page.getViewport({ scale: cssScale * dpr });
      // Text layer: CSS pixels (coords match layout)
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