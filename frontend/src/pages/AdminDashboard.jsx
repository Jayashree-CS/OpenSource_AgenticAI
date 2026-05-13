import React from 'react';
import { Link } from 'react-router-dom';
import { adminApi } from '../api/admin';
import useApi from '../hooks/useApi';
import { ErrorState, Loading, PageHeader } from '../components/PageState';
import ApprovalWidget from '../components/ApprovalWidget';

export default function AdminDashboard() {
  const analytics = useApi(() => adminApi.analytics(), []);

  return (
    <div style={{ padding: 20 }}>
      <PageHeader title="Admin Dashboard" subtitle="System-wide overview" />

      {analytics.loading && <Loading />}
      {analytics.error && <ErrorState message={analytics.error} onRetry={analytics.refetch} />}
      {!analytics.loading && !analytics.error && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 12,
              marginBottom: 24,
            }}
          >
            {Object.entries(analytics.data || {}).map(([k, v]) => (
              <Stat key={k} label={k.replace(/_/g, ' ')} value={v} />
            ))}
          </div>

          {/* Admin is superior to manager + IT — surface every pending
              approval across the company so the queue is never blank. */}
          <div style={{ marginBottom: 24 }}>
            <ApprovalWidget role="admin" />
          </div>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Link to="/manager/approvals" style={linkBtn}>Approval History →</Link>
            <Link to="/admin/users" style={linkBtn}>User Management →</Link>
            <Link to="/admin/system-logs" style={linkBtn}>System Logs →</Link>
            <Link to="/admin/analytics" style={linkBtn}>Analytics →</Link>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div style={{ padding: 14, borderRadius: 12, border: '1px solid var(--border,#e5e7eb)' }}>
      <div style={{ color: 'var(--text-muted)', fontSize: 13, textTransform: 'capitalize' }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700 }}>{String(value)}</div>
    </div>
  );
}

const linkBtn = {
  padding: '10px 14px',
  borderRadius: 10,
  border: '1px solid var(--border,#e5e7eb)',
  background: 'rgba(0,0,0,0.04)',
  color: 'inherit',
  textDecoration: 'none',
  fontWeight: 600,
};
