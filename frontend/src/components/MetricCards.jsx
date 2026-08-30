import React from 'react';
import { TrendingUp, TrendingDown, AlertTriangle, Activity } from 'lucide-react';

export default function MetricCards({ metrics }) {
  if (!metrics || metrics.length === 0) return null;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 my-4">
      {metrics.map((m, idx) => {
        const isPositive = m.sentiment === 'positive';
        const isWarning = m.sentiment === 'warning';
        const isNegative = m.sentiment === 'negative';

        return (
          <div
            key={idx}
            className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition flex flex-col justify-between shadow-sm"
          >
            <div className="flex items-center justify-between text-xs text-slate-400 font-medium mb-1">
              <span className="truncate">{m.label}</span>
              {isPositive && <TrendingUp className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
              {isWarning && <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />}
              {isNegative && <TrendingDown className="w-3.5 h-3.5 text-rose-400 shrink-0" />}
              {!isPositive && !isWarning && !isNegative && <Activity className="w-3.5 h-3.5 text-sky-400 shrink-0" />}
            </div>
            
            <div className="text-lg font-bold text-white tracking-tight my-0.5 truncate">
              {m.value}
            </div>

            {m.subtext && (
              <div className="text-[11px] text-slate-400 truncate mt-1">
                {m.subtext}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
