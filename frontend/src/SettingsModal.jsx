import React, { useState, useEffect, useRef } from 'react';
import {
  X, Lock, Eye, EyeOff, Check, Shield, Chrome,
} from 'lucide-react';

// ── tiny helpers ──────────────────────────────────────────────────────────────
const PasswordInput = ({ value, onChange, placeholder, id, label }) => {
  const [show, setShow] = useState(false);
  return (
    <div>
      {label && (
        <label htmlFor={id} className="block text-xs font-medium mb-1.5 text-white/40">
          {label}
        </label>
      )}
      <div className="relative">
        <input
          id={id}
          type={show ? 'text' : 'password'}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete="new-password"
          className="w-full rounded-xl px-4 py-2.5 pr-10 text-sm outline-none transition bg-white/5 border border-white/10 text-white placeholder-white/25 focus:border-blue-500/50"
        />
        <button
          type="button"
          onClick={() => setShow(s => !s)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/60 transition"
        >
          {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
};

const StrengthBar = ({ password }) => {
  const score = (() => {
    if (!password) return 0;
    let s = 0;
    if (password.length >= 8)  s++;
    if (password.length >= 12) s++;
    if (/[A-Z]/.test(password)) s++;
    if (/[0-9]/.test(password)) s++;
    if (/[^A-Za-z0-9]/.test(password)) s++;
    return s;
  })();

  const colors = ['', '#ef4444', '#f97316', '#eab308', '#22c55e', '#16a34a'];
  const labels = ['', 'Very weak', 'Weak', 'Fair', 'Strong', 'Very strong'];

  if (!password) return null;
  return (
    <div className="mt-2">
      <div className="flex gap-1">
        {[1,2,3,4,5].map(i => (
          <div
            key={i}
            className="h-1 flex-1 rounded-full transition-all"
            style={{ background: i <= score ? colors[score] : 'rgba(255,255,255,0.1)' }}
          />
        ))}
      </div>
      <p className="text-[11px] mt-1" style={{ color: colors[score] || 'rgba(255,255,255,0.35)' }}>
        {labels[score]}
      </p>
    </div>
  );
};

// ── Change Password (email/password users) ────────────────────────────────────
const ChangePasswordForm = ({ apiUrl, authHeaders, onAuthError }) => {
  const [current, setCurrent] = useState('');
  const [next,    setNext]    = useState('');
  const [confirm, setConfirm] = useState('');
  const [status,  setStatus]  = useState('idle');
  const [errMsg,  setErrMsg]  = useState('');

  const reset = () => { setCurrent(''); setNext(''); setConfirm(''); setStatus('idle'); setErrMsg(''); };

  const handleSubmit = async () => {
    setErrMsg('');
    if (!current)         return setErrMsg('Please enter your current password.');
    if (next.length < 8)  return setErrMsg('New password must be at least 8 characters.');
    if (next !== confirm)  return setErrMsg('New passwords do not match.');
    if (next === current)  return setErrMsg('New password must differ from current.');

    setStatus('loading');
    try {
      const res = await fetch(`${apiUrl}/change-password`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_password:     current,
          new_password:         next,
          confirm_new_password: confirm,
        }),
      });
      if (res.status === 401) { onAuthError(); return; }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to change password.');
      }
      setStatus('success');
      setTimeout(reset, 3000);
    } catch (err) {
      setErrMsg(err.message);
      setStatus('error');
    }
  };

  if (status === 'success') return <SuccessBanner label="Password changed!" />;

  return (
    <div className="space-y-3">
      <PasswordInput id="current-pw" label="Current password"    value={current} onChange={setCurrent} placeholder="Enter current password" />
      <PasswordInput id="new-pw"     label="New password"         value={next}    onChange={setNext}    placeholder="Min. 8 characters" />
      <StrengthBar password={next} />
      <PasswordInput id="confirm-pw" label="Confirm new password" value={confirm} onChange={setConfirm} placeholder="Repeat new password" />
      <ErrorMsg msg={errMsg} />
      <SubmitButton loading={status === 'loading'} onClick={handleSubmit} label="Change Password" />
    </div>
  );
};

