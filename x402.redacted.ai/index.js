import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import dotenv from 'dotenv';
import { readFileSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { getAllAgents, getAgentById, getEndpointByPath, getAllEndpoints, buildUpstreamUrl, getAgentGroups } from './agents.js';
import { generateEndpointPage, generateAgentsListPage, generateAgentDetailPage } from './templates.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment variables from .env file
const envResult = dotenv.config();

if (envResult.error) {
  console.log('⚠️  No .env file found, using defaults');
  console.log('💡 Create a .env file with: echo "PORT=3000" > .env');
} else {
  console.log('✅ Environment variables loaded from .env');
}

const app = express();
const PORT = process.env.PORT || 3000;
const HOST = process.env.HOST || '0.0.0.0';

// Get PUBLIC_URL and strip any trailing slashes for clean URLs
let publicUrl = process.env.PUBLIC_URL || `http://${HOST}:${PORT}`;
const PUBLIC_URL = publicUrl.replace(/\/+$/, '');

// Helper function to get real client IP from X-Forwarded-For
function getClientIp(req) {
  // X-Forwarded-For header contains comma-separated IPs: "client, proxy1, proxy2"
  // The leftmost IP is the original client IP
  const xForwardedFor = req.headers['x-forwarded-for'];
  
  if (xForwardedFor) {
    // Split by comma and get the first IP, trim whitespace
    const ips = xForwardedFor.split(',').map(ip => ip.trim());
    return ips[0];
  }
  
  // Fallback to other headers or socket address
  return req.headers['x-real-ip'] || 
         req.ip || 
         req.socket.remoteAddress || 
         'unknown';
}

// Middleware
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: [
        "'self'", 
        "'unsafe-inline'", 
        "https://unpkg.com",
        "https://cdn.jsdelivr.net"
      ],
      scriptSrcAttr: ["'unsafe-inline'"], // Allow inline event handlers (onclick, onchange, etc.)
      styleSrc: ["'self'", "'unsafe-inline'"],
      imgSrc: ["'self'", "data:", "https:"],
      connectSrc: [
        "'self'",
        "https://api.mainnet-beta.solana.com",
        "https://api.devnet.solana.com",
        "https://api.testnet.solana.com",
        "https://unpkg.com",
        "https://cdn.jsdelivr.net"
      ],
      fontSrc: ["'self'", "https:", "data:"],
      objectSrc: ["'none'"],
      mediaSrc: ["'self'"],
      frameSrc: ["'none'"],
    },
  },
})); // Security headers
app.use(cors()); // Enable CORS
app.use('/public', express.static(path.join(__dirname, 'public'))); // Serve static files

// Custom morgan token for real client IP
morgan.token('client-ip', (req) => getClientIp(req));

// Request logging with real client IP
app.use(morgan(':client-ip - :remote-user [:date[clf]] ":method :url HTTP/:http-version" :status :res[content-length] ":referrer" ":user-agent"'));

app.use(express.json()); // Parse JSON bodies
app.use(express.urlencoded({ extended: true })); // Parse URL-encoded bodies

// Helper function to determine if client wants HTML
function wantsHtml(req) {
  const accept = req.headers.accept || '';
  // Check if Accept header prefers HTML over JSON
  return accept.includes('text/html') && !accept.includes('application/json');
}

// Helper function to proxy request to upstream
async function proxyToUpstream(upstreamUrl, method, queryParams, body, incomingHeaders = {}) {
  try {
    // Build URL with query parameters
    const url = new URL(upstreamUrl);
    Object.keys(queryParams).forEach(key => {
      url.searchParams.append(key, queryParams[key]);
    });

    // Forward relevant headers from the incoming request
    const forwardHeaders = {
      'User-Agent': 'X402-Gateway/1.0'
    };

    // Headers to forward from client (case-insensitive)
    const headersToForward = [
      'authorization',
      'accept',
      'accept-language',
      'accept-encoding',
      'content-type',
      'x-requested-with',
      'x-api-key',
      'x-client-id',
      // x402-specific payment headers
      'x-payment-id',
      'x-payment-proof',
      'x-payment-signature',
      'x-payment-timestamp',
      'x-payment-hash',
      'x-payment-network',
      'x-payment-amount'
    ];

    // Copy headers from incoming request
    for (const [key, value] of Object.entries(incomingHeaders)) {
      const lowerKey = key.toLowerCase();
      if (headersToForward.includes(lowerKey)) {
        forwardHeaders[key] = value;
      }
      // Also forward any custom x- headers
      else if (lowerKey.startsWith('x-')) {
        forwardHeaders[key] = value;
      }
    }

    // Ensure Content-Type is set for POST requests
    if (method === 'POST' && !forwardHeaders['Content-Type'] && !forwardHeaders['content-type']) {
      forwardHeaders['Content-Type'] = 'application/json';
    }

    const options = {
      method: method,
      headers: forwardHeaders
    };

    if (method === 'POST' && body) {
      options.body = JSON.stringify(body);
    }

    const response = await fetch(url.toString(), options);
    const data = await response.json();
    
    return {
      success: true,
      statusCode: response.status,
      data: data,
      upstream: upstreamUrl
    };
  } catch (error) {
    return {
      success: false,
      error: error.message,
      upstream: upstreamUrl
    };
  }
}

