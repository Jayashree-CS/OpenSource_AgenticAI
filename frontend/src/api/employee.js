import { api } from './client';

const unwrap = (res) => {
  const body = res?.data ?? res;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

export const employeeAPI = {
  me: () => api.get('/api/employee/me').then(unwrap),
  leaveBalance: () => api.get('/api/employee/leave/balance').then(unwrap),
  leaveHistory: () => api.get('/api/employee/leave/history').then(unwrap),
  applyLeave: (payload) => api.post('/api/employee/leave/apply', payload).then(unwrap),
  listTickets: () => api.get('/api/employee/tickets').then(unwrap),
  createTicket: (payload) => api.post('/api/employee/tickets', payload).then(unwrap),
  listAssets: () => api.get('/api/employee/assets').then(unwrap),
  createAsset: (payload) => api.post('/api/employee/assets', payload).then(unwrap),
};

export default employeeAPI;
