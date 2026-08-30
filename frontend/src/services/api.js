const API_BASE = import.meta.env.VITE_API_URL || '/api';

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Health check failed');
  return res.json();
}

export async function syncBoards(forceMock = false) {
  const res = await fetch(`${API_BASE}/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ board_type: 'all', force_mock: forceMock })
  });
  if (!res.ok) throw new Error('Sync failed');
  return res.json();
}

export async function askAgent(query) {
  const res = await fetch(`${API_BASE}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to process query' }));
    throw new Error(err.detail || 'Failed to process query');
  }
  return res.json();
}

export async function fetchDataQuality() {
  const res = await fetch(`${API_BASE}/data-quality`);
  if (!res.ok) throw new Error('Failed to fetch data quality');
  return res.json();
}

export async function fetchBoardsOverview() {
  const res = await fetch(`${API_BASE}/boards/overview`);
  if (!res.ok) throw new Error('Failed to fetch boards overview');
  return res.json();
}

export async function fetchWorkOrders(sector = 'all', status = 'all') {
  const url = new URL(`${API_BASE}/data/work-orders`, window.location.origin);
  if (sector !== 'all') url.searchParams.append('sector', sector);
  if (status !== 'all') url.searchParams.append('status', status);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error('Failed to fetch work orders');
  return res.json();
}

export async function fetchDeals(sector = 'all', stage = 'all') {
  const url = new URL(`${API_BASE}/data/deals`, window.location.origin);
  if (sector !== 'all') url.searchParams.append('sector', sector);
  if (stage !== 'all') url.searchParams.append('stage', stage);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error('Failed to fetch deals');
  return res.json();
}
