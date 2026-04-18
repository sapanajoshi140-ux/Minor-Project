import React, { useEffect, useRef, useState, useCallback } from 'react';

const PDFJS_VERSION = '3.11.174';
const PDFJS_CDN = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}`;

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
    const script = document.createElement('script');
    script.src = src;
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

function loadLink(href) {
  if (document.querySelector(`link[href="${href}"]`)) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = href;
  document.head.appendChild(link);
}

const PdfViewer = ({ pdfUrl }) => {
  const canvasRef        = useRef(null);
  const textLayerRef     = useRef(null);
  const renderTaskRef    = useRef(null);
  const pdfDocRef        = useRef(null);

  const [ready,       setReady]       = useState(false);
  const [error,       setError]       = useState(null);
  const [totalPages,  setTotalPages]  = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [inputPage,   setInputPage]   = useState('1');
  const [rendering,   setRendering]   = useState(false);

  // ── Load PDF.js script + text layer CSS once ──────────────────────────────
  useEffect(() => {
    loadLink(`${PDFJS_CDN}/pdf_viewer.min.css`);
    loadScript(`${PDFJS_CDN}/pdf.min.js`)
      .then(() => {
        window.pdfjsLib.GlobalWorkerOptions.workerSrc =
          `${PDFJS_CDN}/pdf.worker.min.js`;
        setReady(true);
      })
      .catch(() => setError('Failed to load PDF.js'));
  }, []);

  // ── Load PDF document once URL + library are ready ────────────────────────
  useEffect(() => {
    if (!ready || !pdfUrl) return;

    const token = new URL(pdfUrl, window.location.href).searchParams.get('token')
      || localStorage.getItem('access_token')
      || '';

    window.pdfjsLib
      .getDocument({
        url: pdfUrl,
        httpHeaders: { Authorization: `Bearer ${token}` },
        withCredentials: false,
      })
      .promise
      .then((pdf) => {
        pdfDocRef.current = pdf;
        setTotalPages(pdf.numPages);
        setCurrentPage(1);
        setInputPage('1');
      })
      .catch((err) => {
        console.error('PDF load error:', err);
        setError('Failed to load PDF.');
      });

    return () => {
      if (pdfDocRef.current) {
        pdfDocRef.current.destroy();
        pdfDocRef.current = null;
      }
    };
  }, [ready, pdfUrl]);

  // ── Render page + text layer ───────────────────────────────────────────────
  const renderPage = useCallback(async (pageNum) => {
    const pdf    = pdfDocRef.current;
    const canvas = canvasRef.current;
    const textLayer = textLayerRef.current;
    if (!pdf || !canvas) return;

    // Cancel any in-flight render
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

      // Render canvas
      const task = page.render({ canvasContext: ctx, viewport });
      renderTaskRef.current = task;
      await task.promise;

      // ── Render text layer for selection ────────────────────────────────────
      if (textLayer) {
        textLayer.innerHTML = '';
        textLayer.style.width  = `${viewport.width}px`;
        textLayer.style.height = `${viewport.height}px`;

        const textContent = await page.getTextContent();

        window.pdfjsLib.renderTextLayer({
          textContent,
          container: textLayer,
          viewport,
          textDivs: [],
        });
      }
    } catch (err) {
      if (err?.name !== 'RenderingCancelledException') {
        console.error('PDF render error:', err);
        setError('Failed to render page.');
      }
    } finally {
      setRendering(false);
    }
  }, []);

  useEffect(() => {
    if (totalPages > 0) renderPage(currentPage);
  }, [currentPage, totalPages, renderPage]);

  // ── Cleanup on unmount ────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (renderTaskRef.current) renderTaskRef.current.cancel();
      if (pdfDocRef.current)     pdfDocRef.current.destroy();
    };
  }, []);

  // ── Navigation handlers ───────────────────────────────────────────────────
  const goTo = (page) => {
    const p = Math.max(1, Math.min(page, totalPages));
    setCurrentPage(p);
    setInputPage(String(p));
  };

  const handleInputChange = (e) => setInputPage(e.target.value);

  const handleInputCommit = () => {
    const parsed = parseInt(inputPage, 10);
    if (!isNaN(parsed)) goTo(parsed);
    else setInputPage(String(currentPage));
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleInputCommit();
  };

  // ── Render ────────────────────────────────────────────────────────────────
  if (error) return (
    <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-danger)' }}>
      {error}
    </div>
  );

  if (!ready || totalPages === 0) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
      <div style={{
        width: 28, height: 28, borderRadius: '50%',
        border: '2px solid var(--color-border-secondary)',
        borderTopColor: 'var(--color-text-secondary)',
        animation: 'spin 0.8s linear infinite',
      }} />
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>

      {/* ── Top toolbar ── */}
      <div style={{
        position: 'sticky', top: 64, zIndex: 10,
        display: 'flex', alignItems: 'center', gap: 8,
        background: 'var(--color-background-primary)',
        border: '1px solid var(--color-border-tertiary)',
        borderRadius: 999,
        padding: '6px 14px',
        marginBottom: 16,
        boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
        userSelect: 'none',
      }}>
        <button onClick={() => goTo(currentPage - 1)} disabled={currentPage <= 1 || rendering} style={btnStyle(currentPage <= 1 || rendering)} title="Previous page">‹</button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            type="text"
            value={inputPage}
            onChange={handleInputChange}
            onBlur={handleInputCommit}
            onKeyDown={handleKeyDown}
            style={{
              width: 40, textAlign: 'center',
              border: '1px solid var(--color-border-secondary)',
              borderRadius: 6, padding: '2px 4px',
              fontSize: 13, background: 'var(--color-background-secondary)',
              color: 'var(--color-text-primary)', outline: 'none',
            }}
          />
          <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
            / {totalPages}
          </span>
        </div>

        <button onClick={() => goTo(currentPage + 1)} disabled={currentPage >= totalPages || rendering} style={btnStyle(currentPage >= totalPages || rendering)} title="Next page">›</button>

        <div style={{ width: 1, height: 18, background: 'var(--color-border-tertiary)', margin: '0 4px' }} />

        <select
          value={currentPage}
          onChange={(e) => goTo(Number(e.target.value))}
          disabled={rendering}
          style={{
            fontSize: 13,
            border: '1px solid var(--color-border-secondary)',
            borderRadius: 6, padding: '2px 6px',
            background: 'var(--color-background-secondary)',
            color: 'var(--color-text-primary)',
            cursor: 'pointer',
          }}
        >
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
            <option key={p} value={p}>Page {p}</option>
          ))}
        </select>

        {rendering && (
          <div style={{
            width: 14, height: 14, borderRadius: '50%',
            border: '2px solid var(--color-border-secondary)',
            borderTopColor: 'var(--color-text-secondary)',
            animation: 'spin 0.7s linear infinite',
            marginLeft: 4,
          }} />
        )}
      </div>

      {/* ── Canvas + Text Layer wrapper ── */}
      <div style={{ position: 'relative' }}>
        <canvas
          ref={canvasRef}
          style={{
            display: 'block',
            maxWidth: '100%',
            boxShadow: '0 2px 8px rgba(0,0,0,0.10)',
            border: '1px solid var(--color-border-tertiary)',
            opacity: rendering ? 0.5 : 1,
            transition: 'opacity 0.15s',
          }}
        />

        {/* Text layer sits on top of canvas — invisible but selectable */}
        <div
          ref={textLayerRef}
          className="textLayer"
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            overflow: 'hidden',
            opacity: 0.2,           // low opacity so it's invisible but text is selectable
            lineHeight: 1.0,
            userSelect: 'text',
            pointerEvents: 'auto',
          }}
        />

        {rendering && (
          <div style={{
            position: 'absolute', inset: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <div style={{
              width: 32, height: 32, borderRadius: '50%',
              border: '3px solid rgba(0,0,0,0.08)',
              borderTopColor: 'var(--color-text-secondary)',
              animation: 'spin 0.7s linear infinite',
            }} />
          </div>
        )}
      </div>

      {/* ── Bottom navigation ── */}
      {totalPages > 1 && (
        <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap', justifyContent: 'center' }}>
          <button onClick={() => goTo(1)}               disabled={currentPage === 1}          style={btnStyle(currentPage === 1)}>« First</button>
          <button onClick={() => goTo(currentPage - 1)} disabled={currentPage <= 1}           style={btnStyle(currentPage <= 1)}>‹ Prev</button>
          <button onClick={() => goTo(currentPage + 1)} disabled={currentPage >= totalPages}  style={btnStyle(currentPage >= totalPages)}>Next ›</button>
          <button onClick={() => goTo(totalPages)}      disabled={currentPage === totalPages} style={btnStyle(currentPage === totalPages)}>Last »</button>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
};

function btnStyle(disabled) {
  return {
    padding: '4px 10px', fontSize: 15, borderRadius: 6,
    border: '1px solid var(--color-border-secondary)',
    background: 'var(--color-background-secondary)',
    color: disabled ? 'var(--color-text-tertiary)' : 'var(--color-text-primary)',
    cursor: disabled ? 'default' : 'pointer',
    opacity: disabled ? 0.4 : 1,
    transition: 'opacity 0.15s',
  };
}

export default PdfViewer;