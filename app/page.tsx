import { redirect } from 'next/navigation'

// DC-era (2026-08-15): the dashboard is DC-only — root lands on DC Ads.
// (Was '/clients' when the fulfillment side was the front door.)
export default function Root() {
  redirect('/sales-dashboard/dc-ads')
}
