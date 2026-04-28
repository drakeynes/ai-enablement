import { createClient } from '@/lib/supabase/server'
import { TopNav } from '@/components/top-nav'

export default async function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  // Middleware already redirects unauthenticated users to /login, but if the
  // session expires between the middleware check and this render, fall back
  // to a sensible empty string rather than crashing.
  const userEmail = user?.email ?? ''

  return (
    <div className="min-h-screen">
      <TopNav userEmail={userEmail} />
      <main>{children}</main>
    </div>
  )
}
