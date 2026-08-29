import type { ChanMood, ChanFact, ProxyLogEntry, PrivacyConfig, VaultEntry, AgentHeartbeat, SwarmMessage, SwarmPendingEntry } from '@/app/types'

const BASE = ''

function getToken() {
  return localStorage.getItem('rc_token') ?? ''
}

function authHeaders(): HeadersInit {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${getToken()}`,
  }
}

// Auto-logout on 401 — expired or invalid token
function handleResponse(res: Response): Response {
  if (res.status === 401) {
    localStorage.removeItem('rc_token')
    localStorage.removeItem('rc_session')
    localStorage.removeItem('rc-auth')
    window.location.replace('/login')
  }
  return res
}

export async function apiLogin(password: string): Promise<{ token: string; session_id: string }> {
  const res = await fetch(`${BASE}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'Login failed')
  }
  return res.json()
}

export async function apiChat(payload: {
  message: string
  session_id: string
  history: Array<{ role: string; content: string }>
  image_data?: string
}): Promise<{ response: string; session_id: string }> {
  const res = handleResponse(await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(95_000),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? 'Chat failed')
  }
  return res.json()
}

export async function apiUpload(file: File): Promise<{ type: 'image' | 'text'; data: string; name: string }> {
  const form = new FormData()
  form.append('file', file)
  const res = handleResponse(await fetch(`${BASE}/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
    body: form,
  }))
  if (!res.ok) throw new Error('Upload failed')
  return res.json()
}

export async function apiGetMood(): Promise<ChanMood> {
  const res = handleResponse(await fetch(`${BASE}/chan/mood`, { headers: authHeaders() }))
  if (!res.ok) throw new Error('Failed to fetch mood')
  return res.json()
}

export async function apiGetFacts(): Promise<{ facts: ChanFact[] }> {
  const res = handleResponse(await fetch(`${BASE}/chan/facts`, { headers: authHeaders() }))
  if (!res.ok) throw new Error('Failed to fetch facts')
  return res.json()
}

export async function apiGetAnticipation(): Promise<{ anticipation: string }> {
  const res = handleResponse(await fetch(`${BASE}/chan/anticipation`, { headers: authHeaders() }))
  if (!res.ok) throw new Error('Failed to fetch anticipation')
  return res.json()
}

export async function apiGetHeatmap(): Promise<{ heatmap: Record<string, number> }> {
  const res = handleResponse(await fetch(`${BASE}/chan/heatmap`, { headers: authHeaders() }))
  if (!res.ok) throw new Error('Failed to fetch heatmap')
  return res.json()
}

export async function apiGetProxyLogs(): Promise<{ logs: ProxyLogEntry[]; entries?: ProxyLogEntry[] }> {
  const res = handleResponse(await fetch(`${BASE}/proxy-logs?n=500`, { headers: authHeaders() }))
  if (!res.ok) throw new Error('Failed to fetch proxy logs')
  return res.json()
}

export async function apiGetHeartbeats(): Promise<{ agents: AgentHeartbeat[] }> {
  const res = handleResponse(await fetch(`${BASE}/chan/heartbeats`, { headers: authHeaders() }))
  if (!res.ok) throw new Error('Failed to fetch heartbeats')
  return res.json()
}

export async function apiGetVault(n = 30): Promise<{ entries: VaultEntry[] }> {
  const res = handleResponse(await fetch(`${BASE}/chan/vault?n=${n}`, { headers: authHeaders() }))
  if (!res.ok) throw new Error('Failed to fetch vault')
  return res.json()
}

export async function apiGetSwarmActivity(n = 60): Promise<{ messages: SwarmMessage[] }> {
  const res = handleResponse(await fetch(`${BASE}/api/swarm/activity?n=${n}`, { headers: authHeaders() }))
  if (!res.ok) throw new Error('Failed to fetch swarm activity')
  return res.json()
}

export async function apiGetSwarmPending(): Promise<{ pending: Record<string, SwarmPendingEntry> }> {
  const res = handleResponse(await fetch(`${BASE}/api/swarm/pending`, { headers: authHeaders() }))
  if (!res.ok) throw new Error('Failed to fetch swarm pending')
  return res.json()
}

function fromProxyConfig(raw: Record<string, unknown>): PrivacyConfig {
  return {
    mode: String(raw.privacy_mode ?? raw.mode ?? 'anonymous') as PrivacyConfig['mode'],
    log_level: String(raw.log_level ?? 'full') as PrivacyConfig['log_level'],
    pii_scrub: Boolean(raw.privacy_scrub ?? raw.pii_scrub ?? false),
    ephemeral: Boolean(raw.ephemeral_mode ?? raw.ephemeral ?? false),
  }
}

function toProxyConfig(config: Partial<PrivacyConfig>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  if (config.mode !== undefined) out.privacy_mode = config.mode
  if (config.log_level !== undefined) out.log_level = config.log_level
  if (config.pii_scrub !== undefined) out.privacy_scrub = config.pii_scrub
  if (config.ephemeral !== undefined) out.ephemeral_mode = config.ephemeral
  return out
}

export async function apiGetPrivacyConfig(): Promise<PrivacyConfig> {
  const res = handleResponse(await fetch(`${BASE}/proxy-config`, { headers: authHeaders() }))
  if (!res.ok) throw new Error('Failed to fetch privacy config')
  const raw = await res.json() as Record<string, unknown>
  return fromProxyConfig(raw)
}

export async function apiSetPrivacyConfig(config: Partial<PrivacyConfig>): Promise<void> {
  const res = handleResponse(await fetch(`${BASE}/proxy-config`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(toProxyConfig(config)),
  }))
  if (!res.ok) throw new Error('Failed to update privacy config')
}
