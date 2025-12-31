/**
 * EVM Wallet Connector (MetaMask, Coinbase Wallet, etc.)
 * Supports Ethereum, Base, Polygon, Arbitrum, Optimism
 */

class EVMWalletConnector {
  constructor() {
    this.wallet = null;
    this.address = null;
    this.connected = false;
    this.chainId = null;
    this.chainName = 'Unknown';
  }

  // Chain configurations
  static CHAINS = {
    1: { name: 'Ethereum Mainnet', symbol: 'ETH', decimals: 18 },
    8453: { name: 'Base', symbol: 'ETH', decimals: 18 },
    137: { name: 'Polygon', symbol: 'MATIC', decimals: 18 },
    42161: { name: 'Arbitrum One', symbol: 'ETH', decimals: 18 },
    10: { name: 'Optimism', symbol: 'ETH', decimals: 18 },
    5: { name: 'Goerli Testnet', symbol: 'ETH', decimals: 18 },
    84532: { name: 'Base Sepolia', symbol: 'ETH', decimals: 18 },
  };

  /**
   * Check if MetaMask or other EVM wallet is installed
   */
  isWalletInstalled() {
    return typeof window !== 'undefined' && typeof window.ethereum !== 'undefined';
  }

  /**
   * Get wallet provider name
   */
  getWalletName() {
    if (!window.ethereum) return 'None';
    if (window.ethereum.isMetaMask) return 'MetaMask';
    if (window.ethereum.isCoinbaseWallet) return 'Coinbase Wallet';
    if (window.ethereum.isRabby) return 'Rabby';
    return 'EVM Wallet';
  }

  /**
   * Get diagnostics
   */
  getDiagnostics() {
    return {
      walletExists: this.isWalletInstalled(),
      walletName: this.getWalletName(),
      isConnected: this.connected,
      hasAddress: !!this.address,
      address: this.address,
      chainId: this.chainId,
      chainName: this.chainName
    };
  }

  /**
   * Connect to EVM wallet
   */
  async connect() {
    try {
      if (!this.isWalletInstalled()) {
        throw new Error('No EVM wallet found. Please install MetaMask from https://metamask.io/');
      }

      console.log('Attempting to connect to', this.getWalletName(), '...');

      // Request account access
      const accounts = await window.ethereum.request({ 
        method: 'eth_requestAccounts' 
      });

      if (!accounts || accounts.length === 0) {
        throw new Error('No accounts found');
      }

      this.wallet = window.ethereum;
      this.address = accounts[0];
      this.connected = true;

      // Get chain info
      const chainId = await window.ethereum.request({ method: 'eth_chainId' });
      this.chainId = parseInt(chainId, 16);
      this.chainName = EVMWalletConnector.CHAINS[this.chainId]?.name || `Chain ${this.chainId}`;

      console.log('✅ Connected to', this.getWalletName());
      console.log('Address:', this.address);
      console.log('Chain:', this.chainName, `(${this.chainId})`);

      // Listen for account changes
      window.ethereum.on('accountsChanged', (accounts) => {
        if (accounts.length === 0) {
          this.disconnect();
        } else {
          this.address = accounts[0];
          console.log('Account changed to:', this.address);
          this.onAccountChanged && this.onAccountChanged(this.address);
        }
      });

      // Listen for chain changes
      window.ethereum.on('chainChanged', (chainId) => {
        this.chainId = parseInt(chainId, 16);
        this.chainName = EVMWalletConnector.CHAINS[this.chainId]?.name || `Chain ${this.chainId}`;
        console.log('Chain changed to:', this.chainName);
        this.onChainChanged && this.onChainChanged(this.chainId, this.chainName);
      });

      return {
        success: true,
        address: this.address,
        chainId: this.chainId,
        chainName: this.chainName,
        walletName: this.getWalletName()
      };
    } catch (error) {
      console.error('❌ Failed to connect wallet:', error);

      let errorMessage = error.message || 'Unknown error';

      if (error.code === 4001) {
        errorMessage = 'Connection rejected by user.';
      } else if (error.code === -32002) {
        errorMessage = 'Please check your wallet - a connection request may already be pending.';
      } else if (!this.isWalletInstalled()) {
        errorMessage = 'No EVM wallet found. Please install MetaMask from https://metamask.io/';
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
    this.wallet = null;
    this.address = null;
    this.connected = false;
    this.chainId = null;
    this.chainName = 'Unknown';
    this.onDisconnect && this.onDisconnect();
    console.log('🔌 Wallet disconnected');
  }

  /**
   * Send payment transaction
   */
  async sendPayment(recipient, amount, chainId = null) {
    if (!this.connected) {
      throw new Error('Wallet not connected');
    }

    try {
      // Switch chain if needed
      if (chainId && chainId !== this.chainId) {
        await this.switchChain(chainId);
      }

      // Convert amount to wei (assuming ETH/native token)
      const amountWei = '0x' + Math.floor(amount * 1e18).toString(16);

      // Send transaction
      const txHash = await window.ethereum.request({
        method: 'eth_sendTransaction',
        params: [{
          from: this.address,
          to: recipient,
          value: amountWei,
        }],
      });

      console.log('✅ Transaction sent:', txHash);

      return {
        success: true,
        txHash,
        amount,
        recipient,
        chainId: this.chainId,
        chainName: this.chainName
      };
    } catch (error) {
      console.error('❌ Payment failed:', error);
      return {
        success: false,
        error: error.message || 'Transaction failed',
        details: error
      };
    }
  }

  /**
   * Switch to a different chain
   */
  async switchChain(chainId) {
    try {
      await window.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: '0x' + chainId.toString(16) }],
      });
      
