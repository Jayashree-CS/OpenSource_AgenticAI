import { api } from './client';

const unwrap = (res) => {
  const body = res?.data ?? res;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

export const adminApi = {
  logs: () => api.get('/api/admin/logs').then(unwrap),
  users: () => api.get('/api/admin/users').then(unwrap),
  createUser: (payload) => api.post('/api/admin/users', payload).then(unwrap),
  deleteUser: (id) => api.delete(`/api/admin/users/${id}`).then(unwrap),
  inventory: () => api.get('/api/admin/inventory').then(unwrap),
  upsertInventory: (payload) => api.post('/api/admin/inventory', payload).then(unwrap),
  analytics: () => api.get('/api/admin/analytics').then(unwrap),
};

export default adminApi;