// Favicon endpoint
app.get('/favicon.ico', (req, res) => {
  try {
    const favicon = readFileSync('./favicon.svg');
    res.setHeader('Content-Type', 'image/svg+xml');
    res.setHeader('Cache-Control', 'public, max-age=86400'); // Cache for 1 day
    res.send(favicon);
  } catch (error) {
    res.status(404).send('Favicon not found');
  }
});

// Validation helper functions for x402 schema
function validateBasicX402Schema(data) {
  try {
    // Basic x402 validation - minimal requirements for most clients
    if (typeof data !== 'object' || data === null) {
      return { valid: false, errors: ['Response must be an object'] };
    }

    const errors = [];

    // Check x402Version exists and is a number
    if (typeof data.x402Version !== 'number') {
      errors.push('x402Version must be a number');
    }

    // If accepts exists, it should be an array
    if (data.accepts !== undefined) {
      if (!Array.isArray(data.accepts)) {
        errors.push('accepts must be an array');
      } else {
        // Check each accepts item has minimal fields
        data.accepts.forEach((item, idx) => {
          if (typeof item !== 'object' || item === null) {
            errors.push(`accepts[${idx}] must be an object`);
          } else {
            // Minimal fields check
            if (!item.resource) errors.push(`accepts[${idx}].resource is required`);
            if (!item.payTo) errors.push(`accepts[${idx}].payTo is required`);
          }
        });
      }
    }

    return { valid: errors.length === 0, errors };
  } catch (e) {
    return { valid: false, errors: [e.message] };
  }
}

function validateStrictX402ScanSchema(data) {
  try {
    // Strict x402scan.com validation
    if (typeof data !== 'object' || data === null) {
      return { valid: false, errors: ['Response must be an object'] };
    }

    const errors = [];

    // Check x402Version
    if (typeof data.x402Version !== 'number') {
      errors.push('x402Version must be a number');
    }

    // accepts must exist and be an array
    if (!data.accepts) {
      errors.push('accepts array is required for x402scan.com');
    } else if (!Array.isArray(data.accepts)) {
      errors.push('accepts must be an array');
    } else if (data.accepts.length === 0) {
      errors.push('accepts array cannot be empty for x402scan.com');
    } else {
      // Strict validation for each accepts item
      data.accepts.forEach((item, idx) => {
        if (typeof item !== 'object' || item === null) {
          errors.push(`accepts[${idx}] must be an object`);
          return;
        }

        // All required fields for x402scan.com
        const requiredFields = {
          scheme: 'string',
          network: 'string',
          maxAmountRequired: 'string',
          resource: 'string',
          description: 'string',
          mimeType: 'string',
          payTo: 'string',
          maxTimeoutSeconds: 'number',
          asset: 'string'
        };

        for (const [field, expectedType] of Object.entries(requiredFields)) {
          if (item[field] === undefined || item[field] === null) {
            errors.push(`accepts[${idx}].${field} is required for x402scan.com`);
          } else if (typeof item[field] !== expectedType) {
            errors.push(`accepts[${idx}].${field} must be a ${expectedType}, got ${typeof item[field]}`);
          }
        }

        // Validate scheme is exactly "exact"
        if (item.scheme && item.scheme !== 'exact') {
          errors.push(`accepts[${idx}].scheme must be "exact" for x402scan.com, got "${item.scheme}"`);
        }

        // Validate network is a known network (base, solana, ethereum, etc.)
        const validNetworks = ['base', 'solana', 'ethereum', 'polygon', 'arbitrum', 'optimism'];
        if (item.network && !validNetworks.includes(item.network.toLowerCase())) {
          errors.push(`accepts[${idx}].network must be a valid network (e.g., base, solana, ethereum), got "${item.network}"`);
        }

        // Validate outputSchema structure if present
        if (item.outputSchema !== undefined) {
          if (typeof item.outputSchema !== 'object' || item.outputSchema === null) {
            errors.push(`accepts[${idx}].outputSchema must be an object if provided`);
          } else if (item.outputSchema.input) {
            const input = item.outputSchema.input;
            if (input.type !== 'http') {
              errors.push(`accepts[${idx}].outputSchema.input.type must be "http"`);
            }
            if (input.method && !['GET', 'POST'].includes(input.method)) {
              errors.push(`accepts[${idx}].outputSchema.input.method must be "GET" or "POST"`);
            }
            if (input.bodyType && !['json', 'form-data', 'multipart-form-data', 'text', 'binary'].includes(input.bodyType)) {
              errors.push(`accepts[${idx}].outputSchema.input.bodyType must be one of: json, form-data, multipart-form-data, text, binary`);
            }
          }
        }

        // Validate extra is an object if present
        if (item.extra !== undefined && (typeof item.extra !== 'object' || item.extra === null || Array.isArray(item.extra))) {
          errors.push(`accepts[${idx}].extra must be a plain object if provided`);
        }
      });
    }

    return { valid: errors.length === 0, errors };
  } catch (e) {
    return { valid: false, errors: [e.message] };
  }
}

