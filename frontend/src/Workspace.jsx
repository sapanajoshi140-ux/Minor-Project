import React, { useState, useEffect, useRef, useCallback } from 'react';
import PdfViewer   from './PdfViewer';
import ChatPanel   from './ChatPanel';
import { getFreshHeaders, isValidHeaders, getToken } from './Docutils';
import { Spinner, Toast, EndOfDocument, menuBtnStyle } from './Sharedui';
import { useBottomInfiniteScroll } from './Hooks';

// ── Note component — single unified floating note section ────────────────────
import { CenteredNoteButton, FloatingNotePanel } from './NoteSection';

const DOC_API_URL = import.meta.env.VITE_DOCUMENT_API_URL || 'http://localhost:8001';
const RAG_API_URL = import.meta.env.VITE_RAG_API_URL      || 'http://localhost:8001';

const getRagHeaders = () => ({
  'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`,
});

// ─────────────────────────────────────────────────────────────────────────────
// Workspace
// ─────────────────────────────────────────────────────────────────────────────
const Workspace = ({
  documentId,
  totalPages: totalPagesProp,
  documentCategory,
  documentName,
  apiUrl,
  authHeaders,
  onBack,
  onAuthError,
  sessionId,
}) => {
  const BASE = apiUrl || DOC_API_URL;

  // ── Refs ──────────────────────────────────────────────────────────────────
  const startTimeRef       = useRef(Date.now());
  const activeSecsRef      = useRef(0);
  const lastActivityRef    = useRef(Date.now());
  const activityTimerRef   = useRef(null);
  const heartbeatTimerRef  = useRef(null);
  const INACTIVITY_TIMEOUT = 5 * 60 * 1000;
  const pagesRef           = useRef([]);
  const pageRefs           = useRef({});

  // ── 1. guardedHeaders — defined FIRST, used everywhere ───────────────────
  const guardedHeaders = useCallback(() => {
    const h = getFreshHeaders();
    if (!isValidHeaders(h)) { onAuthError(); return null; }
    return h;
  }, [onAuthError]);

  // ── 2. tickActiveTime ─────────────────────────────────────────────────────
  const tickActiveTime = useCallback(() => {
    const now = Date.now();
    const sinceActivity = now - lastActivityRef.current;
    if (sinceActivity < INACTIVITY_TIMEOUT) {
      activeSecsRef.current += 30;
    }
  }, []);

  const recordActivity = useCallback(() => {
    lastActivityRef.current = Date.now();
  }, []);

  // ── 3. handleBack ─────────────────────────────────────────────────────────
  const handleBack = useCallback(() => {
    tickActiveTime();
    onBack(activeSecsRef.current);
  }, [onBack, tickActiveTime]);

  // ── 4. Heartbeat effect ───────────────────────────────────────────────────
  useEffect(() => {
    const events = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'];
    events.forEach(e => window.addEventListener(e, recordActivity, { passive: true }));

    heartbeatTimerRef.current = setInterval(async () => {
      tickActiveTime();
      if (!sessionId) return;
      const headers = guardedHeaders();
      if (!headers) return;
      try {
        await fetch(`${BASE}/reading-session/heartbeat`, {
          method: 'POST',
          headers: { ...headers, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            active_seconds: activeSecsRef.current,
          }),
        });
      } catch (err) {
        console.error('Heartbeat failed:', err);
      }
    }, 30_000);

    return () => {
      events.forEach(e => window.removeEventListener(e, recordActivity));
      clearInterval(heartbeatTimerRef.current);
    };
  }, [sessionId, BASE, guardedHeaders, tickActiveTime, recordActivity]);

  // ── 5. popstate effect ────────────────────────────────────────────────────
  useEffect(() => {
    const onPopState = () => {
      tickActiveTime();
      onBack(activeSecsRef.current);
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, [onBack, tickActiveTime]);

  // ── State ─────────────────────────────────────────────────────────────────
  const [pages,           setPages]           = useState([]);
  const [currentPage,     setCurrentPage]     = useState(0);
  const currentPageRef                        = useRef(0);
  const [isLoadingMore,   setIsLoadingMore]   = useState(false);
  const [selectedText,    setSelectedText]    = useState('');
  const [menuConfig,      setMenuConfig]      = useState({ show: false, x: 0, y: 0, type: 'word' });
  const [isSpeaking,      setIsSpeaking]      = useState(false);
  const [pdfUrl,          setPdfUrl]          = useState('');
  const [phonetic,        setPhonetic]        = useState('');

  const [meaningPopup, setMeaningPopup] = useState({ show: false, x: 0, y: 0, text: '', result: '', loading: false });

  const [docMeta,    setDocMeta]    = useState(null);
  const [totalPages, setTotalPages] = useState(totalPagesProp || 0);

  const [isGeneratingPdf, setIsGeneratingPdf] = useState(false);
  const [pdfGenStatus,    setPdfGenStatus]     = useState('');
  const [pdfGenMessage,   setPdfGenMessage]    = useState('');

  // ── PDF ready modal state ─────────────────────────────────────────────────
  const [pdfReadyModal,   setPdfReadyModal]   = useState(false);
  const [generatedPdfUrl, setGeneratedPdfUrl] = useState('');

  const [dirtyPages,     setDirtyPages]     = useState(new Set());
  const [isBulkSaving,   setIsBulkSaving]   = useState(false);
  const [bulkSaveStatus, setBulkSaveStatus] = useState('');

  const [streamingPage, setStreamingPage] = useState(null);
  const streamAbortRef = useRef(null);

  const [injectedMessage, setInjectedMessage] = useState(null);
  const [lengthPicker,    setLengthPicker]    = useState(false);
  const [pageLoadError,   setPageLoadError]   = useState(false);

  const [pageNotes,       setPageNotes]       = useState({});
  const [openNotePageNum, setOpenNotePageNum] = useState(null);

  const scrollRef = useRef(null);

  const isTextDoc = documentCategory === 'text';
  const hasMore   = currentPage < totalPages;

  // ── Mobile: which panel is active on small screens ───────────────────────
  // 'doc' = document view, 'chat' = chat panel
  const [mobileTab, setMobileTab] = useState('doc');
  // Detect mobile
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  // Chat panel width: 520 on desktop, full width on mobile
  const CHAT_WIDTH = isMobile ? window.innerWidth : 520;

  // ── OCR Formatting state ──────────────────────────────────────────────────
  const [fmtSummary, setFmtSummary] = useState(null);
  const [fmtPolling, setFmtPolling] = useState(false);
  const fmtPollRef = useRef(null);
  const [showFmtDone, setShowFmtDone] = useState(false);
  const fmtWasAlreadyDoneRef = useRef(false);

  useEffect(() => {
    if (!fmtSummary?.all_done) return;
    if (fmtWasAlreadyDoneRef.current) return;
    fmtWasAlreadyDoneRef.current = true;
    if (!fmtPolling) return;
    setShowFmtDone(true);
    const id = setTimeout(() => setShowFmtDone(false), 4000);
    return () => clearTimeout(id);
  }, [fmtSummary?.all_done, fmtPolling]);

  const pollFormattingStatusRef = useRef(null);

  // ── saveNote ──────────────────────────────────────────────────────────────
  const saveNote = useCallback(async (pageNum, text) => {
    const headers = guardedHeaders();
    if (!headers) return;
    const res = await fetch(`${BASE}/documents/${documentId}/pages/${pageNum}/note`, {
      method: 'PUT',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ note_text: text }),
    });
    if (res.status === 401) { onAuthError(); throw new Error('Unauthorized'); }
    if (!res.ok) throw new Error('Failed to save note');
  }, [BASE, documentId, guardedHeaders, onAuthError]);

  // ── Document metadata ─────────────────────────────────────────────────────
  const fetchDocumentMeta = useCallback(async () => {
    const headers = guardedHeaders();
    if (!headers) return;
    try {
      const res = await fetch(`${BASE}/document/${documentId}`, { headers });
      if (res.status === 401) { onAuthError(); return; }
      if (!res.ok) return;
      const data = await res.json();
      setDocMeta(data);
      if (data.total_pages) setTotalPages(data.total_pages);
    } catch (err) {
      console.error('Failed to fetch document metadata:', err);
    }
  }, [documentId, BASE, guardedHeaders, onAuthError]);

  // ── Unified view ──────────────────────────────────────────────────────────
  const fetchDocumentView = useCallback(async () => {
    const headers = guardedHeaders();
    if (!headers) return false;
    try {
      const res = await fetch(`${BASE}/documents/${documentId}/view`, { headers });
      if (res.status === 401) { onAuthError(); return false; }
      if (!res.ok) return false;
      const data = await res.json();

      setDocMeta({
        filename:          data.filename,
        total_pages:       data.total_pages,
        document_category: data.document_category,
        processing_status: data.processing_status,
      });
      if (data.total_pages) setTotalPages(data.total_pages);

      if (data.formatting_summary) {
        setFmtSummary(data.formatting_summary);
        if (!data.formatting_summary.all_done) {
          clearInterval(fmtPollRef.current);
          fmtPollRef.current = setInterval(
            () => pollFormattingStatusRef.current?.(),
            4000,
          );
          setFmtPolling(true);
        } else {
          clearInterval(fmtPollRef.current);
          setFmtPolling(false);
        }
      }

      if (data.pdf_url) {
        const token = getToken();
        setPdfUrl(`${BASE}${data.pdf_url}?token=${encodeURIComponent(token)}`);
        setGeneratedPdfUrl(`${BASE}${data.pdf_url}?token=${encodeURIComponent(token)}`);
      }

      if (data.ocr_lines?.length) {
        const pageMap = {};
        for (const line of data.ocr_lines) {
          const pn = line.page_number;
          if (!pageMap[pn]) {
            pageMap[pn] = {
              page_number:       pn,
              extracted_text:    '',
              formatting_status: line.formatting_status,
            };
          }
          pageMap[pn].extracted_text += line.text + '\n';
        }
        const pageList = Object.values(pageMap).sort((a, b) => a.page_number - b.page_number);
        setPages(pageList);

        const lastPage = pageList[pageList.length - 1].page_number;
        currentPageRef.current = lastPage;
        setCurrentPage(lastPage);
        return true;
      }

      return false;
    } catch (err) {
      console.error('Failed to fetch document view:', err);
      return false;
    }
  }, [BASE, documentId, guardedHeaders, onAuthError]);

  // ── OCR formatting status polling ─────────────────────────────────────────
  const pollFormattingStatus = useCallback(async () => {
    const headers = guardedHeaders();
    if (!headers) return;
    try {
      const res = await fetch(`${BASE}/document/${documentId}/formatting-status`, { headers });
      if (!res.ok) return;
      const data = await res.json();
      setFmtSummary(data.summary);

      if (data.summary.all_done) {
        setFmtPolling(false);
        clearInterval(fmtPollRef.current);
        fetchDocumentView();
      }
    } catch (err) {
      console.error('Formatting status poll failed:', err);
    }
  }, [BASE, documentId, guardedHeaders, fetchDocumentView]);

  useEffect(() => {
    pollFormattingStatusRef.current = pollFormattingStatus;
  }, [pollFormattingStatus]);

  useEffect(() => {
    return () => clearInterval(fmtPollRef.current);
  }, []);

  useEffect(() => { pagesRef.current = pages; }, [pages]);

  useEffect(() => {
    if (isTextDoc) return;
    const observers = [];

    pages.forEach((page) => {
      const el = pageRefs.current[page.page_number];
      if (!el) return;

      const obs = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) {
            setCurrentPage(page.page_number);
          }
        },
        { threshold: 0.3 }
      );
      obs.observe(el);
      observers.push(obs);
    });

    return () => observers.forEach(obs => obs.disconnect());
  }, [pages, isTextDoc]);

  // ── Load notes ────────────────────────────────────────────────────────────
  useEffect(() => {
    const loadNotes = async () => {
      const headers = guardedHeaders();
      if (!headers) return;
      try {
        const res = await fetch(`${BASE}/documents/${documentId}/notes`, { headers });
        if (!res.ok) return;
        const data = await res.json();
        const map = {};
        (data.notes || []).forEach(n => { map[n.page_number] = n.note_text; });
        setPageNotes(map);
      } catch (err) {
        console.error('Failed to load notes:', err);
      }
    };
    loadNotes();
  }, [documentId, BASE, guardedHeaders]);

  // ── Text document: PDF URL ────────────────────────────────────────────────
  useEffect(() => {
    if (isTextDoc) {
      const token = getToken();
      setPdfUrl(`${BASE}/document/${documentId}/pdf?token=${encodeURIComponent(token)}`);
    }
  }, [isTextDoc, BASE, documentId]);

  useEffect(() => () => {
    streamAbortRef.current?.abort();
    window.speechSynthesis?.cancel();
  }, []);

  // ── Auto-dismiss toasts ───────────────────────────────────────────────────
  useEffect(() => {
    if (!bulkSaveStatus) return;
    const id = setTimeout(() => setBulkSaveStatus(''), 3000);
    return () => clearTimeout(id);
  }, [bulkSaveStatus]);

  useEffect(() => {
    if (!pdfGenStatus) return;
    const id = setTimeout(() => { setPdfGenStatus(''); setPdfGenMessage(''); }, 4000);
  }, [pdfGenStatus]);

  // ── Save single page ──────────────────────────────────────────────────────
  const handleContentChange = (pageNum, newText) => {
    setPages(prev => prev.map(p => p.page_number === pageNum ? { ...p, extracted_text: newText } : p));
    setDirtyPages(prev => new Set(prev).add(pageNum));
  };

  // ── Bulk save ─────────────────────────────────────────────────────────────
  const handleBulkSave = useCallback(async () => {
    if (dirtyPages.size === 0) return;
    setIsBulkSaving(true);

    const headers = guardedHeaders();
    if (!headers) { setIsBulkSaving(false); return; }

    const payload = {
      pages: pages
        .filter(p => dirtyPages.has(p.page_number))
        .map(p => ({ page_number: p.page_number, extracted_text: p.extracted_text || '' })),
    };

    try {
      const res = await fetch(`${BASE}/document/${documentId}/edit`, {
        method: 'PUT',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.status === 401) { onAuthError(); return; }
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Bulk save failed.');

      if (data.updated_pages?.length) {
        setDirtyPages(prev => {
          const n = new Set(prev);
          data.updated_pages.forEach(num => n.delete(num));
          return n;
        });
      }
      setBulkSaveStatus('success');
    } catch (err) {
      console.error('Bulk save failed:', err);
      setBulkSaveStatus('error');
    } finally {
      setIsBulkSaving(false);
    }
  }, [dirtyPages, pages, documentId, BASE, guardedHeaders, onAuthError]);

  // ── Generate PDF ──────────────────────────────────────────────────────────
  const handleGeneratePdf = async () => {
    setIsGeneratingPdf(true);
    const headers = guardedHeaders();
    if (!headers) { setIsGeneratingPdf(false); return; }

    try {
      const res = await fetch(`${BASE}/documents/${documentId}/generate-pdf`, {
        method: 'POST',
        headers,
      });
      if (res.status === 401) { onAuthError(); return; }
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'PDF generation failed.');

      const token = getToken();
      const newPdfUrl = `${BASE}/document/${documentId}/pdf?token=${encodeURIComponent(token)}&t=${Date.now()}`;

      setPdfUrl(newPdfUrl);
      setGeneratedPdfUrl(newPdfUrl);
      setPdfReadyModal(true);
      setPdfGenStatus('success');
      setPdfGenMessage(data.message || 'PDF generated successfully.');
    } catch (err) {
      setPdfGenStatus('error');
      setPdfGenMessage(err.message || 'Failed to generate PDF.');
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  // ── Reformat ──────────────────────────────────────────────────────────────
  const handleReformat = async () => {
    const headers = guardedHeaders();
    if (!headers) return;
    try {
      await fetch(`${BASE}/document/${documentId}/reformat`, { method: 'POST', headers });
      setFmtPolling(true);
      clearInterval(fmtPollRef.current);
      fmtPollRef.current = setInterval(
        () => pollFormattingStatusRef.current?.(),
        4000,
      );
    } catch (err) {
      console.error('Reformat request failed:', err);
    }
  };

  // ── NDJSON streaming ──────────────────────────────────────────────────────
  const fetchPageStreaming = useCallback(async (pageNum) => {
    const alreadyLoaded = pagesRef.current.find(
      p => p.page_number === pageNum && p.extracted_text?.trim()
    );
    if (alreadyLoaded) return true;

    const headers = guardedHeaders();
    if (!headers) return null;

    streamAbortRef.current?.abort();
    const controller = new AbortController();
    streamAbortRef.current = controller;

    setStreamingPage(pageNum);
    setPages(prev =>
      prev.find(p => p.page_number === pageNum)
        ? prev
        : [...prev, { page_number: pageNum, extracted_text: '', _streaming: true }]
    );

    try {
      const res = await fetch(`${BASE}/document/${documentId}/page/${pageNum}/lines`, {
        headers,
        signal: controller.signal,
      });
      if (res.status === 401) { onAuthError(); return null; }
      if (!res.ok) {
        setPages(prev => prev.filter(p => p.page_number !== pageNum));
        setStreamingPage(null);
        return null;
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

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
          } catch { /* malformed JSON line — skip */ }
        }
      }

      setPages(prev => prev.map(p => p.page_number === pageNum ? { ...p, _streaming: false } : p));
      setStreamingPage(null);
      return true;
    } catch (err) {
      if (err.name === 'AbortError') return null;
      console.error(`Streaming failed for page ${pageNum}:`, err);
      setPages(prev => prev.filter(p => p.page_number !== pageNum));
      setStreamingPage(null);
      return null;
    }
  }, [documentId, BASE, guardedHeaders, onAuthError]);

  const fetchPage = useCallback(async (pageNum, retries = 4, delayMs = 800) => {
    const headers = guardedHeaders();
    if (!headers) return null;

    for (let attempt = 0; attempt <= retries; attempt++) {
      const res = await fetch(`${BASE}/document/${documentId}/page/${pageNum}`, { headers });
      if (res.status === 401) { onAuthError(); return null; }
      if (res.ok) return await res.json();

      if (res.status === 404 && attempt < retries) {
        console.warn(`Page ${pageNum} not ready (attempt ${attempt + 1}/${retries}), retrying…`);
        await new Promise(r => setTimeout(r, delayMs * (attempt + 1)));
        continue;
      }

      throw new Error(`Failed to fetch page ${pageNum} (HTTP ${res.status})`);
    }
    return null;
  }, [documentId, BASE, guardedHeaders, onAuthError]);

  const prefetchPageBatch = useCallback(async (afterPage, limit = 5) => {
    const headers = guardedHeaders();
    if (!headers) return;
    const nextPageNum = afterPage + 1;
    if (nextPageNum > totalPages) return;

    try {
      const res = await fetch(
        `${BASE}/document/${documentId}/pages?page=${Math.ceil(nextPageNum / limit)}&limit=${limit}`,
        { headers }
      );
      if (!res.ok || res.status === 401) return;
      const data = await res.json();

      if (data.pages?.length) {
        setPages(prev => {
          const existing = new Set(prev.map(p => p.page_number));
          const fresh    = data.pages.filter(p => !existing.has(p.page_number));
          return fresh.length ? [...prev, ...fresh] : prev;
        });
        const last = data.pages[data.pages.length - 1].page_number;
        if (last > currentPageRef.current) {
          currentPageRef.current = last;
          setCurrentPage(last);
        }
      }
    } catch (err) {
      console.error('Batch prefetch failed:', err);
    }
  }, [documentId, BASE, totalPages, guardedHeaders]);

  const loadNextPage = useCallback(async () => {
    if (isLoadingMore || currentPageRef.current >= totalPages) return;
    setIsLoadingMore(true);
    setPageLoadError(false);

    try {
      const nextPage = currentPageRef.current + 1;
      if (pagesRef.current.find(p => p.page_number === nextPage && p.extracted_text?.trim())) {
        currentPageRef.current = nextPage;
        setCurrentPage(nextPage);
        setIsLoadingMore(false);
        return;
      }

      const streamed = await fetchPageStreaming(nextPage);
      if (streamed === null) {
        let pageData = null;
        try {
          pageData = await fetchPage(nextPage);
        } catch (err) {
          console.error('Failed to load page after retries:', err);
          setPageLoadError(true);
          setIsLoadingMore(false);
          return;
        }

        if (pageData) {
          setPages(prev =>
            prev.find(p => p.page_number === pageData.page_number)
              ? prev
              : [...prev, pageData]
          );
        } else {
          setIsLoadingMore(false);
          return;
        }
      }

      currentPageRef.current = nextPage;
      setCurrentPage(nextPage);

      if (nextPage === 1) prefetchPageBatch(nextPage);
    } catch (err) {
      console.error('Failed to load page:', err);
      setPageLoadError(true);
    }

    setIsLoadingMore(false);
  }, [isLoadingMore, totalPages, fetchPageStreaming, fetchPage, prefetchPageBatch]);

  // ── Initial load ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (isTextDoc) return;
    fetchDocumentView().then((hasData) => {
      if (!hasData) {
        fetchDocumentMeta();
        loadNextPage();
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const bottomRef = useBottomInfiniteScroll(loadNextPage, !isTextDoc && hasMore);

  // ── Text-selection → floating menu ───────────────────────────────────────
  const handleMouseUp = (e) => {
    if (
      e.target.closest('.floating-menu') ||
      e.target.closest('.meaning-popup') ||
      e.target.closest('.chat-panel') ||
      e.target.closest('.note-panel') ||
      e.target.closest('.note-toggle-btn')
    ) return;

    setTimeout(() => {
      const selection = window.getSelection();
      const text = selection?.toString().trim();
      if (!text || selection.rangeCount === 0) {
        setMenuConfig(prev => ({ ...prev, show: false }));
        return;
      }

      const range = selection.getRangeAt(0);
      const rect  = range.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) return;

      const wordCount   = text.split(/\s+/).length;
      const isParagraph = wordCount > 10;

      const MENU_W = 200, MENU_H = 40, GAP = 10;
      const vw = window.innerWidth, vh = window.innerHeight;
      let rawX = rect.left + rect.width / 2;
      let rawY, placement;

      if (isParagraph) {
        const belowFits = rect.bottom + GAP + MENU_H <= vh;
        const aboveFits = rect.top   - GAP - MENU_H >= 0;
        if (belowFits) { rawY = rect.bottom + GAP; placement = 'below'; }
        else if (aboveFits) { rawY = rect.top - GAP; placement = 'above'; }
        else { rawY = vh - MENU_H - GAP * 2; placement = 'below'; }
      } else {
        if (rect.top - GAP - MENU_H >= 0) { rawY = rect.top - GAP; placement = 'above'; }
        else { rawY = rect.bottom + GAP; placement = 'below'; }
      }

      const halfMenu = MENU_W / 2 + GAP;
      const clampedX = Math.min(Math.max(rawX, halfMenu), vw - halfMenu);

      setSelectedText(text);
      setMenuConfig({
        show: true, x: clampedX, y: rawY, placement,
        type: wordCount === 1 ? 'word' : wordCount <= 10 ? 'short' : 'paragraph',
      });
    }, 30);
  };

  const handleMouseDown = (e) => {
    const path = typeof e.composedPath === 'function' ? e.composedPath() : [];
    const insidePanel = path.some(el =>
      el?.classList?.contains('floating-menu') ||
      el?.classList?.contains('meaning-popup') ||
      el?.classList?.contains('chat-panel') ||
      el?.classList?.contains('note-panel') ||
      el?.classList?.contains('note-toggle-btn')
    );
    if (!insidePanel) {
      setMenuConfig(prev => ({ ...prev, show: false }));
      setMeaningPopup(prev => ({ ...prev, show: false }));
      setLengthPicker(false);
      setPhonetic('');
    }
  };

  // ── Meaning ───────────────────────────────────────────────────────────────
  const handleMeaningClick = async (e) => {
    e.stopPropagation();
    setMenuConfig(prev => ({ ...prev, show: false }));
    setMeaningPopup({ show: true, x: menuConfig.x, y: menuConfig.y, text: selectedText, result: '', loading: true });

    const headers = guardedHeaders();
    if (!headers) return;

    try {
      const word = encodeURIComponent(selectedText.trim());
      const res  = await fetch(`${BASE}/dictionary/${word}/meaning`, { headers });
      if (res.status === 401) { onAuthError(); return; }

      if (res.ok) {
        const data = await res.json();
        const result = [
          data.meaning,
          data.synonym ? `Synonym: ${data.synonym}` : '',
          data.example ? `Example: ${data.example}` : '',
        ].filter(Boolean).join('\n');
        setMeaningPopup(prev => ({ ...prev, loading: false, result }));
        return;
      }

      const ragRes = await fetch(`${RAG_API_URL}/chat`, {
        method: 'POST',
        headers: { ...getRagHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: `Define the word or phrase: "${selectedText}". Give a concise, plain-English definition in 1-2 sentences.`,
          top_k: 3, use_hybrid: false,
        }),
      });
      const ragData = ragRes.ok ? await ragRes.json() : null;
      setMeaningPopup(prev => ({
        ...prev, loading: false,
        result: ragData?.answer || `No definition found for "${selectedText}".`,
      }));
    } catch {
      setMeaningPopup(prev => ({ ...prev, loading: false, result: 'Failed to fetch definition.' }));
    }
  };

  // ── Summarize ─────────────────────────────────────────────────────────────
  const handleSummaryClick = (e) => { e.stopPropagation(); setLengthPicker(prev => !prev); };

  const fireSummarize = async (length) => {
    setLengthPicker(false);
    setMenuConfig(prev => ({ ...prev, show: false }));
    const capturedText = selectedText;
    setInjectedMessage({ type: 'summary', selectedText: capturedText, length, result: null, id: Date.now() });
    // On mobile, switch to chat tab after summarizing
    if (isMobile) setMobileTab('chat');

    const headers = guardedHeaders();
    if (!headers) return;

    try {
      const res = await fetch(`${RAG_API_URL}/summarize`, {
        method: 'POST',
        headers: { ...getRagHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: capturedText, length }),
      });
      if (res.status === 401) { onAuthError(); return; }
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Summarize failed (${res.status})`);
      setInjectedMessage(prev => ({ ...prev, result: data.summary || data.detail || 'No summary generated.' }));
    } catch (err) {
      setInjectedMessage(prev => ({ ...prev, result: err.message || 'Failed to generate summary.' }));
    }
  };

  // ── Text-to-speech ────────────────────────────────────────────────────────
  const handlePronounce = async (e) => {
    e.stopPropagation();
    setPhonetic('');

    if (isSpeaking) { window.speechSynthesis.cancel(); setIsSpeaking(false); return; }

    if (menuConfig.type === 'word') {
      const headers = guardedHeaders();
      if (!headers) return;
      try {
        const res = await fetch(`${BASE}/dictionary/${encodeURIComponent(selectedText.trim())}/pronounce`, { headers });
        if (res.ok) {
          const rawPhonetic = res.headers.get('X-Phonetic');
          if (rawPhonetic) { const sym = decodeURIComponent(rawPhonetic); setPhonetic(sym); setTimeout(() => setPhonetic(''), 4000); }
          const blob  = await res.blob();
          const audio = new Audio(URL.createObjectURL(blob));
          setIsSpeaking(true);
          audio.onended = () => setIsSpeaking(false);
          audio.onerror = () => setIsSpeaking(false);
          audio.play();
          return;
        }
      } catch (err) { console.error('Pronunciation API failed:', err); }
    }

    const utterance = new SpeechSynthesisUtterance(selectedText);
    utterance.rate    = 0.95;
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend   = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    window.speechSynthesis.speak(utterance);
  };

  // ── Delete document ───────────────────────────────────────────────────────
  const handleDelete = async () => {
    if (!window.confirm('Delete this document? This cannot be undone.')) return;
    const headers = guardedHeaders();
    if (!headers) return;
    try {
      const res = await fetch(`${BASE}/document/${documentId}`, { method: 'DELETE', headers });
      if (res.status === 401) { onAuthError(); return; }
      handleBack();
    } catch (err) { console.error('Delete failed:', err); }
  };

  // ── Page note helpers ─────────────────────────────────────────────────────
  const toggleNoteSection = (pageNum) => setOpenNotePageNum(prev => (prev === pageNum ? null : pageNum));
  const handleNoteChange  = (pageNum, value) => setPageNotes(prev => ({ ...prev, [pageNum]: value }));

  const dirtyCount = dirtyPages.size;

  // ── Sidebar icons (reused on desktop sidebar & mobile top bar) ────────────
  const SidebarActions = ({ className = '' }) => (
    <>
      {!isTextDoc && (
        <>
          {/* Bulk save */}
          <div className={`relative ${className}`}>
            <button
              onClick={handleBulkSave}
              className={`p-3 rounded-xl transition-all ${dirtyCount > 0 ? 'text-blue-500 hover:bg-blue-50 cursor-pointer' : 'text-gray-300 cursor-default opacity-50'}`}
              title={dirtyCount > 0 ? `Save all ${dirtyCount} unsaved page(s)` : 'No unsaved changes'}
            >
              {isBulkSaving ? <Spinner size="w-5 h-5" color="border-t-blue-500" /> : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                </svg>
              )}
              {dirtyCount > 0 && !isBulkSaving && (
                <span className="absolute -top-1 -right-1 w-4 h-4 bg-blue-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
                  {dirtyCount}
                </span>
              )}
            </button>
          </div>

          {/* Generate PDF */}
          <button
            onClick={handleGeneratePdf}
            disabled={isGeneratingPdf}
            className={`p-3 text-gray-400 hover:bg-blue-50 hover:text-blue-500 rounded-xl transition-all disabled:opacity-50 ${className}`}
            title="Rebuild PDF from edited text"
          >
            {isGeneratingPdf ? <Spinner size="w-5 h-5" color="border-t-blue-500" /> : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            )}
          </button>

          {/* View generated PDF */}
          {generatedPdfUrl && (
            <a
              href={generatedPdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className={`p-3 text-gray-400 hover:bg-emerald-50 hover:text-emerald-600 rounded-xl transition-all relative group ${className}`}
              title="View generated PDF"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
              </svg>
              <span className="absolute top-2 right-2 w-2 h-2 bg-emerald-400 rounded-full ring-2 ring-white" />
            </a>
          )}
        </>
      )}

      {/* Delete */}
      <button
        onClick={handleDelete}
        className={`p-3 text-gray-400 hover:bg-red-50 hover:text-red-500 rounded-xl transition-all ${className}`}
        title="Delete document"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
      </button>
    </>
  );

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div
      className="flex flex-col md:flex-row h-screen bg-[#F0F2F5] relative overflow-hidden font-sans"
      onMouseUp={handleMouseUp}
      onMouseDown={handleMouseDown}
    >
      {/* ── FLOATING SELECTION MENU ── */}
      {menuConfig.show && (
        <>
          {phonetic && (
            <div
              style={{
                position:      'fixed',
                zIndex:        10000,
                top:           menuConfig.placement === 'below'
                  ? `${menuConfig.y + 44}px`
                  : `${menuConfig.y - 44}px`,
                left:          `${menuConfig.x}px`,
                transform:     'translateX(-50%)',
                background:    '#2d2d2d',
                color:         '#a5f3fc',
                fontSize:      '15px',
                fontFamily:    'serif',
                letterSpacing: '0.05em',
                padding:       '5px 14px',
                borderRadius:  '20px',
                border:        '1px solid #444',
                boxShadow:     '0 2px 12px rgba(0,0,0,0.4)',
                pointerEvents: 'none',
                whiteSpace:    'nowrap',
              }}
            >
              {phonetic}
            </div>
          )}

          <div
            className="floating-menu"
            style={{
              position:  'fixed',
              zIndex:    9999,
              top:       `${menuConfig.y}px`,
              left:      `${menuConfig.x}px`,
              transform: menuConfig.placement === 'below'
                ? 'translateX(-50%)'
                : 'translateX(-50%) translateY(-100%)',
              background:   '#1a1a1a',
              color:        '#fff',
              borderRadius: '8px',
              display:      'flex',
              overflow:     'hidden',
              boxShadow:    '0 4px 20px rgba(0,0,0,0.3)',
              border:       '1px solid #333',
            }}
            onMouseUp={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex' }}>
              {menuConfig.type === 'word' && (
                <>
                  <button onClick={handleMeaningClick} style={menuBtnStyle}>📖 Meaning</button>
                  <div style={{ width: 1, background: '#333' }} />
                  <button onClick={handlePronounce} style={menuBtnStyle}>{isSpeaking ? '⏹ Stop' : '🔊 Speak'}</button>
                </>
              )}
              {menuConfig.type === 'short' && (
                <button onClick={handlePronounce} style={menuBtnStyle}>{isSpeaking ? '⏹ Stop' : '🔊 Speak'}</button>
              )}
              {menuConfig.type === 'paragraph' && (
                <>
                  {lengthPicker ? (
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                      <span style={{ padding: '0 10px', fontSize: '11px', color: '#888', whiteSpace: 'nowrap' }}>Length:</span>
                      {[
                        { key: 'short',   label: 'Short'   },
                        { key: 'medium',  label: 'Medium'  },
                        { key: 'long',    label: 'Long'    },
                        { key: 'bullets', label: 'Bullets' },
                      ].map(({ key, label }, i, arr) => (
                        <React.Fragment key={key}>
                          <button
                            onClick={(e) => { e.stopPropagation(); fireSummarize(key); }}
                            style={{ ...menuBtnStyle, color: '#60a5fa', fontWeight: 600, fontSize: '12px', padding: '8px 12px' }}
                          >
                            {label}
                          </button>
                          {i < arr.length - 1 && <div style={{ width: 1, background: '#333' }} />}
                        </React.Fragment>
                      ))}
                      <div style={{ width: 1, background: '#333' }} />
                      <button onClick={(e) => { e.stopPropagation(); setLengthPicker(false); }} style={{ ...menuBtnStyle, color: '#888', padding: '8px 10px' }}>✕</button>
                    </div>
                  ) : (
                    <>
                      <button onClick={handleSummaryClick} style={menuBtnStyle}>✨ Summarize</button>
                      <div style={{ width: 1, background: '#333' }} />
                      <button onClick={handlePronounce} style={menuBtnStyle}>{isSpeaking ? '⏹ Stop' : '🔊 Read'}</button>
                    </>
                  )}
                </>
              )}
            </div>
          </div>
        </>
      )}

      {/* ── MEANING POPUP ── */}
      {meaningPopup.show && (
        <div
          className="meaning-popup fixed z-[9998] w-[280px] bg-gray-50 rounded-2xl border border-gray-200 shadow-lg overflow-hidden"
          style={{
            left:      `${Math.min(meaningPopup.x, window.innerWidth - 150)}px`,
            top:       `${meaningPopup.y}px`,
            transform: 'translateX(-50%) translateY(-100%) translateY(-12px)',
          }}
          onMouseDown={(e) => e.stopPropagation()}
          onMouseUp={(e) => e.stopPropagation()}
        >
          <div className="px-4 pt-3.5 pb-0 bg-white border-b border-gray-200 flex items-end justify-between">
            <div className="flex items-center gap-2 pb-1 -mb-px">
              <svg className="w-[14px] h-[14px] text-indigo-400 shrink-0 mb-[1px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
              <span className="text-[15px] font-semibold text-gray-900 leading-none">{meaningPopup.text}</span>
            </div>
            <button
              onClick={() => setMeaningPopup(prev => ({ ...prev, show: false }))}
              className="text-gray-400 hover:text-gray-600 text-lg pb-1 -mb-px leading-none bg-transparent border-0 cursor-pointer transition-colors"
            >×</button>
          </div>

          <div className="px-4 py-3">
            {meaningPopup.loading ? (
              <div className="flex flex-col gap-2">
                {[100, 75, 50].map((w, i) => (
                  <div key={i} className="h-[11px] bg-gray-200 rounded animate-pulse" style={{ width: `${w}%` }} />
                ))}
              </div>
            ) : (
              <div>
                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-[0.07em] mb-0.5">Definition</p>
                <p className="text-[13px] leading-[1.65] text-gray-900 mb-2.5">{meaningPopup.result.split('\n')[0]}</p>
                {meaningPopup.result.split('\n').slice(1).map((line, i) => {
                  const colonIdx = line.indexOf(': ');
                  const label    = colonIdx !== -1 ? line.slice(0, colonIdx) : line;
                  const value    = colonIdx !== -1 ? line.slice(colonIdx + 2) : '';
                  return (
                    <div key={i} className="mt-2">
                      <span className="block text-[10px] font-bold text-gray-400 uppercase tracking-[0.07em] mb-0.5">{label}</span>
                      <span className={`text-[13px] text-gray-600 leading-relaxed ${label.toLowerCase() === 'example' ? 'italic' : ''}`}>{value}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="absolute -bottom-[7px] left-1/2 -translate-x-1/2 w-0 h-0"
            style={{ borderLeft: '7px solid transparent', borderRight: '7px solid transparent', borderTop: '7px solid #e5e7eb' }} />
          <div className="absolute -bottom-[6px] left-1/2 -translate-x-1/2 w-0 h-0"
            style={{ borderLeft: '6px solid transparent', borderRight: '6px solid transparent', borderTop: '6px solid #f9fafb' }} />
        </div>
      )}

      {/* ── MOBILE TOP BAR ── */}
      <header className="md:hidden flex items-center gap-2 px-3 py-2 bg-white border-b border-gray-200 shrink-0 z-20">
        <button onClick={handleBack} className="p-2 text-gray-500 hover:bg-gray-100 rounded-xl transition-all" title="Back">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
        </button>

        {/* Page indicator */}
        {!isTextDoc && totalPages > 0 && (
          <span className="text-xs text-gray-500 font-medium">
            {currentPage > 0 ? `${currentPage}/${totalPages}` : `0/${totalPages}`}
          </span>
        )}

        {/* Doc name */}
        <div className="flex-1 min-w-0 mx-1">
          {(docMeta?.filename || documentName) && (
            <p className="text-xs font-medium text-gray-700 truncate">
              {docMeta?.filename || documentName}
            </p>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center">
          <SidebarActions />
        </div>

        {/* Tab switcher */}
        <div className="flex bg-gray-100 rounded-xl p-0.5">
          <button
            onClick={() => setMobileTab('doc')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${mobileTab === 'doc' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'}`}
          >
            Doc
          </button>
          <button
            onClick={() => setMobileTab('chat')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${mobileTab === 'chat' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'}`}
          >
            Chat
          </button>
        </div>
      </header>

      {/* ── DESKTOP SIDEBAR ── */}
      <aside className="hidden md:flex w-16 bg-white border-r border-gray-200 flex-col items-center py-6 shrink-0 z-20">
        {/* Back */}
        <button onClick={handleBack} className="p-3 mb-4 text-gray-500 hover:bg-gray-100 hover:text-gray-900 rounded-xl transition-all" title="Back to Dashboard">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
        </button>

        <div className="w-8 h-px bg-gray-200 my-2" />

        {!isTextDoc && (
          <>
            {/* Bulk save */}
            <div className="relative">
              <button
                onClick={handleBulkSave}
                className={`p-3 rounded-xl transition-all ${dirtyCount > 0 ? 'text-blue-500 hover:bg-blue-50 cursor-pointer' : 'text-gray-300 cursor-default opacity-50'}`}
                title={dirtyCount > 0 ? `Save all ${dirtyCount} unsaved page(s)` : 'No unsaved changes'}
              >
                {isBulkSaving ? <Spinner size="w-5 h-5" color="border-t-blue-500" /> : (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                  </svg>
                )}
              </button>
              {dirtyCount > 0 && !isBulkSaving && (
                <span className="absolute -top-1 -right-1 w-4 h-4 bg-blue-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
                  {dirtyCount}
                </span>
              )}
            </div>

            {/* Generate PDF */}
            <button
              onClick={handleGeneratePdf}
              disabled={isGeneratingPdf}
              className="p-3 text-gray-400 hover:bg-blue-50 hover:text-blue-500 rounded-xl transition-all disabled:opacity-50"
              title="Rebuild PDF from edited text"
            >
              {isGeneratingPdf ? <Spinner size="w-5 h-5" color="border-t-blue-500" /> : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
              )}
            </button>

            {generatedPdfUrl && (
              <>
                <div className="w-8 h-px bg-gray-100 my-1" />
                <a
                  href={generatedPdfUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-3 text-gray-400 hover:bg-emerald-50 hover:text-emerald-600 rounded-xl transition-all relative group"
                  title="View generated PDF"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                  <span className="absolute top-2 right-2 w-2 h-2 bg-emerald-400 rounded-full ring-2 ring-white" />
                  <span className="absolute left-full ml-2 top-1/2 -translate-y-1/2 bg-gray-900 text-white text-xs font-medium px-2.5 py-1.5 rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
                    View generated PDF
                  </span>
                </a>
              </>
            )}
          </>
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

      {/* ── MAIN CONTENT AREA ── */}
      <main className="flex-1 flex flex-col md:flex-row h-full md:h-screen relative min-w-0 overflow-hidden">

        {/* ── DOCUMENT COLUMN — hidden on mobile when chat tab active ── */}
        <div className={`
          flex-1 flex flex-col relative overflow-hidden min-w-0
          ${isMobile && mobileTab === 'chat' ? 'hidden' : 'flex'}
          h-full md:h-screen
        `}>

          {/* Desktop top bar */}
          <header className="hidden md:flex absolute top-8 left-0 right-0 z-10 px-0 py-4 pointer-events-none justify-between items-center">
            <div className="flex items-center gap-2 pointer-events-auto">
              {(docMeta?.filename || documentName || documentCategory) && (
                <div className="bg-white/90 backdrop-blur-sm border border-gray-200 shadow-sm px-3 py-1.5 rounded-full">
                  <span className="text-xs font-medium text-gray-500">
                    {documentCategory === 'text' ? '📄' : '🔍'}{' '}
                    {docMeta?.filename || documentName || (documentCategory === 'text' ? 'Digital document' : 'Scanned document')}
                  </span>
                </div>
              )}
              {docMeta?.processing_status && docMeta.processing_status !== 'completed' && (
                <div className="bg-amber-50 border border-amber-200 shadow-sm px-3 py-1.5 rounded-full">
                  <span className="text-xs font-medium text-amber-600 capitalize">{docMeta.processing_status}</span>
                </div>
              )}
            </div>

            <div className="bg-white/90 backdrop-blur-sm border border-gray-200 shadow-sm px-4 py-1.5 rounded-full pointer-events-auto flex items-center gap-3 ml-auto">
              {!isTextDoc && totalPages > 0 && (
                <span className="text-xs font-medium text-gray-600">
                  {currentPage > 0 ? `Page ${currentPage} of ${totalPages}` : `0 of ${totalPages}`}
                </span>
              )}
              {streamingPage && <span className="text-xs text-blue-500 font-medium">Streaming p.{streamingPage}…</span>}
              {isLoadingMore && !streamingPage && <Spinner size="w-3 h-3" color="border-t-blue-500" />}
            </div>
          </header>

          {/* Mobile streaming/loading indicator */}
          {isMobile && (streamingPage || isLoadingMore) && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 border-b border-blue-100">
              <Spinner size="w-3 h-3" color="border-t-blue-500" />
              <span className="text-xs text-blue-600 font-medium">
                {streamingPage ? `Loading page ${streamingPage}…` : 'Loading…'}
              </span>
            </div>
          )}

          {/* Toasts */}
          <div className="relative z-[400]">
            {!isTextDoc && fmtSummary && !fmtSummary.all_done && (
              <div className="mx-3 md:mx-4 mt-2 md:mt-16 mb-0 z-10">
                <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex items-center gap-3">
                  <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-semibold text-amber-800">Formatting OCR text with AI…</span>
                      <span className="text-xs text-amber-600 font-medium tabular-nums">
                        {fmtSummary.completed}/{fmtSummary.total_pages} pages
                      </span>
                    </div>
                    <div className="h-1.5 bg-amber-200 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-amber-500 rounded-full transition-all duration-500"
                        style={{ width: `${fmtSummary.total_pages > 0 ? (fmtSummary.completed / fmtSummary.total_pages) * 100 : 0}%` }}
                      />
                    </div>
                    <div className="flex gap-2 mt-1.5">
                      {fmtSummary.processing > 0 && (
                        <span className="text-[10px] text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
                          {fmtSummary.processing} processing
                        </span>
                      )}
                      {fmtSummary.pending > 0 && (
                        <span className="text-[10px] text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">
                          {fmtSummary.pending} pending
                        </span>
                      )}
                      {fmtSummary.failed > 0 && (
                        <button
                          onClick={handleReformat}
                          className="text-[10px] text-red-600 bg-red-50 hover:bg-red-100 px-2 py-0.5 rounded-full transition-colors border border-red-200"
                        >
                          {fmtSummary.failed} failed — retry ↺
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {!isTextDoc && showFmtDone && (
              <div className="mx-3 md:mx-4 mt-2 md:mt-16 mb-0 z-10">
                <div className="bg-green-50 border border-green-200 rounded-xl px-4 py-2.5 flex items-center gap-2">
                  <svg className="w-4 h-4 text-green-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span className="text-xs font-medium text-green-800">
                    OCR formatting complete — text quality improved
                  </span>
                  {fmtSummary.failed > 0 && (
                    <button onClick={handleReformat} className="ml-auto text-[10px] text-red-500 hover:underline">
                      Retry {fmtSummary.failed} failed
                    </button>
                  )}
                </div>
              </div>
            )}

            <Toast status={bulkSaveStatus} message={bulkSaveStatus === 'success' ? 'All changes saved' : 'Save failed — try again'} />
            <Toast status={pdfGenStatus} message={pdfGenMessage} />
          </div>

          {/* Scrollable content */}
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto pb-20 scroll-smooth"
            style={{ maxHeight: '100%' }}
          >
            {isTextDoc ? (
              pdfUrl ? (
                <PdfViewer
                  pdfUrl={pdfUrl}
                  pageNotes={pageNotes}
                  onNoteChange={handleNoteChange}
                  openNotePageNum={openNotePageNum}
                  onToggleNote={toggleNoteSection}
                  onPageChange={(pageNum) => setCurrentPage(pageNum)}
                  onNoteSave={saveNote}
                />
              ) : (
                <div className="flex items-center justify-center h-full">
                  <Spinner size="w-8 h-8" color="border-t-gray-600" />
                </div>
              )
            ) : (
            // AFTER
<div className="flex flex-col items-center px-0 sm:px-6 space-y-6 sm:space-y-8 pt-4 md:pt-20">
                {pages.map((page) => (
                  <div key={page.page_number} className="relative group transition-transform duration-300 w-full flex flex-col items-center">
                    <div className="absolute -left-3 sm:-left-5 top-0 text-xs text-gray-400 font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                      p.{page.page_number}
                    </div>

                    {dirtyPages.has(page.page_number) && (
                      <div className="absolute -right-1 sm:-right-3 top-3 w-2 h-2 bg-blue-400 rounded-full" title="Unsaved changes" />
                    )}

                    {/* PAGE CARD — responsive width */}
                    <div
                      ref={(el) => { if (el) pageRefs.current[page.page_number] = el; }}
                      className="bg-white w-full  shadow-sm hover:shadow-md transition-shadow duration-300 border border-gray-200/60 relative"
                      style={{ userSelect: 'text', WebkitUserSelect: 'text', overflow: 'visible' }}
                    >
                      <div
                        contentEditable
                        suppressContentEditableWarning
                        className="w-full h-full p-4 sm:p-[25mm] sm:pb-[15mm] outline-none text-[11pt] sm:text-[12pt] leading-[1.8] text-gray-800 font-serif text-justify selection:bg-blue-100 selection:text-blue-900 whitespace-pre-wrap empty:before:content-['Start_typing...'] empty:before:text-gray-300"
                       style={{ minHeight: 'auto' }}
                        onInput={(e) => setDirtyPages(prev => new Set(prev).add(page.page_number))}
                        onBlur={(e) => handleContentChange(page.page_number, e.currentTarget.innerText)}
                      >
                        {page.extracted_text || ''}
                      </div>

                      {page._streaming && (
                        <div className="absolute top-4 right-4 flex items-center gap-1.5 bg-white/80 backdrop-blur-sm px-2 py-1 rounded-full border border-gray-200">
                          <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
                          <span className="text-[10px] text-gray-400 font-medium">Loading…</span>
                        </div>
                      )}

                      <div className="border-t border-gray-100 flex items-center justify-center px-4 py-2.5 bg-white">
                        <CenteredNoteButton
                          hasNote={!!pageNotes[page.page_number]}
                          isOpen={openNotePageNum === page.page_number}
                          onClick={() => toggleNoteSection(page.page_number)}
                          pageNum={page.page_number}
                        />
                      </div>
                    </div>

                    <FloatingNotePanel
                      pageNum={page.page_number}
                      note={pageNotes[page.page_number] || ''}
                      onChange={(val) => handleNoteChange(page.page_number, val)}
                      isOpen={openNotePageNum === page.page_number}
                      onClose={() => toggleNoteSection(page.page_number)}
                      onSave={saveNote}
                    />
                  </div>
                ))}

                {pageLoadError && !isLoadingMore && (
                  <div className="flex flex-col items-center gap-3 py-8 text-center w-full max-w-[210mm]">
                    <p className="text-sm text-gray-500">Failed to load page. The document may still be processing.</p>
                    <button
                      onClick={() => { setPageLoadError(false); loadNextPage(); }}
                      className="px-4 py-2 bg-blue-500 text-white text-sm rounded-lg hover:bg-blue-600 transition-colors"
                    >
                      Retry
                    </button>
                  </div>
                )}

                {isLoadingMore && (
                  <div className="bg-white w-full max-w-[210mm] shadow-sm border border-gray-200 p-6 sm:p-[25mm] space-y-6 animate-pulse" style={{ minHeight: '40vw' }}>
                    <div className="h-4 bg-gray-100 rounded w-full" />
                    <div className="h-4 bg-gray-100 rounded w-full" />
                    <div className="h-4 bg-gray-100 rounded w-5/6" />
                    <div className="h-4 bg-gray-100 rounded w-full" />
                    <div className="h-32 bg-gray-50 rounded w-full mt-8" />
                  </div>
                )}

                {!hasMore && pages.length > 0 && (
                  <div className="w-full max-w-[250mm] flex justify-center py-1">
                    <EndOfDocument />
                  </div>
                )}
                <div ref={bottomRef} className="h-4" />
              </div>
            )}
          </div>
        </div>

        {/* ── CHAT PANEL — full screen on mobile when active, fixed width on desktop ── */}
        <div className={`
          ${isMobile
            ? `${mobileTab === 'chat' ? 'flex' : 'hidden'} w-full`
            : 'flex shrink-0 border-l border-gray-200'
          }
          chat-panel relative self-stretch
        `}
          style={isMobile ? {} : { width: 520, minWidth: 520, maxWidth: 520 }}
        >
          <ChatPanel
            documentId={documentId}
            documentName={docMeta?.filename || documentName || ''}
            injectedMessage={injectedMessage}
            onInjectedMessageConsumed={() => setInjectedMessage(null)}
            panelWidth={isMobile ? window.innerWidth : 520}
          />
        </div>
      </main>
    </div>
  );
};

export default Workspace;