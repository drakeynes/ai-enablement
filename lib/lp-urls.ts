// DC landing-page URL normalization — the TypeScript twin of
// shared/lp_urls.py (KEEP IN LOCKSTEP: the ingestion resolver and the Wistia
// embed scan key dc_landing_pages rows by this normalization; the DC Setup
// admin page must produce identical keys or edits would fork identities).
//
// lowercase host, strip scheme / www. / port / query / fragment / trailing
// slash: 'https://Join.DigitalCollege.ai/training/?x=1#f' →
// 'join.digitalcollege.ai/training'.

export function normalizeLpUrl(url: string): string {
  const withScheme = url.includes('://') ? url : `https://${url}`
  let parsed: URL
  try {
    parsed = new URL(withScheme)
  } catch {
    return url.trim().toLowerCase()
  }
  let host = parsed.hostname.toLowerCase()
  if (host.startsWith('www.')) host = host.slice(4)
  const path = parsed.pathname.replace(/\/+$/, '')
  return `${host}${path}`
}

// The DC landing-page domain(s) — twin of shared/lp_urls.py DC_LANDING_HOSTS.
export const DC_LANDING_HOSTS = ['digitalcollege.ai']

// 'join.digitalcollege.ai/training' → 'join/training'; 'go.digitalcollege.ai'
// → 'go' — twin of shared/lp_urls.py lp_short_label.
export function lpShortLabel(normalizedUrl: string, domains: string[] = DC_LANDING_HOSTS): string {
  const slash = normalizedUrl.indexOf('/')
  let host = slash === -1 ? normalizedUrl : normalizedUrl.slice(0, slash)
  const path = slash === -1 ? '' : normalizedUrl.slice(slash + 1)
  for (const domain of domains) {
    if (host === domain) {
      host = ''
      break
    }
    if (host.endsWith(`.${domain}`)) {
      host = host.slice(0, -(domain.length + 1))
      break
    }
  }
  const parts = [host, path].filter(Boolean)
  return parts.length ? parts.join('/') : normalizedUrl
}

// 'join/training' → 'join-training' — twin of shared/lp_urls.py lp_slugify.
export function lpSlugify(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}
