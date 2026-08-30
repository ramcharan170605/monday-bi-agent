import React, { useState, useEffect, useRef } from 'react';
import Header from './components/Header';
import MetricCards from './components/MetricCards';
import DataQualityDrawer from './components/DataQualityDrawer';
import DataExplorer from './components/DataExplorer';
import { fetchHealth, syncBoards, askAgent } from './services/api';
import { Send, Sparkles, AlertTriangle, ShieldCheck, ChevronDown, ChevronUp, ArrowRight, Bot, User, RefreshCw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

const SUGGESTED_QUESTIONS = [
  "How's our pipeline looking for the energy sector this quarter?",
  "What is our work order completion rate and execution backlog?",
  "Prepare data for our upcoming leadership update",
  "What data quality issues exist across our Monday boards?"
];

export default function App() {
  const [health, setHealth] = useState(null);
  const [activeTab, setActiveTab] = useState('chat');
  const [isSyncing, setIsSyncing] = useState(false);
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      type: 'agent',
      text: `👋 **Welcome to the Skylark Drones Business Intelligence Agent.**

I continuously analyze our live **Monday.com Work Orders** and **Deals Funnel** boards cached in Neon PostgreSQL. Ask me any founder-level query regarding revenue, sectoral pipeline velocity, flight operations backlog, or leadership briefing data.

Select a quick question below or type your inquiry:`
    }
  ]);

  const messagesEndRef = useRef(null);

  const loadHealth = async () => {
    try {
      const data = await fetchHealth();
      setHealth(data);
    } catch (err) {
      console.error('Health fetch error:', err);
    }
  };

  useEffect(() => {
    loadHealth();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSync = async () => {
    setIsSyncing(true);
    try {
      await syncBoards();
      await loadHealth();
      setMessages(prev => [
        ...prev,
        {
          id: Date.now().toString(),
          type: 'system',
          text: '🔄 **Monday.com Boards Synced Successfully:** Analytical cache in Neon updated with latest Work Orders and Deals.'
        }
      ]);
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
    const userMsgId = Date.now().toString();
    const compactHistory = messages
      .filter((m) => m.type === 'user' || m.type === 'agent')
      .slice(-8)
      .map((m) => ({
        type: m.type,
        text: m.text,
        executive_summary: m.executive_summary,
        caveats: m.caveats,
        assumptions: m.assumptions,
        actions: m.actions,
        tools_used: m.tools_used,
        raw_data_summary: m.raw_data_summary
      }));
    setMessages(prev => [
      ...prev,
      { id: userMsgId, type: 'user', text: textToSend }
    ]);

    setIsLoading(true);

    try {
      const resp = await askAgent(textToSend, compactHistory);
      
      let displayText = resp.answer || '';
      if (typeof displayText === 'string' && displayText.trim().startsWith('{') && displayText.includes('"answer"')) {
        try {
          const parsed = JSON.parse(displayText.trim());
          if (parsed.answer) displayText = parsed.answer;
        } catch (e) {
          const match = displayText.match(/"answer"\s*:\s*"((?:[^"\\]|\\.)*)"/);
          if (match && match[1]) {
            displayText = match[1].replace(/\\n/g, '\n').replace(/\\"/g, '"');
          }
        }
      }

      setMessages(prev => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          type: 'agent',
          text: displayText,
          executive_summary: resp.executive_summary,
          metrics: resp.metrics,
          caveats: resp.data_quality_caveats,
          assumptions: resp.assumptions_made,
          actions: resp.recommended_actions,
          tools_used: resp.tools_used,
          raw_data_summary: resp.raw_data_summary
        }
      ]);
    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          type: 'error',
          text: `⚠️ **Error generating response:** ${err.message}`
        }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100 font-sans">
      <Header
        health={health}
        isSyncing={isSyncing}
        onSync={handleSync}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />

      <main className="flex-1 flex flex-col max-w-7xl w-full mx-auto">
        {activeTab === 'chat' && (
          <div className="flex-1 flex flex-col h-[calc(100vh-4rem)] p-4 sm:p-6 max-w-5xl mx-auto w-full">
            <div className="mb-4">
              <div className="text-xs font-semibold text-slate-400 mb-2 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-sky-400" />
                <span>Recommended Founder Questions</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {SUGGESTED_QUESTIONS.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSend(q)}
                    disabled={isLoading}
                    className="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs text-slate-300 hover:text-white transition text-left flex items-center gap-1.5 shadow-sm"
                  >
                    <span>{q}</span>
                    <ArrowRight className="w-3 h-3 text-sky-400 opacity-70" />
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto space-y-5 pr-2 pb-4">
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={`flex gap-3 ${m.type === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {m.type !== 'user' && (
                    <div className="h-8 w-8 rounded-lg bg-sky-600/20 border border-sky-500/30 flex items-center justify-center text-sky-400 shrink-0 mt-1">
                      <Bot className="w-4 h-4" />
                    </div>
                  )}

                  <div
                    className={`max-w-3xl rounded-2xl p-4 sm:p-5 text-sm leading-relaxed ${
                      m.type === 'user'
                        ? 'bg-sky-600 text-white rounded-br-none shadow-md shadow-sky-600/10'
                        : m.type === 'error'
                        ? 'bg-rose-950/40 border border-rose-800 text-rose-200 rounded-bl-none'
                        : m.type === 'system'
                        ? 'bg-slate-900 border border-slate-800 text-sky-300 rounded-xl'
                        : 'bg-slate-900/90 border border-slate-800/90 rounded-bl-none text-slate-200 shadow-sm'
                    }`}
                  >
                    {m.metrics && <MetricCards metrics={m.metrics} />}

                    <div className="prose prose-invert prose-sm max-w-none prose-headings:font-bold prose-headings:text-white prose-p:my-2 prose-table:my-3 prose-th:text-slate-300 prose-td:text-slate-300">
                      <ReactMarkdown>{m.text}</ReactMarkdown>
                    </div>

                    {m.caveats && m.caveats.length > 0 && (
                      <div className="mt-4 pt-3 border-t border-slate-800/80 space-y-2">
                        <div className="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>Data Quality Caveats & Integrity Notes</span>
                        </div>
                        <ul className="text-xs text-slate-400 space-y-1 pl-4 list-disc">
                          {m.caveats.map((c, idx) => (
                            <li key={idx}>{c}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {m.tools_used && m.tools_used.length > 0 && (
                      <div className="mt-3 pt-2 text-[10px] text-slate-500 font-mono flex items-center gap-2">
                        <span>Engine tools dispatched:</span>
                        {m.tools_used.map((t, idx) => (
                          <span key={idx} className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800">
                            {t}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {m.type === 'user' && (
                    <div className="h-8 w-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 shrink-0 mt-1">
                      <User className="w-4 h-4" />
                    </div>
                  )}
                </div>
              ))}

              {isLoading && (
                <div className="flex gap-3 items-start">
                  <div className="h-8 w-8 rounded-lg bg-sky-600/20 border border-sky-500/30 flex items-center justify-center text-sky-400 shrink-0 mt-1">
                    <Bot className="w-4 h-4 animate-bounce" />
                  </div>
                  <div className="p-4 rounded-2xl rounded-bl-none bg-slate-900 border border-slate-800 flex items-center gap-3 text-slate-400 text-xs">
                    <RefreshCw className="w-4 h-4 animate-spin text-sky-400" />
                    <span>Executing SQL calculations & synthesizing executive answer...</span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            <div className="pt-2">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSend();
                }}
                className="relative flex items-center"
              >
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Ask a question about pipeline, work orders backlog, revenue, or leadership updates..."
                  className="w-full pl-4 pr-12 py-3.5 rounded-2xl bg-slate-900 border border-slate-800 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 shadow-lg shadow-black/20"
                />
                <button
                  type="submit"
                  disabled={!query.trim() || isLoading}
                  className="absolute right-2 p-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white disabled:opacity-40 disabled:hover:bg-sky-600 transition shadow-sm"
                >
                  <Send className="w-4 h-4" />
                </button>
              </form>
              <div className="flex items-center justify-between text-[11px] text-slate-500 mt-2 px-1">
                <span>Direct Neon PostgreSQL analytical cache + Groq LLM tool engine</span>
                <span>Press Enter ↵ to submit</span>
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
