import React, { useState, useEffect, useCallback } from 'react';
import { Upload, FileText, LogOut, ChevronRight, AlertCircle, HardDrive, Trash2, RefreshCw, X, Clock, BookOpen } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
import Workspace from './Workspace.jsx';

const API_URL = import.meta.env.VITE_DOCUMENT_API_URL || 'http://localhost:8001';

// ── Helpers ───────────────────────────────────────────────────────────────────

const formatBytes = (bytes) => {
  if (!bytes) return '0 KB';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatDate = (dateStr) => {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleDateString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric',
  });
};

const categoryIcon = (cat) => cat === 'text' ? '📄' : '🔍';
const categoryLabel = (cat) => cat === 'text' ? 'Digital' : 'Scanned';

// ── Dashboard ─────────────────────────────────────────────────────────────────

const Dashboard = () => {
  const navigate = useNavigate();
  const { logout, accessToken, user, loading } = useAuth();

  // Upload state
  const [file, setFile] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isProcessed, setIsProcessed] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState('');

  // Workspace state
  const [documentId, setDocumentId] = useState(null);
  const [totalPages, setTotalPages] = useState(0);
  const [documentCategory, setDocumentCategory] = useState('');

  // Storage state
  const [storageInfo, setStorageInfo] = useState(null);

  // Document library state
  const [showLibrary, setShowLibrary] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docsError, setDocsError] = useState('');
  const [docsPage, setDocsPage] = useState(1);
  const [docsTotal, setDocsTotal] = useState(0);
  const [deletingId, setDeletingId] = useState(null);

  // Opening-from-library loading state
  const [openingDocId, setOpeningDocId] = useState(null);

  const DOCS_LIMIT = 10;

  // Always read token fresh
  const getAuthHeaders = useCallback(() => ({
    Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
  }), []);

  // ── Auth guards ──────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex h-screen bg-neutral-900 items-center justify-center">
        <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  if (!loading && !accessToken) {
    navigate('/?showLogin=true', { replace: true });
    return null;
  }

  const handleAuthError = () => {
    logout();
    navigate('/?showLogin=true', { replace: true });
  };

  // ── Storage fetch ────────────────────────────────────────────────────────────

  const fetchStorage = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/me/storage`, { headers: getAuthHeaders() });
      if (res.status === 401) { handleAuthError(); return; }
      if (res.ok) setStorageInfo(await res.json());
    } catch (_) {}
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) return;
    fetchStorage();
  }, [accessToken]);

  // ── GET /documents — document library ────────────────────────────────────────

  const fetchDocuments = useCallback(async (page = 1) => {
    setDocsLoading(true);
    setDocsError('');
    try {
      const res = await fetch(
        `${API_URL}/documents?page=${page}&limit=${DOCS_LIMIT}`,
        { headers: getAuthHeaders() }
      );
      if (res.status === 401) { handleAuthError(); return; }
      if (!res.ok) throw new Error(`Failed to load documents (${res.status})`);
      const data = await res.json();
      setDocuments(data.documents || []);
      setDocsTotal(data.total || 0);
      setDocsPage(page);
    } catch (err) {
      setDocsError(err.message || 'Failed to load documents.');
    } finally {
      setDocsLoading(false);
    }
  }, [getAuthHeaders]);

  // Load library when panel opens
  useEffect(() => {
    if (showLibrary) fetchDocuments(1);
  }, [showLibrary]);

  // ── DELETE /document/{id} from library ───────────────────────────────────────

  const handleDeleteFromLibrary = async (docId, e) => {
    e.stopPropagation();
    if (!window.confirm('Delete this document? This cannot be undone.')) return;
    setDeletingId(docId);
    try {
      const res = await fetch(`${API_URL}/document/${docId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      if (res.status === 401) { handleAuthError(); return; }
      if (!res.ok) throw new Error('Delete failed');
      await fetchDocuments(docsPage);
      await fetchStorage();
    } catch (err) {
      alert(err.message || 'Failed to delete document.');
    } finally {
      setDeletingId(null);
    }
  };

  // ── GET /documents/{id}/view — open a document from library ─────────────────
  // Uses the unified view endpoint to get fresh metadata + pdf_url before
  // entering the Workspace. Falls back to the library row data if the call fails.
  const handleOpenFromLibrary = async (doc) => {
    setOpeningDocId(doc.id);
    try {
      const res = await fetch(`${API_URL}/documents/${doc.id}/view`, {
        headers: getAuthHeaders(),
      });
      if (res.status === 401) { handleAuthError(); return; }

      if (res.ok) {
        const viewData = await res.json();
        // viewData shape: { document_id, filename, document_category, total_pages, pdf_url, ocr_lines }
        setDocumentId(viewData.document_id);
        setTotalPages(viewData.total_pages || doc.total_pages || 0);
        setDocumentCategory(viewData.document_category || doc.document_category || '');
      } else {
        // Fallback: use library row data directly
        setDocumentId(doc.id);
        setTotalPages(doc.total_pages || 0);
        setDocumentCategory(doc.document_category || '');
      }
    } catch {
      // Network error — fall back gracefully
      setDocumentId(doc.id);
      setTotalPages(doc.total_pages || 0);
      setDocumentCategory(doc.document_category || '');
    } finally {
      setOpeningDocId(null);
      setShowLibrary(false);
      setIsProcessed(true);
    }
  };

  // ── Back button while in workspace ───────────────────────────────────────────

  useEffect(() => {
    if (!isProcessed) return;
    const handleBackButton = () => {
      setIsProcessed(false);
      setDocumentId(null);
      window.history.pushState(null, '', window.location.pathname);
    };
    window.history.pushState(null, '', window.location.pathname);
    window.addEventListener('popstate', handleBackButton);
    return () => window.removeEventListener('popstate', handleBackButton);
  }, [isProcessed]);

  // ── Upload ───────────────────────────────────────────────────────────────────

  const handleUpload = async () => {
    if (!file) return;
    setIsProcessing(true);
    setError('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const uploadRes = await fetch(`${API_URL}/upload`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData,
      });
      if (uploadRes.status === 401) { handleAuthError(); return; }
      if (!uploadRes.ok) {
        const errData = await uploadRes.json().catch(() => ({}));
        if (uploadRes.status === 413) {
          throw new Error(errData.detail || 'Storage quota exceeded. Please delete some documents first.');
        }
        throw new Error(errData.detail || `Upload failed (${uploadRes.status})`);
      }
      const uploadData = await uploadRes.json();
      setDocumentId(uploadData.document_id);
      setTotalPages(uploadData.total_pages);
      setDocumentCategory(uploadData.document_category || '');
      setIsProcessing(false);
      setIsProcessed(true);
      await fetchStorage();
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.');
      setIsProcessing(false);
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true);
    else if (e.type === 'dragleave') setDragActive(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files?.[0]) { setFile(e.dataTransfer.files[0]); setError(''); }
  };

  const handleLogout = () => { logout(); navigate('/', { replace: true }); };

  const handleBackFromWorkspace = () => {
    setIsProcessed(false);
    setDocumentId(null);
    setFile(null);
    setDocumentCategory('');
    fetchStorage();
  };

  // ── Workspace view ───────────────────────────────────────────────────────────

  if (isProcessed) {
    return (
      <Workspace
        documentId={documentId}
        totalPages={totalPages}
        documentCategory={documentCategory}
        apiUrl={API_URL}
        authHeaders={getAuthHeaders()}
        onBack={handleBackFromWorkspace}
        onAuthError={handleAuthError}
      />
    );
  }

  // ── Storage bar helpers ───────────────────────────────────────────────────────

  const usedMb = storageInfo?.used_mb ?? 0;
  const limitMb = storageInfo?.limit_mb ?? 500;
  const usedPct = Math.min((usedMb / limitMb) * 100, 100);
  const storageNearFull = usedPct > 80;
  const displayName = user?.full_name?.split(' ')[0] || user?.email || '';
  const totalPages_ = Math.ceil(docsTotal / DOCS_LIMIT);

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen bg-neutral-900">

      {/* ── DOCUMENT LIBRARY PANEL (slide-in overlay) ── */}
      {showLibrary && (
        <div className="fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div
            className="flex-1 bg-black/60 backdrop-blur-sm"
            onClick={() => setShowLibrary(false)}
          />
          {/* Panel */}
          <div className="w-[480px] bg-neutral-900 border-l border-white/10 flex flex-col h-full shadow-2xl">

            {/* Panel header */}
            <div className="p-6 border-b border-white/10 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-white">My Documents</h2>
                <p className="text-xs text-gray-400 mt-0.5">{docsTotal} document{docsTotal !== 1 ? 's' : ''} · click to open, trash to delete</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => fetchDocuments(docsPage)}
                  className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition"
                  title="Refresh"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setShowLibrary(false)}
                  className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Panel body */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2">

              {docsLoading && (
                <div className="flex items-center justify-center py-16">
                  <div className="w-6 h-6 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                </div>
              )}

              {docsError && !docsLoading && (
                <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/30 text-red-300 px-4 py-3 rounded-xl text-sm">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  {docsError}
                </div>
              )}

              {!docsLoading && !docsError && documents.length === 0 && (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <BookOpen className="w-10 h-10 text-white/20 mb-3" />
                  <p className="text-white/40 text-sm">No documents yet.</p>
                  <p className="text-white/25 text-xs mt-1">Upload your first document to get started.</p>
                </div>
              )}

              {!docsLoading && documents.map((doc) => (
                <div
                  key={doc.id}
                  onClick={() => !openingDocId && handleOpenFromLibrary(doc)}
                  className={`group flex items-center gap-3 p-4 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 rounded-xl transition-all ${
                    openingDocId === doc.id ? 'cursor-wait opacity-70' : 'cursor-pointer'
                  }`}
                >
                  {/* Icon */}
                  <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center shrink-0 text-lg">
                    {openingDocId === doc.id
                      ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      : categoryIcon(doc.document_category)
                    }
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm font-medium truncate">{doc.filename}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-gray-500">{categoryLabel(doc.document_category)}</span>
                      <span className="text-gray-700">·</span>
                      <span className="text-xs text-gray-500">{doc.total_pages || 0} page{doc.total_pages !== 1 ? 's' : ''}</span>
                      <span className="text-gray-700">·</span>
                      <span className="text-xs text-gray-500">{formatBytes(doc.file_size_bytes)}</span>
                    </div>
                    <div className="flex items-center gap-1 mt-0.5">
                      <Clock className="w-3 h-3 text-gray-600" />
                      <span className="text-xs text-gray-600">{formatDate(doc.created_at)}</span>
                    </div>
                  </div>

                  {/* Delete button */}
                  <button
                    onClick={(e) => handleDeleteFromLibrary(doc.id, e)}
                    disabled={deletingId === doc.id || !!openingDocId}
                    className="p-2 text-gray-600 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition opacity-0 group-hover:opacity-100 disabled:pointer-events-none"
                    title="Delete document"
                  >
                    {deletingId === doc.id
                      ? <div className="w-4 h-4 border-2 border-red-400/30 border-t-red-400 rounded-full animate-spin" />
                      : <Trash2 className="w-4 h-4" />
                    }
                  </button>
                </div>
              ))}
            </div>

            {/* Pagination */}
            {totalPages_ > 1 && (
              <div className="p-4 border-t border-white/10 flex items-center justify-between">
                <button
                  onClick={() => fetchDocuments(docsPage - 1)}
                  disabled={docsPage <= 1 || docsLoading}
                  className="px-3 py-1.5 text-xs text-white/60 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition"
                >
                  Previous
                </button>
                <span className="text-xs text-gray-500">Page {docsPage} of {totalPages_}</span>
                <button
                  onClick={() => fetchDocuments(docsPage + 1)}
                  disabled={docsPage >= totalPages_ || docsLoading}
                  className="px-3 py-1.5 text-xs text-white/60 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition"
                >
                  Next
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── SIDEBAR ── */}
      <aside className="w-72 bg-black/20 backdrop-blur-xl border-r border-white/10 flex flex-col">
        <div className="p-6 border-b border-white/10">
          <h1 className="text-2xl font-bold font-serif text-white">ReadWithEase</h1>
          <p className="text-xs text-gray-400">Your AI-Powered Reading Companion</p>
          {displayName && (
            <p className="text-xs text-blue-400 mt-1">👋 Hey, {displayName}</p>
          )}
        </div>

        <nav className="flex-1 p-4 space-y-2">
          <button
            onClick={() => setShowLibrary(true)}
            className="w-full p-4 bg-white/5 border border-white/10 rounded-xl text-white/60 flex items-center gap-3 hover:bg-white/10 hover:text-white transition group"
          >
            <FileText className="w-5 h-5" />
            <span className="font-medium">My Documents</span>
            {docsTotal > 0 && (
              <span className="ml-auto text-xs bg-white/10 text-white/50 px-2 py-0.5 rounded-full">
                {docsTotal}
              </span>
            )}
            <ChevronRight className="w-4 h-4 ml-auto opacity-0 group-hover:opacity-100 transition" />
          </button>
        </nav>

        {/* Storage usage */}
        {storageInfo && (
          <div className="px-4 pb-2">
            <div className="bg-white/5 border border-white/10 rounded-xl p-3">
              <div className="flex items-center gap-2 mb-2">
                <HardDrive className="w-4 h-4 text-gray-400" />
                <span className="text-xs text-gray-400 font-medium">Storage</span>
                <span className={`ml-auto text-xs font-medium ${storageNearFull ? 'text-red-400' : 'text-gray-400'}`}>
                  {usedMb.toFixed(1)} / {limitMb} MB
                </span>
              </div>
              <div className="w-full bg-white/10 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full transition-all ${storageNearFull ? 'bg-red-400' : 'bg-blue-400'}`}
                  style={{ width: `${usedPct}%` }}
                />
              </div>
              {storageNearFull && (
                <p className="text-xs text-red-400/80 mt-2">
                  Storage nearly full.{' '}
                  <button
                    onClick={() => setShowLibrary(true)}
                    className="underline hover:text-red-300"
                  >
                    Free up space
                  </button>
                </p>
              )}
            </div>
          </div>
        )}

        <div className="p-4 border-t border-white/10">
          <button
            onClick={handleLogout}
            className="w-full p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-red-300 flex items-center gap-3 hover:bg-red-500/20 transition"
          >
            <LogOut className="w-5 h-5" />
            <span className="font-medium">Logout</span>
          </button>
        </div>
      </aside>

      {/* ── MAIN CONTENT ── */}
      <main className="flex-1 flex items-center justify-center p-8">
        <div className="max-w-2xl w-full">
          <div className="text-center mb-8">
            <h2 className="text-4xl font-bold text-white mb-3">Upload Your Document</h2>
            <p className="text-gray-100 text-lg">Drop your document and start reading</p>
          </div>

          <div className="bg-white/10 backdrop-blur-xl border border-white/20 rounded-3xl p-8 shadow-2xl">
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-2xl p-12 text-center transition-all ${
                dragActive
                  ? 'border-white bg-gray-900'
                  : 'border-white/30 hover:border-white hover:bg-white/5'
              }`}
            >
              <div className="flex flex-col items-center gap-4">
                <div
                  className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${
                    dragActive ? 'bg-gray-600' : 'bg-gradient-to-br from-black to-gray-500'
                  }`}
                >
                  <Upload className="w-10 h-10 text-white" />
                </div>

                {file ? (
                  <div className="flex items-center gap-3 bg-white/5 border border-white/20 rounded-xl p-4 max-w-md">
                    <FileText className="w-10 h-10 text-white flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-white font-medium text-sm truncate">{file.name}</p>
                      <p className="text-white text-xs">{(file.size / 1024).toFixed(2)} KB</p>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); setFile(null); setError(''); }}
                    >
                      <span className="text-red-400 hover:text-white text-xl font-bold">×</span>
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-white font-medium text-lg">Drag & drop your file here</p>
                    <p className="text-white text-sm">or click to browse</p>
                    <p className="text-white/40 text-xs">PDF, DOCX, PPTX, TXT, PNG, JPG</p>
                  </div>
                )}

                <input
                  type="file"
                  onChange={(e) => { setFile(e.target.files[0]); setError(''); }}
                  className="hidden"
                  id="file-upload"
                  accept=".pdf,.jpg,.jpeg,.png,.docx,.doc,.pptx,.ppt,.txt"
                />
                <label
                  htmlFor="file-upload"
                  className="px-6 py-3 bg-white/10 hover:bg-white/20 border border-white/30 rounded-xl text-white font-medium cursor-pointer transition"
                >
                  Browse Files
                </label>
              </div>
            </div>

            {error && (
              <div className="mt-4 flex items-start gap-3 bg-red-500/20 border border-red-500/40 text-red-200 px-4 py-3 rounded-xl text-sm">
                <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            <button
              onClick={handleUpload}
              disabled={!file || isProcessing}
              className={`w-full mt-6 py-4 rounded-xl font-bold text-lg transition-all transform ${
                isProcessing
                  ? 'bg-black text-white cursor-wait scale-95'
                  : !file
                  ? 'bg-white/5 text-white/30 cursor-not-allowed'
                  : 'bg-gradient-to-r from-gray-800 to-black text-white hover:scale-105 hover:shadow-2xl hover:shadow-gray-500/50'
              }`}
            >
              {isProcessing ? (
                <span className="flex items-center justify-center gap-3">
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Processing... please wait
                </span>
              ) : (
                'Start Reading'
              )}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Dashboard;