      this.chainId = chainId;
      this.chainName = EVMWalletConnector.CHAINS[chainId]?.name || `Chain ${chainId}`;
      
      return { success: true };
    } catch (error) {
      // Chain not added, try to add it
      if (error.code === 4902) {
        return await this.addChain(chainId);
      }
      throw error;
    }
  }

  /**
   * Add a new chain to wallet
   */
  async addChain(chainId) {
    const chainConfig = this.getChainConfig(chainId);
    
    try {
      await window.ethereum.request({
        method: 'wallet_addEthereumChain',
        params: [chainConfig],
      });
      
      return { success: true };
    } catch (error) {
      console.error('Failed to add chain:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Get chain configuration for adding
   */
  getChainConfig(chainId) {
    const configs = {
      8453: {
        chainId: '0x2105',
        chainName: 'Base',
        nativeCurrency: { name: 'Ethereum', symbol: 'ETH', decimals: 18 },
        rpcUrls: ['https://mainnet.base.org'],
        blockExplorerUrls: ['https://basescan.org']
      },
      84532: {
        chainId: '0x14a34',
        chainName: 'Base Sepolia',
        nativeCurrency: { name: 'Ethereum', symbol: 'ETH', decimals: 18 },
        rpcUrls: ['https://sepolia.base.org'],
        blockExplorerUrls: ['https://sepolia.basescan.org']
      },
      137: {
        chainId: '0x89',
        chainName: 'Polygon',
        nativeCurrency: { name: 'MATIC', symbol: 'MATIC', decimals: 18 },
        rpcUrls: ['https://polygon-rpc.com'],
        blockExplorerUrls: ['https://polygonscan.com']
      }
    };

    return configs[chainId] || null;
  }

  /**
   * Sign a message
   */
  async signMessage(message) {
    if (!this.connected) {
      throw new Error('Wallet not connected');
    }

    try {
      const signature = await window.ethereum.request({
        method: 'personal_sign',
        params: [message, this.address],
      });

      return {
        success: true,
        signature,
        message,
        address: this.address
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
window.evmWalletConnector = new EVMWalletConnector();

