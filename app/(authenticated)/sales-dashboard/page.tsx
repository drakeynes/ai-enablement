import { redirect } from 'next/navigation'

// /sales-dashboard root → DC Ads. DC-era (2026-08-15): the dashboard is
// DC-only, so the segment root lands on its one data page. (Was
// '/sales-dashboard/funnel' when the full sales dashboard was live.)

export default function SalesDashboardRootRedirect() {
  redirect('/sales-dashboard/dc-ads')
}
