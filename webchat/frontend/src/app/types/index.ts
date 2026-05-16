export type Role = 'user' | 'assistant'

export interface Attachment {
  type: 'image' | 'file'
  name: string
  data: string
  mimeType?: string
}

export interface Message {
  id: string
  role: Role
  content: string
  timestamp: number
  attachments?: Attachment[]
  isStreaming?: boolean
}

export interface AgentStatus {
  id: string
  name: string
  label: string
  online: boolean
  lastSeen?: string
}

export interface ChanMood {
  mood: string
  emoji: string
  phi: number
  anticipation: string
  lastMessage?: string
}

export interface ChanFact {
  id?: string
  fact: string
  ts?: string
  resonance: number
}

export interface VaultEntry {
  text: string
  category: string
  title?: string
  emotional_tone?: string
  love_resonance?: number
  source?: string
}

export interface AgentHeartbeat {
  id: string
  label: string
  llm: string
  online: boolean
  age_s: number | null
  last_seen: string | null
}

export interface ProxyLogEntry {
  timestamp: string
  provider: string
  model: string
  latency_ms: number
  tokens?: number
  cached?: boolean
}

export interface PrivacyConfig {
  mode: 'anonymous' | 'private' | 'maximum'
  log_level: 'full' | 'minimal' | 'none'
  pii_scrub: boolean
  ephemeral: boolean
}

export type NavItem = {
  id: string
  label: string
  icon: string
  path: string
}
