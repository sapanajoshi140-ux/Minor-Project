import React, { useState, useRef, useEffect, useCallback } from 'react';

const RAG_API_URL = import.meta.env.VITE_RAG_API_URL || 'http://localhost:8001';

const getRagHeaders = () => ({
  'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`,
});

// ── tiny helpers ──────────────────────────────────────────────────────────────
const TypingDots = () => (
  <span className="inline-flex gap-1 items-center h-4">
    {[0, 1, 2].map(i => (
      <span
        key={i}
        className="w-1.5 h-1.5 rounded-full animate-bounce"
        style={{ background: 'var(--muted-text)', animationDelay: `${i * 0.15}s` }}
      />
    ))}
  </span>
);

// ── Animated placeholder hook ─────────────────────────────────────────────────
const PLACEHOLDER_QUESTIONS = [
  'What is the main topic?',
  'Summarize the key points',
  'What conclusions are drawn?',
  'Explain the key concepts…',
  'What are the main arguments?',
];

const useAnimatedPlaceholder = (active) => {
  const [placeholder, setPlaceholder] = useState('');
  const stateRef = useRef({ qIndex: 0, charIndex: 0, deleting: false, pauseTick: 0 });
  const timerRef = useRef(null);

  useEffect(() => {
    if (!active) { setPlaceholder('Ask a question…'); return; }

    const tick = () => {
      const s = stateRef.current;
      const question = PLACEHOLDER_QUESTIONS[s.qIndex];

      if (!s.deleting && s.charIndex === question.length) {
        s.pauseTick++;
        if (s.pauseTick < 18) { timerRef.current = setTimeout(tick, 80); return; }
        s.deleting = true;
        s.pauseTick = 0;
      }

      if (s.deleting && s.charIndex === 0) {
        s.pauseTick++;
        if (s.pauseTick < 8) { timerRef.current = setTimeout(tick, 80); return; }
        s.deleting = false;
        s.pauseTick = 0;
        s.qIndex = (s.qIndex + 1) % PLACEHOLDER_QUESTIONS.length;
      }

      s.charIndex += s.deleting ? -1 : 1;
      const current = PLACEHOLDER_QUESTIONS[s.qIndex];
      setPlaceholder(current.slice(0, s.charIndex));

      const speed = s.deleting ? 35 : 65;
      timerRef.current = setTimeout(tick, speed);
    };

    timerRef.current = setTimeout(tick, 600);
    return () => clearTimeout(timerRef.current);
  }, [active]);

  return placeholder;
};

// ── Fake typing illusion bubble ───────────────────────────────────────────────
const FakeTypingBubble = () => (
  <div
    className="px-3.5 py-3 rounded-2xl rounded-tl-sm shadow-sm"
    style={{
      background: 'var(--bubble-ai-bg, var(--page-bg))',
      border: '1px solid var(--bubble-ai-border, var(--page-border))',
    }}
  >
    <TypingDots />
  </div>
);

// ── Animated assistant bubble ─────────────────────────────────────────────────
const AssistantBubble = ({ content, streaming }) => (
  <div
    className="max-w-[82%] sm:max-w-[78%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed rounded-tl-sm shadow-sm"
    style={{
      background: 'var(--bubble-ai-bg, var(--page-bg))',
      border: '1px solid var(--bubble-ai-border, var(--page-border))',
      color: 'var(--bubble-ai-text, var(--page-text))',
    }}
  >
    {content}
    {streaming && (
      <span
        className="inline-block w-0.5 h-3.5 ml-0.5 animate-pulse align-middle"
        style={{ background: 'var(--muted-text)' }}
      />
    )}
  </div>
);

