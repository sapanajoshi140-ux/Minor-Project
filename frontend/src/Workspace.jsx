import React, { useState, useEffect, useRef, useCallback } from 'react';

const Workspace = ({
  documentId,
  totalPages: totalPagesProp,
  documentCategory,
  apiUrl,
  authHeaders,
  onBack,
  onAuthError,
}) => {
  const [pages, setPages] = useState([]);
  const [currentPage, setCurrentPage] = useState(0);
  const currentPageRef = useRef(0);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [selectedText, setSelectedText] = useState('');
  const [menuConfig, setMenuConfig] = useState({ show: false, x: 0, y: 0, type: 'word', mode: 'options' });
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [drawerContent, setDrawerContent] = useState({ type: '', text: '', result: '' });
  const [isDrawerLoading, setIsDrawerLoading] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [pdfUrl, setPdfUrl] = useState('');

  // ── Document metadata (live, from GET /document/{id}) ─────────────────────
  const [docMeta, setDocMeta] = useState(null);
  const [totalPages, setTotalPages] = useState(totalPagesProp || 0);

  // ── PDF generation state ───────────────────────────────────────────────────
  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);
  const [pdfGenStatus, setPdfGenStatus] = useState('');
  const [pdfGenMessage, setPdfGenMessage] = useState('');

  // ── Bulk save (PUT /document/{id}/edit) ───────────────────────────────────
  const [dirtyPages, setDirtyPages] = useState(new Set());   // page_numbers with unsaved edits
  const [isBulkSaving, setIsBulkSaving] = useState(false);
  const [bulkSaveStatus, setBulkSaveStatus] = useState('');  // 'success' | 'error' | ''

  // ── Line-streaming state ───────────────────────────────────────────────────
  const [streamingPage, setStreamingPage] = useState(null);  // page_number currently streaming

  const scrollRef = useRef(null);
  const bottomRef = useRef(null);

  const isTextDoc = documentCategory === 'text';
  const hasMore = currentPage < totalPages;

  const getToken = () => localStorage.getItem('access_token') || '';

  const getFreshHeaders = () => ({
    Authorization: `Bearer ${getToken()}`,
  });

  const isValidHeaders = (headers) => {
    if (!headers) return false;
    const auth = headers.Authorization || '';
    return (
      auth.startsWith('Bearer ') &&
      auth !== 'Bearer null' &&
      auth !== 'Bearer undefined' &&
      auth !== 'Bearer '
    );
  };

  // ── GET /document/{id} — fetch/refresh document metadata ──────────────────
  const fetchDocumentMeta = useCallback(async () => {
    const headers = getFreshHeaders();
    if (!isValidHeaders(headers)) { onAuthError(); return; }
    try {
      const res = await fetch(`${apiUrl}/document/${documentId}`, { headers });
      if (res.status === 401) { onAuthError(); return; }
      if (!res.ok) return;
      const data = await res.json();
      setDocMeta(data);
      if (data.total_pages) setTotalPages(data.total_pages);
    } catch (err) {
      console.error('Failed to fetch document metadata:', err);
    }
  }, [documentId, apiUrl, onAuthError]);

  // Fetch metadata on mount so we always have the freshest total_pages / status
  useEffect(() => {
    fetchDocumentMeta();
  }, []);

  // Build PDF URL after mount so token is always fresh
  useEffect(() => {
    if (isTextDoc) {
      const token = getToken();
      setPdfUrl(`${apiUrl}/document/${documentId}/pdf?token=${encodeURIComponent(token)}`);
    }
  }, [isTextDoc, apiUrl, documentId]);

  // ── Save edited page — marks dirty, then persists via single PUT ──────────
  const handleContentChange = async (pageNum, newText) => {
    setPages(prev => {
      const updated = [...prev];
      const idx = updated.findIndex(p => p.page_number === pageNum);
      if (idx !== -1) updated[idx].extracted_text = newText;
      return updated;
    });
    setDirtyPages(prev => new Set(prev).add(pageNum));

    const headers = getFreshHeaders();
    if (!isValidHeaders(headers)) { onAuthError(); return; }

    try {
      const res = await fetch(`${apiUrl}/document/${documentId}/page/${pageNum}`, {
        method: 'PUT',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ extracted_text: newText }),
      });
      if (res.status === 401) { onAuthError(); return; }
      if (res.ok) {
        setDirtyPages(prev => {
          const next = new Set(prev);
          next.delete(pageNum);
          return next;
        });
      }
    } catch (err) {
      console.error('Failed to save edit:', err);
    }
  };

  // ── PUT /document/{id}/edit — bulk save all dirty pages ───────────────────
  const handleBulkSave = useCallback(async () => {
    if (dirtyPages.size === 0) return;
    setIsBulkSaving(true);
    setBulkSaveStatus('');

    const headers = getFreshHeaders();
    if (!isValidHeaders(headers)) { onAuthError(); return; }

    const payload = {
      pages: pages
        .filter(p => dirtyPages.has(p.page_number))
        .map(p => ({ page_number: p.page_number, extracted_text: p.extracted_text || '' })),
    };

    try {
      const res = await fetch(`${apiUrl}/document/${documentId}/edit`, {
        method: 'PUT',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.status === 401) { onAuthError(); return; }
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Bulk save failed.');

      // Clear only the pages the backend confirmed as updated
      if (data.updated_pages?.length) {
        setDirtyPages(prev => {
          const next = new Set(prev);
          data.updated_pages.forEach(n => next.delete(n));
          return next;
        });
      }
      setBulkSaveStatus('success');
    } catch (err) {
      console.error('Bulk save failed:', err);
      setBulkSaveStatus('error');
    } finally {
      setIsBulkSaving(false);
      setTimeout(() => setBulkSaveStatus(''), 3000);
    }
  }, [dirtyPages, pages, documentId, apiUrl, onAuthError]);

  // ── POST /documents/{id}/generate-pdf ─────────────────────────────────────
  const handleGeneratePdf = async () => {
    setIsGeneratingPdf(true);
    setPdfGenStatus('');
    setPdfGenMessage('');

    const headers = getFreshHeaders();
    if (!isValidHeaders(headers)) { onAuthError(); return; }

    try {
      const res = await fetch(`${apiUrl}/documents/${documentId}/generate-pdf`, {
        method: 'POST',
        headers,
      });
      if (res.status === 401) { onAuthError(); return; }
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'PDF generation failed.');

      setPdfGenStatus('success');
      setPdfGenMessage(data.message || 'PDF generated successfully.');

      const token = getToken();
      setPdfUrl(
        `${apiUrl}/document/${documentId}/pdf?token=${encodeURIComponent(token)}&t=${Date.now()}`
      );
    } catch (err) {
      setPdfGenStatus('error');
      setPdfGenMessage(err.message || 'Failed to generate PDF.');
    } finally {
      setIsGeneratingPdf(false);
      setTimeout(() => { setPdfGenStatus(''); setPdfGenMessage(''); }, 4000);
    }
  };

  // ── GET /document/{id}/page/{n}/lines — NDJSON streaming ──────────────────
  // Streams a page line-by-line, appending text progressively for fast display
  const fetchPageStreaming = useCallback(async (pageNum) => {
    const headers = getFreshHeaders();
    if (!isValidHeaders(headers)) { onAuthError(); return null; }

    setStreamingPage(pageNum);

    // Insert a placeholder so the page card appears immediately
    setPages(prev => {
      if (prev.find(p => p.page_number === pageNum)) return prev;
      return [...prev, { page_number: pageNum, extracted_text: '', _streaming: true }];
    });

    try {
      const res = await fetch(
        `${apiUrl}/document/${documentId}/page/${pageNum}/lines`,
        { headers }
      );
      if (res.status === 401) { onAuthError(); return null; }

      // Fall back to single-page fetch if the endpoint isn't available
      if (!res.ok) {
        setPages(prev => prev.filter(p => p.page_number !== pageNum));
        setStreamingPage(null);
        return null; // signal caller to use fetchPage instead
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete trailing line

        for (const raw of lines) {
          const trimmed = raw.trim();
          if (!trimmed) continue;
          try {
            const lineObj = JSON.parse(trimmed);
            if (lineObj.text) {
              setPages(prev =>
                prev.map(p =>
                  p.page_number === pageNum
                    ? { ...p, extracted_text: (p.extracted_text || '') + lineObj.text + '\n' }
                    : p
                )
              );
            }
          } catch {
            // malformed JSON line — skip
          }
        }
      }

      // Mark streaming done
      setPages(prev =>
        prev.map(p => p.page_number === pageNum ? { ...p, _streaming: false } : p)
      );
      setStreamingPage(null);
      return true;
    } catch (err) {
      console.error(`Streaming failed for page ${pageNum}:`, err);
      setPages(prev => prev.filter(p => p.page_number !== pageNum));
      setStreamingPage(null);
      return null;
    }
  }, [documentId, apiUrl, onAuthError]);

  // ── GET /document/{id}/page/{n} — single page fallback ────────────────────
  const fetchPage = useCallback(async (pageNum) => {
    const headers = getFreshHeaders();
    if (!isValidHeaders(headers)) { onAuthError(); return null; }
    const res = await fetch(
      `${apiUrl}/document/${documentId}/page/${pageNum}`,
      { headers }
    );
    if (res.status === 401) { onAuthError(); return null; }
    if (!res.ok) throw new Error(`Failed to fetch page ${pageNum}`);
    return await res.json();
  }, [documentId, apiUrl, onAuthError]);

  // ── GET /document/{id}/pages — batch prefetch next N pages ────────────────
  // Called after the first page loads to prefetch the next batch in one request
  const prefetchPageBatch = useCallback(async (afterPage, limit = 5) => {
    const headers = getFreshHeaders();
    if (!isValidHeaders(headers)) return;

    // Calculate which batch number contains afterPage + 1
    const nextPageNum = afterPage + 1;
    if (nextPageNum > totalPages) return;

    const batchNum = Math.ceil(nextPageNum / limit);

    try {
      const res = await fetch(
        `${apiUrl}/document/${documentId}/pages?page=${batchNum}&limit=${limit}`,
        { headers }
      );
      if (!res.ok || res.status === 401) return;
      const data = await res.json();

      if (data.pages?.length) {
        setPages(prev => {
          const existingNums = new Set(prev.map(p => p.page_number));
          const newPages = data.pages.filter(p => !existingNums.has(p.page_number));
          return newPages.length ? [...prev, ...newPages] : prev;
        });
        // Advance currentPage ref to the last prefetched page
        const lastPrefetched = data.pages[data.pages.length - 1].page_number;
        if (lastPrefetched > currentPageRef.current) {
          currentPageRef.current = lastPrefetched;
          setCurrentPage(lastPrefetched);
        }
      }
    } catch (err) {
      console.error('Batch prefetch failed:', err);
    }
  }, [documentId, apiUrl, totalPages]);

  // ── Load next page: stream first, fall back to single fetch ───────────────
  const loadNextPage = useCallback(async () => {
    if (isLoadingMore || currentPageRef.current >= totalPages) return;
    setIsLoadingMore(true);
    try {
      const nextPage = currentPageRef.current + 1;

      // 1. Try NDJSON streaming
      const streamed = await fetchPageStreaming(nextPage);

      if (streamed === null) {
        // 2. Streaming not available — fall back to single page fetch
        const pageData = await fetchPage(nextPage);
        if (pageData) {
          setPages(prev => {
            if (prev.find(p => p.page_number === pageData.page_number)) return prev;
            return [...prev, pageData];
          });
        }
      }

      currentPageRef.current = nextPage;
      setCurrentPage(nextPage);

      // 3. After page 1, kick off a batch prefetch for the next few pages
      if (nextPage === 1) {
        prefetchPageBatch(nextPage);
      }
    } catch (err) {
      console.error('Failed to load page:', err);
    }
    setIsLoadingMore(false);
  }, [isLoadingMore, totalPages, fetchPageStreaming, fetchPage, prefetchPageBatch]);

  // Load first page on mount (scanned docs only)
  useEffect(() => {
    if (!isTextDoc) loadNextPage();
  }, []);

  // IntersectionObserver — only attach after page 1 is loaded
  useEffect(() => {
    if (!bottomRef.current || isTextDoc || currentPage === 0) return;
    const observer = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) loadNextPage(); },
      { threshold: 0.1 }
    );
    observer.observe(bottomRef.current);
    return () => observer.disconnect();
  }, [loadNextPage, isTextDoc, currentPage]);

  // Stop speech when leaving workspace
  useEffect(() => {
    return () => window.speechSynthesis?.cancel();
  }, []);

  // ── Text selection → floating menu ─────────────────────────────────────────
  const handleMouseUp = (e) => {
    if (e.target.closest('.floating-menu')) return;
    const selection = window.getSelection();
    const selectionText = selection?.toString().trim();

    if (!selectionText) {
      setMenuConfig(prev => ({ ...prev, show: false }));
      return;
    }

    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    const wordCount = selectionText.split(/\s+/).length;
    setSelectedText(selectionText);

    let menuType = 'word';
    if (wordCount > 1 && wordCount <= 20) menuType = 'short';
    if (wordCount > 20) menuType = 'paragraph';

    setMenuConfig({
      show: true,
      x: rect.left + rect.width / 2,
      y: rect.top - 60,
      type: menuType,
      mode: 'options',
    });
  };

  // ── Word definition ─────────────────────────────────────────────────────────
  const handleMeaningClick = async (e) => {
    e.stopPropagation();
    setMenuConfig(prev => ({ ...prev, show: false }));
    setDrawerContent({ type: 'meaning', text: selectedText, result: '' });
    setIsDrawerLoading(true);
    setIsDrawerOpen(true);

    const headers = getFreshHeaders();
    if (!isValidHeaders(headers)) { onAuthError(); return; }

    try {
      const res = await fetch(`${apiUrl}/ai/meaning`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ word: selectedText }),
      });
      if (res.status === 401) { onAuthError(); return; }
      const data = await res.json();
      setDrawerContent(prev => ({
        ...prev,
        result: data.meaning || data.detail || 'No definition found.',
      }));
    } catch {
      setDrawerContent(prev => ({ ...prev, result: 'Failed to fetch definition. Please try again.' }));
    } finally {
      setIsDrawerLoading(false);
    }
  };

  // ── Summarize selection ─────────────────────────────────────────────────────
  const handleSummaryClick = async (e) => {
    e.stopPropagation();
    setMenuConfig(prev => ({ ...prev, show: false }));
    setDrawerContent({ type: 'summary', text: selectedText, result: '' });
    setIsDrawerLoading(true);
    setIsDrawerOpen(true);

    const headers = getFreshHeaders();
    if (!isValidHeaders(headers)) { onAuthError(); return; }

    try {
      const res = await fetch(`${apiUrl}/ai/summarize`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: selectedText }),
      });
      if (res.status === 401) { onAuthError(); return; }
      const data = await res.json();
      setDrawerContent(prev => ({
        ...prev,
        result: data.summary || data.detail || 'No summary generated.',
      }));
    } catch {
      setDrawerContent(prev => ({ ...prev, result: 'Failed to generate summary. Please try again.' }));
    } finally {
      setIsDrawerLoading(false);
    }
  };

  // ── Text-to-speech ──────────────────────────────────────────────────────────
  const handleTTS = (e) => {
    e.stopPropagation();
    setMenuConfig(prev => ({ ...prev, show: false }));

    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      return;
    }

    const utterance = new SpeechSynthesisUtterance(selectedText);
    utterance.rate = 0.95;
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    window.speechSynthesis.speak(utterance);
  };

  // ── Delete document ─────────────────────────────────────────────────────────
  const handleDelete = async () => {
    if (!window.confirm('Delete this document? This cannot be undone.')) return;

    const headers = getFreshHeaders();
    if (!isValidHeaders(headers)) { onAuthError(); return; }

    try {
      const res = await fetch(`${apiUrl}/document/${documentId}`, {
        method: 'DELETE',
        headers,
      });
      if (res.status === 401) { onAuthError(); return; }
      onBack();
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  // ── Dirty-page indicator label ─────────────────────────────────────────────
  const dirtyCount = dirtyPages.size;

  return (
    <div
      className="flex h-screen bg-[#F0F2F5] relative overflow-hidden font-sans"
      onMouseUp={handleMouseUp}
    >
      {/* ── FLOATING MENU ── */}
      {menuConfig.show && (
        <div
          className="floating-menu fixed z-50 bg-gray-900 text-white rounded-lg shadow-xl border border-gray-800 flex flex-col overflow-hidden"
          style={{ top: `${menuConfig.y}px`, left: `${menuConfig.x}px`, transform: 'translateX(-50%)' }}
          onMouseUp={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div className="flex divide-x divide-gray-700 whitespace-nowrap">
            {menuConfig.type === 'word' && (
              <>
                <button onClick={handleMeaningClick} className="px-4 py-2 text-xs font-semibold hover:bg-gray-800 transition">
                  Meaning
                </button>
                <button onClick={handleTTS} className="px-4 py-2 text-xs font-semibold hover:bg-gray-800 transition">
                  {isSpeaking ? '⏹' : '🔊'}
                </button>
              </>
            )}
            {menuConfig.type === 'short' && (
              <button onClick={handleTTS} className="px-5 py-2 text-xs font-semibold hover:bg-gray-800 transition">
                {isSpeaking ? 'Stop ⏹' : 'Speak 🔊'}
              </button>
            )}
            {menuConfig.type === 'paragraph' && (
              <>
                <button onClick={handleSummaryClick} className="px-4 py-2 text-xs font-semibold hover:bg-gray-800 flex items-center gap-1 transition">
                  ✨ Summarize
                </button>
                <button onClick={handleTTS} className="px-4 py-2 text-xs font-semibold hover:bg-gray-800 transition">
                  {isSpeaking ? 'Stop ⏹' : 'Read 🔊'}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── SIDEBAR ── */}
      <aside className="w-16 bg-white border-r border-gray-200 flex flex-col items-center py-6 shrink-0 z-20">

        {/* Back */}
        <button
          onClick={onBack}
          className="p-3 mb-4 text-gray-500 hover:bg-gray-100 hover:text-gray-900 rounded-xl transition-all"
          title="Back to Dashboard"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
        </button>

        <div className="w-8 h-px bg-gray-200 my-2" />

        {/* Bulk save — scanned docs only, shown when there are unsaved edits */}
        {!isTextDoc && (
          <div className="relative">
            <button
              onClick={handleBulkSave}
              disabled={isBulkSaving || dirtyCount === 0}
              className={`p-3 rounded-xl transition-all ${
                dirtyCount > 0
                  ? 'text-blue-500 hover:bg-blue-50'
                  : 'text-gray-300 cursor-default'
              } disabled:opacity-50`}
              title={dirtyCount > 0 ? `Save all ${dirtyCount} unsaved page(s)` : 'No unsaved changes'}
            >
              {isBulkSaving ? (
                <div className="w-5 h-5 border-2 border-blue-300 border-t-blue-500 rounded-full animate-spin" />
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                </svg>
              )}
            </button>
            {/* Dirty-page badge */}
            {dirtyCount > 0 && !isBulkSaving && (
              <span className="absolute -top-1 -right-1 w-4 h-4 bg-blue-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
                {dirtyCount}
              </span>
            )}
          </div>
        )}

        {/* Rebuild PDF — scanned docs only */}
        {!isTextDoc && (
          <button
            onClick={handleGeneratePdf}
            disabled={isGeneratingPdf}
            className="p-3 text-gray-400 hover:bg-blue-50 hover:text-blue-500 rounded-xl transition-all disabled:opacity-50"
            title="Rebuild PDF from edited text"
          >
            {isGeneratingPdf ? (
              <div className="w-5 h-5 border-2 border-blue-300 border-t-blue-500 rounded-full animate-spin" />
            ) : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            )}
          </button>
        )}

        {/* Delete */}
        <button
          onClick={handleDelete}
          className="p-3 mt-auto text-gray-400 hover:bg-red-50 hover:text-red-500 rounded-xl transition-all"
          title="Delete document"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      </aside>

      {/* ── MAIN LAYOUT ── */}
      <main className="flex-1 flex flex-col h-screen relative">

        {/* TOP BAR */}
        <header className="absolute top-0 left-0 right-0 z-10 px-8 py-4 pointer-events-none flex justify-between items-center">
          <div className="flex items-center gap-2 pointer-events-auto">
            {documentCategory && (
              <div className="bg-white/90 backdrop-blur-sm border border-gray-200 shadow-sm px-3 py-1.5 rounded-full">
                <span className="text-xs font-medium text-gray-500">
                  {documentCategory === 'text' ? '📄 Digital document' : '🔍 Scanned document'}
                </span>
              </div>
            )}
            {/* Document metadata badge — processing status */}
            {docMeta && docMeta.processing_status && docMeta.processing_status !== 'completed' && (
              <div className="bg-amber-50 border border-amber-200 shadow-sm px-3 py-1.5 rounded-full">
                <span className="text-xs font-medium text-amber-600 capitalize">
                  {docMeta.processing_status}
                </span>
              </div>
            )}
          </div>

          <div className="bg-white/90 backdrop-blur-sm border border-gray-200 shadow-sm px-4 py-1.5 rounded-full pointer-events-auto flex items-center gap-3 ml-auto">
            {!isTextDoc && (
              <span className="text-xs font-medium text-gray-600">
                Page {currentPage} of {totalPages}
              </span>
            )}
            {/* Streaming indicator */}
            {streamingPage && (
              <span className="text-xs text-blue-500 font-medium">
                Streaming p.{streamingPage}…
              </span>
            )}
            {isLoadingMore && !streamingPage && (
              <div className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            )}
          </div>
        </header>

        {/* BULK SAVE STATUS TOAST */}
        {bulkSaveStatus && (
          <div
            className={`absolute top-16 left-1/2 -translate-x-1/2 z-20 px-4 py-2 rounded-full text-xs font-medium shadow-lg ${
              bulkSaveStatus === 'success'
                ? 'bg-green-100 border border-green-200 text-green-700'
                : 'bg-red-100 border border-red-200 text-red-700'
            }`}
          >
            {bulkSaveStatus === 'success' ? '✓ All changes saved' : '✕ Save failed — try again'}
          </div>
        )}

        {/* PDF GEN STATUS TOAST */}
        {pdfGenStatus && (
          <div
            className={`absolute top-16 left-1/2 -translate-x-1/2 z-20 px-4 py-2 rounded-full text-xs font-medium shadow-lg ${
              pdfGenStatus === 'success'
                ? 'bg-green-100 border border-green-200 text-green-700'
                : 'bg-red-100 border border-red-200 text-red-700'
            }`}
          >
            {pdfGenStatus === 'success' ? '✓' : '✕'} {pdfGenMessage}
          </div>
        )}

        {/* SCROLLABLE CONTENT AREA */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto overflow-x-hidden pt-16 pb-20 scroll-smooth"
        >
          {isTextDoc ? (
            pdfUrl ? (
              <div className="flex flex-col items-center h-full px-4">
                <iframe
                  src={`${pdfUrl}#toolbar=1`}
                  title="Document PDF viewer"
                  className="w-full max-w-4xl flex-1 min-h-[80vh] border border-gray-200 rounded-xl shadow-sm bg-white"
                />
              </div>
            ) : (
              <div className="flex items-center justify-center h-full">
                <div className="w-8 h-8 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
              </div>
            )
          ) : (
            <div className="flex flex-col items-center space-y-8">
              {pages.map((page) => (
                <div key={page.page_number} className="relative group transition-transform duration-300">
                  <div className="absolute -left-12 top-0 text-xs text-gray-400 font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                    p.{page.page_number}
                  </div>
                  {/* Unsaved indicator dot */}
                  {dirtyPages.has(page.page_number) && (
                    <div className="absolute -right-3 top-3 w-2 h-2 bg-blue-400 rounded-full" title="Unsaved changes" />
                  )}
                  <div className="bg-white w-[210mm] min-h-[297mm] shadow-sm hover:shadow-md transition-shadow duration-300 border border-gray-200/60 mx-auto relative">
                    <div
                      contentEditable="true"
                      suppressContentEditableWarning={true}
                      className="w-full h-full p-[25mm] outline-none text-[12pt] leading-[1.8] text-gray-800 font-serif text-justify selection:bg-blue-100 selection:text-blue-900 whitespace-pre-wrap empty:before:content-['Start_typing...'] empty:before:text-gray-300"
                      onBlur={(e) => handleContentChange(page.page_number, e.currentTarget.innerText)}
                    >
                      {page.extracted_text || ''}
                    </div>
                    {/* Streaming pulse overlay */}
                    {page._streaming && (
                      <div className="absolute bottom-4 right-4 flex items-center gap-1.5 bg-white/80 backdrop-blur-sm px-2 py-1 rounded-full border border-gray-200">
                        <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
                        <span className="text-[10px] text-gray-400 font-medium">Loading…</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {isLoadingMore && (
                <div className="bg-white w-[210mm] h-[297mm] shadow-sm border border-gray-200 mx-auto p-[25mm] space-y-6 animate-pulse">
                  <div className="h-4 bg-gray-100 rounded w-full" />
                  <div className="h-4 bg-gray-100 rounded w-full" />
                  <div className="h-4 bg-gray-100 rounded w-5/6" />
                  <div className="h-4 bg-gray-100 rounded w-full" />
                  <div className="h-32 bg-gray-50 rounded w-full mt-8" />
                </div>
              )}

              {!hasMore && pages.length > 0 && (
                <div className="text-center py-8">
                  <span className="bg-gray-200 text-gray-600 text-xs px-3 py-1 rounded-full font-medium">
                    End of Document
                  </span>
                </div>
              )}

              <div ref={bottomRef} className="h-4" />
            </div>
          )}
        </div>
      </main>

      {/* ── SUMMARY / MEANING DRAWER ── */}
      <div
        className={`fixed top-0 right-0 h-full w-[450px] bg-white shadow-2xl border-l border-gray-100 z-[200] transition-transform duration-500 flex flex-col ${
          isDrawerOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="p-6 border-b border-gray-100 shrink-0 flex justify-between items-center bg-white/50 backdrop-blur-md">
          <div className="flex items-center gap-2">
            <span className="text-xl">{drawerContent.type === 'summary' ? '✨' : '📖'}</span>
            <h2 className="text-lg font-bold text-gray-900">
              {drawerContent.type === 'summary' ? 'AI Summary' : 'Definition'}
            </h2>
          </div>
          <button
            onClick={() => setIsDrawerOpen(false)}
            className="text-gray-400 hover:text-gray-900 transition-colors p-2 hover:bg-gray-100 rounded-full"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 bg-gray-50/30">
          <div className="bg-blue-50/50 p-6 rounded-2xl border border-blue-100">
            <h3 className="text-xs font-bold text-blue-800 uppercase tracking-wider mb-3">Selected Text</h3>
            <p className="text-gray-600 italic mb-6 text-sm border-l-2 border-blue-200 pl-3 line-clamp-4">
              "{drawerContent.text}"
            </p>
            <h3 className="text-xs font-bold text-blue-800 uppercase tracking-wider mb-2">
              {drawerContent.type === 'summary' ? 'Summary' : 'Meaning'}
            </h3>
            {isDrawerLoading ? (
              <div className="space-y-3 animate-pulse">
                <div className="h-4 bg-blue-100 rounded w-full" />
                <div className="h-4 bg-blue-100 rounded w-5/6" />
                <div className="h-4 bg-blue-100 rounded w-4/6" />
              </div>
            ) : (
              <p className="text-base text-gray-800 leading-relaxed font-medium">
                {drawerContent.result}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Workspace;