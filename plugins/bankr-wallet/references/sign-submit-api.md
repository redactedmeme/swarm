# Sign & Submit API

Low-level wallet endpoints for cryptographic operations and transaction broadcasting.

## Endpoints

### POST /wallet/sign

Supports three signature types:

1. **personal_sign** — plain text message authentication / identity verification
2. **eth_signTypedData_v4** — EIP-712 typed data (e.g. permit approvals)
3. **eth_signTransaction** — pre-sign transaction before submission

Response returns signature, signer address, and signature type.

### POST /wallet/submit

Broadcast a signed transaction directly to the blockchain.

Request fields: recipient address, chain ID, value, calldata.

Supports:
- `waitForConfirmation: false` — fire-and-forget
- `waitForConfirmation: true` — wait and return final status

Transaction statuses: `success`, `reverted`, `pending`.

## Requirements

Both endpoints require:
- API key with write permissions (`walletApiEnabled: true`)
- IP allowlist enforcement

## Deprecated Endpoints

`/agent/sign` and `/agent/submit` still work but are deprecated — use `/wallet/sign` and `/wallet/submit` for all new code.