// ── Create Password (OAuth-only users) ───────────────────────────────────────
const CreatePasswordForm = ({ apiUrl, authHeaders, onAuthError, onPasswordCreated }) => {
  const [next,    setNext]    = useState('');
  const [confirm, setConfirm] = useState('');
  const [status,  setStatus]  = useState('idle');
  const [errMsg,  setErrMsg]  = useState('');

  const reset = () => { setNext(''); setConfirm(''); setStatus('idle'); setErrMsg(''); };

  const handleSubmit = async () => {
    setErrMsg('');
    if (next.length < 8)  return setErrMsg('Password must be at least 8 characters.');
    if (next !== confirm)  return setErrMsg('Passwords do not match.');

    setStatus('loading');
    try {
      const res = await fetch(`${apiUrl}/create-password`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          new_password:         next,
          confirm_new_password: confirm,
        }),
      });
      if (res.status === 401) { onAuthError(); return; }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to create password.');
      }
      setStatus('success');
      // Notify parent so it can flip user.has_password → true
      setTimeout(() => { reset(); onPasswordCreated?.(); }, 3000);
    } catch (err) {
      setErrMsg(err.message);
      setStatus('error');
    }
  };

  if (status === 'success') return <SuccessBanner label="Password created! You can now log in with email too." />;

  return (
    <div className="space-y-3">
      {/* Info banner explaining why there's no "current password" field */}
      <div className="flex gap-2.5 px-3 py-2.5 rounded-xl border bg-blue-500/8 border-blue-500/20">
        <Chrome className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-blue-300/80 leading-relaxed">
          You signed in with Google. Create a password to also log in with your email and password.
        </p>
      </div>

      <PasswordInput id="new-pw"     label="New password"         value={next}    onChange={setNext}    placeholder="Min. 8 characters" />
      <StrengthBar password={next} />
      <PasswordInput id="confirm-pw" label="Confirm password"     value={confirm} onChange={setConfirm} placeholder="Repeat new password" />
      <ErrorMsg msg={errMsg} />
      <SubmitButton loading={status === 'loading'} onClick={handleSubmit} label="Create Password" />
    </div>
  );
};

// ── Shared micro-components ───────────────────────────────────────────────────
const SuccessBanner = ({ label }) => (
  <div className="flex flex-col items-center justify-center py-8 rounded-2xl border text-center gap-3 bg-green-500/8 border-green-500/25">
    <div className="w-12 h-12 rounded-full flex items-center justify-center bg-green-500/15">
      <Check className="w-6 h-6 text-green-400" />
    </div>
    <div>
      <p className="text-sm font-semibold text-green-400">{label}</p>
      <p className="text-xs mt-0.5 text-white/40">Form will reset shortly.</p>
    </div>
  </div>
);

const ErrorMsg = ({ msg }) =>
  msg ? (
    <p className="text-xs px-3 py-2 rounded-lg border text-red-400 bg-red-500/8 border-red-500/20">
      {msg}
    </p>
  ) : null;

const SubmitButton = ({ loading, onClick, label }) => (
  <button
    onClick={onClick}
    disabled={loading}
    className="w-full py-2.5 rounded-xl text-sm font-semibold transition disabled:opacity-50 flex items-center justify-center gap-2 bg-blue-500 text-white hover:bg-blue-600"
  >
    {loading ? (
      <>
        <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
        Please wait…
      </>
    ) : (
      <>
        <Lock className="w-3.5 h-3.5" />
        {label}
      </>
    )}
  </button>
);

// ── Password section — picks the right form based on has_password ─────────────
const PasswordSection = ({ apiUrl, authHeaders, onAuthError, user, onPasswordCreated }) => {
  const hasPassword = user?.has_password;

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-red-500/15">
          <Shield className="w-4 h-4 text-red-400" />
        </div>
        <div>
          <p className="text-sm font-semibold text-white">
            {hasPassword ? 'Change Password' : 'Create Password'}
          </p>
          <p className="text-[11px] text-white/40">
            {hasPassword ? 'Update your account password' : 'Add a password to your Google account'}
          </p>
        </div>
      </div>

      {hasPassword ? (
        <ChangePasswordForm
          apiUrl={apiUrl}
          authHeaders={authHeaders}
          onAuthError={onAuthError}
        />
      ) : (
        <CreatePasswordForm
          apiUrl={apiUrl}
          authHeaders={authHeaders}
          onAuthError={onAuthError}
          onPasswordCreated={onPasswordCreated}
        />
      )}
    </div>
  );
};

// ── Main modal ────────────────────────────────────────────────────────────────
const SettingsModal = ({
  isOpen,
  onClose,
  apiUrl = '',
  authHeaders = {},
  onAuthError = () => {},
  user = null,
  onPasswordCreated = null, // () => void — called after OAuth user sets a password
}) => {
  const overlayRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      ref={overlayRef}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
    >
      <div className="w-full max-w-lg rounded-3xl shadow-2xl overflow-hidden flex flex-col bg-neutral-900 border border-white/10 max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 flex-shrink-0 border-b border-white/10">
          <div>
            <h2 className="text-lg font-bold text-white">Settings</h2>
            {user?.email && (
              <p className="text-[11px] mt-0.5 text-white/40">{user.email}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl flex items-center justify-center transition bg-white/5 text-white/40 hover:bg-white/10 hover:text-white"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <PasswordSection
            apiUrl={apiUrl}
            authHeaders={authHeaders}
            onAuthError={onAuthError}
            user={user}
            onPasswordCreated={onPasswordCreated}
          />
        </div>
      </div>
    </div>
  );
};

export default SettingsModal;