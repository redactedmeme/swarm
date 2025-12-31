/**
 * HTML Templates for Product Pages
 * 
 * Generates beautiful product description pages for endpoints
 */

/**
 * Helper function to format method(s) as string
 */
function formatMethods(method) {
  if (Array.isArray(method)) {
    return method.join(', ');
  }
  return method;
}

/**
 * Helper function to generate method badges HTML
 */
function generateMethodBadges(method) {
  const methods = Array.isArray(method) ? method : [method];
  return methods.map(m => `<span class="method-badge method-${m.toLowerCase()}">${m}</span>`).join(' ');
}

/**
 * Helper function to get primary method for examples
 */
function getPrimaryMethod(method) {
  if (Array.isArray(method)) {
    return method[0]; // Use first method for examples
  }
  return method;
}

/**
 * Auto-generate example request URL from endpoint path and parameters
 * This ensures consistency and prevents manual URL errors
 */
function generateExampleRequest(endpoint) {
  const path = endpoint.path || '';
  const parameters = endpoint.parameters || '';
  
  // If no parameters, just return the path
  if (!parameters) {
    return path;
  }
  
  // If parameters is a string, append it to the path
  // It should be in the format: "param1=value1&param2=value2" or "?param1=value1&param2=value2"
  const queryString = parameters.startsWith('?') ? parameters : `?${parameters}`;
  
  return `${path}${queryString}`;
}

/**
 * Generate HTML page for an endpoint
 */
