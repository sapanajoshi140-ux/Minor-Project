import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Upload, FileText, LogOut, ChevronRight, AlertCircle, HardDrive, Trash2, RefreshCw, X, Clock, BookOpen } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
import Workspace from './Workspace.jsx';
import ReadingDashboard from './ReadingDashboard.jsx';
import UploadSection from './UploadSection.jsx';


const API_URL = import.meta.env.VITE_DOCUMENT_API_URL || 'http://localhost:8001';

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

const categoryIcon  = (cat) => cat === 'text' ? '📄' : '🔍';
const categoryLabel = (cat) => cat === 'text' ? 'Digital' : 'Scanned';

const Dashboard = () => {
  const navigate = useNavigate();
  const { logout, accessToken, user, loading } = useAuth();

  const handleAuthError = useCallback(() => {
    logout();
    navigate('/?showLogin=true', { replace: true });
  }, [logout, navigate]);

  const getAuthHeaders = useCallback(() => ({
    Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
  }), []);

  const [isProcessing,     setIsProcessing]     = useState(false);
  const [error,            setError]            = useState('');
  const [isProcessed,      setIsProcessed]      = useState(false);
  const [documentId,       setDocumentId]       = useState(null);
  const [documentName,     setDocumentName]     = useState('');
  const [totalPages,       setTotalPages]       = useState(0);
  const [documentCategory, setDocumentCategory] = useState('');
  const [storageInfo,      setStorageInfo]      = useState(null);
  const [showLibrary,      setShowLibrary]      = useState(false);
  const [documents,        setDocuments]        = useState([]);
  const [docsLoading,      setDocsLoading]      = useState(false);
  const [docsError,        setDocsError]        = useState('');
  const [docsPage,         setDocsPage]         = useState(1);
  const [docsTotal,        setDocsTotal]        = useState(0);
  const [deletingId,       setDeletingId]       = useState(null);
  const [openingDocId,     setOpeningDocId]     = useState(null);
  const [showDashboard,    setShowDashboard]    = useState(null); // null = still checking
 const [lastSessionId, setLastSessionId] = useState(null);
  const [lastSessionMins,  setLastSessionMins]  = useState(0);

  const DOCS_LIMIT = 10;

  const fetchStorage = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/me/storage`, { headers: getAuthHeaders() });
      if (res.status === 401) { handleAuthError(); return; }
      if (res.ok) {
        const data = await res.json();
        setStorageInfo({
          used_bytes:      data.used_bytes  ?? (data.used_mb  != null ? data.used_mb  * 1024 * 1024 : 0),
          limit_bytes:     data.limit_bytes ?? (data.limit_mb != null ? data.limit_mb * 1024 * 1024 : 500 * 1024 * 1024),
          used_mb:         data.used_mb     ?? (data.used_bytes  != null ? data.used_bytes  / (1024 * 1024) : 0),
          limit_mb:        data.limit_mb    ?? (data.limit_bytes != null ? data.limit_bytes / (1024 * 1024) : 500),
          available_bytes: data.available_bytes ?? 0,
        });
      }
    } catch (_) {}
  }, [getAuthHeaders, handleAuthError]);

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
  }, [getAuthHeaders, handleAuthError]);

  // Check if user has any documents to decide which screen to show
  useEffect(() => {
    if (!accessToken) return;
    fetch(`${API_URL}/documents?page=1&limit=1`, { headers: getAuthHeaders() })
      .then(r => {
        if (r.status === 401) { handleAuthError(); return null; }
        return r.json();
      })
      .then(data => {
        if (data !== null) setShowDashboard(data.total > 0);
      })
      .catch(() => setShowDashboard(false));
  }, [accessToken, getAuthHeaders, handleAuthError]);

  useEffect(() => {
    if (!accessToken) return;
    fetchStorage();
  }, [accessToken, fetchStorage]);

  useEffect(() => {
    if (showLibrary) fetchDocuments(1);
  }, [showLibrary, fetchDocuments]);

  useEffect(() => {
    if (!isProcessed) return;
    const handleBackButton = () => {
      setIsProcessed(false);
      setDocumentId(null);
      setDocumentName('');
      window.history.pushState(null, '', window.location.pathname);
    };
    window.history.pushState(null, '', window.location.pathname);
    window.addEventListener('popstate', handleBackButton);
    return () => window.removeEventListener('popstate', handleBackButton);
  }, [isProcessed]);

  // ── Early returns AFTER all hooks ─────────────────────────────────────────

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

  // ── Handlers ──────────────────────────────────────────────────────────────

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

  const handleOpenFromLibrary = async (doc) => {
    const docId = doc.document_id || doc.id;
    const sessionId = doc.sessionId || null;  
  setLastSessionId(sessionId);  
    setOpeningDocId(docId);
    try {
      const res = await fetch(`${API_URL}/document/${docId}`, { headers: getAuthHeaders() });
      if (res.status === 401) { handleAuthError(); return; }
      if (res.ok) {
        const meta = await res.json();
        setDocumentId(meta.document_id || meta.id || docId);
        setDocumentName(meta.filename || doc.filename || '');
        setTotalPages(meta.total_pages || doc.total_pages || 0);
        setDocumentCategory(meta.document_category || doc.document_category || '');
      } else {
        setDocumentId(docId);
        setDocumentName(doc.filename || '');
        setTotalPages(doc.total_pages || 0);
        setDocumentCategory(doc.document_category || '');
      }
    } catch {
      setDocumentId(docId);
      setDocumentName(doc.filename || '');
      setTotalPages(doc.total_pages || 0);
      setDocumentCategory(doc.document_category || '');
    } finally {
      setOpeningDocId(null);
      setShowLibrary(false);
      setShowDashboard(false);
      setIsProcessed(true);
    }
  };

 const handleBackFromWorkspace = () => {
  setIsProcessed(false);
  setDocumentId(null);
  setDocumentName('');
  setDocumentCategory('');
  setShowDashboard(true);
  fetchStorage();
  
};
  const handleUpload = async (fileArg) => {
    const uploadFile = fileArg;
    if (!uploadFile) return;
    setIsProcessing(true);
    setError('');
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
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
      const docId = uploadData.document_id || uploadData.id;
      setDocumentId(docId);
      setDocumentName(uploadFile.name);
      setTotalPages(uploadData.total_pages || 0);
      setDocumentCategory(uploadData.document_category || '');
      setIsProcessing(false);
      setIsProcessed(true);
      setShowDashboard(true);
      await fetchStorage();
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.');
      setIsProcessing(false);
    }
  };

  const handleLogout = () => { logout(); navigate('/', { replace: true }); };

  // ── Derived values ────────────────────────────────────────────────────────

  const usedBytes       = storageInfo?.used_bytes  ?? 0;
  const limitBytes      = storageInfo?.limit_bytes ?? (500 * 1024 * 1024);
  const usedMb          = usedBytes  / (1024 * 1024);
  const limitMb         = limitBytes / (1024 * 1024);
  const usedPct         = limitBytes > 0 ? Math.min((usedBytes / limitBytes) * 100, 100) : 0;
  const storageNearFull = usedPct > 80;
  const displayName     = user?.full_name?.split(' ')[0] || user?.email || '';
  const totalPages_     = Math.ceil(docsTotal / DOCS_LIMIT);

  // ── Workspace ─────────────────────────────────────────────────────────────

  if (isProcessed) {
    return (
      <Workspace
        documentId={documentId}
        documentName={documentName}
        totalPages={totalPages}
        documentCategory={documentCategory}
        apiUrl={API_URL}
        authHeaders={getAuthHeaders()}
        onBack={handleBackFromWorkspace}
        onAuthError={handleAuthError}
      />
    );
  }

  // ── Still checking which screen to show ───────────────────────────────────

  if (showDashboard === null) {
    return (
      <div className="flex h-screen bg-neutral-900 items-center justify-center">
        <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  // ── ReadingDashboard (returning users) ────────────────────────────────────

  if (showDashboard === true) {
    return (
      <ReadingDashboard
        apiUrl={API_URL}
        authHeaders={getAuthHeaders()}
        user={user}
        onOpenDocument={handleOpenFromLibrary}
        onUploadNew={handleUpload}
        onLogout={handleLogout}
        onAuthError={handleAuthError}
        lastSessionId={lastSessionId}
      />
    );
  }

  // ── Upload screen (new users, showDashboard === false) ────────────────────

  return (
    <div className="flex h-screen bg-neutral-900 items-center justify-center">
      <div className="max-w-2xl w-full px-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold font-serif text-white mb-1">ReadWithEase</h1>
          <p className="text-white/40 text-sm mb-6">Your AI-Powered Reading Companion</p>
          <h2 className="text-4xl font-bold text-white mb-3">Upload Your Document</h2>
          <p className="text-gray-400 text-lg">Drop your document and start reading</p>
        </div>

        <UploadSection
          onUpload={handleUpload}
          isProcessing={isProcessing}
          error={error}
        />

        <div className="text-center mt-6">
          <button
            onClick={handleLogout}
            className="text-white/30 hover:text-white/60 text-sm transition"
          >
            Logout
          </button>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;