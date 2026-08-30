import React, { useEffect, useState } from 'react';
import { fetchDataQuality } from '../services/api';
import { AlertCircle, AlertTriangle, CheckCircle, RefreshCw, ShieldAlert } from 'lucide-react';

export default function DataQualityDrawer() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filterSeverity, setFilterSeverity] = useState('ALL');

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await fetchDataQuality();
      setReport(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="p-8 text-center text-slate-400 flex items-center justify-center gap-2">
        <RefreshCw className="w-5 h-5 animate-spin text-sky-400" />
        <span>Auditing Monday.com Data Quality...</span>
      </div>
    );
  }

  const issues = report?.recent_issues || [];
  const filteredIssues = filterSeverity === 'ALL'
    ? issues
    : issues.filter(i => i.severity === filterSeverity);

  return (
    <div className="max-w-7xl mx-auto p-4 sm:p-6 space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Data Hygiene Score</div>
            <div className="text-3xl font-extrabold text-white mt-1">{report?.data_hygiene_score}%</div>
            <p className="text-xs text-slate-400 mt-1">Cross-board integrity metric</p>
          </div>
          <div className="h-12 w-12 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
            <ShieldAlert className="w-6 h-6" />
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-rose-400 uppercase tracking-wider">High Severity Issues</div>
            <div className="text-3xl font-extrabold text-white mt-1">{report?.high_severity_count}</div>
            <p className="text-xs text-slate-400 mt-1">Invalid values / Missing IDs</p>
          </div>
          <div className="h-12 w-12 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
            <AlertCircle className="w-6 h-6" />
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-amber-400 uppercase tracking-wider">Medium Severity</div>
            <div className="text-3xl font-extrabold text-white mt-1">{report?.medium_severity_count}</div>
            <p className="text-xs text-slate-400 mt-1">Missing target dates / Pilots</p>
          </div>
          <div className="h-12 w-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
            <AlertTriangle className="w-6 h-6" />
          </div>
        </div>

        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">Low / Warnings</div>
            <div className="text-3xl font-extrabold text-white mt-1">{report?.low_severity_count}</div>
            <p className="text-xs text-slate-400 mt-1">Non-standard sector strings</p>
          </div>
          <div className="h-12 w-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <CheckCircle className="w-6 h-6" />
          </div>
        </div>
      </div>

      <div className="rounded-2xl bg-slate-900 border border-slate-800 overflow-hidden shadow-sm">
        <div className="p-4 sm:px-6 border-b border-slate-800 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-bold text-white">Detected Data Quality Caveats ({filteredIssues.length})</h3>
            <p className="text-xs text-slate-400">Real-time anomalies scanned during Monday sync</p>
          </div>

          <div className="flex items-center gap-2">
            {['ALL', 'HIGH', 'MEDIUM', 'LOW'].map(sev => (
              <button
                key={sev}
                onClick={() => setFilterSeverity(sev)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                  filterSeverity === sev
                    ? 'bg-sky-600 text-white'
                    : 'bg-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                {sev}
              </button>
            ))}
            <button
              onClick={loadData}
              className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-white transition"
              title="Refresh"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-950/60 text-slate-400 uppercase font-semibold border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Board</th>
                <th className="px-4 py-3">Item / Entity</th>
                <th className="px-4 py-3">Field</th>
                <th className="px-4 py-3">Issue Detail</th>
                <th className="px-4 py-3">Raw Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {filteredIssues.map((iss) => {
                const isHigh = iss.severity === 'HIGH';
                const isMed = iss.severity === 'MEDIUM';

                return (
                  <tr key={iss.id} className="hover:bg-slate-800/40 transition">
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        isHigh ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' :
                        isMed ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                        'bg-slate-800 text-slate-400'
                      }`}>
                        {iss.severity}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-sans capitalize text-slate-300">{iss.board_type.replace('_', ' ')}</td>
                    <td className="px-4 py-3 font-sans font-medium text-white max-w-[200px] truncate">{iss.item_name || 'N/A'}</td>
                    <td className="px-4 py-3 text-sky-400">{iss.field_name}</td>
                    <td className="px-4 py-3 font-sans text-slate-300 max-w-[260px] truncate">{iss.details}</td>
                    <td className="px-4 py-3 text-slate-400 max-w-[150px] truncate">{iss.raw_value || 'None'}</td>
                  </tr>
                );
              })}
              {filteredIssues.length === 0 && (
                <tr>
                  <td colSpan="6" className="px-4 py-8 text-center text-slate-400 font-sans">
                    No data quality issues found for this filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
