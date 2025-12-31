# X402 API Gateway

A modern Express-based API Gateway with dynamic routing, content negotiation, and upstream proxying. Powered by Bun runtime and managed by PM2 process manager.

## Features

- ⚡ **Bun Runtime** - Fast JavaScript runtime with built-in bundler, transpiler, and package manager
- 🚀 **Express Framework** - Minimal and flexible Node.js web application framework
- 🔄 **PM2 Process Manager** - Advanced production process manager with load balancing
- 🎯 **Dynamic Routing** - Data-driven routing based on agent/endpoint configuration
- 🔀 **Content Negotiation** - Serves HTML product pages or JSON data based on Accept headers
- 🔗 **Upstream Proxy** - Transparent proxying to upstream services
- 🎨 **Beautiful UI** - Modern, responsive HTML documentation pages
- 💳 **Web3 Wallet Support** - Phantom wallet integration for x402 payments on Solana
- 🔐 **Payment Verification** - On-chain verification of Solana transactions
- 🔒 **Security** - Helmet.js for security headers
- 🌐 **CORS** - Cross-Origin Resource Sharing enabled
- 📝 **Logging** - Morgan HTTP request logger
- ♻️ **Hot Reload** - Development mode with auto-restart on file changes
- 🛡️ **Error Handling** - Centralized error handling middleware

## Prerequisites

Before you begin, ensure you have installed:

