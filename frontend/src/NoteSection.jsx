// ─────────────────────────────────────────────────────────────────────────────
// NoteSection.jsx
// ─────────────────────────────────────────────────────────────────────────────
import React, { useEffect, useRef, useState, useCallback } from 'react';

const PencilIcon = ({ size = 13, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 20h9"/>
    <path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>
  </svg>
);

const CloseIcon = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 6L6 18M6 6l12 12"/>
  </svg>
);

export const CenteredNoteButton = ({ hasNote, isOpen, onClick, pageNum }) => (
  <button
    onClick={(e) => { e.stopPropagation(); onClick(); }}
    onMouseDown={(e) => e.stopPropagation()}
    className={`
      note-toggle-btn flex items-center gap-1.5 px-4 py-1.5 rounded-full text-[11px] font-medium
      transition-all duration-150 select-none
      ${isOpen || hasNote
        ? 'bg-blue-50 text-blue-600 border border-blue-200 shadow-sm'
        : 'bg-white text-gray-500 border border-gray-200 hover:border-gray-300 hover:text-gray-700 hover:shadow-sm'
      }
    `}
    title={hasNote ? `Edit note for page ${pageNum}` : `Add note for page ${pageNum}`}
  >
    <PencilIcon size={12} color={isOpen || hasNote ? '#3b82f6' : '#9ca3af'} />
    <span>{hasNote ? 'Edit note' : 'Note'}</span>
    {hasNote && !isOpen && (
      <span className="w-1.5 h-1.5 rounded-full bg-blue-500 ml-0.5" />
    )}
  </button>
);

// saveStatus: '' | 'saving' | 'saved' | 'error'
const SaveIndicator = ({ status }) => {
  if (!status) return null;
  const map = {
    saving: { text: 'Saving…',  cls: 'text-gray-400' },
    saved:  { text: 'Saved ✓',  cls: 'text-green-500' },
    error:  { text: 'Save failed', cls: 'text-red-500' },
  };
  const { text, cls } = map[status] || {};
  return <span className={`text-[11px] font-medium ${cls}`}>{text}</span>;
};

export const FloatingNotePanel = ({
  pageNum,
  note,
  onChange,
  isOpen,
  onClose,
  // NEW — called with (pageNum, text) to persist; called with (pageNum, '') to delete
  onSave,
}) => {
  const textareaRef  = useRef(null);
  const debounceRef  = useRef(null);
  const [charCount,   setCharCount]   = useState(note?.length ?? 0);
  const [saveStatus,  setSaveStatus]  = useState('');

  // keep charCount in sync when note prop changes from outside (initial load)
  useEffect(() => { setCharCount(note?.length ?? 0); }, [note]);

  useEffect(() => {
    if (isOpen && textareaRef.current) textareaRef.current.focus();
  }, [isOpen]);

  // clear "saved" indicator after 2 s
  useEffect(() => {
    if (saveStatus !== 'saved') return;
    const id = setTimeout(() => setSaveStatus(''), 2000);
    return () => clearTimeout(id);
  }, [saveStatus]);

  const triggerSave = useCallback(async (text) => {
    if (!onSave) return;
    setSaveStatus('saving');
    try {
      await onSave(pageNum, text);
      setSaveStatus('saved');
    } catch {
      setSaveStatus('error');
    }
  }, [onSave, pageNum]);

  const handleChange = (e) => {
    const val = e.target.value;
    onChange(val);
    setCharCount(val.length);

    // debounced auto-save: 1.2 s after user stops typing
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => triggerSave(val), 1200);
  };

  const handleBlur = () => {
    clearTimeout(debounceRef.current);
    triggerSave(textareaRef.current?.value ?? note);
  };

  const handleClear = async () => {
    clearTimeout(debounceRef.current);
    onChange('');
    setCharCount(0);
    textareaRef.current?.focus();
    if (onSave) {
      setSaveStatus('saving');
      try {
        await onSave(pageNum, '');
        setSaveStatus('saved');
      } catch {
        setSaveStatus('error');
      }
    }
  };

  const handleDone = () => {
    clearTimeout(debounceRef.current);
    triggerSave(textareaRef.current?.value ?? note);
    onClose();
  };

  // cleanup debounce on unmount
  useEffect(() => () => clearTimeout(debounceRef.current), []);

  if (!isOpen) return null;

  return (
    <div
      className="note-panel w-full mt-2 bg-white rounded-2xl border border-gray-200 shadow-[0_8px_30px_rgba(0,0,0,0.12)] overflow-hidden"
      onMouseDown={(e) => e.stopPropagation()}
      onMouseUp={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gradient-to-r from-slate-50 to-blue-50/30">
        <div className="flex items-center gap-2">
          <PencilIcon size={14} color="#6366f1" />
          <span className="text-[13px] font-semibold text-gray-700">
            Page {pageNum} note
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all"
          title="Close"
        >
          <CloseIcon size={14} />
        </button>
      </div>

      <div className="px-4 py-3">
        <textarea
          ref={textareaRef}
          value={note}
          onChange={handleChange}
          onBlur={handleBlur}
          placeholder="Write a note for this page…"
          className="w-full min-h-[120px] resize-y outline-none rounded-xl p-3 text-[13px] leading-relaxed text-gray-800 bg-gray-50/50 border-[1.5px] border-gray-200 box-border transition-all duration-150 focus:border-blue-400 focus:bg-white focus:shadow-[0_0_0_3px_rgba(59,130,246,0.08)]"
        />
      </div>

      <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 bg-gray-50/50">
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-gray-400 font-medium">{charCount} chars</span>
          <SaveIndicator status={saveStatus} />
        </div>
        <div className="flex items-center gap-2">
          {note && (
            <button
              onClick={handleClear}
              className="text-[12px] text-red-500 hover:text-red-600 px-3 py-1.5 rounded-lg hover:bg-red-50 transition-colors font-medium"
            >
              Clear
            </button>
          )}
          <button
            onClick={handleDone}
            className="text-[12px] px-4 py-1.5 rounded-lg bg-gray-900 text-white hover:bg-gray-800 transition-colors font-medium shadow-sm"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};

export const NoteButton = CenteredNoteButton;
export const InlineNoteSection = FloatingNotePanel;
export default CenteredNoteButton;