export function generateEndpointPage(agent, endpoint, baseUrl = 'http://localhost:3000') {
  const exampleResponseFormatted = JSON.stringify(endpoint.exampleResponse, null, 2);

  return `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/svg+xml" href="/favicon.ico">
    <title>${endpoint.name} - ${agent.name}</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .header {
            background: white;
            border-radius: 16px;
            padding: 40px;
            margin-bottom: 30px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
        }
        
        .breadcrumb {
            color: #666;
            font-size: 14px;
            margin-bottom: 20px;
        }
        
        .breadcrumb a {
            color: #667eea;
            text-decoration: none;
        }
        
        .breadcrumb a:hover {
            text-decoration: underline;
        }
        
        .title-section {
            display: flex;
            align-items: center;
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .icon {
            font-size: 64px;
        }
        
        .title-text h1 {
            font-size: 36px;
            color: #1a1a1a;
            margin-bottom: 8px;
        }
        
        .agent-name {
            color: #667eea;
            font-size: 16px;
            font-weight: 500;
        }
        
        .description {
            font-size: 18px;
            color: #666;
            margin-bottom: 30px;
            line-height: 1.8;
        }
        
        .endpoint-meta {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }
        
        .meta-item {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 10px 20px;
            background: #f5f5f5;
            border-radius: 8px;
            font-size: 14px;
        }
        
        .meta-label {
            font-weight: 600;
            color: #666;
        }
        
        .method-badge {
            padding: 4px 12px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
        }
        
        .method-get {
            background: #10b981;
            color: white;
        }
        
        .method-post {
            background: #3b82f6;
            color: white;
        }
        
        .content-card {
            background: white;
            border-radius: 16px;
            padding: 40px;
            margin-bottom: 30px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
        }
        
        .content-card h2 {
            font-size: 24px;
            color: #1a1a1a;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #f0f0f0;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        
        th {
            background: #f8f9fa;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #666;
            font-size: 14px;
            border-bottom: 2px solid #e9ecef;
        }
        
        td {
            padding: 12px;
            border-bottom: 1px solid #e9ecef;
            font-size: 14px;
        }
        
        tr:last-child td {
            border-bottom: none;
        }
        
        code {
            background: #f5f5f5;
            padding: 3px 8px;
            border-radius: 4px;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            color: #e83e8c;
        }
        
        pre {
            background: #1a1a1a;
            color: #f8f8f2;
            padding: 20px;
            border-radius: 8px;
            overflow-x: auto;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.5;
        }
        
        .badge {
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .badge-required {
            background: #fee2e2;
            color: #dc2626;
        }
        
        .badge-optional {
            background: #dbeafe;
            color: #2563eb;
        }
        
        .try-it {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
            display: inline-block;
            text-decoration: none;
        }
        
        .try-it:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }
        
        .code-block-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #2d2d2d;
            padding: 10px 20px;
            border-radius: 8px 8px 0 0;
            margin-top: 20px;
        }
        
        .code-block-title {
            color: #888;
            font-size: 12px;
            text-transform: uppercase;
            font-weight: 600;
        }
        
        .copy-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 12px;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .copy-btn:hover {
            background: #5568d3;
        }
        
        .code-wrapper {
            margin-top: 0;
        }
        
        .code-wrapper pre {
            border-radius: 0 0 8px 8px;
            margin-top: 0;
        }
        
        .footer {
            text-align: center;
            color: white;
            margin-top: 40px;
            padding: 20px;
        }
        
        .footer a {
            color: white;
            text-decoration: none;
            font-weight: 600;
        }
        
        .footer a:hover {
            text-decoration: underline;
        }
        
        .json-access {
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 16px;
            border-radius: 8px;
            margin-top: 20px;
        }
        
        .json-access-title {
            font-weight: 600;
            color: #92400e;
            margin-bottom: 8px;
        }
        
        .json-access-desc {
            color: #78350f;
            font-size: 14px;
        }
        
        .json-access code {
            background: white;
            color: #92400e;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="breadcrumb">
                <a href="/">Home</a> / <a href="/agents">Agents</a> / <a href="/agents/${agent.id}">${agent.name}</a> / ${endpoint.name}
            </div>
            
            <div class="title-section">
                <div class="icon">${agent.icon}</div>
                <div class="title-text">
                    <h1>${endpoint.name}</h1>
                    <div class="agent-name">${agent.name}</div>
                </div>
            </div>
            
            <p class="description">${endpoint.description}</p>
            
            <div class="endpoint-meta">
                <div class="meta-item">
                    <span class="meta-label">Method:</span>
                    ${generateMethodBadges(endpoint.method)}
                </div>
                <div class="meta-item">
                    <span class="meta-label">Path:</span>
                    <code>${endpoint.path}</code>
                </div>
            </div>
        </div>
        
        <div class="content-card">
            <h2>📋 Parameters</h2>
            ${endpoint.parameters ? `
            <p style="color: #666; margin-bottom: 10px;">Example query string:</p>
            <div class="code-wrapper">
                <pre><code>${endpoint.parameters}</code></pre>
            </div>
            ` : '<p style="color: #666; margin-top: 10px;">No parameters required.</p>'}
        </div>
        
        <div class="content-card">
            <h2>📝 Example Request</h2>
            <div class="code-block-header">
                <span class="code-block-title">cURL</span>
                <button class="copy-btn" data-copy-target="curl-example">Copy</button>
            </div>
            <div class="code-wrapper">
                <pre id="curl-example">curl -X ${getPrimaryMethod(endpoint.method)} \\
  -H "Accept: application/json" \\
  "${baseUrl}${generateExampleRequest(endpoint)}"</pre>
            </div>
            
            <div class="code-block-header" style="margin-top: 20px;">
                <span class="code-block-title">JavaScript</span>
                <button class="copy-btn" data-copy-target="js-example">Copy</button>
            </div>
            <div class="code-wrapper">
                <pre id="js-example">const response = await fetch('${baseUrl}${generateExampleRequest(endpoint)}', {
  method: '${getPrimaryMethod(endpoint.method)}',
  headers: {
    'Accept': 'application/json'
  }
});
const data = await response.json();</pre>
            </div>
        </div>
        
        <div class="content-card">
            <h2>✨ Example Response</h2>
            <div class="code-block-header">
                <span class="code-block-title">JSON Response</span>
                <button class="copy-btn" data-copy-target="response-example">Copy</button>
            </div>
            <div class="code-wrapper">
                <pre id="response-example">${exampleResponseFormatted}</pre>
            </div>
        </div>
        
        <div class="content-card">
            <h2>🔧 Access Methods</h2>
            
            <div class="json-access">
                <div class="json-access-title">💡 JSON API Access</div>
                <div class="json-access-desc">
                    To get the raw JSON response from the upstream service, include the <code>Accept: application/json</code> header in your request.
                    The server will proxy the request to the upstream URL and return the data.
                </div>
            </div>
            
            <div class="json-access" style="background: #dbeafe; border-left-color: #3b82f6; margin-top: 15px;">
                <div class="json-access-title" style="color: #1e3a8a;">📄 HTML Documentation</div>
                <div class="json-access-desc" style="color: #1e40af;">
                    To view this product page, include the <code>Accept: text/html</code> header or simply visit the URL in your browser.
                </div>
            </div>
            
            <div style="margin-top: 30px; text-align: center;">
                <a href="${endpoint.path}" class="try-it">Try It Now (JSON) →</a>
            </div>
        </div>
        
        <div class="content-card">
            <h2>💳 Web3 Wallet Payment (x402)</h2>
            
            <div id="wallet-status" style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div style="font-size: 32px;">👛</div>
                    <div style="flex: 1;">
                        <div style="font-weight: 600; margin-bottom: 5px;">Wallet Status: <span id="wallet-status-text">Not Connected</span></div>
                        <div style="font-size: 14px; color: #666;" id="wallet-address"></div>
                    </div>
                </div>
            </div>
            
            <div style="display: flex; gap: 10px; margin-bottom: 20px;">
                <button id="connect-phantom-btn" class="try-it" style="flex: 1; text-decoration: none; text-align: center; cursor: pointer; border: none; font-size: 16px;">
                    🔌 Connect Phantom Wallet
                </button>
                <button id="disconnect-wallet-btn" class="try-it" style="flex: 1; text-decoration: none; text-align: center; cursor: pointer; border: none; font-size: 16px; background: #dc3545; display: none;">
                    ❌ Disconnect
                </button>
            </div>
            
            <div id="payment-section" style="display: none;">
                <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    <div style="font-weight: 600; color: #92400e; margin-bottom: 5px;">💰 Payment Required</div>
                    <div style="color: #78350f; font-size: 14px;">
                        This endpoint requires payment via x402 protocol.
                    </div>
                    <div style="margin-top: 10px; font-family: 'Monaco', monospace; font-size: 13px;">
                        <div><strong>Amount:</strong> <span id="payment-amount">-</span></div>
                        <div><strong>Network:</strong> <span id="payment-network">-</span></div>
                        <div><strong>Recipient:</strong> <span id="payment-recipient" style="font-size: 11px; word-break: break-all;">-</span></div>
                    </div>
                </div>
                
                <button id="make-payment-btn" class="try-it" style="width: 100%; text-decoration: none; text-align: center; cursor: pointer; border: none; font-size: 16px; background: linear-gradient(135deg, #10b981 0%, #059669 100%);">
                    💸 Make Payment & Access Endpoint
                </button>
                
                <div id="payment-result" style="margin-top: 20px; display: none;">
                    <div style="background: #1e1e1e; color: #d4d4d4; padding: 20px; border-radius: 8px; font-family: 'Monaco', monospace; font-size: 13px; max-height: 400px; overflow-y: auto;">
                        <pre id="payment-result-content"></pre>
                    </div>
                </div>
            </div>
            
            <div id="install-phantom" style="display: none; background: #fee2e2; border-left: 4px solid #ef4444; padding: 15px; border-radius: 8px; margin-top: 20px;">
                <div style="font-weight: 600; color: #991b1b; margin-bottom: 5px;">⚠️ Phantom Wallet Not Detected</div>
                <div style="color: #7f1d1d; font-size: 14px; margin-bottom: 10px;">
                    Please install Phantom wallet to make Web3 payments.
                </div>
                <a href="https://phantom.app/" target="_blank" rel="noopener" style="color: #dc2626; text-decoration: underline;">
                    Download Phantom Wallet →
                </a>
            </div>
        </div>
        
        <div class="footer">
            <p>Powered by <a href="/">X402 API Gateway</a> | Built with Express + Bun + PM2</p>
        </div>
    </div>
    
    <!-- Load wallet connector first (without Solana Web3.js to avoid conflicts) -->
    <script src="/public/wallet-connector.js"></script>
    <script>
      console.log('✅ Wallet connector loaded');
      console.log('Phantom available:', typeof window.solana !== 'undefined');
    </script>
    
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            // Use event delegation for copy buttons
            document.addEventListener('click', function(e) {
                if (e.target.classList.contains('copy-btn')) {
                    const targetId = e.target.getAttribute('data-copy-target');
                    const element = document.getElementById(targetId);
                    if (element) {
                        const text = element.textContent;
                        navigator.clipboard.writeText(text).then(() => {
                            const originalText = e.target.textContent;
                            e.target.textContent = 'Copied!';
                            e.target.style.background = '#10b981';
                            setTimeout(() => {
                                e.target.textContent = originalText;
                                e.target.style.background = '#667eea';
                            }, 2000);
                        });
                    }
                }
            });
            
            // Wallet connector functionality
            const connectBtn = document.getElementById('connect-phantom-btn');
            const disconnectBtn = document.getElementById('disconnect-wallet-btn');
            const statusText = document.getElementById('wallet-status-text');
            const walletAddress = document.getElementById('wallet-address');
            const paymentSection = document.getElementById('payment-section');
            const installPhantom = document.getElementById('install-phantom');
            const makePaymentBtn = document.getElementById('make-payment-btn');
            const paymentResult = document.getElementById('payment-result');
            const paymentResultContent = document.getElementById('payment-result-content');
            
            // Payment info will be populated from upstream's 402 response
            let paymentInfo = null;
            
            // Check if Phantom is installed
            function checkPhantom() {
                if (!window.walletConnector.isPhantomInstalled()) {
                    installPhantom.style.display = 'block';
                    connectBtn.disabled = true;
                    connectBtn.style.opacity = '0.5';
                    connectBtn.style.cursor = 'not-allowed';
                    return false;
                }
                return true;
            }
            
            // Update UI based on wallet connection status
            function updateWalletUI(connected) {
                if (connected) {
                    statusText.textContent = 'Connected';
                    statusText.style.color = '#10b981';
                    walletAddress.textContent = window.walletConnector.publicKey;
                    connectBtn.style.display = 'none';
                    disconnectBtn.style.display = 'block';
                    paymentSection.style.display = 'block';
                } else {
                    statusText.textContent = 'Not Connected';
                    statusText.style.color = '#666';
                    walletAddress.textContent = '';
                    connectBtn.style.display = 'block';
                    disconnectBtn.style.display = 'none';
                    paymentSection.style.display = 'none';
                }
            }
            
            // Connect wallet
            connectBtn.addEventListener('click', async function() {
                if (!checkPhantom()) return;
                
                connectBtn.disabled = true;
                connectBtn.textContent = '🔄 Connecting...';
                
                console.log('🔄 Attempting to connect to Phantom wallet...');
                
                // Show diagnostics
                const diagnostics = window.walletConnector.getDiagnostics();
                console.log('Phantom Diagnostics:', diagnostics);
                
                const result = await window.walletConnector.connectPhantom();
                
                if (result.success) {
                    updateWalletUI(true);
                    console.log('✅ Wallet connected successfully');
                } else {
                    console.error('❌ Failed to connect:', result.error);
                    
                    // Show diagnostics in console for debugging
                    if (result.details) {
                        console.error('Connection error details:', result.details);
                    }
                    
                    // Show user-friendly alert
                    alert(result.error);
                    
                    connectBtn.disabled = false;
                    connectBtn.textContent = '🔌 Connect Phantom Wallet';
                }
            });
            
            // Disconnect wallet
            disconnectBtn.addEventListener('click', async function() {
                await window.walletConnector.disconnect();
                updateWalletUI(false);
            });
            
            // Make payment
            makePaymentBtn.addEventListener('click', async function() {
                makePaymentBtn.disabled = true;
                makePaymentBtn.textContent = '⏳ Processing Payment...';
                paymentResultContent.textContent = 'Initiating payment...\\nPlease approve the transaction in your wallet...';
                paymentResult.style.display = 'block';
                
                try {
                    const result = await window.walletConnector.makeX402Request(
                        '${endpoint.path}',
                        paymentInfo,
                        {
                            method: '${getPrimaryMethod(endpoint.method)}',
                            headers: {
                                'Accept': 'application/json'
                            }
                        }
                    );
                    
                    if (result.success) {
                        paymentResultContent.textContent = 
                            '✅ Payment Successful!\\n\\n' +
                            'Transaction: ' + result.paymentSignature + '\\n' +
                            'Amount: ' + result.paymentAmount + ' SOL\\n' +
                            'Network: ' + paymentInfo.network + '\\n\\n' +
                            '📡 API Response:\\n' +
                            JSON.stringify(result.data, null, 2);
                    } else {
                        paymentResultContent.textContent = 
                            '❌ Payment Failed\\n\\n' +
                            'Error: ' + result.error;
                    }
                } catch (error) {
                    paymentResultContent.textContent = 
                        '❌ Error\\n\\n' + error.message;
                } finally {
                    makePaymentBtn.disabled = false;
                    makePaymentBtn.textContent = '💸 Make Payment & Access Endpoint';
                }
            });
            
            // Wallet event handlers
            window.walletConnector.onAccountChanged = function(publicKey) {
                walletAddress.textContent = publicKey;
            };
            
            window.walletConnector.onDisconnect = function() {
                updateWalletUI(false);
            };
            
            // Check Phantom on load
            checkPhantom();
        });
    </script>
</body>
</html>
  `.trim();
}

