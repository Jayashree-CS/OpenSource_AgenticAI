import React, { useMemo, useState } from 'react';
import { adminApi } from '../api/admin';
import useApi from '../hooks/useApi';
import { DataTable, ErrorState, Loading, PageHeader } from '../components/PageState';

export default function SystemLogs() {
  const logs = useApi(() => adminApi.logs(), []);
  const [filter, setFilter] = useState('');

  const rows = useMemo(() => {
    const all = logs.data || [];
    if (!filter.trim()) return all;
    const q = filter.toLowerCase();
    return all.filter((r) =>
      [r.user, r.role, r.action, r.agent, r.tool_used, r.status]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q))
    );
  }, [logs.data, filter]);

  return (
    <div style={{ padding: 20 }}>
      <PageHeader
        title="System Logs"
        subtitle="Audit of agent and user activity"
        actions={
          <input
            placeholder="Filter logs…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{
              padding: '8px 10px',
              borderRadius: 8,
              border: '1px solid var(--border,#d1d5db)',
              background: 'transparent',
              color: 'inherit',
              minWidth: 220,
            }}
          />
        }
      />

      {logs.loading && <Loading />}
      {logs.error && <ErrorState message={logs.error} onRetry={logs.refetch} />}
      {!logs.loading && !logs.error && (
        <DataTable
          columns={[
            { key: 'time', label: 'Time' },
            { key: 'user', label: 'User' },
            { key: 'role', label: 'Role' },
            { key: 'agent', label: 'Agent' },
            { key: 'action', label: 'Action' },
            { key: 'tool_used', label: 'Tool' },
            { key: 'status', label: 'Status' },
          ]}
          rows={rows}
          emptyMessage="No log entries"
        />
      )}
    </div>
  );
}
