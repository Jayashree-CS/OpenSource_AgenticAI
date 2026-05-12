import React from 'react';
import { Link } from 'react-router-dom';
import { itAPI } from '../api/it';
import useApi from '../hooks/useApi';
import { DataTable, ErrorState, Loading, PageHeader } from '../components/PageState';

export default function ITDashboard() {
  const tickets = useApi(() => itAPI.listTickets(), []);
  const assets = useApi(() => itAPI.pendingAssets(), []);
  const inventory = useApi(() => itAPI.inventory(), []);

  const loading = tickets.loading || assets.loading || inventory.loading;
  const error = tickets.error || assets.error || inventory.error;

  const allTickets = tickets.data || [];
  const openTickets = allTickets
    .filter((t) => !['closed', 'resolved', 'rejected'].includes((t.status || '').toLowerCase()))
    .sort((a, b) => (b.id || 0) - (a.id || 0));
  const high = openTickets.filter((t) => (t.priority || '').toLowerCase() === 'high').length;
  const pendingAssets = (assets.data || []).slice().sort((a, b) => (b.id || 0) - (a.id || 0));

  return (
    <div style={{ padding: 20 }}>
      <PageHeader title="IT Dashboard" subtitle="Tickets, assets and inventory at a glance" />

      {loading && <Loading />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 12,
              marginBottom: 24,
            }}
          >
            <Stat label="Open tickets" value={openTickets.length} />
            <Stat label="High priority" value={high} />
            <Stat label="Pending assets" value={pendingAssets.length} />
            <Stat label="Inventory items" value={(inventory.data || []).length} />
          </div>

          {/* New requests inbox — mirrors the manager dashboard's pending
              lists so IT users see incoming work the moment they log in. */}
          <section style={{ marginBottom: 24 }}>
            <h3>
              New / Open Tickets{' '}
              {openTickets.length > 0 && (
                <span style={badgeStyle}>{openTickets.length}</span>
              )}
            </h3>
            <DataTable
              columns={[
                { key: 'id', label: 'ID' },
                { key: 'user_id', label: 'Employee' },
                { key: 'issue_type', label: 'Type' },
                { key: 'priority', label: 'Priority' },
                { key: 'status', label: 'Status' },
              ]}
              rows={openTickets.slice(0, 10)}
              emptyMessage="No open tickets — you're all caught up."
            />
            {openTickets.length > 10 && (
              <div style={{ marginTop: 8, color: 'var(--text-muted)', fontSize: 13 }}>
                Showing 10 of {openTickets.length}.{' '}
                <Link to="/it/tickets">See all tickets →</Link>
              </div>
            )}
          </section>

          <section style={{ marginBottom: 24 }}>
            <h3>
              Pending Asset Approvals{' '}
              {pendingAssets.length > 0 && (
                <span style={badgeStyle}>{pendingAssets.length}</span>
              )}
            </h3>
            <DataTable
              columns={[
                { key: 'id', label: 'ID' },
                { key: 'user_id', label: 'Employee' },
                { key: 'asset_type', label: 'Asset' },
                { key: 'status', label: 'Status' },
              ]}
              rows={pendingAssets.slice(0, 10)}
              emptyMessage="No asset requests waiting on IT."
            />
          </section>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Link to="/it/tickets" style={linkBtn}>Resolve Tickets →</Link>
            <Link to="/it/inventory" style={linkBtn}>Manage Inventory →</Link>
          </div>
        </>
      )}
    </div>
  );
}

const badgeStyle = {
  display: 'inline-block',
  marginLeft: 8,
  padding: '2px 8px',
  borderRadius: 999,
  background: '#dc2626',
  color: '#fff',
  fontSize: 12,
  fontWeight: 700,
  verticalAlign: 'middle',
};

function Stat({ label, value }) {
  return (
    <div style={{ padding: 14, borderRadius: 12, border: '1px solid var(--border,#e5e7eb)' }}>
      <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700 }}>{value}</div>
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
