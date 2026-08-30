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

  useEffect(() => {
    loadData();
  }, [boardType, sectorFilter]);

  const items = boardType === 'work_orders' ? workOrders : deals;
  const filtered = items.filter(item => {
    const name = item.work_order_no || item.deal_name || '';
    const client = item.client_name || '';
    const sector = item.normalized_sector || '';
    const q = searchTerm.toLowerCase();
    return name.toLowerCase().includes(q) || client.toLowerCase().includes(q) || sector.toLowerCase().includes(q);
  });

  return (
    <div className="max-w-7xl mx-auto p-4 sm:p-6 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl bg-slate-900 border border-slate-800">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setBoardType('work_orders')}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition ${
              boardType === 'work_orders'
                ? 'bg-sky-600 text-white shadow-md shadow-sky-600/20'
                : 'bg-slate-800 text-slate-400 hover:text-white'
            }`}
          >
            Work Orders Board ({workOrders.length})
          </button>
          <button
            onClick={() => setBoardType('deals')}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition ${
              boardType === 'deals'
                ? 'bg-sky-600 text-white shadow-md shadow-sky-600/20'
                : 'bg-slate-800 text-slate-400 hover:text-white'
            }`}
          >
            Deals Pipeline Board ({deals.length})
          </button>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search items, clients..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-8 pr-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 w-48"
            />
          </div>

          <select
            value={sectorFilter}
            onChange={(e) => setSectorFilter(e.target.value)}
            className="px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-sky-500"
          >
            <option value="all">All Sectors</option>
            <option value="Energy">Energy</option>
            <option value="Mining">Mining</option>
            <option value="Infrastructure">Infrastructure</option>
            <option value="Telecom">Telecom</option>
            <option value="Agriculture">Agriculture</option>
          </select>

          <button
            onClick={loadData}
            className="p-2 rounded-xl bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="rounded-2xl bg-slate-900 border border-slate-800 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          {boardType === 'work_orders' ? (
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-950/60 text-slate-400 uppercase font-semibold border-b border-slate-800">
                <tr>
                  <th className="px-4 py-3">Work Order #</th>
                  <th className="px-4 py-3">Client</th>
                  <th className="px-4 py-3">Sector</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Contract Value</th>
                  <th className="px-4 py-3">Actual Cost</th>
                  <th className="px-4 py-3">Lead Pilot</th>
                  <th className="px-4 py-3">Due Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filtered.map((wo) => {
                  const hasFlags = wo.data_quality_flags && wo.data_quality_flags.length > 0;
                  const isCompleted = wo.normalized_status === 'Completed';
                  const isDelayed = wo.normalized_status === 'Delayed';

                  return (
                    <tr key={wo.id} className="hover:bg-slate-800/40 transition">
                      <td className="px-4 py-3 font-medium text-white flex items-center gap-2">
                        {hasFlags && <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" title="Data quality caveats detected" />}
                        <span>{wo.work_order_no || 'N/A'}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-200">{wo.client_name || 'N/A'}</td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded-md bg-slate-800 text-sky-400 font-medium">
                          {wo.normalized_sector || 'Unassigned'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ${
                          isCompleted ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                          isDelayed ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' :
                          'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                        }`}>
                          {wo.normalized_status || 'Unknown'}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono font-semibold text-white">
                        {wo.contract_value ? `$${Number(wo.contract_value).toLocaleString()}` : '$0'}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-400">
                        {wo.actual_cost ? `$${Number(wo.actual_cost).toLocaleString()}` : '$0'}
                      </td>
                      <td className="px-4 py-3 text-slate-300">{wo.assigned_pilot_or_lead || 'Unassigned'}</td>
                      <td className="px-4 py-3 font-mono text-slate-400">{wo.due_date || 'None'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-950/60 text-slate-400 uppercase font-semibold border-b border-slate-800">
                <tr>
                  <th className="px-4 py-3">Deal Name</th>
                  <th className="px-4 py-3">Client</th>
                  <th className="px-4 py-3">Sector</th>
                  <th className="px-4 py-3">Stage</th>
                  <th className="px-4 py-3">Deal Value</th>
                  <th className="px-4 py-3">Win Prob</th>
                  <th className="px-4 py-3">Weighted Value</th>
                  <th className="px-4 py-3">Owner</th>
                  <th className="px-4 py-3">Expected Close</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filtered.map((d) => {
                  const hasFlags = d.data_quality_flags && d.data_quality_flags.length > 0;
                  const isWon = d.normalized_stage === 'Won';
                  const isLost = d.normalized_stage === 'Lost';

                  return (
                    <tr key={d.id} className="hover:bg-slate-800/40 transition">
                      <td className="px-4 py-3 font-medium text-white flex items-center gap-2">
                        {hasFlags && <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" title="Data quality caveat" />}
                        <span>{d.deal_name || 'N/A'}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-200">{d.client_name || 'N/A'}</td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded-md bg-slate-800 text-sky-400 font-medium">
                          {d.normalized_sector || 'Unassigned'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ${
                          isWon ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                          isLost ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' :
                          'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                        }`}>
                          {d.normalized_stage || 'Unknown'}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-mono font-semibold text-white">
                        {d.deal_value ? `$${Number(d.deal_value).toLocaleString()}` : '$0'}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-300">{d.probability || 0}%</td>
                      <td className="px-4 py-3 font-mono text-emerald-400 font-medium">
                        {d.weighted_value ? `$${Number(d.weighted_value).toLocaleString()}` : '$0'}
                      </td>
                      <td className="px-4 py-3 text-slate-300">{d.deal_owner || 'N/A'}</td>
                      <td className="px-4 py-3 font-mono text-slate-400">{d.expected_close_date || 'None'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