/**
 * Generate HTML page for listing all agents
 */
export function generateAgentsListPage(agents, baseUrl = 'http://localhost:3000') {
  const agentCards = agents.map(agent => {
    // Groups are internal - only show endpoint count
    const endpointCount = (agent.groups || []).reduce((total, group) => 
      total + group.endpoints.length, 0
    );
    return `
      <a href="/agents/${agent.id}" class="agent-card">
        <div class="agent-icon">${agent.icon}</div>
        <h3>${agent.name}</h3>
        <p>${agent.description}</p>
        <div class="endpoint-count">${endpointCount} endpoint${endpointCount !== 1 ? 's' : ''}</div>
      </a>
    `;
  }).join('');

  return `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/svg+xml" href="/favicon.ico">
    <title>Available Agents - X402 API Gateway</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 50px;
        }
        
        .header h1 {
            font-size: 48px;
            margin-bottom: 15px;
        }
        
        .header p {
            font-size: 20px;
            opacity: 0.9;
        }
        
        .agents-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 30px;
            margin-bottom: 40px;
        }
        
        .agent-card {
            background: white;
            border-radius: 16px;
            padding: 40px;
            text-decoration: none;
            color: inherit;
            transition: transform 0.3s, box-shadow 0.3s;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
        }
        
        .agent-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 50px rgba(0, 0, 0, 0.2);
        }
        
        .agent-icon {
            font-size: 64px;
            margin-bottom: 20px;
        }
        
        .agent-card h3 {
            font-size: 24px;
            color: #1a1a1a;
            margin-bottom: 12px;
        }
        
        .agent-card p {
            color: #666;
            font-size: 16px;
            line-height: 1.6;
            margin-bottom: 20px;
        }
        
        .endpoint-count {
            color: #667eea;
            font-weight: 600;
            font-size: 14px;
        }
        
        .footer {
            text-align: center;
            color: white;
            padding: 20px;
        }
        
        .breadcrumb {
            text-align: center;
            color: white;
            margin-bottom: 30px;
            font-size: 14px;
        }
        
        .breadcrumb a {
            color: white;
            text-decoration: none;
        }
        
        .breadcrumb a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="breadcrumb">
            <a href="/">Home</a> / Agents
        </div>
        
        <div class="header">
            <h1>🚀 Available Agents</h1>
            <p>Choose an agent to explore its endpoints</p>
        </div>
        
        <div class="agents-grid">
            ${agentCards}
        </div>
        
        <div class="footer">
            <p>Powered by X402 API Gateway | Built with Express + Bun + PM2</p>
        </div>
    </div>
</body>
</html>
  `.trim();
}

