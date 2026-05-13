import React, { useState } from 'react';
import { managerAPI } from '../api/manager';
import useApi from '../hooks/useApi';
import { useToast } from '../components/Toast';
import { DataTable, ErrorState, Loading, PageHeader } from '../components/PageState';
import { formatAssetStatus } from '../utils/assetStatus';

export default function ManagerDashboard() {
  const { toast } = useToast();
  const summary = useApi(() => managerAPI.approvalsSummary(), []);
  const leaves = useApi(() => managerAPI.pendingLeaves(), []);
  const assets = useApi(() => managerAPI.pendingAssets(), []);
  const [busy, setBusy] = useState({});

  const act = async (kind, id, action) => {
    setBusy((b) => ({ ...b, [`${kind}-${id}`]: true }));
    try {
      if (kind === 'leave') await managerAPI.actionLeave(id, action);
      else await managerAPI.actionAsset(id, action);
      toast(`${kind === 'leave' ? 'Leave' : 'Asset'} ${action}d`, { type: 'success' });
      summary.refetch();
      leaves.refetch();
      assets.refetch();
    } catch (err) {
      toast(err?.message || 'Action failed', { type: 'error' });
    } finally {
      setBusy((b) => ({ ...b, [`${kind}-${id}`]: false }));
    }
  };

  return (
    <div style={{ padding: 20 }}>
      <PageHeader title="Manager Dashboard" subtitle="Approve pending requests from your team" />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 12,
          marginBottom: 24,
        }}
      >
        <Stat label="Pending leaves" value={summary.data?.pending_leaves ?? '—'} />
        <Stat label="Pending assets" value={summary.data?.pending_assets ?? '—'} />
      </div>

      <section style={{ marginBottom: 24 }}>
        <h3>Pending Leaves</h3>
        {leaves.loading && <Loading />}
        {leaves.error && <ErrorState message={leaves.error} onRetry={leaves.refetch} />}
        {!leaves.loading && !leaves.error && (
          <DataTable
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'employee_id', label: 'Employee' },
              { key: 'leave_type', label: 'Type' },
              { key: 'start_date', label: 'From' },
              { key: 'end_date', label: 'To' },
              { key: 'reason', label: 'Reason' },
              {
                key: '_act',
                label: 'Action',
                render: (r) => (
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      onClick={() => act('leave', r.id, 'approve')}
                      disabled={busy[`leave-${r.id}`]}
                      style={approveBtn}
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => act('leave', r.id, 'reject')}
                      disabled={busy[`leave-${r.id}`]}
                      style={rejectBtn}
                    >
                      Reject
                    </button>
                  </div>
                ),
              },
            ]}
            rows={leaves.data || []}
            emptyMessage="No pending leaves"
          />
        )}
      </section>

      <section>
        <h3>Pending Asset Requests</h3>
        {assets.loading && <Loading />}
        {assets.error && <ErrorState message={assets.error} onRetry={assets.refetch} />}
        {!assets.loading && !assets.error && (
          <DataTable
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'user_id', label: 'Employee' },
              { key: 'asset_type', label: 'Asset' },
              {
                key: 'status',
                label: 'Status',
                render: (row) => formatAssetStatus(row),
              },
              { key: 'reason', label: 'Reason' },
              {
                key: '_act',
                label: 'Action',
                render: (r) => (
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      onClick={() => act('asset', r.id, 'approve')}
                      disabled={busy[`asset-${r.id}`]}
                      style={approveBtn}
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => act('asset', r.id, 'reject')}
                      disabled={busy[`asset-${r.id}`]}
                      style={rejectBtn}
                    >
                      Reject
                    </button>
                  </div>
                ),
              },
            ]}
            rows={assets.data || []}
            emptyMessage="No pending asset requests"
          />
        )}
      </section>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div style={{ padding: 14, borderRadius: 12, border: '1px solid var(--border,#e5e7eb)' }}>
      <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

const approveBtn = {
  padding: '6px 10px',
  borderRadius: 8,
  border: 'none',
  background: '#16a34a',
  color: '#fff',
  cursor: 'pointer',
};
const rejectBtn = {
  padding: '6px 10px',
  borderRadius: 8,
  border: 'none',
  background: '#dc2626',
  color: '#fff',
  cursor: 'pointer',
};
