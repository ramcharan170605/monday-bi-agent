import React, { useState, useEffect, useRef } from 'react';
import Header from './components/Header';
import DataQualityDrawer from './components/DataQualityDrawer';
import DataExplorer from './components/DataExplorer';
import { fetchHealth, syncBoards, askAgent } from './services/api';
import { Send, AlertTriangle, ChevronDown, ChevronUp, Copy, Check, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

const SUGGESTED_QUESTIONS = [
  "How is our energy sector pipeline looking?",
  "What's our work order completion rate?",
  "Compare sales pipeline with project execution",
  "Show me delayed work orders",
  "What data quality issues should we address?",
  "What's the overall win rate across sectors?"
];

export default function App() {
  const [health, setHealth] = useState(null);
  const [activeTab, setActiveTab] = useState('chat');
  const [isSyncing, setIsSyncing] = useState(false);
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState([]);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const loadHealth = async () => {
    try {
      const data = await fetchHealth();
      setHealth(data);
    } catch (err) {
      console.error('Health fetch error:', err);
    }
  };

  useEffect(() => { loadHealth(); }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSync = async () => {
    setIsSyncing(true);
    try {
      await syncBoards();
      await loadHealth();
    } catch (err) {
      alert(`Sync failed: ${err.message}`);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleSend = async (questionText = query) => {
    const textToSend = questionText.trim();
    if (!textToSend || isLoading) return;

    setQuery('');
    const compactHistory = messages
      .filter((m) => m.type === 'user' || m.type === 'agent')
      .slice(-8)
      .map((m) => ({ type: m.type, text: m.text }));

    setMessages(prev => [
      ...prev,
      { id: Date.now().toString(), type: 'user', text: textToSend }
    ]);

    setIsLoading(true);

    try {
      const resp = await askAgent(textToSend, compactHistory);

      let displayText = resp.answer || '';
      // Unwrap JSON-wrapped answers
      if (typeof displayText === 'string' && displayText.trim().startsWith('{') && displayText.includes('"answer"')) {
        try {
          const parsed = JSON.parse(displayText.trim());
          if (parsed.answer) displayText = parsed.answer;
        } catch (e) {
          const match = displayText.match(/"answer"\s*:\s*"((?:[^"\\]|\\.)*)"/);
          if (match?.[1]) displayText = match[1].replace(/\\n/g, '\n').replace(/\\"/g, '"');
        }
      }

      setMessages(prev => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          type: 'agent',
          text: displayText,
          caveats: resp.data_quality_caveats,
        }
      ]);
    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          type: 'error',
          text: `Something went wrong. ${err.message}`
        }
      ]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Empty state
  const isEmptyChat = messages.length === 0;

  return (
    <div className="min-h-screen flex flex-col bg-[#0a0e1a] text-slate-100">
      <Header
        health={health}
        isSyncing={isSyncing}
        onSync={handleSync}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />

      <main className="flex-1 flex flex-col">
        {activeTab === 'chat' && (
          <div className="flex-1 flex flex-col h-[calc(100vh-3.5rem)]">

            {isEmptyChat ? (
              /* ───── Empty State ───── */
              <div className="flex-1 flex flex-col items-center justify-center px-4">
                <div className="mb-8 text-center">
                  <div className="h-12 w-12 rounded-2xl bg-blue-600/10 border border-blue-500/20 flex items-center justify-center mx-auto mb-4">
                    <span className="text-xl font-bold text-blue-400">S</span>
                  </div>
                  <h2 className="text-lg font-semibold text-white mb-1">
                    Skylark BI Assistant
                  </h2>
                  <p className="text-sm text-slate-500 max-w-sm">
                    Ask questions about your Monday.com pipeline, operations, and data quality.
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-xl w-full mb-8">
                  {SUGGESTED_QUESTIONS.map((q, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(q)}
                      disabled={isLoading}
                      className="text-left px-4 py-3 rounded-xl bg-slate-800/50 hover:bg-slate-800 border border-slate-700/40 hover:border-slate-600/60 text-[13px] text-slate-400 hover:text-slate-200 transition-all duration-150"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              /* ───── Messages ───── */
              <div className="flex-1 overflow-y-auto">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-6">
                  {messages.map((m) => (
                    <MessageBubble key={m.id} message={m} />
                  ))}

                  {isLoading && (
                    <div className="flex gap-3 items-start">
                      <Avatar type="agent" />
                      <div className="py-2.5 px-4 rounded-2xl rounded-tl-sm bg-slate-800/50 border border-slate-700/40">
                        <div className="flex items-center gap-2 text-sm text-slate-500">
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Analyzing your data…</span>
                        </div>
                      </div>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </div>
              </div>
            )}

            {/* ───── Input Bar ───── */}
            <div className="border-t border-slate-800/60 bg-[#0a0e1a]">
              <div className="max-w-3xl mx-auto px-4 sm:px-6 py-3">
                <div className="relative flex items-center">
                  <input
                    ref={inputRef}
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask about pipeline, operations, or data quality…"
                    className="w-full pl-4 pr-12 py-3 rounded-xl bg-slate-800/40 border border-slate-700/40 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-slate-600 transition-colors"
                  />
                  <button
                    onClick={() => handleSend()}
                    disabled={!query.trim() || isLoading}
                    className="absolute right-2 p-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-20 disabled:hover:bg-blue-600 transition-all"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

          </div>
        )}

        {activeTab === 'explorer' && <DataExplorer />}
        {activeTab === 'quality' && <DataQualityDrawer />}
      </main>
    </div>
  );
}


/* ─────────────────────────────────────────────────────
   Avatar
───────────────────────────────────────────────────── */

function Avatar({ type }) {
  if (type === 'user') {
    return (
      <div className="h-7 w-7 rounded-full bg-slate-700 flex items-center justify-center shrink-0 mt-0.5">
        <svg className="w-3.5 h-3.5 text-slate-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      </div>
    );
  }
  return (
    <div className="h-7 w-7 rounded-full bg-blue-600/15 border border-blue-500/20 flex items-center justify-center shrink-0 mt-0.5">
      <span className="text-[11px] font-bold text-blue-400">S</span>
    </div>
  );
}


/* ─────────────────────────────────────────────────────
   Message Bubble
───────────────────────────────────────────────────── */

function MessageBubble({ message: m }) {
  const [caveatsOpen, setCaveatsOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const hasCaveats = m.caveats && m.caveats.length > 0;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(m.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (m.type === 'error') {
    return (
      <div className="flex gap-3 items-start">
        <div className="h-7 w-7 rounded-full bg-red-900/30 flex items-center justify-center shrink-0 mt-0.5">
          <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
        </div>
        <div className="py-2.5 px-4 rounded-2xl rounded-tl-sm bg-red-950/20 border border-red-900/20 text-sm text-red-300/90 max-w-2xl">
          {m.text}
        </div>
      </div>
    );
  }

  if (m.type === 'user') {
    return (
      <div className="flex gap-3 justify-end">
        <div className="py-2.5 px-4 rounded-2xl rounded-tr-sm bg-blue-600 text-sm text-white max-w-2xl leading-relaxed">
          {m.text}
        </div>
        <Avatar type="user" />
      </div>
    );
  }

  // Agent response
  return (
    <div className="group flex gap-3 items-start">
      <Avatar type="agent" />
      <div className="max-w-3xl min-w-0 space-y-1.5">
        <div className="relative py-2.5 px-4 rounded-2xl rounded-tl-sm bg-slate-800/50 border border-slate-700/40">
          <div className="prose prose-invert prose-sm max-w-none
            prose-headings:font-semibold prose-headings:text-slate-100
            prose-h2:text-[15px] prose-h2:mt-4 prose-h2:mb-2
            prose-h3:text-[14px] prose-h3:mt-3 prose-h3:mb-1.5
            prose-p:text-slate-300 prose-p:text-[13px] prose-p:leading-relaxed prose-p:my-1.5
            prose-strong:text-white prose-strong:font-semibold
            prose-li:text-slate-300 prose-li:text-[13px] prose-li:my-0.5
            prose-a:text-blue-400 prose-a:no-underline hover:prose-a:underline
            prose-table:text-[12px] prose-th:text-slate-300 prose-th:font-medium prose-th:py-1.5 prose-td:text-slate-400 prose-td:py-1.5
            prose-hr:border-slate-700/50 prose-hr:my-3
            prose-code:text-blue-300 prose-code:bg-slate-700/50 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs
          ">
            <ReactMarkdown>{m.text}</ReactMarkdown>
          </div>

          {/* Copy button */}
          <button
            onClick={handleCopy}
            className="absolute -right-9 top-1 p-1.5 rounded-md opacity-0 group-hover:opacity-100 hover:bg-slate-700/50 text-slate-500 hover:text-slate-300 transition-all"
            title="Copy"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>

        {/* Data quality caveats — collapsible */}
        {hasCaveats && (
          <div className="pl-1">
            <button
              onClick={() => setCaveatsOpen(!caveatsOpen)}
              className="flex items-center gap-1.5 text-[11px] text-slate-600 hover:text-slate-400 transition-colors"
            >
              <AlertTriangle className="w-3 h-3" />
              <span>{m.caveats.length} data quality {m.caveats.length === 1 ? 'note' : 'notes'}</span>
              {caveatsOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            {caveatsOpen && (
              <ul className="mt-1.5 space-y-0.5 text-[11px] text-slate-500 pl-4 list-disc">
                {m.caveats.map((c, idx) => (
                  <li key={idx} className="leading-relaxed">{c}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
