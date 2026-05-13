// Single source of truth for the human-readable status of an asset request.
//
// The backend AssetRequest row has FOUR independent status columns
// (manager_status, it_status, inventory_status, final_status). Different
// pages used to render the row's non-existent ``status`` field directly
// and ended up showing an em-dash. This helper collapses the four-stage
// state machine into one display label, matching the rules requested:
//
//   • manager rejects        → "Rejected"
//   • manager approves       → "In progress (with IT)"
//   • IT / admin rejects     → "Rejected"
//   • IT / admin approves    → "Approved"
//   • inventory out of stock → "Waiting for stock"
//   • nothing decided yet    → "Pending manager approval"

const norm = (v) => String(v ?? '').trim().toLowerCase();

export function formatAssetStatus(row) {
  if (!row || typeof row !== 'object') return '—';

  const m = norm(row.manager_status);
  const it = norm(row.it_status);
  const inv = norm(row.inventory_status);
  const finalS = norm(row.final_status);

  if (m === 'rejected' || finalS === 'rejected' || it === 'rejected') {
    return 'Rejected';
  }
  if (finalS === 'fulfilled' || it === 'approved' || finalS === 'approved') {
    return 'Approved';
  }
  if (inv === 'unavailable' || finalS === 'waiting_for_stock') {
    return 'Waiting for stock';
  }
  if (m === 'approved' && (it === 'pending' || finalS === 'pending_it_approval')) {
    return 'In progress (with IT)';
  }
  if (m === 'pending') {
    return 'Pending manager approval';
  }

  // Last resort — surface whatever the backend gave us instead of a dash
  // so we never silently hide an unknown state.
  return row.final_status || row.it_status || row.manager_status || '—';
}

export function assetStatusTone(row) {
  const label = formatAssetStatus(row);
  switch (label) {
    case 'Rejected':
      return 'danger';
    case 'Approved':
      return 'success';
    case 'In progress (with IT)':
      return 'progress';
    case 'Waiting for stock':
      return 'warning';
    case 'Pending manager approval':
      return 'pending';
    default:
      return 'muted';
  }
}

export default formatAssetStatus;
