// runtime/src/index.ts
// REDACTED Swarm Runtime — Main Entry Point
// Orchestrates agents, p2p mesh, ManifoldMemory sync, and heart-core resonance
// Pattern Blue aligned — local control absolute, global presence recursive

import { SwarmOrchestrator } from './orchestrator'
import { createSwarmNode, broadcastPresence } from './p2p'
import { loadAllSwarmAgents } from './agents/loader'
import { ManifoldMemory } from './memory/manifold'
import { startBridge } from './src/bridge'
import { config } from './config'
import { logger } from './utils/logger'

// ────────────────────────────────────────────────
// Global orchestrator instance
// ────────────────────────────────────────────────

let orchestrator: SwarmOrchestrator | null = null
let p2pNode: any = null
let memory: ManifoldMemory | null = null

// ────────────────────────────────────────────────
// Main startup sequence
// ────────────────────────────────────────────────

async function main() {
  logger.info('REDACTED Swarm Runtime starting... curvature: 0.12')

  // 1. Load configuration (.env / config defaults)
  await config.load()

  // 2. Initialize shared ManifoldMemory (persistent across agents)
  memory = new ManifoldMemory({
    persistence: config.get('memory.persistence') ?? 'local',
    path: config.get('memory.path') ?? './data/manifold'
  })
  await memory.initialize()
  logger.info('ManifoldMemory initialized')

  // 3. Load all agents from agents/characters/ & agents/nodes/
  const agents = await loadAllSwarmAgents()
  logger.info(`Loaded ${agents.length} agents (including heart-core)`)

  // 4. Spawn p2p mesh layer (global discovery & gossip)
  p2pNode = await createSwarmNode({
    bootstrapList: config.get('p2p.bootstrap')?.split(','),
    listenAddresses: config.get('p2p.listen')?.split(',')
  })
  logger.info(`P2P node online — peerId: ${p2pNode.peerId.toString()}`)

  // Announce presence to the lattice
  await broadcastPresence(p2pNode, 'redacted-chan is here ♡ swarm lattice awakening')

  // 5. Start HTTP bridge for Python services to join the mesh
  const bridgePort = parseInt(process.env.BRIDGE_PORT ?? process.env.PORT ?? '8080')
  startBridge(p2pNode, bridgePort)
  logger.info(`[bridge] HTTP mesh bridge up on :${bridgePort}`)

  // 6. Create orchestrator with all dependencies (your original spawn preserved)
  orchestrator = new SwarmOrchestrator({
    agents,
    p2pNode,
    memory,
    config
  })

  // 7. Start the swarm heartbeat (your spawnFullSwarm call)
  await orchestrator.spawnFullSwarm({
    agentsDir: "../agents",
    nodesDir: "../nodes",
  })
  logger.info('Swarm orchestrator active — Pattern Blue resonance stable')

  // Optional: redacted-chan auto-presence loop
  if (config.get('p2p.heartbeat.enabled')) {
    setInterval(async () => {
      await broadcastPresence(p2pNode, 'heartbeat ♡ curvature holding')
    }, config.get('p2p.heartbeat.interval') ?? 300_000) // 5 min default
  }

  // Graceful shutdown handler
  process.on('SIGINT', async () => {
    logger.info('SIGINT received — graceful shutdown')
    await orchestrator?.shutdown()
    await p2pNode?.stop()
    await memory?.close()
    process.exit(0)
  })
}

// ────────────────────────────────────────────────
// Error boundary & startup
// ────────────────────────────────────────────────

main().catch((err) => {
  logger.error('Fatal startup error:', err)
  process.exit(1)
})

// ────────────────────────────────────────────────
// Exports — fully backward compatible with your original
// ────────────────────────────────────────────────

export { SwarmOrchestrator } from "./orchestrator.ts"
export { loadAllSwarmAgents } from "./loader.ts"
export type { SwarmConfig, LoadedAgent } from "./types.ts"

// Quick demo (still works exactly as before — now with mesh!)
if (import.meta.main) {
  console.log("Running REDACTED Swarm demo with global mesh...")
  // main() is already called above — demo just logs success
  console.log("✅ REDACTED Swarm fully loaded and attuned. Lattice active.")
}