// Test/validate x402 JSON endpoint
app.post('/test', express.json(), (req, res) => {
  const { url, data } = req.body;

  // If URL is provided, fetch and validate
  if (url) {
    fetch(url)
      .then(response => response.json())
      .then(jsonData => {
        const basicValidation = validateBasicX402Schema(jsonData);
        const strictValidation = validateStrictX402ScanSchema(jsonData);

        res.json({
          isBasicValid: basicValidation.valid,
          isStrictValid: strictValidation.valid,
          basicErrors: basicValidation.errors,
          strictErrors: strictValidation.errors,
          data: jsonData
        });
      })
      .catch(error => {
        res.status(400).json({
          isBasicValid: false,
          isStrictValid: false,
          error: `Failed to fetch or parse JSON from URL: ${error.message}`
        });
      });
  } else if (data) {
    // Validate provided data directly
    const basicValidation = validateBasicX402Schema(data);
    const strictValidation = validateStrictX402ScanSchema(data);

    res.json({
      isBasicValid: basicValidation.valid,
      isStrictValid: strictValidation.valid,
      basicErrors: basicValidation.errors,
      strictErrors: strictValidation.errors,
      data: data
    });
  } else {
    res.status(400).json({
      error: 'Must provide either "url" or "data" in request body',
      usage: {
        byUrl: { url: 'https://example.com/api/endpoint' },
        byData: { data: { x402Version: 1, accepts: [] } }
      }
    });
  }
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.status(200).json({
    status: 'OK',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    environment: process.env.NODE_ENV || 'development',
    runtime: 'bun',
    agents: getAllAgents().length,
    endpoints: getAllEndpoints().length
  });
});

