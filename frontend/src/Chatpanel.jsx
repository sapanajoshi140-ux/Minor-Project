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
        className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"
        style={{ animationDelay: `${i * 0.15}s` }}
      />
    ))}
  </span>
);

// ── Animated placeholder hook ─────────────────────────────────────────────────
// Cycles through sample questions with a typewriter + delete effect.
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

      // Pause at full word before deleting
      if (!s.deleting && s.charIndex === question.length) {
        s.pauseTick++;
        if (s.pauseTick < 18) { timerRef.current = setTimeout(tick, 80); return; }
        s.deleting = true;
        s.pauseTick = 0;
      }

      // Pause at empty before next word
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

// ── Typewriter hook ───────────────────────────────────────────────────────────
// Animates `text` character by character. Returns the currently displayed slice.
const useTypewriter = (text, speed = 18, enabled = true) => {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone] = useState(false);
  const indexRef = useRef(0);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!enabled || !text) {
      setDisplayed(text || '');
      setDone(true);
      return;
    }
    // Reset when text changes (e.g. streaming chunk arrives)
    setDone(false);
    const tick = () => {
      indexRef.current += 1;
      setDisplayed(text.slice(0, indexRef.current));
      if (indexRef.current < text.length) {
        timerRef.current = setTimeout(tick, speed);
      } else {
        setDone(true);
      }
    };
    timerRef.current = setTimeout(tick, speed);
    return () => clearTimeout(timerRef.current);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  return { displayed, done };
};

// ── Fake typing illusion bubble ───────────────────────────────────────────────
const FakeTypingBubble = () => (
  <div className="px-3.5 py-3 rounded-2xl bg-white border border-gray-100 shadow-sm rounded-tl-sm">
    <TypingDots />
  </div>
);

// ── Animated assistant bubble ─────────────────────────────────────────────────
const AssistantBubble = ({ content, streaming }) => {
  return (
    <div className="max-w-[78%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed bg-white border border-gray-100 text-gray-800 shadow-sm rounded-tl-sm">
      {content}
      {streaming && (
        <span className="inline-block w-0.5 h-3.5 bg-blue-400 ml-0.5 animate-pulse align-middle" />
      )}
    </div>
  );
};

// ── Summary card ──────────────────────────────────────────────────────────────
const SummaryCard = ({ selectedText, result }) => (
  <div className="flex justify-start">
    <div className="max-w-[90%] w-full">
      <div className="flex items-center gap-1.5 mb-1.5 ml-1">
        <span className="text-[10px] font-semibold text-purple-500 uppercase tracking-wider">✨ Summary</span>
      </div>
      <div className="bg-gradient-to-br from-purple-50 to-indigo-50 border border-purple-100 rounded-2xl rounded-tl-sm overflow-hidden shadow-sm">
        <div className="px-3.5 pt-3 pb-2 border-b border-purple-100/60">
          <p className="text-[10px] font-bold text-purple-400 uppercase tracking-wider mb-1">Selected text</p>
          <p className="text-[12px] text-purple-700/70 italic leading-relaxed line-clamp-3">
            "{selectedText}"
          </p>
        </div>
        <div className="px-3.5 py-3">
          <p className="text-[10px] font-bold text-purple-400 uppercase tracking-wider mb-1.5">Summary</p>
          {result === null ? (
            <div className="space-y-2 animate-pulse">
              <div className="h-3 bg-purple-100 rounded w-full" />
              <div className="h-3 bg-purple-100 rounded w-5/6" />
              <div className="h-3 bg-purple-100 rounded w-4/6" />
            </div>
          ) : (
            <p className="text-[13px] text-gray-800 leading-relaxed font-medium whitespace-pre-wrap">{result}</p>
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
}) => {
  const [messages,    setMessages]    = useState([]);
  const [input,       setInput]       = useState('');
  const [sessionId,   setSessionId]   = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error,       setError]       = useState('');

  const bottomRef = useRef(null);
  const inputRef  = useRef(null);
  const abortRef  = useRef(null);

  // Animated placeholder — only active when chat is empty and user hasn't typed
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
        id:    injectedMessage.id,
        role:  'summary',
        selectedText: injectedMessage.selectedText,
        result: injectedMessage.result,
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
    // Only add the user message here. The assistant bubble is created on first chunk.
    setMessages(prev => [
      ...prev,
      { role: 'user', content: q, id: now },
    ]);
    // Show a "waiting" indicator separately via isStreaming state
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
                // citations intentionally ignored
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
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
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

  // ── render ────────────────────────────────────────────────────────────────
  return (
    <div className="w-[380px] h-full flex flex-col bg-white border-l border-gray-100 shadow-xl">

      {/* header */}
      <div className="shrink-0 px-5 py-4 border-b border-gray-100 flex items-center gap-3 bg-gradient-to-r from-blue-50 to-indigo-50">
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shrink-0">
          <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-bold text-gray-900 leading-tight">Ask about this document</h2>
          {documentName && <p className="text-[10px] text-gray-400 truncate">{documentName}</p>}
        </div>
        {messages.length > 0 && (
          <button
            onClick={clearChat}
            className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition text-[10px] font-medium"
            title="Clear chat"
          >
            Clear
          </button>
        )}
      </div>

      {/* messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 bg-gray-50/40">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center py-12 select-none">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-100 to-indigo-100 flex items-center justify-center mb-4">
              <svg className="w-8 h-8 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <p className="text-sm font-semibold text-gray-600 mb-1">Ask anything about this document</p>
            <p className="text-xs text-gray-400 mb-1">Select a paragraph and hit Summarize,</p>
            <p className="text-xs text-gray-400">or type a question below.</p>
            <div className="mt-6 space-y-2 w-full max-w-xs">
              {['What is the main topic?', 'Summarize the key points', 'What conclusions are drawn?'].map(q => (
                <button
                  key={q}
                  onClick={() => { setInput(q); inputRef.current?.focus(); }}
                  className="w-full text-left text-xs text-blue-600 bg-blue-50 hover:bg-blue-100 border border-blue-100 px-3 py-2 rounded-lg transition"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

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
                <div className="max-w-[78%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed bg-gradient-to-br from-blue-500 to-indigo-600 text-white rounded-tr-sm">
                  {msg.content}
                </div>
              )}
            </div>
          );
        })}

        {/* Fake typing illusion — shown only while waiting for first real chunk */}
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

        {error && (
          <div className="flex items-start gap-2 bg-red-50 border border-red-100 text-red-600 px-3 py-2.5 rounded-xl text-xs">
            <svg className="w-4 h-4 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* input */}
      <div className="shrink-0 p-4 border-t border-gray-100 bg-white">
        <div className="flex items-end gap-2 bg-gray-50 border border-gray-200 rounded-2xl px-3 py-2 focus-within:border-blue-300 focus-within:bg-white transition">
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
            className="flex-1 bg-transparent text-sm text-gray-800 placeholder-gray-400 outline-none resize-none max-h-24 leading-relaxed disabled:opacity-60"
            style={{ minHeight: '24px' }}
            onInput={e => {
              e.target.style.height = 'auto';
              e.target.style.height = `${Math.min(e.target.scrollHeight, 96)}px`;
            }}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isStreaming}
            className="w-8 h-8 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center transition hover:opacity-90 disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
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
        <p className="text-[10px] text-gray-400 text-center mt-2">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
};

export default ChatPanel;