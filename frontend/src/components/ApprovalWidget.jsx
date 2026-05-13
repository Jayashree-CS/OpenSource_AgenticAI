import React, { useCallback, useEffect, useState } from 'react';
import { managerAPI } from '../api/manager';
import { itAPI } from '../api/it';
import { useToast } from './Toast';
import { formatAssetStatus } from '../utils/assetStatus';
import './Approvalwidget.css';

export default function ApprovalWidget({ role = 'manager' }) {
  const { toast } = useToast();
  const isIT = role === 'it_team';
  // Admin is superior to manager + IT, so they see both queues at once.
  const isAdmin = role === 'admin';
  const [leaves, setLeaves] = useState([]);
  const [assets, setAssets] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      if (isAdmin) {
        // Whole-company view: pending leaves + every asset still in
        // flight (manager-stage OR IT-stage) + every open IT ticket.
        const [l, mgrAssets, itAssets, t] = await Promise.all([
          managerAPI.pendingLeaves(),
          managerAPI.pendingAssets(),
          itAPI.pendingAssets(),
          itAPI.openTickets(),
        ]);
        setLeaves(Array.isArray(l) ? l : []);
        // Dedupe by id — manager-stage and IT-stage rows are normally
        // disjoint, but be defensive in case of overlap.
        const merged = new Map();
        for (const row of [...(mgrAssets || []), ...(itAssets || [])]) {
          if (row && row.id != null) merged.set(row.id, row);
        }
        setAssets(Array.from(merged.values()));
        setTickets(Array.isArray(t) ? t : []);
      } else if (isIT) {
        const [t, a] = await Promise.all([
          itAPI.openTickets(),
          itAPI.pendingAssets(),
        ]);
        setTickets(Array.isArray(t) ? t : []);
        setAssets(Array.isArray(a) ? a : []);
        setLeaves([]);
      } else {
        const [l, a] = await Promise.all([
          managerAPI.pendingLeaves(),
          managerAPI.pendingAssets(),
        ]);
        setLeaves(Array.isArray(l) ? l : []);
        setAssets(Array.isArray(a) ? a : []);
        setTickets([]);
      }
    } catch (e) {
      setError(e?.message || 'Failed to load pending approvals');
    } finally {
      setLoading(false);
    }
  }, [isIT, isAdmin]);

  useEffect(() => {
    load();
  }, [load]);

  const handleLeave = async (id, action) => {
    setBusy((b) => ({ ...b, [`l-${id}`]: true }));
    try {
      await managerAPI.actionLeave(id, action);
      setLeaves((prev) => prev.filter((r) => r.id !== id));
      toast(`Leave ${action}d`, { type: 'success' });
    } catch (e) {
      toast(e?.message || 'Action failed', { type: 'error' });
    } finally {
      setBusy((b) => ({ ...b, [`l-${id}`]: false }));
    }
  };

  const handleAsset = async (id, action, row) => {
    setBusy((b) => ({ ...b, [`a-${id}`]: true }));
    try {
      // For admin: pick the right endpoint based on the row's current
      // workflow stage. Manager-stage rows still need a manager-route
      // decision; IT-stage rows must go through the IT route. For pure
      // IT users the IT route is always correct; for pure managers the
      // manager route is always correct.
      const isItStage =
        row &&
        String(row.manager_status || '').toLowerCase() === 'approved' &&
        String(row.it_status || '').toLowerCase() === 'pending';
      const useItRoute = isIT || (isAdmin && isItStage);
      if (useItRoute) {
        await itAPI.actionAsset(id, action);
      } else {
        await managerAPI.actionAsset(id, action);
      }
      setAssets((prev) => prev.filter((r) => r.id !== id));
      toast(`Asset ${action}d`, { type: 'success' });
    } catch (e) {
      toast(e?.message || 'Action failed', { type: 'error' });
    } finally {
      setBusy((b) => ({ ...b, [`a-${id}`]: false }));
    }
  };

  const handleTicket = async (id, status, label) => {
    setBusy((b) => ({ ...b, [`t-${id}`]: true }));
    try {
      await itAPI.updateTicket(id, status);
      setTickets((prev) => prev.filter((r) => r.id !== id));
      toast(`Ticket ${label}`, { type: 'success' });
    } catch (e) {
      toast(e?.message || 'Action failed', { type: 'error' });
    } finally {
      setBusy((b) => ({ ...b, [`t-${id}`]: false }));
    }
  };

  const total = leaves.length + assets.length + tickets.length;
  if (!loading && !error && total === 0) return null;

  return (
    <div className="approval-widget">
      <div className="approval-widget-header">
        <div className="approval-widget-title">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
          Pending Approvals
          {total > 0 && <span className="approval-badge">{total}</span>}
        </div>
        <button className="approval-refresh" onClick={load} aria-label="Refresh">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="23 4 23 10 17 10" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
          </svg>
        </button>
      </div>

      {loading ? (
        <div className="approval-loading">
          <div className="approval-spinner" />
          Loading requests...
        </div>
      ) : error ? (
        <div className="approval-loading">
          <div style={{ marginBottom: 10, color: 'var(--text-muted)' }}>{error}</div>
          <button className="approval-refresh" onClick={load} aria-label="Retry">
            Retry
          </button>
        </div>
      ) : (
        <div className="approval-list">
          {tickets.map((req) => (
            <div key={`t-${req.id}`} className="approval-item">
              <div className="approval-item-left">
                <span className="approval-type-badge ticket">Ticket</span>
                <div className="approval-item-info">
                  <span className="approval-item-name">{req.user_id || `Ticket #${req.id}`}</span>
                  <span className="approval-item-detail">
                    {req.issue_type || '—'} · {req.priority || 'medium'} · {req.status}
                  </span>
                </div>
              </div>
              <div className="approval-item-actions">
                <button
                  className="approval-btn approve"
                  title={req.status === 'open' ? 'Start work' : 'Resolve'}
                  onClick={() =>
                    handleTicket(
                      req.id,
                      req.status === 'open' ? 'in_progress' : 'resolved',
                      req.status === 'open' ? 'started' : 'resolved'
                    )
                  }
                  disabled={busy[`t-${req.id}`]}
                >
                  ✓
                </button>
                <button
                  className="approval-btn reject"
                  title="Reject"
                  onClick={() => handleTicket(req.id, 'rejected', 'rejected')}
                  disabled={busy[`t-${req.id}`]}
                >
                  ✗
                </button>
              </div>
            </div>
          ))}

          {leaves.map((req) => (
            <div key={`l-${req.id}`} className="approval-item">
              <div className="approval-item-left">
                <span className="approval-type-badge leave">Leave</span>
                <div className="approval-item-info">
                  <span className="approval-item-name">
                    Employee #{req.employee_id ?? '—'}
                  </span>
                  <span className="approval-item-detail">
                    {req.leave_type || 'leave'} · {req.start_date} → {req.end_date}
                  </span>
                </div>
              </div>
              <div className="approval-item-actions">
                <button
                  className="approval-btn approve"
                  onClick={() => handleLeave(req.id, 'approve')}
                  disabled={busy[`l-${req.id}`]}
                >
                  ✓
                </button>
                <button
                  className="approval-btn reject"
                  onClick={() => handleLeave(req.id, 'reject')}
                  disabled={busy[`l-${req.id}`]}
                >
                  ✗
                </button>
              </div>
            </div>
          ))}

          {assets.map((req) => (
            <div key={`a-${req.id}`} className="approval-item">
              <div className="approval-item-left">
                <span className="approval-type-badge asset">Asset</span>
                <div className="approval-item-info">
                  <span className="approval-item-name">{req.user_id || '—'}</span>
                  <span className="approval-item-detail">
                    {req.asset_type} · {formatAssetStatus(req)}
                  </span>
                </div>
              </div>
              <div className="approval-item-actions">
                <button
                  className="approval-btn approve"
                  onClick={() => handleAsset(req.id, 'approve', req)}
                  disabled={busy[`a-${req.id}`]}
                >
                  ✓
                </button>
                <button
                  className="approval-btn reject"
                  onClick={() => handleAsset(req.id, 'reject', req)}
                  disabled={busy[`a-${req.id}`]}
                >
                  ✗
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