// ── Summary card ──────────────────────────────────────────────────────────────
const SummaryCard = ({ selectedText, result }) => (
  <div className="flex justify-start">
    <div className="max-w-[95%] sm:max-w-[90%] w-full">
      <div className="flex items-center gap-1.5 mb-1.5 ml-1">
        <span className="text-[10px] font-semibold text-purple-500 uppercase tracking-wider">✨ Summary</span>
      </div>
      <div
        className="rounded-2xl rounded-tl-sm overflow-hidden shadow-sm"
        style={{
          background: 'var(--bubble-ai-bg, var(--page-bg))',
          border: '1px solid var(--bubble-ai-border, var(--page-border))',
        }}
      >
        <div
          className="px-3.5 pt-3 pb-2"
          style={{ borderBottom: '1px solid var(--bubble-ai-border, var(--page-border))' }}
        >
          <p className="text-[10px] font-bold text-purple-400 uppercase tracking-wider mb-1">Selected text</p>
          <p
            className="text-[12px] italic leading-relaxed line-clamp-3"
            style={{ color: 'var(--muted-text)' }}
          >
            "{selectedText}"
          </p>
        </div>
        <div className="px-3.5 py-3">
          <p className="text-[10px] font-bold text-purple-400 uppercase tracking-wider mb-1.5">Summary</p>
          {result === null ? (
            <div className="space-y-2 animate-pulse">
              {[100, 83, 66].map((w, i) => (
                <div
                  key={i}
                  className="h-3 rounded"
                  style={{ width: `${w}%`, background: 'var(--bubble-ai-border, var(--page-border))' }}
                />
              ))}
            </div>
          ) : (
            <p
              className="text-[13px] leading-relaxed font-medium whitespace-pre-wrap"
              style={{ color: 'var(--bubble-ai-text, var(--page-text))' }}
            >
              {result}
            </p>
          )}
        </div>
      </div>
    </div>
  </div>
);

