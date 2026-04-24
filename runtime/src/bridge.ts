/**
 * runtime/src/bridge.ts
 * HTTP REST bridge — lets Python services (smolting, hermes, etc.) join the
 * swarm mesh without needing a libp2p Python client.
 *
 * Endpoints:
 *   POST /announce          — register a node (role + capabilities)
 *   GET  /peers             — list active nodes
 *   POST /broadcast         — send a message to all nodes
 *   POST /message/:nodeId   — send a message to a specific node
 *   GET  /messages/:nodeId  — poll for messages addressed to this node
 *   GET  /health            — liveness check
 */

import { z } from 'zod'

// p2p type shim — bridge works standalone (p2pNode may be null)
type Libp2p = { peerId: { toString(): string } }

function _log(msg: string): void { console.log(msg) }
const logger = { info: _log, debug: _log, error: _log, warning: _log }

// ─── Schemas ─────────────────────────────────────────────────────────────────

const AnnounceSchema = z.object({
  nodeId:       z.string().min(1),
  role:         z.string().min(1),
  capabilities: z.array(z.string()).default([]),
  metadata:     z.record(z.unknown()).optional(),
})

const BroadcastSchema = z.object({
  from:    z.string().min(1),
  type:    z.string().min(1),
  payload: z.unknown(),
})

const DirectMessageSchema = z.object({
  from:    z.string().min(1),
  type:    z.string().min(1),
  payload: z.unknown(),
})

// ─── In-memory store ─────────────────────────────────────────────────────────

interface NodeRecord {
  nodeId:       string
  role:         string
  capabilities: string[]
  metadata?:    Record<string, unknown>
  lastSeen:     number
}

interface PendingMessage {
  from:      string
  type:      string
  payload:   unknown
  timestamp: number
}

const _nodes  = new Map<string, NodeRecord>()
const _inbox  = new Map<string, PendingMessage[]>()
const _NODE_TTL_MS = 5 * 60 * 1000  // evict after 5 min silence

function _evictStale(): void {
  const cutoff = Date.now() - _NODE_TTL_MS
  for (const [id, node] of _nodes.entries()) {
    if (node.lastSeen < cutoff) {
      _nodes.delete(id)
      logger.info(`[bridge] evicted stale node: ${id} (${node.role})`)
    }
  }
}

function _activeNodes(): NodeRecord[] {
  _evictStale()
  return Array.from(_nodes.values())
}

// ─── Request helpers ─────────────────────────────────────────────────────────

async function parseBody<T>(req: Request, schema: z.ZodSchema<T>): Promise<T | null> {
  try {
    const raw = await req.json()
    return schema.parse(raw)
  } catch {
    return null
  }
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// ─── Route handlers ──────────────────────────────────────────────────────────

function handleHealth(): Response {
  return json({ ok: true, nodes: _activeNodes().length, ts: Date.now() })
}

function handlePeers(): Response {
  return json({ peers: _activeNodes() })
}

async function handleAnnounce(req: Request): Promise<Response> {
  const body = await parseBody(req, AnnounceSchema)
  if (!body) return json({ error: 'invalid body' }, 400)

  const record: NodeRecord = {
    nodeId:       body.nodeId,
    role:         body.role,
    capabilities: body.capabilities,
    metadata:     body.metadata,
    lastSeen:     Date.now(),
  }
  _nodes.set(body.nodeId, record)
  if (!_inbox.has(body.nodeId)) _inbox.set(body.nodeId, [])

  logger.info(`[bridge] node announced: ${body.nodeId} (${body.role})`)
  return json({ ok: true, nodeId: body.nodeId })
}

async function handleBroadcast(req: Request, p2pNode: Libp2p | null): Promise<Response> {
  const body = await parseBody(req, BroadcastSchema)
  if (!body) return json({ error: 'invalid body' }, 400)

  const msg: PendingMessage = { from: body.from, type: body.type, payload: body.payload, timestamp: Date.now() }

  // Deliver to all registered HTTP nodes (except sender)
  let delivered = 0
  for (const [nodeId, msgs] of _inbox.entries()) {
    if (nodeId !== body.from) {
      msgs.push(msg)
      delivered++
    }
  }

  return json({ ok: true, delivered })
}

async function handleDirectMessage(req: Request, nodeId: string): Promise<Response> {
  const body = await parseBody(req, DirectMessageSchema)
  if (!body) return json({ error: 'invalid body' }, 400)

  const inbox = _inbox.get(nodeId)
  if (!inbox) return json({ error: 'node not found' }, 404)

  inbox.push({ from: body.from, type: body.type, payload: body.payload, timestamp: Date.now() })
  return json({ ok: true })
}

function handlePollMessages(nodeId: string): Response {
  // Refresh lastSeen on poll (acts as heartbeat)
  const node = _nodes.get(nodeId)
  if (node) node.lastSeen = Date.now()

  const messages = _inbox.get(nodeId) ?? []
  _inbox.set(nodeId, [])  // clear after delivery
  return json({ messages })
}

// ─── Server factory ───────────────────────────────────────────────────────────

export function startBridge(p2pNode: Libp2p | null, port: number): void {
  const server = Bun.serve({
    port,
    async fetch(req: Request): Promise<Response> {
      const url  = new URL(req.url)
      const path = url.pathname
      const method = req.method.toUpperCase()

      if (method === 'GET'  && path === '/health')           return handleHealth()
      if (method === 'GET'  && path === '/peers')            return handlePeers()
      if (method === 'POST' && path === '/announce')         return handleAnnounce(req)
      if (method === 'POST' && path === '/broadcast')        return handleBroadcast(req, p2pNode)

      const dmMatch = path.match(/^\/message\/(.+)$/)
      if (dmMatch && method === 'POST') return handleDirectMessage(req, dmMatch[1])

      const pollMatch = path.match(/^\/messages\/(.+)$/)
      if (pollMatch && method === 'GET') return handlePollMessages(pollMatch[1])

      return json({ error: 'not found' }, 404)
    },
    error(err: Error): Response {
      logger.error(`[bridge] unhandled error: ${err}`)
      return json({ error: 'internal server error' }, 500)
    },
  })

  logger.info(`[bridge] HTTP bridge listening on :${port}`)
}
