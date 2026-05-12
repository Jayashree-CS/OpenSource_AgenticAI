import { api } from './client';

const unwrap = (res) => {
  const body = res?.data ?? res;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

export const itAPI = {
  listTickets: () => api.get('/api/it/tickets').then(unwrap),
  openTickets: () =>
    api.get('/api/it/tickets').then(unwrap).then((rows) =>
      (Array.isArray(rows) ? rows : []).filter((t) =>
        ['open', 'in_progress'].includes(String(t.status || '').toLowerCase())
      )
    ),
  updateTicket: (id, status) => api.put(`/api/it/tickets/${id}`, { status }).then(unwrap),
  pendingAssets: () => api.get('/api/it/assets/pending').then(unwrap),
  actionAsset: (id, action) => api.post(`/api/it/assets/${id}`, { action }).then(unwrap),
  inventory: () => api.get('/api/it/inventory').then(unwrap),
  upsertInventory: (payload) => api.post('/api/it/inventory', payload).then(unwrap),
};

export default itAPI;
