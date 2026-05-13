import React from 'react';
import { managerAPI } from '../api/manager';
import useApi from '../hooks/useApi';
import { DataTable, ErrorState, Loading, PageHeader } from '../components/PageState';
import { formatAssetStatus } from '../utils/assetStatus';

export default function ApprovalHistory() {
  const overview = useApi(() => managerAPI.teamOverview(), []);

  return (
    <div style={{ padding: 20 }}>
      <PageHeader title="Approval History" subtitle="All decisions across your team" />

      {overview.loading && <Loading />}
      {overview.error && <ErrorState message={overview.error} onRetry={overview.refetch} />}

      {!overview.loading && !overview.error && (
        <>
          <h3>Team Leaves</h3>
          <DataTable
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'employee_id', label: 'Employee' },
              { key: 'leave_type', label: 'Type' },
              { key: 'start_date', label: 'From' },
              { key: 'end_date', label: 'To' },
              { key: 'status', label: 'Status' },
            ]}
            rows={overview.data?.leaves || []}
            emptyMessage="No leave records"
          />

          <h3 style={{ marginTop: 24 }}>Team Tickets</h3>
          <DataTable
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'user_id', label: 'Employee' },
              { key: 'issue_type', label: 'Type' },
              { key: 'priority', label: 'Priority' },
              { key: 'status', label: 'Status' },
            ]}
            rows={overview.data?.tickets || []}
            emptyMessage="No tickets"
          />

          <h3 style={{ marginTop: 24 }}>Team Asset Requests</h3>
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
            ]}
            rows={overview.data?.assets || []}
            emptyMessage="No asset requests"
          />
        </>
      )}
    </div>
  );
}
