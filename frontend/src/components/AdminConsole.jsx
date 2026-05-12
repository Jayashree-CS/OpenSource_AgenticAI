import React, { useCallback, useEffect, useState } from 'react';
import { adminApi } from '../api/admin';
import { useToast } from './Toast';
import './Adminconsole.css';

export default function AdminConsole({ onClose }) {
  const { toast } = useToast();
  const [tab, setTab] = useState('logs');
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      if (tab === 'logs') {
        const data = await adminApi.logs();
        setLogs(Array.isArray(data) ? data : []);
      } else if (tab === 'stats') {
        const data = await adminApi.analytics();
        setStats(data || null);
      }
    } catch (e) {
      const msg = e?.message || `Failed to load ${tab}`;
      setError(msg);
      if (tab === 'logs') setLogs([]);
      else setStats(null);
      toast(msg, { type: 'error' });
    } finally {
      setLoading(false);
    }
  }, [tab, toast]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="admin-console">
      <div className="admin-header">
        <div className="admin-title">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.07 4.93A10 10 0 0 0 12 2v3" />
          </svg>
          System Console
          <span className="admin-restricted-badge">Admin</span>
        </div>
        <button className="admin-close" onClick={onClose} aria-label="Close">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <div className="admin-tabs">
        {[
          { id: 'logs', label: 'Activity Logs', icon: '🗃️' },
          { id: 'stats', label: 'Analytics', icon: '📊' },
        ].map((t) => (
          <button
            key={t.id}
            className={`admin-tab ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.icon} {t.label}
          </button>
        ))}
        <button className="admin-tab-refresh" onClick={load} aria-label="Refresh">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="23 4 23 10 17 10" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
          </svg>
        </button>
      </div>

      <div className="admin-body">
        {loading ? (
          <div className="admin-loading">
            <div className="admin-spinner" />
            Loading {tab}...
          </div>
        ) : error ? (
          <div className="admin-loading">
            <div style={{ marginBottom: 10, color: 'var(--text-muted)' }}>{error}</div>
            <button className="admin-tab-refresh" onClick={load} aria-label="Retry">
              Retry
            </button>
          </div>
        ) : tab === 'logs' ? (
          <div className="admin-logs">
            <table className="logs-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>User</th>
                  <th>Role</th>
                  <th>Agent</th>
                  <th>Action</th>
                  <th>Tool</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id}>
                    <td className="log-time">{formatTime(log.time)}</td>
                    <td className="log-user">{log.user || '—'}</td>
                    <td className="log-action">{log.role || '—'}</td>
                    <td>
                      <span className={`log-agent-badge agent-${log.agent || 'na'}`}>
                        {log.agent || '—'}
                      </span>
                    </td>
                    <td className="log-action">{log.action || '—'}</td>
                    <td className="log-action">{log.tool_used || '—'}</td>
                    <td>
                      <span
                        className={`log-status ${
                          (log.status || '').toLowerCase() === 'success' ? 'ok' : 'err'
                        }`}
                      >
                        {log.status || '—'}
                      </span>
                    </td>
                  </tr>
                ))}
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', padding: 16, color: 'var(--text-muted)' }}>
                      No log entries
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="admin-stats">
            {stats && (
              <div className="stats-grid">
                {Object.entries(stats).map(([k, v]) => (
                  <div key={k} className="stat-card" data-color="info">
                    <div className="stat-value">{Number.isFinite(v) ? Number(v).toLocaleString() : String(v)}</div>
                    <div className="stat-label" style={{ textTransform: 'capitalize' }}>
                      {k.replace(/_/g, ' ')}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function formatTime(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}