- [Bun](https://bun.sh) (v1.0.0 or higher)
- [PM2](https://pm2.keymetrics.io/) (v5.0.0 or higher)

### Installing Bun

```bash
curl -fsSL https://bun.sh/install | bash
```

### Installing PM2

```bash
bun install -g pm2
```

Or using npm:

```bash
npm install -g pm2
```

## Installation

1. Clone or navigate to the project directory:

```bash
cd /root/x402
```

2. Install dependencies:

```bash
bun install
```

3. Configure environment variables (optional):

```bash
cp .env.example .env
```

Edit `.env` to customize your settings.

## Usage

### Development Mode

Run the server with hot reload:

```bash
bun run dev
```

### Production Mode with PM2

Start the application with PM2:

```bash
bun run pm2:start
```

Or directly:

```bash
pm2 start ecosystem.config.cjs
```

### PM2 Commands

The following npm scripts are available for PM2 management:

```bash
# Start the application
bun run pm2:start

# Stop the application
bun run pm2:stop

# Restart the application
bun run pm2:restart

# Delete from PM2
bun run pm2:delete

# View logs
bun run pm2:logs

# Monitor processes
bun run pm2:monit

# Check status
bun run pm2:status
```

### Direct PM2 Commands

```bash
# Start with environment
pm2 start ecosystem.config.cjs --env production

# View logs
pm2 logs express-bun-server

# Monitor CPU/Memory
pm2 monit

# List all processes
pm2 list

# Stop all processes
pm2 stop all

# Restart all processes
pm2 restart all

# Delete all processes
pm2 delete all

# Save PM2 process list (persist across reboots)
pm2 save

# Startup script (auto-start on system boot)
pm2 startup
```

## Architecture

### Agent-Based Routing

The gateway uses a data-driven architecture where **agents** expose multiple **endpoints**. Each endpoint can:
- Serve HTML product description pages (for browsers/documentation)
- Proxy JSON data from upstream services (for API clients)

### Content Negotiation

The server uses HTTP `Accept` headers to determine response format:
- `Accept: text/html` → Beautiful HTML product page
- `Accept: application/json` → Proxied JSON from upstream

## API Endpoints

### System Endpoints

#### Health Check
```bash
GET /health
```
Returns server health status, uptime, runtime information, and agent/endpoint counts.

#### Homepage
```bash
GET /
```
Returns gateway information. HTML view shows hero page, JSON shows system info.

#### List All Agents
```bash
GET /agents
```
Returns all available agents. HTML view shows agent grid, JSON shows agent data.

#### Get Agent Details
```bash
GET /agents/{agentId}
```
Returns specific agent and its endpoints. HTML view shows endpoint cards, JSON shows structured data.

### Dynamic Agent Endpoints

All endpoints defined in `agents.js` are automatically routed:

#### Weather Agent Examples

**Current Weather (HTML Documentation)**
```bash
curl -H "Accept: text/html" http://localhost:3000/weather/current
```

**Current Weather (JSON Data)**
```bash
curl -H "Accept: application/json" http://localhost:3000/weather/current
```

**Weather Forecast**
```bash
curl -H "Accept: application/json" http://localhost:3000/weather/forecast
```

#### Data Analytics Agent Examples

**Data Analysis**
```bash
curl -H "Accept: application/json" http://localhost:3000/data/analyze
```

**Data Transformation (POST)**
```bash
curl -X POST http://localhost:3000/data/transform \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"format":"json","data":{}}'
```

#### AI Agent Examples

**Text Summarization**
```bash
curl -X POST http://localhost:3000/ai/summarize \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"text":"Your text here","length":"medium"}'
```

**Sentiment Analysis**
```bash
curl -X POST http://localhost:3000/ai/sentiment \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"text":"I love this product!"}'
```

## Testing Endpoints

### Browser Testing

Simply visit any endpoint in your browser to see the HTML documentation:
- http://localhost:3000/
- http://localhost:3000/agents
- http://localhost:3000/weather/current
- http://localhost:3000/data/analyze

### API Testing

Use curl with JSON accept header:

```bash
# Health check
curl -H "Accept: application/json" http://localhost:3000/health

# List agents
curl -H "Accept: application/json" http://localhost:3000/agents

# Get specific agent
curl -H "Accept: application/json" http://localhost:3000/agents/weather-agent

# Call endpoint (proxied to upstream)
curl -H "Accept: application/json" http://localhost:3000/weather/current
```

## Configuration

### Environment Variables

Edit `.env` file to configure:

- `NODE_ENV` - Environment mode (development/production)
- `PORT` - Server port (default: 3000)
- `HOST` - Server host (default: 0.0.0.0)
- `PUBLIC_URL` - Public URL for API (used in HTML docs and examples)
  - Development: `http://localhost:3000`
  - Production: `https://api.yourdomain.com`
  - Default: `http://{HOST}:{PORT}`
  - Note: Trailing slashes are automatically stripped for clean URLs

### PM2 Configuration

Edit `ecosystem.config.cjs` to customize:

- `instances` - Number of instances to run
- `max_memory_restart` - Auto-restart if memory exceeds limit
- `exec_mode` - Execution mode (cluster/fork)
- `watch` - Enable file watching
- `cron_restart` - Schedule automatic restarts
- `env` - Environment variables for different modes

## Adding New Agents and Endpoints

### Agent with Base URL (Recommended)

Use a `baseUrl` for agents with multiple endpoints sharing the same API base:

```javascript
{
  id: 'my-agent',
  name: 'My Custom Agent',
  description: 'Description of what this agent does',
  icon: '🎯',
  baseUrl: 'https://api.example.com/v1',  // Base URL for all endpoints
  endpoints: [
    {
      id: 'my-endpoint',
      name: 'My Endpoint',
      description: 'What this endpoint does',
      path: '/my-agent/endpoint',
      upstreamUrl: '/data',  // Relative to baseUrl
      method: 'GET',
      parameters: 'param1=value',
      exampleResponse: { result: 'example' }
    },
    {
      id: 'another-endpoint',
      name: 'Another Endpoint',
      description: 'Another endpoint',
      path: '/my-agent/other',
      upstreamUrl: '/other',  // Also relative to baseUrl
      method: 'POST',
      parameters: '',  // No parameters
      exampleResponse: { success: true }
    }
  ]
}
```

**Result:**
- `/my-agent/endpoint` → `https://api.example.com/v1/data`
- `/my-agent/other` → `https://api.example.com/v1/other`

### Upstream URL Resolution

The `upstreamUrl` can be:
1. **Relative path** (combined with agent's `baseUrl`): `/path`
2. **Full URL** (overrides agent's `baseUrl`): `https://different-api.com/endpoint`

See [`AGENT_STRUCTURE.md`](./AGENT_STRUCTURE.md) for detailed documentation.

### Features

Endpoints automatically:
- Appear in the agents list and UI
- Serve HTML documentation at the endpoint path
- Proxy JSON requests to the upstream URL
- Validate HTTP method
- Combine agent baseUrl with endpoint path

## Project Structure

```
x402/
├── index.js              # Main Express application with routing logic
├── agents.js             # Agent and endpoint configuration (data structure)
├── templates.js          # HTML template generators for product pages
├── package.json          # Project dependencies and scripts
├── ecosystem.config.cjs  # PM2 configuration
├── .env                  # Environment variables (not in git)
├── env.example           # Example environment variables template
├── .gitignore           # Git ignore patterns
├── README.md            # This file (main documentation)
├── QUICKSTART.md        # Quick start guide
├── EXAMPLES.md          # Usage examples
├── AGENT_STRUCTURE.md   # Agent configuration guide  
├── GROUPS_GUIDE.md      # Groups and multiple baseURLs guide
└── logs/                # PM2 logs directory (auto-created)
```

### File Descriptions

- **index.js** - Express server with content negotiation and dynamic routing
- **agents.js** - Data-driven configuration for all agents and endpoints (**Edit this to add endpoints!**)
- **templates.js** - HTML page generators for beautiful documentation
- **public/wallet-connector.js** - Client-side wallet connector for Phantom integration (for x402-enabled upstreams)
- **ecosystem.config.cjs** - PM2 process manager configuration
- **package.json** - Dependencies and npm scripts
- **AGENT_STRUCTURE.md** - Detailed guide for configuring agents with baseUrl

## Logs

PM2 logs are stored in the `logs/` directory:

- `error.log` - Error logs
- `out.log` - Standard output logs
- `combined.log` - Combined logs

View logs in real-time:

```bash
pm2 logs express-bun-server
```

## Web3 Wallet Integration

The gateway provides a client-side wallet connector to help users interact with x402-enabled upstream services.

### How It Works

1. **Upstream Services**: Your upstream APIs may implement the x402 payment protocol
2. **Client Wallet**: Users can connect their Phantom wallet via the gateway's UI
3. **Payment Flow**: 
   - User requests an endpoint
   - If upstream returns 402 Payment Required, payment details are shown
   - User pays the upstream service directly using their wallet
   - Gateway forwards the request with payment proof headers
   - Upstream validates payment and returns data

### Quick Start

1. **Install Phantom Wallet** (for users):
   - Visit https://phantom.app/
   - Install browser extension
   - Create or import a wallet

2. **Get Test SOL** (for devnet testing):
   - Visit https://solfaucet.com/
   - Request devnet SOL
   - Or use: `solana airdrop 1 YOUR_ADDRESS --url devnet`

3. **Use the UI**:
   - Navigate to any endpoint page in your browser
   - Connect Phantom Wallet if the upstream requires payment
   - Pay the upstream service to access protected endpoints

### Features

- 💳 **Phantom Wallet Support** - Seamless browser wallet integration
- ⛓️ **Multi-Network** - Support for mainnet, devnet, and testnet
- 🔐 **Cryptographic Proofs** - Sign and verify payment messages
- 📡 **x402 Headers** - Automatic payment header management
- 🔄 **Transparent Proxy** - Gateway forwards payment headers to upstream services

### Documentation

The wallet connector is purely client-side and helps users make payments to x402-enabled upstream services. The gateway acts as a transparent proxy, forwarding payment headers from the client to the upstream for verification.

**Note**: Payment verification is handled by the upstream services, not by this gateway.

## Performance

Bun provides excellent performance benefits:

- **Fast startup** - 3-4x faster than Node.js
- **Low memory usage** - More efficient memory management
- **Built-in utilities** - No need for additional tools like nodemon

## Troubleshooting

### Port Already in Use

If port 3000 is already in use, change the `PORT` in `.env` file or stop the conflicting process:

```bash
# Find process using port 3000
lsof -i :3000

# Kill the process
kill -9 <PID>
```

### PM2 Not Found

Ensure PM2 is installed globally:

```bash
bun install -g pm2
# or
npm install -g pm2
```

### Bun Not Found

Install Bun runtime:

```bash
curl -fsSL https://bun.sh/install | bash
```

## License

MIT

## Author

Built with ❤️ using Bun, Express, and PM2

