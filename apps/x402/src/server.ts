import express from 'express';
import http from 'http';
import { Server as SocketIOServer } from 'socket.io';

type CmdRequest = { cmd: string };
type CmdResponse = { ok: boolean; output?: string; error?: string };

const app = express();
const server = http.createServer(app);
const io = new SocketIOServer(server, {
  cors: {
    origin: '*',
  },
});

app.use(express.json());
// Basic in-memory swarm state for the TS service (incremental migration)
type Agent = { id: string; name: string; status: string };
const swarmAgents: Record<string, Agent> = {
  smolting: { id: 'smolting', name: 'smolting', status: 'idle' },
  RedactedBuilder: { id: 'RedactedBuilder', name: 'Builder', status: 'idle' },
  RedactedGovImprover: { id: 'RedactedGovImprover', name: 'GovImprover', status: 'idle' },
  RedactedChan: { id: 'RedactedChan', name: 'redacted-chan', status: 'idle' },
  MandalaSettler: { id: 'MandalaSettler', name: 'MandalaSettler', status: 'idle' }
};
// Simple event log for UI visibility of actions
const swarmEventLog: string[] = [];
function logEvent(evt: string) {
  swarmEventLog.push(evt);
  if (swarmEventLog.length > 200) swarmEventLog.shift();
}

function swarmStatusSummary(): string {
  const total = Object.keys(swarmAgents).length;
  const active = Object.values(swarmAgents).filter(a => a.status === 'active').length;
  return `Swarm: ${active}/${total} active`;
}

app.post('/command', (req, res) => {
  const cmd = req.body?.cmd || '';
  // Very small local dialect for TS service
  let output = '';
  if (!cmd) {
    res.json({ ok: false, output: 'No command provided' } as CmdResponse);
    return;
  }
  const parts = cmd.trim().split(/\s+/);
  const base = parts[0].toLowerCase();
  switch (base) {
    case '/status':
      output = swarmStatusSummary();
      break;
    case '/summon': {
      const agentKey = parts[1];
      if (agentKey && swarmAgents[agentKey]) {
        swarmAgents[agentKey].status = 'active';
        output = `Summoned agent: ${swarmAgents[agentKey].name}`;
      } else {
        output = `Unknown agent: ${parts[1] || ''}`;
      }
      break;
    }
    case '/exit': {
      Object.values(swarmAgents).forEach(a => a.status = 'idle');
      output = 'Swarm session terminated';
      logEvent('exit');
      break;
    }
    case '/observe': {
      const target = parts.slice(1).join(' ') || 'unknown';
      if (target) logEvent(`observe:${target}`);
      output = `Observing: ${target}`;
      break;
    }
    case '/shard': {
      const concept = parts.slice(1).join(' ') || 'default';
      logEvent(`shard:${concept}`);
      output = `Shard invoked: ${concept}`;
      break;
    }
    case '/pay': {
      const amount = parts[1] || '0';
      const recipient = parts.slice(2).join(' ') || 'unknown';
      logEvent(`pay:${amount}->${recipient}`);
      output = `Pay: ${amount} to ${recipient}`;
      break;
    }
    default:
      output = `Unknown command: ${cmd}`;
  }
  res.json({ ok: true, output } as CmdResponse);
});
app.get('/health', (req, res) => {
  res.json({ status: 'OK', timestamp: new Date().toISOString(), service: 'swarm-core-ts' });
});

// Lightweight state export for debugging/UI
app.get('/state', (req, res) => {
  res.json({ agents: swarmAgents, events: swarmEventLog, curvature: 13, timestamp: new Date().toISOString() });
});

io.on('connection', (socket) => {
  console.log('TS swarm-core connected:', socket.id);
  socket.emit('output', { data: 'TS swarm-core ready' });

  socket.on('command', (payload) => {
    const cmd = payload?.cmd ?? '';
    socket.emit('output', { data: `> ${cmd}` });
  });
});

const PORT = process.env.PORT ? Number(process.env.PORT) : 3001;
server.listen(PORT, () => {
  console.log(`TS swarm-core listening on http://localhost:${PORT}`);
});
