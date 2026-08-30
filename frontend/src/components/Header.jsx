import React from 'react';
import { RefreshCw } from 'lucide-react';

export default function Header({ health, isSyncing, onSync, activeTab, setActiveTab }) {
  const tabs = [
    { key: 'chat', label: 'Ask AI' },
    { key: 'explorer', label: 'Data Explorer' },
    { key: 'quality', label: 'Data Quality' },
  ];

  return (
    <header className="h-14 border-b border-slate-800/80 bg-[#0d1117] sticky top-0 z-30">
      <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 h-full flex items-center justify-between">

        {/* Logo */}
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-blue-600 flex items-center justify-center">
            <span className="text-sm font-bold text-white">S</span>
          </div>
          <span className="text-sm font-semibold text-white tracking-tight hidden sm:block">
            Skylark Drones
          </span>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center gap-0.5">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`relative px-4 py-1.5 text-[13px] font-medium rounded-md transition-colors ${
                activeTab === tab.key
                  ? 'text-white bg-slate-800'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        {/* Right: Status + Sync */}
        <div className="flex items-center gap-3">
          <div className="hidden md:flex items-center gap-1.5 text-xs text-slate-500">
            <span className={`h-1.5 w-1.5 rounded-full ${health?.database_connected ? 'bg-emerald-400' : 'bg-red-400'}`} />
            <span>{health?.database_connected ? 'Neon Connected' : 'Neon Offline'}</span>
          </div>

          <button
            onClick={onSync}
            disabled={isSyncing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700/50 transition disabled:opacity-40"
          >
            <RefreshCw className={`w-3 h-3 ${isSyncing ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{isSyncing ? 'Syncing…' : 'Sync'}</span>
          </button>
        </div>

      </div>
    </header>
  );
}
