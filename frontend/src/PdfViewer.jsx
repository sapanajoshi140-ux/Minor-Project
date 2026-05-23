import React, { useEffect, useRef, useState, useCallback } from 'react';
import { loadScript, getToken } from './Docutils';
import { Spinner, PageSkeleton, EndOfDocument } from './Sharedui';
import { useIntersectionVisible } from './Hooks';
import { CenteredNoteButton, FloatingNotePanel } from './NoteSection';

const PDFJS_VERSION = '3.4.120';
const PDFJS_CDN = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}`;

// ── Render text layer: one span per item, exact pdf.js transform logic ──────
const renderTextLayer = async (textLayer, page, viewport) => {
  textLayer.innerHTML = '';
  textLayer.style.width = `${viewport.width}px`;
  textLayer.style.height = `${viewport.height}px`;

  const textContent = await page.getTextContent();

  for (const item of textContent.items) {
    const tx = window.pdfjsLib.Util.transform(viewport.transform, item.transform);

    const fontHeight = Math.hypot(tx[0], tx[1]);
    const fontWidth = Math.hypot(tx[2], tx[3]);
    const fontSize = fontHeight;

    const left = tx[4];
    const top = tx[5] - fontSize;

    const span = document.createElement('span');
    span.style.cssText = `
      position: absolute;
      left: ${left}px;
      top: ${top}px;
      font-size: ${fontSize}px;
      font-family: sans-serif;
      transform: scaleX(${fontWidth / fontHeight || 1});
      transform-origin: 0% 0%;
      white-space: pre;
      cursor: text;
      color: transparent;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      user-select: text;
      pointer-events: auto;
    `;
    span.textContent = item.str;
    textLayer.appendChild(span);
  }
};

// ── Single rendered page ──────────────────────────────────────────────────────
const PdfPage = ({
  pdf,
  pageNum,
  containerWidth,
  onVisible,
  noteContent,
  onNoteChange,
  isNoteOpen,
  onToggleNote,
  onNoteSave,
}) => {
  const canvasRef = useRef(null);
  const textLayerRef = useRef(null);
  const renderTaskRef = useRef(null);
  const [rendered, setRendered] = useState(false);
  const [rendering, setRendering] = useState(false);

  const wrapperRef = useIntersectionVisible(pageNum, onVisible);
  const hasRendered = useRef(false);

  useEffect(() => {
    if (!wrapperRef.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !hasRendered.current && !rendering) {
          hasRendered.current = true;
          renderPage();
        }
      },
      { threshold: 0.3 }
    );
    observer.observe(wrapperRef.current);
    return () => observer.disconnect();
  }, [rendering]);

  const renderPage = useCallback(async () => {
    const canvas = canvasRef.current;
    const textLayer = textLayerRef.current;
    if (!pdf || !canvas) return;

    if (renderTaskRef.current) {
      renderTaskRef.current.cancel();
      renderTaskRef.current = null;
    }

    setRendering(true);
    try {
      const page = await pdf.getPage(pageNum);

      // Dynamic scale: fit page to container width
      const unscaledViewport = page.getViewport({ scale: 1 });
      const scale = containerWidth / unscaledViewport.width;
      const viewport = page.getViewport({ scale });

      canvas.width = viewport.width;
      canvas.height = viewport.height;

      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const task = page.render({ canvasContext: ctx, viewport });
      renderTaskRef.current = task;
      await task.promise;

      if (textLayer) {
        await renderTextLayer(textLayer, page, viewport);
      }

      setRendered(true);
    } catch (err) {
      if (err?.name !== 'RenderingCancelledException') {
        console.error(`Page ${pageNum} render error:`, err);
      }
    } finally {
      setRendering(false);
    }
  }, [pdf, pageNum, containerWidth]);

  // Re-render when container width changes
  useEffect(() => {
    if (hasRendered.current && containerWidth > 0) {
      hasRendered.current = false;
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
            width: rendered ? `${containerWidth}px` : `${containerWidth}px`,
            minHeight: rendered ? undefined : `${containerWidth * 1.414}px`,
            overflow: 'hidden'
          }}
        >
          {!rendered && <PageSkeleton />}

          <canvas
            ref={canvasRef}
            className="block"
            style={{ 
              width: `${containerWidth}px`,
              height: 'auto',
              pointerEvents: 'none'
            }}
          />

          <div
            ref={textLayerRef}
            className="absolute top-0 left-0 overflow-hidden select-text"
            style={{ 
              pointerEvents: 'auto', 
              zIndex: 2,
              width: `${containerWidth}px`,
              height: '100%'
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
  pdfUrl,
  onPageChange,
  pageNotes,
  onNoteChange,
  openNotePageNum,
  onToggleNote,
  onNoteSave,
}) => {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(null);
  const [totalPages, setTotalPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [containerWidth, setContainerWidth] = useState(860);
  const pdfDocRef = useRef(null);
  const scrollRef = useRef(null);
  const containerRef = useRef(null);
  const [padding, setPadding] = useState(48);
  useEffect(() => {
    loadScript(`${PDFJS_CDN}/pdf.min.js`)
      .then(() => {
        window.pdfjsLib.GlobalWorkerOptions.workerSrc = `${PDFJS_CDN}/pdf.worker.min.js`;
        setReady(true);
      })
      .catch(() => setError('Failed to load PDF.js'));
  }, []);

  // Measure container width
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
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, []);

  useEffect(() => {
    if (!ready || !pdfUrl) return;

    const token =
      new URL(pdfUrl, window.location.href).searchParams.get('token') ||
      getToken();

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

    return () => {
      if (pdfDocRef.current) {
        pdfDocRef.current.destroy();
        pdfDocRef.current = null;
      }
    };
  }, [ready, pdfUrl]);

  useEffect(() => () => { pdfDocRef.current?.destroy(); }, []);

  const handlePageVisible = useCallback((pageNum) => {
    setCurrentPage(pageNum);
    onPageChange?.(pageNum);
  }, [onPageChange]);

  const scrollToPage = (pageNum) => {
    const p = Math.max(1, Math.min(pageNum, totalPages));
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
        <div className="flex flex-col items-center space-y-8 pt-8" style={{ paddingLeft: padding, paddingRight: padding }}>
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
            { label: '>', title: 'Next page', delta: 1, disabled: currentPage >= totalPages },
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