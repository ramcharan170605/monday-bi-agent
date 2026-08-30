import React, { useEffect, useState } from 'react';
import { fetchDataQuality } from '../services/api';
import { RefreshCw } from 'lucide-react';

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

  useEffect(() => { loadData(); }, []);

  if (loading) {
    return (
      <div className="p-12 text-center text-sm text-slate-500 flex items-center justify-center gap-2">
        <RefreshCw className="w-4 h-4 animate-spin" />
        <span>Loading data quality report…</span>
      </div>
    );
  }

  const issues = report?.recent_issues || [];
  const filteredIssues = filterSeverity === 'ALL'
    ? issues
    : issues.filter(i => i.severity === filterSeverity);

  const StatCard = ({ label, value, color = 'text-white' }) => (
    <div className="px-5 py-4 rounded-xl bg-slate-800/30 border border-slate-700/30">
      <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
    </div>
  );

  const severityColor = (sev) => {
    if (sev === 'HIGH') return 'text-red-400 bg-red-500/8 border-red-500/15';
    if (sev === 'MEDIUM') return 'text-amber-400 bg-amber-500/8 border-amber-500/15';
    return 'text-slate-400 bg-slate-500/8 border-slate-500/15';
  };

  return (
    <div className="max-w-screen-2xl mx-auto p-4 sm:p-6 space-y-4">
      {/* Stat Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Hygiene Score" value={`${report?.data_hygiene_score ?? '—'}%`} color="text-blue-400" />
        <StatCard label="High Severity" value={report?.high_severity_count ?? 0} color="text-red-400" />
        <StatCard label="Medium Severity" value={report?.medium_severity_count ?? 0} color="text-amber-400" />
        <StatCard label="Low Severity" value={report?.low_severity_count ?? 0} color="text-slate-300" />
      </div>

      {/* Issues Table */}
      <div className="rounded-xl bg-slate-800/20 border border-slate-700/30 overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-700/30 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-white">Data Quality Issues</h3>
            <p className="text-[11px] text-slate-500 mt-0.5">{filteredIssues.length} issues found</p>
          </div>

          <div className="flex items-center gap-1.5">
            {['ALL', 'HIGH', 'MEDIUM', 'LOW'].map(sev => (
              <button
                key={sev}
                onClick={() => setFilterSeverity(sev)}
                className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
                  filterSeverity === sev
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {sev}
              </button>
            ))}
            <button
              onClick={loadData}
              className="p-1 rounded-md text-slate-500 hover:text-white transition"
            >
              <RefreshCw className="w-3 h-3" />
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12px]">
            <thead className="text-slate-500 uppercase text-[10px] font-semibold tracking-wider border-b border-slate-700/30">
              <tr>
                <th className="px-4 py-2.5">Severity</th>
                <th className="px-4 py-2.5">Board</th>
                <th className="px-4 py-2.5">Item</th>
                <th className="px-4 py-2.5">Field</th>
                <th className="px-4 py-2.5">Issue</th>
                <th className="px-4 py-2.5">Raw Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/20">
              {filteredIssues.map((iss) => (
                <tr key={iss.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-4 py-2.5">
                    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold border ${severityColor(iss.severity)}`}>
                      {iss.severity}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-slate-400 capitalize">{iss.board_type?.replace('_', ' ')}</td>
                  <td className="px-4 py-2.5 text-slate-200 font-medium max-w-[180px] truncate">{iss.item_name || '—'}</td>
                  <td className="px-4 py-2.5 text-blue-400/80">{iss.field_name}</td>
                  <td className="px-4 py-2.5 text-slate-400 max-w-[240px] truncate">{iss.details}</td>
                  <td className="px-4 py-2.5 text-slate-500 font-mono text-[11px] max-w-[120px] truncate">{iss.raw_value || '—'}</td>
                </tr>
              ))}
              {filteredIssues.length === 0 && (
                <tr>
                  <td colSpan="6" className="px-4 py-8 text-center text-slate-500">
                    No issues found for this filter.
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
