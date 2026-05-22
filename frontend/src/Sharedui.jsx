// ─────────────────────────────────────────────────────────────────────────────
// SharedUI.jsx  —  tiny presentational components used in both Workspace and
//                  PdfViewer so nothing is copy-pasted twice.
// ─────────────────────────────────────────────────────────────────────────────
import React from 'react';

// ── Spinner ───────────────────────────────────────────────────────────────────
/**
 * @param {string} [size]   Tailwind w/h pair, e.g. "w-8 h-8" (default "w-6 h-6")
 * @param {string} [color]  Tailwind border-t colour, e.g. "border-t-blue-500"
 */
export const Spinner = ({ size = 'w-6 h-6', color = 'border-t-gray-600' }) => (
  <div
    className={`${size} rounded-full border-2 border-gray-200 ${color} animate-spin`}
  />
);

// ── Skeleton page shimmer ─────────────────────────────────────────────────────
export const PageSkeleton = () => (
  <div className="absolute inset-0 p-10 space-y-5 animate-pulse pointer-events-none">
    <div className="h-4 bg-gray-100 rounded w-full" />
    <div className="h-4 bg-gray-100 rounded w-5/6" />
    <div className="h-4 bg-gray-100 rounded w-full" />
    <div className="h-4 bg-gray-100 rounded w-4/6" />
    <div className="h-32 bg-gray-50 rounded w-full mt-8" />
    <div className="h-4 bg-gray-100 rounded w-full" />
    <div className="h-4 bg-gray-100 rounded w-3/4" />
  </div>
);

// ── Toast ─────────────────────────────────────────────────────────────────────
/**
 * Positioned toast banner that sits below the top bar.
 * @param {'success'|'error'} status
 * @param {string}            message
 */
export const Toast = ({ status, message }) => {
  if (!status || !message) return null;
  const ok = status === 'success';
  return (
    <div
      className={`absolute top-16 left-1/2 -translate-x-1/2 z-20 px-4 py-2 rounded-full text-xs font-medium shadow-lg ${
        ok
          ? 'bg-green-100 border border-green-200 text-green-700'
          : 'bg-red-100 border border-red-200 text-red-700'
      }`}
    >
      {ok ? '✓' : '✕'} {message}
    </div>
  );
};

// ── Page-counter pill ─────────────────────────────────────────────────────────
/**
 * The "Page X of Y" pill used in both Workspace's top bar and PdfViewer's
 * overlay.
 */
export const PagePill = ({ current, total, extra }) => (
  <div className="bg-white/90 backdrop-blur-sm border border-gray-200 shadow-sm px-4 py-1.5 rounded-full flex items-center gap-3">
    <span className="text-xs font-medium text-gray-600">
      Page {current} of {total}
    </span>
    {extra}
  </div>
);

// ── End-of-document marker ────────────────────────────────────────────────────
export const EndOfDocument = () => (
  <div className="text-center py-8">
    <span className="bg-gray-200 text-gray-600 text-xs px-3 py-1 rounded-full font-medium">
      End of Document
    </span>
  </div>
);

// ── Floating-menu button style (inline, kept as a plain object) ───────────────
export const menuBtnStyle = {
  background: 'none',
  border: 'none',
  color: '#fff',
  padding: '8px 14px',
  fontSize: '12px',
  fontWeight: '600',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  gap: '5px',
  whiteSpace: 'nowrap',
  fontFamily: 'inherit',
};