import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  FileText, LogOut, HardDrive, Clock, BookOpen,
  Upload, LayoutDashboard, ChevronRight,
  Flame, Target, BookMarked, Search, X,
  Settings, TrendingUp, Award, Trash2
} from 'lucide-react';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement,
  Tooltip, Legend,
} from 'chart.js';
import { Bar } from 'react-chartjs-2';
import UploadSection from './UploadSection.jsx';

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

const fmt = (bytes) => {
  if (!bytes) return '0 KB';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const fmtDate = (d) =>
  d ? new Date(d).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : '';

const fmtMins = (mins) => {
  if (!mins) return '0m';
  const h = Math.floor(mins / 60);
  const m = Math.round(mins % 60);
  return h ? `${h}h ${m}m` : `${m}m`;
};

const last14Days = () => {
  const days = [];
  for (let i = 13; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    days.push(d.toISOString().split('T')[0]);
  }
  return days;
};

const dayLabel = (iso) => {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

const catIcon = (cat) => (cat === 'text' ? '📄' : '🔍');

const timeAgo = (isoStr) => {
  const diff = Math.floor((Date.now() - new Date(isoStr)) / 1000);
  if (diff < 60)    return `${diff}s ago`;
  if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
};

const Highlight = ({ text, query }) => {
  if (!query) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-blue-500/30 text-blue-200 rounded px-0.5">
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
};

const SearchBar = ({ value, onChange, placeholder = 'Search documents…', autoFocus = false }) => (
  <div className="relative">
    <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30 pointer-events-none" />
    <input
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      autoFocus={autoFocus}
      className="w-full bg-white/5 border border-white/10 rounded-2xl pl-10 pr-9 py-3 text-sm text-white placeholder-white/25 outline-none focus:border-blue-500/50 transition"
    />
    {value && (
      <button
        onClick={() => onChange('')}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    )}
  </div>
);

const ReadingGoalModal = ({ isOpen, onClose, currentGoal, onSave, isLoading }) => {
  const [goal, setGoal] = useState(currentGoal);
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-neutral-800 border border-white/10 rounded-2xl p-6 w-80">
        <h3 className="text-lg font-bold text-white mb-4">Daily Reading Goal</h3>
        <p className="text-sm text-white/50 mb-4">Set your target reading time in minutes per day.</p>
        <input
          type="number"
          min="5"
          max="480"
          value={goal}
          onChange={(e) => setGoal(parseInt(e.target.value) || 60)}
          className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white text-center text-2xl font-bold outline-none focus:border-blue-500/50 mb-4"
        />
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white/60 hover:bg-white/10 transition"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(goal)}
            disabled={isLoading}
            className="flex-1 py-2.5 bg-blue-500 rounded-xl text-white font-medium hover:bg-blue-600 transition disabled:opacity-50"
          >
            {isLoading ? 'Saving…' : 'Save Goal'}
          </button>
        </div>
      </div>
    </div>
  );
};

const ReadingDashboard = ({
  apiUrl,
  authHeaders,
  user,
  onOpenDocument,
  onUploadNew,
  onLogout,
  onAuthError,
  lastSessionId = null,  

}) => {
  // ── Unmount guard ────────────────────────────────────────────────────────
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const [stats,        setStats]        = useState(null);
  const [documents,    setDocuments]    = useState([]);
  const [storage,      setStorage]      = useState(null);
  const [loading,      setLoading]      = useState(true);
  const [activeNav,    setActiveNav]    = useState('overview');
  const [uploadError,  setUploadError]  = useState('');
  const [isUploading,  setIsUploading]  = useState(false);

  const [vocabulary,   setVocabulary]   = useState([]);
  const [vocabLoading, setVocabLoading] = useState(false);
  const [vocabSearch,  setVocabSearch]  = useState('');
  const [vocabPage,    setVocabPage]    = useState(1);
  const [vocabTotal,   setVocabTotal]   = useState(0);

  const [readingGoal,  setReadingGoal]  = useState(60);
  const [showGoalModal,setShowGoalModal]= useState(false);
  const [isSavingGoal, setIsSavingGoal] = useState(false);
const [dailyChart, setDailyChart] = useState([]);
  const [healthStatus, setHealthStatus] = useState(null);
  const [docSearch,    setDocSearch]    = useState('');
  const [overviewSearch, setOverviewSearch] = useState('');
const [deleteModal, setDeleteModal] = useState({ open: false, doc: null, deleting: false });
const [deleteError, setDeleteError] = useState('');
  const getHeaders = useCallback(() => ({
    ...authHeaders,
    'Content-Type': 'application/json',
  }), [authHeaders]);

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${apiUrl}/health`);
      if (res.ok) {
        const data = await res.json();
        if (mountedRef.current) setHealthStatus(data.status === 'ok' ? 'online' : 'degraded');
      } else if (mountedRef.current) setHealthStatus('offline');
    } catch { if (mountedRef.current) setHealthStatus('offline'); }
  }, [apiUrl]);

  const updateReadingGoal = async (newGoal) => {
    setIsSavingGoal(true);
    try {
      const res = await fetch(`${apiUrl}/me/reading-goal`, {
        method: 'PUT',
        headers: getHeaders(),
        body: JSON.stringify({ daily_goal_min: newGoal }),
      });
      if (res.status === 401) { onAuthError(); return; }
      if (!res.ok) throw new Error('Failed to update goal');
      if (mountedRef.current) {
        setReadingGoal(newGoal);
        setShowGoalModal(false);
      }
      await fetchDashboard();
    } catch (err) {
      console.error('Failed to update reading goal:', err);
    } finally {
      if (mountedRef.current) setIsSavingGoal(false);
    }
  };

  const fetchVocabulary = useCallback(async (page = 1, search = '') => {
    if (mountedRef.current) setVocabLoading(true);
    try {
      const headers = getHeaders();
      const url = search
        ? `${apiUrl}/me/vocabulary/search?q=${encodeURIComponent(search)}&page=${page}&limit=20`
        : `${apiUrl}/me/vocabulary?page=${page}&limit=20`;
      const res = await fetch(url, { headers });
      if (!mountedRef.current) return;
      if (res.status === 401) { onAuthError(); return; }
      if (!res.ok) throw new Error('Failed to fetch vocabulary');
      const data = await res.json();
      if (mountedRef.current) {
        setVocabulary(data.words || []);
        setVocabTotal(data.total || 0);
        setVocabPage(data.page || 1);
      }
    } catch (err) {
      console.error('Failed to fetch vocabulary:', err);
      if (mountedRef.current) setVocabulary([]);
    } finally {
      if (mountedRef.current) setVocabLoading(false);
    }
  }, [apiUrl, getHeaders, onAuthError]);
const fetchAllDocuments = useCallback(async () => {
    const allDocs = [];
    let page = 1;
    let hasMore = true;
    
    while (hasMore) {
      try {
        const res = await fetch(`${apiUrl}/documents?page=${page}&limit=100`, { 
          headers: getHeaders() 
        });
        if (!res.ok) break;
        
        const data = await res.json();
        const docs = data.documents || [];
        
        allDocs.push(...docs);
        
        // Stop if we got less than 100 (last page) or if total reached
        hasMore = docs.length === 100 && allDocs.length < (data.total || 0);
        page++;
      } catch (err) {
        console.error('Failed to fetch documents page', page, err);
        break;  
      }
    }
    
    if (mountedRef.current) setDocuments(allDocs);
  }, [apiUrl, getHeaders]);
   const fetchAllIndividual = useCallback(async () => {
    try {
      const [statsRes, storageRes] = await Promise.all([
        fetch(`${apiUrl}/me/stats`, { headers: getHeaders() }),
        fetch(`${apiUrl}/me/storage`, { headers: getHeaders() }),
      ]);
      if (!mountedRef.current) return;
      if ([statsRes, storageRes].some(r => r.status === 401)) { onAuthError(); return; }
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        if (mountedRef.current) {
          setStats(statsData);
          setReadingGoal(statsData.daily_goal_minutes || 60);
        }
      }
      if (storageRes.ok && mountedRef.current) setStorage(await storageRes.json());
      
      // Fetch all documents separately
      await fetchAllDocuments();
    } catch (_) {}
  }, [apiUrl, getHeaders, onAuthError, fetchAllDocuments]);

   const fetchDashboard = useCallback(async () => {
  if (mountedRef.current) setLoading(true);
  let timeMap = {};                              // ← NEW
  try {
    const headers = getHeaders();
    const res = await fetch(`${apiUrl}/me/dashboard`, { headers });
    if (!mountedRef.current) return;
    if (res.status === 401) { onAuthError(); return; }
    if (!res.ok) throw new Error('Dashboard fetch failed');
    const data = await res.json();
    if (mountedRef.current) {
      setStats(data.stats);
      setDailyChart(data.daily_chart || []);
      setVocabulary(data.vocabulary || []);
      setVocabTotal(data.vocabulary?.length || 0);
      setReadingGoal(data.stats?.daily_goal_minutes || 60);
      timeMap = {};                              // ← NEW
      (data.recent_documents || []).forEach(d => {
        timeMap[d.id] = d.time_spent_seconds ?? 0;
      });                                        // ← NEW
    }
    const storageRes = await fetch(`${apiUrl}/me/storage`, { headers });
    if (storageRes.ok && mountedRef.current) setStorage(await storageRes.json());

    await fetchAllDocuments();

    if (Object.keys(timeMap).length > 0) {      // ← NEW
      setDocuments(prev => prev.map(doc => ({
        ...doc,
        time_spent_seconds: timeMap[doc.id ?? doc.document_id] ?? doc.time_spent_seconds,
      })));
    }                                            // ← NEW
  } catch (err) {
    console.error('Dashboard fetch error:', err);
    await fetchAllIndividual();
  } finally {
    if (mountedRef.current) setLoading(false);
  }
}, [apiUrl, getHeaders, onAuthError, fetchAllIndividual, fetchAllDocuments]);

  // ── SILENT REFRESH — never sets loading=true ─────────────────────────────
    const silentRefresh = useCallback(async () => {
    try {
      const headers = getHeaders();
      const [dashRes, storageRes] = await Promise.all([
        fetch(`${apiUrl}/me/dashboard`, { headers }),
        fetch(`${apiUrl}/me/storage`, { headers }),
      ]);
      if (!mountedRef.current) return;
      if (dashRes.status === 401) { onAuthError(); return; }
      if (dashRes.ok) {
        const data = await dashRes.json();
        if (mountedRef.current) {
          setStats(data.stats);
          setDailyChart(data.daily_chart || []);
          setVocabulary(data.vocabulary || []);
          setVocabTotal(data.vocabulary?.length || 0);
          setReadingGoal(data.stats?.daily_goal_minutes || 60);
        }
      }
      if (storageRes.ok && mountedRef.current) setStorage(await storageRes.json());
      
      // Refresh all documents
      await fetchAllDocuments();
    } catch (err) {
      console.error('Silent refresh failed:', err);
    }
  }, [apiUrl, getHeaders, onAuthError, fetchAllDocuments]);

const postReadingSession = useCallback(async () => {
  if (!lastSessionId) return;
  try {
    await fetch(`${apiUrl}/reading-session/end`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ session_id: lastSessionId }),
    });
    // ← After session is recorded, re-fetch dashboard so minutes appear
    await silentRefresh();
  } catch (err) {
    console.error('Failed to post reading session:', err);
  }
}, [lastSessionId, apiUrl, getHeaders, silentRefresh]);

  useEffect(() => {
  const init = async () => {
    await fetchDashboard();
    if (lastSessionId) {
      await postReadingSession();
    }
  };
  init();
  checkHealth();
}, []);

  // ── Upload handler ────────────────────────────────────────────────────────
  const handleUpload = async (file) => {
    if (!file) return;
    setIsUploading(true);
    setUploadError('');
    try {
      await onUploadNew(file);
      if (mountedRef.current) await silentRefresh();
    } catch (err) {
      if (mountedRef.current)
        setUploadError(err?.message || 'Something went wrong. Please try again.');
    } finally {
      if (mountedRef.current) setIsUploading(false);
    }
  };
const handleDelete = async () => {
  const { doc } = deleteModal;
  if (!doc) return;
  
  setDeleteModal(prev => ({ ...prev, deleting: true }));
  setDeleteError('');
  
  try {
    const res = await fetch(`${apiUrl}/document/${doc.id || doc.document_id}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
    
    if (res.status === 401) { onAuthError(); return; }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to delete document');
    }
    
    // Remove from local state
    setDocuments(prev => prev.filter(d => (d.id || d.document_id) !== (doc.id || doc.document_id)));
    setDeleteModal({ open: false, doc: null, deleting: false });
    
    // Refresh storage and stats
    await silentRefresh();
  } catch (err) {
    setDeleteError(err.message || 'Delete failed');
  } finally {
    setDeleteModal(prev => ({ ...prev, deleting: false }));
  }
};
// Add this function
const startReadingSession = useCallback(async (documentId) => {
  try {
    const res = await fetch(`${apiUrl}/reading-session/start`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ document_id: documentId }),
    });
    if (res.status === 401) { onAuthError(); return null; }
    if (!res.ok) throw new Error('Failed to start session');
    const data = await res.json();
    return data.session_id; // Return this so parent can pass it back later
  } catch (err) {
    console.error('Failed to start reading session:', err);
    return null;
  }
}, [apiUrl, getHeaders, onAuthError]);

  // ── Derived values ────────────────────────────────────────────────────────
  const days      = last14Days();
  const dayMap    = {};
  (dailyChart || []).forEach(d => { dayMap[d.date] = d.minutes; });
  const barData   = days.map(d => dayMap[d] || 0);
  const barLabels = days.map(dayLabel);

  const totalMins  = stats?.total_time_read_minutes  ?? 0;
  const todayMins  = stats?.today_read_minutes       ?? 0;
  const streak     = stats?.current_streak_days      ?? 0;
  const bestStreak = stats?.best_streak_days         ?? 0;
  const docsRead   = stats?.documents_read           ?? 0;
  const totalDocs  = stats?.total_documents_uploaded ?? 0;
  const dailyGoal  = stats?.daily_goal_minutes       ?? readingGoal;

  const usedBytes  = storage?.used_bytes  ?? 0;
  const limitBytes = storage?.limit_bytes ?? 500 * 1024 * 1024;
  const usedMb     = usedBytes  / (1024 * 1024);
  const limitMb    = limitBytes / (1024 * 1024);
  const usedPct    = limitBytes > 0 ? Math.min((usedBytes / limitBytes) * 100, 100) : 0;
  const nearFull   = usedPct > 80;

  const displayName = user?.full_name?.split(' ')[0] || user?.email || '';
  const todayPct    = Math.min((todayMins / dailyGoal) * 100, 100);

  const filteredDocsTab  = documents.filter(d => d.filename?.toLowerCase().includes(docSearch.toLowerCase()));

  const barChartData = {
    labels: barLabels,
    datasets: [{
      label: 'Minutes',
      data: barData,
      backgroundColor: barData.map((_, i) =>
        i === barData.length - 1 ? '#6ea8fe' : 'rgba(110,168,254,0.4)'
      ),
      borderRadius: 4,
      borderSkipped: false,
    }],
  };

  const barChartOpts = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: { callbacks: { label: c => ` ${c.parsed.y} min` } },
    },
    scales: {
      x: {
        ticks: { color: 'rgba(255,255,255,0.3)', font: { size: 10 }, maxRotation: 35, autoSkip: false },
        grid: { display: false },
        border: { display: false },
      },
      y: {
        ticks: { color: 'rgba(255,255,255,0.3)', font: { size: 10 }, callback: v => `${v}m` },
        grid: { color: 'rgba(255,255,255,0.07)' },
        border: { display: false },
        beginAtZero: true,
      },
    },
  };

  // ── Upload card (shared between overview & upload tab) ───────────────────
  const UploadCard = (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Upload className="w-4 h-4 text-blue-400" />
          <p className="text-sm font-medium text-white/70">Upload New Document</p>
        </div>
        {activeNav === 'overview' && (
          <button
            onClick={() => setActiveNav('upload')}
            className="text-[11px] text-blue-400 hover:text-blue-300 transition"
          >
            Full upload page →
          </button>
        )}
      </div>
      <UploadSection
        onUpload={handleUpload}
        isProcessing={isUploading}
        error={uploadError}
      />
    </div>
  );

  // ── Skeleton components ──────────────────────────────────────────────────
  const StatCardSkeleton = () => (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-4 animate-pulse">
      <div className="h-3 w-24 bg-white/10 rounded mb-4" />
      <div className="h-7 w-16 bg-white/10 rounded mb-2" />
      <div className="h-2 w-20 bg-white/10 rounded" />
    </div>
  );

  const DocItemSkeleton = () => (
    <div className="w-full flex items-center gap-4 p-4 bg-white/5 border border-white/10 rounded-2xl animate-pulse">
      <div className="w-11 h-11 rounded-xl bg-white/10 flex-shrink-0" />
      <div className="flex-1">
        <div className="h-4 w-48 bg-white/10 rounded mb-2" />
        <div className="h-2 w-32 bg-white/10 rounded" />
      </div>
      <div className="h-4 w-12 bg-white/10 rounded" />
    </div>
  );

  const VocabItemSkeleton = () => (
    <div className="rounded-2xl overflow-hidden border border-white/10 bg-white/5 p-4 animate-pulse">
      <div className="flex items-center gap-4">
        <div className="w-11 h-11 rounded-xl bg-white/10 flex-shrink-0" />
        <div className="flex-1">
          <div className="h-4 w-24 bg-white/10 rounded mb-2" />
          <div className="h-2 w-40 bg-white/10 rounded" />
        </div>
      </div>
    </div>
  );

 const ChartSkeleton = () => (
  <div className="bg-white/5 border border-white/10 rounded-2xl p-5 animate-pulse" style={{ height: 340 }}>
    <div className="h-4 w-40 bg-white/10 rounded mb-6" />
    <div className="flex items-end gap-2 h-52">  {/* increased from h-36 */}
      {[40,70,30,90,50,80,60,45,75,55,85,65,95,100].map((h,i) => (
        <div key={i} className="flex-1 bg-white/10 rounded-sm" style={{ height: `${h}%` }} />
      ))}
    </div>
  </div>
);
const DeleteModal = () => {
  const { open, doc, deleting } = deleteModal;
  if (!open || !doc) return null;
  
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-neutral-800 border border-white/10 rounded-2xl p-6 w-96">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-red-500/15 flex items-center justify-center">
            <Trash2 className="w-5 h-5 text-red-400" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Delete Document</h3>
            <p className="text-xs text-white/40">This action cannot be undone</p>
          </div>
        </div>
        
        <p className="text-sm text-white/60 mb-1">
          Are you sure you want to delete:
        </p>
        <p className="text-sm font-medium text-white mb-4 truncate">
          {doc.filename}
        </p>
        
        {deleteError && (
          <p className="text-xs text-red-400 mb-3 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
            {deleteError}
          </p>
        )}
        
        <div className="flex gap-3">
          <button
            onClick={() => {
              setDeleteModal({ open: false, doc: null, deleting: false });
              setDeleteError('');
            }}
            disabled={deleting}
            className="flex-1 py-2.5 bg-white/5 border border-white/10 rounded-xl text-white/60 hover:bg-white/10 transition disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="flex-1 py-2.5 bg-red-500 rounded-xl text-white font-medium hover:bg-red-600 transition disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {deleting ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Deleting…
              </>
            ) : (
              'Delete'
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
  return (
    <div className="flex h-screen bg-neutral-900 text-white overflow-hidden">

 
    <DeleteModal />
   
      {/* ── SIDEBAR ── */}
      <aside className="w-[230px] flex-shrink-0 bg-black/20 border-r border-white/10 flex flex-col">
        <div className="p-5 border-b border-white/10">
          <h1 className="text-xl font-bold font-serif">ReadWithEase</h1>
          <p className="text-[11px] text-white/35 mt-0.5">AI-Powered Reading Companion</p>
          {displayName && <p className="text-[11px] text-blue-400 mt-1.5">👋 Hey, {displayName}</p>}
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {[
            { id: 'overview',   icon: LayoutDashboard, label: 'Overview' },
            { id: 'upload',     icon: Upload,          label: 'Upload Document' },
            { id: 'documents',  icon: FileText,        label: 'My Documents',  badge: totalDocs > 0 ? totalDocs : null },
            { id: 'vocabulary', icon: BookMarked,      label: 'My Vocabulary', badge: vocabTotal > 0 ? vocabTotal : null },
            { id: 'history',    icon: Clock,           label: 'Reading History' },
          ].map(({ id, icon: Icon, label, badge }) => (
            <button
              key={id}
              onClick={() => {
                setActiveNav(id);
                if (id === 'vocabulary') fetchVocabulary();
              }}
              className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm transition-all ${
                activeNav === id
                  ? 'bg-white/10 text-white'
                  : 'text-white/50 hover:bg-white/5 hover:text-white'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span className="font-medium">{label}</span>
              {badge && (
                <span className="ml-auto text-[11px] bg-white/10 text-white/50 px-2 py-0.5 rounded-full">
                  {badge}
                </span>
              )}
              {activeNav === id && <ChevronRight className="w-3 h-3 ml-auto text-white/30" />}
            </button>
          ))}
        </nav>

        {storage && (
          <div className="px-3 pb-2">
            <div className="bg-white/5 border border-white/10 rounded-xl p-3">
              <div className="flex items-center gap-2 mb-2">
                <HardDrive className="w-3.5 h-3.5 text-white/40" />
                <span className="text-[11px] text-white/40 font-medium">Storage</span>
                <span className={`ml-auto text-[11px] font-medium ${nearFull ? 'text-red-400' : 'text-white/40'}`}>
                  {usedMb.toFixed(1)} / {limitMb.toFixed(0)} MB
                </span>
              </div>
              <div className="w-full bg-white/10 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full transition-all ${nearFull ? 'bg-red-400' : 'bg-blue-400'}`}
                  style={{ width: `${usedPct}%` }}
                />
              </div>
            </div>
          </div>
        )}

        <div className="p-3 border-t border-white/10">
          <button
            onClick={onLogout}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 bg-red-500/10 border border-red-500/30 rounded-xl text-red-300 text-sm hover:bg-red-500/20 transition"
          >
            <LogOut className="w-4 h-4" />
            <span className="font-medium">Logout</span>
          </button>
        </div>
      </aside>

      {/* ── MAIN ── */}
      <main className="flex-1 overflow-y-auto p-6 space-y-5">

        <ReadingGoalModal
          isOpen={showGoalModal}
          onClose={() => setShowGoalModal(false)}
          currentGoal={dailyGoal}
          onSave={updateReadingGoal}
          isLoading={isSavingGoal}
        />

        {activeNav === 'upload' && (
          <>
            <div>
              <h2 className="text-2xl font-bold">Upload Document</h2>
              <p className="text-sm text-white/40 mt-0.5">Add a new document to your library</p>
            </div>

            {storage && (
              <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-sm ${
                nearFull
                  ? 'bg-red-500/10 border-red-500/30 text-red-300'
                  : 'bg-white/5 border-white/10 text-white/50'
              }`}>
                <HardDrive className="w-4 h-4 flex-shrink-0" />
                <span>
                  {usedMb.toFixed(1)} MB used of {limitMb.toFixed(0)} MB
                  {nearFull && ' — storage nearly full'}
                </span>
                <div className="flex-1 bg-white/10 rounded-full h-1.5 ml-2">
                  <div
                    className={`h-1.5 rounded-full ${nearFull ? 'bg-red-400' : 'bg-blue-400'}`}
                    style={{ width: `${usedPct}%` }}
                  />
                </div>
                <span className="flex-shrink-0">{usedPct.toFixed(0)}%</span>
              </div>
            )}

            <div className="flex justify-center">
              <div className="w-full max-w-2xl">
                {UploadCard}
              </div>
            </div>
          </>
        )}

        {/*
            OVERVIEW TAB
        */}
        {activeNav === 'overview' && (
          <>
            {/* Header — always visible */}
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold">Your Reading Dashboard</h2>
                <p className="text-sm text-white/40 mt-0.5">
                  {new Date().toLocaleDateString(undefined, {
                    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
                  })}
                </p>
              </div>
              <button
                onClick={() => setShowGoalModal(true)}
                className="flex items-center gap-2 px-4 py-2 bg-white/5 border border-white/10 rounded-xl text-sm text-white/60 hover:bg-white/10 hover:text-white transition"
              >
                <Target className="w-4 h-4" />
                Goal: {dailyGoal}m
              </button>
            </div>

            {/* Stat cards — shimmer while loading, real data after */}
            {loading ? (
              <div className="grid grid-cols-4 gap-3">
                {[0,1,2,3].map(i => <StatCardSkeleton key={i} />)}
              </div>
            ) : (
              <div className="grid grid-cols-4 gap-3">
                {[
                  { icon: Clock,    label: 'Total time read',  value: fmtMins(totalMins), sub: 'All time' },
                  { icon: Target,   label: "Today's reading",  value: fmtMins(todayMins), sub: `Goal: ${dailyGoal} min`, progress: todayPct },
                  { icon: BookOpen, label: 'Documents read',   value: docsRead,            sub: `${totalDocs} uploaded` },
                  { icon: Flame,    label: 'Current streak',   value: `${streak}d`,        sub: `Best: ${bestStreak} days` },
                ].map(({ icon: Icon, label, value, sub, progress }) => (
                  <div key={label} className="bg-white/5 border border-white/10 rounded-2xl p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <Icon className="w-4 h-4 text-white/40" />
                      <span className="text-[11px] text-white/40">{label}</span>
                    </div>
                    <p className="text-2xl font-bold">{value}</p>
                    {progress != null && (
                      <div className="w-full bg-white/10 rounded-full h-1 my-2">
                        <div className="h-1 rounded-full bg-blue-400" style={{ width: `${progress}%` }} />
                      </div>
                    )}
                    <p className="text-[11px] mt-1.5 text-white/30">{sub}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Upload card — ALWAYS visible */}
            <div className="w-[800px] ml-55">
              {UploadCard}
            </div>

            {/* Rest of overview — shimmer while loading */}
            {loading ? (
              <div className="space-y-4">
                <ChartSkeleton />
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-white/5 border border-white/10 rounded-2xl p-5 animate-pulse h-48" />
                  <div className="bg-white/5 border border-white/10 rounded-2xl p-5 animate-pulse h-48" />
                </div>
              </div>
            ) : (
              <>
                <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <p className="text-sm font-medium text-white/70">Daily reading time</p>
                      <p className="text-[11px] text-white/30 mt-0.5">Last 14 days · minutes</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-sm bg-blue-400 opacity-40 inline-block" />
                      <span className="text-[11px] text-white/30">Past days</span>
                      <span className="w-2.5 h-2.5 rounded-sm bg-blue-400 inline-block ml-3" />
                      <span className="text-[11px] text-white/30">Today</span>
                    </div>
                  </div>
                  <div style={{ height: 190 }}>
                    <Bar data={barChartData} options={barChartOpts} />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  {/* Recent docs - only show 10 with "View all" link */}
<div className="bg-white/5 border border-white/10 rounded-2xl p-5">
  <div className="flex items-center justify-between mb-3">
    <p className="text-sm font-medium text-white/70">Recent documents</p>
    {documents.length > 0 && (
      <span className="text-[11px] text-white/30">
        {overviewSearch ? `${documents.filter(d => d.filename?.toLowerCase().includes(overviewSearch.toLowerCase())).length} of ${documents.length}` : `${Math.min(10, documents.length)} of ${documents.length}`}
      </span>
    )}
  </div>

  {documents.length > 0 && (
    <div className="relative mb-3">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/25 pointer-events-none" />
      <input
        type="text"
        value={overviewSearch}
        onChange={e => setOverviewSearch(e.target.value)}
        placeholder="Search recent docs…"
        className="w-full bg-white/5 border border-white/10 rounded-xl pl-8 pr-7 py-2 text-xs text-white placeholder-white/25 outline-none focus:border-blue-500/40 transition"
      />
      {overviewSearch && (
        <button onClick={() => setOverviewSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-white/25 hover:text-white/50 transition">
          <X className="w-3 h-3" />
        </button>
      )}
    </div>
  )}

  <div className="space-y-1">
    {documents.length === 0 && (
      <p className="text-sm text-white/30 py-4 text-center">No documents yet.</p>
    )}
    {documents.length > 0 && documents.filter(d => d.filename?.toLowerCase().includes(overviewSearch.toLowerCase())).length === 0 && (
      <div className="flex flex-col items-center py-6 text-center">
        <Search className="w-6 h-6 text-white/15 mb-2" />
        <p className="text-xs text-white/30">No documents match "{overviewSearch}"</p>
      </div>
    )}
    {documents
      .filter(d => d.filename?.toLowerCase().includes(overviewSearch.toLowerCase()))
      .slice(0, 10) // ← Only show first 10
      .map((doc) => {
        const id = doc.id || doc.document_id;
        return (
          <button
  key={id}
  onClick={async () => {
  const sessionId = await startReadingSession(id);
  onOpenDocument({ ...doc, id, sessionId });
}}
  className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-white/5 transition text-left group relative"
>
  <div className="w-9 h-9 rounded-lg bg-white/8 flex items-center justify-center text-base flex-shrink-0">
    {catIcon(doc.document_category || doc.file_type)}
  </div>
  <div className="flex-1 min-w-0">
    <p className="text-sm font-medium text-white truncate">
      <Highlight text={doc.filename} query={overviewSearch} />
    </p>
    <p className="text-[11px] text-white/35 mt-0.5">
      {doc.total_pages || 0} pages · {fmt(doc.file_size_bytes)} · {fmtDate(doc.created_at)}
    </p>
  </div>
  <div className="text-right flex-shrink-0">
    <p className="text-sm text-white/50">
      {doc.time_spent_seconds ? fmtMins(doc.time_spent_seconds / 60) : '—'}
    </p>
    <p className="text-[10px] text-white/25 mt-0.5">time spent</p>
  </div>
  
  {/* Delete button - appears on hover */}
  <button
    onClick={(e) => {
      e.stopPropagation();
      setDeleteModal({ open: true, doc, deleting: false });
      setDeleteError('');
    }}
    className="opacity-0 group-hover:opacity-100 transition p-1.5 rounded-lg hover:bg-red-500/15 text-white/20 hover:text-red-400"
    title="Delete document"
  >
    <Trash2 className="w-3.5 h-3.5" />
  </button>
  
  <ChevronRight className="w-4 h-4 text-white/20 opacity-0 group-hover:opacity-100 transition" />
</button>
        );
      })}
  </div>

  {/* View all link - only show if more than 10 documents */}
  {documents.length > 10 && !overviewSearch && (
    <button
      onClick={() => setActiveNav('documents')}
      className="w-full mt-3 py-2 text-center text-[11px] text-blue-400 hover:text-blue-300 transition border-t border-white/10"
    >
      View all {documents.length} documents →
    </button>
  )}
</div>
                  {/* Vocabulary preview */}
                  <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <BookMarked className="w-4 h-4 text-purple-400" />
                        <p className="text-sm font-medium text-white/70">Recent Vocabulary</p>
                      </div>
                      <button onClick={() => { setActiveNav('vocabulary'); fetchVocabulary(); }} className="text-[11px] text-blue-400 hover:text-blue-300 transition">View all</button>
                    </div>
                    {vocabulary.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-10 text-white/20"><BookMarked className="w-7 h-7 mb-2" /><p className="text-xs">No words looked up yet.</p></div>
                    ) : (
                      <div className="space-y-2">
                        {vocabulary.slice(0, 5).map((item) => (
                          <div key={item.word} className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5 transition">
                            <div className="w-8 h-8 rounded-lg bg-purple-500/15 flex items-center justify-center text-sm flex-shrink-0">📖</div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-white">{item.word}</p>
                              <p className="text-[11px] text-white/35 truncate">{item.meaning}</p>
                            </div>
                            <span className="text-[10px] text-white/25">{timeAgo(item.looked_up_at)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
          </>
        )}

        {/* 
            DOCUMENTS TAB 
       */}
        {activeNav === 'documents' && (
          <>
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold">My Documents</h2>
              {loading ? (
                <div className="h-5 w-24 bg-white/10 rounded animate-pulse" />
              ) : (
                <span className="text-sm text-white/40">
                  {docSearch ? `${filteredDocsTab.length} of ${documents.length} document${documents.length !== 1 ? 's' : ''}` : `${documents.length} document${documents.length !== 1 ? 's' : ''}`}
                </span>
              )}
            </div>

            <SearchBar value={docSearch} onChange={setDocSearch} placeholder="Search by filename…" autoFocus />

            {loading ? (
              <div className="space-y-2">
                {[1,2,3,4,5].map(i => <DocItemSkeleton key={i} />)}
              </div>
            ) : (
              <div className="space-y-2">
                {documents.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-20 text-center">
                    <BookOpen className="w-12 h-12 text-white/20 mb-3" />
                    <p className="text-white/40 text-sm">No documents yet.</p>
                  </div>
                )}
                {documents.length > 0 && filteredDocsTab.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-20 text-center">
                    <Search className="w-12 h-12 text-white/20 mb-3" />
                    <p className="text-white/40 text-sm">No documents match "{docSearch}"</p>
                    <button onClick={() => setDocSearch('')} className="mt-3 text-xs text-blue-400 hover:text-blue-300 transition">Clear search</button>
                  </div>
                )}
                {filteredDocsTab.map((doc) => {
                  const id = doc.id || doc.document_id;
                  return (
                    <button
  key={id}
  onClick={async () => {
  const sessionId = await startReadingSession(id);
  onOpenDocument({ ...doc, id, sessionId });
}}
  
  className="w-full flex items-center gap-4 p-4 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 rounded-2xl transition text-left group relative"
>
  <div className="w-11 h-11 rounded-xl bg-white/10 flex items-center justify-center text-xl flex-shrink-0">
    {catIcon(doc.document_category || doc.file_type)}
  </div>
  <div className="flex-1 min-w-0">
    <p className="text-white font-medium truncate">
      <Highlight text={doc.filename} query={docSearch} />
    </p>
    <p className="text-[11px] text-white/35 mt-0.5">
      {doc.total_pages || 0} pages · {fmt(doc.file_size_bytes)} · {fmtDate(doc.created_at)}
    </p>
  </div>
  <div className="text-right flex-shrink-0">
    <p className="text-sm text-white/50">
      {doc.time_spent_seconds ? fmtMins(doc.time_spent_seconds / 60) : '—'}
    </p>
    <p className="text-[10px] text-white/25 mt-0.5">time spent</p>
  </div>
  
  {/* Delete button - appears on hover */}
  <button
    onClick={(e) => {
      e.stopPropagation();
      setDeleteModal({ open: true, doc, deleting: false });
      setDeleteError('');
    }}
    className="opacity-0 group-hover:opacity-100 transition p-2 rounded-lg hover:bg-red-500/15 text-white/20 hover:text-red-400"
    title="Delete document"
  >
    <Trash2 className="w-4 h-4" />
  </button>
  
  <ChevronRight className="w-4 h-4 text-white/20 opacity-0 group-hover:opacity-100 transition" />
</button>
                  );
                })}
              </div>
            )}
          </>
        )}

        {/* ══════════════════════════════════════════════════════════════════
            VOCABULARY TAB — shimmer loaders instead of full-page spinner
        ══════════════════════════════════════════════════════════════════ */}
        {activeNav === 'vocabulary' && (
          <>
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold">My Vocabulary</h2>
                <p className="text-sm text-white/40 mt-0.5">Words you've looked up while reading</p>
              </div>
              {loading ? (
                <div className="h-5 w-16 bg-white/10 rounded animate-pulse" />
              ) : (
                <span className="text-sm text-white/40">{vocabTotal} word{vocabTotal !== 1 ? 's' : ''}</span>
              )}
            </div>

            <div className="relative mb-4">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30 pointer-events-none" />
              <input
                type="text"
                value={vocabSearch}
                onChange={e => { setVocabSearch(e.target.value); fetchVocabulary(1, e.target.value); }}
                placeholder="Search words, meanings, or documents…"
                className="w-full bg-white/5 border border-white/10 rounded-2xl pl-10 pr-9 py-3 text-sm text-white placeholder-white/25 outline-none focus:border-purple-500/50 transition"
              />
              {vocabSearch && (
                <button onClick={() => { setVocabSearch(''); fetchVocabulary(); }} className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition">
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {loading ? (
              <div className="space-y-2">
                {[1,2,3,4,5].map(i => <VocabItemSkeleton key={i} />)}
              </div>
            ) : (
              <div className="space-y-2">
                {vocabulary.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-20 text-center">
                    <BookMarked className="w-12 h-12 text-white/20 mb-3" />
                    <p className="text-white/40 text-sm">No words looked up yet.</p>
                    <p className="text-white/20 text-xs mt-1">Start reading and click "Meaning" on any word!</p>
                  </div>
                )}
                {vocabulary.map((item) => (
                  <div key={item.word} className="rounded-2xl overflow-hidden border border-white/10 bg-white/5 hover:border-white/20 transition">
                    <div className="flex items-center gap-4 p-4">
                      <div className="w-11 h-11 rounded-xl bg-purple-500/15 flex items-center justify-center text-lg flex-shrink-0">📖</div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-white font-medium">{item.word}</span>
                          {item.synonym && <span className="text-[10px] text-purple-300 bg-purple-500/10 px-2 py-0.5 rounded-full">{item.synonym}</span>}
                        </div>
                        <p className="text-[11px] text-white/35 mt-0.5 line-clamp-2">{item.meaning}</p>
                      </div>
                      <div className="text-right flex-shrink-0">
                        {item.document_name && <p className="text-xs text-white/40">{item.document_name}</p>}
                        <p className="text-[10px] text-white/25 mt-0.5">{timeAgo(item.looked_up_at)}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!loading && vocabTotal > 20 && (
              <div className="flex items-center justify-center gap-2 mt-4">
                <button onClick={() => fetchVocabulary(Math.max(1, vocabPage - 1), vocabSearch)} disabled={vocabPage === 1 || vocabLoading} className="px-3 py-1.5 bg-white/5 border border-white/10 rounded-lg text-sm text-white/60 hover:bg-white/10 disabled:opacity-30 transition">Previous</button>
                <span className="text-sm text-white/40">Page {vocabPage}</span>
                <button onClick={() => fetchVocabulary(vocabPage + 1, vocabSearch)} disabled={vocabPage * 20 >= vocabTotal || vocabLoading} className="px-3 py-1.5 bg-white/5 border border-white/10 rounded-lg text-sm text-white/60 hover:bg-white/10 disabled:opacity-30 transition">Next</button>
              </div>
            )}
          </>
        )}

        {/* 
            HISTORY TAB 
        */}
       {activeNav === 'history' && (
  <>
    <div className="flex items-center justify-between">
      <div>
        <h2 className="text-2xl font-bold">Reading History</h2>
        <p className="text-sm text-white/40 mt-0.5">Your reading activity over the last 14 days</p>
      </div>
      <button
        onClick={() => setShowGoalModal(true)}
        className="flex items-center gap-2 px-4 py-2 bg-white/5 border border-white/10 rounded-xl text-sm text-white/60 hover:bg-white/10 hover:text-white transition"
      >
        <Target className="w-4 h-4" />
        Goal: {dailyGoal}m
      </button>
    </div>

    {/* Same stat cards as Overview */}
    {loading ? (
      <div className="grid grid-cols-4 gap-3">
        {[0,1,2,3].map(i => <StatCardSkeleton key={i} />)}
      </div>
    ) : (
      <div className="grid grid-cols-4 gap-3">
        {[
          { icon: Clock,    label: 'Total time read',  value: fmtMins(totalMins), sub: 'All time' },
          { icon: Target,   label: "Today's reading",  value: fmtMins(todayMins), sub: `Goal: ${dailyGoal} min`, progress: todayPct },
          { icon: BookOpen, label: 'Documents read',   value: docsRead,            sub: `${totalDocs} uploaded` },
          { icon: Flame,    label: 'Current streak',   value: `${streak}d`,        sub: `Best: ${bestStreak} days` },
        ].map(({ icon: Icon, label, value, sub, progress }) => (
          <div key={label} className="bg-white/5 border border-white/10 rounded-2xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <Icon className="w-4 h-4 text-white/40" />
              <span className="text-[11px] text-white/40">{label}</span>
            </div>
            <p className="text-2xl font-bold">{value}</p>
            {progress != null && (
              <div className="w-full bg-white/10 rounded-full h-1 my-2">
                <div className="h-1 rounded-full bg-blue-400" style={{ width: `${progress}%` }} />
              </div>
            )}
            <p className="text-[11px] mt-1.5 text-white/30">{sub}</p>
          </div>
        ))}
      </div>
    )}

    {/* Bigger chart */}
    {loading ? (
      <ChartSkeleton />
    ) : (
      <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm font-medium text-white/70">Daily reading time</p>
            <p className="text-[11px] text-white/30 mt-0.5">Last 14 days · minutes</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-sm bg-blue-400 opacity-40 inline-block" />
            <span className="text-[11px] text-white/30">Past days</span>
            <span className="w-2.5 h-2.5 rounded-sm bg-blue-400 inline-block ml-3" />
            <span className="text-[11px] text-white/30">Today</span>
          </div>
        </div>
        <div style={{ height: 340 }}>
          <Bar data={barChartData} options={barChartOpts} />
        </div>
      </div>
    )}
  </>
)}
      </main>
    </div>
  );
};

export default ReadingDashboard;