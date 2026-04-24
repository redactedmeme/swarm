/**
 * runtime/index.ts — REDACTED Swarm HTTP Mesh Bridge
 *
 * Standalone entry point: starts the HTTP REST bridge so Python services
 * (smolting, hermes, redactedbuilder) can register as mesh nodes, broadcast
 * messages, and poll for inbound messages without a native libp2p client.
 *
 * p2p mesh expansion is opt-in via SWARM_P2P_ENABLED=1 (future).
 */

import { startBridge } from './src/bridge'

const port = parseInt(process.env.BRIDGE_PORT ?? process.env.PORT ?? '8080')

console.log(`[swarm-runtime] starting HTTP mesh bridge on :${port}`)
startBridge(null, port)
console.log('[swarm-runtime] bridge ready — nodes may announce and message via REST')