/**
 * Generate HTML page for a specific agent
 */
export function generateAgentDetailPage(agent, baseUrl = 'http://localhost:3000') {
  // Flatten endpoints from all groups - groups are internal only
  const allEndpoints = [];
  for (const group of (agent.groups || [])) {
    allEndpoints.push(...group.endpoints);
  }
  
  const endpointCards = allEndpoints.map(endpoint => `
    <a href="${endpoint.path}" class="endpoint-card">
      <div class="endpoint-header">
        <h3>${endpoint.name}</h3>
        ${generateMethodBadges(endpoint.method)}
      </div>
      <p class="endpoint-description">${endpoint.description}</p>
      <code class="endpoint-path">${endpoint.path}</code>
    </a>
  `).join('');

  return `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/svg+xml" href="/favicon.ico">
    <title>${agent.name} - X402 API Gateway</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .breadcrumb {
            color: white;
            margin-bottom: 30px;
            font-size: 14px;
        }
        
        .breadcrumb a {
            color: white;
            text-decoration: none;
        }
        
        .breadcrumb a:hover {
            text-decoration: underline;
        }
        
        .header {
            background: white;
            border-radius: 16px;
            padding: 40px;
            margin-bottom: 40px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
        }
        
        .header-content {
            display: flex;
            align-items: center;
            gap: 20px;
        }
        
        .agent-icon {
            font-size: 80px;
        }
        
        .header h1 {
            font-size: 42px;
            color: #1a1a1a;
            margin-bottom: 10px;
        }
        
        .header p {
            font-size: 18px;
            color: #666;
        }
        
        .endpoints-section h2 {
            color: white;
            font-size: 32px;
            margin-bottom: 40px;
            text-align: center;
        }
        
        .endpoints-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 25px;
        }
        
        .endpoint-card {
            background: white;
            border-radius: 12px;
            padding: 30px;
            text-decoration: none;
            color: inherit;
            transition: transform 0.3s, box-shadow 0.3s;
            box-shadow: 0 5px 20px rgba(0, 0, 0, 0.1);
        }
        
        .endpoint-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
        }
        
        .endpoint-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 15px;
            gap: 15px;
        }
        
        .endpoint-card h3 {
            font-size: 20px;
            color: #1a1a1a;
        }
        
        .method-badge {
            padding: 4px 12px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            white-space: nowrap;
        }
        
        .method-get {
            background: #10b981;
            color: white;
        }
        
        .method-post {
            background: #3b82f6;
            color: white;
        }
        
        .endpoint-description {
            color: #666;
            font-size: 15px;
            line-height: 1.6;
            margin-bottom: 15px;
        }
        
        .endpoint-path {
            display: block;
            background: #f5f5f5;
            padding: 8px 12px;
            border-radius: 6px;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            color: #e83e8c;
        }
        
        .footer {
            text-align: center;
            color: white;
            margin-top: 50px;
            padding: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="breadcrumb">
            <a href="/">Home</a> / <a href="/agents">Agents</a> / ${agent.name}
        </div>
        
        <div class="header">
            <div class="header-content">
                <div class="agent-icon">${agent.icon}</div>
                <div>
                    <h1>${agent.name}</h1>
                    <p>${agent.description}</p>
                </div>
            </div>
        </div>
        
        <div class="endpoints-section">
            <h2>Endpoints</h2>
            <div class="endpoints-grid">
                ${endpointCards}
            </div>
        </div>
        
        <div class="footer">
            <p>Powered by X402 API Gateway | Built with Express + Bun + PM2</p>
        </div>
    </div>
</body>
</html>
  `.trim();
}

