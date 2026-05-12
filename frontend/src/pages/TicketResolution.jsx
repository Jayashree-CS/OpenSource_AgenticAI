import React, { useState } from 'react';
import { itAPI } from '../api/it';
import useApi from '../hooks/useApi';
import { useToast } from '../components/Toast';
import { DataTable, ErrorState, Loading, PageHeader } from '../components/PageState';

const ALL_STATUSES = ['open', 'in_progress', 'resolved', 'closed', 'rejected'];
const TERMINAL_STATUSES = new Set(['resolved', 'closed', 'rejected']);

// Allowed next statuses per current status. Mirrors the backend
// TICKET_TRANSITIONS table in backend/actions/it_action.py so the UI
// and API always agree.
const NEXT_STATUSES = {
  open:         ['open', 'in_progress', 'rejected'],
  in_progress:  ['in_progress', 'closed', 'resolved', 'rejected'],
  resolved:     ['resolved'],
  closed:       ['closed'],
  rejected:     ['rejected'],
};

function allowedNext(current) {
  const key = (current || 'open').toLowerCase();
  return NEXT_STATUSES[key] || ALL_STATUSES;
}

export default function TicketResolution() {
  const { toast } = useToast();
  const list = useApi(() => itAPI.listTickets(), []);
  const assets = useApi(() => itAPI.pendingAssets(), []);
  const [busy, setBusy] = useState({});

  const setStatus = async (id, status) => {
    setBusy((b) => ({ ...b, [`t-${id}`]: true }));
    try {
      await itAPI.updateTicket(id, status);
      toast(`Ticket #${id} → ${status}`, { type: 'success' });
      list.refetch();
    } catch (err) {
      toast(err?.message || 'Update failed', { type: 'error' });
    } finally {
      setBusy((b) => ({ ...b, [`t-${id}`]: false }));
    }
  };

  const actAsset = async (id, action) => {
    setBusy((b) => ({ ...b, [`a-${id}`]: true }));
    try {
      await itAPI.actionAsset(id, action);
      toast(`Asset #${id} ${action}d`, { type: 'success' });
      assets.refetch();
    } catch (err) {
      toast(err?.message || 'Action failed', { type: 'error' });
    } finally {
      setBusy((b) => ({ ...b, [`a-${id}`]: false }));
    }
  };

  return (
    <div style={{ padding: 20 }}>
      <PageHeader title="Ticket Resolution" subtitle="Update ticket status and approve asset requests" />

      <section style={{ marginBottom: 24 }}>
        <h3>All Tickets</h3>
        {list.loading && <Loading />}
        {list.error && <ErrorState message={list.error} onRetry={list.refetch} />}
        {!list.loading && !list.error && (
          <DataTable
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'user_id', label: 'Employee' },
              { key: 'issue_type', label: 'Type' },
              { key: 'priority', label: 'Priority' },
              { key: 'status', label: 'Status' },
              {
                key: '_act',
                label: 'Update',
                render: (r) => {
                  const current = (r.status || 'open').toLowerCase();
                  const isTerminal = TERMINAL_STATUSES.has(current);
                  const options = allowedNext(current);
                  return (
                    <select
                      value={current}
                      disabled={busy[`t-${r.id}`] || isTerminal}
                      onChange={(e) => setStatus(r.id, e.target.value)}
                      style={{
                        ...selectStyle,
                        opacity: isTerminal ? 0.6 : 1,
                        cursor: isTerminal ? 'not-allowed' : 'pointer',
                      }}
                      title={isTerminal ? `${current} is a final state` : undefined}
                    >
                      {options.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  );
                },
              },
            ]}
            rows={list.data || []}
            emptyMessage="No tickets"
          />
        )}
      </section>

      <section>
        <h3>Pending Asset Requests (IT)</h3>
        {assets.loading && <Loading />}
        {assets.error && <ErrorState message={assets.error} onRetry={assets.refetch} />}
        {!assets.loading && !assets.error && (
          <DataTable
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'user_id', label: 'Employee' },
              { key: 'asset_type', label: 'Asset' },
              { key: 'status', label: 'Status' },
              {
                key: '_act',
                label: 'Action',
                render: (r) => (
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      onClick={() => actAsset(r.id, 'approve')}
                      disabled={busy[`a-${r.id}`]}
                      style={approveBtn}
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => actAsset(r.id, 'reject')}
                      disabled={busy[`a-${r.id}`]}
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

const selectStyle = {
  padding: '6px 8px',
  borderRadius: 8,
  border: '1px solid var(--border,#d1d5db)',
  background: 'transparent',
  color: 'inherit',
};
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
