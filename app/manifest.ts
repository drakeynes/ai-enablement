import type { MetadataRoute } from 'next'

// PWA manifest (boss batch 2026-08-15): "Add to Home Screen" installs the
// dashboard as a standalone app opening straight on DC Ads — the DC-era
// front door (middleware.ts). Icons generated under public/icons/; the
// maskable variant keeps the mark inside Android's safe zone. Colors =
// --color-geg-bg so the splash/status chrome matches the page.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'DC Ads — The Engine',
    short_name: 'DC Ads',
    description: 'Digital College ads funnel — spend, opt-ins, speed to lead, closes.',
    start_url: '/sales-dashboard/dc-ads',
    display: 'standalone',
    background_color: '#0b0a09',
    theme_color: '#0b0a09',
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
      { src: '/icons/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
  }
}
