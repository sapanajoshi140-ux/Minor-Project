// ─────────────────────────────────────────────────────────────────────────────
// PdfViewer.jsx  —  refactored; shared code lives in ../shared/
// ─────────────────────────────────────────────────────────────────────────────
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { loadScript, loadLink, getToken }                  from './Docutils';
import { Spinner, PageSkeleton, EndOfDocument }            from './Sharedui';
import { useIntersectionVisible }                          from './Hooks';

const PDFJS_VERSION = '3.4.120';
const PDFJS_CDN     = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}`;

// ── Single rendered page ──────────────────────────────────────────────────────
const PdfPage = ({ pdf, pageNum, onVisible }) => {
  const canvasRef     = useRef(null);
  const textLayerRef  = useRef(null);
  const renderTaskRef = useRef(null);
  const [rendered,  setRendered]  = useState(false);
  const [rendering, setRendering] = useState(false);

  // Fire onVisible whenever this page enters the viewport
  const wrapperRef = useIntersectionVisible(pageNum, onVisible);

  // Lazy-render on first intersection
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
    const canvas    = canvasRef.current;
    const textLayer = textLayerRef.current;
    if (!pdf || !canvas) return;

    if (renderTaskRef.current) {
      renderTaskRef.current.cancel();
      renderTaskRef.current = null;
    }

    setRendering(true);
    try {
      const page     = await pdf.getPage(pageNum);
      const viewport = page.getViewport({ scale: 1.5 });

      canvas.width  = viewport.width;
      canvas.height = viewport.height;

      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const task = page.render({ canvasContext: ctx, viewport });
      renderTaskRef.current = task;
      await task.promise;

      if (textLayer) {
        textLayer.innerHTML = '';
        textLayer.style.width  = `${viewport.width}px`;
        textLayer.style.height = `${viewport.height}px`;

        const textContent = await page.getTextContent();
        textContent.items.forEach((item) => {
          if (!item.str) return;
          const tx       = window.pdfjsLib.Util.transform(viewport.transform, item.transform);
          const fontSize = Math.sqrt(tx[0] * tx[0] + tx[1] * tx[1]);
          const span     = document.createElement('span');
          span.textContent = item.str;
          span.style.cssText = `
            position:absolute;left:${tx[4]}px;top:${tx[5] - fontSize}px;
            font-size:${fontSize}px;font-family:sans-serif;
            transform-origin:0% 0%;white-space:pre;cursor:text;color:transparent;
          `;
          textLayer.appendChild(span);
        });
      }

      setRendered(true);
    } catch (err) {
      if (err?.name !== 'RenderingCancelledException') {
        console.error(`Page ${pageNum} render error:`, err);
      }
    } finally {
      setRendering(false);
    }
  }, [pdf, pageNum]);

  useEffect(() => () => { renderTaskRef.current?.cancel(); }, []);

  return (
    <div
      ref={wrapperRef}
      data-page={pageNum}
      className="relative group mx-auto transition-transform duration-300"
      style={{ width: 'fit-content' }}
    >
      {/* Page-number label on hover */}
      <div className="absolute -left-10 top-0 text-xs text-gray-400 font-medium opacity-0 group-hover:opacity-100 transition-opacity select-none">
        p.{pageNum}
      </div>

      {/* A4 card */}
      <div
        className="bg-white shadow-sm hover:shadow-md transition-shadow duration-300 border border-gray-200/60 relative overflow-hidden"
        style={{ minHeight: rendered ? undefined : '297mm', minWidth: '210mm' }}
      >
        {!rendered && <PageSkeleton />}

        <canvas
          ref={canvasRef}
          className={`block max-w-full transition-opacity duration-200 ${rendering ? 'opacity-50' : 'opacity-100'}`}
        />

        <div
          ref={textLayerRef}
          className="absolute top-0 left-0 overflow-hidden select-text pointer-events-auto"
        />

        {rendering && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <Spinner size="w-7 h-7" color="border-t-gray-400" />
          </div>
        )}
      </div>
    </div>
  );
};

// ── Main PdfViewer ────────────────────────────────────────────────────────────
const PdfViewer = ({ pdfUrl }) => {
  const [ready,       setReady]       = useState(false);
  const [error,       setError]       = useState(null);
  const [totalPages,  setTotalPages]  = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const pdfDocRef = useRef(null);
  const scrollRef = useRef(null);

  // Load PDF.js once
  useEffect(() => {
    loadLink(`${PDFJS_CDN}/pdf_viewer.min.css`);
    loadScript(`${PDFJS_CDN}/pdf.min.js`)
      .then(() => {
        window.pdfjsLib.GlobalWorkerOptions.workerSrc = `${PDFJS_CDN}/pdf.worker.min.js`;
        setReady(true);
      })
      .catch(() => setError('Failed to load PDF.js'));
  }, []);

  // Load document
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

    return () => { if (pdfDocRef.current) { pdfDocRef.current.destroy(); pdfDocRef.current = null; } };
  }, [ready, pdfUrl]);

  useEffect(() => () => { pdfDocRef.current?.destroy(); }, []);

  const handlePageVisible = useCallback((pageNum) => setCurrentPage(pageNum), []);

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
    <div className="relative flex">
      {/* Scroll area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto pb-20 scroll-smooth" style={{ maxHeight: '100vh' }}>
        <div className="flex flex-col items-center space-y-8 pt-8 px-12">
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((pageNum) => (
            <PdfPage key={pageNum} pdf={pdfDocRef.current} pageNum={pageNum} onVisible={handlePageVisible} />
          ))}
          <EndOfDocument />
        </div>
      </div>

      {/* Right overlay: page tracker */}
      <div className="absolute top-4 right-4 z-10 flex flex-col items-end gap-2 pointer-events-none">
        {/* Page pill */}
        <div className="bg-white/90 backdrop-blur-sm border border-gray-200 shadow-sm px-4 py-1.5 rounded-full pointer-events-auto select-none">
          <span className="text-xs font-medium text-gray-600">
            Page {currentPage} of {totalPages}
          </span>
        </div>

        {/* Prev / next */}
        <div className="bg-white/90 backdrop-blur-sm border border-gray-200 shadow-sm px-2 py-1.5 rounded-full pointer-events-auto flex items-center gap-1 select-none">
          {[
            { label: '‹', title: 'Previous page', delta: -1, disabled: currentPage <= 1 },
            { label: '›', title: 'Next page',     delta:  1, disabled: currentPage >= totalPages },
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

        {/* Dot nav for small documents */}
        {totalPages <= 20 && (
          <div className="flex flex-col items-center gap-1.5 pointer-events-auto">
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
              <button
                key={p}
                onClick={() => scrollToPage(p)}
                title={`Page ${p}`}
                className={`rounded-full transition-all duration-200 ${
                  p === currentPage ? 'w-2 h-2 bg-gray-600' : 'w-1.5 h-1.5 bg-gray-300 hover:bg-gray-400'
                }`}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default PdfViewer;