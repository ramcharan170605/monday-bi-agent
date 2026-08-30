import React, { useEffect, useState } from 'react';
import { fetchWorkOrders, fetchDeals } from '../services/api';
import { Search, RefreshCw, AlertTriangle } from 'lucide-react';

export default function DataExplorer() {
  const [boardType, setBoardType] = useState('work_orders');
  const [workOrders, setWorkOrders] = useState([]);
  const [deals, setDeals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [sectorFilter, setSectorFilter] = useState('all');

  const loadData = async () => {
    setLoading(true);
    try {
      if (boardType === 'work_orders') {
        const data = await fetchWorkOrders(sectorFilter);
        setWorkOrders(data);
      } else {
        const data = await fetchDeals(sectorFilter);
        setDeals(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, [boardType, sectorFilter]);

  const items = boardType === 'work_orders' ? workOrders : deals;
  const filtered = items.filter(item => {
    const name = item.work_order_no || item.deal_name || '';
    const client = item.client_name || '';
    const sector = item.normalized_sector || '';
    const q = searchTerm.toLowerCase();
    return name.toLowerCase().includes(q) || client.toLowerCase().includes(q) || sector.toLowerCase().includes(q);
  });

  const StatusBadge = ({ status, type = 'status' }) => {
    const colors = {
      Completed: 'text-emerald-400 bg-emerald-500/8 border-emerald-500/15',
      Won: 'text-emerald-400 bg-emerald-500/8 border-emerald-500/15',
      Delayed: 'text-red-400 bg-red-500/8 border-red-500/15',
      Lost: 'text-red-400 bg-red-500/8 border-red-500/15',
      'In Progress': 'text-blue-400 bg-blue-500/8 border-blue-500/15',
      Proposal: 'text-blue-400 bg-blue-500/8 border-blue-500/15',
      Discovery: 'text-violet-400 bg-violet-500/8 border-violet-500/15',
      Negotiation: 'text-amber-400 bg-amber-500/8 border-amber-500/15',
    };
    const fallback = 'text-slate-400 bg-slate-500/8 border-slate-500/15';
    return (
      <span className={`inline-block px-2 py-0.5 rounded text-[11px] font-medium border ${colors[status] || fallback}`}>
        {status || 'Unknown'}
      </span>
    );
  };

  const formatCurrency = (val) => {
    if (!val || val === 0) return '—';
    const n = Number(val);
    if (n >= 1_000_000) return `₹${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `₹${(n / 1_000).toFixed(0)}K`;
    return `₹${n.toLocaleString()}`;
  };

  return (
    <div className="max-w-screen-2xl mx-auto p-4 sm:p-6 space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 rounded-xl bg-slate-800/30 border border-slate-700/30">
        <div className="flex items-center gap-1.5">
          {['work_orders', 'deals'].map((type) => (
            <button
              key={type}
              onClick={() => setBoardType(type)}
              className={`px-3 py-1.5 rounded-lg text-[13px] font-medium transition-colors ${
                boardType === type
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`}
            >
              {type === 'work_orders' ? 'Work Orders' : 'Deals Pipeline'}
              <span className="ml-1.5 text-slate-500 text-xs">
                ({type === 'work_orders' ? workOrders.length : deals.length})
              </span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2" />
            <input
              type="text"
              placeholder="Search…"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-8 pr-3 py-1.5 rounded-lg bg-slate-900/60 border border-slate-700/40 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-slate-600 w-40"
            />
          </div>

          <select
            value={sectorFilter}
            onChange={(e) => setSectorFilter(e.target.value)}
            className="px-2.5 py-1.5 rounded-lg bg-slate-900/60 border border-slate-700/40 text-xs text-slate-300 focus:outline-none focus:border-slate-600"
          >
            <option value="all">All Sectors</option>
            {['Energy', 'Mining', 'Infrastructure', 'Railways', 'Aviation', 'Manufacturing'].map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          <button
            onClick={loadData}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700/50 transition"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl bg-slate-800/20 border border-slate-700/30 overflow-hidden">
        <div className="overflow-x-auto">
          {boardType === 'work_orders' ? (
            <table className="w-full text-left text-[12px]">
              <thead className="text-slate-500 uppercase text-[10px] font-semibold tracking-wider border-b border-slate-700/30">
                <tr>
                  <th className="px-4 py-3">Work Order</th>
                  <th className="px-4 py-3">Client</th>
                  <th className="px-4 py-3">Sector</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Contract</th>
                  <th className="px-4 py-3 text-right">Actual Cost</th>
                  <th className="px-4 py-3">Pilot</th>
                  <th className="px-4 py-3">Due</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/20">
                {filtered.map((wo) => (
                  <tr key={wo.id} className="hover:bg-slate-800/30 transition-colors text-slate-300">
                    <td className="px-4 py-2.5 font-medium text-white flex items-center gap-1.5">
                      {wo.data_quality_flags?.length > 0 && <AlertTriangle className="w-3 h-3 text-amber-500/60 shrink-0" />}
                      <span>{wo.work_order_no || '—'}</span>
                    </td>
                    <td className="px-4 py-2.5">{wo.client_name || '—'}</td>
                    <td className="px-4 py-2.5 text-slate-400">{wo.normalized_sector || '—'}</td>
                    <td className="px-4 py-2.5"><StatusBadge status={wo.normalized_status} /></td>
                    <td className="px-4 py-2.5 text-right font-mono text-slate-200">{formatCurrency(wo.contract_value)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-slate-400">{formatCurrency(wo.actual_cost)}</td>
                    <td className="px-4 py-2.5 text-slate-400">{wo.assigned_pilot_or_lead || '—'}</td>
                    <td className="px-4 py-2.5 font-mono text-slate-500 text-[11px]">{wo.due_date || '—'}</td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan="8" className="px-4 py-8 text-center text-slate-500">No records found.</td></tr>
                )}
              </tbody>
            </table>
          ) : (
            <table className="w-full text-left text-[12px]">
              <thead className="text-slate-500 uppercase text-[10px] font-semibold tracking-wider border-b border-slate-700/30">
                <tr>
                  <th className="px-4 py-3">Deal</th>
                  <th className="px-4 py-3">Client</th>
                  <th className="px-4 py-3">Sector</th>
                  <th className="px-4 py-3">Stage</th>
                  <th className="px-4 py-3 text-right">Value</th>
                  <th className="px-4 py-3 text-right">Probability</th>
                  <th className="px-4 py-3 text-right">Weighted</th>
                  <th className="px-4 py-3">Owner</th>
                  <th className="px-4 py-3">Expected Close</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/20">
                {filtered.map((d) => (
                  <tr key={d.id} className="hover:bg-slate-800/30 transition-colors text-slate-300">
                    <td className="px-4 py-2.5 font-medium text-white flex items-center gap-1.5">
                      {d.data_quality_flags?.length > 0 && <AlertTriangle className="w-3 h-3 text-amber-500/60 shrink-0" />}
                      <span className="truncate max-w-[180px]">{d.deal_name || '—'}</span>
                    </td>
                    <td className="px-4 py-2.5">{d.client_name || '—'}</td>
                    <td className="px-4 py-2.5 text-slate-400">{d.normalized_sector || '—'}</td>
                    <td className="px-4 py-2.5"><StatusBadge status={d.normalized_stage} /></td>
                    <td className="px-4 py-2.5 text-right font-mono text-slate-200">{formatCurrency(d.deal_value)}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-slate-400">{d.probability || 0}%</td>
                    <td className="px-4 py-2.5 text-right font-mono text-emerald-400/80">{formatCurrency(d.weighted_value)}</td>
                    <td className="px-4 py-2.5 text-slate-400">{d.deal_owner || '—'}</td>
                    <td className="px-4 py-2.5 font-mono text-slate-500 text-[11px]">{d.expected_close_date || '—'}</td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan="9" className="px-4 py-8 text-center text-slate-500">No records found.</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Record count */}
      <div className="text-[11px] text-slate-500 px-1">
        Showing {filtered.length} of {items.length} records
      </div>
    </div>
  );
}
