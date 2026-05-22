import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
import Workspace from './Workspace.jsx';
import ReadingDashboard from './ReadingDashboard.jsx';

const API_URL = import.meta.env.VITE_DOCUMENT_API_URL || 'http://localhost:8001';

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

  // ── Workspace state ───────────────────────────────────────────────────────
  const [isInWorkspace,    setIsInWorkspace]    = useState(false);
  const [documentId,       setDocumentId]       = useState(null);
  const [documentName,     setDocumentName]     = useState('');
  const [totalPages,       setTotalPages]       = useState(0);
  const [documentCategory, setDocumentCategory] = useState('');
  const [lastSessionId,    setLastSessionId]    = useState(null);

  // ── Loading / auth guard ──────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex h-screen bg-neutral-900 items-center justify-center">
        <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  if (!accessToken) {
    navigate('/?showLogin=true', { replace: true });
    return null;
  }

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleUpload = async (file) => {
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_URL}/upload`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: formData,
    });
    if (res.status === 401) { handleAuthError(); return; }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Upload failed (${res.status})`);
    }
    const data = await res.json();
    // After upload, open the document in workspace
    setDocumentId(data.document_id || data.id);
    setDocumentName(file.name);
    setTotalPages(data.total_pages || 0);
    setDocumentCategory(data.document_category || '');
    setLastSessionId(null);
    setIsInWorkspace(true);
  };

  const handleOpenDocument = async (doc) => {
    const docId = doc.id || doc.document_id;
    setLastSessionId(doc.sessionId || null);
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
    }
    setIsInWorkspace(true);
  };

  const handleBackFromWorkspace = () => {
    setIsInWorkspace(false);
    setDocumentId(null);
    setDocumentName('');
    setDocumentCategory('');
  };

  const handleLogout = () => {
    logout();
    navigate('/', { replace: true });
  };

  // ── Workspace ─────────────────────────────────────────────────────────────
  if (isInWorkspace) {
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

  // ── Always show ReadingDashboard (new + returning users) ──────────────────
  return (
    <ReadingDashboard
      apiUrl={API_URL}
      authHeaders={getAuthHeaders()}
      user={user}
      onOpenDocument={handleOpenDocument}
      onUploadNew={handleUpload}
      onLogout={handleLogout}
      onAuthError={handleAuthError}
      lastSessionId={lastSessionId}
    />
  );
};

export default Dashboard;