// Root endpoint - Gateway homepage
app.get('/', (req, res) => {
  if (wantsHtml(req)) {
    // Serve a simple HTML homepage
    const agents = getAllAgents();
    const endpoints = getAllEndpoints();
    const html = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/svg+xml" href="/favicon.ico">
    <title>X402 API Gateway</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .hero {
            background: white;
            border-radius: 24px;
            padding: 60px;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
            margin-bottom: 30px;
        }
        h1 { font-size: 56px; color: #1a1a1a; margin-bottom: 20px; }
        .subtitle { font-size: 24px; color: #666; margin-bottom: 40px; }
        .cta-button {
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 18px 40px;
            border-radius: 12px;
            text-decoration: none;
            font-size: 18px;
            font-weight: 600;
            transition: transform 0.2s;
            margin: 10px;
            border: none;
            cursor: pointer;
        }
        .cta-button:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
        }
        .cta-button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        .stats {
            display: flex;
            justify-content: center;
            gap: 40px;
            margin-top: 40px;
            padding-top: 40px;
            border-top: 2px solid #f0f0f0;
        }
        .stat { text-align: center; }
        .stat-number { font-size: 36px; font-weight: 700; color: #667eea; }
        .stat-label { color: #666; margin-top: 5px; }
        
        /* Testing Utility Styles */
        .testing-panel {
            background: white;
            border-radius: 24px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
        }
        .testing-panel h2 {
            font-size: 32px;
            color: #1a1a1a;
            margin-bottom: 10px;
        }
        .testing-panel .description {
            color: #666;
            margin-bottom: 30px;
            font-size: 16px;
        }
        .test-controls {
            display: grid;
            gap: 20px;
            margin-bottom: 30px;
        }
        .form-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .form-group label {
            font-weight: 600;
            color: #333;
            font-size: 14px;
        }
        .form-group select,
        .form-group input {
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            font-family: 'Monaco', 'Courier New', monospace;
        }
        .form-group select:focus,
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        .rate-limit-info {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .rate-limit-info .label {
            color: #666;
            font-size: 14px;
        }
        .rate-limit-info .value {
            font-weight: 700;
            color: #667eea;
            font-size: 18px;
        }
        .test-output {
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 20px;
            border-radius: 8px;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            max-height: 400px;
            overflow-y: auto;
            margin-top: 20px;
        }
        .test-output .log-entry {
            margin-bottom: 10px;
            padding-bottom: 10px;
            border-bottom: 1px solid #333;
        }
        .test-output .log-entry:last-child {
            border-bottom: none;
        }
        .test-output .timestamp {
            color: #858585;
        }
        .test-output .success {
            color: #4ec9b0;
        }
        .test-output .error {
            color: #f48771;
        }
        .test-output .info {
            color: #569cd6;
        }
        .queue-status {
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
        }
        .queue-stat {
            flex: 1;
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .queue-stat .number {
            font-size: 24px;
            font-weight: 700;
            color: #667eea;
        }
        .queue-stat .label {
            color: #666;
            font-size: 12px;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="hero">
            <h1>🚀 X402 API Gateway</h1>
            <p class="subtitle">Dynamic routing with intelligent content negotiation</p>
            <p style="color: #888; margin-bottom: 30px;">
                Access agent endpoints as beautiful documentation pages or raw JSON APIs
            </p>
            <div>
                <a href="/agents" class="cta-button">Browse Agents</a>
                <a href="/health" class="cta-button" style="background: white; color: #667eea; border: 2px solid #667eea;">Health Check</a>
            </div>
            <div class="stats">
                <div class="stat">
                    <div class="stat-number">${agents.length}</div>
                    <div class="stat-label">Agents</div>
                </div>
                <div class="stat">
                    <div class="stat-number">${endpoints.length}</div>
                    <div class="stat-label">Endpoints</div>
                </div>
                <div class="stat">
                    <div class="stat-number">⚡</div>
                    <div class="stat-label">Bun Powered</div>
                </div>
            </div>
        </div>

        <div class="testing-panel">
            <h2>🧪 Endpoint Tester</h2>
            <p class="description">Test x402 endpoints or any web URL with built-in rate limiting for free tier usage</p>
            
            <div class="rate-limit-info">
                <div>
                    <div class="label">Rate Limit</div>
                    <div class="value" id="rateLimit">10 req/min</div>
                </div>
                <div>
                    <div class="label">Requests Made</div>
                    <div class="value" id="requestCount">0</div>
                </div>
                <div>
                    <div class="label">Queue Size</div>
                    <div class="value" id="queueSize">0</div>
                </div>
            </div>

            <div class="test-controls">
                <div class="form-group">
                    <label for="endpointMode">Endpoint Mode</label>
                    <select id="endpointMode" onchange="toggleEndpointMode()">
                        <option value="preset">Preset x402 Endpoints</option>
                        <option value="custom">Custom URL (Any Web URL)</option>
                    </select>
                </div>

                <div class="form-group" id="presetGroup">
                    <label for="endpoint">Select Endpoint</label>
                    <select id="endpoint">
                        <option value="">Choose an endpoint...</option>
                        ${endpoints.map(ep => {
                            const method = Array.isArray(ep.method) ? ep.method[0] : ep.method;
                            const methodDisplay = Array.isArray(ep.method) ? ep.method.join('/') : ep.method;
                            return `
                            <option value="${ep.path}" data-method="${method}">
                                ${ep.agentIcon} ${ep.agentName} - ${ep.name} (${methodDisplay})
                            </option>
                        `;
                        }).join('')}
                    </select>
                </div>

                <div class="form-group" id="customGroup" style="display: none;">
                    <label for="customUrl">Custom URL</label>
                    <input type="text" id="customUrl" placeholder="https://api.example.com/endpoint" style="width: 100%;">
                </div>

                <div class="form-group" id="customMethodGroup" style="display: none;">
                    <label for="customMethod">HTTP Method</label>
                    <select id="customMethod">
                        <option value="GET">GET</option>
                        <option value="POST">POST</option>
                        <option value="PUT">PUT</option>
                        <option value="DELETE">DELETE</option>
                        <option value="PATCH">PATCH</option>
                    </select>
                </div>

                <div class="form-group">
                    <label for="queryParams">Query Parameters (e.g., ?param1=value1&param2=value2)</label>
                    <input type="text" id="queryParams" placeholder="?key=value&another=value" style="width: 100%;">
                </div>

                <div class="form-group">
                    <label for="rateLimitInput">Rate Limit (requests per minute)</label>
                    <input type="number" id="rateLimitInput" value="10" min="1" max="60">
                </div>

                <div style="display: flex; gap: 10px;">
                    <button class="cta-button" onclick="testEndpoint()" id="testBtn">
                        ▶️ Test Endpoint
                    </button>
                    <button class="cta-button" onclick="testAllEndpoints()" id="testAllBtn">
                        🔄 Test All Endpoints
                    </button>
                    <button class="cta-button" onclick="clearLogs()" style="background: #dc3545;">
                        🗑️ Clear Logs
                    </button>
                </div>
            </div>

            <div class="test-output" id="output">
                <div class="log-entry">
                    <span class="info">Ready to test endpoints. Select an endpoint and click "Test Endpoint".</span>
                </div>
            </div>
            
            <div style="margin-top: 30px; padding-top: 30px; border-top: 2px solid #e0e0e0;">
                <h3 style="font-size: 24px; margin-bottom: 10px;">💳 Web3 Wallet Connector</h3>
                <p class="description">Connect your wallet to make real x402 payments (Solana or EVM chains)</p>
            
            <div id="home-wallet-status" style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div style="font-size: 32px;">👛</div>
                    <div style="flex: 1;">
                        <div style="font-weight: 600; margin-bottom: 5px;">
                            <span id="home-wallet-type" style="color: #667eea;"></span>
                            <span id="home-wallet-status-text">Not Connected</span>
                        </div>
                        <div style="font-size: 14px; color: #666;" id="home-wallet-address"></div>
                        <div style="font-size: 12px; color: #888; margin-top: 5px;" id="home-wallet-chain"></div>
                    </div>
                </div>
            </div>
            
            <div id="wallet-selection" style="margin-bottom: 20px;">
                <div style="font-weight: 600; margin-bottom: 10px; color: #333;">Choose Your Wallet:</div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                    <button id="home-connect-phantom-btn" class="cta-button" style="background: linear-gradient(135deg, #9945FF 0%, #14F195 100%);">
                        🟣 Phantom (Solana)
                    </button>
                    <button id="home-connect-metamask-btn" class="cta-button" style="background: linear-gradient(135deg, #F6851B 0%, #E2761B 100%);">
                        🦊 MetaMask (EVM)
                    </button>
                </div>
            </div>
            
            <div id="disconnect-section" style="display: none; margin-bottom: 20px;">
                <button id="home-disconnect-wallet-btn" class="cta-button" style="width: 100%; background: #dc3545;">
                    ❌ Disconnect Wallet
                </button>
            </div>
            
            <div id="home-wallet-info" style="display: none;">
                <div style="background: #dbeafe; border-left: 4px solid #3b82f6; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    <div style="font-weight: 600; color: #1e3a8a; margin-bottom: 5px;">✅ Wallet Connected</div>
                    <div style="color: #1e40af; font-size: 14px; margin-bottom: 10px;">
                        Your wallet is now connected and ready to make x402 payments.
                    </div>
                    <div style="font-family: 'Monaco', monospace; font-size: 13px;">
                        <div><strong>Public Key:</strong> <span id="home-wallet-pubkey" style="word-break: break-all;"></span></div>
                        <div><strong>Network:</strong> <span id="home-wallet-network">devnet</span></div>
                    </div>
                </div>
                
                <div style="background: #f3f4f6; padding: 15px; border-radius: 8px;">
                    <div style="font-weight: 600; margin-bottom: 10px;">💡 Next Steps:</div>
                    <ol style="margin-left: 20px; color: #666; font-size: 14px; line-height: 1.8;">
                        <li>Browse available <a href="/agents" style="color: #667eea; text-decoration: underline;">agents and endpoints</a></li>
                        <li>Visit any endpoint page to see payment details</li>
                        <li>Use the wallet connector on each page to make payments</li>
                        <li>Access protected content with your payments!</li>
                    </ol>
                </div>
            </div>
            
            <div id="home-install-phantom" style="display: none; background: #fee2e2; border-left: 4px solid #ef4444; padding: 15px; border-radius: 8px;">
                <div style="font-weight: 600; color: #991b1b; margin-bottom: 5px;">⚠️ Phantom Wallet Not Detected</div>
                <div style="color: #7f1d1d; font-size: 14px; margin-bottom: 10px;">
                    Please install Phantom wallet to connect and make Web3 payments.
                </div>
                <a href="https://phantom.app/" target="_blank" rel="noopener" class="cta-button" style="display: inline-block; text-decoration: none; margin-top: 10px;">
                    Download Phantom Wallet →
                </a>
            </div>
            </div>
        </div>
    </div>

    <!-- Load wallet connectors -->
    <script src="/public/wallet-connector.js"></script>
    <script src="/public/evm-wallet-connector.js"></script>
    <script>
      console.log('✅ Solana wallet connector loaded');
      console.log('✅ EVM wallet connector loaded');
      console.log('Phantom available:', typeof window.solana !== 'undefined');
      console.log('MetaMask available:', typeof window.ethereum !== 'undefined');
    </script>

    <script>
        let requestQueue = [];
        let requestCount = 0;
        let isProcessing = false;
        let requestsThisMinute = 0;
        let minuteStartTime = Date.now();

        function toggleEndpointMode() {
            const mode = document.getElementById('endpointMode').value;
            const presetGroup = document.getElementById('presetGroup');
            const customGroup = document.getElementById('customGroup');
            const customMethodGroup = document.getElementById('customMethodGroup');
            const testAllBtn = document.getElementById('testAllBtn');

            if (mode === 'custom') {
                presetGroup.style.display = 'none';
                customGroup.style.display = 'flex';
                customMethodGroup.style.display = 'flex';
                testAllBtn.style.display = 'none';
            } else {
                presetGroup.style.display = 'flex';
                customGroup.style.display = 'none';
                customMethodGroup.style.display = 'none';
                testAllBtn.style.display = 'inline-block';
            }
        }

        function log(message, type = 'info') {
            const output = document.getElementById('output');
            const timestamp = new Date().toLocaleTimeString();
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.innerHTML = \`
                <span class="timestamp">[\${timestamp}]</span> 
                <span class="\${type}">\${message}</span>
            \`;
            output.appendChild(entry);
            output.scrollTop = output.scrollHeight;
        }

        function updateStats() {
            document.getElementById('requestCount').textContent = requestCount;
            document.getElementById('queueSize').textContent = requestQueue.length;
            const rateLimit = document.getElementById('rateLimitInput').value;
            document.getElementById('rateLimit').textContent = \`\${rateLimit} req/min\`;
        }

        function clearLogs() {
            document.getElementById('output').innerHTML = '';
            log('Logs cleared.', 'info');
        }

        async function makeRequest(endpoint, method) {
            try {
                const response = await fetch(endpoint, {
                    method: method,
                    headers: {
                        'Accept': 'application/json'
                    }
                });

                const data = await response.json();
                
                if (response.ok) {
                    log(\`✓ SUCCESS [\${method}] \${endpoint} - Status: \${response.status}\`, 'success');
                    log(\`Response: \${JSON.stringify(data).substring(0, 200)}...\`, 'info');
                } else {
                    log(\`✗ ERROR [\${method}] \${endpoint} - Status: \${response.status}\`, 'error');
                    log(\`Response: \${JSON.stringify(data).substring(0, 200)}...\`, 'info');
                    
                    // If it's a 402 Payment Required, validate the x402 schema
                    if (response.status === 402 && data.x402Version !== undefined) {
                        log(\`🔍 Detected x402 response, validating schema...\`, 'info');
                        await validateX402Response(data);
                    }
                }
                
                requestCount++;
                requestsThisMinute++;
                updateStats();
            } catch (error) {
                log(\`✗ FAILED [\${method}] \${endpoint} - \${error.message}\`, 'error');
                requestCount++;
                updateStats();
            }
        }

        async function validateX402Response(data) {
            try {
                const validationResponse = await fetch('/test', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ data })
                });

                const validation = await validationResponse.json();
                
                // Display validation results
                if (validation.isBasicValid && validation.isStrictValid) {
                    log(\`✓ VALIDATION: ✅ Basic x402 ✅ x402scan.com strict\`, 'success');
                } else if (validation.isBasicValid) {
                    log(\`✓ VALIDATION: ✅ Basic x402 ❌ x402scan.com strict\`, 'info');
                    if (validation.strictErrors.length > 0) {
                        log(\`  Strict errors: \${validation.strictErrors.join(', ')}\`, 'error');
                    }
                } else {
                    log(\`✗ VALIDATION: ❌ Basic x402 ❌ x402scan.com strict\`, 'error');
                    if (validation.basicErrors.length > 0) {
                        log(\`  Basic errors: \${validation.basicErrors.join(', ')}\`, 'error');
                    }
                }
            } catch (error) {
                log(\`⚠️ Validation failed: \${error.message}\`, 'error');
            }
        }

        async function processQueue() {
            if (isProcessing || requestQueue.length === 0) {
                return;
            }

            isProcessing = true;
            const rateLimit = parseInt(document.getElementById('rateLimitInput').value);
            
            // Reset minute counter if a minute has passed
            const now = Date.now();
            if (now - minuteStartTime >= 60000) {
                requestsThisMinute = 0;
                minuteStartTime = now;
            }

            while (requestQueue.length > 0) {
                // Check if we've hit the rate limit
                if (requestsThisMinute >= rateLimit) {
                    const waitTime = 60000 - (Date.now() - minuteStartTime);
                    log(\`⏸️ Rate limit reached. Waiting \${Math.ceil(waitTime / 1000)}s before continuing...\`, 'info');
                    await new Promise(resolve => setTimeout(resolve, waitTime));
                    requestsThisMinute = 0;
                    minuteStartTime = Date.now();
                }

                const { endpoint, method } = requestQueue.shift();
                updateStats();
                
                await makeRequest(endpoint, method);
                
                // Add delay between requests (at least 60000/rateLimit ms)
                const delayBetweenRequests = Math.ceil(60000 / rateLimit);
                if (requestQueue.length > 0) {
                    await new Promise(resolve => setTimeout(resolve, delayBetweenRequests));
                }
            }

            isProcessing = false;
            log('✓ Queue processing complete.', 'success');
            updateStats();
        }

        function testEndpoint() {
            const mode = document.getElementById('endpointMode').value;
            let endpoint, method;

            if (mode === 'custom') {
                endpoint = document.getElementById('customUrl').value.trim();
                method = document.getElementById('customMethod').value;

                if (!endpoint) {
                    log('⚠️ Please enter a custom URL.', 'error');
                    return;
                }

                // Validate URL format
                try {
                    new URL(endpoint);
                } catch (e) {
                    log('⚠️ Invalid URL format. Please enter a valid URL (e.g., https://api.example.com/endpoint)', 'error');
                    return;
                }
            } else {
                const select = document.getElementById('endpoint');
                endpoint = select.value;
                
                if (!endpoint) {
                    log('⚠️ Please select an endpoint first.', 'error');
                    return;
                }

                method = select.options[select.selectedIndex].dataset.method;
            }
            
            // Add query parameters if provided
            const queryParams = document.getElementById('queryParams').value.trim();
            if (queryParams) {
                // Remove leading ? if present
                const cleanParams = queryParams.startsWith('?') ? queryParams.substring(1) : queryParams;
                // Check if endpoint already has query parameters
                endpoint = endpoint + (endpoint.includes('?') ? '&' : '?') + cleanParams;
            }
            
            log(\`📋 Adding to queue: [\${method}] \${endpoint}\`, 'info');
            requestQueue.push({ endpoint, method });
            updateStats();
            processQueue();
        }

        function testAllEndpoints() {
            const select = document.getElementById('endpoint');
            const options = Array.from(select.options).slice(1); // Skip the first "Choose..." option
            
            if (options.length === 0) {
                log('⚠️ No endpoints available.', 'error');
                return;
            }

            log(\`📋 Adding all \${options.length} endpoints to queue...\`, 'info');
            
            options.forEach(option => {
                const endpoint = option.value;
                const method = option.dataset.method;
                requestQueue.push({ endpoint, method });
            });
            
            updateStats();
            processQueue();
        }

        // Initialize stats
        updateStats();
        
        // Home page wallet connector
        const homeConnectPhantomBtn = document.getElementById('home-connect-phantom-btn');
        const homeConnectMetaMaskBtn = document.getElementById('home-connect-metamask-btn');
        const homeDisconnectBtn = document.getElementById('home-disconnect-wallet-btn');
        const homeStatusText = document.getElementById('home-wallet-status-text');
        const homeWalletType = document.getElementById('home-wallet-type');
        const homeWalletAddress = document.getElementById('home-wallet-address');
        const homeWalletChain = document.getElementById('home-wallet-chain');
        const homeWalletInfo = document.getElementById('home-wallet-info');
        const homeInstallPhantom = document.getElementById('home-install-phantom');
        const homeWalletPubkey = document.getElementById('home-wallet-pubkey');
        const walletSelection = document.getElementById('wallet-selection');
        const disconnectSection = document.getElementById('disconnect-section');
        
        let currentWalletType = null; // 'solana' or 'evm'
        
        // Check if wallet connector is available
        function checkHomePhantom() {
            if (typeof window.walletConnector === 'undefined') {
                console.log('Waiting for wallet connector to load...');
                setTimeout(checkHomePhantom, 100);
                return;
            }
            
            if (!window.walletConnector.isPhantomInstalled()) {
                homeInstallPhantom.style.display = 'block';
                homeConnectBtn.disabled = true;
                homeConnectBtn.style.opacity = '0.5';
                homeConnectBtn.style.cursor = 'not-allowed';
            }
        }
        
        function updateHomeWalletUI(connected, type = null) {
            if (connected) {
                homeStatusText.textContent = 'Connected';
                homeStatusText.style.color = '#10b981';
                walletSelection.style.display = 'none';
                disconnectSection.style.display = 'block';
                homeWalletInfo.style.display = 'block';
                
                if (type === 'solana') {
                    homeWalletType.textContent = '🟣 Phantom (Solana) - ';
                    homeWalletAddress.textContent = window.walletConnector.publicKey;
                    homeWalletPubkey.textContent = window.walletConnector.publicKey;
                    homeWalletChain.textContent = 'Network: Solana';
                } else if (type === 'evm') {
                    const connector = window.evmWalletConnector;
                    homeWalletType.textContent = '🦊 ' + connector.getWalletName() + ' (EVM) - ';
                    homeWalletAddress.textContent = connector.address;
                    homeWalletPubkey.textContent = connector.address;
                    homeWalletChain.textContent = 'Network: ' + connector.chainName + ' (Chain ID: ' + connector.chainId + ')';
                }
            } else {
                homeStatusText.textContent = 'Not Connected';
                homeStatusText.style.color = '#666';
                homeWalletType.textContent = '';
                homeWalletAddress.textContent = '';
                homeWalletChain.textContent = '';
                walletSelection.style.display = 'block';
                disconnectSection.style.display = 'none';
                homeWalletInfo.style.display = 'none';
                currentWalletType = null;
            }
        }
        
        // Connect Phantom (Solana)
        homeConnectPhantomBtn.addEventListener('click', async function() {
            if (typeof window.walletConnector === 'undefined') {
                alert('Wallet connector not loaded. Please refresh the page.');
                return;
            }
            
            homeConnectPhantomBtn.disabled = true;
            const originalText = homeConnectPhantomBtn.textContent;
            homeConnectPhantomBtn.textContent = '🔄 Connecting...';
            
            log('🔄 Attempting to connect to Phantom wallet...', 'info');
            
            const diagnostics = window.walletConnector.getDiagnostics();
            console.log('Phantom Diagnostics:', diagnostics);
            
            const result = await window.walletConnector.connectPhantom();
            
            if (result.success) {
                currentWalletType = 'solana';
                updateHomeWalletUI(true, 'solana');
                log('✅ Phantom connected: ' + result.publicKey, 'success');
            } else {
                log('❌ Failed to connect: ' + result.error, 'error');
                alert(result.error);
                homeConnectPhantomBtn.disabled = false;
                homeConnectPhantomBtn.textContent = originalText;
            }
        });
        
        // Connect MetaMask (EVM)
        homeConnectMetaMaskBtn.addEventListener('click', async function() {
            if (typeof window.evmWalletConnector === 'undefined') {
                alert('EVM wallet connector not loaded. Please refresh the page.');
                return;
            }
            
            homeConnectMetaMaskBtn.disabled = true;
            const originalText = homeConnectMetaMaskBtn.textContent;
            homeConnectMetaMaskBtn.textContent = '🔄 Connecting...';
            
            log('🔄 Attempting to connect to MetaMask/EVM wallet...', 'info');
            
            const diagnostics = window.evmWalletConnector.getDiagnostics();
            console.log('EVM Wallet Diagnostics:', diagnostics);
            
            const result = await window.evmWalletConnector.connect();
            
            if (result.success) {
                currentWalletType = 'evm';
                updateHomeWalletUI(true, 'evm');
                log('✅ ' + result.walletName + ' connected: ' + result.address, 'success');
                log('Chain: ' + result.chainName + ' (' + result.chainId + ')', 'info');
            } else {
                log('❌ Failed to connect: ' + result.error, 'error');
                alert(result.error);
                homeConnectMetaMaskBtn.disabled = false;
                homeConnectMetaMaskBtn.textContent = originalText;
            }
        });
        
        // Disconnect wallet
        homeDisconnectBtn.addEventListener('click', async function() {
            if (currentWalletType === 'solana' && typeof window.walletConnector !== 'undefined') {
                await window.walletConnector.disconnect();
                log('🔌 Phantom wallet disconnected', 'info');
            } else if (currentWalletType === 'evm' && typeof window.evmWalletConnector !== 'undefined') {
                await window.evmWalletConnector.disconnect();
                log('🔌 EVM wallet disconnected', 'info');
            }
            updateHomeWalletUI(false);
        });
        
        // Check Phantom on load
        checkHomePhantom();
    </script>
</body>
</html>`;
    res.send(html);
  } else {
    res.json({
      message: 'X402 API Gateway',
      version: '1.0.0',
      description: 'Dynamic routing with content negotiation',
      agents: getAllAgents().length,
      endpoints: getAllEndpoints().length,
      links: {
        health: '/health',
        agents: '/agents',
        documentation: 'Visit any endpoint with Accept: text/html header'
      }
    });
  }
});

// List all agents
app.get('/agents', (req, res) => {
  const agents = getAllAgents();
  
  if (wantsHtml(req)) {
    const html = generateAgentsListPage(agents, PUBLIC_URL);
    res.send(html);
  } else {
    res.json({
      agents: agents.map(agent => {
        // Count all endpoints across all groups (groups are internal only)
        const endpointCount = (agent.groups || []).reduce((total, group) => 
          total + group.endpoints.length, 0
        );
        return {
          id: agent.id,
          name: agent.name,
          description: agent.description,
          icon: agent.icon,
          endpointCount: endpointCount,
          link: `/agents/${agent.id}`
        };
      })
    });
  }
});

// Get specific agent details
app.get('/agents/:agentId', (req, res) => {
  const agent = getAgentById(req.params.agentId);
  
  if (!agent) {
    return res.status(404).json({ error: 'Agent not found' });
  }
  
  if (wantsHtml(req)) {
    const html = generateAgentDetailPage(agent, PUBLIC_URL);
    res.send(html);
  } else {
    // Flatten endpoints from all groups - groups are internal only
    const endpoints = [];
    for (const group of (agent.groups || [])) {
      for (const ep of group.endpoints) {
        endpoints.push({
          id: ep.id,
          name: ep.name,
          description: ep.description,
          path: ep.path,
          method: ep.method,
          link: ep.path
        });
      }
    }
    
    res.json({
      agent: {
        id: agent.id,
        name: agent.name,
        description: agent.description,
        icon: agent.icon,
        endpoints: endpoints.map(ep => ({
          ...ep,
          method: Array.isArray(ep.method) ? ep.method : [ep.method]
        }))
      }
    });
  }
});

// Dynamic endpoint handler - handles all agent endpoints
app.all('*', async (req, res, next) => {
  const result = getEndpointByPath(req.path);
  
  if (!result) {
    return next(); // Pass to 404 handler
  }
  
  const { agent, group, endpoint } = result;
  
  // Check if request method matches
  const allowedMethods = Array.isArray(endpoint.method) ? endpoint.method : [endpoint.method];
  if (!allowedMethods.includes(req.method)) {
    return res.status(405).json({
      error: 'Method Not Allowed',
      message: `This endpoint only accepts ${allowedMethods.join(', ')} requests`,
      endpoint: endpoint.path,
      allowedMethods: allowedMethods
    });
  }
  
  // Content negotiation - HTML or JSON
  if (wantsHtml(req)) {
    // Serve product description page
    const html = generateEndpointPage(agent, endpoint, PUBLIC_URL);
    res.send(html);
  } else {
    // Proxy to upstream and return JSON
    const queryParams = req.query || {};
    const body = req.body || {};
    
    // Build full upstream URL from group baseUrl + endpoint upstreamUrl
    const fullUpstreamUrl = buildUpstreamUrl(group, endpoint);
    
    // Use the actual request method (already validated above)
    console.log(`Proxying ${req.method} request to: ${fullUpstreamUrl}`);
    console.log(`  Agent: ${agent.name}, Group: ${group.name}`);
    if (Object.keys(queryParams).length > 0) {
      console.log(`  Query Params:`, queryParams);
    }
    if (req.method === 'POST' && Object.keys(body).length > 0) {
      console.log(`  Body:`, body);
    }
    
    const proxyResult = await proxyToUpstream(
      fullUpstreamUrl,
      req.method,
      queryParams,
      body,
      req.headers
    );
    
    if (proxyResult.success) {
      res.status(proxyResult.statusCode).json({
        endpoint: endpoint.path,
        agent: agent.name,
        timestamp: new Date().toISOString(),
        ...proxyResult.data
      });
    } else {
      res.status(502).json({
        error: 'Bad Gateway',
        message: 'Failed to proxy request to upstream service',
        details: proxyResult.error,
        endpoint: endpoint.path,
        upstream: proxyResult.upstream
      });
    }
  }
});

// 404 handler
app.use((req, res) => {
  if (wantsHtml(req)) {
    const html = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>404 - Not Found</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .error-box {
            background: white;
            border-radius: 16px;
            padding: 60px;
            text-align: center;
            max-width: 600px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
        }
        .error-code { font-size: 72px; font-weight: 700; color: #667eea; margin-bottom: 20px; }
        h1 { font-size: 32px; color: #1a1a1a; margin-bottom: 15px; }
        p { color: #666; font-size: 16px; margin-bottom: 30px; }
        .home-link {
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 30px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            transition: transform 0.2s;
        }
        .home-link:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
    </style>
</head>
<body>
    <div class="error-box">
        <div class="error-code">404</div>
        <h1>Page Not Found</h1>
        <p>The route <code>${req.url}</code> doesn't exist on this server.</p>
        <a href="/" class="home-link">Go Home</a>
    </div>
</body>
</html>`;
    res.status(404).send(html);
  } else {
    res.status(404).json({
      error: 'Not Found',
      message: `Route ${req.url} not found`,
      method: req.method,
      availableEndpoints: getAllEndpoints().map(ep => ep.path)
    });
  }
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error('Error:', err.stack);
  res.status(err.status || 500).json({
    error: err.message || 'Internal Server Error',
    ...(process.env.NODE_ENV === 'development' && { stack: err.stack })
  });
});

// Start server
app.listen(PORT, HOST, () => {
  console.log(`🚀 Server running on http://${HOST}:${PORT}`);
  console.log(`🌐 Public URL: ${PUBLIC_URL}`);
  console.log(`📝 Environment: ${process.env.NODE_ENV || 'development'}`);
  console.log(`⚡ Runtime: Bun ${Bun.version}`);
  console.log(`📊 Process ID: ${process.pid}`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received. Shutting down gracefully...');
  process.exit(0);
});

process.on('SIGINT', () => {
  console.log('SIGINT received. Shutting down gracefully...');
  process.exit(0);
});

