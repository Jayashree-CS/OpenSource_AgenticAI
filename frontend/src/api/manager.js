import { api } from './client';

const unwrap = (res) => {
  const body = res?.data ?? res;
  if (body && typeof body === 'object' && 'data' in body) return body.data;
  return body;
};

export const managerAPI = {
  approvalsSummary: () => api.get('/api/manager/approvals/summary').then(unwrap),
  pendingLeaves: () => api.get('/api/manager/leaves/pending').then(unwrap),
  actionLeave: (id, action) => api.post(`/api/manager/leaves/${id}`, { action }).then(unwrap),
  pendingAssets: () => api.get('/api/manager/assets/pending').then(unwrap),
  actionAsset: (id, action) => api.post(`/api/manager/assets/${id}`, { action }).then(unwrap),
  teamOverview: () => api.get('/api/manager/team/overview').then(unwrap),
};

export default managerAPI;
