'use client'

import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'

// Terminal page for authenticated users with NO area at all (since the
// 2026-08-21 fulfillment restore, fulfillment-area users go to /clients
// instead). The DC-era guard (middleware.ts) funnels unknown paths to
// /sales-dashboard/dc-ads, whose layout bounces area-less users to
// homePathForAreas() — which sends them here instead of back into the loop.
// Lives outside (authenticated) so it renders without the top nav.

export default function NoAccessPage() {
  const router = useRouter()
  const supabase = createClient()

  async function onLogout() {
    await supabase.auth.signOut()
    router.push('/login')
    router.refresh()
  }

  return (
    <div
      data-theme="gregory-editorial"
      className="min-h-screen flex items-center justify-center"
      style={{ background: 'var(--color-geg-bg)', color: 'var(--color-geg-text)' }}
    >
      <div
        style={{
          maxWidth: 420,
          padding: '28px 32px',
          border: '1px solid var(--color-geg-border)',
          borderRadius: 10,
          background: 'var(--color-geg-bg-elev)',
        }}
      >
        <div
          className="geg-mono"
          style={{ fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--color-geg-text-3)', marginBottom: 10 }}
        >
          No access
        </div>
        <div className="geg-serif" style={{ fontSize: 20, lineHeight: 1.3, marginBottom: 10 }}>
          Your account doesn&apos;t have a dashboard area yet.
        </div>
        <p style={{ fontSize: 13, lineHeight: 1.6, color: 'var(--color-geg-text-2)', marginBottom: 18 }}>
          You&apos;re signed in, but no area (sales or fulfillment) is assigned to
          your account. If you think you should have access, contact Drake or Nabeel.
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={onLogout}
          style={{ background: 'transparent', color: 'var(--color-geg-text)', borderColor: 'var(--color-geg-border-strong)' }}
        >
          Logout
        </Button>
      </div>
    </div>
  )
}
