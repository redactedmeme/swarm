/**
 * X402 Web3 Wallet Connector
 * Supports Phantom and other Solana wallets
 */

class WalletConnector {
  constructor() {
    this.wallet = null;
    this.publicKey = null;
    this.connected = false;
    this.network = 'devnet'; // default network
  }

  /**
   * Check if Phantom wallet is installed
   */
  isPhantomInstalled() {
    return typeof window !== 'undefined' && 
           window.solana && 
           window.solana.isPhantom;
  }

  /**
   * Get Phantom diagnostic info
   */
  getDiagnostics() {
    return {
      phantomExists: typeof window !== 'undefined' && !!window.solana,
      isPhantom: window.solana?.isPhantom || false,
      isConnected: window.solana?.isConnected || false,
      hasPublicKey: !!window.solana?.publicKey,
      publicKey: window.solana?.publicKey?.toString() || null,
      hasConnectMethod: typeof window.solana?.connect === 'function',
      version: window.solana?.version || 'unknown'
    };
  }

  /**
   * Wait for Phantom to be ready
   */
  async waitForPhantom(maxAttempts = 10) {
    for (let i = 0; i < maxAttempts; i++) {
      if (this.isPhantomInstalled() && window.solana.isConnected !== undefined) {
        return true;
      }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    return this.isPhantomInstalled();
  }

  /**
   * Connect to Phantom wallet (pure Phantom API, no Solana Web3.js dependency)
   */
  async connectPhantom() {
    try {
      // Wait for Phantom to be ready
      const isReady = await this.waitForPhantom();
      
      if (!isReady) {
        throw new Error('Phantom wallet is not installed or not ready. Please install it from https://phantom.app/');
      }

      console.log('Attempting to connect to Phantom...');
      console.log('Phantom object:', window.solana);
      console.log('Available methods:', Object.keys(window.solana).filter(k => typeof window.solana[k] === 'function'));
      
      // Check if already connected
      if (window.solana.isConnected) {
        console.log('Phantom is already connected');
        this.wallet = window.solana;
        this.publicKey = window.solana.publicKey.toString();
        this.connected = true;
        
        return {
          success: true,
          publicKey: this.publicKey
        };
      }
      
      // Check if wallet is locked - BLOCK connection attempt if locked
      if (window.solana._publicKey === null && !window.solana.isConnected) {
        console.error('⚠️ IMPORTANT: Phantom is LOCKED!');
        console.error('👉 Please click the Phantom extension icon and unlock your wallet');
        console.error('👉 Enter your password if prompted');
        console.error('👉 Then try connecting again');
        
        throw new Error('❌ Phantom wallet is locked! Please unlock your wallet first:\n\n' +
          '1️⃣ Click the Phantom extension icon in your browser\n' +
          '2️⃣ Enter your password to unlock\n' +
          '3️⃣ Wait for your balance to appear\n' +
          '4️⃣ Then click "Connect Phantom Wallet" again\n\n' +
          'Your wallet must be unlocked before connecting.');
      }

      // Try different connection methods
      let resp;
      let method = 'unknown';
      
      // Method 1: Try the newer signIn API if available
      if (typeof window.solana.signIn === 'function') {
        try {
          console.log('Trying Phantom signIn API (recommended)...');
          const domain = window.location.host;
          const result = await window.solana.signIn({
            statement: 'Sign in to X402 Gateway',
          });
          resp = { publicKey: result.publicKey || result.account?.publicKey || window.solana.publicKey };
          method = 'signIn';
          console.log('✅ Connected via signIn:', result);
        } catch (error) {
          console.log('signIn failed:', error.message);
        }
      }
      
      // Method 2: Try using request API
      if (!resp && typeof window.solana.request === 'function') {
        try {
          console.log('Trying Phantom request API...');
          const result = await window.solana.request({ 
            method: 'connect',
            params: {
              onlyIfTrusted: false
            }
          });
          resp = { publicKey: result?.publicKey || window.solana.publicKey };
          method = 'request';
          console.log('✅ Connected via request API:', result);
        } catch (error) {
          console.log('request API failed:', error.message);
        }
      }
      
      // Method 3: Direct property access (if already connected)
      if (!resp && window.solana.publicKey) {
        console.log('Using existing connection...');
        resp = { publicKey: window.solana.publicKey };
        method = 'existing';
      }
      
      // Method 4: Standard connect (last resort)
      if (!resp) {
        console.log('Trying standard connect() as last resort...');
        try {
          const connectResult = await window.solana.connect();
          resp = connectResult;
          method = 'standard';
          console.log('✅ Connected via standard connect');
        } catch (error) {
          console.error('Standard connect failed:', error);
          throw new Error('All connection methods failed. Error: ' + error.message);
        }
      }
      
      console.log('Connection successful via:', method);
      
      if (!resp || !resp.publicKey) {
        throw new Error('No public key received from Phantom');
      }
      
      this.wallet = window.solana;
      this.publicKey = resp.publicKey.toString();
      this.connected = true;

      console.log('✅ Connected to wallet:', this.publicKey);
      
      // Listen for account changes
      if (window.solana.on) {
        window.solana.on('accountChanged', (publicKey) => {
          if (publicKey) {
            this.publicKey = publicKey.toString();
            console.log('Account changed to:', this.publicKey);
            this.onAccountChanged && this.onAccountChanged(this.publicKey);
          } else {
            this.disconnect();
          }
        });

        // Listen for disconnect
        window.solana.on('disconnect', () => {
          console.log('Wallet disconnected');
          this.disconnect();
        });
      }

      return {
        success: true,
        publicKey: this.publicKey
      };
    } catch (error) {
      console.error('❌ Failed to connect wallet:', error);
      
      // Provide more helpful error messages
      let errorMessage = error.message || 'Unknown error';
      
      if (error.message && error.message.includes('User rejected')) {
        errorMessage = 'Connection rejected. Please approve the connection in Phantom.';
      } else if (error.code === 4001) {
        errorMessage = 'Connection rejected by user.';
      } else if (error.code === -32002) {
        errorMessage = 'Please check Phantom - a connection request may already be pending.';
      } else if (!this.isPhantomInstalled()) {
        errorMessage = 'Phantom wallet not found. Please install it from https://phantom.app/';
      }
      
      return {
        success: false,
        error: errorMessage,
        details: error
      };
    }
  }

  /**
   * Disconnect wallet
   */
  async disconnect() {
    if (this.wallet && this.wallet.disconnect) {
      await this.wallet.disconnect();
    }
    this.wallet = null;
    this.publicKey = null;
    this.connected = false;
    this.onDisconnect && this.onDisconnect();
  }

  /**
   * Load Solana Web3.js dynamically
   */
  async loadSolanaWeb3() {
    if (typeof window.solanaWeb3 !== 'undefined') {
      return; // Already loaded
    }
    
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://unpkg.com/@solana/web3.js@1.87.6/lib/index.iife.min.js';
      script.onload = () => {
        console.log('✅ Solana Web3.js loaded dynamically');
        resolve();
      };
      script.onerror = () => {
        reject(new Error('Failed to load Solana Web3.js'));
      };
      document.head.appendChild(script);
    });
  }

  /**
   * Sign and send a payment transaction
   * @param {string} recipient - Recipient address
   * @param {number} amount - Amount in lamports
   * @param {string} network - Network (mainnet-beta/devnet/testnet)
   */
  async sendPayment(recipient, amount, network = 'devnet') {
    if (!this.connected) {
      throw new Error('Wallet not connected');
    }

    try {
      // Check if Solana Web3 is loaded
      if (typeof window.solanaWeb3 === 'undefined') {
        // Load Solana Web3.js dynamically when needed
        console.log('Loading Solana Web3.js...');
        await this.loadSolanaWeb3();
      }
      
      // Import Solana web3 from CDN (loaded dynamically or already in page)
      const { 
        Connection, 
        PublicKey, 
        Transaction, 
        SystemProgram,
        LAMPORTS_PER_SOL 
      } = window.solanaWeb3;

      // Determine RPC endpoint
      let endpoint;
      switch (network) {
        case 'mainnet':
        case 'mainnet-beta':
          endpoint = 'https://api.mainnet-beta.solana.com';
          break;
        case 'testnet':
          endpoint = 'https://api.testnet.solana.com';
          break;
        case 'devnet':
        default:
          endpoint = 'https://api.devnet.solana.com';
      }

      const connection = new Connection(endpoint, 'confirmed');
      
      // Create transaction
      const transaction = new Transaction().add(
        SystemProgram.transfer({
          fromPubkey: new PublicKey(this.publicKey),
          toPubkey: new PublicKey(recipient),
          lamports: amount
        })
      );

      // Get recent blockhash
      const { blockhash } = await connection.getLatestBlockhash('confirmed');
      transaction.recentBlockhash = blockhash;
      transaction.feePayer = new PublicKey(this.publicKey);

      // Sign and send transaction
      const signed = await this.wallet.signTransaction(transaction);
      const signature = await connection.sendRawTransaction(signed.serialize());

      // Wait for confirmation
      await connection.confirmTransaction(signature, 'confirmed');

      return {
        success: true,
        signature,
        amount,
        recipient,
        network
      };
    } catch (error) {
      console.error('Payment failed:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Sign a message with the wallet
   * @param {string} message - Message to sign
   */
  async signMessage(message) {
    if (!this.connected) {
      throw new Error('Wallet not connected');
    }

    try {
      const encodedMessage = new TextEncoder().encode(message);
      const signedMessage = await this.wallet.signMessage(encodedMessage, 'utf8');
      
      // Convert to base58
      const signature = window.bs58.encode(signedMessage.signature);

      return {
        success: true,
        signature,
        publicKey: this.publicKey,
        message
      };
    } catch (error) {
      console.error('Failed to sign message:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Make an x402 payment request
   * @param {string} endpoint - API endpoint URL
   * @param {object} paymentInfo - Payment information from x402 response
   * @param {object} options - Request options (method, body, etc.)
   */
  async makeX402Request(endpoint, paymentInfo, options = {}) {
    if (!this.connected) {
      return {
        success: false,
        error: 'Wallet not connected'
      };
    }

    try {
      const { LAMPORTS_PER_SOL } = window.solanaWeb3;
      
      // Convert amount to lamports
      const amountLamports = Math.floor(parseFloat(paymentInfo.maxAmountRequired) * LAMPORTS_PER_SOL);

      // Send payment
      const paymentResult = await this.sendPayment(
        paymentInfo.payTo,
        amountLamports,
        paymentInfo.network || 'devnet'
      );

      if (!paymentResult.success) {
        return paymentResult;
      }

      // Create timestamp for payment proof
      const timestamp = new Date().toISOString();
      
      // Create payment proof message
      const proofMessage = `x402-payment:${paymentResult.signature}:${timestamp}`;
      
      // Sign the proof message
      const signResult = await this.signMessage(proofMessage);
      
      if (!signResult.success) {
        return {
          success: false,
          error: 'Failed to sign payment proof'
        };
      }

      // Make the actual API request with payment headers
      const headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'x-payment-id': paymentResult.signature,
        'x-payment-signature': signResult.signature,
        'x-payment-timestamp': timestamp,
        'x-payment-network': paymentInfo.network || 'devnet',
        'x-payment-amount': paymentInfo.maxAmountRequired,
        'x-payment-hash': paymentResult.signature,
        'x-wallet-pubkey': this.publicKey,
        ...(options.headers || {})
      };

      const response = await fetch(endpoint, {
        method: options.method || 'GET',
        headers,
        ...(options.body && { body: JSON.stringify(options.body) })
      });

      const data = await response.json();

      return {
        success: response.ok,
        statusCode: response.status,
        data,
        paymentSignature: paymentResult.signature,
        paymentAmount: paymentInfo.maxAmountRequired
      };
    } catch (error) {
      return {
        success: false,
        error: error.message
      };
    }
  }
}

// Create global instance
window.walletConnector = new WalletConnector();