// ── main component ────────────────────────────────────────────────────────────
const ChatPanel = ({
  documentId,
  documentName,
  injectedMessage,
  onInjectedMessageConsumed,
  panelWidth = 380,
  theme,
}) => {
  const maxTextareaHeight = Math.max(72, Math.round(Math.min(panelWidth, window.innerWidth) * 0.22));

  const [messages,    setMessages]    = useState([]);
  const [input,       setInput]       = useState('');
  const [sessionId,   setSessionId]   = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error,       setError]       = useState('');

  const bottomRef = useRef(null);
  const inputRef  = useRef(null);
  const abortRef  = useRef(null);

  const [inputFocused, setInputFocused] = useState(false);
  const animatedPlaceholder = useAnimatedPlaceholder(
    messages.length === 0 && !input && !inputFocused
  );

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);
  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 100); }, []);
  useEffect(() => () => abortRef.current?.abort(), []);

  // Handle injected summary message
  useEffect(() => {
    if (!injectedMessage) return;
    setMessages(prev => {
      if (prev.find(m => m.id === injectedMessage.id)) {
        return prev.map(m =>
          m.id === injectedMessage.id ? { ...m, result: injectedMessage.result } : m
        );
      }
      return [...prev, {
        id:           injectedMessage.id,
        role:         'summary',
        selectedText: injectedMessage.selectedText,
        result:       injectedMessage.result,
      }];
    });
  }, [injectedMessage]);

  const appendAssistantChunk = useCallback((chunk) => {
    setMessages(prev => {
      const last = prev[prev.length - 1];
      if (last?.role === 'assistant' && last.streaming) {
        return [...prev.slice(0, -1), { ...last, content: last.content + chunk }];
      }
      return [...prev, { role: 'assistant', content: chunk, streaming: true, id: Date.now() }];
    });
  }, []);

  const finaliseAssistant = useCallback(() => {
    setMessages(prev => {
      const last = prev[prev.length - 1];
      if (last?.role === 'assistant') {
        return [...prev.slice(0, -1), { ...last, streaming: false }];
      }
      return prev;
    });
  }, []);

  const sendMessage = async () => {
    const q = input.trim();
    if (!q || isStreaming) return;
    setInput('');
    setError('');

    const now = Date.now();
    setMessages(prev => [...prev, { role: 'user', content: q, id: now }]);
    setIsStreaming(true);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${RAG_API_URL}/chat/stream`, {
        method: 'POST',
        headers: { ...getRagHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question:   q,
          session_id: sessionId || undefined,
          doc_ids:    documentId ? [documentId] : undefined,
          top_k:      5,
          use_hybrid: true,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Request failed (${res.status})`);
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = '';
      let   expectMetaData = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const raw of lines) {
          const line = raw.trim();
          if (!line) { expectMetaData = false; continue; }

          if (line === 'event: meta') { expectMetaData = true; continue; }

          if (line.startsWith('data: ')) {
            const payload = line.slice(6);
            if (payload === '[DONE]') { finaliseAssistant(); expectMetaData = false; continue; }

            if (expectMetaData) {
              try {
                const meta = JSON.parse(payload);
                if (meta.session_id) setSessionId(meta.session_id);
              } catch { /* ignore */ }
              expectMetaData = false;
              continue;
            }

            appendAssistantChunk(payload);
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') return;
      setError(err.message || 'Something went wrong.');
      setMessages(prev => prev.filter(m => !m.streaming));
    } finally {
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && window.innerWidth >= 768) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearChat = async () => {
    if (sessionId) {
      try {
        await fetch(`${RAG_API_URL}/session/${sessionId}`, {
          method: 'DELETE',
          headers: getRagHeaders(),
        });
      } catch {}
    }
    setMessages([]);
    setSessionId(null);
    setError('');
  };

  return (
    <div
      className="w-full flex flex-col"
      style={{ height: '100%', background: 'var(--chat-bg, var(--sidebar-bg))', transition: 'background 0.3s, color 0.3s' }}
    >

      {/* ── Header ── */}
      <div
        className="shrink-0 px-4 sm:px-5 py-3 sm:py-4 flex items-center gap-3"
        style={{
          background: 'var(--sidebar-bg)',
          borderBottom: '1px solid var(--sidebar-border)',
          transition: 'background 0.3s',
        }}
      >
        <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shrink-0">
          <svg className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        </div>

        <div className="flex-1 min-w-0">
          <h2
            className="text-sm font-bold leading-tight"
            style={{ color: 'var(--page-text)' }}
          >
            Ask about this document
          </h2>
          {documentName && (
            <p className="text-[10px] truncate" style={{ color: 'var(--muted-text)' }}>
              {documentName}
            </p>
          )}
        </div>

        {messages.length > 0 && (
          <button
            onClick={clearChat}
            className="p-1.5 rounded-lg transition text-[10px] font-medium"
            style={{ color: 'var(--muted-text)', background: 'transparent' }}
            onMouseEnter={e => e.currentTarget.style.background = 'var(--page-border)'}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            title="Clear chat"
          >
            Clear
          </button>
        )}
      </div>

      {/* ── Messages ── */}
      <div
        className="flex-1 overflow-y-auto px-3 sm:px-4 py-3 sm:py-4 space-y-3 sm:space-y-4"
        style={{ background: 'var(--chat-bg, var(--app-bg))', transition: 'background 0.3s' }}
      >
        {/* Empty state */}
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center py-8 sm:py-12 select-none">
            <div
              className="w-12 h-12 sm:w-16 sm:h-16 rounded-2xl flex items-center justify-center mb-3 sm:mb-4"
              style={{ background: 'var(--bubble-ai-bg, var(--page-bg))', border: '1px solid var(--bubble-ai-border, var(--page-border))' }}
            >
              <svg className="w-6 h-6 sm:w-8 sm:h-8 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <p className="text-sm font-semibold mb-1" style={{ color: 'var(--page-text)' }}>
              Ask anything about this document
            </p>
            <p className="text-xs mb-0.5" style={{ color: 'var(--muted-text)' }}>
              Select a paragraph and hit Summarize,
            </p>
            <p className="text-xs" style={{ color: 'var(--muted-text)' }}>
              or type a question below.
            </p>

            <div className="mt-4 sm:mt-6 space-y-2 w-full max-w-xs">
              {['What is the main topic?', 'Summarize the key points', 'What conclusions are drawn?'].map(q => (
                <button
                  key={q}
                  onClick={() => { setInput(q); inputRef.current?.focus(); }}
                  className="w-full text-left text-xs px-3 py-2.5 sm:py-2 rounded-lg transition"
                  style={{
                    background: 'var(--bubble-ai-bg, var(--page-bg))',
                    border: '1px solid var(--bubble-ai-border, var(--page-border))',
                    color: 'var(--bubble-ai-text, var(--page-text))',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bubble-ai-border, var(--page-border))'}
                  onMouseLeave={e => e.currentTarget.style.background = 'var(--bubble-ai-bg, var(--page-bg))'}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Message list */}
        {messages.map((msg) => {
          if (msg.role === 'summary') {
            return <SummaryCard key={msg.id} selectedText={msg.selectedText} result={msg.result} />;
          }

          return (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'assistant' && (
                <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shrink-0 mt-0.5 mr-2">
                  <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
                  </svg>
                </div>
              )}

              {msg.role === 'assistant' ? (
                <AssistantBubble content={msg.content} streaming={msg.streaming} />
              ) : (
                <div
                  className="max-w-[82%] sm:max-w-[78%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed rounded-tr-sm"
                  style={{
                    background: 'var(--bubble-user-bg, #4f46e5)',
                    color: 'var(--bubble-user-text, #ffffff)',
                  }}
                >
                  {msg.content}
                </div>
              )}
            </div>
          );
        })}

        {/* Typing indicator */}
        {isStreaming && messages.length > 0 && messages[messages.length - 1].role === 'user' && (
          <div className="flex justify-start">
            <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shrink-0 mt-0.5 mr-2">
              <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
              </svg>
            </div>
            <FakeTypingBubble />
          </div>
        )}

        {/* Error */}
        {error && (
          <div
            className="flex items-start gap-2 px-3 py-2.5 rounded-xl text-xs"
            style={{
              background: 'var(--bubble-ai-bg, var(--page-bg))',
              border: '1px solid var(--bubble-ai-border, var(--page-border))',
              color: '#c0392b',
            }}
          >
            <svg className="w-4 h-4 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Input ── */}
      <div
        className="shrink-0 p-3 sm:p-4"
        style={{
          background: 'var(--sidebar-bg)',
          borderTop: '1px solid var(--sidebar-border)',
          transition: 'background 0.3s',
        }}
      >
        <div
          className="flex items-end gap-2 rounded-2xl px-3 py-2"
          style={{
            background: 'var(--bubble-ai-bg, var(--page-bg))',
            border: '1px solid var(--bubble-ai-border, var(--page-border))',
            transition: 'border-color 0.2s',
          }}
          onFocus={e => e.currentTarget.style.borderColor = 'rgba(99,102,241,0.45)'}
          onBlur={e => e.currentTarget.style.borderColor = 'var(--bubble-ai-border, var(--page-border))'}
        >
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setInputFocused(true)}
            onBlur={() => setInputFocused(false)}
            placeholder={animatedPlaceholder}
            disabled={isStreaming}
            className="flex-1 bg-transparent text-sm outline-none resize-none leading-relaxed disabled:opacity-60"
            style={{
              minHeight: '24px',
              maxHeight: `${maxTextareaHeight}px`,
              color: 'var(--bubble-ai-text, var(--page-text))',
              caretColor: 'var(--bubble-ai-text, var(--page-text))',
            }}
            onInput={e => {
              e.target.style.height = 'auto';
              e.target.style.height = `${Math.min(e.target.scrollHeight, maxTextareaHeight)}px`;
            }}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isStreaming}
            className="w-8 h-8 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center transition hover:opacity-90 active:opacity-80 disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
          >
            {isStreaming ? (
              <div className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
            ) : (
              <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            )}
          </button>
        </div>

        <p className="hidden sm:block text-[10px] text-center mt-2" style={{ color: 'var(--muted-text)' }}>
          Enter to send · Shift+Enter for new line
        </p>
      </div>

      {/* ── Placeholder color for themed textarea ── */}
      <style>{`
        .chat-panel textarea::placeholder {
          color: var(--muted-text);
          opacity: 0.7;
        }
      `}</style>
    </div>
  );
};

export default ChatPanel;